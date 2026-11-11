#!/usr/bin/env python3
"""Recompute every rerun video with the live pipeline code (run_vl_vv_branch_scoring.materialize_v6, per-shot rule)
from its stored review results and severity assessments, and compare with rescored.jsonl (rescore.py).  Zero calls."""
import json
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP.parents[1] / 'scripts'))
import run_vl_vv_branch_scoring as scoring  # noqa: E402
import vl_vv_branch_common as common  # noqa: E402


def main():
    cfg = common.config(common.chain_spec('v6')['config'])
    offline = {r['task']: r for r in map(json.loads, open(EXP / 'rescored.jsonl'))}
    mismatches, n = [], 0
    for row in map(json.loads, open(EXP / 'units.jsonl')):
        result = json.loads(Path(row['scoring_result']).read_text())
        reviews = {b: json.loads(Path(p).read_text()) for b, p in result['source_reviews'].items()}
        units = reviews['vl']['units'] + reviews['vv']['units']
        entities = reviews['vl'].get('entities', []) + reviews['vv'].get('entities', [])
        assessments = {u['unit_id']: dict(severity=u['severity'], reason=u['reason'])
                       for u in result['unit_scores'] if u['severity'] is not None}
        shots = scoring.case_shot_count(Path(reviews['vl']['source_case']))
        scores, stats, ledger, _ = scoring.materialize_v6(units, assessments, entities, cfg, shots)
        n += 1
        if shots != row['shots'] or scores != offline[row['task']]['scores'] \
                or stats != result['consistency_issue_statistics'] \
                or [u['adjusted_deduction'] for u in ledger] != [u['adjusted_deduction'] for u in result['unit_scores']]:
            mismatches.append(row['task'])
    print(dict(videos=n, mismatches=len(mismatches), examples=mismatches[:5]))


if __name__ == '__main__':
    main()
