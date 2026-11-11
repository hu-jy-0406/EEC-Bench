#!/usr/bin/env python3
"""Token, cost and time per stage for a test run (runs/<name>/).

Every API call folder holds status.json (usage rows from the transport),
prompt.txt and api_request.json (image count).  A call is attributed to a
stage by its path; folders of the validation-repair loop count as repair calls.
Matching v2 usage comes from its call folders, or from global_match_v2/audit.json
when it has none.  Costs are GPT-6 Luna standard API estimates (USD 0.10/M
uncached input, 0.01/M cached input, 0.50/M output), not bills.

The input composition is estimated by least squares over all calls:
input_tokens ~ a * prompt characters + b * images.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

EXP = Path(__file__).resolve().parent
PRICE = dict(uncached=0.10, cached=0.01, output=0.50)
BASIS = ('GPT-6 Luna standard API estimate: USD 0.10/M uncached input, 0.01/M cached input, 0.50/M output; '
         'cached input is a subset of input; not a bill')


def read(path):
    return json.loads(Path(path).read_text())


def stage_of(path, case, out):
    try:
        rel = path.relative_to(case).parts
        top = rel[0]
        if top == 'entities':
            return 'clustering'
        if top == 'shot_prompt_recovery':
            return 'binding'
        if top.startswith('global_match'):
            return 'matching'
        return 'case:' + top
    except ValueError:
        rel = path.relative_to(out).parts
        top, rest = rel[0], '/'.join(rel[1:]).lower()
        if top.endswith('_review'):
            for part in ('rewrite', 'verdict'):
                if part in rest:
                    return f'{top}_{part}'
        if top == 'episode_scoring':
            for branch in ('vl', 'vv'):
                if rest.startswith((branch, f'call_{branch}')):
                    return f'episode_scoring_{branch}'
        return top


def usage_rows(status):
    return list(status.get('usage') or status.get('known_usage') or [])


def cost(row):
    unc = max(0, row['input'] - row['cached'])
    return (unc * PRICE['uncached'] + row['cached'] * PRICE['cached'] + row['output'] * PRICE['output']) / 1e6


def calls_of(task, outputs_only=False):
    case, out = Path(task['case_dir']), Path(task['output_dir'])
    calls, seen = [], set()
    for root in ((out,) if outputs_only else (case, out)):
        if not root.is_dir():
            continue
        for status_path in sorted(root.rglob('status.json')):
            folder = status_path.parent
            try:
                status = read(status_path)
            except ValueError:
                continue
            rows = usage_rows(status)
            if not rows:
                continue
            request = read(folder / 'api_request.json') if (folder / 'api_request.json').is_file() else {}
            prompt = folder / 'prompt.txt'
            for index, row in enumerate(rows):
                key = row.get('api_response_id') or f'{folder}#{index}'
                if key in seen:
                    continue
                seen.add(key)
                calls.append(dict(
                    stage=stage_of(folder, case, out), folder=str(folder),
                    repair='repair' in str(folder.relative_to(root)).lower() or index > 0,
                    input=int(row.get('input_tokens') or 0), cached=int(row.get('cached_input_tokens') or 0),
                    output=int(row.get('output_tokens') or 0),
                    reasoning=int(row.get('reasoning_output_tokens') or 0),
                    prompt_chars=len(prompt.read_text()) if prompt.is_file() and index == 0 else None,
                    images=request.get('image_count') if index == 0 else None))
    audit = case / 'global_match_v2/audit.json'
    if not outputs_only and audit.is_file() and not any(call['stage'] == 'matching' for call in calls):
        for row in usage_rows(read(audit)):
            calls.append(dict(stage='matching', folder=str(audit), repair=False,
                              input=int(row.get('input_tokens') or 0), cached=int(row.get('cached_input_tokens') or 0),
                              output=int(row.get('output_tokens') or 0),
                              reasoning=int(row.get('reasoning_output_tokens') or 0), prompt_chars=None, images=None))
    return calls


def totals(calls):
    t = dict(calls=len(calls), repair_calls=sum(c['repair'] for c in calls),
             input=sum(c['input'] for c in calls), cached=sum(c['cached'] for c in calls),
             output=sum(c['output'] for c in calls), reasoning=sum(c['reasoning'] for c in calls))
    t['usd'] = round(cost(t), 6)
    return t


def fit(calls):
    rows = [c for c in calls if c['prompt_chars'] is not None and c['images'] is not None]
    if len(rows) < 3:
        return None
    import numpy as np
    x = np.array([[c['prompt_chars'], c['images']] for c in rows], dtype=float)
    y = np.array([c['input'] for c in rows], dtype=float)
    (a, b), *_ = np.linalg.lstsq(x, y, rcond=None)
    image_tokens = float(sum(b * c['images'] for c in rows))
    return dict(calls=len(rows), tokens_per_char=round(float(a), 4), tokens_per_image=round(float(b), 1),
                image_share_of_input=round(image_tokens / float(y.sum()), 3))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, nargs='+', help='One or more run names; tasks are pooled')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--outputs-only', action='store_true',
                        help='Count only the model stages in each output folder (replays on a frozen frontend)')
    parser.add_argument('--tasks', nargs='*', help='Only these task IDs')
    args = parser.parse_args()
    tasks = {}
    for name in args.run:
        tasks.update(read(EXP / 'runs' / name / 'progress.json')['tasks'])
    per_task, all_calls, stage_seconds = {}, [], defaultdict(list)
    for tid, task in sorted(tasks.items()):
        if 'output_dir' not in task or (args.tasks and tid not in args.tasks):
            continue
        calls = calls_of(task, args.outputs_only)
        all_calls.extend(dict(c, task=tid) for c in calls)
        run_json = Path(task['output_dir']) / 'run.json'
        stages = read(run_json).get('stage_results', []) if run_json.is_file() else []
        for row in stages:
            stage_seconds[row['name']].append(row['seconds'])
        per_task[tid] = dict(status=task.get('status'), pipeline_seconds=task.get('pipeline_seconds'),
                             totals=totals(calls),
                             stage_seconds={row['name']: round(row['seconds'], 1) for row in stages})
    by_stage = defaultdict(list)
    for call in all_calls:
        by_stage[call['stage']].append(call)
    report = dict(run=args.run, pricing_basis=BASIS, tasks=len(per_task),
                  succeeded=sum(t['status'] == 'success' for t in per_task.values()),
                  total=totals(all_calls),
                  by_stage={stage: dict(totals(calls), fit=fit(calls)) for stage, calls in sorted(by_stage.items())},
                  input_fit=fit(all_calls),
                  stage_seconds={name: dict(n=len(v), mean=round(sum(v) / len(v), 1), max=round(max(v), 1))
                                 for name, v in sorted(stage_seconds.items())},
                  per_task=per_task)
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        args.out.write_text(text + '\n')
    print(json.dumps({k: report[k] for k in ('tasks', 'succeeded', 'total', 'input_fit')}, indent=1))
    for stage, row in report['by_stage'].items():
        print(f"{stage:28s} calls {row['calls']:4d} (repair {row['repair_calls']:3d})  in {row['input']:9d}"
              f"  cached {row['cached']:8d}  out {row['output']:8d}  USD {row['usd']:.4f}")


if __name__ == '__main__':
    main()
