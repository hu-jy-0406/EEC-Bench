#!/usr/bin/env python3
"""Frozen prompt registry -> audited global visual entity binding; no identity edits."""
import argparse
import csv
import copy
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import time

from gs_consistency_contract import obj, arr, enum, S, I
import run_wedetect_shot_entities as io

ROOT = Path(__file__).resolve().parents[1]
PROMPT = ROOT / 'prompts/gs_prompt_binding_v1.txt'
SCHEMA = obj(bindings=arr(obj(global_entity_id=S, status=enum('bound', 'unbound', 'unknown'),
    prompt_entity_id=dict(type=['string', 'null']), candidate_prompt_entity_ids=arr(S),
    fact_ids=arr(S), witnesses=arr(obj(shot_id=S, frame_id=I)),
    comparison_witnesses=arr(obj(global_entity_id=S, shot_id=S, frame_id=I)), reason=S)))


def output_schema():
    """Expose existing materialize field invariants to structured generation.

    SCHEMA remains the structural/legacy reader contract. Entity ownership,
    valid source IDs and instance competition still require materialize.
    """
    schema = copy.deepcopy(SCHEMA)
    row = schema['properties']['bindings']['items']
    variants = []
    for status in ('bound', 'unbound', 'unknown'):
        variant = copy.deepcopy(row)
        fields = variant['properties']
        fields['status'] = enum(status)
        if status == 'bound':
            fields['prompt_entity_id'] = dict(type='string', minLength=1)
            fields['candidate_prompt_entity_ids']['maxItems'] = 0
            fields['fact_ids']['minItems'] = 1
            fields['witnesses']['minItems'] = 1
        else:
            fields['prompt_entity_id'] = dict(type='null')
            fields['fact_ids']['maxItems'] = 0
            if status == 'unbound':
                fields['candidate_prompt_entity_ids']['maxItems'] = 0
        variants.append(variant)
    schema['properties']['bindings']['items'] = dict(anyOf=variants)
    return schema


OUTPUT_SCHEMA = output_schema()
read, save, sha = io.read, io.dump, io.sha


def validate_registry(registry, shots, narrative):
    if registry.get('schema_version') != 'prompt_registry_v1':
        raise ValueError('Expected prompt_registry_v1')
    ids = [s['shot_id'] for s in shots]
    if len(ids) != len(set(ids)) or registry['shot_ids'] != ids:
        raise ValueError('Registry shot order differs from manifest')
    facts = {f['fact_id']: f['text'] for f in narrative['facts']}
    seen = set()
    for e in registry['entities']:
        pid = e['prompt_entity_id']
        if not isinstance(pid, str) or not pid or pid in seen:
            raise ValueError('Invalid/duplicate prompt entity ID')
        seen.add(pid)
        if not e['name'].strip() or not e['description'].strip() or not e['evidence']:
            raise ValueError('Entity needs description and prompt evidence')
        for ev in e['evidence']:
            if ev['fact_id'] not in facts or not ev['quote'] or ev['quote'] not in facts[ev['fact_id']]:
                raise ValueError('Prompt evidence must quote supplied narrative facts')
        if [r['shot_id'] for r in e['schedule']] != ids:
            raise ValueError('Schedule must explicitly cover every shot in order')
        if any(r['expectation'] not in ('required', 'not_required', 'forbidden', 'unknown')
               or not r['reason'].strip() for r in e['schedule']):
            raise ValueError('Invalid schedule expectation/reason')
    return registry


def materialize(raw, registry, visual):
    import jsonschema
    # Old saved bindings contain own-entity witnesses only; preserve compatibility.
    raw=copy.deepcopy(raw)
    for row in raw.get('bindings', []):
        row.setdefault('comparison_witnesses', [])
    jsonschema.validate(raw, SCHEMA)
    entities = {e['global_entity_id']: e for e in visual['entities']}
    prompts = {e['prompt_entity_id']: e for e in registry['entities']}
    fact_ids = {v['fact_id'] for p in prompts.values() for v in p['evidence']}
    rows = raw['bindings']
    if len(rows) != len(entities) or {r['global_entity_id'] for r in rows} != set(entities):
        raise ValueError('Binding must cover visual inventory exactly once')
    claimed = set()
    for row in rows:
        e = entities[row['global_entity_id']]; pid = row['prompt_entity_id']
        if not row['reason'].strip():
            raise ValueError('Missing reason')
        candidates = row['candidate_prompt_entity_ids']
        if len(candidates) != len(set(candidates)) or not set(candidates) <= set(prompts):
            raise ValueError('Invalid candidate IDs')
        valid = {(a['shot_id'], fid) for a in e['appearances'] for fid in a['observed_frame_ids']}
        if any((w['shot_id'], w['frame_id']) not in valid for w in row['witnesses']):
            raise ValueError('Witness is not a positive observation of this entity')
        for witness in row['comparison_witnesses']:
            other=entities.get(witness['global_entity_id'])
            if other is None or witness['global_entity_id']==row['global_entity_id']:
                raise ValueError('Comparison witness must name another existing visual entity')
            other_valid={(a['shot_id'], fid) for a in other['appearances'] for fid in a['observed_frame_ids']}
            if (witness['shot_id'], witness['frame_id']) not in other_valid:
                raise ValueError('Comparison witness is not a positive observation of the referenced entity')
        if row['status'] == 'bound':
            if pid not in prompts or candidates or not row['witnesses'] or not row['fact_ids']:
                raise ValueError('Bound needs one prompt ID, facts and visual witnesses')
            if not set(row['fact_ids']) <= fact_ids:
                raise ValueError('Wrong prompt fact')
            for sid in e['observed_shot_ids']:
                if (pid, sid) in claimed:
                    raise ValueError('Two visual records compete for one prompt instance in a shot')
                claimed.add((pid, sid))
        elif pid is not None or row['fact_ids'] or (row['status'] == 'unbound' and candidates):
            raise ValueError('Non-bound rows cannot claim a confirmed prompt correspondence')
    ordered = [dict(next(r for r in rows if r['global_entity_id'] == eid),
                    name=e['name'], observed_shot_ids=e['observed_shot_ids']) for eid, e in entities.items()]
    schedule_rows = []
    for pid, p in prompts.items():
        for sched in p['schedule']:
            sid = sched['shot_id']
            matched = [r['global_entity_id'] for r in ordered if r['prompt_entity_id'] == pid and sid in r['observed_shot_ids']]
            uncertain = [r['global_entity_id'] for r in ordered if pid in r['candidate_prompt_entity_ids'] and sid in r['observed_shot_ids']]
            schedule_rows.append(dict(prompt_entity_id=pid, **sched, matched_global_entity_ids=matched,
                candidate_global_entity_ids=uncertain, observation='matched' if matched else 'unknown',
                schedule_assessment='not_evaluated'))
    return dict(protocol='prompt_binding_v1', witness_protocol='own_and_comparison_v2', status='success', bindings=ordered,
        counts={s: sum(r['status'] == s for r in rows) for s in ('bound', 'unbound', 'unknown')},
        prompt_entities=len(prompts), schedule=schedule_rows,
        unmatched_prompt_entity_ids=[pid for pid in prompts if not any(r['prompt_entity_id'] == pid for r in rows)],
        global_identity_changes=False, missing_observation_is_absence=False,
        limitations='Prompt correspondence does not establish cross-scene visual identity. No schedule compliance/prompt fidelity score.')


def call(folder, payload, images, timeout, *, prompt_path=None, schema=None, input_transport="canonical", model="gpt-6-astra", reasoning="medium", previous_response_id=None, trailing_text=None, prompt_cache_key=None, prompt_role=None):
    # trailing_text / prompt_cache_key (2026-11-09): sent by the API shim as a second user message after the
    # prompt and images, and as the Responses API prompt_cache_key; prompt_role='developer' sends the prompt text as
    # a developer message before the images (prompt caching); the Codex CLI backend has none of them.
    if (trailing_text or prompt_cache_key or prompt_role) and os.environ.get('EECBENCH_CODEX_BACKEND', 'cli') != 'api':
        raise ValueError('trailing_text, prompt_cache_key and prompt_role need the API backend (EECBENCH_CODEX_BACKEND=api)')
    prompt_path = Path(prompt_path) if prompt_path else PROMPT
    schema = OUTPUT_SCHEMA if schema is None else schema
    if input_transport not in ('canonical','compact'):raise ValueError('Unknown input transport')
    folder.mkdir(parents=True, exist_ok=False)
    wire=payload;guide=''
    if input_transport=='compact':
        from gs_flow1_compact_payload import pack, GUIDE
        wire=pack(payload);guide='\n'+GUIDE
        save(folder/'wire_input.json',wire)
    prompt = prompt_path.read_text() + guide + '\nINPUT:\n' + json.dumps(wire, ensure_ascii=False, separators=(',', ':'))
    (folder / 'prompt.txt').write_text(prompt); save(folder / 'input.json', payload); save(folder / 'output.schema.json', schema)
    if trailing_text: (folder / 'trailing.txt').write_text(trailing_text)
    state = dict(status='running', started=time.time(), model=model, reasoning=reasoning,input_transport=input_transport)
    save(folder / 'status.json', state)
    try:
        with tempfile.TemporaryDirectory(prefix='eec-binding-') as tmp:
            command = [io.resolve_codex_bin('codex'), '--ask-for-approval', 'never', 'exec', '--ignore-user-config', '-c', io.disabled_skills_config(),
                '--ephemeral', '--skip-git-repo-check', '--sandbox', 'read-only', '--color', 'never', '--json',
                '--model', model, '-c', 'model_reasoning_effort="' + reasoning + '"', '-c', 'project_doc_max_bytes=0',
                '-c', 'web_search="disabled"', '--output-schema', str(folder / 'output.schema.json'),
                '--output-last-message', str(folder / 'response.json'), '--cd', tmp] + (['--previous-response-id', previous_response_id] if previous_response_id else [])
            if trailing_text: command += ['--trailing-text-file', str(folder / 'trailing.txt')]
            if prompt_cache_key: command += ['--prompt-cache-key', prompt_cache_key]
            if prompt_role: command += ['--prompt-role', prompt_role]
            for feature in ('shell_tool','unified_exec','view_image','apps','plugins','hooks','multi_agent','memories','skill_search','browser_use','computer_use','code_mode','code_mode_only','workspace_dependencies'):
                command += ['--disable', feature]
            for i, img in enumerate(images):
                target = Path(tmp) / f'image_{i}.jpg'; shutil.copy2(img['path'], target)
                if sha(target) != img['sha256']: raise ValueError('Image changed before call')
                command += ['--image', str(target)]
            labels = io.image_labels(images)
            for label in labels or []:
                command += ['--image-label', label]
            command += ['-']; save(folder / 'request.json', dict(command=command, images=images, **io.image_label_record(labels)))
            io.run_process(command, prompt, Path(tmp), folder / 'events.jsonl', folder / 'stderr.log', timeout)
        state['transport_status'] = 'success'
        state['usage'] = io.audit_events(folder / 'events.jsonl')
        state['validation_phase'] = 'output_schema'
        result = read(folder / 'response.json')
        import jsonschema
        jsonschema.validate(result, schema)
        state.update(status='success', validation_status='passed')
        return result
    except BaseException as exc:
        state.update(status='failed', error=str(exc))
        if state.get('validation_phase'):
            state['validation_status'] = 'failed'
        if 'usage' not in state and (folder / 'events.jsonl').exists():
            try: state['known_usage'] = io.audit_events(folder / 'events.jsonl')
            except Exception: state['usage_unavailable'] = True
        raise
    finally:
        state.update(seconds=time.time()-state['started']); save(folder / 'status.json', state)



def reuse_shot_bindings(case, registry, visual):
    """Lift unanimous own-shot bindings only after audited visual identity export."""
    root = Path(case) / 'shot_prompt_recovery'
    if not (root/'results.json').exists(): return [], []
    if read(root/'results.json')['status'] != 'success': raise ValueError('Incomplete shot recovery')
    if read(root/'prompt_registry.json') != registry: raise ValueError('Shot/global registry mismatch')
    paths=[root/'shots'/sid/'binding_final.json' for sid in registry['shot_ids']]
    local={(sid,r['entity_id']):r for sid,p in zip(registry['shot_ids'],paths) for r in read(p)['bindings']}
    prompts={p['prompt_entity_id']:p for p in registry['entities']};reused=[]
    for e in visual['entities']:
        rows=[local[(a['shot_id'],a['local_entity_id'])] for a in e['appearances']]
        statuses={r['status'] for r in rows};pids={r['prompt_entity_id'] for r in rows}
        if len(statuses)!=1 or 'unknown' in statuses or len(pids)!=1:continue
        status=rows[0]['status'];pid=rows[0]['prompt_entity_id']
        witnesses=[dict(shot_id=a['shot_id'],frame_id=fid) for a,r in zip(e['appearances'],rows) for fid in r['witness_frame_ids']]
        reused.append(dict(global_entity_id=e['global_entity_id'],status=status,prompt_entity_id=pid,
            candidate_prompt_entity_ids=[],fact_ids=list(dict.fromkeys(v['fact_id'] for v in prompts[pid]['evidence'])) if pid else [],
            witnesses=witnesses,comparison_witnesses=[],reason='All audited local occurrences agree on the shot-level prompt binding.'))
    return reused, paths+[root/'results.json',root/'prompt_registry.json']


def run(case, registry_path, out, timeout=900, narrative_path=None):
    case, registry_path, out = map(lambda p: Path(p).resolve(), (case, registry_path, out))
    if out.exists(): raise FileExistsError('Use a fresh binding output')
    narrative_path = Path(narrative_path).resolve() if narrative_path else case / 'narrative.json'
    shots = read(case / 'raw_manifest.json')['shots']; narrative = read(narrative_path)
    registry = validate_registry(read(registry_path), shots, narrative)
    visual_path = case / 'global_entities/global_entities.json'; visual = read(visual_path)
    if visual['shot_order'] != registry['shot_ids']: raise ValueError('Visual shot order differs')
    io.safe_compute()
    sources = {str(p): sha(p) for p in [registry_path, visual_path, case/'raw_manifest.json', narrative_path, PROMPT, Path(__file__).resolve()]}
    images = [dict(f, shot_id=s['shot_id']) for s in shots for f in s['frames']]
    for image in images:
        if sha(image['path']) != image['sha256']: raise ValueError('Changed original frame')
        sources[image['path']] = image['sha256']
    # No upstream verdicts, geometry, anomaly scores or generation error instructions.
    entities = [dict(global_entity_id=e['global_entity_id'], name=e['name'],
        observed_shot_ids=e['observed_shot_ids'], appearances=[dict(shot_id=a['shot_id'], name=a['name'], observed_frame_ids=a['observed_frame_ids'],
        observations=[dict(frame_id=o['frame_id'], box_xyxy=o['box_xyxy']) for o in a['observations']]) for a in e['appearances']]) for e in visual['entities']]
    payload = dict(registry=registry, visual_entities=entities,
        image_order=[dict(index=i, shot_id=f['shot_id'], frame_id=f['frame_id']) for i,f in enumerate(images)])
    reused, reuse_paths = reuse_shot_bindings(case, registry, visual)
    sources.update({str(p):sha(p) for p in reuse_paths})
    reused_ids={r['global_entity_id'] for r in reused}
    payload['visual_entities']=[e for e in entities if e['global_entity_id'] not in reused_ids]
    out.mkdir(parents=True); save(out/'prompt_registry.json', registry); save(out/'source_hashes.json', sources)
    save(out/'reused_shot_bindings.json',dict(bindings=reused,remaining_global_ids=[e['global_entity_id'] for e in payload['visual_entities']]))
    if payload['visual_entities']:
        raw = call(out/'calls/binding', payload, images, timeout)
        status_path = out/'calls/binding/status.json'; state = read(status_path)
    else:
        raw=dict(bindings=[]);status_path=out/'aggregation_status.json'
        state=dict(status='success',usage=[],seconds=0,calls=0)
    raw=dict(bindings=reused+raw['bindings'])
    save(out/'combined_binding_response.json',raw)
    phase = 'binding_semantics'
    try:
        result = materialize(raw, registry, visual)
        phase = 'source_integrity'
        for p,h in sources.items():
            if sha(p) != h: raise ValueError('Source changed: '+p)
    except Exception as exc:
        # A completed API response is not a successful binding judgment.
        # Keep its raw output and usage; never silently repair or retry it.
        state.update(status='failed', validation_status='failed',
                     validation_phase=phase, error=str(exc))
        save(status_path, state)
        raise
    state.update(validation_status='passed', validation_phase='binding_complete')
    save(status_path, state)
    from gs_entity_appearance_compact import cost
    usage = state['usage']; result['usage'] = usage
    result['total_tokens'] = sum(u['input_tokens']+u['output_tokens'] for u in usage)
    result['standard_api_equivalent_usd'] = cost(usage)
    result['cost_basis'] = 'Existing pipeline Astra rates: USD 10/1/12.5/50 per million uncached/cache-read/cache-write/output; long-context multipliers retained. Standard API equivalent, not billed amount.'
    result['source_case'] = str(case); result['seconds'] = state['seconds']
    save(out/'results.json', result)
    lines = ['# Prompt binding', '', '| Global entity | Name | Binding | Prompt ID | Reason |', '|---|---|---|---|---|']
    for row in result['bindings']:
        lines.append('| '+' | '.join(str(row[k] or '').replace('|','\\|').replace('\n',' ') for k in ('global_entity_id','name','status','prompt_entity_id','reason'))+' |')
    (out/'bindings.md').write_text('\n'.join(lines)+'\n')
    return result


def grouped_report(binding, appearance_csv, out):
    """Partition existing appearance scores; no rerun, new weights, or SB/SU claims."""
    data = read(binding)
    with Path(appearance_csv).open() as handle:
        rows = list(csv.DictReader(handle))
    by_id = {r['global_entity_id']: r for r in rows}
    if len(by_id) != len(rows) or set(by_id) != {r['global_entity_id'] for r in data['bindings']}:
        raise ValueError('Appearance/binding population mismatch')
    result = dict(protocol='prompt_binding_appearance_groups_v1', groups={},
        limitations='Groups count frozen global records, not unique prompt IDs; cross-scene records not merged. These are conditional appearance scores, not complete SB/SU.',
        source_hashes={str(Path(p).resolve()):sha(p) for p in (binding,appearance_csv)})
    for status in ('bound','unbound','unknown'):
        ids = [r['global_entity_id'] for r in data['bindings'] if r['status']==status]
        vals = [float(by_id[i]['codex_score']) for i in ids if by_id[i]['codex_score'] not in ('','None')]
        dino = [float(by_id[i]['dino_score']) for i in ids if by_id[i]['dino_score'] not in ('','None')]
        result['groups'][status] = dict(global_entity_ids=ids, count=len(ids), scored=len(vals), null_count=len(ids)-len(vals),
            codex_score=100-math.sqrt(sum((100-v)**2 for v in vals)/len(vals)) if vals else None,
            codex_mean=sum(vals)/len(vals) if vals else None, dino_mean=sum(dino)/len(dino) if dino else None,
            dino_null_count=len(ids)-len(dino))
    save(Path(out), result); return result


def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='phase',required=True)
    runp=sub.add_parser('run')
    for key in ('case','registry','out'): runp.add_argument('--'+key,type=Path,required=True)
    runp.add_argument('--timeout',type=int,default=900)
    runp.add_argument('--narrative',type=Path,help='Explicit independent evaluation reference; leaves case narrative unchanged')
    report=sub.add_parser('report')
    for key in ('binding','appearance-csv','out'): report.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args()
    if a.phase=='run': print(json.dumps(run(a.case,a.registry,a.out,a.timeout,a.narrative)['counts']))
    else: print(json.dumps(grouped_report(a.binding,a.appearance_csv,a.out)['groups']))


if __name__=='__main__': main()
