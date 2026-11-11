#!/usr/bin/env python3
"""Background-object discovery test, step 2a: box choice (owner, 2026-11-10: "加一个选框步骤").
Per shot with discovered objects that have Grounding DINO candidates: the keyframes with all candidates drawn and
labelled <object>-<n> (sorted by detector score), one isolated call (GPT-6 Luna, low; prompt_boxchoice_v0.txt) that picks
per object and keyframe one candidate or "none". Choices are checked (object/frame coverage, candidate belongs to that
object and frame); one retry with the errors if the check fails. Output boxchoice/<task>/<shot>/{call/, choice.json}
with the chosen original Grounding DINO boxes (coordinates unchanged)."""
import json, sys, hashlib, colorsys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
HERE = Path(__file__).resolve().parent
B = HERE.parents[1]
sys.path.insert(0, str(B / 'scripts'))
import gs_prompt_binding as gpb
FONT = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 18)
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["choices"], "properties": {"choices": {"type": "array", "items": {
    "type": "object", "additionalProperties": False, "required": ["object", "frames"], "properties": {"object": {"type": "string"}, "frames": {
        "type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["frame_id", "candidate"],
                                   "properties": {"frame_id": {"type": "integer"}, "candidate": {"type": "string"}}}}}}}}}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def color(i):
    r, g, b = colorsys.hsv_to_rgb((i * 0.27) % 1, 0.9, 1)
    return (int(r * 255), int(g * 255), int(b * 255))


def jobs():
    req = json.loads((HERE / 'grounding_request.json').read_text())
    shots = {}
    for fr in req['frames']:
        task, shot = fr['shot_id'].rsplit('__', 1)
        res = json.loads((HERE / 'grounding' / fr['shot_id'] / f"frame_{fr['frame_id']:06d}.json").read_text())
        s = shots.setdefault((task, shot), dict(task=task, shot=shot, frames={}, paths={}))
        s['paths'][fr['frame_id']] = fr['path']
        for t in fr['targets']:
            obj = t['prompt_entity_id'].split(':')[1]
            cands = sorted([d for d in res['detections'] if d['prompt_entity_id'] == t['prompt_entity_id'] and d['valid_box']], key=lambda d: -d['score'])
            if cands:
                s['frames'].setdefault(fr['frame_id'], {})[obj] = [dict(label=f'{obj}-{n}', box=d['box_xyxy'], score=d['score'], gd_id=d['candidate_id'], query=d['query'])
                                                                   for n, d in enumerate(cands, 1)]
    out = []
    for (task, shot), s in sorted(shots.items()):
        if not s['frames']: continue
        resp = json.loads((HERE / 'runs' / task / shot / 'response.json').read_text())['objects']
        objs = {}
        for k, o in enumerate(resp, 1):
            frames = {fid: c[f'b{k}'] for fid, c in s['frames'].items() if f'b{k}' in c}
            if frames:
                objs[f'b{k}'] = dict(id=f'b{k}', name=o['name'], description=o['description'], location=o['location'], frames=frames)
        if objs: out.append(dict(task=task, shot=shot, objects=objs, paths=s['paths']))
    return out


def draw(job):
    d = HERE / 'boxchoice' / job['task'] / job['shot'] / 'images'; d.mkdir(parents=True, exist_ok=True)
    images, order = [], sorted({fid for o in job['objects'].values() for fid in o['frames']})
    oidx = {oid: i for i, oid in enumerate(sorted(job['objects']))}
    for fid in order:
        im = Image.open(job['paths'][fid]).convert('RGB'); dr = ImageDraw.Draw(im)
        for oid, o in job['objects'].items():
            for c in o['frames'].get(fid, []):
                col = color(oidx[oid]); x0, y0, x1, y1 = c['box']
                dr.rectangle([x0, y0, x1, y1], outline=col, width=3)
                tx, ty = x0 + 2, max(y0 - 22, 0) if y0 >= 22 else y0 + 2
                dr.rectangle([tx, ty, tx + 13 * len(c['label']) + 6, ty + 21], fill=col); dr.text((tx + 3, ty + 1), c['label'], fill='black', font=FONT)
        p = d / f'frame_{fid:06d}.jpg'; im.save(p, quality=92)
        images.append(dict(path=str(p), sha256=sha(p), shot_id=job['shot'], frame_id=fid))
    return images


def check(job, result):
    errs, seen = [], set()
    for ch in result['choices']:
        o = job['objects'].get(ch['object'])
        if o is None: errs.append(f"unknown object {ch['object']}"); continue
        if ch['object'] in seen: errs.append(f"object {ch['object']} listed twice"); continue
        seen.add(ch['object']); fids = set()
        for f in ch['frames']:
            if f['frame_id'] not in o['frames']: errs.append(f"{ch['object']}: frame {f['frame_id']} has no candidates for it"); continue
            if f['frame_id'] in fids: errs.append(f"{ch['object']}: frame {f['frame_id']} listed twice")
            fids.add(f['frame_id'])
            if f['candidate'] != 'none' and f['candidate'] not in {c['label'] for c in o['frames'][f['frame_id']]}:
                errs.append(f"{ch['object']} frame {f['frame_id']}: {f['candidate']} is not one of its candidates there")
        for fid in set(o['frames']) - fids: errs.append(f"{ch['object']}: frame {fid} missing")
    for oid in set(job['objects']) - seen: errs.append(f'object {oid} missing')
    return errs


def one(job):
    out = HERE / 'boxchoice' / job['task'] / job['shot']
    if (out / 'choice.json').exists(): return job['task'], job['shot'], 'skipped'
    images = draw(job)
    payload = dict(shot_id=job['shot'], objects=[dict(id=o['id'], name=o['name'], description=o['description'], location=o['location'],
                                                      candidates={str(fid): [c['label'] for c in cs] for fid, cs in sorted(o['frames'].items())})
                                                 for o in job['objects'].values()])
    try:
        res = gpb.call(out / 'call', payload, images, 600, prompt_path=HERE / 'prompt_boxchoice_v0.txt', schema=SCHEMA, model='gpt-6-luna', reasoning='low')
        errs = check(job, res); tries = 1
        if errs:
            payload['previous_answer_problems'] = errs
            res = gpb.call(out / 'call_retry', payload, images, 600, prompt_path=HERE / 'prompt_boxchoice_v0.txt', schema=SCHEMA, model='gpt-6-luna', reasoning='low')
            errs = check(job, res); tries = 2
        chosen = []
        for ch in res['choices']:
            o = job['objects'].get(ch['object'])
            for f in ch['frames']:
                if o and f['candidate'] != 'none':
                    c = next((c for c in o['frames'].get(f['frame_id'], []) if c['label'] == f['candidate']), None)
                    if c: chosen.append(dict(object=ch['object'], name=o['name'], frame_id=f['frame_id'], **c))
        (out / 'choice.json').write_text(json.dumps(dict(task=job['task'], shot=job['shot'], tries=tries, remaining_errors=errs,
                                                         choices=res['choices'], chosen=chosen), indent=1, ensure_ascii=False) + '\n')
        return job['task'], job['shot'], f'ok tries={tries} errors={len(errs)} chosen={len(chosen)}'
    except Exception as e:
        return job['task'], job['shot'], 'failed ' + repr(e)[:160]


if __name__ == '__main__':
    js = jobs(); print('shots', len(js), 'objects', sum(len(j['objects']) for j in js), flush=True)
    only = sys.argv[1:]
    if only: js = [j for j in js if f"{j['task']}:{j['shot']}" in only]
    with ThreadPoolExecutor(8) as pool:
        for r in pool.map(one, js): print(*r, flush=True)
