"""Extra controls: same shot count; same contract entity across the five generation models."""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

OUT = Path(sys.argv[1])
rows = [r for r in json.loads((OUT / 'entities.json').read_text()) if r['dino'] is not None and r['n_shots'] >= 2]
VV = {'within_shot', 'cross_shot'}


def label(r):
    pos = any(i['verdict'] == 'confirmed' and i['sub'] == 'appearance' and i['scope'] in VV for i in r['issues'])
    vl_only = any(i['verdict'] == 'confirmed' and i['sub'] == 'appearance' and i['scope'] == 'v_l' for i in r['issues'])
    return None if (not pos and vl_only) else pos


def grouped_auc(key):
    groups = defaultdict(lambda: ([], []))
    for r in rows:
        y = label(r)
        if y is None:
            continue
        groups[key(r)][0 if y else 1].append(r['dino'])
    num = den = 0.0
    for pos, neg in groups.values():
        if pos and neg:
            p, n = np.array(pos), np.array(neg)
            num += (p[:, None] < n[None, :]).sum() + 0.5 * (p[:, None] == n[None, :]).sum()
            den += len(p) * len(n)
    return dict(auc=round(num / den, 3) if den else None, pairs=int(den),
                groups_with_both=sum(1 for p, n in groups.values() if p and n))


out = {
    'same shot count': grouped_auc(lambda r: r['n_shots']),
    'same shot count and category': grouped_auc(lambda r: (r['n_shots'], r['category'])),
    'same contract entity across models (pb, same episode)': grouped_auc(
        lambda r: (r['episode'], r['gid']) if r['partition'] == 'prompt_bound' else id(r)),
    'same episode and category across models': grouped_auc(lambda r: (r['episode'], r['category'])),
    'same model and category': grouped_auc(lambda r: (r['model'], r['category'])),
}
per_model = defaultdict(lambda: [[], 0])
for r in rows:
    per_model[r['model']][0].append(r['dino'])
    per_model[r['model']][1] += bool(label(r))
out['per model (entities in >=2 shots)'] = {m: dict(mean_dino=round(float(np.mean(v[0])), 3), n=len(v[0]),
                                                    vv_appearance_rate=round(v[1] / len(v[0]), 3)) for m, v in per_model.items()}
(OUT / 'controls.json').write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(json.dumps(out, ensure_ascii=False, indent=1))
