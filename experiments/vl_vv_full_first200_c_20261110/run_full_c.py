#!/usr/bin/env python3
"""Full first-200 run of pipeline C, without and with the unspecified branch as a plug-in (owner, 2026-11-10: "我希望的是
新流程把C设为默认，然后把这个unspecify专属分支作为plug in ... 我睡觉的时候你用带/不带这个分支的C把200个episode全量开跑").

Per video (the 1,000 videos of the first-200 rerun v3; their cases are the read-only sources):
  C frontend (overnight arm B of ../vl_vv_background_discovery_20261110, code/EECBench frozen at 01:26):
    discovery     one call per shot (GPT-6 Luna low, prompt_discovery_v0.txt): visible objects not in the shot's
                  final local entity list;
    grounding     Grounding DINO on the frames each object is listed in (GPU, box 0.30 / text 0.25);
    boxchoice     one call per shot (Luna low, prompt_boxchoice_v0.txt) picking a drawn candidate or none per frame,
                  one retry on errors;
    aug           the original WeDetect detections plus the chosen boxes (originals unchanged);
    clustering, detect (binding + prompt recovery, GPU), match.
  C evaluation (overnight arm C): V-V detection/review and scoring with code_vv/EECBench (17 items + W8, X10),
    V-L detection/review with code/EECBench  ->  results/ (C without the branch).
  Plug-in (../vl_vv_unspecified_branch_20261110, round --branch-round): U1 inventory per shot starting from the
    ledger's unspecified entities, U2 by rule, U3 per suspect; its real findings are appended to C's V-V candidates
    (issue ids and added-entity keys continue C's numbering), then one V-V review of all candidates (code_vv) and
    scoring with C's V-L review  ->  results_with/.
GPU stages take a slot of an idle GPU given as --gpu INDEX=UUID (one slot per GPU); everything else is API/CPU.
Several drivers (one per allocation) share the task list through claims/ (atomic create). Stage markers make every
video resumable. Budget gate on the standard-price estimate of all calls. Logs: events.jsonl."""
import argparse
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

EXP = Path(__file__).resolve().parent
NIGHT = EXP.parent / 'vl_vv_background_discovery_20261110'
BR = EXP.parent / 'vl_vv_unspecified_branch_20261110'
V3 = EXP.parent / 'vl_vv_full_first200_v3_20261109'
CODE = NIGHT / 'code/EECBench'
CODE_VV = NIGHT / 'code_vv/EECBench'
VACE = '/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python'
sys.path.insert(0, str(BR))
sys.path.insert(0, str(CODE / 'scripts'))
import gs_prompt_binding as gpb  # noqa: E402
import run_u_branch as ub  # noqa: E402
import run_u_branch_v1 as br2  # noqa: E402
import run_u_branch_v2 as br3  # noqa: E402  (importing it patches ub.PROMPT/EFFORT; set again below)
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

LOCK = threading.Lock()
DERIVED = {'entities', 'shot_prompt_recovery', 'global_match_v2', 'episode_entities.json', 'global_entities', 'dino'}
FONT = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 18)
DISC_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["objects"], "properties": {"objects": {
    "type": "array", "items": {"type": "object", "additionalProperties": False,
                               "required": ["name", "query", "description", "location", "frames", "in_prompt"],
                               "properties": {"name": {"type": "string"}, "query": {"type": "string"},
                                              "description": {"type": "string"}, "location": {"type": "string"},
                                              "frames": {"type": "array", "items": {"type": "integer"}},
                                              "in_prompt": {"type": "string", "enum": ["yes", "no", "unsure"]}}}}}}
BOX_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["choices"], "properties": {"choices": {
    "type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["object", "frames"],
                               "properties": {"object": {"type": "string"}, "frames": {"type": "array", "items": {
                                   "type": "object", "additionalProperties": False, "required": ["frame_id", "candidate"],
                                   "properties": {"frame_id": {"type": "integer"}, "candidate": {"type": "string"}}}}}}}}}
PRICE = (0.10, 0.01, 0.50)


def read(p):
    return json.loads(Path(p).read_text())


def write(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, indent=1, ensure_ascii=False) + '\n')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def log(**row):
    with LOCK, open(EXP / 'events.jsonl', 'a') as h:
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


def sources():
    states = {}
    for path in (V3 / 'runs').glob('*/progress.json'):
        for tid, t in read(path)['tasks'].items():
            if t.get('status') == 'success':
                states[tid] = t
    return {t: dict(case=Path(states[t]['case_dir']).resolve(), output=Path(states[t]['output_dir']).resolve())
            for t in sorted(states)}


def done(base, name):
    return (base / 'stages' / f'{name}.done').is_file()


def mark(base, name, **info):
    write(base / 'stages' / f'{name}.done', dict(time=time.strftime('%Y-%m-%dT%H:%M:%S'), **info))


def run_cmd(base, name, cmd, code, env_extra):
    env = os.environ.copy()
    env.update(OMP_NUM_THREADS='4', MKL_NUM_THREADS='4', TOKENIZERS_PARALLELISM='false', EECBENCH_REVIEW_PYTHON=VACE,
               EECBENCH_API_MODEL='gpt-6-luna', **env_extra)
    start = time.time()
    with open(base / 'logs' / f'{name}.log', 'w') as h:
        rc = subprocess.call([str(code / 'scripts/openai_api_env.sh'), *map(str, cmd)], stdout=h, stderr=subprocess.STDOUT,
                             cwd=str(code), env=env)
    return rc, round(time.time() - start, 1)


# ------------------------------------------------------------------ C frontend: discovery, grounding, box choice
def discovery(base, src, case):
    manifest = read(case / 'raw_manifest.json')
    prompt = {s['shot_id']: s['text'] for s in read(case / 'prompt.json')['shots']}

    def one(s):
        folder = base / 'discovery' / s['shot_id']
        if (folder / 'response.json').is_file():
            return
        if folder.exists():  # an interrupted call: the transport refuses an existing folder
            shutil.rmtree(folder)
        ents = read(src / f"shot_prompt_recovery/entities/shots/{s['shot_id']}/entities.json")['entities']
        images = [dict(path=f['path'], sha256=sha(f['path']), shot_id=s['shot_id'], frame_id=f['frame_id']) for f in s['frames']]
        payload = dict(shot_id=s['shot_id'], shot_text=prompt[s['shot_id']],
                       registered=[dict(id=e['entity_id'], name=e.get('name')) for e in ents],
                       frames=[i['frame_id'] for i in images])
        gpb.call(folder, payload, images, 600, prompt_path=NIGHT / 'prompt_discovery_v0.txt', schema=DISC_SCHEMA,
                 model='gpt-6-luna', reasoning='low')
    with ThreadPoolExecutor(6) as pool:
        list(pool.map(one, manifest['shots']))


def grounding_request(base, task, case):
    paths = {(s['shot_id'], f['frame_id']): f['path'] for s in read(case / 'raw_manifest.json')['shots'] for f in s['frames']}
    frames = {}
    for resp in sorted((base / 'discovery').glob('*/response.json')):
        shot = resp.parent.name
        for k, o in enumerate(read(resp)['objects'], 1):
            q = o['query'].strip().lower()
            q = q if q.endswith('.') else q + '.'
            for fr in sorted({f for f in o['frames'] if (shot, f) in paths}):
                key = (shot, fr)
                if key not in frames:
                    p = paths[key]
                    frames[key] = dict(frame_id=fr, path=p, sha256=sha(p), shot_id=f'{task}__{shot}', targets=[])
                frames[key]['targets'].append(dict(prompt_entity_id=f'{shot}:b{k}', query=q))
    req = dict(frames=list(frames.values()))
    write(base / 'grounding_request.json', req)
    return len(req['frames'])


def color(i):
    import colorsys
    r, g, b = colorsys.hsv_to_rgb((i * 0.27) % 1, 0.9, 1)
    return (int(r * 255), int(g * 255), int(b * 255))


def boxchoice(base, task):
    req = read(base / 'grounding_request.json')
    shots = {}
    for fr in req['frames']:
        shot = fr['shot_id'].rsplit('__', 1)[1]
        res = read(base / 'grounding' / fr['shot_id'] / f"frame_{fr['frame_id']:06d}.json")
        s = shots.setdefault(shot, dict(shot=shot, frames={}, paths={}))
        s['paths'][fr['frame_id']] = fr['path']
        for t in fr['targets']:
            obj = t['prompt_entity_id'].split(':')[1]
            cands = sorted([d for d in res['detections'] if d['prompt_entity_id'] == t['prompt_entity_id'] and d['valid_box']],
                           key=lambda d: -d['score'])
            if cands:
                s['frames'].setdefault(fr['frame_id'], {})[obj] = [dict(label=f'{obj}-{n}', box=d['box_xyxy'], score=d['score'],
                                                                         gd_id=d['candidate_id'], query=d['query'])
                                                                    for n, d in enumerate(cands, 1)]
    jobs = []
    for shot, s in sorted(shots.items()):
        if not s['frames']:
            continue
        resp = read(base / 'discovery' / shot / 'response.json')['objects']
        objs = {}
        for k, o in enumerate(resp, 1):
            fr = {fid: c[f'b{k}'] for fid, c in s['frames'].items() if f'b{k}' in c}
            if fr:
                objs[f'b{k}'] = dict(id=f'b{k}', name=o['name'], description=o['description'], location=o['location'], frames=fr)
        if objs:
            jobs.append(dict(shot=shot, objects=objs, paths=s['paths']))

    def check(job, result):
        errs, seen = [], set()
        for ch in result['choices']:
            o = job['objects'].get(ch['object'])
            if o is None:
                errs.append(f"unknown object {ch['object']}")
                continue
            if ch['object'] in seen:
                errs.append(f"object {ch['object']} listed twice")
                continue
            seen.add(ch['object'])
            fids = set()
            for f in ch['frames']:
                if f['frame_id'] not in o['frames']:
                    errs.append(f"{ch['object']}: frame {f['frame_id']} has no candidates for it")
                    continue
                if f['frame_id'] in fids:
                    errs.append(f"{ch['object']}: frame {f['frame_id']} listed twice")
                fids.add(f['frame_id'])
                if f['candidate'] != 'none' and f['candidate'] not in {c['label'] for c in o['frames'][f['frame_id']]}:
                    errs.append(f"{ch['object']} frame {f['frame_id']}: {f['candidate']} is not one of its candidates there")
            for fid in set(o['frames']) - fids:
                errs.append(f"{ch['object']}: frame {fid} missing")
        for oid in set(job['objects']) - seen:
            errs.append(f'object {oid} missing')
        return errs

    def one(job):
        out = base / 'boxchoice' / job['shot']
        if (out / 'choice.json').is_file():
            return
        if out.exists():  # an interrupted call
            shutil.rmtree(out)
        d = out / 'images'
        d.mkdir(parents=True, exist_ok=True)
        images, order = [], sorted({fid for o in job['objects'].values() for fid in o['frames']})
        oidx = {oid: i for i, oid in enumerate(sorted(job['objects']))}
        for fid in order:
            im = Image.open(job['paths'][fid]).convert('RGB')
            dr = ImageDraw.Draw(im)
            for oid, o in job['objects'].items():
                for c in o['frames'].get(fid, []):
                    col = color(oidx[oid])
                    x0, y0, x1, y1 = c['box']
                    dr.rectangle([x0, y0, x1, y1], outline=col, width=3)
                    tx, ty = x0 + 2, max(y0 - 22, 0) if y0 >= 22 else y0 + 2
                    dr.rectangle([tx, ty, tx + 13 * len(c['label']) + 6, ty + 21], fill=col)
                    dr.text((tx + 3, ty + 1), c['label'], fill='black', font=FONT)
            p = d / f'frame_{fid:06d}.jpg'
            im.save(p, quality=92)
            images.append(dict(path=str(p), sha256=sha(p), shot_id=job['shot'], frame_id=fid))
        payload = dict(shot_id=job['shot'], objects=[dict(id=o['id'], name=o['name'], description=o['description'],
                                                         location=o['location'],
                                                         candidates={str(fid): [c['label'] for c in cs] for fid, cs in sorted(o['frames'].items())})
                                                    for o in job['objects'].values()])
        res = gpb.call(out / 'call', payload, images, 600, prompt_path=NIGHT / 'prompt_boxchoice_v0.txt', schema=BOX_SCHEMA,
                       model='gpt-6-luna', reasoning='low')
        errs, tries = check(job, res), 1
        if errs:
            payload['previous_answer_problems'] = errs
            res = gpb.call(out / 'call_retry', payload, images, 600, prompt_path=NIGHT / 'prompt_boxchoice_v0.txt',
                           schema=BOX_SCHEMA, model='gpt-6-luna', reasoning='low')
            errs, tries = check(job, res), 2
        chosen = []
        for ch in res['choices']:
            o = job['objects'].get(ch['object'])
            for f in ch['frames']:
                if o and f['candidate'] != 'none':
                    c = next((c for c in o['frames'].get(f['frame_id'], []) if c['label'] == f['candidate']), None)
                    if c:
                        chosen.append(dict(object=ch['object'], name=o['name'], frame_id=f['frame_id'], **c))
        write(out / 'choice.json', dict(task=base.name, shot=job['shot'], tries=tries, remaining_errors=errs,
                                        choices=res['choices'], chosen=chosen))
    with ThreadPoolExecutor(6) as pool:
        list(pool.map(one, jobs))


def augment(base, src):
    dst = base / 'aug_detections'
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src / 'entities/detections', dst)
    run = read(dst / 'run.json')
    added = 0
    for ch in sorted((base / 'boxchoice').glob('*/choice.json')):
        c = read(ch)
        for x in c['chosen']:
            f = dst / c['shot'] / f"frame_{x['frame_id']:06d}" / 'detections.json'
            data = read(f)
            nid = max([d['id'] for d in data['detections']] + [0]) + 1
            data['detections'].append(dict(id=nid, label=x['name'], class_id=-1, box_xyxy=x['box'], score=x['score'],
                                           source='grounding_dino_background_discovery',
                                           discovery_object=f"{c['shot']}:{x['object']}", query=x['query'], gd_candidate_id=x['gd_id']))
            write(f, data)
            for r in run['results']:
                if r['shot'] == c['shot'] and r['frame_id'] == x['frame_id']:
                    r['count'] = len(data['detections'])
            added += 1
    run['augmentation'] = dict(note='chosen Grounding DINO boxes of discovered background objects appended (pipeline C)', added=added)
    write(dst / 'run.json', run)
    return added


# ------------------------------------------------------------------ plug-in: unspecified branch on C's case
def branch(base, case, round_name):
    if round_name == 'r3':
        ub.PROMPT['u1'], ub.EFFORT['u1'] = BR / 'prompts/u1_inventory_v1.txt', 'medium'
        mod = br3
    else:
        ub.PROMPT['u1'], ub.EFFORT['u1'] = BR / 'prompts/u1_inventory_v0.txt', 'low'
        mod = br2
    out = base / 'branch'
    ctx = ub.context(case)
    shots = ub.common.shot_ids(ctx[2])
    todo = [s for s in shots if not (out / 'u1' / s / 'inventory.json').is_file()]
    with ThreadPoolExecutor(6) as pool:
        list(pool.map(lambda s: ub.u1(out, ctx, s), todo))
    inventories = {s: read(out / 'u1' / s / 'inventory.json') for s in shots}
    suspects, raw = mod.u2_rule(ctx, inventories)
    write(out / 'u2' / 'suspects.json', dict(before_cap=raw, count=len(suspects)))
    with ThreadPoolExecutor(6) as pool:
        verified = list(pool.map(lambda a: mod.u3(out, ctx, a[0], a[1]), enumerate(suspects, 1)))
    return ctx, inventories, verified


def merge(base, ctx, inventories, verified):
    """C's V-V candidates plus the branch's real findings; issue ids and added-entity keys continue C's numbering."""
    c_det = base / 'results/vv_detection/result.json'
    tmp, n = ub.build_detection(base / 'branch', ctx, c_det, inventories, verified)
    branch_det = read(tmp)
    main = read(c_det)
    vmax = max([int(i['issue_id'][1:].split('.')[0]) for i in main['issues'] if i['issue_id'][1:].split('.')[0].isdigit()] + [0])
    nmain = max([int(e['entity_key'][1:]) for e in main['entities'] if str(e['entity_key']).startswith('n')
                 and str(e['entity_key'])[1:].isdigit()] + [0])
    main_keys = {e['entity_key'] for e in main['entities']}
    # build_detection copied C's entity records first, then appended ledger records and the branch's new objects.
    assert branch_det['entities'][:len(main['entities'])] == main['entities']
    rename, extra = {}, []
    for e in branch_det['entities'][len(main['entities']):]:
        if e['source'] == 'added_by_vv_detection':
            nmain += 1
            rename[e['entity_key']] = f'n{nmain}'
            extra.append(dict(e, entity_key=f'n{nmain}'))
        elif e['entity_key'] not in main_keys:
            extra.append(e)
    issues = []
    for k, i in enumerate(branch_det['issues'], 1):
        i = json.loads(json.dumps(i))
        i['issue_id'] = f'V{vmax + k}'
        for r in i['entity_refs']:
            r['entity_key'] = rename.get(r['entity_key'], r['entity_key'])
        for ev in i['key_evidence']:
            ev['entity_keys'] = [rename.get(x, x) for x in ev['entity_keys']]
        issues.append(i)
    merged = dict(main, issues=main['issues'] + issues, entities=main['entities'] + extra,
                  u_branch=dict(note='C V-V candidates plus the unspecified branch findings (plug-in)', branch_issue_ids=[i['issue_id'] for i in issues],
                                suspects=len(verified), real=n))
    write(base / 'results_with/vv_detection/result.json', merged)
    return len(issues)


# ------------------------------------------------------------------ per video
def video(task, src, gpus, a):
    base = EXP / 'runs' / task
    case, out, out_w = base / 'case', base / 'results', base / 'results_with'
    (base / 'logs').mkdir(parents=True, exist_ok=True)
    if not done(base, 'prepare'):
        if case.exists():
            shutil.rmtree(case)
        shutil.copytree(src['case'], case, ignore=lambda d, names: [x for x in names if Path(d) == src['case'] and x in DERIVED])
        st = read(case / 'run.json')
        st.update(status='prepared', experiment='vl_vv_full_first200_c_20261110', copied_from=str(src['case']))
        for k in ('detected_at', 'matched_at', 'matching_protocol', 'detector_device', 'binding_protocol'):
            st.pop(k, None)
        write(case / 'run.json', st)
        mark(base, 'prepare')
    if not done(base, 'discovery'):
        discovery(base, src['case'], case)
        mark(base, 'discovery')
    if not done(base, 'grounding'):
        n = grounding_request(base, task, case)
        if n:
            if (base / 'grounding').exists():  # an interrupted run: the script refuses an existing output folder
                shutil.rmtree(base / 'grounding')
            gpu = gpus.get()
            try:
                rc, sec = run_cmd(base, 'grounding', [VACE, CODE / 'scripts/gs_grounding_recovery.py', '--request',
                                                      base / 'grounding_request.json', '--output', base / 'grounding',
                                                      '--device', 'cuda'], CODE, dict(ROCR_VISIBLE_DEVICES=gpu[1]))  # the script requires the GPU UUID here
            finally:
                gpus.put(gpu)
            if rc:
                return 'failed at grounding'
        mark(base, 'grounding', frames=n)
    if not done(base, 'boxchoice'):
        boxchoice(base, task)
        mark(base, 'boxchoice')
    if not done(base, 'aug'):
        mark(base, 'aug', added=augment(base, src['case']))
    S, SV = CODE / 'scripts', CODE_VV / 'scripts'
    cpu = dict(ROCR_VISIBLE_DEVICES='-1', CUDA_VISIBLE_DEVICES='')
    stages = [
        ('clustering', CODE, [VACE, S / 'run_wedetect_shot_entities.py', '--manifest', case / 'raw_manifest.json', '--output',
                              case / 'entities', '--device', 'cpu', '--model', 'gpt-6-luna', '--reasoning', 'low',
                              '--shot-workers', '3', '--detections', base / 'aug_detections'], cpu),
        ('detect', CODE, None, None),
        ('match', CODE, [VACE, S / 'run_vl_vv_detection.py', 'match', '--case', case], cpu),
        ('vv_detection', CODE_VV, [VACE, SV / 'run_vl_vv_branch_detection.py', '--branch', 'vv', '--case', case, '--output',
                                   out / 'vv_detection', '--chain', 'v6'], cpu),
        ('vv_review', CODE_VV, [VACE, SV / 'run_vl_vv_branch_review.py', '--branch', 'vv', '--case', case, '--detection',
                                out / 'vv_detection/result.json', '--output', out / 'vv_review', '--chain', 'v6'], cpu),
        ('vl_detection', CODE, [VACE, S / 'run_vl_vv_branch_detection.py', '--branch', 'vl', '--case', case, '--output',
                                out / 'vl_detection', '--chain', 'v6'], cpu),
        ('vl_review', CODE, [VACE, S / 'run_vl_vv_branch_review.py', '--branch', 'vl', '--case', case, '--detection',
                             out / 'vl_detection/result.json', '--output', out / 'vl_review', '--chain', 'v6'], cpu),
        ('episode_scoring', CODE_VV, [VACE, SV / 'run_vl_vv_branch_scoring.py', '--vl-review', out / 'vl_review/result.json',
                                      '--vv-review', out / 'vv_review/result.json', '--output', out / 'episode_scoring',
                                      '--chain', 'v6'], cpu)]
    out.mkdir(exist_ok=True)
    for name, code, cmd, env in stages:
        if done(base, name):
            continue
        for p in ([out / name] if name in ('vv_detection', 'vv_review', 'vl_detection', 'vl_review', 'episode_scoring')
                  else [case / 'entities'] if name == 'clustering' else []):  # interrupted output: the scripts refuse it
            if p.exists():
                shutil.rmtree(p)
        if name == 'detect':
            gpu = gpus.get()
            try:
                rc, sec = run_cmd(base, name, [VACE, S / 'run_vl_vv_detection.py', 'detect', '--case', case, '--device', 'cuda',
                                               '--gpu', gpu[0], '--gpu-uuid', gpu[1], '--shot-workers', '3'], code, {})
            finally:
                gpus.put(gpu)
        else:
            rc, sec = run_cmd(base, name, cmd, code, env)
        log(event=name, task=task, exit_code=rc, seconds=sec)
        if rc:
            return f'failed at {name}'
        mark(base, name, seconds=sec)
    if a.branch_round == 'off':
        return 'success (no branch)'
    if not done(base, 'branch'):
        for p in (base / 'branch', out_w):
            if p.exists():  # an interrupted plug-in run starts again
                shutil.rmtree(p)
        ctx, inventories, verified = branch(base, case, a.branch_round)
        added = merge(base, ctx, inventories, verified)
        mark(base, 'branch', added=added, suspects=len(verified))
    for name, cmd in [('with_vv_review', [VACE, SV / 'run_vl_vv_branch_review.py', '--branch', 'vv', '--case', case, '--detection',
                                          out_w / 'vv_detection/result.json', '--output', out_w / 'vv_review', '--chain', 'v6']),
                      ('with_episode_scoring', [VACE, SV / 'run_vl_vv_branch_scoring.py', '--vl-review', out / 'vl_review/result.json',
                                                '--vv-review', out_w / 'vv_review/result.json', '--output', out_w / 'episode_scoring',
                                                '--chain', 'v6'])]:
        if done(base, name):
            continue
        target = out_w / name.replace('with_', '')
        if target.exists():
            shutil.rmtree(target)
        rc, sec = run_cmd(base, name, cmd, CODE_VV, cpu)
        log(event=name, task=task, exit_code=rc, seconds=sec)
        if rc:
            return f'failed at {name}'
        mark(base, name, seconds=sec)
    return 'success'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gpu', action='append', default=[], metavar='INDEX=UUID')
    p.add_argument('--only', nargs='*')
    p.add_argument('--limit', type=int, default=0)
    p.add_argument('--threads', type=int, default=8)
    p.add_argument('--cap', type=float, default=110.0)
    p.add_argument('--branch-round', choices=['r2', 'r3', 'off'], default='r3')
    a = p.parse_args()
    if not os.environ.get('SLURM_JOB_ID'):
        raise RuntimeError('Run inside an owned Slurm allocation')
    gpus = queue.Queue()
    for g in a.gpu:
        gpus.put(tuple(g.split('=', 1)))
    if gpus.empty():
        raise SystemExit('--gpu INDEX=UUID required')
    src = sources()
    tasks = [t for t in src if not a.only or t in a.only]
    if a.limit:
        tasks = tasks[:a.limit]
    (EXP / 'claims').mkdir(exist_ok=True)
    log(event='driver_started', tasks=len(tasks), gpus=a.gpu, host=os.uname().nodename, slurm=os.environ['SLURM_JOB_ID'],
        branch_round=a.branch_round, cap=a.cap)
    reserved = {}

    def job(t):
        claim = EXP / 'claims' / t
        try:
            fd = os.open(claim, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f'{os.uname().nodename} {os.getpid()}'.encode())
            os.close(fd)
        except FileExistsError:
            if not (EXP / 'runs' / t / 'stages').exists() or (EXP / 'runs' / t / 'stages' / 'with_episode_scoring.done').is_file():
                return t, 'claimed elsewhere or done'
            if (EXP / 'claims' / t).read_text().split()[0] != os.uname().nodename:
                return t, 'claimed elsewhere'
        with LOCK:
            if spent(EXP / 'runs') + sum(reserved.values()) + 0.25 > a.cap:
                return t, 'not started: budget gate'
            reserved[t] = 0.25
        try:
            log(event='start', task=t)
            try:
                r = video(t, src[t], gpus, a)
            except Exception as exc:  # noqa: BLE001 - record and continue
                r = f'failed: {type(exc).__name__}: {exc}'[:400]
            log(event='result', task=t, result=r)
            return t, r
        finally:
            with LOCK:
                reserved.pop(t, None)
    with ThreadPoolExecutor(a.threads) as pool:
        for t, r in pool.map(job, tasks):
            print(t, r, flush=True)
    log(event='driver_finished', spent_usd=round(spent(EXP / 'runs'), 4))


if __name__ == '__main__':
    main()
