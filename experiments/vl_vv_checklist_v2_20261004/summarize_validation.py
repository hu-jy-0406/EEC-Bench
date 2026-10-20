#!/usr/bin/env python3
"""Summarize v2 validation rounds against the historical v1 scores (offline, no API)."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNS = [ROOT / 'experiments/vl_vv_multimodel_first200_run02/final_scores.jsonl',
        ROOT / 'experiments/vl_vv_multimodel_first200_run02_b/final_scores.jsonl']
ROUNDS = ['validation_round1', 'validation_round2', 'validation_round3']
STAGES = ['issue_discovery', 'issue_review', 'episode_scoring']
PRICE = dict(uncached=0.10, cached=0.01, output=0.50)  # GPT-6 Luna standard API USD per million tokens


def read(path):
    return json.loads(Path(path).read_text())


def stage_usage(case_dir, stage):
    """Usage rows of every call in a stage, including repair rounds, from the repair audit."""
    audit = case_dir / stage / 'call_repair_audit.json'
    if audit.is_file():
        return read(audit).get('usage', [])
    return []


def main():
    v1 = {}
    for path in RUNS:
        for line in path.read_text().splitlines():
            row = json.loads(line)
            v1[(row['generation_priority'], row['model_id'])] = row
    table = []
    totals = dict(calls=0, input=0, cached=0, output=0)
    for name in ROUNDS:
        root = HERE / name
        if not root.is_dir():
            continue
        for case_dir in sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith('p')):
            priority, model = int(case_dir.name[1:4]), case_dir.name[5:]
            scoring_path = case_dir / 'episode_scoring/result.json'
            if not scoring_path.is_file():
                table.append(dict(round=name, priority=priority, model=model, status='incomplete'))
                continue
            scoring = read(scoring_path)
            discovery = read(case_dir / 'issue_discovery/result.json')
            review = read(case_dir / 'issue_review/result.json')
            usage = sum((stage_usage(case_dir, stage) for stage in STAGES), [])
            tokens = dict(calls=len(usage),
                          input=sum(int(u.get('input_tokens', 0)) for u in usage),
                          cached=sum(int(u.get('cached_input_tokens', 0)) for u in usage),
                          output=sum(int(u.get('output_tokens', 0)) for u in usage))
            for key in totals:
                totals[key] += tokens[key]
            old = v1[(priority, model)]['scores']
            table.append(dict(
                round=name, priority=priority, model=model, status='success',
                v1=dict(v_l=old['v_l'], within=old['v_v_within'], cross=old['v_v_cross']),
                v2=dict(v_l=scoring['scores']['v_l'], within=scoring['scores']['v_v']['within_shot'],
                        cross=scoring['scores']['v_v']['cross_shot']),
                discovery_counts=discovery['counts'], label_counts=scoring.get('label_counts'),
                review_verdicts=review['review_run']['verdict_counts'],
                repair_rounds=dict(discovery=discovery.get('repair_rounds'),
                                   review=review['review_run'].get('repair_rounds'),
                                   scoring=scoring.get('repair_rounds')),
                tokens=tokens))
    uncached = totals['input'] - totals['cached']
    totals['estimated_usd'] = round(uncached / 1e6 * PRICE['uncached'] + totals['cached'] / 1e6 * PRICE['cached']
                                    + totals['output'] / 1e6 * PRICE['output'], 6)
    totals['pricing_basis'] = ('GPT-6 Luna standard API estimate: USD 0.10/M uncached input, 0.01/M cached input '
                               '(subset of input), 0.50/M output; estimate, not a billed amount.')
    result = dict(cases=table, totals=totals)
    (HERE / 'validation_summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    for row in table:
        if row['status'] != 'success':
            print(row)
            continue
        print(f"{row['round'][-6:]} p{row['priority']:03d} {row['model']:9s} v1 L/W/X={row['v1']['v_l']:6.2f}/{row['v1']['within']:6.2f}/{row['v1']['cross']:6.2f}"
              f"  v2 L/W/X={row['v2']['v_l']:6.2f}/{row['v2']['within']:6.2f}/{row['v2']['cross']:6.2f}"
              f"  issues={row['discovery_counts']['issues']} dual={row['discovery_counts']['dual_labeled']}"
              f" W={row['discovery_counts']['v_v_within']} X={row['discovery_counts']['v_v_cross']}"
              f"  repair={row['repair_rounds']}")
    print(totals)


if __name__ == '__main__':
    main()
