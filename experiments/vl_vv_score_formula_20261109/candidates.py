#!/usr/bin/env python3
"""Compare candidate aggregation rules on the rerun units (units.jsonl) with the earliest first-200 run
(vl_vv_multimodel_first200_run02 + _b, chain v1, scoring v2).  Deductions D are those of scoring v6
(w(severity) x confidence factor; uncertain w x 0.25); only the aggregation changes.  S = shots."""
import csv
import json
import math
import statistics as st
from collections import defaultdict
from pathlib import Path

EXP = Path(__file__).resolve().parent
B = ('v_l', 'within_shot', 'cross_shot')
MODELS = ('storymem', 'holocine', 'wan22', 'cinetrans', 'wan21')


def deductions(r, b):
    return [u['deduction'] for u in r['units'] if u['bucket'] == b and u['verdict'] in ('confirmed', 'uncertain')]


RULES = {
    'v6_product': lambda D, S: 100 * math.prod(1 - d / 100 for d in D),
    'per_shot_product': lambda D, S: 100 * math.prod(1 - d / 100 for d in D) ** (1 / S),
    'per_shot_exp': lambda D, S: 100 * math.exp(-sum(D) / (100 * S)),
    'per_shot_hyperbolic': lambda D, S: 100 / (1 + sum(D) / (100 * S)),
    'hyperbolic_no_norm': lambda D, S: 100 / (1 + sum(D) / 100),
}


def earliest():
    out = {}
    for d in ('vl_vv_multimodel_first200_run02', 'vl_vv_multimodel_first200_run02_b'):
        for r in csv.DictReader(open(EXP.parent / d / 'final_scores.csv')):
            v = dict(v_l=float(r['v_l']), within_shot=float(r['v_v_within']), cross_shot=float(r['v_v_cross']))
            out[(int(r['generation_priority']), r['model_id'])] = v
    return out


def table(scores, label):
    print(f'== {label}')
    for m in MODELS + ('all',):
        vs = [v for (p, mm), v in scores.items() if m in (mm, 'all')]
        means = {b: st.mean(x[b] for x in vs) for b in B}
        uec = st.mean(st.mean(x[b] for b in B) for x in vs)
        sd = st.pstdev(st.mean(x[b] for b in B) for x in vs)
        print(f'{m:10s} V-L {means["v_l"]:6.2f} within {means["within_shot"]:6.2f} cross {means["cross_shot"]:6.2f} '
              f'V-V {(means["within_shot"] + means["cross_shot"]) / 2:6.2f} UEC {uec:6.2f} (sd {sd:5.2f})')
    by_s = defaultdict(list)
    shots = {(r['priority'], r['model']): r['shots'] for r in ROWS}
    for key, x in scores.items():
        by_s[shots[key]].append(st.mean(x[b] for b in B))
    print('  UEC by shots:', {s: round(st.mean(v), 2) for s, v in sorted(by_s.items())})


ROWS = [json.loads(l) for l in open(EXP / 'units.jsonl')]

if __name__ == '__main__':
    table(earliest(), 'earliest run (chain v1, scoring v2)')
    for name, f in RULES.items():
        table({(r['priority'], r['model']): {b: f(deductions(r, b), r['shots']) for b in B} for r in ROWS}, name)
