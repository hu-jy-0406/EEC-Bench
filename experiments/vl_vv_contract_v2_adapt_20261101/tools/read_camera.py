import json,re,sys
from pathlib import Path
HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE.parents[1]/'scripts'))
import episode_contract as c
rows=[json.loads(l) for l in open(HERE/'camera_remaining.jsonl')]
for r in rows:
    if r['kind']=='reverse_or_opposite_view': continue
    k=c.read(c.resolve_v2_contract(r['episode_id']))
    names={i:e['name'] for i,e in k['entity_descriptions'].items()}
    print('=====',r['episode_id'],r['shot_id'],r['field'],r['contract'],'|',r['value'])
    field=next(s for s in k['shots'] if s['shot_id']==r['shot_id'])['shot_description'][r['field']]
    print('  ev:',[q['quote'] for q in field['evidence']],'src',field.get('source_claim_ids'))
    t={s['shot_id']:s['text'] for s in k['prompt']['shots']}
    for s in k['shots']:
        d=s['shot_description']
        v=(d['camera_view'] or {}).get('value') if d['camera_view'] else None
        print('  ',s['shot_id'],'loc',[names[str(x)][:22] for x in s['locations']],'view:',(v or '-')[:70],'| pres:',[names[str(x)][:16] for x in s['presence']][:5],'|',t[s['shot_id']][:95])
