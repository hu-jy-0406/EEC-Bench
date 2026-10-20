#!/usr/bin/env python3
"""Review behaviour, repair rounds, timing, cost and scores of the final validation runs (runs/main)."""
import collections
import glob
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    bases, verdicts, split, cands = collections.Counter(), collections.Counter(), collections.Counter(), collections.Counter()
    clarified = units = challenge = 0
    repair, calls = collections.Counter(), collections.Counter()
    for run in sorted(p for p in (HERE / 'runs/main').glob('run_*/*') if p.is_dir()):
        for b in ('vl', 'vv'):
            r = json.load(open(run / f'{b}_review/result.json'))
            cands[b] += len(r['candidates'])
            for u in r['units']:
                units += 1
                bases[f'{b}:{u["basis"]}'] += 1
                verdicts[f'{b}:{u["scope"]}:{u["verdict"]}'] += 1
                clarified += u['revision'] == 'clarified'
            if r['model_output']:
                split[b] += sum(rv['action'] == 'split' for rv in r['model_output']['reviews'])
        for st in ('vl_detection', 'vv_detection', 'vl_review', 'vv_review'):
            f = run / st / 'call_repair_audit.json'
            if f.is_file():
                a = json.load(open(f))
                repair[st] += a['repair_rounds']
                calls[st] += len(a['rounds'])
                challenge += sum('the detector located' in e for rd in a['rounds'] for e in rd['errors'])
    a = json.load(open(HERE / 'analysis.json'))
    rows = [r for r in a['runs'] if r['run'].startswith('runs/main/')]
    stage = collections.defaultdict(list)
    cost = collections.defaultdict(float)
    for r in rows:
        for k, v in r['stage_seconds'].items():
            stage[k].append(v)
        for st, c in r['token_cost'].items():
            cost[st] += (c or {}).get('estimated_usd', 0)
    scores = collections.defaultdict(list)
    for r in rows:
        s = r['scores']
        scores[r['case']].append(dict(v_l=s['v_l'], within=s['v_v']['within_shot'], cross=s['v_v']['cross_shot'],
                                      v_v=s['v_v']['overall'], unintentional=s['v_v_unintentional']['overall'],
                                      remainder=s['v_v_remainder']['overall'],
                                      involving=r['v_v_issue_statistics']['total']['involving_unintentional'],
                                      confirmed_vv=r['v_v_issue_statistics']['total']['confirmed_issues']))
    out = dict(candidates=dict(cands), units=units, clarified_units=clarified, split_candidates=dict(split),
               verdicts=dict(sorted(verdicts.items())), bases=dict(sorted(bases.items())),
               repair_rounds=dict(repair), first_and_repair_calls=dict(calls), not_verifiable_challenges=challenge,
               wall_seconds=dict(mean=round(statistics.mean(r['wall_seconds'] for r in rows), 1),
                                 median=statistics.median(r['wall_seconds'] for r in rows),
                                 max=max(r['wall_seconds'] for r in rows)),
               stage_seconds_mean={k: round(statistics.mean(v), 1) for k, v in stage.items()},
               stage_usd_total={k: round(v, 6) for k, v in cost.items()}, scores=scores)
    (HERE / 'review_stats.json').write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
