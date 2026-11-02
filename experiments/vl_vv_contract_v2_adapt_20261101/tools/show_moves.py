import json
from pathlib import Path
R=Path('/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments')
CASES=[('WItUr-qHHBw_s00042_n4_clean_v2','Shot3'),('iJVAiOxLEiU_s00160_n8_clean_v2','Shot3'),('ZQe51dHPgXk_s00091_n4_clean_v2','Shot4'),('3pQVL49eHfs_s00057_n4_clean_v2','Shot3'),('mu-YLZpB6is_s00061_n4_clean_v2','Shot4'),
       ('imopUZe289I_s00019_n4_clean_v2','Shot3'),('TTXjgOan_KI_s00004_n6_clean_v2','Shot5'),('6oh2hNWmf00_s00329_n6_clean_v2','Shot3'),('4kRRDuR7OBM_s00007_n6_clean_v2','Shot4')]
for eid,sid in CASES:
    cl=R/'contract_cleanup_20261031/episodes'/eid/'contract_with_evidence.json'
    p=cl if cl.exists() else R/'episode_contracts_v2_20261029/deliverables/episodes'/eid/'contract_with_evidence.json'
    c=json.loads(p.read_text())
    names={k:(e['label'][0],e['name']) for k,e in c['entity_descriptions'].items()}
    print('=====',eid,sid,'cleaned' if cl.exists() else 'v2')
    print('prompt global:',c['prompt']['global_prompt'][:200])
    i=[s['shot_id'] for s in c['shots']].index(sid)
    for s,t in zip(c['shots'],c['prompt']['shots']):
        if abs(c['shots'].index(s)-i)<=1 or s['shot_id'] in ('Shot1','Shot2'):
            sd=s['shot_description']
            print(' ',s['shot_id'],'loc',[names[str(k)][1] for k in s['locations']],'view',(sd['camera_view'] or {}).get('value') if sd['camera_view'] else None,'| src',(sd['camera_view'] or {}).get('source_claim_ids') if sd['camera_view'] else None,'| ev',[q['quote'] for q in (sd['camera_view'] or {}).get('evidence',[])] if sd['camera_view'] else None)
            print('     pres',[f'{k}:{names[str(k)][1]}' for k in s['presence']][:12])
            print('     text',t['text'][:260])
    print('  cross',[(x['id'],x['shot_ids'],x['expected'][:60]) for x in c['cross_shot']])
v1=R/'episode_contracts_20260921/deliverables/episodes'
import collections
cnt=collections.Counter(); ex=None
for d in sorted(v1.iterdir()):
    for q in json.loads((d/'contract.json').read_text())['claims']:
        if q['dimension']=='presence' and q['predicate']!='present':
            cnt[(q['predicate'],q['quantifier'],q['coordinate_frame'])]+=1; ex=ex or q
print(cnt); print(ex)
