#!/usr/bin/env python3
"""Raw WeDetect candidates with wall/floor/ceiling-type labels in all keyframes of the given reuse tasks, and the
score range of all candidates (to see whether such labels occur at all)."""
import json, re, sys, glob, collections
from pathlib import Path
EXP = Path(__file__).resolve().parent
DET_WALL = re.compile(r'墙|壁纸|瓷砖|地面|地板|天花')
st = {}
for path in (EXP / 'runs').glob('*/progress.json'):
    for tid, s in json.loads(path.read_text())['tasks'].items():
        if s.get('status') == 'success' and s.get('mode') == 'reuse_vv':
            st[tid] = s
for tid in sys.argv[1:]:
    case = Path(st[tid]['case_dir'])
    hits, n, frames, scores = collections.Counter(), 0, 0, []
    for f in glob.glob(str(case / 'entities/detections/Shot*/frame_*/detections.json')):
        d = json.loads(Path(f).read_text())
        frames += 1
        for x in d['detections']:
            n += 1
            scores.append(x['score'])
            if DET_WALL.search(x['label']):
                hits[x['label']] += 1
    print(tid, 'frames', frames, 'candidates', n, 'min score', round(min(scores), 2) if scores else None, 'wall-type', dict(hits))
