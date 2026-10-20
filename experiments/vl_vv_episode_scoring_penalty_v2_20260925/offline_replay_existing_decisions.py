#!/usr/bin/env python3
"""Reapply v2 deductions to existing v1 severity/verdict decisions; no API calls."""
import json
import statistics
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[0] / 'vl_vv_episode_scoring_20260925' / 'batch'
OUT = HERE / 'offline_replay_v1_decisions'
WEIGHTS = {'minor': Decimal(10), 'moderate': Decimal(25),
           'major': Decimal(50), 'critical': Decimal(80)}
CONFIDENCE = {'high': Decimal(1), 'medium': Decimal('0.75'), 'low': Decimal('0.5')}
BUCKETS = ('v_l', 'within_shot', 'cross_shot')


def read(path):
    return json.loads(path.read_text())


def rounded(value):
    return float(value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def replay(old):
    groups = {bucket: {} for bucket in BUCKETS}
    for row in old['issue_scores']:
        if row['verdict'] != 'confirmed':
            continue
        root = row['event_root_issue_id']
        deduction = WEIGHTS[row['severity']] * CONFIDENCE[row['review_confidence']]
        groups[row['bucket']][root] = max(groups[row['bucket']].get(root, Decimal(0)), deduction)
    scores = {}
    event_rows = []
    for bucket in BUCKETS:
        score = Decimal(100)
        for root, deduction in groups[bucket].items():
            score *= 1 - deduction / 100
            event_rows.append({'bucket': bucket, 'root_issue_id': root,
                               'deduction': float(deduction)})
        scores[bucket] = rounded(score)
    scores['v_v_overall'] = rounded((Decimal(str(scores['within_shot'])) +
                                     Decimal(str(scores['cross_shot']))) / 2)
    return scores, event_rows


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    rows = []
    for model_dir in sorted(SOURCE.iterdir()):
        if not model_dir.is_dir():
            continue
        for path in sorted(model_dir.glob('*/result.json')):
            old = read(path)
            scores, events = replay(old)
            output = {'status': 'offline_reaggregation',
                      'rubric_version': 'penalty_v2',
                      'source_v1_result': str(path.resolve()),
                      'source_v1_scores': old['scores'],
                      'scores': {'v_l': scores['v_l'],
                                 'v_v': {'within_shot': scores['within_shot'],
                                         'cross_shot': scores['cross_shot'],
                                         'overall': scores['v_v_overall']}},
                      'event_scores_v2': events,
                      'api_calls': 0,
                      'limitation': 'Reuses v1 verdict, confidence, severity and duplicate decisions; this is not a fresh v2 Luna assessment.'}
            dest = OUT / model_dir.name / path.parent.name
            dest.mkdir(parents=True)
            (dest / 'result.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
            rows.append({'model': model_dir.name, 'episode': path.parent.name,
                         'v1_vl': old['scores']['v_l'], 'v2_vl': scores['v_l'],
                         'v1_within': old['scores']['v_v']['within_shot'],
                         'v2_within': scores['within_shot'],
                         'v1_cross': old['scores']['v_v']['cross_shot'],
                         'v2_cross': scores['cross_shot'],
                         'v1_vv': old['scores']['v_v']['overall'],
                         'v2_vv': scores['v_v_overall'],
                         'confirmed': sum(x['verdict'] == 'confirmed' for x in old['issue_scores']),
                         'events_v2': len(events)})
    if len(rows) != 30:
        raise RuntimeError(f'Expected 30 frozen v1 scoring outputs; found {len(rows)}')

    summary = {'status': 'offline_reaggregation', 'cases': len(rows), 'api_calls': 0,
               'base_deductions_v2': {k: int(v) for k, v in WEIGHTS.items()},
               'model_means': {}}
    lines = ['# Offline replay of existing scoring decisions under penalty v2', '',
             'This replay reuses the v1 scorer’s recorded review verdicts, confidence, severity and duplicate links. It changes only the deterministic base deduction table to 10/25/50/80. No Luna calls were made; these are not fresh v2 assessments or human-calibrated scores.', '',
             '| Model | V-L v1 | V-L replay | Within v1 | Within replay | Cross v1 | Cross replay | V-V v1 | V-V replay |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for model in ('wan22', 'storymem', 'holocine'):
        sub = [r for r in rows if r['model'] == model]
        cols = ('v1_vl', 'v2_vl', 'v1_within', 'v2_within', 'v1_cross', 'v2_cross', 'v1_vv', 'v2_vv')
        means = {c: statistics.mean(r[c] for r in sub) for c in cols}
        summary['model_means'][model] = {c: round(v, 2) for c, v in means.items()}
        lines.append(f"| {model} | " + ' | '.join(f'{means[c]:.2f}' for c in cols) + ' |')
    lines += ['', 'A bucket with no confirmed event remains 100. Penalty changes therefore do not recover candidates missed by discovery or review.', '',
              '| Model | Episode | V-L v1→replay | Within v1→replay | Cross v1→replay | V-V v1→replay | Confirmed |',
              '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for r in rows:
        lines.append(f"| {r['model']} | `{r['episode']}` | {r['v1_vl']:.2f}→{r['v2_vl']:.2f} | {r['v1_within']:.2f}→{r['v2_within']:.2f} | {r['v1_cross']:.2f}→{r['v2_cross']:.2f} | {r['v1_vv']:.2f}→{r['v2_vv']:.2f} | {r['confirmed']} |")
    (OUT / 'REPORT.md').write_text('\n'.join(lines) + '\n')
    (OUT / 'summary.json').write_text(json.dumps(summary | {'rows': rows}, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
