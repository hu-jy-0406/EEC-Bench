#!/usr/bin/env python3
"""EXPERIMENT ONLY (owner, 2026-11-10: "尝试一下添加unspecified分支。U1最好是在前面流程找到的unspecified实体基础上做补充"):
an unspecified-object branch for V-V detection, reviewed by the unchanged V-V review.

Per video, on the rerun v3 case (frozen frontend and ledger, read only):
- U1, one call per shot (GPT-6 Luna, low; prompts/u1_inventory_v0.txt): the shot's six keyframes; keeps every ledger
  unspecified entity of the shot (ge...) and adds the background objects the ledger misses; per object: description,
  location, frames visible, change within the shot; plus one sentence on the view.
- U2, one text-only call per video (Luna, medium; u2_suspects_v0.txt): the inventories of all shots with the shot
  texts and contract places; lists at most 10 suspects (within or across shots) with 2-4 frames to check.
- U3, one call per suspect (Luna, high; u3_verify_v0.txt): only the suspect's frames; real / not_real / unclear, and
  for real a V-V issue (subcategory, description, evidence).
- Real suspects become V-V candidates (issues V1..., checklist item O1; subjects = ledger ids or new entities n1...
  made from U1's new objects), written as a V-V detection result next to the host's entity records, then the frozen
  chain v6 V-V review (two calls, Luna low) runs on these candidates only. No scoring.
Every model call uses the repair loop (all errors back to the model). Code: code/EECBench (frozen live copy,
SHA256SUMS_code_frozen); prompts in prompts/. Logs: runs/events.jsonl. Run inside an owned Slurm allocation, under
code/EECBench/scripts/openai_api_env.sh (the driver does this)."""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

EXP = Path(__file__).resolve().parent
CODE = EXP / 'code/EECBench'
sys.path.insert(0, str(CODE / 'scripts'))
import vl_vv_branch_common as common  # noqa: E402
import vl_vv_repair_loop as repair_loop  # noqa: E402
import run_vl_vv_issue_discovery as discovery_v4  # noqa: E402
import run_vl_vv_branch_detection as det  # noqa: E402

VACE = '/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python'
MODEL = 'gpt-6-luna'
EFFORT = dict(u1='low', u2='medium', u3='high')
PRICE = (0.10, 0.01, 0.50)  # GPT-6 Luna standard USD per 1M: uncached input, cached input, output
PROMPT = dict(u1=EXP / 'prompts/u1_inventory_v0.txt', u2=EXP / 'prompts/u2_suspects_v0.txt',
              u3=EXP / 'prompts/u3_verify_v0.txt')
P1, P2, P3 = 'vl_vv_u1_inventory_exp_v0', 'vl_vv_u2_suspects_exp_v0', 'vl_vv_u3_verify_exp_v0'
CFG = common.config(common.chain_spec('v6')['config'])
WITHIN = ['object_instability', 'presence_instability', 'background_drift', 'relation_break']
CROSS = ['setting_background', 'object_identity', 'instance_count', 'spatial_continuity']
assert set(WITHIN) <= set(CFG['v_v_subcategories']['within_shot'])
assert set(CROSS) <= set(CFG['v_v_subcategories']['cross_shot'])
MAX_SUSPECTS, MAX_OBJECTS = 10, 30
LOCK = threading.Lock()


def obj(props, required=None):
    return dict(type='object', additionalProperties=False, required=required or list(props), properties=props)


S = dict(type='string')
U1_SCHEMA = obj(dict(protocol=dict(type='string', const=P1), view=S, objects=dict(type='array', items=obj(dict(
    ref=S, name=S, description=S, location=S, frames_visible=dict(type='array', items=dict(type='integer')),
    change_within_shot=S)))))
U2_SCHEMA = obj(dict(protocol=dict(type='string', const=P2), suspects=dict(type='array', items=obj(dict(
    scope=dict(type='string', enum=['within_shot', 'cross_shot']), shots=dict(type='array', items=S),
    kind=dict(type='string', enum=['changed', 'missing', 'appears', 'moves', 'duplicated', 'other']),
    objects=dict(type='array', items=obj(dict(shot_id=S, ref=S))), what=S,
    check_frames=dict(type='array', items=obj(dict(shot_id=S, frame_id=dict(type='integer')))))))))
U3_SCHEMA = obj(dict(protocol=dict(type='string', const=P3), verdict=dict(type='string', enum=['real', 'not_real', 'unclear']),
                     reason=S, subcategory=S, description=S,
                     key_evidence=dict(type='array', items=obj(dict(shot_id=S, frame_id=dict(type='integer'), observation=S))),
                     confidence=dict(type='string', enum=['high', 'medium', 'low', ''])))


def log(**row):
    with LOCK, open(EXP / 'runs/events.jsonl', 'a') as h:
        h.write(json.dumps(dict(time=time.strftime('%Y-%m-%dT%H:%M:%S'), **row), ensure_ascii=False) + '\n')


def spent(root):
    total = 0.0
    for st in Path(root).rglob('status.json'):
        try:
            s = json.loads(st.read_text())
        except ValueError:
            continue
        for u in s.get('usage') or s.get('known_usage') or []:
            i, c, o = int(u.get('input_tokens') or 0), int(u.get('cached_input_tokens') or 0), int(u.get('output_tokens') or 0)
            total += ((i - c) * PRICE[0] + c * PRICE[1] + o * PRICE[2]) / 1e6
    return total


def shot_key(s):
    return int(s[4:])


def call(folder, payload, images, schema, step, errors, stage):
    folder.parent.mkdir(parents=True, exist_ok=True)
    value, _, usage, audit = repair_loop.call_with_repair(
        folder, payload, images, 900, prompt_path=PROMPT[step], schema=schema, model=MODEL, reasoning=EFFORT[step],
        collect_errors=lambda c: (errors(c), c), stage=stage, repair_prompt=common.REPAIR_PROMPT)
    return value, audit['repair_rounds']


def context(case_dir):
    case, contract, manifest, ledger = det.load_case(Path(case_dir), False)
    images = discovery_v4.image_rows(case, manifest)
    prompt = contract.get('prompt') or {}
    texts = {row['shot_id']: row.get('text', '') for row in prompt.get('shots', [])}
    ents = contract['entity_descriptions']
    places = {s['shot_id']: [ents[str(i)]['name'] for i in s.get('locations') or [] if str(i) in ents] for s in contract['shots']}
    return case, contract, manifest, ledger, images, prompt, texts, places


def u1(out, ctx, shot):
    case, contract, manifest, ledger, images, prompt, texts, places = ctx
    rows = [r for r in images if r['shot_id'] == shot]
    frames = {r['frame_id'] for r in rows}
    spec, unspec = [], []
    for kind, bucket in (('prompt_bound', spec), ('prompt_unbound', unspec)):
        for e in ledger[kind]:
            for o in e.get('occurrences') or []:
                if o['shot_id'] == shot:
                    boxed = sorted({b['frame_id'] for b in o.get('boxes') or []})
                    bucket.append(dict(id=e['global_entity_id'], name=e.get('name'), description=e.get('description'),
                                       boxed_frames=boxed) if kind == 'prompt_unbound' else
                                  dict(id=e['global_entity_id'], name=e.get('name')))
    registered = {r['id'] for r in unspec}
    payload = dict(protocol=P1, shot_id=shot, shot_text=texts.get(shot, ''), global_prompt=prompt.get('global_prompt', ''),
                   contract_entities=[dict(id=k, label=v['label'], name=v['name'], description=v.get('description', ''))
                                      for k, v in contract['entity_descriptions'].items()],
                   REGISTERED_SPECIFIED=spec, REGISTERED_UNSPECIFIED=unspec, image_order=common.image_order(rows))

    def errors(c):
        e, seen = [], []
        if len(c['objects']) > MAX_OBJECTS:
            e.append(f'objects: at most {MAX_OBJECTS} entries')
        for i, o in enumerate(c['objects']):
            w = f'objects[{i}] {o["name"]!r}'
            if o['ref'] != 'new' and o['ref'] not in registered:
                e.append(f'{w}: ref must be "new" or an id of REGISTERED_UNSPECIFIED {sorted(registered)}')
            if o['ref'] in registered:
                seen.append(o['ref'])
            if not set(o['frames_visible']) <= frames:
                e.append(f'{w}: frames_visible must be keyframes of {shot}: {sorted(frames)}')
            if o['ref'] == 'new' and not o['frames_visible']:
                e.append(f'{w}: a new object must be visible in at least one keyframe')
            if not o['name'].strip() or not o['change_within_shot'].strip():
                e.append(f'{w}: name and change_within_shot must not be empty ("none" when nothing changes)')
        for r in sorted(registered):
            if seen.count(r) != 1:
                e.append(f'REGISTERED_UNSPECIFIED {r}: needs exactly one entry (found {seen.count(r)})')
        return e
    value, repairs = call(out / 'u1' / shot / 'call', payload, rows, U1_SCHEMA, 'u1', errors, f'U1 {shot}')
    n, inv = 0, []
    for o in value['objects']:
        if o['ref'] == 'new':
            n += 1
            key = f'{shot}/o{n}'
        else:
            key = o['ref']
        inv.append(dict(o, ref=key, frames_visible=sorted(set(o['frames_visible']))))
    res = dict(shot_id=shot, view=value['view'], inventory=inv, repair_rounds=repairs)
    (out / 'u1' / shot / 'inventory.json').write_text(json.dumps(res, indent=1, ensure_ascii=False) + '\n')
    return res


def u2(out, ctx, inventories):
    case, contract, manifest, ledger, images, prompt, texts, places = ctx
    pairs = common.frame_pairs(manifest)
    refs = {s: {o['ref'] for o in inventories[s]['inventory']} for s in inventories}
    payload = dict(protocol=P2, global_prompt=prompt.get('global_prompt', ''), shots=[dict(
        shot_id=s, text=texts.get(s, ''), places=places.get(s, []), view=inventories[s]['view'],
        inventory=[{k: o[k] for k in ('ref', 'name', 'description', 'location', 'frames_visible', 'change_within_shot')}
                   for o in inventories[s]['inventory']]) for s in common.shot_ids(manifest)])
    shots = set(common.shot_ids(manifest))

    def errors(c):
        e = []
        if len(c['suspects']) > MAX_SUSPECTS:
            e.append(f'suspects: at most {MAX_SUSPECTS}')
        for i, s in enumerate(c['suspects']):
            w = f'suspects[{i}]'
            sh = s['shots']
            if not set(sh) <= shots or len(set(sh)) != len(sh):
                e.append(f'{w}: shots must be distinct shot ids of {sorted(shots, key=shot_key)}')
                continue
            if s['scope'] == 'within_shot' and len(sh) != 1:
                e.append(f'{w}: within_shot has exactly one shot')
            if s['scope'] == 'cross_shot' and len(sh) < 2:
                e.append(f'{w}: cross_shot has two or more shots')
            if not s['objects']:
                e.append(f'{w}: objects must name at least one inventory entry')
            for o in s['objects']:
                if o['shot_id'] not in sh or o['ref'] not in refs.get(o['shot_id'], set()):
                    e.append(f'{w}: object {o["shot_id"]} {o["ref"]} is not an inventory entry of a shot of this suspect')
            cf = [(f['shot_id'], f['frame_id']) for f in s['check_frames']]
            if not 2 <= len(cf) <= 4 or len(set(cf)) != len(cf):
                e.append(f'{w}: check_frames needs 2 to 4 distinct keyframes')
            for f in cf:
                if f not in pairs or f[0] not in sh:
                    e.append(f'{w}: check frame {f[0]} {f[1]} is not a keyframe of a shot of this suspect')
            if s['scope'] == 'cross_shot' and not set(sh) <= {f[0] for f in cf}:
                e.append(f'{w}: cross_shot check_frames need at least one frame of each of its shots')
        return e
    if not any(inventories[s]['inventory'] for s in inventories):
        value, repairs = dict(protocol=P2, suspects=[]), 0
    else:
        value, repairs = call(out / 'u2' / 'call', payload, [], U2_SCHEMA, 'u2', errors, 'U2')
    (out / 'u2' / 'suspects.json').parent.mkdir(parents=True, exist_ok=True)
    (out / 'u2' / 'suspects.json').write_text(json.dumps(dict(value, repair_rounds=repairs), indent=1, ensure_ascii=False) + '\n')
    return value['suspects']


def u3(out, ctx, inventories, index, s):
    case, contract, manifest, ledger, images, prompt, texts, places = ctx
    by = {(r['shot_id'], r['frame_id']): r for r in images}
    cf = sorted({(f['shot_id'], f['frame_id']) for f in s['check_frames']}, key=lambda p: (shot_key(p[0]), p[1]))
    rows = [by[p] for p in cf]
    inv = {(sh, o['ref']): o for sh in inventories for o in inventories[sh]['inventory']}
    allowed = WITHIN if s['scope'] == 'within_shot' else CROSS
    payload = dict(protocol=P3, shots=[dict(shot_id=sh, text=texts.get(sh, '')) for sh in s['shots']],
                   SUSPECT=dict(scope=s['scope'], kind=s['kind'], what=s['what'], objects=[dict(
                       shot_id=o['shot_id'], **{k: inv[(o['shot_id'], o['ref'])][k] for k in
                                               ('ref', 'name', 'description', 'location', 'frames_visible', 'change_within_shot')})
                       for o in s['objects']]),
                   allowed_subcategories={k: CFG['v_v_subcategories'][s['scope']][k] for k in allowed},
                   image_order=common.image_order(rows))
    attached = set(cf)

    def errors(c):
        if c['verdict'] != 'real':
            return []
        e = []
        if c['subcategory'] not in allowed:
            e.append(f'subcategory must be one of {allowed}')
        if not c['description'].strip():
            e.append('description must not be empty for a real verdict')
        if c['confidence'] not in ('high', 'medium', 'low'):
            e.append('confidence must be high, medium or low for a real verdict')
        ev = [(x['shot_id'], x['frame_id']) for x in c['key_evidence']]
        if len(set(ev)) < 2:
            e.append('key_evidence needs two or more distinct attached frames')
        for p in ev:
            if p not in attached:
                e.append(f'key_evidence frame {p[0]} {p[1]} is not attached; use only {sorted(attached)}')
        if s['scope'] == 'cross_shot' and len({p[0] for p in ev}) < 2:
            e.append('cross_shot key_evidence needs frames of at least two shots')
        return e
    value, repairs = call(out / 'u3' / f's{index}' / 'call', payload, rows, U3_SCHEMA, 'u3', errors, f'U3 suspect {index}')
    res = dict(index=index, suspect=s, result=value, repair_rounds=repairs)
    (out / 'u3' / f's{index}' / 'verdict.json').write_text(json.dumps(res, indent=1, ensure_ascii=False) + '\n')
    return res


def build_detection(out, ctx, host_detection, inventories, verified):
    case, contract, manifest, ledger, images, prompt, texts, places = ctx
    base = json.loads(Path(host_detection).read_text())
    led = {e['global_entity_id']: (e, kind) for kind in ('prompt_bound', 'prompt_unbound') for e in ledger[kind]}
    have = {r['entity_key'] for r in base['entities']}
    inv = {(sh, o['ref']): o for sh in inventories for o in inventories[sh]['inventory']}
    added, new_key, extra, issues = [], {}, [], []
    for v in verified:
        r, s = v['result'], v['suspect']
        if r['verdict'] != 'real':
            continue
        keys = []
        for o in s['objects']:
            ref = o['ref']
            if ref in led:
                if ref not in have:
                    e, part = led[ref]
                    extra.append(dict(entity_key=ref, global_entity_id=ref, source='detection_ledger', name=e.get('name'),
                                      description=e.get('description'), partition=part,
                                      prompt_entity_id=e.get('prompt_entity_id'), frame_refs=[],
                                      label='specified' if part == 'prompt_bound' else 'unspecified'))
                    have.add(ref)
                keys.append(ref)
            else:
                if ref not in new_key:
                    new_key[ref] = f'n{len(new_key) + 1}'
                    entry = inv[(o['shot_id'], ref)]
                    added.append(dict(entity_key=new_key[ref], global_entity_id=None, source='added_by_vv_detection',
                                      name=entry['name'], description=entry['description'], partition=None,
                                      prompt_entity_id=None, label='unspecified',
                                      frame_refs=[dict(shot_id=o['shot_id'], frame_id=f) for f in entry['frames_visible']]))
                keys.append(new_key[ref])
        keys = list(dict.fromkeys(keys))
        issues.append(dict(issue_id=f'V{len(issues) + 1}', branch='v_v', scope=s['scope'], subcategory=r['subcategory'],
                           description=r['description'], shot_ids=sorted(set(s['shots']), key=shot_key),
                           entity_refs=[dict(entity_key=k, role='subject') for k in keys],
                           key_evidence=[dict(shot_id=x['shot_id'], frame_id=x['frame_id'], entity_keys=keys,
                                              observation=x['observation']) for x in r['key_evidence']],
                           confidence=r['confidence'], v_l_detail=None, v_v_detail=dict(checklist_items=['O1'])))
    result = dict(base, issues=issues, entities=base['entities'] + extra + added,
                  u_branch=dict(note='EXPERIMENT vl_vv_unspecified_branch_20261110: candidates of the unspecified branch '
                                     'only (the host detection issues are not included)',
                                host_detection=str(host_detection), suspects=len(verified),
                                real=sum(v['result']['verdict'] == 'real' for v in verified)))
    path = out / 'vv_detection/result.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1, ensure_ascii=False) + '\n')
    return path, len(issues)


def review(out, case, detection_path):
    env = os.environ.copy()
    env.update(ROCR_VISIBLE_DEVICES='-1', CUDA_VISIBLE_DEVICES='', EECBENCH_REVIEW_PYTHON=VACE, EECBENCH_API_MODEL=MODEL,
               OMP_NUM_THREADS='2')
    with open(out / 'vv_review.log', 'w') as h:
        return subprocess.call([VACE, str(CODE / 'scripts/run_vl_vv_branch_review.py'), '--branch', 'vv', '--case', str(case),
                                '--detection', str(detection_path), '--output', str(out / 'vv_review'), '--chain', 'v6'],
                               stdout=h, stderr=subprocess.STDOUT, cwd=str(CODE), env=env)


def run_video(task, row, workers):
    out = EXP / 'runs' / task
    if (out / 'done.json').is_file():
        return 'skipped'
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    ctx = context(row['case_dir'])
    shots = common.shot_ids(ctx[2])
    with ThreadPoolExecutor(workers) as pool:
        inventories = {r['shot_id']: r for r in pool.map(lambda s: u1(out, ctx, s), shots)}
    t1 = time.time()
    suspects = u2(out, ctx, inventories)
    t2 = time.time()
    with ThreadPoolExecutor(workers) as pool:
        verified = list(pool.map(lambda a: u3(out, ctx, inventories, a[0], a[1]), enumerate(suspects, 1)))
    t3 = time.time()
    detection_path, n = build_detection(out, ctx, Path(row['output_dir']) / 'vv_detection/result.json', inventories, verified)
    rc = review(out, ctx[0], detection_path) if n else 0
    t4 = time.time()
    if rc:
        return f'failed at review (exit {rc})'
    summary = dict(task=task, objects=sum(len(r['inventory']) for r in inventories.values()),
                   new_objects=sum(o['ref'] not in {e['global_entity_id'] for e in ctx[3]['prompt_unbound']}
                                   for r in inventories.values() for o in r['inventory']),
                   suspects=len(suspects), real=n, seconds=dict(u1=round(t1 - t0, 1), u2=round(t2 - t1, 1),
                                                             u3=round(t3 - t2, 1), review=round(t4 - t3, 1)),
                   usd=round(spent(out), 6))
    (out / 'done.json').write_text(json.dumps(summary, indent=1) + '\n')
    return f'success {summary}'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--set', choices=['dev', 'val', 'all'], default='all')
    p.add_argument('--only', nargs='*')
    p.add_argument('--threads', type=int, default=4)
    p.add_argument('--workers', type=int, default=6)
    p.add_argument('--cap', type=float, default=1.0)
    a = p.parse_args()
    if not os.environ.get('SLURM_JOB_ID'):
        raise RuntimeError('Run inside an owned Slurm allocation')
    (EXP / 'runs').mkdir(exist_ok=True)
    dev = json.loads((EXP.parent / 'vl_vv_stronger_vv_recall_20261110/baseline_usage.json').read_text())
    val = json.loads((EXP.parent / 'vl_vv_view_pair_validation_20261110/videos.json').read_text())
    rows = {}
    if a.set in ('dev', 'all'):
        rows.update({t: dict(case_dir=dev['rows'][t]['case_dir'], output_dir=dev['rows'][t]['output_dir'], set='dev')
                     for t in dev['target_videos']})
    if a.set in ('val', 'all'):
        rows.update({t: dict(v, set='val') for t, v in val.items()})
    tasks = [t for t in rows if not a.only or t in a.only]
    log(event='started', tasks=len(tasks), cap=a.cap, host=os.uname().nodename, slurm=os.environ['SLURM_JOB_ID'],
        effort=EFFORT, model=MODEL)
    reserved = {}

    def job(t):
        with LOCK:
            if spent(EXP / 'runs') + sum(reserved.values()) + 0.06 > a.cap:
                return t, 'not started: budget gate'
            reserved[t] = 0.06
        try:
            log(event='start', task=t, set=rows[t]['set'])
            try:
                r = run_video(t, rows[t], a.workers)
            except Exception as exc:  # noqa: BLE001 - record and continue with the other videos
                r = f'failed: {type(exc).__name__}: {exc}'[:500]
            log(event='result', task=t, result=r, spent_usd=round(spent(EXP / 'runs'), 6))
            return t, r
        finally:
            with LOCK:
                reserved.pop(t, None)
    with ThreadPoolExecutor(a.threads) as pool:
        for t, r in pool.map(job, tasks):
            print(t, r, flush=True)
    log(event='finished', spent_usd=round(spent(EXP / 'runs'), 6))
    print('spent (GPT-6 Luna standard-price estimate, USD):', round(spent(EXP / 'runs'), 6))


if __name__ == '__main__':
    main()
