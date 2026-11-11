#!/usr/bin/env python3
"""Upper bound for 'walls/floors as entities': confirmed V-V issues in this run (all finished videos) whose subjects
include a contract place (location) and no other specified subject, by subcategory; compared with all confirmed
V-V issues and those already counted unspecified."""
import json, collections
from pathlib import Path
EXP = Path(__file__).resolve().parent
tot = collections.Counter(); sub = collections.Counter()
for path in (EXP / 'runs').glob('*/progress.json'):
    for tid, s in json.loads(path.read_text())['tasks'].items():
        if s.get('status') != 'success':
            continue
        out = Path(s['output_dir']); case = Path(s['case_dir'])
        role = {k: v.get('label') for k, v in (json.loads((case / 'contract.json').read_text()).get('entity_descriptions') or {}).items()}
        rv = json.loads((out / 'vv_review/result.json').read_text())
        pe = {e['entity_key']: str(e.get('prompt_entity_id')) for e in rv.get('entities') or [] if isinstance(e, dict)}
        sc = json.loads((out / 'episode_scoring/result.json').read_text())
        units = {u['unit_id']: u for u in rv['units']}
        tot['videos'] += 1
        for u in sc['unit_scores']:
            if u['bucket'] == 'v_l' or u['verdict'] != 'confirmed':
                continue
            tot['vv_confirmed'] += 1
            subs = u.get('subject_entities') or []
            labels = {x['label'] for x in subs}
            if 'unspecified' in labels:
                tot['already_unspecified'] += 1
                continue
            roles = [role.get(pe.get(x['entity_key'])) for x in subs]
            if subs and all(r == 'location' for r in roles):
                tot['place_only_subject'] += 1
                sub[units[u['unit_id']]['subcategory']] += 1
print(dict(tot)); print(dict(sub))
