"""Experimental wire schema encodes existing materialize invariants; no gate changes."""
import copy,sys,json
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
import gs_prompt_binding as binding
from run_gs_integrated import save,read
schema=copy.deepcopy(binding.SCHEMA);row=schema['properties']['bindings']['items'];variants=[]
for status in ['bound','unbound','unknown']:
 v=copy.deepcopy(row);p=v['properties'];p['status']={'type':'string','enum':[status]}
 if status=='bound':
  p['prompt_entity_id']={'type':'string','minLength':1};p['candidate_prompt_entity_ids']['maxItems']=0;p['fact_ids']['minItems']=1;p['witnesses']['minItems']=1
 else:
  p['prompt_entity_id']={'type':'null'};p['fact_ids']['maxItems']=0
  if status=='unbound':p['candidate_prompt_entity_ids']['maxItems']=0
 variants.append(v)
schema['properties']['bindings']['items']={'anyOf':variants}
original=binding.call
def call(folder,payload,images,timeout,**kwargs):
 assert 'schema' not in kwargs
 return original(folder,payload,images,timeout,schema=schema,**kwargs)
binding.call=call
if __name__=='__main__':
 import jsonschema
 # Check the schema rejects the observed invalid output without changing decisions.
 old=read(R/'study4_prompt_corrected/binding/calls/binding/response.json')
 assert list(jsonschema.Draft202012Validator(schema).iter_errors(old))
 checks=[]
 for status in ['bound','unbound','unknown']:
  row=dict(global_entity_id='ge0001',status=status,prompt_entity_id='door' if status=='bound' else None,candidate_prompt_entity_ids=['door'] if status=='unknown' else [],fact_ids=['shot1'] if status=='bound' else [],witnesses=[dict(shot_id='shot1',frame_id=0)],comparison_witnesses=[],reason='schema fixture')
  jsonschema.validate(dict(bindings=[row]),schema);checks.append(status)
 save(R/'strict_binding_schema.json',schema);save(R/'strict_binding_schema_audit.json',dict(valid_states=checks,observed_invalid_rows_rejected=True,original_prompt_changed=False,materialize_changed=False,production_default_changed=False))
 ref=R/'references/study4_corrected';out=R/'study4_prompt_recovery_v2/binding'
 result=binding.run(R/'runs/study4',ref/'prompt_registry.json',out,1800,ref/'narrative.json');print(result['counts'],flush=True)
