#!/usr/bin/env python3
"""Rescore the first-200 rerun (vl_vv_full_first200_v3_20261109) with the per-shot rule (zero model calls).

Per issue (unchanged from scoring v6): D = w(severity) x c, w = 10 / 25 / 50 / 80 (minor, moderate, major,
critical), c = 1 / 0.75 / 0.5 for a confirmed issue with verifier confidence high / medium / low and 0.25 for an
uncertain issue; rejected issues deduct nothing.  Per dimension (V-L, V-V within-shot, V-V cross-shot):

    s = 100 * exp(-sum(D) / (100 * S)),   S = number of shots of the episode

UEC = mean of the three dimensions, V-V = mean of within and cross (as in v6).  The per-issue deductions are read
from each video's scoring v6 result (`adjusted_deduction`), so severities and confidences are those of the run.
Outputs: rescored.jsonl (per video), summary.json (per model, distribution, rankings).
"""
import csv
import json
import math
import random
import statistics as st
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

EXP = Path(__file__).resolve().parent
BUCKETS = ('v_l', 'within_shot', 'cross_shot')
MODELS = ('storymem', 'holocine', 'wan22', 'cinetrans', 'wan21')
W = {'minor': 10, 'moderate': 25, 'major': 50, 'critical': 80}
C = {('confirmed', 'high'): 1.0, ('confirmed', 'medium'): 0.75, ('confirmed', 'low'): 0.5}
C_UNCERTAIN = 0.25


def r2(x):
    return float(Decimal(repr(x)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def deduction(u):
    """D of one unit, recomputed from severity and confidence and checked against the v6 record."""
    if u['verdict'] == 'rejected':
        return 0.0
    c = C_UNCERTAIN if u['verdict'] == 'uncertain' else C[(u['verdict'], u['confidence'])]
    d = W[u['severity']] * c
    assert abs(d - u['deduction']) < 1e-9, (u, d)
    return d


def dimension_score(ds, shots):
    return 100 * math.exp(-sum(ds) / (100 * shots))


def rescore(row):
    out = dict(task=row['task'], model=row['model'], priority=row['priority'], shots=row['shots'])
    scores, inputs = {}, {}
    for b in BUCKETS:
        ds = [deduction(u) for u in row['units'] if u['bucket'] == b]
        units = [u for u in row['units'] if u['bucket'] == b]
        inputs[b] = dict(sum_deduction=sum(ds), confirmed=sum(u['verdict'] == 'confirmed' for u in units),
                         uncertain=sum(u['verdict'] == 'uncertain' for u in units),
                         rejected=sum(u['verdict'] == 'rejected' for u in units))
        scores[b] = dimension_score(ds, row['shots'])
    uec = sum(scores.values()) / 3
    out['scores'] = dict(v_l=r2(scores['v_l']), v_v=dict(within_shot=r2(scores['within_shot']),
                                                         cross_shot=r2(scores['cross_shot']),
                                                         overall=r2((scores['within_shot'] + scores['cross_shot']) / 2)),
                         uec=r2(uec))
    out['inputs'] = inputs
    out['scores_v6'] = row['scores_v6']
    out['scoring_result_v6'] = row['scoring_result']
    return out


def flat(s):
    return dict(v_l=s['v_l'], within=s['v_v']['within_shot'], cross=s['v_v']['cross_shot'], v_v=s['v_v']['overall'],
                uec=s['uec'])


def percentiles(v):
    v = sorted(v)
    return {f'p{int(q * 100)}': round(v[round(q * (len(v) - 1))], 2) for q in (0.05, 0.25, 0.5, 0.75, 0.95)}


def bootstrap(diffs, n=5000, seed=0):
    rng = random.Random(seed)
    means = sorted(st.mean(rng.choices(diffs, k=len(diffs))) for _ in range(n))
    return [round(means[int(0.025 * n)], 2), round(means[int(0.975 * n) - 1], 2)]


def earliest():
    out = {}
    for d in ('vl_vv_multimodel_first200_run02', 'vl_vv_multimodel_first200_run02_b'):
        for r in csv.DictReader(open(EXP.parent / d / 'final_scores.csv')):
            v = dict(v_l=float(r['v_l']), within=float(r['v_v_within']), cross=float(r['v_v_cross']))
            v['v_v'] = (v['within'] + v['cross']) / 2
            v['uec'] = (v['v_l'] + v['within'] + v['cross']) / 3
            out[(int(r['generation_priority']), r['model_id'])] = v
    return out


def summarize(scores, shots):
    keys = ('v_l', 'within', 'cross', 'v_v', 'uec')
    per_model = {}
    for m in MODELS + ('all',):
        vs = [v for (p, mm), v in scores.items() if m in (mm, 'all')]
        per_model[m] = {k: round(st.mean(x[k] for x in vs), 2) for k in keys}
        per_model[m]['videos'] = len(vs)
    ranking = {k: sorted(MODELS, key=lambda m: -per_model[m][k]) for k in keys}
    pris = sorted({p for p, _ in scores})
    pairs = {}
    order = ranking['uec']
    for a, b in zip(order, order[1:]):
        diffs = [scores[(p, a)]['uec'] - scores[(p, b)]['uec'] for p in pris]
        pairs[f'{a} - {b}'] = dict(mean=round(st.mean(diffs), 2), bootstrap_95=bootstrap(diffs))
    by_shots = defaultdict(list)
    for key, v in scores.items():
        by_shots[shots[key]].append(v['uec'])
    return dict(per_model=per_model, ranking=ranking, adjacent_uec_pairs=pairs,
                uec_percentiles=percentiles([v['uec'] for v in scores.values()]),
                v_l_percentiles=percentiles([v['v_l'] for v in scores.values()]),
                cross_percentiles=percentiles([v['cross'] for v in scores.values()]),
                uec_by_shots={s: round(st.mean(v), 2) for s, v in sorted(by_shots.items())})


def main():
    rows = [json.loads(l) for l in open(EXP / 'units.jsonl')]
    rescored = [rescore(r) for r in rows]
    with open(EXP / 'rescored.jsonl', 'w') as f:
        for r in rescored:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    shots = {(r['priority'], r['model']): r['shots'] for r in rows}
    new = {(r['priority'], r['model']): flat(r['scores']) for r in rescored}
    v6 = {(r['priority'], r['model']): flat(r['scores_v6']) for r in rescored}
    summary = dict(
        rule='s = 100 * exp(-sum(D) / (100 * S)) per dimension; D = w(severity) x c; w = 10/25/50/80; '
             'c = 1/0.75/0.5 (confirmed high/medium/low), 0.25 (uncertain), 0 (rejected); S = shots; '
             'UEC = mean of V-L, within, cross; V-V = mean of within and cross',
        source='experiments/vl_vv_full_first200_v3_20261109 (1,000 videos, chain v6); per-issue deductions of scoring v6',
        model_calls=0,
        per_shot_exp=summarize(new, shots), scoring_v6=summarize(v6, shots), earliest_chain_v1=summarize(earliest(), shots))
    (EXP / 'summary.json').write_text(json.dumps(summary, indent=1, ensure_ascii=False) + '\n')
    for name in ('earliest_chain_v1', 'scoring_v6', 'per_shot_exp'):
        s = summary[name]
        print('==', name)
        for m, v in s['per_model'].items():
            print(f"  {m:10s} V-L {v['v_l']:6.2f} within {v['within']:6.2f} cross {v['cross']:6.2f} V-V {v['v_v']:6.2f} UEC {v['uec']:6.2f}")
        print('  UEC order:', ' > '.join(s['ranking']['uec']))
        print('  adjacent pairs:', s['adjacent_uec_pairs'])
        print('  UEC percentiles:', s['uec_percentiles'], ' by shots:', s['uec_by_shots'])


if __name__ == '__main__':
    main()
