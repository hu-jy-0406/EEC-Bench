"""Share of confirmed (and confirmed+uncertain) issues with an unspecified subject entity, per arm (v3, C, C+plug-in),
for V-V, V-L and both together; writes unspecified_share.json."""
import json, collections, sys
from pathlib import Path
sys.path.insert(0, '.')
import summarize_full as sf
EXP = sf.EXP
v3 = {}
for path in (sf.V3 / 'runs').glob('*/progress.json'):
    for tid, t in sf.read(path)['tasks'].items():
        if t.get('status') == 'success':
            v3[tid] = Path(t['output_dir'])
def counts(review, verdicts=('confirmed',)):
    r = sf.read(review)
    labels = {e['entity_key']: e.get('label') for e in r.get('entities') or []}
    us = [u for u in r['units'] if u['verdict'] in verdicts]
    un = [u for u in us if any(labels.get(x['entity_key']) == 'unspecified' for x in u.get('entity_refs') or [] if x.get('role') == 'subject')]
    return len(us), len(un)
tot = collections.defaultdict(collections.Counter)
for base in sorted((EXP / 'runs').iterdir()):
    t = base.name; m = t.split('__')[1]
    src = {'v3': (v3[t] / 'vl_review/result.json', v3[t] / 'vv_review/result.json'),
           'c': (base / 'results/vl_review/result.json', base / 'results/vv_review/result.json'),
           'cw': (base / 'results/vl_review/result.json', base / 'results_with/vv_review/result.json')}
    for arm, (vl, vv) in src.items():
        for kind, path in (('vl', vl), ('vv', vv)):
            for name, verd in (('conf', ('confirmed',)), ('cu', ('confirmed', 'uncertain'))):
                n, u = counts(path, verd)
                for key in (m, 'all'):
                    tot[(key, arm)][f'{kind}_{name}'] += n; tot[(key, arm)][f'{kind}_{name}_uns'] += u
out = {f'{k[0]}|{k[1]}': dict(v) for k, v in tot.items()}
json.dump(out, open(sys.argv[1], 'w'), indent=1)
for k, v in sorted(tot.items()):
    for name in ('conf', 'cu'):
        vv, vvu, vl, vlu = v[f'vv_{name}'], v[f'vv_{name}_uns'], v[f'vl_{name}'], v[f'vl_{name}_uns']
        print(k, name, f'VV {vvu}/{vv}={100*vvu/vv:.2f}%', f'VL {vlu}/{vl}', f'all {vvu+vlu}/{vv+vl}={100*(vvu+vlu)/(vv+vl):.2f}%')
