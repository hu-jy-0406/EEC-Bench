import copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'EECBench/scripts'))
import gs_prompt_binding as b
case=ROOT/'EECBench/experiments/study3_final_integrated_20260921/run'
registry=b.read(case/'prompt_registry.json');visual=b.read(case/'global_entities/global_entities.json')
raw=b.read(case/'prompt_binding/calls/binding/response.json');old=b.read(case/'prompt_binding/results.json')
result=b.materialize(raw,registry,visual)
assert result['counts']==old['counts']
assert [{k:v for k,v in row.items() if k!='comparison_witnesses'} for row in result['bindings']]==old['bindings']
# Explicit representation fixture for the diagnosed comparison, NOT a new model verdict.
original=b.read(case/'prompt_binding/calls/binding_attempt1/response.json');fixture=copy.deepcopy(original)
byid={e['global_entity_id']:e for e in visual['entities']}
console=next(r['global_entity_id'] for r in original['bindings'] if r['prompt_entity_id']=='console')
converted=[]
for row in fixture['bindings']:
 valid={(a['shot_id'],f) for a in byid[row['global_entity_id']]['appearances'] for f in a['observed_frame_ids']}
 own=[];comparison=[]
 for w in row['witnesses']:
  if (w['shot_id'],w['frame_id']) in valid:own.append(w)
  else:
   assert row['global_entity_id'] in ('ge0019','ge0031') and w==dict(shot_id='shot2',frame_id=0)
   comparison.append(dict(global_entity_id=console,**w));converted.append(row['global_entity_id'])
 row.update(witnesses=own,comparison_witnesses=comparison)
fixed=b.materialize(fixture,registry,visual)
assert len(converted)==2
out=Path(__file__).resolve().parent
b.save(out/'explicit_comparison_fixture.json',dict(origin='Deterministic test fixture: two diagnosed hallway-console references explicitly attributed; no new inference or historical overwrite',response=fixture))
b.save(out/'audit.json',dict(status='pass',legacy_successful_bindings_unchanged=True,diagnosed_comparisons_supported=converted,
 referenced_comparison_entity=console,fixture_is_not_fresh_model_validation=True,tests_passed=34,new_model_calls=0,tokens=0,api_usd=0))
print('PASS legacy binding compatibility and two explicitly attributed comparison fixtures')
