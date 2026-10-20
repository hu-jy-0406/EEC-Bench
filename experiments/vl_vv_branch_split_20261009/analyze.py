#!/usr/bin/env python3
"""Summarize the live validation runs of the branch-separated chain.

Writes analysis.json (per-run status, timing, repair rounds, tokens and USD per stage,
scores, V-V unintentional-entity statistics, verdict and basis counts, artifact matches)
and units_for_matching.md (every detected issue and reviewed unit, for the assistant's
matching against experiments/vl_vv_v2_results_20261005/results_reference.json).
Matches live in matches.json: {case: {run: {artifact_id: [unit or issue IDs]}}}.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REFERENCE = ROOT / 'experiments/vl_vv_v2_results_20261005/results_reference.json'
STAGES = ('vl_detection', 'vv_detection', 'vl_review', 'vv_review', 'episode_scoring')


def read(path):
    return json.loads(Path(path).read_text())


def run_dirs():
    """Pipeline run folders: main, both smoke sets and the stopped first-template runs."""
    patterns = ('main/run_*/*/run.json', 'main_pre_element_gate/run_*/*/run.json', 'smoke/*/run.json',
                'smoke2/*/run.json', 'main_template_v1/run_*/*/run.json')
    for pattern in patterns:
        for path in sorted((HERE / 'runs').glob(pattern)):
            if read(path).get('protocol') == 'vl_vv_pipeline_v1':
                yield path.parent


def repair_rounds(stage_dir):
    rounds = {}
    for audit in sorted(stage_dir.glob('*_repair_audit.json')):
        value = read(audit)
        rounds[audit.name.replace('_repair_audit.json', '')] = dict(
            repair_rounds=value.get('repair_rounds'), errors_per_round=[r['error_count'] for r in value['rounds']])
    return rounds


def summarize(run):
    state = read(run / 'run.json')
    if state['status'] == 'running':
        state = dict(state, status='stopped')
    row = dict(run=str(run.relative_to(HERE)), case=run.name, status=state['status'],
               wall_seconds=round(state.get('seconds', 0), 1),
               stage_seconds={r['name']: round(r['seconds'], 1) for r in state.get('stage_results', [])})
    if state['status'] != 'success':
        row['error'] = state.get('error')
        return row
    costs = {stage: read(run / stage / 'run.json').get('token_cost') for stage in STAGES}
    row['token_cost'] = costs
    row['total'] = {key: sum((cost or {}).get(key, 0) for cost in costs.values())
                    for key in ('uncached_input_tokens', 'cached_input_tokens', 'output_tokens', 'api_calls',
                                'estimated_usd')}
    row['total']['estimated_usd'] = round(row['total']['estimated_usd'], 6)
    row['repairs'] = {stage: repair_rounds(run / stage) for stage in STAGES}
    det = {b: read(run / f'{b}_detection/result.json') for b in ('vl', 'vv')}
    rev = {b: read(run / f'{b}_review/result.json') for b in ('vl', 'vv')}
    score = read(run / 'episode_scoring/result.json')
    row['detection_counts'] = {b: det[b]['counts'] for b in det}
    row['review_counts'] = {b: rev[b]['counts'] for b in rev}
    row['scores'] = score['scores']
    row['v_v_issue_statistics'] = score['v_v_issue_statistics']
    row['unit_counts'] = score['counts']
    return row


def listing(run):
    lines = [f'## {run.relative_to(HERE)}']
    if read(run / 'run.json')['status'] != 'success':
        return lines + ['FAILED']
    entities = {}
    for b in ('vl', 'vv'):
        for e in read(run / f'{b}_detection/result.json')['entities']:
            entities[e['entity_key']] = e['name']
    severities = {u['unit_id']: u['severity'] for u in read(run / 'episode_scoring/result.json')['unit_scores']}
    for b in ('vl', 'vv'):
        review = read(run / f'{b}_review/result.json')
        for unit in review['units']:
            ents = ', '.join(f'{entities.get(e["entity_key"], e["entity_key"])}:{e["role"][0]}'
                             + (f'/{e["provenance"]}' if e.get('provenance') else '') for e in unit['entity_refs'])
            lines.append(f'- {unit["unit_id"]} [{unit["scope"]}/{unit["subcategory"]}] {",".join(unit["shot_ids"])} '
                         f'{unit["verdict"]}/{unit["basis"]}/{unit["confidence"]} sev={severities.get(unit["unit_id"])} '
                         f'| {unit["description"]} | ents: {ents}'
                         + (' | split' if unit['split'] else '') + (f' | REV: {unit["revision_note"]}' if unit['revision'] == 'clarified' else ''))
    return lines


def artifact_summary(rows):
    path = HERE / 'matches.json'
    if not path.is_file():
        return None
    matches = read(path)
    reference = {case['key']: case for case in read(REFERENCE)['cases']}
    result = dict(per_case={}, totals=dict(artifact_runs=0, found=0, confirmed=0, control_runs=0, control_flagged=0,
                                           control_confirmed=0))
    status = {}
    for row in rows:
        if row['status'] == 'success' and row['run'].startswith('runs/main/'):
            run = HERE / row['run']
            for b in ('vl', 'vv'):
                for unit in read(run / f'{b}_review/result.json')['units']:
                    status[(row['run'], unit['unit_id'])] = unit['verdict']
    for case, runs in matches.items():
        artifacts = reference[case]['artifacts']
        per = dict(artifacts=len([a for a in artifacts if a['kind'] != 'control']), runs={})
        for run, found in runs.items():
            run_key = f'runs/main/{run}/{case}'
            entry = {}
            for art in artifacts:
                ids = found.get(art['id'], [])
                confirmed = any(status.get((run_key, uid)) == 'confirmed' for uid in ids)
                entry[art['id']] = dict(ids=ids, found=bool(ids), confirmed=confirmed)
                tot = result['totals']
                if art['kind'] == 'control':
                    tot['control_runs'] += 1
                    tot['control_flagged'] += bool(ids)
                    tot['control_confirmed'] += confirmed
                else:
                    tot['artifact_runs'] += 1
                    tot['found'] += bool(ids)
                    tot['confirmed'] += confirmed
            per['runs'][run] = entry
        result['per_case'][case] = per
    return result


def main():
    rows = [summarize(run) for run in run_dirs()]
    main_rows = [row for row in rows if row['run'].startswith('runs/main/') and row['status'] == 'success']
    aggregate = {key: round(sum(row['total'][key] for row in main_rows), 6)
                 for key in ('uncached_input_tokens', 'cached_input_tokens', 'output_tokens', 'api_calls', 'estimated_usd')}
    all_rows = [row for row in rows if row['status'] == 'success']
    pre_rows = [row for row in rows if row['run'].startswith('runs/main_pre_element_gate/') and row['status'] == 'success']
    aggregate_pre = {key: round(sum(row['total'][key] for row in pre_rows), 6)
                     for key in ('uncached_input_tokens', 'cached_input_tokens', 'output_tokens', 'api_calls', 'estimated_usd')}
    stopped = [row for row in rows if row['run'].startswith('runs/main_template_v1/')]
    aggregate_all = {key: round(sum(row['total'][key] for row in all_rows), 6)
                     for key in ('uncached_input_tokens', 'cached_input_tokens', 'output_tokens', 'api_calls', 'estimated_usd')}
    vv_stats = dict(confirmed_issues=0, involving_unintentional=0, involving_unintentional_or_uncertain=0)
    by_scope = {scope: dict(vv_stats) for scope in ('within_shot', 'cross_shot')}
    for row in main_rows:
        stats = row['v_v_issue_statistics']
        for key in vv_stats:
            vv_stats[key] += stats['total'][key]
            for scope in by_scope:
                by_scope[scope][key] += stats[scope][key]
    for block in [vv_stats, *by_scope.values()]:
        block['proportion'] = round(block['involving_unintentional'] / block['confirmed_issues'], 4) \
            if block['confirmed_issues'] else None
        block['proportion_upper_bound'] = round(block['involving_unintentional_or_uncertain'] / block['confirmed_issues'], 4) \
            if block['confirmed_issues'] else None
    output = dict(runs=rows, main_runs=len([r for r in rows if r['run'].startswith('runs/main/')]),
                  main_success=len(main_rows), main_usage=aggregate, pre_element_gate_usage=aggregate_pre,
                  all_usage_successful_runs=aggregate_all,
                  stopped_template_v1_runs=[dict(run=r['run'], status=r['status']) for r in stopped],
                  pooled_v_v_issue_statistics=dict(total=vv_stats, **by_scope),
                  artifacts=artifact_summary(rows))
    (HERE / 'analysis.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    text = []
    for run in run_dirs():
        text += listing(run) + ['']
    (HERE / 'units_for_matching.md').write_text('\n'.join(text) + '\n')
    print(json.dumps(dict(main_success=output['main_success'], main_runs=output['main_runs'], usage=aggregate,
                          pooled=output['pooled_v_v_issue_statistics']['total']), ensure_ascii=False))


if __name__ == '__main__':
    main()
