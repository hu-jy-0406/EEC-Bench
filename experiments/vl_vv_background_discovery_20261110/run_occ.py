#!/usr/bin/env python3
"""Round 3: object continuity check (OCC) as extra V-V candidates (overnight iteration, owner decisions in README).
Arms: E = B's case (ledger with discovered objects), F = A's case. Per video one isolated call (GPT-6 Luna, low;
prompt_occ_v0.txt) over all keyframes plus one reference crop per object entity (ledger pb entities whose contract
label is object, and every ge entity, all labels treated alike). Problems are checked (entity ids, evidence frames,
scope), one retry on errors, then appended as V-V candidates to the host arm's own V-V detection result; then V-V
review and episode scoring with code_vv (whose config knows W8/X10) and the host's V-L review."""
import json, sys, shutil, hashlib, subprocess, os, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PIL import Image
EXP = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP / 'code/EECBench/scripts'))
import gs_prompt_binding as gpb
VACE = '/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python'
CODE = EXP / 'code_vv/EECBench'
HOST = dict(E='B', F='A', E2='B', F2='A')  # E2/F2: the same check at reasoning medium (diagnostic)
SUB = {('within_shot', 'missing'): 'presence_instability', ('within_shot', 'appears'): 'presence_instability',
       ('within_shot', 'moves'): 'object_instability', ('within_shot', 'changes'): 'object_instability', ('within_shot', 'other'): 'object_instability',
       ('cross_shot', 'missing'): 'setting_background', ('cross_shot', 'appears'): 'setting_background',
       ('cross_shot', 'moves'): 'spatial_continuity', ('cross_shot', 'changes'): 'object_identity', ('cross_shot', 'other'): 'object_identity'}
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["entities"], "properties": {"entities": {"type": "array", "items": {
    "type": "object", "additionalProperties": False, "required": ["entity", "problems"], "properties": {"entity": {"type": "string"}, "problems": {
        "type": "array", "items": {"type": "object", "additionalProperties": False,
                                   "required": ["scope", "kind", "shots", "evidence", "description"],
                                   "properties": {"scope": {"type": "string", "enum": ["within_shot", "cross_shot"]},
                                                  "kind": {"type": "string", "enum": ["missing", "appears", "moves", "changes", "other"]},
                                                  "shots": {"type": "array", "items": {"type": "string"}},
                                                  "evidence": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                                                          "required": ["shot_id", "frame_id", "observation"],
                                                                                          "properties": {"shot_id": {"type": "string"}, "frame_id": {"type": "integer"},
                                                                                                         "observation": {"type": "string"}}}},
                                                  "description": {"type": "string"}}}}}}}}}


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_text())


def prepare(arm, task):
    host = EXP / 'arms' / HOST[arm] / task; case = host / 'case'
    man = read(case / 'raw_manifest.json'); led = read(case / 'episode_entities.json'); con = read(case / 'contract.json')
    labels = {k: v['label'] for k, v in con['entity_descriptions'].items()}
    paths = {(s['shot_id'], f['frame_id']): f['path'] for s in man['shots'] for f in s['frames']}
    ents = []
    for e in led['prompt_bound']:
        if e.get('occurrences') and labels.get(str(e.get('contract_entity_id', e.get('prompt_entity_id')))) == 'object':
            ents.append((e, 'specified'))
    for e in led['prompt_unbound']:
        if e.get('occurrences'): ents.append((e, 'unspecified'))
    out = EXP / 'arms' / arm / task; (out / 'occ/crops').mkdir(parents=True, exist_ok=True)
    images = [dict(path=paths[(s['shot_id'], f['frame_id'])], sha256=sha(paths[(s['shot_id'], f['frame_id'])]), shot_id=s['shot_id'], frame_id=f['frame_id'])
              for s in man['shots'] for f in s['frames']]
    rows = []
    for e, lab in ents:
        best = max(((o['shot_id'], b) for o in e['occurrences'] for b in o.get('boxes') or []),
                   key=lambda x: (x[1]['box_xyxy'][2] - x[1]['box_xyxy'][0]) * (x[1]['box_xyxy'][3] - x[1]['box_xyxy'][1]), default=None)
        crop_index = None
        if best:
            shot, b = best; im = Image.open(paths[(shot, b['frame_id'])]).convert('RGB'); x0, y0, x1, y1 = b['box_xyxy']
            px, py = 0.15 * (x1 - x0) + 4, 0.15 * (y1 - y0) + 4
            c = im.crop((max(0, x0 - px), max(0, y0 - py), min(im.width, x1 + px), min(im.height, y1 + py)))
            p = out / 'occ/crops' / f"{e['global_entity_id']}.jpg"; c.save(p, quality=92)
            images.append(dict(path=str(p), sha256=sha(p), shot_id=f"{e['global_entity_id']} reference crop from {shot}", frame_id=b['frame_id']))
            crop_index = len(images)
        rows.append(dict(entity=e['global_entity_id'], label=lab, name=e.get('name'), description=e.get('description'),
                         recorded=[dict(shot_id=o['shot_id'], frames=sorted(b['frame_id'] for b in o.get('boxes') or [])) for o in e['occurrences']],
                         reference_crop_image=crop_index))
    prompt = read(case / 'prompt.json')
    payload = dict(shots=[dict(shot_id=s['shot_id'], text=s['text']) for s in prompt['shots']], entities=rows)
    return host, out, man, images, payload


def check(result, payload, man):
    ids = {r['entity'] for r in payload['entities']}; pairs = {(s['shot_id'], f['frame_id']) for s in man['shots'] for f in s['frames']}
    shots = {s['shot_id'] for s in man['shots']}; errs = []
    for e in result['entities']:
        if e['entity'] not in ids: errs.append(f"unknown entity {e['entity']}")
        for i, p in enumerate(e['problems']):
            if not set(p['shots']) <= shots: errs.append(f"{e['entity']} problem {i}: unknown shot")
            if p['scope'] == 'within_shot' and len(set(p['shots'])) != 1: errs.append(f"{e['entity']} problem {i}: within_shot needs exactly one shot")
            if p['scope'] == 'cross_shot' and len(set(p['shots'])) < 2: errs.append(f"{e['entity']} problem {i}: cross_shot needs two or more shots")
            if not p['evidence']: errs.append(f"{e['entity']} problem {i}: no evidence")
            for ev in p['evidence']:
                if (ev['shot_id'], ev['frame_id']) not in pairs: errs.append(f"{e['entity']} problem {i}: evidence frame {ev['shot_id']} {ev['frame_id']} not a keyframe")
    return errs


def stage(out, name, cmd):
    env = os.environ.copy(); env.update(ROCR_VISIBLE_DEVICES='-1', CUDA_VISIBLE_DEVICES='', EECBENCH_REVIEW_PYTHON=VACE)
    t = time.time()
    with open(out / f'{name}.log', 'w') as h:
        rc = subprocess.call([str(CODE / 'scripts/openai_api_env.sh'), *map(str, cmd)], stdout=h, stderr=subprocess.STDOUT, cwd=str(CODE), env=env)
    return rc, round(time.time() - t, 1)


def one(job):
    arm, task = job
    host, out, man, images, payload = prepare(arm, task)
    res = out / 'results'
    if (res / 'episode_scoring/result.json').is_file(): return arm, task, 'skipped'
    prior = out / 'occ/result.json'
    if prior.is_file():
        o = read(prior); result, errs, tries = o['result'], o['remaining_errors'], o['tries']
    elif not payload['entities']: result, errs, tries = dict(entities=[]), [], 0
    else:
        result = gpb.call(out / 'occ/call', payload, images, 900, prompt_path=EXP / 'prompt_occ_v0.txt', schema=SCHEMA, model='gpt-6-luna', reasoning='medium' if arm.endswith('2') else 'low')
        errs = check(result, payload, man); tries = 1
        if errs:
            payload2 = dict(payload, previous_answer_problems=errs)
            result = gpb.call(out / 'occ/call_retry', payload2, images, 900, prompt_path=EXP / 'prompt_occ_v0.txt', schema=SCHEMA, model='gpt-6-luna', reasoning='medium' if arm.endswith('2') else 'low')
            errs = check(result, payload, man); tries = 2
    if not prior.is_file():
        (out / 'occ/result.json').write_text(json.dumps(dict(tries=tries, remaining_errors=errs, result=result), indent=1, ensure_ascii=False) + '\n')
    if res.exists(): shutil.rmtree(res)
    base = read(host / 'results/vv_detection/result.json')
    n = max([int(i['issue_id'][1:].split('.')[0]) for i in base['issues'] if i['issue_id'][1:].split('.')[0].isdigit()] + [0])
    ids = {r['entity'] for r in payload['entities']}; pairs = {(s['shot_id'], f['frame_id']) for s in man['shots'] for f in s['frames']}
    added = []
    for e in result['entities']:
        if e['entity'] not in ids: continue
        for p in e['problems']:
            ev = [x for x in p['evidence'] if (x['shot_id'], x['frame_id']) in pairs]
            shots = sorted(set(p['shots']) & {s['shot_id'] for s in man['shots']}, key=lambda s: int(s[4:]))
            if not ev or not shots or (p['scope'] == 'within_shot' and len(shots) != 1) or (p['scope'] == 'cross_shot' and len(shots) < 2): continue
            n += 1
            added.append(dict(issue_id=f'V{n}', branch='v_v', scope=p['scope'], subcategory=SUB[(p['scope'], p['kind'])], description=p['description'],
                              shot_ids=shots, entity_refs=[dict(entity_key=e['entity'], role='subject')],
                              key_evidence=[dict(shot_id=x['shot_id'], frame_id=x['frame_id'], entity_keys=[e['entity']], observation=x['observation']) for x in ev],
                              confidence='medium', v_l_detail=None, v_v_detail=dict(checklist_items=['W8' if p['scope'] == 'within_shot' else 'X10'])))
    led = read(host / 'case/episode_entities.json')
    rows = {e['global_entity_id']: (e, 'prompt_bound') for e in led['prompt_bound']}
    rows.update({e['global_entity_id']: (e, 'prompt_unbound') for e in led['prompt_unbound']})
    have = {r['entity_key'] for r in base['entities']}; extra = []
    for a in added:
        k = a['entity_refs'][0]['entity_key']
        if k in have or k not in rows: continue
        e, part = rows[k]; have.add(k)
        extra.append(dict(entity_key=k, global_entity_id=k, source='detection_ledger', name=e.get('name'), description=e.get('description'),
                          partition=part, prompt_entity_id=e.get('prompt_entity_id'), frame_refs=[],
                          label='specified' if part == 'prompt_bound' else 'unspecified'))
    merged = dict(base, issues=base['issues'] + added, entities=base['entities'] + extra, occ_added=[a['issue_id'] for a in added],
                  occ_note='object continuity check candidates appended (vl_vv_background_discovery_20261110 run_occ.py)')
    res.mkdir(parents=True, exist_ok=True); (res / 'vv_detection').mkdir(exist_ok=True)
    (res / 'vv_detection/result.json').write_text(json.dumps(merged, indent=1, ensure_ascii=False) + '\n')
    S = CODE / 'scripts'; case = host / 'case'
    for name, cmd in [('vv_review', [VACE, S / 'run_vl_vv_branch_review.py', '--branch', 'vv', '--case', case, '--detection', res / 'vv_detection/result.json',
                                     '--output', res / 'vv_review', '--chain', 'v6']),
                      ('episode_scoring', [VACE, S / 'run_vl_vv_branch_scoring.py', '--vl-review', host / 'results/vl_review/result.json', '--vv-review',
                                           res / 'vv_review/result.json', '--output', res / 'episode_scoring', '--chain', 'v6'])]:
        rc, sec = stage(out, name, cmd)
        if rc: return arm, task, f'failed at {name} (occ added {len(added)})'
    return arm, task, f'success occ_added={len(added)} tries={tries} errors={len(errs)}'


if __name__ == '__main__':
    tasks = [r['task'] for r in read(EXP.parent / 'vl_vv_full_first200_v3_20261109/miss_diagnosis/audit20/index.json')]
    arms = sys.argv[1].split(',') if len(sys.argv) > 1 else ['E', 'F']
    only = sys.argv[2:]
    jobs = [(a, t) for a in arms for t in tasks if not only or t in only]
    with ThreadPoolExecutor(6) as pool:
        for r in pool.map(lambda j: (lambda: one(j))() if True else None, jobs):
            print(*r, flush=True)
