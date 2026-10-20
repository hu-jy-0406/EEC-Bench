"""Exercise the corrected entrypoint with the unchanged recorded model response."""
import sys
import shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
import gs_prompt_binding as b
r=Path(__file__).resolve().parent;case=ROOT/'experiments/pipeline_parallel_20260921/run'
source=r/'binding/calls/binding'
def frozen_call(folder,payload,images,timeout):
 assert payload==b.read(source/'input.json')
 assert images==b.read(source/'request.json')['images']
 shutil.copytree(source,folder)
 return b.read(source/'response.json')
b.call=frozen_call
result=b.run(case,r/'prompt_registry.json',r/'replay')
original=b.read(r/'binding/results.json')
for key in ('bindings','counts','schedule','unmatched_prompt_entity_ids','total_tokens','standard_api_equivalent_usd'):
 assert result[key]==original[key],key
b.save(r/'replay_audit.json',dict(passed=True,corrected_entrypoint_complete=True,exact_model_input_images_and_response=True,new_api_calls=0,new_tokens=0,new_api_usd=0,reused_recorded_tokens=result['total_tokens'],reused_standard_api_equivalent_usd=result['standard_api_equivalent_usd']))
print(result['counts'])
