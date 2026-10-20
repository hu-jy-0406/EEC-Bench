#!/usr/bin/env python3
"""Normalize old (v1) and new (v2) run outputs of the selected cases into runs.json (offline)."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HISTORICAL = [ROOT / 'experiments/vl_vv_multimodel_first200_run02/final_scores.jsonl',
              ROOT / 'experiments/vl_vv_multimodel_first200_run02_b/final_scores.jsonl']
PRICE = dict(uncached=0.10, cached=0.01, output=0.50)
BUCKET = {'v_l_inconsistencies': 'V-L', 'within_shot': 'V-V within', 'cross_shot': 'V-V cross'}


def read(path):
    return json.loads(Path(path).read_text())


def usd(rows):
    inp = sum(int(r.get('input_tokens', 0)) for r in rows)
    cached = sum(int(r.get('cached_input_tokens', 0)) for r in rows)
    out = sum(int(r.get('output_tokens', 0)) for r in rows)
    return dict(calls=len(rows), input=inp, cached=cached, output=out,
                usd=round((inp - cached) / 1e6 * PRICE['uncached'] + cached / 1e6 * PRICE['cached'] + out / 1e6 * PRICE['output'], 6))


def stage_usage(out):
    rows = []
    for stage in ('issue_discovery', 'issue_review', 'episode_scoring'):
        audit = out / stage / 'call_repair_audit.json'
        if audit.is_file():
            rows += read(audit).get('usage', [])
        else:  # pre-repair-loop historical runs record usage in the result
            result = read(out / stage / 'result.json')
            rows += (result.get('review_run', {}).get('usage') if stage == 'issue_review' else result.get('usage')) or []
    return rows


def v1_issues(out):
    reviewed = read(out / 'issue_review/result.json')
    scoring = read(out / 'episode_scoring/result.json')
    sev = {row['issue_id']: row for row in scoring['issue_scores']}
    issues = []
    for key, rows in (('v_l_inconsistencies', reviewed['v_l_inconsistencies']),
                      ('within_shot', reviewed['v_v_inconsistencies']['within_shot']),
                      ('cross_shot', reviewed['v_v_inconsistencies']['cross_shot'])):
        for issue in rows:
            s = sev.get(issue['issue_id'], {})
            issues.append(dict(issue_id=issue['issue_id'], description=issue['description'], scope=issue['scope_shot_ids'],
                               labels=[dict(label=BUCKET[key], subcategory=issue['subcategory'],
                                            verdict=issue['review']['verdict'], confidence=issue['review']['confidence'],
                                            severity=s.get('severity'), deduction=s.get('adjusted_deduction'))],
                               quotes=[q['quote'] for q in issue['prompt_evidence']]))
    return issues, scoring


def v2_issues(out):
    reviewed = read(out / 'issue_review/result.json')
    scoring = read(out / 'episode_scoring/result.json')
    sev = {(row['issue_id'], row['label']): row for row in scoring['issue_scores']}
    issues = []
    for issue in reviewed['issues']:
        labels = []
        if issue['v_l']:
            s = sev[(issue['issue_id'], 'v_l')]
            r = issue['review']['v_l_review']
            labels.append(dict(label='V-L', subcategory=issue['v_l']['subcategory'], verdict=r['verdict'],
                               confidence=r['confidence'], severity=s['severity'], deduction=s['adjusted_deduction']))
        if issue['v_v']:
            s = sev[(issue['issue_id'], 'v_v')]
            r = issue['review']['v_v_review']
            labels.append(dict(label='V-V within' if issue['v_v']['scope'] == 'within_shot' else 'V-V cross',
                               subcategory=issue['v_v']['subcategory'], verdict=r['verdict'], confidence=r['confidence'],
                               severity=s['severity'], deduction=s['adjusted_deduction']))
        issues.append(dict(issue_id=issue['issue_id'], description=issue['description'], scope=issue['scope_shot_ids'],
                           labels=labels, checklist_items=issue['checklist_items'],
                           quotes=[q['quote'] for q in (issue['v_l'] or {}).get('prompt_evidence', [])]))
    return issues, scoring


def scores(scoring):
    s = scoring['scores']
    return dict(v_l=s['v_l'], within=s['v_v']['within_shot'], cross=s['v_v']['cross_shot'], v_v=s['v_v']['overall'])


def main():
    ref = read(HERE / 'reference.json')
    hist = {}
    for path in HISTORICAL:
        for line in path.read_text().splitlines():
            row = json.loads(line)
            hist[(row['generation_priority'], row['model_id'])] = Path(row['output_dir'])
    result = {}
    for case in ref['cases']:
        key = case['key']
        runs = []
        sources = [('v1', 'historical', hist[(case['priority'], case['model'])])]
        sources += [('v1', rid, HERE / 'runs/v1' / rid / key) for rid in ('rerun_a', 'rerun_b')]
        sources += [('v2', rid, HERE / 'runs/v2' / rid / key) for rid in ('run_a', 'run_b', 'run_c')]
        for protocol, run_id, out in sources:
            if not (out / 'episode_scoring/result.json').is_file():
                runs.append(dict(protocol=protocol, run_id=run_id, status='missing', output=str(out)))
                continue
            issues, scoring = (v1_issues if protocol == 'v1' else v2_issues)(out)
            runs.append(dict(protocol=protocol, run_id=run_id, status='success', output=str(out),
                             scoring_protocol=scoring['protocol'], scores=scores(scoring), issues=issues,
                             usage=usd(stage_usage(out))))
        result[key] = runs
    (HERE / 'runs.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    for key, runs in result.items():
        print(key, [(r['protocol'], r['run_id'], r['status'], r.get('scores')) for r in runs])


if __name__ == '__main__':
    main()
