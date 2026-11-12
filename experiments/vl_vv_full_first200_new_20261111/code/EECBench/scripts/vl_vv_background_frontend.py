#!/usr/bin/env python3
"""Background-object frontend of pipeline C (owner, 2026-11-10: "新流程把C设为默认"; default of the VL/VV pipeline).

Runs on a case after the first detection pass (shot clustering + prompt binding/recovery) and before the second:
  discover   one call per shot (GPT-6 Luna low, prompts/vl_vv_background_discovery_v0.txt): visible objects that are
             not in the shot's local entity list of the first pass;
  ground     Grounding DINO (scripts/gs_grounding_recovery.py, box 0.30 / text 0.25) on the frames each object is
             listed in; GPU pinned by UUID (cuda) or CPU with hidden GPUs;
  choose     one call per shot (Luna low, prompts/vl_vv_background_boxchoice_v0.txt) picking a drawn candidate box or
             none per frame; one retry with the problems listed;
  augment    the first pass's original WeDetect detections plus the chosen boxes (originals unchanged) in
             background_frontend/aug_detections; the first pass's entities/ and shot_prompt_recovery/ move to
             background_frontend/pass1/. The second pass then clusters these detections:
             run_vl_vv_detection.py detect --detections <case>/background_frontend/aug_detections.
A port of the validated full first-200 C run (experiments/vl_vv_full_first200_c_20261110/run_full_c.py, EECBench
commit 6f530ee): same prompts (byte copies), schemas, payloads, model settings and box rules.
Outputs in <case>/background_frontend/; state in its run.json."""
import argparse
import colorsys
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import gs_prompt_binding as gpb  # noqa: E402
import gpu_lock  # noqa: E402

MODEL, REASONING = 'gpt-6-luna', 'low'
DISCOVERY_PROMPT = ROOT / 'prompts/vl_vv_background_discovery_v0.txt'
BOXCHOICE_PROMPT = ROOT / 'prompts/vl_vv_background_boxchoice_v0.txt'
GROUNDING = ROOT / 'scripts/gs_grounding_recovery.py'
FONT_PATH = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
PASS1 = ('entities', 'shot_prompt_recovery')
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


def read(p):
    return json.loads(Path(p).read_text())


def write(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, indent=1, ensure_ascii=False) + '\n')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def base_of(case):
    return Path(case) / 'background_frontend'


def record(case, step, **info):
    path = base_of(case) / 'run.json'
    state = read(path) if path.is_file() else dict(protocol='vl_vv_background_frontend_v1', model=MODEL, reasoning=REASONING,
                                                   prompts={str(p.relative_to(ROOT)): sha(p) for p in (DISCOVERY_PROMPT, BOXCHOICE_PROMPT)},
                                                   steps={})
    state['steps'][step] = dict(info, finished_at=time.time())
    write(path, state)


def done(case, step):
    path = base_of(case) / 'run.json'
    return path.is_file() and step in read(path).get('steps', {})


# ---------------------------------------------------------------- discover
def discover(case, workers=6):
    case = Path(case)
    base = base_of(case)
    manifest = read(case / 'raw_manifest.json')
    prompt = {s['shot_id']: s['text'] for s in read(case / 'prompt.json')['shots']}
    first_pass = case / 'shot_prompt_recovery' / 'entities' / 'shots'
    if not first_pass.is_dir():
        raise ValueError('discover needs the first detection pass (shot_prompt_recovery/entities)')

    def one(s):
        folder = base / 'discovery' / s['shot_id']
        if (folder / 'response.json').is_file():
            return
        if folder.exists():  # an interrupted call: the transport refuses an existing folder
            shutil.rmtree(folder)
        ents = read(first_pass / s['shot_id'] / 'entities.json')['entities']
        images = [dict(path=f['path'], sha256=sha(f['path']), shot_id=s['shot_id'], frame_id=f['frame_id']) for f in s['frames']]
        payload = dict(shot_id=s['shot_id'], shot_text=prompt[s['shot_id']],
                       registered=[dict(id=e['entity_id'], name=e.get('name')) for e in ents],
                       frames=[i['frame_id'] for i in images])
        gpb.call(folder, payload, images, 600, prompt_path=DISCOVERY_PROMPT, schema=DISC_SCHEMA, model=MODEL, reasoning=REASONING)
    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(one, manifest['shots']))
    objects = sum(len(read(p)['objects']) for p in (base / 'discovery').glob('*/response.json'))
    record(case, 'discover', objects=objects)
    return objects


# ---------------------------------------------------------------- ground
def grounding_request(case):
    case = Path(case)
    base = base_of(case)
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
                    frames[key] = dict(frame_id=fr, path=p, sha256=sha(p), shot_id=f'{case.name}__{shot}', targets=[])
                frames[key]['targets'].append(dict(prompt_entity_id=f'{shot}:b{k}', query=q))
    req = dict(frames=list(frames.values()))
    write(base / 'grounding_request.json', req)
    return len(req['frames'])


def ground(case, device='cuda', gpu_uuid=None, python=sys.executable):
    case = Path(case)
    base = base_of(case)
    n = grounding_request(case)
    out = base / 'grounding'
    state = read(out / 'run.json') if (out / 'run.json').is_file() else {}
    if n and state.get('status') != 'success':
        if out.exists():  # an interrupted run: the detector refuses an existing output folder
            shutil.rmtree(out)
        env = os.environ.copy()
        if device == 'cuda':
            if not gpu_uuid or not str(gpu_uuid).startswith('GPU-'):
                raise ValueError('Grounding DINO on cuda needs the checked GPU UUID (GPU-...)')
            env.update(ROCR_VISIBLE_DEVICES=gpu_uuid)
        else:
            env.update(ROCR_VISIBLE_DEVICES='-1', CUDA_VISIBLE_DEVICES='')
        lock = gpu_lock.prefix(gpu_uuid) if device == 'cuda' else []  # optional per-GPU lock (EECBENCH_GPU_LOCK_DIR)
        subprocess.run(lock + [python, str(GROUNDING), '--request', str(base / 'grounding_request.json'), '--output',
                               str(out), '--device', device], check=True, env=env, cwd=str(ROOT))
    record(case, 'ground', frames=n, device=device)
    return n


# ---------------------------------------------------------------- choose
def color(i):
    r, g, b = colorsys.hsv_to_rgb((i * 0.27) % 1, 0.9, 1)
    return (int(r * 255), int(g * 255), int(b * 255))


def choice_jobs(case):
    base = base_of(case)
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
    return jobs


def choice_errors(job, result):
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


def choose(case, workers=6):
    from PIL import Image, ImageDraw, ImageFont
    case = Path(case)
    base = base_of(case)
    font = ImageFont.truetype(FONT_PATH, 18)
    jobs = choice_jobs(case) if (base / 'grounding_request.json').is_file() and read(base / 'grounding_request.json')['frames'] else []

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
                    dr.text((tx + 3, ty + 1), c['label'], fill='black', font=font)
            p = d / f'frame_{fid:06d}.jpg'
            im.save(p, quality=92)
            images.append(dict(path=str(p), sha256=sha(p), shot_id=job['shot'], frame_id=fid))
        payload = dict(shot_id=job['shot'], objects=[dict(id=o['id'], name=o['name'], description=o['description'],
                                                         location=o['location'],
                                                         candidates={str(fid): [c['label'] for c in cs] for fid, cs in sorted(o['frames'].items())})
                                                    for o in job['objects'].values()])
        res = gpb.call(out / 'call', payload, images, 600, prompt_path=BOXCHOICE_PROMPT, schema=BOX_SCHEMA, model=MODEL,
                       reasoning=REASONING)
        errs, tries = choice_errors(job, res), 1
        if errs:
            payload['previous_answer_problems'] = errs
            res = gpb.call(out / 'call_retry', payload, images, 600, prompt_path=BOXCHOICE_PROMPT, schema=BOX_SCHEMA,
                           model=MODEL, reasoning=REASONING)
            errs, tries = choice_errors(job, res), 2
        chosen = []
        for ch in res['choices']:
            o = job['objects'].get(ch['object'])
            for f in ch['frames']:
                if o and f['candidate'] != 'none':
                    c = next((c for c in o['frames'].get(f['frame_id'], []) if c['label'] == f['candidate']), None)
                    if c:
                        chosen.append(dict(object=ch['object'], name=o['name'], frame_id=f['frame_id'], **c))
        write(out / 'choice.json', dict(case=case.name, shot=job['shot'], tries=tries, remaining_errors=errs,
                                        choices=res['choices'], chosen=chosen))
    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(one, jobs))
    chosen = sum(len(read(p)['chosen']) for p in (base / 'boxchoice').glob('*/choice.json'))
    record(case, 'choose', shots=len(jobs), chosen=chosen)
    return chosen


# ---------------------------------------------------------------- augment
def augment(case):
    """Original detections plus the chosen boxes; then move the first pass aside for the second detection pass."""
    case = Path(case)
    base = base_of(case)
    # The first pass's original WeDetect detections: its own run, or the reused run it clustered (--reuse-detections).
    state = case / 'entities' / 'run.json'
    recorded = read(state).get('detections') if state.is_file() else None
    src = Path(recorded) if recorded and Path(recorded).is_dir() else case / 'entities' / 'detections'
    if not src.is_dir():
        if (base / 'pass1' / 'entities' / 'detections').is_dir() and (base / 'aug_detections' / 'run.json').is_file():
            return read(base / 'aug_detections' / 'run.json')['augmentation']['added']  # already done
        raise ValueError('augment needs the first pass detections (entities/detections)')
    dst = base / 'aug_detections'
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
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
    (base / 'pass1').mkdir(exist_ok=True)
    for name in PASS1:
        if (case / name).exists():
            shutil.move(str(case / name), str(base / 'pass1' / name))
    record(case, 'augment', added=added, moved=list(PASS1))
    return added


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)
    for name in ('discover', 'ground', 'choose', 'augment'):
        s = sub.add_parser(name)
        s.add_argument('--case', type=Path, required=True)
        if name == 'ground':
            s.add_argument('--device', choices=('cuda', 'cpu'), default='cuda')
            s.add_argument('--gpu-uuid')
    a = p.parse_args()
    case = a.case.resolve()
    if a.cmd == 'discover':
        print(json.dumps(dict(objects=discover(case))))
    elif a.cmd == 'ground':
        print(json.dumps(dict(frames=ground(case, a.device, a.gpu_uuid))))
    elif a.cmd == 'choose':
        print(json.dumps(dict(chosen=choose(case))))
    else:
        print(json.dumps(dict(added=augment(case))))


if __name__ == '__main__':
    main()
