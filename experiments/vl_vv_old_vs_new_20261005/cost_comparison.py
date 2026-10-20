#!/usr/bin/env python3
"""Token usage and estimated API cost: old (v1) vs new (v2) evaluator on the same nine cases (offline).

Uses every recorded call (including validation-repair rounds) of the 18 fresh
v1 reruns and 27 v2 runs, plus the historical v1 runs and the shared detection
front end from the first-200 batch.  Prices: GPT-6 Luna standard API, USD per
million tokens: uncached input 0.10, cached input 0.01, output 0.50 (output
includes reasoning tokens).  Cached input is a subset of input.  "No-cache"
bills every input token at the uncached price.
"""
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HISTORICAL = [ROOT / 'experiments/vl_vv_multimodel_first200_run02/final_scores.jsonl',
              ROOT / 'experiments/vl_vv_multimodel_first200_run02_b/final_scores.jsonl']
STAGES = ('issue_discovery', 'issue_review', 'episode_scoring')
PRICE = dict(uncached=0.10, cached=0.01, output=0.50)
RUNS = {'v1': ('rerun_a', 'rerun_b'), 'v2': ('run_a', 'run_b', 'run_c')}


def read(path):
    return json.loads(Path(path).read_text())


def stage_rows(out, stage):
    audit = out / stage / 'call_repair_audit.json'
    if audit.is_file():
        return read(audit).get('usage', [])
    result = read(out / stage / 'result.json')
    return (result.get('review_run', {}).get('usage') if stage == 'issue_review' else result.get('usage')) or []


def tally(rows):
    inp = sum(int(r.get('input_tokens', 0)) for r in rows)
    cached = sum(int(r.get('cached_input_tokens', 0)) for r in rows)
    out = sum(int(r.get('output_tokens', 0)) for r in rows)
    reasoning = sum(int(r.get('reasoning_output_tokens', 0)) for r in rows)
    return dict(calls=len(rows), input=inp, cached=cached, uncached=inp - cached, output=out, reasoning=reasoning,
                usd=(inp - cached) / 1e6 * PRICE['uncached'] + cached / 1e6 * PRICE['cached'] + out / 1e6 * PRICE['output'],
                usd_nocache=inp / 1e6 * PRICE['uncached'] + out / 1e6 * PRICE['output'])


def add(a, b):
    return {k: a.get(k, 0) + b[k] for k in b}


def scale(a, n):
    return {k: v / n for k, v in a.items()}


def main():
    ref = read(HERE / 'reference.json')
    hist = {}
    for path in HISTORICAL:
        for line in path.read_text().splitlines():
            row = json.loads(line)
            hist[(row['generation_priority'], row['model_id'])] = row
    per = {p: {s: {} for s in STAGES + ('all',)} for p in ('v1', 'v2', 'v1_historical')}
    counts = {p: 0 for p in per}
    per_case = []
    frontend = {}
    for case in ref['cases']:
        key = case['key']
        row = hist[(case['priority'], case['model'])]
        frontend[key] = row['frontend_token_usage']
        sources = [('v1_historical', Path(row['output_dir']))]
        sources += [('v1', HERE / 'runs/v1' / r / key) for r in RUNS['v1']]
        sources += [('v2', HERE / 'runs/v2' / r / key) for r in RUNS['v2']]
        case_totals = {}
        for proto, out in sources:
            counts[proto] += 1
            total = {}
            for stage in STAGES:
                t = tally(stage_rows(out, stage))
                per[proto][stage] = add(per[proto][stage], t)
                total = add(total, t)
            per[proto]['all'] = add(per[proto]['all'], total)
            case_totals.setdefault(proto, []).append(total)
        per_case.append(dict(key=key, shots=len(read(Path(row['output_dir']).parent / 'work/case/raw_manifest.json')['shots']),
                             **{p: dict(mean_usd=statistics.mean(t['usd'] for t in v),
                                        mean_usd_nocache=statistics.mean(t['usd_nocache'] for t in v),
                                        mean_input=statistics.mean(t['input'] for t in v),
                                        mean_output=statistics.mean(t['output'] for t in v),
                                        mean_calls=statistics.mean(t['calls'] for t in v)) for p, v in case_totals.items()}))
    means = {p: {s: scale(per[p][s], counts[p]) for s in per[p]} for p in per}
    fe = {k: v for k, v in frontend.items()}
    fe_mean_usd = statistics.mean(v['estimated_usd'] for v in fe.values())
    fe_mean_nocache = statistics.mean((v['uncached_input_tokens'] + v['cached_input_tokens']) / 1e6 * PRICE['uncached']
                                      + v['output_tokens'] / 1e6 * PRICE['output'] for v in fe.values())
    # first-200 batch (1,000 tasks, all v1) as production context
    all_rows = [json.loads(l) for p in HISTORICAL for l in p.read_text().splitlines()]
    batch = dict(tasks=len(all_rows),
                 evaluation_usd=sum(r['evaluation_token_usage']['estimated_usd'] for r in all_rows),
                 frontend_usd=sum(r['frontend_token_usage']['estimated_usd'] for r in all_rows),
                 evaluation_input=sum(r['evaluation_token_usage']['uncached_input_tokens'] + r['evaluation_token_usage']['cached_input_tokens'] for r in all_rows),
                 evaluation_cached=sum(r['evaluation_token_usage']['cached_input_tokens'] for r in all_rows),
                 evaluation_output=sum(r['evaluation_token_usage']['output_tokens'] for r in all_rows))
    result = dict(pricing=PRICE, run_counts=counts, mean_per_run=means, per_case=per_case,
                  frontend_mean_per_task=dict(usd=fe_mean_usd, usd_nocache=fe_mean_nocache), first200_v1_batch=batch)
    (HERE / 'cost_comparison.json').write_text(json.dumps(result, indent=1) + '\n')

    f = lambda x: f'{x:,.0f}'
    for p in ('v1_historical', 'v1', 'v2'):
        print(f'== {p} (runs={counts[p]}) mean per run')
        for s in STAGES + ('all',):
            m = means[p][s]
            print(f"  {s:16s} calls {m['calls']:.2f} | input {f(m['input'])} (cached {f(m['cached'])}, uncached {f(m['uncached'])}) | output {f(m['output'])} (reasoning {f(m['reasoning'])}) | USD obs {m['usd']:.5f} no-cache {m['usd_nocache']:.5f}")
    print('frontend mean per task USD', round(fe_mean_usd, 5), 'no-cache', round(fe_mean_nocache, 5))
    for c in per_case:
        print(c['key'], c['shots'], 'v1 nocache', round(c['v1']['mean_usd_nocache'], 5), 'v2 nocache', round(c['v2']['mean_usd_nocache'], 5),
              'ratio', round(c['v2']['mean_usd_nocache'] / c['v1']['mean_usd_nocache'], 2), '| obs', round(c['v1']['mean_usd'], 5), round(c['v2']['mean_usd'], 5))
    print('batch', {k: round(v, 3) if isinstance(v, float) else v for k, v in batch.items()})


if __name__ == '__main__':
    main()
