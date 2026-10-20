import json,copy,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent;C=R/'shared/parking4'
read=lambda p:json.loads(p.read_text())
raw=read(C/'optimization/results.json');assert raw['status']=='success'
glob=read(C/'global_initial/results.json')
car=next(g for g in glob['groups'] if 'Shot1/e1' in g['entity_ids'])
assert 'Shot3/e1' in car['entity_ids']
# Case-specific explicit protocol audit, not a new anchor policy or residual filter.
# Existing prompt: only fixed room structure/large furniture. The parked car fails it.
violations=[dict(group_id=car['group_id'],entity_ids=car['entity_ids'],anchor_pairs=car['anchor_pairs'],reason='Car is not stable common room structure/large furniture required by unchanged global_match.txt. Static label alone is insufficient.')]
aud=copy.deepcopy(raw);aud['method']='roma_fps32_incremental_protocol_audited';aud['raw_results']='optimization/results.json';aud['protocol_audit']=violations
for row in aud['shots']:
 if row['shot_id']=='Shot3':
  row.update(prototype='Shot3',status='root_invalid_anchor_rejected',fit=None)
  row.pop('pair_case',None)
# Shot3 has no allowed anchor to any other shot. No untested valid attachment
# is created or omitted by removing the car-only Shot3->Shot1 link.
assert not any('Shot3' in [p['shot_a'],p['shot_b']] for g in glob['groups'] if g['group_id']!=car['group_id'] for p in g['anchor_pairs'])
assert not any(row['shot_id']!='Shot3' and row['prototype']=='Shot3' for row in raw['shots'])
aud['roots']=[r['shot_id'] for r in aud['shots'] if r['prototype']==r['shot_id']]
for a in aud['attempts']:
 if a['shot']=='Shot3' and a['root']=='Shot1':a['protocol_status']='invalid_car_anchor_excluded_from_accepted_registration'
(C/'optimization_audited').mkdir(exist_ok=True);(C/'optimization_audited/results.json').write_text(json.dumps(aud,ensure_ascii=False,indent=2))
summary={}
for p in sorted((C/'pairs').glob('*/registration/roma_geometry/pair_diagnostics.json')):
 ds=read(p);summary[p.parents[2].name]={k:sum(x.get(k,0) for x in ds) for k in ['raw','same_structural_region','confidence_and_cycle','lifted']}
(R/'registration_audit.json').write_text(json.dumps(dict(violations=violations,pair_filter_counts=summary,accepted_optimization_roots=aud['roots'],raw_outputs_preserved=True),ensure_ascii=False,indent=2))
print(json.dumps(summary,indent=2))
