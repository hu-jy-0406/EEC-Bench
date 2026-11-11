#!/usr/bin/env python3
"""Arm B input: copy each video's original WeDetect detections and append the chosen Grounding DINO boxes of the
discovered objects (boxchoice/<task>/<shot>/choice.json) to the frames they were chosen in. Original detections, ids
and boxes are unchanged; added detections get the next integer ids, label = discovered object name, score = Grounding
DINO score, class_id -1 and provenance fields. run.json counts are updated for the changed frames. Writes
aug_detections/<task>/ and aug_detections/summary.json."""
import json, shutil
from pathlib import Path
HERE = Path(__file__).resolve().parent
V3 = HERE.parent / 'vl_vv_full_first200_v3_20261109'
states = {}
for path in (V3 / 'runs').glob('*/progress.json'):
    for tid, t in json.loads(path.read_text())['tasks'].items():
        if t.get('status') == 'success': states[tid] = t
summary = {}
for row in json.loads((V3 / 'miss_diagnosis/audit20/index.json').read_text()):
    task = row['task']; src = Path(states[task]['case_dir']).resolve() / 'entities/detections'
    dst = HERE / 'aug_detections' / task
    if dst.exists(): shutil.rmtree(dst)
    shutil.copytree(src, dst)
    run = json.loads((dst / 'run.json').read_text())
    added = 0
    for ch in sorted((HERE / 'boxchoice' / task).glob('*/choice.json')):
        c = json.loads(ch.read_text())
        for x in c['chosen']:
            f = dst / c['shot'] / f"frame_{x['frame_id']:06d}" / 'detections.json'
            data = json.loads(f.read_text())
            nid = max([d['id'] for d in data['detections']] + [0]) + 1
            data['detections'].append(dict(id=nid, label=x['name'], class_id=-1, box_xyxy=x['box'], score=x['score'],
                                           source='grounding_dino_background_discovery', discovery_object=f"{c['shot']}:{x['object']}",
                                           query=x['query'], gd_candidate_id=x['gd_id']))
            f.write_text(json.dumps(data, indent=1, ensure_ascii=False) + '\n')
            for r in run['results']:
                if r['shot'] == c['shot'] and r['frame_id'] == x['frame_id']:
                    r['count'] = len(data['detections'])
            added += 1
    run['augmentation'] = dict(note='chosen Grounding DINO boxes of discovered background objects appended (vl_vv_background_discovery_20261110)', added=added)
    (dst / 'run.json').write_text(json.dumps(run, indent=1, ensure_ascii=False) + '\n')
    summary[task] = dict(source=str(src), added=added)
(HERE / 'aug_detections' / 'summary.json').write_text(json.dumps(summary, indent=1) + '\n')
print(sum(v['added'] for v in summary.values()), 'boxes added over', len(summary), 'videos')
