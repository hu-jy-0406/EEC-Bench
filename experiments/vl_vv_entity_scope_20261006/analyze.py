#!/usr/bin/env python3
"""Effect of the episode-wide entity-description rule (review v5, discovery v4); writes analysis.json.

1. previous_failures: every paired V-L label that review v4 rejected in vl_vv_core_review_20261006, with its
   classified cause, and its review-v5 verdict on the identical candidate issue;
2. paired_v_l: all paired V-L labels, review v4 vs review v5 on identical candidates (dual-label and split sets);
3. targets: E1, E2, E3, E5 V-L labels under review v2 x3, v4 x3, v5 x3;
4. clip24: review v2 x2, v4, v5 on the 24 clip-model runs (confirmed labels, verified artifacts, controls);
5. pipeline: fresh discovery v4 + review v5 runs (per-video label counts, paired V-L verdicts, scores);
6. cost of this experiment.
"""
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
CORE = EXP / 'vl_vv_core_review_20261006'
V5 = HERE / 'runs/review'
OLD_NEW, RESULTS = EXP / 'vl_vv_old_vs_new_20261005/runs/v2', EXP / 'vl_vv_v2_results_20261005/runs/v2'
CASES = ('p002_wan21', 'p014_wan21', 'p028_wan22', 'p069_wan21')
COST_KEYS = ('uncached_input_tokens', 'cached_input_tokens', 'output_tokens', 'estimated_usd')


def read(path):
    return json.loads(Path(path).read_text())


def issues(path):
    return {i['issue_id']: i for i in read(path)['issues']}


def base_of(case):
    return RESULTS if case == 'p069_wan21' else OLD_NEW


def paths_for(key):
    """Review-v4 and review-v5 result paths of one '<case> <run>' key used in the rejection-reason file."""
    case, run = key.split()
    if run.startswith('run_'):
        return CORE / 'runs/fixed/v4_1' / run / case / 'issue_review/result.json', V5 / 'clip/v5_1' / run / case / 'issue_review/result.json'
    if run.startswith('v2fresh_'):
        k = run.split('_')[1]
        return (CORE / f'runs/fresh_v4/v4_1/fresh_{k}' / case / 'issue_review/result.json',
                V5 / 'v2fresh' / f'fresh_{k}' / case / 'issue_review/result.json')
    k = run.split('_')[1]
    return CORE / f'runs/split/fresh_{k}' / case / 'issue_review/result.json', V5 / 'split' / f'fresh_{k}' / case / 'issue_review/result.json'


def previous_failures():
    reasons = read(CORE / 'vl_rejection_reasons.json')
    rows = []
    for group in ('v2_dual', 'v3_split'):
        for key, cause in reasons[group].items():
            case, run, iid = key.split()
            p4, p5 = paths_for(f'{case} {run}')
            new = issues(p5)[iid]['review']['v_l_review']
            rows.append(dict(group=group, key=key, cause=cause, v4=issues(p4)[iid]['review']['v_l_review']['verdict'],
                             v5=new['verdict'], v5_assessment=new['assessment'], description=issues(p5)[iid]['description']))
    summary = {}
    for row in rows:
        summary.setdefault(row['group'], {}).setdefault(row['cause'], Counter())[row['v5']] += 1
    return rows, {g: {c: dict(v) for c, v in causes.items()} for g, causes in summary.items()}


def run_keys():
    dual = [f'{case} {run}' for case in CASES for run in ('run_a', 'run_b', 'run_c')]
    dual += [f'{case} v2fresh_{k}' for case in ('p014_wan21', 'p069_wan21') for k in (1, 2, 3)]
    split = [f'{case} split_{k}' for case in CASES for k in (1, 2, 3)]
    return dict(v2_dual=dual, v3_split=split)


def paired_v_l():
    out = {}
    for group, keys in run_keys().items():
        pairs = Counter()
        for key in keys:
            p4, p5 = paths_for(key)
            r4, r5 = issues(p4), issues(p5)
            for iid, issue in r5.items():
                if issue['v_l'] is None:
                    continue
                paired = issue['v_v'] is not None if group == 'v2_dual' else bool(issue.get('related_issue_ids'))
                if paired:
                    pairs[(r4[iid]['review']['v_l_review']['verdict'], issue['review']['v_l_review']['verdict'])] += 1
        total = sum(pairs.values())
        out[group] = dict(labels=total,
                          v4_confirmed=sum(n for (a, _), n in pairs.items() if a == 'confirmed'),
                          v5_confirmed=sum(n for (_, b), n in pairs.items() if b == 'confirmed'),
                          transitions={f'{a} -> {b}': n for (a, b), n in sorted(pairs.items())})
    return out


TARGETS = [('E1', 'p014_wan21', 'run_c', 'I1'), ('E2', 'p069_wan21', 'run_a', 'I2'),
           ('E3', 'p069_wan21', 'run_b', 'I3'), ('E5', 'p069_wan21', 'run_c', 'I2')]


def targets():
    out = {}
    for name, case, run, iid in TARGETS:
        paths = {'v2_1': base_of(case) / run / case / 'issue_review/result.json',
                 'v2_2': EXP / 'vl_vv_partial_review_20261006/runs_v2_repeat' / run / case / 'issue_review/result.json',
                 'v2_3': CORE / 'runs/fixed/v2_3' / run / case / 'issue_review/result.json'}
        for k in (1, 2, 3):
            paths[f'v4_{k}'] = CORE / f'runs/fixed/v4_{k}' / run / case / 'issue_review/result.json'
            paths[f'v5_{k}'] = V5 / f'clip/v5_{k}' / run / case / 'issue_review/result.json'
        rows = {}
        for review, path in paths.items():
            value = issues(path)[iid]['review']['v_l_review']
            rows[review] = dict(verdict=value['verdict'], assessment=value['assessment'])
        out[name] = rows
    return out


def clip24():
    ann = {}
    for path in (EXP / 'vl_vv_old_vs_new_20261005/annotations.json', EXP / 'vl_vv_v2_results_20261005/results_annotations.json'):
        ann.update(read(path))
    counts = {r: Counter() for r in ('v2_1', 'v2_2', 'v4_1', 'v5_1')}
    for base in (OLD_NEW, RESULTS):
        for run in sorted(p for p in base.iterdir() if p.is_dir()):
            for src in sorted(p for p in run.iterdir() if p.is_dir() and p.name.endswith(('wan21', 'wan22', 'storymem'))):
                paths = {'v2_1': src / 'issue_review/result.json',
                         'v2_2': EXP / 'vl_vv_partial_review_20261006/runs_v2_repeat' / run.name / src.name / 'issue_review/result.json',
                         'v4_1': CORE / 'runs/fixed/v4_1' / run.name / src.name / 'issue_review/result.json',
                         'v5_1': V5 / 'clip/v5_1' / run.name / src.name / 'issue_review/result.json'}
                reviews = {r: issues(p) for r, p in paths.items()}
                matches = ann.get(src.name, {}).get('runs', {}).get(f'v2/{run.name}', {}).get('matches', {})
                inverse = {}
                for artifact, ids in matches.items():
                    for iid in ids:
                        inverse.setdefault(iid, []).append(artifact)
                for iid, issue in reviews['v5_1'].items():
                    for label in ('v_l', 'v_v'):
                        if issue[label] is None:
                            continue
                        for r, rev in reviews.items():
                            verdict = rev[iid]['review'][f'{label}_review']['verdict']
                            counts[r][verdict] += 1
                            counts[r][f'{label}_confirmed'] += verdict == 'confirmed'
                            for artifact in inverse.get(iid, []):
                                kind = 'artifact' if artifact.startswith('A') else 'control'
                                counts[r][kind] += 1
                                counts[r][f'{kind}_confirmed'] += verdict == 'confirmed'
    return {r: dict(c) for r, c in counts.items()}


def pipeline():
    out = {}
    for case in CASES:
        rows = []
        for k in (1, 2, 3):
            root = HERE / 'runs/pipeline' / f'fresh_{k}' / case
            rev = read(root / 'issue_review/result.json')
            score = read(root / 'episode_scoring/result.json')['scores']
            disc = read(root / 'issue_discovery/result.json')
            c = Counter()
            for issue in rev['issues']:
                if issue['v_l'] is not None:
                    c['v_l'] += 1
                    c['v_l_confirmed'] += issue['review']['v_l_review']['verdict'] == 'confirmed'
                    if issue['related_issue_ids']:
                        c['paired_v_l'] += 1
                        c['paired_v_l_confirmed'] += issue['review']['v_l_review']['verdict'] == 'confirmed'
                    if any(q['source'] in ('contract', 'global_prompt') for q in issue['v_l']['prompt_evidence']):
                        c['v_l_quoting_contract_or_global'] += 1
                if issue['v_v'] is not None:
                    c['v_v'] += 1
                    c['v_v_confirmed'] += issue['review']['v_v_review']['verdict'] == 'confirmed'
            rows.append(dict(run=f'fresh_{k}', counts=dict(c), scores=score, repair_rounds=disc['repair_rounds']))
        out[case] = rows
    return out


def costs():
    total, calls = Counter(), 0
    for path in sorted((HERE / 'runs').rglob('result.json')):
        if path.parent.name not in ('issue_discovery', 'issue_review', 'episode_scoring'):
            continue
        result = read(path)
        token_cost = result.get('review_run', {}).get('token_cost') or result.get('token_cost')
        calls += result.get('review_run', {}).get('calls') or result.get('calls') or 0
        for key in COST_KEYS:
            total[key] += token_cost[key]
    total['estimated_usd'] = round(total['estimated_usd'], 6)
    return dict(calls=calls, **total, pricing_basis='GPT-6 Luna standard API estimate: USD 0.10/M uncached input, '
                                                     '0.01/M cached input, 0.50/M output; estimate, not billed amount.')


def main():
    rows, summary = previous_failures()
    result = dict(previous_failures=rows, previous_failure_summary=summary, paired_v_l=paired_v_l(), targets=targets(),
                  clip24=clip24(), pipeline=pipeline(), cost=costs())
    (HERE / 'analysis.json').write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps(summary, indent=1))
    print(json.dumps(result['paired_v_l'], indent=1))
    for name, rows_ in result['targets'].items():
        print(name, ' '.join(f'{r}={v["verdict"][:4]}' for r, v in rows_.items()))
    print(json.dumps(result['clip24'], indent=1))
    for case, rows_ in result['pipeline'].items():
        for row in rows_:
            print(case, row['run'], row['counts'], row['scores'])
    print(json.dumps(result['cost'], indent=1))


if __name__ == '__main__':
    main()
