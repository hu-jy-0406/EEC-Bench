#!/usr/bin/env python3
"""Floor coverings removed before clustering (exclude_floor_coverings_v1) and WeDetect candidates for wall, floor,
ceiling and similar place parts in the C full run: detections, shots and videos. Zero model calls."""
import collections
import json
import re
from pathlib import Path

RUNS = Path(__file__).resolve().parent.parent / 'vl_vv_full_first200_c_20261110' / 'runs'
PLACE = re.compile(r'墙|地板|地面|天花板|瓷砖|天空|草地|草坪|道路|街道|Wall|Floor|Ceiling|Sky|Ground', re.I)
exc, exc_v, exc_s, place, place_v = collections.Counter(), collections.defaultdict(set), collections.Counter(), collections.Counter(), collections.defaultdict(set)
sample = None
for base in sorted(RUNS.iterdir()):
    for inp in sorted((base / 'case/entities/shots').glob('*/input.json')):
        i = json.loads(inp.read_text())
        ex = (i.get('candidate_filter') or {}).get('excluded_detections') or []
        if ex and sample is None:
            sample = ex[0]
        names = {d['candidate_id']: d['name'] for f in i['frames'] for d in f['detections']}
        seen = set()
        for x in ex:
            n = x.get('name') or x.get('label') or x.get('detector_name') or '?'
            exc[n] += 1; exc_v[n].add(base.name); seen.add(n)
        for n in seen:
            exc_s[n] += 1
        for n in names.values():
            if PLACE.search(n):
                place[n] += 1; place_v[n].add(base.name)
print('sample', sample)
print('floor coverings', {n: (k, exc_s[n], len(exc_v[n])) for n, k in exc.items()})
print('place-part labels', {n: (k, len(place_v[n])) for n, k in place.most_common(20)})
