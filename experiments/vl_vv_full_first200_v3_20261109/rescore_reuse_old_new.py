#!/usr/bin/env python3
"""Old (first run) vs new (this rerun) scores on the 668 reuse videos under the per-shot rule that became the default
on 2026-11-09 (s = 100*exp(-sum(D)/(100*S)) per dimension, ../vl_vv_score_formula_20261109/REPORT.md). Zero calls:
D = each unit's stored adjusted_deduction (rejected units deduct 0), S = shots from that experiment's rescored.jsonl.
New-side values are checked against rescored.jsonl. Writes rescored_reuse_old_new.json."""
import json, math, statistics as st
from pathlib import Path
EXP = Path(__file__).resolve().parent
RES = {json.loads(l)['task']: json.loads(l) for l in open(EXP.parent / 'vl_vv_score_formula_20261109/rescored.jsonl')}
BUCKETS = ('v_l', 'within_shot', 'cross_shot')


def score(result, shots):
    units = json.loads(Path(result).read_text())['unit_scores']
    s = {b: 100 * math.exp(-sum(u['adjusted_deduction'] for u in units if u['bucket'] == b and u['verdict'] != 'rejected') / (100 * shots)) for b in BUCKETS}
    return dict(v_l=s['v_l'], within=s['within_shot'], cross=s['cross_shot'], v_v=(s['within_shot'] + s['cross_shot']) / 2,
                uec=sum(s.values()) / 3)


old, new, maxdiff = [], [], 0.0
for path in sorted((EXP / 'runs').glob('*/progress.json')):
    for tid, t in json.loads(path.read_text())['tasks'].items():
        if t.get('status') != 'success' or t.get('mode') != 'reuse_vv':
            continue
        shots = RES[tid]['shots']
        n = score(Path(t['output_dir']) / 'episode_scoring/result.json', shots)
        maxdiff = max(maxdiff, abs(n['uec'] - RES[tid]['scores']['uec']))
        new.append(n)
        old.append(score(Path(t['source_attempt']) / 'results/episode_scoring/result.json', shots))
mean = lambda rows: {k: round(st.mean(r[k] for r in rows), 2) for k in rows[0]}
out = dict(videos=len(new), old=mean(old), new=mean(new), max_abs_diff_new_vs_rescored_jsonl=round(maxdiff, 4))
(EXP / 'rescored_reuse_old_new.json').write_text(json.dumps(out, indent=1) + '\n')
print(json.dumps(out, indent=1))
