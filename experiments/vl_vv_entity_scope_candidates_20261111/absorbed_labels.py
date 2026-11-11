#!/usr/bin/env python3
"""Which WeDetect labels never became entities of their own in the C full run (1,000 videos, fresh shot clustering):
labels absorbed into another entity (a candidate inside an entity whose dominant label differs), labels rejected by
the clustering agent (with reasons), and floor coverings removed before clustering. Zero model calls.
Writes absorbed_labels.json."""
import collections
import json
from pathlib import Path

RUNS = Path(__file__).resolve().parent.parent / 'vl_vv_full_first200_c_20261110' / 'runs'
absorbed = collections.Counter()          # (host label, absorbed label)
absorbed_videos = collections.defaultdict(set)
own = collections.Counter()               # labels that are the dominant label of an entity
rejected = collections.Counter()
rejected_reasons = collections.defaultdict(collections.Counter)
excluded = collections.Counter()
shots = 0
for base in sorted(RUNS.iterdir()):
    for sd in sorted((base / 'case/entities/shots').glob('*')):
        inp, ent = sd / 'input.json', sd / 'entities.json'
        if not (inp.is_file() and ent.is_file()):
            continue
        shots += 1
        i, e = json.loads(inp.read_text()), json.loads(ent.read_text())
        label = {d['candidate_id']: d['name'] for f in i['frames'] for d in f['detections']}
        for x in (i.get('candidate_filter') or {}).get('excluded_detections') or []:
            excluded[x.get('name') or x.get('label') or str(x)[:30]] += 1
        for x in e['entities']:
            labs = collections.Counter(label.get(c) for c in x['candidate_ids'] if c in label)
            if not labs:
                continue
            dom = labs.most_common(1)[0][0]
            own[dom] += 1
            for lab, k in labs.items():
                if lab != dom:
                    absorbed[(dom, lab)] += k
                    absorbed_videos[lab].add(base.name)
        for r in e.get('rejected_detections') or []:
            cid = r.get('candidate_id') if isinstance(r, dict) else r
            lab = label.get(cid, '?')
            rejected[lab] += 1
            reason = (r.get('reason') or '')[:80] if isinstance(r, dict) else ''
            rejected_reasons[lab][reason] += 1
by_label = collections.Counter()
for (dom, lab), k in absorbed.items():
    by_label[lab] += k
out = dict(shots=shots,
           absorbed_by_label=[dict(label=l, candidates=k, videos=len(absorbed_videos[l]), own_entities=own[l],
                                   hosts=dict(collections.Counter({d: c for (d, x), c in absorbed.items() if x == l}).most_common(4)))
                              for l, k in by_label.most_common(150)],
           rejected_by_label=[dict(label=l, candidates=k, reasons=dict(rejected_reasons[l].most_common(3))) for l, k in rejected.most_common(80)],
           excluded_floor_coverings=dict(excluded))
Path(__file__).with_name('absorbed_labels.json').write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n')
print('shots', shots, 'excluded', dict(excluded))
for r in out['absorbed_by_label'][:70]:
    print(r['label'], r['candidates'], r['videos'], 'own', r['own_entities'], r['hosts'])
print('--- rejected')
for r in out['rejected_by_label'][:40]:
    print(r['label'], r['candidates'], list(r['reasons'].items())[:2])
