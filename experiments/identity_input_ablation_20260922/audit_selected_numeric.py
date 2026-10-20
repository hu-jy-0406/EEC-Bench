"""Retain all endpoint cosines/distances/raw r_e for the selected replay."""
import sys,json
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from gs_entity_displacement import boundary
from gs_temporal_core import boundary_proposals
read=lambda p:json.loads(p.read_text())
selection=read(R/'selection.json');rows=[]
for study in ['study2','study3','study4']:
 for repeat in [1,2,3]:
  out=R/'runs'/study/selection['variant']/f'r{repeat}';meta=read(out/'manifest.json');case=Path(meta['source_case'])
  graphs=[read(case/f'selected/{sid}_scene.json') for sid in ['shot1','shot3']];fit=read(case/'registration/roma_geometry/registration.json')['fits']['all_structures'];scope=read(case/'pair_scope.json');reviewed=read(case/'boundary/results.json')
  result={}
  for kind,m in [('baseline',read(case/'matching.json')),('selected',read(out/'calls/identity_review/response.json')['matching'])]:
   b=boundary('pair_000',graphs,m,fit,scope,reviewed);p=boundary_proposals(graphs,m,fit)
   result[kind]=dict(boundary=b,spatial_units=p['spatial_units'])
  sig=lambda b:sorted((tuple(r['entity_ids']),r['distance'],r['r_e'],r['entity_score']) for r in b['records'] if r.get('r_e') is not None)
  assert sig(result['baseline']['boundary'])==sig(result['selected']['boundary'])
  result.update(note='Local frozen-geometry reaggregation using existing presence motion exemptions; no new model verdicts. Raw r_e retained without rounding.',model_calls=0,total_tokens=0,api_usd=0)
  (out/'numeric_replay.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n');rows.append(dict(study=study,repeat=repeat,raw_r_e_equal=True,scored_entities=len(sig(result['selected']['boundary'])),artifact=str(out/'numeric_replay.json')))
(R/'selected_numeric_audit.json').write_text(json.dumps(rows,indent=2)+'\n');print('PASS: all9 frozen boundary raw r_e and entity scores match; original values saved.')
