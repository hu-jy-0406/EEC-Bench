#!/usr/bin/env python3
"""Review outcomes of the previous chains on the same videos, for comparison with the branch chain.

v2 chain (discovery v2 + review v2): 8 clip videos x 3 runs (vl_vv_old_vs_new_20261005, vl_vv_v2_results_20261005).
v4+v5 chain (discovery v4 + review v5): 4 videos x 3 runs (vl_vv_entity_scope_20261006/runs/pipeline).
Branch chain: runs/main (this experiment).  Artifact-level loss uses the assistant's reference matching.
"""
import collections
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
OLD_NEW = ['p002_wan21', 'p014_wan21', 'p014_storymem', 'p028_wan22', 'p047_wan21']
RESULTS = ['p032_wan22', 'p047_storymem', 'p069_wan21']


def label_counts(review):
    counts = collections.Counter()
    for issue in review['issues']:
        for label in ('v_l', 'v_v'):
            if issue[label] is None:
                continue
            bucket = 'v_l' if label == 'v_l' else issue['v_v']['scope']
            counts[(bucket, issue['review'][f'{label}_review']['verdict'])] += 1
    return counts


def artifact_loss(annotations, runs_root, cases, prefix='v2/'):
    found = confirmed = 0
    lost = []
    for case in cases:
        for run, row in annotations[case]['runs'].items():
            if not run.startswith(prefix):
                continue
            review = json.loads((runs_root / run.split('/')[1] / case / 'issue_review/result.json').read_text())
            by_id = {i['issue_id']: i for i in review['issues']}
            for art, ids in row['matches'].items():
                if art.startswith('C') or not ids:
                    continue
                found += 1
                ok = any(by_id[i]['review'][f'{lab}_review']['verdict'] == 'confirmed'
                         for i in ids if i in by_id for lab in ('v_l', 'v_v') if by_id[i][lab] is not None)
                confirmed += ok
                if not ok:
                    lost.append(f'{case}/{run}/{art}')
    return found, confirmed, lost


def main():
    out = {}
    v2 = collections.Counter()
    for case in OLD_NEW + RESULTS:
        base = EXP / ('vl_vv_old_vs_new_20261005' if case in OLD_NEW else 'vl_vv_v2_results_20261005') / 'runs/v2'
        for run in ('run_a', 'run_b', 'run_c'):
            v2.update(label_counts(json.loads((base / run / case / 'issue_review/result.json').read_text())))
    out['v2_chain_labels'] = {f'{b}:{v}': n for (b, v), n in sorted(v2.items())}
    v45 = collections.Counter()
    for k in (1, 2, 3):
        for case in ('p002_wan21', 'p014_wan21', 'p028_wan22', 'p069_wan21'):
            v45.update(label_counts(json.loads((EXP / f'vl_vv_entity_scope_20261006/runs/pipeline/fresh_{k}/{case}/issue_review/result.json').read_text())))
    out['v4_v5_chain_labels'] = {f'{b}:{v}': n for (b, v), n in sorted(v45.items())}
    a1 = json.loads((EXP / 'vl_vv_old_vs_new_20261005/annotations.json').read_text())
    a2 = json.loads((EXP / 'vl_vv_v2_results_20261005/results_annotations.json').read_text())
    f1 = artifact_loss(a1, EXP / 'vl_vv_old_vs_new_20261005/runs/v2', OLD_NEW)
    f2 = artifact_loss(a2, EXP / 'vl_vv_v2_results_20261005/runs/v2', RESULTS)
    out['v2_chain_artifacts'] = dict(found=f1[0] + f2[0], confirmed=f1[1] + f2[1], lost_at_review=f1[2] + f2[2])
    new = collections.Counter()
    for run in sorted(p for p in (HERE / 'runs/main').glob('run_*/*') if p.is_dir()):
        for b in ('vl', 'vv'):
            for u in json.loads((run / f'{b}_review/result.json').read_text())['units']:
                new[(u['scope'], u['verdict'])] += 1
    out['branch_chain_units'] = {f'{b}:{v}': n for (b, v), n in sorted(new.items())}
    (HERE / 'rejection_compare.json').write_text(json.dumps(out, indent=2) + '\n')
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
