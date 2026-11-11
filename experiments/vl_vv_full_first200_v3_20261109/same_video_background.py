#!/usr/bin/env python3
"""For given reuse tasks: confirmed setting/background V-V issues in the new run, with subject keys/names."""
import json, sys
from pathlib import Path
EXP = Path(__file__).resolve().parent
want = set(sys.argv[1:])
for path in sorted((EXP / 'runs').glob('*/progress.json')):
    for tid, st in json.loads(path.read_text())['tasks'].items():
        if tid not in want or st.get('status') != 'success':
            continue
        out = Path(st['output_dir'])
        rv = json.loads((out / 'vv_review/result.json').read_text())
        nm = {e['entity_key']: e.get('name') for e in rv.get('entities') or [] if isinstance(e, dict)}
        for u in rv['units']:
            if u['verdict'] == 'confirmed' and u['subcategory'] in ('setting_background', 'background_drift'):
                subs = [r['entity_key'] for r in u.get('entity_refs') or [] if r.get('role') == 'subject']
                print(tid, [(k, (nm.get(k) or '')[:30]) for k in subs], '|', u['description'][:120])
