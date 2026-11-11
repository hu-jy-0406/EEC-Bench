#!/usr/bin/env python3
"""Collect the scoring units of the first-200 rerun (vl_vv_full_first200_v3_20261109) into units.jsonl:
one row per video with model, priority, number of shots, number of contract requirements and every
scored unit (bucket, verdict, review confidence, severity, deduction of scoring v6).  Read-only."""
import json
from pathlib import Path

EXP = Path(__file__).resolve().parent
RUN = EXP.parent / 'vl_vv_full_first200_v3_20261109'


def main():
    rows = []
    for path in sorted((RUN / 'runs').glob('*/progress.json')):
        for tid, s in json.loads(path.read_text())['tasks'].items():
            if s.get('status') != 'success':
                continue
            pri, model = tid.split('__')
            case, out = Path(s['case_dir']), Path(s['output_dir'])
            req = json.loads((case / 'requirements.json').read_text())
            sc = json.loads((out / 'episode_scoring/result.json').read_text())
            rows.append(dict(
                task=tid, model=model, priority=int(pri.split('_')[1]), shots=len(req['shot_ids']),
                requirements=len(req['requirements']), template_rows=len(req['template']),
                scores_v6=sc['scores'], scoring_result=str(out / 'episode_scoring/result.json'),
                units=[dict(unit_id=u['unit_id'], bucket=u['bucket'], verdict=u['verdict'],
                            confidence=u.get('review_confidence'), severity=u.get('severity'),
                            deduction=u.get('adjusted_deduction')) for u in sc['unit_scores']]))
    rows.sort(key=lambda r: (r['priority'], r['model']))
    with open(EXP / 'units.jsonl', 'w') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(len(rows))


if __name__ == '__main__':
    main()
