#!/usr/bin/env python3
"""Detected issues involving prompt-unbound entities: previous chains vs the branch chain, same videos.

Measure A (all chains): the issue cites a detector-ledger prompt_unbound entity (ge...) in entity_ids
or witness entity_ids, or (branch chain) an added entity labeled prompt_unbound.
Measure B needs reading: listing.md prints every earlier V-V-labeled issue with its entity names
for the assistant's classification under the branch chain's definition (unbound_judgments.json).
"""
import json
from pathlib import Path

import run_jobs

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
OLD_NEW = ['p002_wan21', 'p014_wan21', 'p014_storymem', 'p028_wan22', 'p047_wan21']
RESULTS = ['p032_wan22', 'p047_storymem', 'p069_wan21']
V45 = ['p002_wan21', 'p014_wan21', 'p028_wan22', 'p069_wan21']


def ledger(case):
    return json.loads((run_jobs.case_dir(case) / 'episode_entities.json').read_text())


def old_runs():
    for case in OLD_NEW + RESULTS:
        base = EXP / ('vl_vv_old_vs_new_20261005' if case in OLD_NEW else 'vl_vv_v2_results_20261005') / 'runs/v2'
        for run in ('run_a', 'run_b', 'run_c'):
            yield 'v2_chain', case, run, base / run / case / 'issue_discovery/result.json'
    for case in V45:
        for k in (1, 2, 3):
            yield 'v4_v5_chain', case, f'fresh_{k}', EXP / f'vl_vv_entity_scope_20261006/runs/pipeline/fresh_{k}/{case}/issue_discovery/result.json'


def main():
    out, lines = {}, []
    names = {}
    for chain, case, run, path in old_runs():
        led = ledger(case)
        ge = {e['global_entity_id'] for e in led['prompt_unbound']}
        names[case] = {e['global_entity_id']: e['name'] for part in ('prompt_bound', 'prompt_unbound') for e in led[part]}
        stats = out.setdefault(chain, dict(issues=0, v_v_issues=0, v_l_only_issues=0, cite_ge=0, v_v_cite_ge=0, cases=set()))
        stats['cases'].add(case)
        for issue in json.loads(path.read_text())['issues']:
            keys = set(issue['entity_ids']) | {k for ev in issue['key_evidence'] for k in ev['entity_ids']}
            stats['issues'] += 1
            hit = bool(keys & ge)
            stats['cite_ge'] += hit
            if issue['v_v'] is not None:
                stats['v_v_issues'] += 1
                stats['v_v_cite_ge'] += hit
                ents = ', '.join(f'{k}={names[case].get(k, k)}' for k in issue['entity_ids'])
                lines.append(f'- {chain} {case} {run} {issue["issue_id"]} [{issue["v_v"]["scope"]}/{issue["v_v"]["subcategory"]}] '
                             f'ents: {ents or "-"} | {issue["description"][:220]}')
            else:
                stats['v_l_only_issues'] += 1
    new = dict(issues=0, v_v_issues=0, cite_ge=0, v_v_cite_ge=0, v_v_text_unbound=0, cases=set())
    for run in sorted(p for p in (HERE / 'runs/main').glob('run_*/*') if p.is_dir()):
        ge = {e['global_entity_id'] for e in ledger(run.name)['prompt_unbound']}
        new['cases'].add(run.name)
        for b in ('vl', 'vv'):
            d = json.loads((run / f'{b}_detection/result.json').read_text())
            prov = {e['entity_key']: e['provenance'] for e in d['entities']}
            for issue in d['issues']:
                keys = {r['entity_key'] for r in issue['entity_refs']} | {k for ev in issue['key_evidence'] for k in ev['entity_keys']}
                new['issues'] += 1
                new['cite_ge'] += bool(keys & ge)
                if b == 'vv':
                    new['v_v_issues'] += 1
                    new['v_v_cite_ge'] += bool(keys & ge)
                    new['v_v_text_unbound'] += any(prov.get(r['entity_key']) == 'prompt_unbound'
                                                   for r in issue['entity_refs'] if r['role'] == 'subject')
    out['branch_chain'] = new
    for value in out.values():
        value['cases'] = sorted(value['cases'])
    (HERE / 'unbound_compare.json').write_text(json.dumps(out, indent=2) + '\n')
    (HERE / 'unbound_compare_listing.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != 'cases'} for k, v in out.items()}, indent=1))


if __name__ == '__main__':
    main()
