#!/usr/bin/env python3
"""Summarize the core-review / atomic-label tests into analysis.json.

1. labeling: for the four target problems, how each discovery version labeled them per run (old v1 lists,
   v2 multi-label issues, v3 one label per issue with links) and the review verdicts (v1 review; v2 review and
   v4 review on v2 issues; v4 review on v3 issues);
2. fixed: verdicts on the fixed target issues (E1, E2, E3, E5, #068 I5) under review v2 x3, v3 (partly true) and v4 x3;
3. paired V-L: verdicts of V-L labels whose discrepancy is also reported as V-V, with the classified rejection reasons;
4. cost of every call made in this experiment.
"""
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
RUNS = HERE / 'runs'
OLD_NEW, RESULTS = EXP / 'vl_vv_old_vs_new_20261005', EXP / 'vl_vv_v2_results_20261005'
HIST = {'p014_wan21': EXP / 'vl_vv_multimodel_first200_run02/wan21/priority_014_MTYQT6fSzaE_s00091_n4_clean_v2/attempt_01/results',
        'p069_wan21': EXP / 'vl_vv_multimodel_first200_run02/wan21/priority_069_pwSkfvXD_ug_s00037_n4_clean_v2/attempt_01/results'}
V2_BASE = {'p014_wan21': OLD_NEW / 'runs/v2', 'p069_wan21': RESULTS / 'runs/v2'}
COST_KEYS = ('uncached_input_tokens', 'cached_input_tokens', 'output_tokens', 'estimated_usd')


def read(path):
    return json.loads(Path(path).read_text())


def review_paths(case, run_key):
    """{review name: issue_review/result.json} for one (case, 'version/run') key."""
    version, run = run_key.split('/')
    if version == 'v1':
        if run == 'hist':
            return {'v1': HIST[case] / 'issue_review/result.json'}
        if run.startswith('rerun_') and case == 'p014_wan21':
            return {'v1': OLD_NEW / 'runs/v1' / run / case / 'issue_review/result.json'}
        return {'v1': RUNS / 'labeling' / f'v1_{run}' / case / 'issue_review/result.json'}
    if version == 'v2':
        if run.startswith('run_'):
            return {'v2': V2_BASE[case] / run / case / 'issue_review/result.json',
                    'v4': RUNS / 'fixed/v4_1' / run / case / 'issue_review/result.json'}
        return {'v2': RUNS / 'labeling' / run / case / 'issue_review/result.json',
                'v4': RUNS / 'fresh_v4/v4_1' / run / case / 'issue_review/result.json'}
    return {'v4': RUNS / 'split' / run / case / 'issue_review/result.json'}


def v1_issues(result):
    for bucket, rows in (('V-L', result['v_l_inconsistencies']), ('V-V within', result['v_v_inconsistencies']['within_shot']),
                         ('V-V cross', result['v_v_inconsistencies']['cross_shot'])):
        for issue in rows:
            yield bucket, issue


def describe(case, run_key, issue_ids):
    """Labels and verdicts of the matched issues of one run."""
    paths = review_paths(case, run_key)
    rows = []
    if run_key.startswith('v1/'):
        issues = {i['issue_id']: (b, i) for b, i in v1_issues(read(paths['v1']))}
        for iid in issue_ids:
            bucket, issue = issues[iid]
            rows.append(dict(issue_id=iid, labels=[bucket], related=[], scope=issue['scope_shot_ids'],
                             description=issue['description'], verdicts={bucket: {'v1': issue['review']['verdict']}}))
        return rows
    reviews = {name: {i['issue_id']: i for i in read(path)['issues']} for name, path in paths.items()}
    first = next(iter(reviews.values()))
    for iid in issue_ids:
        issue = first[iid]
        labels, verdicts = [], {}
        for label in ('v_l', 'v_v'):
            if issue[label] is None:
                continue
            name = 'V-L' if label == 'v_l' else ('V-V within' if issue['v_v']['scope'] == 'within_shot' else 'V-V cross')
            labels.append(name)
            verdicts[name] = {review: reviews[review][iid]['review'][f'{label}_review']['verdict'] for review in reviews}
        rows.append(dict(issue_id=iid, labels=labels, related=issue.get('related_issue_ids', []), scope=issue['scope_shot_ids'],
                         description=issue['description'], verdicts=verdicts))
    return rows


def labeling():
    data = read(HERE / 'labeling_matches.json')
    out = {}
    for problem, runs in data['matches'].items():
        case = data['problems'][problem]['case']
        out[problem] = dict(data['problems'][problem], runs={key: describe(case, key, ids) for key, ids in runs.items()})
    return out


def shape(rows):
    """How a run reported the problem: none, V-L only, V-V only, dual (one issue, both labels) or pair (linked issues)."""
    if not rows:
        return 'not reported'
    labels = {label.split()[0] for row in rows for label in row['labels']}
    if any(len(row['labels']) == 2 for row in rows):
        return 'one issue, both labels'
    if labels == {'V-L', 'V-V'}:
        linked = any(row['related'] for row in rows)
        return 'linked pair' if linked else 'separate V-V and V-L issues'
    return 'V-L only' if labels == {'V-L'} else 'V-V only'


TARGETS = [('E1', 'p014_wan21', 'run_c', 'I1', OLD_NEW), ('E2', 'p069_wan21', 'run_a', 'I2', RESULTS),
           ('E3', 'p069_wan21', 'run_b', 'I3', RESULTS), ('E5', 'p069_wan21', 'run_c', 'I2', RESULTS),
           ('I5', 'p068_holocine', 'run_a', 'I5', OLD_NEW)]


def fixed():
    out = {}
    for name, case, run, iid, base in TARGETS:
        paths = {'v2_1': base / 'runs/v2' / run / case / 'issue_review/result.json',
                 'v2_2': EXP / 'vl_vv_partial_review_20261006/runs_v2_repeat' / run / case / 'issue_review/result.json',
                 'v3': EXP / 'vl_vv_partial_review_20261006/runs' / run / case / 'issue_review/result.json'}
        if case == 'p068_holocine':
            paths['v2_2'] = RUNS / 'fixed/v2_2' / run / case / 'issue_review/result.json'
        paths['v2_3'] = RUNS / 'fixed/v2_3' / run / case / 'issue_review/result.json'
        for k in (1, 2, 3):
            paths[f'v4_{k}'] = RUNS / f'fixed/v4_{k}' / run / case / 'issue_review/result.json'
        entry = dict(case=case, run=run, issue_id=iid, labels={})
        for review, path in paths.items():
            if not path.is_file():
                continue
            issue = next(i for i in read(path)['issues'] if i['issue_id'] == iid)
            entry['description'] = issue['description']
            for label in ('v_l', 'v_v'):
                value = issue['review'][f'{label}_review']
                if value is not None:
                    entry['labels'].setdefault(label, {})[review] = dict(verdict=value['verdict'], assessment=value['assessment'])
        out[name] = entry
    return out


def paired_vl():
    reasons = read(HERE / 'vl_rejection_reasons.json')
    cases = ('p002_wan21', 'p014_wan21', 'p028_wan22', 'p069_wan21')
    groups = {'v2_dual': [], 'v3_split': []}
    for case in cases:
        for run in ('run_a', 'run_b', 'run_c'):
            groups['v2_dual'].append((f'{case} {run}', RUNS / 'fixed/v4_1' / run / case / 'issue_review/result.json'))
    for case in ('p014_wan21', 'p069_wan21'):
        for k in (1, 2, 3):
            groups['v2_dual'].append((f'{case} v2fresh_{k}', RUNS / f'fresh_v4/v4_1/fresh_{k}' / case / 'issue_review/result.json'))
    for case in cases:
        for k in (1, 2, 3):
            groups['v3_split'].append((f'{case} split_{k}', RUNS / f'split/fresh_{k}' / case / 'issue_review/result.json'))
    out = {}
    for group, runs in groups.items():
        verdicts, causes, unpaired = Counter(), Counter(), Counter()
        for name, path in runs:
            for issue in read(path)['issues']:
                if issue['v_l'] is None:
                    continue
                paired = issue['v_v'] is not None if group == 'v2_dual' else bool(issue['related_issue_ids'])
                verdict = issue['review']['v_l_review']['verdict']
                if not paired:
                    unpaired[verdict] += 1
                    continue
                verdicts[verdict] += 1
                if verdict != 'confirmed':
                    causes[reasons[group][f'{name} {issue["issue_id"]}']] += 1
        out[group] = dict(runs=len(runs), paired_v_l=dict(verdicts), rejection_causes=dict(causes), unpaired_v_l=dict(unpaired))
    return out


def costs():
    total = Counter()
    calls = 0
    for path in sorted(RUNS.rglob('result.json')):
        if path.parent.name not in ('issue_discovery', 'issue_review', 'episode_scoring'):
            continue
        result = read(path)
        token_cost = result.get('review_run', {}).get('token_cost') or result.get('token_cost')
        if not token_cost:
            continue
        calls += result.get('review_run', {}).get('calls') or result.get('calls') or 0
        for key in COST_KEYS:
            total[key] += token_cost[key]
    total['estimated_usd'] = round(total['estimated_usd'], 6)
    return dict(calls=calls, **total,
                pricing_basis='GPT-6 Luna standard API estimate: USD 0.10/M uncached input, 0.01/M cached input, 0.50/M output; '
                              'estimate, not billed amount.')


def main():
    result = dict(labeling=labeling(), fixed=fixed(), paired_v_l=paired_vl(), cost=costs())
    result['labeling_shapes'] = {p: {k: shape(rows) for k, rows in v['runs'].items()} for p, v in result['labeling'].items()}
    (HERE / 'analysis.json').write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n')
    for problem, runs in result['labeling'].items():
        print(problem, runs['title'])
        for key, rows in runs['runs'].items():
            verdicts = '; '.join(f'{row["issue_id"]} ' + ', '.join(f'{label}: ' + '/'.join(f'{r}={v}' for r, v in vv.items())
                                                                    for label, vv in row['verdicts'].items()) for row in rows)
            print(f'  {key:12s} {result["labeling_shapes"][problem][key]:24s} {verdicts}')
    for name, entry in result['fixed'].items():
        for label, reviews in entry['labels'].items():
            print(name, label, ' '.join(f'{r}={v["verdict"][:4]}' for r, v in reviews.items()))
    print(json.dumps(result['paired_v_l'], indent=1))
    print(json.dumps(result['cost'], indent=1))


if __name__ == '__main__':
    main()
