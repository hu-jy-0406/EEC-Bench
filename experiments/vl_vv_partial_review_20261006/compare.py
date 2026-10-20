#!/usr/bin/env python3
"""Compare three reviews of the same discovery candidates (24 clip-model runs).

- v2_orig: the original review v2 + scoring v3 of each run (vl_vv_old_vs_new_20261005 / vl_vv_v2_results_20261005);
- v2_repeat: a fresh repeat of review v2 + scoring v3 (runs_v2_repeat/), the reviewer's own run-to-run variance;
- v3: review v3 (true / partly true / false) + scoring v4 (runs/).

Writes comparison.json: per-label verdict transitions for each pair, every partly confirmed label with its true
part, labels whose scored status differs, annotation matches (A* = verified artifact, C* = control that should
not be reported), per-run scores, and token cost of review + scoring.
"""
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ANNOTATIONS = {}
for path in (ROOT / 'experiments/vl_vv_old_vs_new_20261005/annotations.json',
             ROOT / 'experiments/vl_vv_v2_results_20261005/results_annotations.json'):
    ANNOTATIONS.update(json.loads(path.read_text()))
SCORED = {'confirmed', 'partly_confirmed'}
VERSIONS = ('v2_orig', 'v2_repeat', 'v3')
COST_KEYS = ('uncached_input_tokens', 'cached_input_tokens', 'output_tokens', 'estimated_usd')


def read(path):
    return json.loads(Path(path).read_text())


def matches(case, run):
    found = ANNOTATIONS.get(case, {}).get('runs', {}).get(f'v2/{run}', {}).get('matches', {})
    inverse = {}
    for artifact, ids in found.items():
        for iid in ids:
            inverse.setdefault(iid, []).append(artifact)
    return inverse


def cost(review, score):
    total = Counter()
    for token_cost in (review['review_run']['token_cost'], score['token_cost']):
        for key in COST_KEYS:
            total[key] += token_cost[key]
    return dict(total)


def labels(review, score):
    """(issue_id, label) -> verdict, confidence, severity, deduction and review fields."""
    scored = {(r['issue_id'], r['label']): r for r in score['issue_scores']}
    rows = {}
    for issue in review['issues']:
        for label in ('v_l', 'v_v'):
            value = issue['review'][f'{label}_review']
            if value is None:
                continue
            ledger = scored[(issue['issue_id'], label)]
            rows[(issue['issue_id'], label)] = dict(verdict=value['verdict'], confidence=value['confidence'],
                                                    assessment=value['assessment'], severity=ledger['severity'],
                                                    deduction=ledger['adjusted_deduction'],
                                                    confirmed_part=value.get('confirmed_part'),
                                                    unsupported_part=value.get('unsupported_part'),
                                                    confirmed_shot_ids=value.get('confirmed_shot_ids'))
    return rows


def main():
    sources = {}
    for events in sorted(HERE.glob('events_stream*.jsonl')):
        for line in events.read_text().splitlines():
            row = json.loads(line)
            sources[(row['run'], row['case'])] = Path(row['source'])
    dirs = {'v3': HERE / 'runs', 'v2_repeat': HERE / 'runs_v2_repeat'}
    transitions = {pair: Counter() for pair in (('v2_orig', 'v2_repeat'), ('v2_orig', 'v3'), ('v2_repeat', 'v3'))}
    scored_changes = {f'{a} vs {b}': [] for a, b in transitions}
    partial, items, runs = [], [], []
    annotated = {version: Counter() for version in VERSIONS}
    calls = {version: Counter() for version in ('v2_repeat', 'v3')}
    for (run, case), src in sorted(sources.items(), key=lambda x: (x[0][1], x[0][0])):
        paths = {'v2_orig': src, **{version: base / run / case for version, base in dirs.items()}}
        if not all((path / 'episode_scoring/result.json').is_file() for path in paths.values()):
            continue
        reviews = {v: read(p / 'issue_review/result.json') for v, p in paths.items()}
        scores = {v: read(p / 'episode_scoring/result.json') for v, p in paths.items()}
        digests = {r['review_run']['source_discovery_sha256'] for r in reviews.values()}
        assert len(digests) == 1, (run, case)
        per_version = {v: labels(reviews[v], scores[v]) for v in VERSIONS}
        inverse = matches(case, run)
        descriptions = {issue['issue_id']: issue for issue in reviews['v3']['issues']}
        for key in per_version['v3']:
            iid, label = key
            issue = descriptions[iid]
            item = dict(run=run, case=case, issue_id=iid, label=label,
                        bucket='v_l' if label == 'v_l' else issue['v_v']['scope'],
                        subcategory=issue[label]['subcategory'], annotation=inverse.get(iid, []),
                        description=issue['description'], **{v: per_version[v][key] for v in VERSIONS})
            items.append(item)
            for a, b in transitions:
                transitions[(a, b)][(item[a]['verdict'], item[b]['verdict'])] += 1
                if (item[a]['verdict'] in SCORED) != (item[b]['verdict'] in SCORED):
                    scored_changes[f'{a} vs {b}'].append(dict(run=run, case=case, issue_id=iid, label=label,
                                                              annotation=item['annotation'],
                                                              verdicts=[item[a]['verdict'], item[b]['verdict']]))
            if item['v3']['verdict'] == 'partly_confirmed':
                partial.append(item)
            for artifact in item['annotation']:
                kind = 'artifact' if artifact.startswith('A') else 'control'
                for version in VERSIONS:
                    annotated[version][f'{kind}_labels'] += 1
                    annotated[version][f'{kind}_labels_scored'] += item[version]['verdict'] in SCORED
        for version in calls:
            calls[version]['review_calls'] += reviews[version]['review_run']['calls']
            calls[version]['review_repair_rounds'] += reviews[version]['review_run']['repair_rounds']
            calls[version]['scoring_calls'] += scores[version]['calls']
            calls[version]['scoring_repair_rounds'] += scores[version]['repair_rounds']
        runs.append(dict(run=run, case=case, scores={v: scores[v]['scores'] for v in VERSIONS},
                         verdict_counts={v: reviews[v]['review_run']['verdict_counts'] for v in VERSIONS},
                         cost={v: cost(reviews[v], scores[v]) for v in VERSIONS}))
    total_cost = {v: {k: round(sum(r['cost'][v][k] for r in runs), 9) for k in COST_KEYS} for v in VERSIONS}
    bucket_means = {}
    for version in VERSIONS:
        values = {'v_l': [r['scores'][version]['v_l'] for r in runs],
                  'within_shot': [r['scores'][version]['v_v']['within_shot'] for r in runs],
                  'cross_shot': [r['scores'][version]['v_v']['cross_shot'] for r in runs]}
        bucket_means[version] = {k: round(sum(v) / len(v), 2) for k, v in values.items()} if runs else {}
    result = dict(runs=len(runs), labels=len(items),
                  transitions={f'{a} -> {b}': {f'{x} -> {y}': n for (x, y), n in sorted(c.items())}
                               for (a, b), c in transitions.items()},
                  scored_status_changes=scored_changes,
                  annotated_label_recall=annotated, bucket_means=bucket_means,
                  partly_confirmed=partial, items=items, per_run=runs, calls={v: dict(c) for v, c in calls.items()},
                  review_plus_scoring_cost=total_cost,
                  pricing_basis='GPT-6 Luna standard API estimate: USD 0.10/M uncached input, 0.01/M cached input, '
                                '0.50/M output; estimate, not billed amount.')
    (HERE / 'comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n')
    summary = {k: result[k] for k in ('runs', 'labels', 'transitions', 'annotated_label_recall', 'bucket_means', 'calls',
                                      'review_plus_scoring_cost')}
    summary['scored_status_changes'] = {k: len(v) for k, v in scored_changes.items()}
    summary['partly_confirmed'] = len(partial)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
