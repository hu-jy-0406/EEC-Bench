import os,time,subprocess,json,sys
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path[:0]=[str(B/'scripts'),str(B/'tests')]
import gs_prompt_binding as binding
import jsonschema
cmd=[sys.executable,'-m','unittest','test_gs_prompt_binding','test_gs_prompt_alignment','test_gs_scoring_efficiency','test_gs_integrated','-v']
env=os.environ.copy();env['PYTHONPATH']=os.pathsep.join([str(B/'scripts'),str(B/'tests')])
with (R/'tests_corrected_invocation.log').open('w') as log:res=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT)
print('Tests exit',res.returncode,flush=True)
if res.returncode:sys.exit(res.returncode)
historic=B/'experiments/identity_minimal_full_validation_20260922'
assert binding.OUTPUT_SCHEMA==binding.read(historic/'strict_binding_schema.json')
checks={}
for name,rel in [('initial_invalid','runs/study4/prompt_binding/calls/binding/response.json'),('second_invalid','study4_prompt_corrected/binding/calls/binding/response.json'),('strict_valid','study4_prompt_recovery_v2/binding/calls/binding/response.json'),('study2_valid','runs/study2/prompt_binding/calls/binding/response.json'),('study3_valid','runs/study3/prompt_binding/calls/binding/response.json')]:
 checks[name]=jsonschema.Draft202012Validator(binding.OUTPUT_SCHEMA).is_valid(binding.read(historic/rel))
assert checks==dict(initial_invalid=False,second_invalid=False,strict_valid=True,study2_valid=True,study3_valid=True)
binding.save(R/'historical_schema_audit.json',checks);print('Historic audit',checks,flush=True)
case=historic/'runs/study4';ref=historic/'references/study4_corrected';start=time.time()
result=binding.run(case,ref/'prompt_registry.json',R/'fresh_study4',1800,ref/'narrative.json')
binding.save(R/'live_validation.json',dict(status='success',seconds=time.time()-start,counts=result['counts'],total_tokens=result['total_tokens'],standard_api_equivalent_usd=result['standard_api_equivalent_usd'],production_default_schema=True,model='gpt-6-astra',reasoning='medium',prompt_unchanged=True))
print('LIVE VALIDATION',binding.read(R/'live_validation.json'),flush=True)
