#!/usr/bin/env python3
"""Print a compact view of one validation case (discovery labels, reviews, scores)."""
import json, sys
from pathlib import Path
d = Path(sys.argv[1])
s = json.loads((d / 'episode_scoring/result.json').read_text())
r = json.loads((d / 'issue_review/result.json').read_text())
print('SCORES', s['scores'], 'labels', s.get('label_counts'), 'tokens/cost', {k: r['review_run']['token_cost'][k] for k in ('estimated_usd',)})
print('counts', r['counts'])
sev = {(x['issue_id'], x['label']): x['severity'] for x in s['issue_scores']}
for i in r['issues']:
    rv = i['review']
    lab = []
    if i['v_l']: lab.append(f"VL:{i['v_l']['subcategory']}={rv['v_l_review']['verdict']}/{sev[(i['issue_id'],'v_l')]}")
    if i['v_v']: lab.append(f"VV-{i['v_v']['scope'][:5]}:{i['v_v']['subcategory']}={rv['v_v_review']['verdict']}/{sev[(i['issue_id'],'v_v')]}")
    print(f"  {i['issue_id']} {i['scope_shot_ids']} {i['checklist_items']} | {' + '.join(lab)} | {i['description']}")
print('LEDGER')
for x in r['continuity_ledger']:
    print(f"  {x['subject_kind']} {x['entity_ids']} {x['name']}: {x['assessment']} {x['issue_ids']} | " + ' ; '.join(f"{o['shot_id']}:{o['signature']}" for o in x['observations']))
print('AUDIT', ' | '.join(f"{a['item']}:{a['status'][:3]}:{a['note'][:40]}" for a in r['checklist_audit']))
