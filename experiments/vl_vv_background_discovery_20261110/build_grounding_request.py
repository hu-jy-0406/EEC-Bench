#!/usr/bin/env python3
"""Grounding DINO request for the discovered objects: for every object, its query on each keyframe it is listed in.
shot_id is '<task>__<shot>' so one request covers all 20 videos. Target id = '<shot>:b<k>' (k = position in that
shot's discovery output). Writes grounding_request.json."""
import json, hashlib
from pathlib import Path
HERE = Path(__file__).resolve().parent
V3 = HERE.parent / 'vl_vv_full_first200_v3_20261109'
states = {}
for path in (V3 / 'runs').glob('*/progress.json'):
    for tid, t in json.loads(path.read_text())['tasks'].items():
        if t.get('status') == 'success': states[tid] = t
frames = {}
for resp in sorted(HERE.glob('runs/*/*/response.json')):
    task, shot = resp.parent.parent.name, resp.parent.name
    case = Path(states[task]['case_dir'])
    paths = {(s['shot_id'], f['frame_id']): f['path'] for s in json.loads((case / 'raw_manifest.json').read_text())['shots'] for f in s['frames']}
    for k, o in enumerate(json.loads(resp.read_text())['objects'], 1):
        q = o['query'].strip().lower()
        q = q if q.endswith('.') else q + '.'
        for fr in sorted({f for f in o['frames'] if (shot, f) in paths}):
            key = (task, shot, fr)
            if key not in frames:
                p = paths[(shot, fr)]
                frames[key] = dict(frame_id=fr, path=p, sha256=hashlib.sha256(Path(p).read_bytes()).hexdigest(), shot_id=f'{task}__{shot}', targets=[])
            frames[key]['targets'].append(dict(prompt_entity_id=f'{shot}:b{k}', query=q))
req = dict(frames=list(frames.values()))
(HERE / 'grounding_request.json').write_text(json.dumps(req, indent=1, ensure_ascii=False) + '\n')
print('frames', len(req['frames']), 'frame-query pairs', sum(len(f['targets']) for f in req['frames']))
