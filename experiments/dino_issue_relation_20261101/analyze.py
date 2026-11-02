"""Does a low DINO appearance score go with confirmed appearance issues? (offline, no model calls)"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

OUT = Path(sys.argv[1])
rows = [r for r in json.loads((OUT / 'entities.json').read_text()) if r['dino'] is not None]
rng = np.random.default_rng(0)


def confirmed(r, scopes):
    return any(i['verdict'] == 'confirmed' and i['sub'] == 'appearance' and i['scope'] in scopes for i in r['issues'])


def auc(pos, neg):
    """P(score of a positive < score of a negative): low DINO predicts an issue."""
    if not len(pos) or not len(neg):
        return None
    both = np.concatenate([pos, neg])
    ranks = both.argsort().argsort() + 1.0
    # average ranks for ties
    order = np.sort(both)
    _, inv, counts = np.unique(both, return_inverse=True, return_counts=True)
    first = np.cumsum(counts) - counts + 1
    ranks = (first + (counts - 1) / 2.0)[inv]
    r_neg = ranks[len(pos):].sum()
    return float((r_neg - len(neg) * (len(neg) + 1) / 2) / (len(pos) * len(neg)))


def within_group_auc(items, key):
    """Pairs compared only inside the same group (same run and category)."""
    groups = defaultdict(lambda: ([], []))
    for score, label, g in items:
        groups[g][0 if label else 1].append(score)
    num = den = 0.0
    for pos, neg in groups.values():
        if pos and neg:
            p, n = np.array(pos), np.array(neg)
            num += (p[:, None] < n[None, :]).sum() + 0.5 * (p[:, None] == n[None, :]).sum()
            den += len(p) * len(n)
    return (num / den if den else None), int(den)


def boot(items, n=500):
    """Cluster bootstrap over runs (episode x model)."""
    by = defaultdict(list)
    for x in items:
        by[x[3]].append(x)
    keys = list(by)
    vals = []
    for _ in range(n):
        pick = rng.choice(len(keys), len(keys))
        s = [x for k in pick for x in by[keys[k]]]
        pos = np.array([x[0] for x in s if x[1]]); neg = np.array([x[0] for x in s if not x[1]])
        a = auc(pos, neg)
        if a is not None:
            vals.append(a)
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def analysis(name, positive_scopes, exclude_scopes, subset):
    items = []
    for r in subset:
        pos = confirmed(r, positive_scopes)
        if not pos and confirmed(r, exclude_scopes):
            continue
        run = (r['run'], r['episode'], r['model'])
        items.append((r['dino'], pos, (run, r['category']), run))
    pos = np.array([x[0] for x in items if x[1]]); neg = np.array([x[0] for x in items if not x[1]])
    w, pairs = within_group_auc([(x[0], x[1], x[2]) for x in items], None)
    q10 = np.percentile([x[0] for x in items], 10)
    low = [x for x in items if x[0] <= q10]
    res = dict(analysis=name, n=len(items), positives=int(len(pos)), base_rate=len(pos) / len(items) if items else None,
               auc=auc(pos, neg), auc_ci95=boot(items) if len(pos) >= 20 else None,
               within_run_category_auc=w, within_pairs=pairs,
               mean_dino_pos=float(pos.mean()) if len(pos) else None, mean_dino_neg=float(neg.mean()) if len(neg) else None,
               rate_in_lowest_decile=sum(x[1] for x in low) / len(low) if low else None)
    return res


VV = {'within_shot', 'cross_shot'}
ALL = VV | {'v_l'}
multi = [r for r in rows if r['n_shots'] >= 2]
results = []
for label, pos_scopes, excl in [('V-V appearance (cross or within)', VV, {'v_l'}),
                                ('any confirmed appearance (V-L or V-V)', ALL, set())]:
    results.append(analysis(label + ' | all entities', pos_scopes, excl, rows))
    results.append(analysis(label + ' | entities in >=2 shots', pos_scopes, excl, multi))
    for cat in ('characters', 'places', 'objects', 'unbound'):
        results.append(analysis(f'{label} | {cat}, >=2 shots', pos_scopes, excl, [r for r in multi if r['category'] == cat]))

# DINO of candidate issues: confirmed vs rejected V-V appearance candidates (mean DINO of their entities)
cand = defaultdict(list)
for r in rows:
    for i in r['issues']:
        if i['sub'] == 'appearance' and i['scope'] in VV and i['verdict'] in ('confirmed', 'rejected'):
            cand[i['verdict']].append(r['dino'])
results.append(dict(analysis='V-V appearance candidates: entity DINO by review verdict',
                    confirmed_n=len(cand['confirmed']), confirmed_mean=float(np.mean(cand['confirmed'])) if cand['confirmed'] else None,
                    rejected_n=len(cand['rejected']), rejected_mean=float(np.mean(cand['rejected'])) if cand['rejected'] else None,
                    auc_rejected_lower=auc(np.array(cand['rejected']), np.array(cand['confirmed']))))

(OUT / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=1))
for r in results:
    print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()}, ensure_ascii=False))
