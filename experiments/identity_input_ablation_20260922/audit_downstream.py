"""Local frozen-geometry audit; does not reuse model scores as fresh evaluations."""
import json,sys,math
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from gs_temporal_core import boundary_proposals,center
read=lambda p:json.loads(p.read_text())
def numeric(case,matching):
 graphs=[read(case/f'selected/{s}_scene.json') for s in ['shot1','shot3']]
 fit=read(case/'registration/roma_geometry/registration.json')['fits']['all_structures']
 p=boundary_proposals(graphs,matching,fit);groups={g['group_id']:g for g in matching['groups']}
 key=lambda g:(tuple(sorted(g['a_ids'])),tuple(sorted(g['b_ids'])),g['identity'])
 spatial=sorted((tuple(sorted(key(groups[g]) for g in u['endpoint_groups'])),u['cosine'],u['reason']) for u in p['spatial_units'])
 presence=sorted((tuple(sorted(u['entity_ids'])),u['reason']) for u in p['presence_units'])
 distances=[]
 for g in matching['groups']:
  if g['identity']!='matched':continue
  pts=[center(p['endpoint_observations'][i][g[k][0]]) for i,k in enumerate(['a_ids','b_ids'])]
  distances.append((key(g),math.dist(*pts) if all(x is not None for x in pts) else None))
 return dict(spatial=spatial,presence=presence,distances=sorted(distances))
rows=[]
for path in sorted((R/'runs').glob('*/*/*/result.json')):
 d=read(path)
 if d['status']!='success':continue
 case=Path(d['source_case']);a=numeric(case,read(case/'matching.json'));b=numeric(case,read(path.parent/'calls/identity_review/response.json')['matching'])
 rows.append(dict(study=d['study'],variant=d['variant'],repeat=d['repeat'],**{k+'_equal':a[k]==b[k] for k in a},spatial_pairs=len(b['spatial']),negative_pairs=sum(x[1] is not None and x[1]<0 for x in b['spatial']),note='Frozen numeric inputs/populations only; no fresh downstream model verdicts.'))
(R/'downstream_audit.json').write_text(json.dumps(rows,indent=2)+'\n')
for r in rows:print(r)
