#!/usr/bin/env python3
"""VL/VV evaluator frontend: six-frame entity detection and global entity ledger.

The executable stages are deliberately restartable and append-only:
  extract -> prepare -> detect -> match -> dino_prepare -> dino -> attach_dino

`detect` runs WeDetect-Anything once per keyframe, isolated per-shot Luna-low
clustering, then shot-level binding plus one targeted Grounding-DINO recovery.
It never retries WeDetect-Anything during recovery.  Binding protocol v2
(default since 2026-11-02, open-questions Q12) lets several local entities of
one shot bind to the same contract entity when the contract text describes
several items or members; the ledger then keeps all of them as occurrences of
that one specified entity in that shot.  `--binding-protocol v1` keeps at most
one local entity per contract entity and shot.

`match` builds the episode ledger. Matching v2 (default, owner decision
2026-11-01): specified entities stay linked by contract ID; every unbound
occurrence is merged with others into one unspecified entity, kept alone, or
merged into a specified entity, by the most likely reading of the episode
(prompt text, shot settings, relations to anchor entities, keyframes with
drawn boxes). A specified entity that states several items or members may
receive missed members from a shot where other members are already bound
(owner decision 2026-11-02, open-questions Q13); an unspecified entity keeps
at most one occurrence per shot. `--matching-protocol v1` keeps the
historical visual matcher.
"""
import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_wedetect_shot_entities as wedetect
import gs_shot_prompt_recovery as recovery
import gpu_lock
import gs_prompt_binding as transport
import vl_vv_repair_loop as repair_loop
import run_vl_vv_issue_discovery as issue_discovery
import episode_shot_segments as shot_segments
import episode_contract as contract_io
from gs_consistency_contract import arr, enum, obj, S

MODEL = 'gpt-6-luna'
REASONING = 'low'
PROTOCOL = 'vl_vv_detection_v1'
EPISODE_SCHEMA = ROOT / 'schemas/vl-vv-episode-entities-v1.schema.json'
# Simplified ledger written by matching v2 (2026-11-01); matching v1 keeps the v1 ledger.
LEDGER_V2 = 'vl_vv_entity_ledger_v2'
EPISODE_SCHEMA_V2 = ROOT / 'schemas/vl-vv-episode-entities-v2.schema.json'


def read(path):
    return json.loads(Path(path).read_text())


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha256_json(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def schedule_sort_key(key):
    nums = tuple(int(x) for x in re.findall(r'\d+', key))
    return nums if nums else (10**9, key)


def normalize_contract(contract, shots):
    """Turn a contract schedule into a stable-ID prompt registry.

    entity_schedule contains display names, while entity_descriptions owns the
    cross-shot instance identifiers (for example Character 2). A display name
    must resolve to exactly one such identifier. Failing fast is intentional:
    inventing a name-derived ID loses the contract identity semantics before
    cross-shot matching begins.  A v2 contract keys entities by ID directly.
    """
    if contract_io.is_v2(contract):
        return contract_io.prompt_registry(contract, shots)
    schedule = contract.get('entity_schedule')
    if not isinstance(schedule, dict) or not schedule:
        raise ValueError('contract.json requires a nonempty entity_schedule object')
    shot_ids = [s['shot_id'] for s in shots]
    direct = all(sid in schedule for sid in shot_ids)
    if direct:
        key_by_shot = {sid: sid for sid in shot_ids}; mapping = 'shot_id_exact'
    else:
        keys = sorted(schedule, key=schedule_sort_key)
        if len(keys) != len(shots):
            raise ValueError('Cannot infer contract schedule mapping: provide manifest schedule_key per shot or equal shot counts')
        explicit = [s.get('schedule_key') for s in shots]
        if any(explicit) and (not all(explicit) or set(explicit) != set(schedule)):
            raise ValueError('schedule_key must be present and cover contract entity_schedule exactly once')
        key_by_shot = {s['shot_id']: s.get('schedule_key', key) for s, key in zip(shots, keys)}
        mapping = 'manifest_schedule_key' if all(explicit) else 'manifest_order_to_sorted_contract_keys'
    names, category_by_name = [], {}
    for sid in shot_ids:
        row = schedule[key_by_shot[sid]]
        if not isinstance(row, dict):
            raise ValueError(f'entity_schedule[{key_by_shot[sid]}] must be an object')
        for category, values in row.items():
            if not isinstance(values, list):
                raise ValueError(f'entity_schedule[{key_by_shot[sid]}].{category} must be a list')
            for name in values:
                if not isinstance(name, str) or not name.strip():
                    raise ValueError('Schedule entity names must be nonempty strings')
                name = name.strip()
                if name not in category_by_name:
                    names.append(name); category_by_name[name] = category
                elif category_by_name[name] != category:
                    category_by_name[name] = 'mixed'
    descriptions = contract.get('entity_descriptions', {})
    if not isinstance(descriptions, dict) or not descriptions:
        raise ValueError('contract.json requires entity_descriptions with stable cross-shot instance IDs')
    ids_by_name = {}
    for entity_id, row in descriptions.items():
        if not isinstance(entity_id, str) or not entity_id.strip() or not isinstance(row, dict):
            raise ValueError('entity_descriptions must map stable string IDs to objects')
        display = row.get('name')
        if not isinstance(display, str) or not display.strip():
            raise ValueError(f'entity_descriptions[{entity_id!r}].name must be a nonempty display name')
        ids_by_name.setdefault(display.strip(), []).append(entity_id)
    facts = []
    for sid in shot_ids:
        values = []
        for category, items in schedule[key_by_shot[sid]].items():
            values += [str(x).strip() for x in items]
        facts.append(dict(fact_id=sid, shot_id=sid, text='; '.join(values) or '(no scheduled entities)'))
    fact_text = {f['fact_id']: f['text'] for f in facts}
    entities = []
    for name in names:
        ids = ids_by_name.get(name, [])
        if len(ids) != 1:
            raise ValueError(f'Scheduled name {name!r} must resolve to exactly one entity_descriptions ID; found {ids!r}')
        pid = ids[0]
        description_row = descriptions[pid]
        sched = []
        for sid in shot_ids:
            listed = any(name == str(x).strip() for xs in schedule[key_by_shot[sid]].values() for x in xs)
            sched.append(dict(shot_id=sid, expectation='required' if listed else 'not_required',
                              reason='Listed in contract.entity_schedule.' if listed else 'Not listed in contract.entity_schedule.'))
        entities.append(dict(prompt_entity_id=pid, contract_entity_id=pid, name=name,
            description=str(description_row.get('description', name)).strip() or name,
            contract_category=category_by_name[name],
            evidence=[dict(fact_id=sid, quote=name) for sid in shot_ids if name in fact_text[sid]],
            schedule=sched))
    return dict(schema_version='prompt_registry_v1', source='contract.entity_schedule', shot_ids=shot_ids,
                mapping=dict(method=mapping, contract_schedule_key_by_shot=key_by_shot), entities=entities)

def require_api():
    if os.environ.get('EECBENCH_CODEX_BACKEND') != 'api':
        raise RuntimeError('Run under EECBench/scripts/openai_api_env.sh; this frontend requires the configured API transport')
    if os.environ.get('EECBENCH_API_MODEL', MODEL) != MODEL:
        raise RuntimeError(f'This frontend is pinned to {MODEL}; set EECBENCH_API_MODEL={MODEL}')


def extract_six(video_index, frames_out, manifest_out):
    """Extract six timestamps per already-separated shot clip with ffmpeg."""
    index = read(video_index)
    rows = index['shots'] if isinstance(index, dict) else index
    if not isinstance(rows, list) or not rows: raise ValueError('video index must be a nonempty list or {shots:[...]}')
    out = Path(frames_out).resolve(); manifest_out = Path(manifest_out).resolve()
    if out.exists() or manifest_out.exists(): raise FileExistsError('Use fresh frame and manifest outputs')
    shots=[]
    for item in rows:
        sid, video = item.get('shot_id'), Path(item.get('video_path','')).resolve()
        if not sid or not video.is_file(): raise ValueError('Every video-index row needs shot_id and existing video_path')
        ffprobe, ffmpeg = shutil.which('ffprobe'), shutil.which('ffmpeg')
        if ffprobe and ffmpeg:
            probe = subprocess.check_output([ffprobe,'-v','error','-show_entries','format=duration','-of','default=nokey=1:noprint_wrappers=1',str(video)], text=True)
            duration=float(probe.strip())
        else:
            # Some allocated compute images intentionally omit system ffmpeg.
            # imageio-ffmpeg ships a self-contained decoder in the Python env.
            try:
                import imageio_ffmpeg
                _, duration = imageio_ffmpeg.count_frames_and_secs(str(video))
                ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            except Exception as exc:
                raise RuntimeError('Video extraction requires system ffmpeg/ffprobe or imageio-ffmpeg') from exc
        if duration <= 0: raise ValueError(f'Nonpositive duration: {video}')
        # The exact container duration is end-exclusive for decoders. Keep
        # the final sample one short decode interval before it, while retaining
        # the intended start-to-end uniform coverage.
        last_time=max(0.0, duration-max(0.25, duration*0.05))
        frames=[]
        for i, ts in enumerate(last_time*j/5 for j in range(6)):
            path=out/sid/f'frame_{i:06d}.jpg'; path.parent.mkdir(parents=True,exist_ok=True)
            subprocess.run([ffmpeg,'-v','error','-ss',f'{ts:.9f}','-i',str(video),'-frames:v','1','-q:v','2','-y',str(path)],check=True)
            if not path.is_file(): raise RuntimeError(f'Frame decoder produced no image at {ts:.6f}s: {video}')
            frames.append(dict(frame_id=i, timestamp_sec=ts, path=str(path), sha256=sha(path)))
        shots.append(dict(shot_id=sid, video_path=str(video), frames=frames))
    dump(manifest_out,dict(shots=shots, keyframe_policy='six uniform timestamps from clip start through a decoder-safe point before the container end'))


def narrative_for(registry, shot_ids, v2):
    """The narrative.json content of a prompt registry: per shot, the names of the entities it must show.

    A pure function of the contract (shared by prepare and the episode requirement compiler)."""
    facts=[dict(fact_id=sid,shot_id=sid,text='; '.join(e['name'] for e in registry['entities'] if next(x for x in e['schedule'] if x['shot_id']==sid)['expectation']=='required') or '(no scheduled entities)') for sid in shot_ids]
    # Contract v2: entities listed in no presence list are in the registry too (Q16); this fact is their evidence.
    extra=contract_io.no_presence_fact(registry) if v2 else None
    return dict(facts=facts+([extra] if extra else []))


def prepare(manifest_path, contract_path, case, allow_legacy_keyframes=False, prompt_path=None, allow_v1_contract=False, compiled=None):
    """Freeze a case. A v2 contract (with evidence, or without it plus prompt_path) is stored model-facing with prompt.json."""
    manifest_path, contract_path, case = map(lambda p: Path(p).resolve(), (manifest_path, contract_path, case))
    if case.exists(): raise FileExistsError('Use a fresh case directory')
    raw = read(manifest_path); shots = raw.get('shots')
    shot_segments.require_record_segmentation(raw, allow_legacy_keyframes, where=str(manifest_path))
    if not isinstance(shots, list) or not shots: raise ValueError('Manifest needs shots')
    for shot in shots:
        if len(shot.get('frames',[])) != 6: raise ValueError(f"{shot.get('shot_id')}: exactly six keyframes required")
        ids=[f.get('frame_id') for f in shot['frames']]
        if len(set(ids)) != 6: raise ValueError('Frame IDs must be unique per shot')
        for frame in shot['frames']:
            p=Path(frame['path'])
            if not p.is_file() or sha(p) != frame['sha256']: raise ValueError(f'Frame hash mismatch: {p}')
    contract=read(contract_path); hashed=[manifest_path,contract_path]
    contract_io.require_v2(contract,allow_v1_contract,str(contract_path))
    prompt=None
    if contract_io.is_v2(contract):
        contract,prompt=contract_io.split_v2(contract,read(prompt_path) if prompt_path else None)
        contract_io.validate_v2(contract,prompt,[s['shot_id'] for s in shots])
        if raw.get('episode_id') not in (None,contract['episode_id']): raise ValueError(f"Contract episode {contract['episode_id']} differs from manifest {raw['episode_id']}")
        if prompt_path: hashed.append(Path(prompt_path).resolve())
    registry=normalize_contract(contract, shots)
    narrative=narrative_for(registry,[s['shot_id'] for s in shots],contract_io.is_v2(contract))
    package=None
    if compiled is not None:
        # Compiled package (docs/contract-and-requirements-design.md): must belong to this contract file and agree with
        # what prepare derives; its requirements.json is copied into the case, its registry/narrative are written.
        import episode_requirements
        package=episode_requirements.verify_package(compiled,contract_path,contract,registry,narrative)
    case.mkdir(parents=True)
    shutil.copy2(manifest_path,case/'raw_manifest.json')
    if prompt is None: shutil.copy2(contract_path,case/'contract.json')
    else: dump(case/'contract.json',contract);dump(case/contract_io.PROMPT_FILE,prompt)
    if package is None:
        dump(case/'prompt_registry.json',registry)
        dump(case/'narrative.json',narrative)
    else:
        shutil.copy2(package['folder']/'prompt_registry.json',case/'prompt_registry.json')
        shutil.copy2(package['folder']/'narrative.json',case/'narrative.json')
        shutil.copy2(package['folder']/'requirements.json',case/'requirements.json')
    dump(case/'run.json',dict(protocol=PROTOCOL,status='prepared',model=MODEL,reasoning=REASONING,started=time.time(),
        contract_format='v2' if prompt is not None else 'v1',
        **({} if package is None else dict(compiled_requirements=package['record'])),
        source_hashes={**{str(path):sha(path) for path in hashed},str(Path(__file__).resolve()):sha(__file__)}))


BINDING_PROTOCOLS = ('v1', 'v2')
DEFAULT_BINDING_PROTOCOL = 'v2'


def detect(case, gpu, gpu_uuid, shot_workers, device='cuda', binding_protocol=DEFAULT_BINDING_PROTOCOL, detections=None):
    # detections (pipeline C, 2026-11-11): the second detection pass clusters the background frontend's augmented
    # detections (original WeDetect detections plus chosen Grounding DINO boxes) without running WeDetect again;
    # that clustering subprocess sees no GPU, binding and prompt recovery keep the given device.
    require_api(); case=Path(case).resolve(); manifest=case/'raw_manifest.json'; entities=case/'entities'
    if entities.exists():
        # Detection/shot-clustering is immutable once complete.  A later
        # detect invocation may resume the downstream binding stage, but it
        # must never silently use a partial clustering directory.
        entity_state = read(entities/'run.json') if (entities/'run.json').is_file() else {}
        if entity_state.get('status') != 'success':
            raise ValueError('Existing detection output is incomplete; resume clustering into a fresh directory first')
    else:
        # The isolated shot reviewer is a CPU/schema-validation utility. On the
        # ROCm VACE runtime, jsonschema is not installed; allow the batch runner
        # to route only this subprocess through the configured base Python.
        review_python=os.environ.get('EECBENCH_REVIEW_PYTHON',sys.executable)
        cmd=[review_python,str(ROOT/'scripts/run_wedetect_shot_entities.py'),'--manifest',str(manifest),'--output',str(entities),
             '--device','cpu' if detections else device,'--model',MODEL,'--reasoning',REASONING,'--shot-workers',str(shot_workers)]
        if detections:
            detections=Path(detections).resolve()
            if not (detections/'run.json').is_file(): raise ValueError(f'No detection run in {detections}')
            cmd.extend(['--detections',str(detections)])
            subprocess.run(cmd,check=True,env=dict(os.environ,ROCR_VISIBLE_DEVICES='-1',CUDA_VISIBLE_DEVICES=''))
        elif device=='cuda':
            if gpu is None or not gpu_uuid: raise ValueError('CUDA detection requires physical GPU index and UUID')
            cmd.extend(['--gpu',str(gpu),'--gpu-uuid',gpu_uuid])
        elif device=='cpu':
            # The lower-level detector fails closed unless GPU visibility is hidden.
            os.environ.update(ROCR_VISIBLE_DEVICES='-1',CUDA_VISIBLE_DEVICES='')
        else:
            raise ValueError('Unsupported detector device')
        if not detections:
            subprocess.run(cmd,check=True)
    recovery_out = case / 'shot_prompt_recovery'
    resume_rec = recovery_out.exists() and (recovery_out / 'run.json').is_file() and read(recovery_out / 'run.json').get('status') == 'failed'
    if recovery_out.exists() and not resume_rec and not (recovery_out / 'results.json').is_file():
        shutil.rmtree(recovery_out)
        resume_rec = False
    if not (recovery_out / 'results.json').is_file() or read(recovery_out / 'results.json').get('status') != 'success':
        recovery.run(case,case/'prompt_registry.json',out=recovery_out,workers=shot_workers,device=device,
                     gpu=gpu if device=='cuda' else None,gpu_uuid=gpu_uuid if device=='cuda' else None,
                     model=MODEL,reasoning=REASONING,resume=resume_rec,binding_protocol=binding_protocol)
    recorded=read(recovery_out/'results.json').get('binding_protocol','v1')
    if recorded!=binding_protocol: raise ValueError(f'Existing shot prompt recovery used binding protocol {recorded}, not {binding_protocol}')
    state=read(case/'run.json');state.update(status='detected',detected_at=time.time(),detector_device=device,binding_protocol=binding_protocol);dump(case/'run.json',state)


def local_rows(case):
    case=Path(case); shots=read(case/'raw_manifest.json')['shots']; root=case/'shot_prompt_recovery'
    if not (root/'results.json').is_file() or read(root/'results.json')['status']!='success': raise ValueError('Need successful shot prompt recovery')
    registry=read(case/'prompt_registry.json'); bind={}
    out=[]
    for shot in shots:
        sid=shot['shot_id']; inv=read(root/'entities/shots'/sid/'entities.json'); inp=read(root/'entities/shots'/sid/'input.json')
        bycid={d['candidate_id']:d for f in inp['frames'] for d in f['detections']}; bindings={x['entity_id']:x for x in read(root/'shots'/sid/'binding_final.json')['bindings']}; bind[sid]=bindings
        for e in inv['entities']:
            obs=[]; wd, gd=set(),set()
            for o in e['observations']:
                cid=o['box_candidate_id']; candidate=bycid.get(cid) if cid else None
                detector='grounding_dino' if candidate and candidate.get('detector')=='grounding_dino' else 'wedetect_anything' if candidate else None
                if candidate:
                    (gd if detector=='grounding_dino' else wd).add(candidate.get('name',''))
                obs.append(dict(frame_id=o['frame_id'], box_xyxy=o['box_xyxy'], candidate_id=cid, detector=detector,
                                detector_category=candidate.get('name') if candidate else None, score=candidate.get('score') if candidate else None))
            b=bindings[e['entity_id']]
            out.append(dict(local_key=f'{sid}/{e["entity_id"]}',shot_id=sid,local_entity_id=e['entity_id'],name=e['name'],
                short_description=e['name'], binding_status=b['status'],prompt_entity_id=b['prompt_entity_id'],
                candidate_prompt_entity_ids=b['candidate_prompt_entity_ids'],binding_reason=b['reason'],observations=obs,
                observed_frame_ids=[x['frame_id'] for x in obs if x['box_xyxy'] is not None],
                wedetect_categories=sorted(x for x in wd if x),grounding_dino_categories=sorted(x for x in gd if x)))
    return shots, registry, out


def match_schema():
    member=obj(shot_id=S, local_entity_id=S)
    members=arr(member); members['minItems']=1
    group=obj(identity=enum('confirmed','singleton','unresolved'), members=members, short_description=S, reason=S)
    groups=arr(group); groups['minItems']=1
    return obj(groups=groups)


def normalize_match_groups(raw, local):
    """Enforce that a confirmed cross-shot identity has two occurrences.

    A one-member `confirmed` group cannot introduce a link.  Preserve the
    original agent output in the caller, then represent that local entity as a
    singleton rather than failing the entire episode.
    """
    normalized=copy.deepcopy(raw)
    for group in normalized.get('groups', []):
        members = group.get('members', [])
        shots = [m.get('shot_id') for m in members if isinstance(m, dict)]
        if group.get('identity') == 'confirmed' and len(members) == 1:
            group['identity'] = 'singleton'
            group['reason'] = group.get('reason', '').strip() + ' [normalized: a single occurrence cannot form a confirmed cross-shot identity.]'
        elif group.get('identity') == 'confirmed' and len(shots) != len(set(shots)):
            group['identity'] = 'unresolved'
            group['reason'] = group.get('reason', '').strip() + ' [normalized: multiple local entities from one shot cannot form a confirmed cross-shot identity.]'
    covered = {(m['shot_id'], m['local_entity_id']) for g in normalized.get('groups', []) for m in g.get('members', []) if isinstance(m, dict) and 'shot_id' in m and 'local_entity_id' in m}
    for item in local:
        key = (item['shot_id'], item['local_entity_id'])
        if key not in covered:
            normalized['groups'].append(dict(identity='singleton', members=[dict(shot_id=key[0], local_entity_id=key[1])], short_description=item['name'], reason='[normalized: omitted by global matcher; no cross-shot identity link inferred.]'))
    return normalized


def validate_groups(raw, local):
    import jsonschema
    jsonschema.validate(raw, match_schema())
    local_by={(x['shot_id'],x['local_entity_id']):x for x in local}; seen=set()
    for g in raw['groups']:
        members=[(x['shot_id'],x['local_entity_id']) for x in g['members']]
        if len(members)!=len(set(members)) or not set(members)<=set(local_by): raise ValueError('Unknown or duplicate local member')
        if seen & set(members): raise ValueError('Local entity appears in multiple groups')
        seen.update(members)
        if not g['reason'].strip() or not g['short_description'].strip(): raise ValueError('Groups need description and reason')
        if g['identity']=='confirmed' and len(members)<2: raise ValueError('Confirmed group needs two observations')
        if g['identity']=='singleton' and len(members)!=1: raise ValueError('Singleton must have one member')
        shots=[x[0] for x in members]
        if g['identity']=='confirmed' and len(shots)!=len(set(shots)): raise ValueError('Confirmed group cannot contain two entities from one shot')
    if seen != set(local_by): raise ValueError('Global matching must cover every local entity exactly once')
    return raw


def schedule_fields(registry, pid, occurrences):
    byshot={}
    for x in occurrences: byshot.setdefault(x['shot_id'],[]).append(x)  # binding v2: several local entities per shot
    prompt=next(x for x in registry['entities'] if x['prompt_entity_id']==pid)
    result=[]
    for row in prompt['schedule']:
        positive=[o for occ in byshot.get(row['shot_id'],[]) for o in occ['observations'] if o['box_xyxy'] is not None]
        result.append(dict(shot_id=row['shot_id'], expectation=row['expectation'], schedule_reason=row['reason'],
            detector_observation='observed' if positive else 'not_detected',
            observed_frame_ids=[o['frame_id'] for o in positive], boxes=[dict(frame_id=o['frame_id'],box_xyxy=o['box_xyxy']) for o in positive]))
    return result


def build_episode_entities(case, raw):
    case=Path(case); shots,registry,local=local_rows(case)
    local_by={x['local_key']:x for x in local}
    raw_group_by_local={}
    unresolved=[]
    for group in raw['groups']:
        keys=[f"{x['shot_id']}/{x['local_entity_id']}" for x in group['members']]
        for key in keys: raw_group_by_local[key]=group
        if group['identity']=='unresolved':
            unresolved.append(dict(members=keys,short_description=group['short_description'],reason=group['reason']))

    # Prompt-bound entities are schedule instances. Their contract ID is the
    # authoritative cross-shot reference even if the visual matcher abstains:
    # downstream scoring compares all of their observed appearances rather than
    # losing a scheduled recurrence at the identity-matching boundary.
    bound_by_pid={p['prompt_entity_id']:[] for p in registry['entities']}
    for member in local:
        if member['binding_status']=='bound':
            bound_by_pid[member['prompt_entity_id']].append(member)
    bound_records=[]
    for index,prompt in enumerate(registry['entities'],1):
        pid=prompt['prompt_entity_id']; members=bound_by_pid[pid]
        member_keys={m['local_key'] for m in members}
        visual_groups={id(raw_group_by_local[m['local_key']]):raw_group_by_local[m['local_key']] for m in members}
        confirmed=any(g['identity']=='confirmed' and {f"{x['shot_id']}/{x['local_entity_id']}" for x in g['members']}==member_keys for g in visual_groups.values())
        if not members:
            visual_status='scheduled_only'
            visual_reason='Required by the fixed contract schedule; no detector-backed local entity was bound.'
        elif confirmed:
            visual_status='confirmed'
            visual_reason='The fixed contract instance is also one confirmed visual identity group.'
        elif len(members)==1:
            visual_status='singleton'
            visual_reason='One detector-backed local occurrence is bound to the fixed contract instance.'
        else:
            visual_status='schedule_bound'
            visual_reason='Local occurrences share this fixed contract instance; the separate visual matcher did not confirm one global identity group.'
        bound_records.append(dict(global_entity_id=f'pb{index:04d}',partition='prompt_bound',prompt_entity_id=pid,
            name=prompt['name'],short_description=prompt['description'],identity_status=visual_status,identity_reason=visual_reason,
            occurrences=members,observed_shot_ids=list(dict.fromkeys(m['shot_id'] for m in members)),
            wedetect_categories=sorted({x for m in members for x in m['wedetect_categories']}),
            grounding_dino_categories=sorted({x for m in members for x in m['grounding_dino_categories']}),
            dino_appearance=None,schedule=schedule_fields(registry,pid,members),
            visual_identity_group_refs=[dict(identity=g['identity'],members=[f"{x['shot_id']}/{x['local_entity_id']}" for x in g['members']],reason=g['reason']) for g in visual_groups.values()]))

    # Prompt-unbound entities derive their recurrence only from the visual
    # matcher. A mixed or unresolved visual group is never merged here.
    unbound_records=[]; gid=1
    for group in raw['groups']:
        members=[local_by[f"{x['shot_id']}/{x['local_entity_id']}"] for x in group['members']]
        unbound=[m for m in members if m['binding_status']!='bound']
        if not unbound:
            continue
        whole_unbound=len(unbound)==len(members)
        if group['identity']=='confirmed' and whole_unbound:
            components=[(unbound,'confirmed',group['reason'])]
        elif group['identity']=='singleton' and whole_unbound:
            components=[(unbound,'singleton',group['reason'])]
        else:
            components=[([m],'unresolved' if group['identity']=='unresolved' else 'singleton',
                         'Not merged because the visual group is mixed with prompt-bound entities or unresolved.') for m in unbound]
        for component,status,reason in components:
            unbound_records.append(dict(global_entity_id=f'ge{gid:04d}',partition='prompt_unbound',prompt_entity_id=None,
                name=group['short_description'],short_description=group['short_description'],identity_status=status,identity_reason=reason,
                occurrences=component,observed_shot_ids=[m['shot_id'] for m in component],
                wedetect_categories=sorted({x for m in component for x in m['wedetect_categories']}),
                grounding_dino_categories=sorted({x for m in component for x in m['grounding_dino_categories']}),dino_appearance=None))
            gid+=1
    records=bound_records+unbound_records

    # DINO has no meaningful image input for a schedule-only entry; all
    # detector-backed entries retain their original observations verbatim.
    compatible=[]
    for r in records:
        if not r['occurrences']:
            continue
        appearances=[]
        for m in r['occurrences']:
            appearances.append(dict(shot_id=m['shot_id'],local_entity_id=m['local_entity_id'],name=m['name'],
                observed_frame_ids=m['observed_frame_ids'],observations=[dict(frame_id=o['frame_id'],box_xyxy=o['box_xyxy'],box_candidate_id=o['candidate_id'],candidate_ids=[o['candidate_id']] if o['candidate_id'] else [],exist=True if o['box_xyxy'] is not None else None) for o in m['observations']]))
        compatible.append(dict(global_entity_id=r['global_entity_id'],name=r['name'],scene_id='episode',observed_shot_ids=r['observed_shot_ids'],appearances=appearances))
    sources={str(case/'raw_manifest.json'):sha(case/'raw_manifest.json'),str(case/'prompt_registry.json'):sha(case/'prompt_registry.json'),str(case/'shot_prompt_recovery/results.json'):sha(case/'shot_prompt_recovery/results.json')}
    for shot in shots:
        for n in ('entities.json','input.json'):
            source=case/'shot_prompt_recovery/entities/shots'/shot['shot_id']/n
            sources[str(source)]=sha(source)
    global_compat=dict(schema_version='episode_entities_v1',policy='vl_vv_schedule_bound_plus_visual_unbound',
        shot_order=[s['shot_id'] for s in shots],entities=compatible,
        counts=dict(local_entities=len(local),global_records=len(compatible),confirmed_links=sum(1 for g in raw['groups'] if g['identity']=='confirmed'),unresolved_links=len(unresolved)),
        source_case=str(case),source_hashes=sources,appearance_score_computed=False)
    payload=dict(protocol=PROTOCOL,status='matched',model=MODEL,reasoning=REASONING,shot_order=[s['shot_id'] for s in shots],
        prompt_bound=bound_records,prompt_unbound=unbound_records,unresolved_identity_links=unresolved,
        counts=dict(prompt_bound=len(bound_records),prompt_unbound=len(unbound_records)),
        limitations='not_detected is a detector result; visual identity groups remain separate evidence from fixed schedule identity.')
    import jsonschema
    jsonschema.validate(payload, read(EPISODE_SCHEMA))
    dump(case/'episode_entities.json',payload);dump(case/'global_entities/global_entities.json',global_compat)

def exact_once_errors(raw, local):
    """Return all identity-partition violations without repairing the agent output."""
    import jsonschema
    errors=[]
    try: jsonschema.validate(raw, match_schema())
    except Exception as exc: return [f'schema: {exc}']
    valid={(x['shot_id'], x['local_entity_id']) for x in local}; seen={}
    for i, group in enumerate(raw['groups']):
        members=[(m['shot_id'],m['local_entity_id']) for m in group['members']]
        listed=[f'{s}/{e}' for s,e in members]
        if not group['reason'].strip() or not group['short_description'].strip(): errors.append(f'group {i}: empty description or reason')
        if group['identity']=='confirmed' and len(members)<2: errors.append(f'group {i}: confirmed needs at least two members (groups[{i}] has {listed})')
        if group['identity']=='singleton' and len(members)!=1: errors.append(f'group {i}: singleton needs one member (groups[{i}] is labeled singleton but has {len(members)} members {listed}; use confirmed/unresolved for multiple members or split into singletons)')
        if group['identity']=='confirmed' and len({x[0] for x in members}) != len(members): errors.append(f'group {i}: confirmed has multiple members from one shot (groups[{i}] has {listed})')
        for key in members:
            if key not in valid: errors.append(f'group {i}: unknown local entity {key[0]}/{key[1]}')
            elif key in seen: errors.append(f'duplicate local entity {key[0]}/{key[1]} in groups {seen[key]} and {i}')
            else: seen[key]=i
    for sid,eid in sorted(valid-set(seen)): errors.append(f'missing local entity {sid}/{eid}')
    return errors


def ownership_problems(raw, local):
    """List only local keys whose global-group ownership is not exact-once."""
    valid={(x['shot_id'],x['local_entity_id']) for x in local}
    occurrences={key:[] for key in valid}
    unknown={}
    for index,group in enumerate(raw.get('groups', [])):
        for member in group.get('members', []):
            key=(member.get('shot_id'),member.get('local_entity_id'))
            (occurrences if key in valid else unknown).setdefault(key,[]).append(index)
    problems=[]
    for key,indices in sorted(occurrences.items()):
        if len(indices)==1: continue
        if indices:
            problems.append(dict(
                shot_id=key[0],local_entity_id=key[1],problem='duplicate',
                existing_group_indices=indices,allowed_group_indices=indices,
                template=dict(shot_id=key[0],local_entity_id=key[1],action='keep_existing',target_group_index=f'CHOOSE_ONE_FROM_{indices}')
            ))
        else:
            allowed=[]
            for index,group in enumerate(raw['groups']):
                members=group['members']
                if group['identity']=='unresolved' or (group['identity']=='confirmed' and all(m['shot_id']!=key[0] for m in members)):
                    allowed.append(index)
            problems.append(dict(
                shot_id=key[0],local_entity_id=key[1],problem='missing',
                existing_group_indices=[],allowed_group_indices=allowed,
                template_options=[
                    dict(action='assign_existing',target_group_index=f'CHOOSE_ONE_FROM_{allowed}'),
                    dict(action='new_singleton',target_group_index=None)
                ]
            ))
    for key,indices in sorted(unknown.items()):
        problems.append(dict(
            shot_id=key[0],local_entity_id=key[1],problem='unknown',
            existing_group_indices=indices,allowed_group_indices=[],
            template=dict(shot_id=key[0],local_entity_id=key[1],action='remove_unknown',target_group_index=None)
        ))
    return problems


def repair_schema():
    return obj(repairs=arr(obj(shot_id=S,local_entity_id=S,
        action=enum('keep_existing','assign_existing','new_singleton','remove_unknown'),
        target_group_index=dict(type=['integer','null']))))


def apply_ownership_repairs(raw, problems, response):
    """Apply model choices only to listed bad keys; preserve all other content."""
    import jsonschema
    jsonschema.validate(response,repair_schema())
    expected={(p['shot_id'],p['local_entity_id']):p for p in problems}
    rows=response['repairs']; keys=[(r['shot_id'],r['local_entity_id']) for r in rows]
    if len(keys)!=len(set(keys)) or set(keys)!=set(expected):
        raise ValueError('Repair response must cover each listed problem key exactly once and no other key')
    repaired=copy.deepcopy(raw); decisions={key:r for key,r in zip(keys,rows)}
    for key,problem in expected.items():
        row=decisions[key]; action=row['action']; target=row['target_group_index']
        if problem['problem']=='duplicate':
            if action=='assign_existing' and target in problem['existing_group_indices']:
                action='keep_existing'
                row['action']='keep_existing'
            if action!='keep_existing' or target not in problem['existing_group_indices']:
                raise ValueError(f'Invalid duplicate repair for {key}: action must be keep_existing with target in {problem["existing_group_indices"]}')
        elif problem['problem']=='missing':
            if action=='assign_existing' and target not in problem['allowed_group_indices']:
                raise ValueError(f'Invalid missing assignment for {key}: target must be in {problem["allowed_group_indices"]}')
            if action=='new_singleton':
                if target is not None:
                    target=None
                    row['target_group_index']=None
            if action not in ('assign_existing','new_singleton'):
                raise ValueError(f'Invalid missing repair for {key}')
        elif action!='remove_unknown' or target is not None:
            raise ValueError(f'Invalid unknown-key repair for {key}')
    for key,problem in expected.items():
        row=decisions[key]; target=row['target_group_index']
        if problem['problem'] in ('duplicate','unknown'):
            for index,group in enumerate(repaired['groups']):
                group['members']=[m for m in group['members'] if
                    (m['shot_id'],m['local_entity_id'])!=key or (problem['problem']=='duplicate' and index==target)]
        elif row['action']=='assign_existing':
            repaired['groups'][target]['members'].append(dict(shot_id=key[0],local_entity_id=key[1]))
        else:
            repaired['groups'].append(dict(identity='singleton',members=[dict(shot_id=key[0],local_entity_id=key[1])],
                short_description=key[1],reason='Exact-once repair created a singleton for an omitted local entity.'))
    cleaned=[]
    for group in repaired['groups']:
        if not group['members']: continue
        if group['identity']=='confirmed' and len(group['members'])==1: group['identity']='singleton'
        cleaned.append(group)
    repaired['groups']=cleaned
    return repaired


def response_id(folder):
    for line in (Path(folder)/'events.jsonl').read_text().splitlines():
        try:
            event=json.loads(line)
            if event.get('type')=='turn.completed' and event.get('api_response_id'): return event['api_response_id']
        except json.JSONDecodeError: pass
    raise ValueError('API response ID unavailable; cannot continue the same Luna conversation')


def match(case, protocol=None):
    protocol = protocol or DEFAULT_MATCHING_PROTOCOL
    if protocol not in MATCHING_PROTOCOLS:
        raise ValueError(f'Unknown matching protocol {protocol!r}')
    return match_v2(case) if protocol == 'v2' else match_v1(case)


def match_v1(case):
    require_api(); case=Path(case).resolve();shots,registry,local=local_rows(case);out=case/'global_match'
    payload=dict(protocol=PROTOCOL,shot_order=[s['shot_id'] for s in shots],schedule=registry['entities'],local_entities=local)
    images=[dict(frame,shot_id=shot['shot_id']) for shot in shots for frame in shot['frames']]
    attempts=out/'attempts'; attempts.mkdir(parents=True,exist_ok=True)
    original=attempts/'attempt_00'
    first=read(original/'response.json') if (original/'response.json').is_file() else None
    # Every identity-partition problem (missing/duplicate/unknown members and
    # identity labels inconsistent with member counts) goes back to the model
    # together, in the same conversation, until the raw output is valid.
    raw,_,usage,repair=repair_loop.call_with_repair(original,payload,images,1800,
        prompt_path=ROOT/'prompts/vvvl_global_entity_match_v1.txt',schema=match_schema(),
        model=MODEL,reasoning=REASONING,collect_errors=lambda candidate:(exact_once_errors(candidate,local),candidate),
        first_response=first,first_folder=original if first is not None else None,stage='global entity matching')
    attempt=repair['repair_rounds']; audit=repair['rounds']; prior=repair_loop.response_id(audit[-1]['call_folder'])
    raw_model_result=copy.deepcopy(raw)
    raw=normalize_match_groups(raw,local)
    errors=exact_once_errors(raw,local)
    if errors: raise ValueError('Global matching semantics invalid after exact-once pass: '+json.dumps(errors,ensure_ascii=False))
    normalizations=[]
    for index,(before_group,after_group) in enumerate(zip(raw_model_result['groups'],raw['groups'])):
        if before_group!=after_group:
            normalizations.append(dict(group_index=index,before=before_group,after=after_group))
    if len(raw['groups'])>len(raw_model_result['groups']):
        normalizations.extend(dict(group_index=index,before=None,after=group)
                              for index,group in enumerate(raw['groups'][len(raw_model_result['groups']):],start=len(raw_model_result['groups'])))
    dump(out/'raw_model_result.json',raw_model_result)
    dump(out/'semantic_normalization.json',dict(protocol='vl_vv_global_match_normalization_v1',count=len(normalizations),changes=normalizations))
    dump(out/'exact_once_audit.json',dict(status='passed',repair_protocol=repair['protocol'],repair_attempts=attempt,final_response_id=prior,attempts=audit,usage=usage,semantic_normalizations=normalizations))
    validate_groups(raw,local);dump(out/'result.json',raw);build_episode_entities(case,raw)
    state=read(case/'run.json');state.update(status='matched',matched_at=time.time(),matching_protocol='v1');dump(case/'run.json',state)


# ---------------------------------------------------------------------------
# Matching v2: only unbound occurrences are matched; specified entities are
# anchors linked by contract ID. Three destinations per unbound occurrence.
# ---------------------------------------------------------------------------
MATCHING_PROTOCOLS = ('v1', 'v2')
DEFAULT_MATCHING_PROTOCOL = 'v2'
MATCHING_V2 = 'vl_vv_unspecified_matching_v2'
MATCH_V2_PROMPT = ROOT / 'prompts/vl_vv_unspecified_matching_v2.txt'
SPECIFIED_COLOR, UNBOUND_COLOR = (30, 110, 255), (255, 140, 0)


def match_v2_schema():
    assignment = obj(members=dict(type='array', items=S, minItems=1), destination=enum('unspecified', 'specified'),
                     specified_tag={'type': ['string', 'null']}, short_description=S,
                     confidence=enum('high', 'medium', 'low'), basis=S)
    return obj(assignments=arr(assignment))


def match_v2_tags(registry, local):
    """P<k> per contract entity in registry order; U<n> per unbound occurrence in shot order."""
    ptag = {p['prompt_entity_id']: f'P{k}' for k, p in enumerate(registry['entities'], 1)}
    utag = {}
    for m in local:
        if m['binding_status'] != 'bound':
            utag[m['local_key']] = f'U{len(utag) + 1}'
    return ptag, utag


def match_v2_payload(shots, registry, local, contract, ptag, utag):
    prompt = contract.get('prompt') or {}
    if contract_io.is_v2(contract):
        settings = contract_io.shot_settings(contract)
    else:
        settings = [dict(shot_id=s['shot_id'], places=[p['name'] for p in registry['entities'] if p.get('contract_category') == 'places'
                                                        and any(r['shot_id'] == s['shot_id'] and r['expectation'] == 'required'
                                                                for r in p['schedule'])]) for s in shots]
    specified = [dict(tag=ptag[p['prompt_entity_id']], name=p['name'], description=p['description'],
                      category=p.get('contract_category'),
                      occurrences=[dict(shot_id=m['shot_id'], observed_frame_ids=m['observed_frame_ids']) for m in local
                                   if m['binding_status'] == 'bound' and m['prompt_entity_id'] == p['prompt_entity_id']])
                 for p in registry['entities']]
    unbound = [dict(tag=utag[m['local_key']], shot_id=m['shot_id'], name=m['name'], observed_frame_ids=m['observed_frame_ids'],
                    boxes=[dict(frame_id=o['frame_id'], box_xyxy=o['box_xyxy']) for o in m['observations'] if o['box_xyxy'] is not None],
                    detector_categories=sorted(set(m['wedetect_categories']) | set(m['grounding_dino_categories'])))
               for m in local if m['local_key'] in utag]
    return dict(protocol=MATCHING_V2, shot_order=[s['shot_id'] for s in shots],
                original_prompt=dict(global_prompt=prompt.get('global_prompt'),
                                     shots=[dict(shot_id=s['shot_id'], text=s['text']) for s in prompt.get('shots', [])]),
                shot_settings=settings, specified_entities=specified, unbound_occurrences=unbound)


def match_v2_errors(raw, local, ptag, utag):
    """Every problem of a matching-v2 answer; the repair loop returns all of them to the model together.

    An unspecified entity has at most one occurrence per shot. A specified entity may receive occurrences from a
    shot where it already has some (owner decision 2026-11-02, open-questions Q13): a contract entity that states
    several items or members has one occurrence per member. Nothing marks such entities in the contract, so, as in
    binding v2, the agent judges this from the contract text and the gate does not count specified occurrences.
    """
    import jsonschema
    try:
        jsonschema.validate(raw, match_v2_schema())
    except Exception as exc:
        return [f'schema: {exc}']
    errors = []
    by_tag = {utag[m['local_key']]: m for m in local if m['local_key'] in utag}
    known_p = set(ptag.values())
    seen = {}
    for i, a in enumerate(raw['assignments']):
        where = f'assignments[{i}]'
        if not a['basis'].strip() or not a['short_description'].strip():
            errors.append(f'{where}: needs a short_description and a basis')
        shots = []
        for tag in a['members']:
            if tag not in by_tag:
                errors.append(f'{where}: unknown unbound tag {tag!r}; use only the supplied U tags')
                continue
            if tag in seen:
                errors.append(f'{tag} is in assignments[{seen[tag]}] and {where}; every unbound occurrence needs exactly one destination')
            else:
                seen[tag] = i
            shots.append(by_tag[tag]['shot_id'])
        if a['destination'] == 'unspecified':
            repeated = sorted({s for s in shots if shots.count(s) > 1})
            if repeated:
                errors.append(f'{where}: more than one occurrence from {repeated}; an unspecified entity has at most one '
                              f'occurrence per shot')
            if a['specified_tag'] is not None:
                errors.append(f'{where}: destination "unspecified" needs specified_tag null')
            continue
        if a['specified_tag'] not in known_p:
            errors.append(f'{where}: destination "specified" needs one of the supplied P tags (got {a["specified_tag"]!r})')
    missing = [t for t in by_tag if t not in seen]
    if missing:
        errors.append(f'missing unbound occurrences {missing}; every one needs exactly one destination')
    return errors


def annotate_match_frames(shots, local, ptag, utag, out):
    """Copies of the keyframes with every occurrence drawn and tagged: blue P = specified, orange U = unbound."""
    from PIL import Image, ImageDraw, ImageFont
    images = []
    for shot in shots:
        sid = shot['shot_id']
        for frame in shot['frames']:
            img = Image.open(frame['path']).convert('RGB')
            draw = ImageDraw.Draw(img)
            line = max(2, round(min(img.size) / 240))
            size = max(12, round(min(img.size) / 28))
            try:
                font = ImageFont.load_default(size=size)
            except TypeError:
                font = ImageFont.load_default()
            for m in local:
                if m['shot_id'] != sid:
                    continue
                if m['binding_status'] == 'bound':
                    tag, color = ptag[m['prompt_entity_id']], SPECIFIED_COLOR
                elif m['local_key'] in utag:
                    tag, color = utag[m['local_key']], UNBOUND_COLOR
                else:
                    continue
                for o in m['observations']:
                    if o['frame_id'] != frame['frame_id'] or o['box_xyxy'] is None:
                        continue
                    x1, y1, x2, y2 = (float(v) for v in o['box_xyxy'])
                    draw.rectangle([x1, y1, x2, y2], outline=color, width=line)
                    ty = y1 - size - 2 * line if y1 > size + 2 * line else y1 + line
                    left, top, right, bottom = draw.textbbox((x1 + line, ty), tag, font=font)
                    draw.rectangle([left - 2, top - 2, right + 2, bottom + 2], fill=color)
                    draw.text((x1 + line, ty), tag, fill=(255, 255, 255), font=font)
            path = Path(out) / sid / f'frame_{int(frame["frame_id"]):06d}.jpg'
            path.parent.mkdir(parents=True, exist_ok=True)
            img.save(path, quality=92)
            images.append(dict(frame, shot_id=sid, path=str(path), source_path=frame['path'],
                               source_sha256=frame.get('sha256'), sha256=sha(path)))
    return images


def ledger_occurrence(m):
    """One shot of an entity in the simplified ledger: the keyframes with a box and the box on each."""
    return dict(shot_id=m['shot_id'], local_entity_id=m['local_entity_id'],
                boxes=[dict(frame_id=o['frame_id'], box_xyxy=o['box_xyxy']) for o in m['observations'] if o['box_xyxy'] is not None])


def build_episode_entities_v2(case, raw, shots, registry, local, ptag, utag):
    """Simplified ledger from matching v2 (owner decision 2026-11-01).

    Two lists; each record is ID, contract ID (specified only), name,
    description and occurrences. Matching bases, confidences, tags and
    supplementary bindings stay in global_match_v2/; DINO stays in dino/ and
    global_entities.json and is not put into this ledger.
    """
    case = Path(case)
    order = [s['shot_id'] for s in shots]
    by_tag = {utag[m['local_key']]: m for m in local if m['local_key'] in utag}
    pid_of = {t: pid for pid, t in ptag.items()}
    supplementary = {pid: [] for pid in ptag}
    unbound_records, unbound_members = [], []
    for a in raw['assignments']:
        if a['destination'] == 'specified':
            supplementary[pid_of[a['specified_tag']]] += [by_tag[t] for t in a['members']]
            continue
        members = sorted((by_tag[t] for t in a['members']), key=lambda m: order.index(m['shot_id']))
        unbound_members.append(members)
        unbound_records.append(dict(global_entity_id=f'ge{len(unbound_records) + 1:04d}', name=members[0]['name'],
                                    description=a['short_description'], occurrences=[ledger_occurrence(m) for m in members]))
    bound_records, bound_members = [], []
    for index, prompt in enumerate(registry['entities'], 1):
        pid = prompt['prompt_entity_id']
        members = [m for m in local if m['binding_status'] == 'bound' and m['prompt_entity_id'] == pid] + supplementary[pid]
        members.sort(key=lambda m: order.index(m['shot_id']))
        bound_members.append(members)
        bound_records.append(dict(global_entity_id=f'pb{index:04d}', prompt_entity_id=pid, name=prompt['name'],
                                  description=prompt['description'], occurrences=[ledger_occurrence(m) for m in members]))
    compatible = []
    for r, members in zip(bound_records + unbound_records, bound_members + unbound_members):
        if not members:
            continue
        appearances = [dict(shot_id=m['shot_id'], local_entity_id=m['local_entity_id'], name=m['name'], observed_frame_ids=m['observed_frame_ids'],
                            observations=[dict(frame_id=o['frame_id'], box_xyxy=o['box_xyxy'], box_candidate_id=o['candidate_id'],
                                               candidate_ids=[o['candidate_id']] if o['candidate_id'] else [],
                                               exist=True if o['box_xyxy'] is not None else None) for o in m['observations']])
                       for m in members]
        compatible.append(dict(global_entity_id=r['global_entity_id'], name=r['name'], scene_id='episode',
                               observed_shot_ids=list(dict.fromkeys(m['shot_id'] for m in members)), appearances=appearances))
    sources = {str(case / 'raw_manifest.json'): sha(case / 'raw_manifest.json'), str(case / 'prompt_registry.json'): sha(case / 'prompt_registry.json'),
               str(case / 'contract.json'): sha(case / 'contract.json'),
               str(case / 'shot_prompt_recovery/results.json'): sha(case / 'shot_prompt_recovery/results.json')}
    for shot in shots:
        for n in ('entities.json', 'input.json'):
            source = case / 'shot_prompt_recovery/entities/shots' / shot['shot_id'] / n
            sources[str(source)] = sha(source)
    global_compat = dict(schema_version='episode_entities_v1', policy='vl_vv_contract_id_plus_unspecified_matching_v2',
                         shot_order=order, entities=compatible,
                         counts=dict(local_entities=len(local), global_records=len(compatible),
                                     matched_unspecified=sum(1 for members in unbound_members if len(members) > 1),
                                     supplementary_bindings=sum(len(v) for v in supplementary.values())),
                         source_case=str(case), source_hashes=sources, appearance_score_computed=False)
    payload = dict(protocol=PROTOCOL, ledger_format=LEDGER_V2, matching_protocol=MATCHING_V2, status='matched', shot_order=order,
                   prompt_bound=bound_records, prompt_unbound=unbound_records)
    import jsonschema
    jsonschema.validate(payload, read(EPISODE_SCHEMA_V2))
    dump(case / 'episode_entities.json', payload)
    dump(case / 'global_entities/global_entities.json', global_compat)
    return payload


def match_v2(case):
    require_api(); case = Path(case).resolve(); shots, registry, local = local_rows(case)
    contract = contract_io.load_case_contract(case); out = case / 'global_match_v2'
    ptag, utag = match_v2_tags(registry, local)
    payload = match_v2_payload(shots, registry, local, contract, ptag, utag)
    attempts = out / 'attempts'; attempts.mkdir(parents=True, exist_ok=True)
    dump(out / 'tags.json', dict(specified={t: pid for pid, t in ptag.items()}, unbound={t: key for key, t in utag.items()}))
    if not utag:
        raw = dict(assignments=[]); audit = dict(status='skipped', reason='no unbound occurrences', model=MODEL, reasoning=REASONING, usage=[])
    else:
        images = annotate_match_frames(shots, local, ptag, utag, out / 'annotated_frames')
        original = attempts / 'attempt_00'
        first = read(original / 'response.json') if (original / 'response.json').is_file() else None
        raw, _, usage, repair = repair_loop.call_with_repair(
            original, payload, images, 1800, prompt_path=MATCH_V2_PROMPT, schema=match_v2_schema(), model=MODEL, reasoning=REASONING,
            collect_errors=lambda candidate: (match_v2_errors(candidate, local, ptag, utag), candidate),
            first_response=first, first_folder=original if first is not None else None, stage='unspecified entity matching v2')
        audit = dict(status='passed', model=MODEL, reasoning=REASONING, repair_protocol=repair['protocol'],
                     repair_rounds=repair['repair_rounds'], attempts=repair['rounds'], usage=usage)
    errors = match_v2_errors(raw, local, ptag, utag)
    if errors:
        raise ValueError('Matching v2 output invalid: ' + json.dumps(errors, ensure_ascii=False))
    dump(out / 'audit.json', audit); dump(out / 'result.json', raw)
    build_episode_entities_v2(case, raw, shots, registry, local, ptag, utag)
    state = read(case / 'run.json'); state.update(status='matched', matched_at=time.time(), matching_protocol='v2'); dump(case / 'run.json', state)


def dino_prepare(case):
    import gs_entity_appearance as appearance
    case=Path(case).resolve();out=case/'dino/canonical'
    if out.exists():raise FileExistsError('DINO prepare output already exists')
    appearance.prepare(case,out)


def dino(case,gpu,gpu_uuid):
    case=Path(case).resolve();runs=case/'dino/canonical'
    if not (runs/'manifest.json').is_file():raise ValueError('Run dino_prepare first')
    guard=ROOT/'experiments/study2_detection_only_fresh_20260918/guard_gpu.py'
    cmd=gpu_lock.prefix(gpu_uuid)+[sys.executable,str(guard),str(gpu),gpu_uuid,'/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python',str(ROOT/'scripts/gs_entity_appearance.py'),'dino','--runs',str(runs)]
    subprocess.run(cmd,check=True)


def attach_dino(case):
    case=Path(case).resolve();episode=read(case/'episode_entities.json');root=case/'dino/canonical/entities'
    if not root.is_dir():raise ValueError('Need DINO results')
    scores={p.parent.name:read(p) for p in root.glob('*/dino.json')}
    # The simplified ledger (matching v2) does not carry DINO (owner, 2026-11-01; ablation pending in docs/open-questions.md Q1).
    if episode.get('ledger_format')!=LEDGER_V2:
        for partition in ('prompt_bound','prompt_unbound'):
            for entity in episode[partition]:
                entity['dino_appearance']=scores.get(entity['global_entity_id'])
        dump(case/'episode_entities.json',episode)
    compat=read(case/'global_entities/global_entities.json');compat['appearance_score_computed']=True
    for entity in compat['entities']: entity['dino_appearance']=scores[entity['global_entity_id']]
    dump(case/'global_entities/global_entities.json',compat)
    state=read(case/'run.json');state.update(status='complete',dino_attached_at=time.time());dump(case/'run.json',state)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage',choices=['extract','prepare','detect','match','dino_prepare','dino','attach_dino','discover_issues','all'])
    p.add_argument('--video-index',type=Path);p.add_argument('--frames-out',type=Path);p.add_argument('--manifest-out',type=Path)
    p.add_argument('--manifest',type=Path);p.add_argument('--contract',type=Path);p.add_argument('--case',type=Path)
    p.add_argument('--detections',type=Path,help='detect: cluster these detections (background frontend aug_detections) instead of running WeDetect')
    p.add_argument('--gpu',type=int);p.add_argument('--gpu-uuid');p.add_argument('--device',choices=['cuda','cpu'],default='cuda');p.add_argument('--shot-workers',type=int,default=3);p.add_argument('--run-dino',action='store_true')
    p.add_argument('--issue-output',type=Path,help='Fresh output directory for the independent VL/VV issue-discovery agent')
    p.add_argument('--allow-legacy-nominal-keyframes',action='store_true',help='Accept episode keyframes on the nominal 5 s grid; only to reproduce historical results')
    p.add_argument('--prompt',type=Path,help='Prompt JSON for a v2 contract without evidence; a contract with evidence holds its prompt')
    p.add_argument('--compiled',type=Path,help='Compiled requirement package of the contract (compile_episode_requirements.py): copied into the case; a package that does not match the contract file is an error')
    p.add_argument('--allow-v1-contract',action='store_true',help='Accept a v1 contract; only to reproduce historical results')
    p.add_argument('--binding-protocol',choices=BINDING_PROTOCOLS,default=DEFAULT_BINDING_PROTOCOL,
                   help='v2 (default): several local entities of one shot may bind to one contract entity when its text describes several items; v1: at most one')
    p.add_argument('--matching-protocol',choices=MATCHING_PROTOCOLS,default=DEFAULT_MATCHING_PROTOCOL,
                   help='v2 (default): match only unbound occurrences by the most likely reading, three destinations; v1: historical visual matcher')
    a=p.parse_args()
    if a.stage=='extract':
        if not all((a.video_index,a.frames_out,a.manifest_out)):p.error('extract requires --video-index --frames-out --manifest-out')
        extract_six(a.video_index,a.frames_out,a.manifest_out);return
    if a.stage=='prepare':
        if not all((a.manifest,a.contract,a.case)):p.error('prepare requires --manifest --contract --case')
        prepare(a.manifest,a.contract,a.case,a.allow_legacy_nominal_keyframes,a.prompt,a.allow_v1_contract,a.compiled);return
    if not a.case:p.error('this stage requires --case')
    if a.stage in ('dino',) and (a.gpu is None or not a.gpu_uuid):p.error('GPU stage requires --gpu and --gpu-uuid')
    if a.stage in ('detect','all') and a.device=='cuda' and (a.gpu is None or not a.gpu_uuid):p.error('CUDA detection requires --gpu and --gpu-uuid')
    if a.run_dino and (a.gpu is None or not a.gpu_uuid):p.error('--run-dino requires --gpu and --gpu-uuid')
    if a.stage=='detect':detect(a.case,a.gpu,a.gpu_uuid,a.shot_workers,a.device,a.binding_protocol,a.detections)
    elif a.stage=='match':match(a.case,a.matching_protocol)
    elif a.stage=='dino_prepare':dino_prepare(a.case)
    elif a.stage=='dino':dino(a.case,a.gpu,a.gpu_uuid)
    elif a.stage=='attach_dino':attach_dino(a.case)
    elif a.stage=='discover_issues':
        if not a.issue_output:p.error('discover_issues requires --issue-output')
        issue_discovery.run(a.case,a.issue_output)
    else:
        if not a.manifest or not a.contract:p.error('all requires --manifest and --contract')
        prepare(a.manifest,a.contract,a.case,a.allow_legacy_nominal_keyframes,a.prompt,a.allow_v1_contract);detect(a.case,a.gpu,a.gpu_uuid,a.shot_workers,a.device,a.binding_protocol);match(a.case,a.matching_protocol);dino_prepare(a.case)
        if a.run_dino:dino(a.case,a.gpu,a.gpu_uuid);attach_dino(a.case)

if __name__=='__main__':main()
