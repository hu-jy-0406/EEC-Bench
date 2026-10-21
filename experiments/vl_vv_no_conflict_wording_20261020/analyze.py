#!/usr/bin/env python3
"""Compare V-L verdicts per candidate: original (2026-10-09), old-wording repeat, new wording."""
import collections, glob, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPLIT = HERE.parents[0] / 'vl_vv_branch_split_20261009/runs/main'
sys.path.insert(0, str(HERE.parents[0] / 'vl_vv_branch_split_20261009'))
from run_jobs import CASES  # noqa: E402

def load(path):
    r = json.load(open(path))
    cand, bases = {}, collections.Counter()
    for u in r['units']:
        cid = u['unit_id'].split('.')[0]
        cand.setdefault(cid, []).append(u['verdict'])
        bases[(u['verdict'], u.get('basis'))] += 1
    state = {c: ('confirmed' if 'confirmed' in v else 'uncertain' if 'uncertain' in v else 'rejected') for c, v in cand.items()}
    return state, bases, len(r['units'])

arms = {'original': lambda run, key: SPLIT / run / key / 'vl_review/result.json',
        'old_repeat': lambda run, key: HERE / 'runs/old' / run / key / 'vl_review/result.json',
        'new': lambda run, key: HERE / 'runs/new' / run / key / 'vl_review/result.json'}
states = {a: {} for a in arms}; bases = {a: collections.Counter() for a in arms}; units = collections.Counter()
for run in ('run_a', 'run_b'):
    for key in CASES:
        for a, f in arms.items():
            s, b, n = load(f(run, key))
            states[a].update({(run, key, c): v for c, v in s.items()}); bases[a] += b; units[a] += n
keys = sorted(states['original'])
assert all(set(states[a]) == set(keys) for a in arms)
out = dict(candidates=len(keys), units=dict(units))
for a in arms:
    out[a] = dict(collections.Counter(states[a][k] for k in keys)), {f'{v}/{b}': n for (v, b), n in sorted(bases[a].items())}
def flips(x, y):
    return [dict(run=k[0], case=k[1], candidate=k[2], **{x: states[x][k], y: states[y][k]}) for k in keys if states[x][k] != states[y][k]]
out['flips_original_vs_old_repeat'] = flips('original', 'old_repeat')
out['flips_original_vs_new'] = flips('original', 'new')
out['flips_old_repeat_vs_new'] = flips('old_repeat', 'new')
json.dump(out, open(HERE / 'analysis.json', 'w'), indent=2)
print(json.dumps({k: v for k, v in out.items() if not k.startswith('flips')}, indent=1))
for k in ('flips_original_vs_old_repeat', 'flips_original_vs_new', 'flips_old_repeat_vs_new'):
    print(k, len(out[k]))
    for f in out[k]: print('   ', f)
