#!/usr/bin/env python3
"""Confirmed V-V issues of the C + plug-in run by the kind of their subjects: contract label of each specified
subject (character / location / object) or unspecified. Zero model calls."""
import collections
import json
from pathlib import Path

RUNS = Path(__file__).resolve().parent.parent / 'vl_vv_full_first200_c_20261110' / 'runs'
kinds, sub_place = collections.Counter(), collections.Counter()
for base in sorted(RUNS.iterdir()):
    c = json.loads((base / 'case/contract.json').read_text())['entity_descriptions']
    r = json.loads((base / 'results_with/vv_review/result.json').read_text())
    ent = {e['entity_key']: e for e in r.get('entities') or []}
    for u in r['units']:
        if u['verdict'] != 'confirmed':
            continue
        ks = set()
        for x in u.get('entity_refs') or []:
            if x.get('role') != 'subject':
                continue
            e = ent.get(x['entity_key'], {})
            if e.get('label') == 'unspecified':
                ks.add('unspecified')
            else:
                ks.add(c.get(str(e.get('prompt_entity_id')), {}).get('label', 'unknown'))
        key = '+'.join(sorted(ks)) or 'no subject'
        kinds[key] += 1
        if key == 'location':
            sub_place[f"{u['scope']}:{u['subcategory']}"] += 1
print(kinds.most_common())
print('location-only by subcategory', sub_place.most_common())
