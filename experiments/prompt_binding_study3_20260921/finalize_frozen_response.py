"""Development-only recovery: preserve the sole actual response and its expenses."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
import gs_prompt_binding as b
from gs_entity_appearance_compact import cost
r=Path(__file__).resolve().parent;out=r/'binding';case=ROOT/'experiments/pipeline_parallel_20260921/run'
pinned=b.read(out/'source_hashes.json');script=str(ROOT/'scripts/gs_prompt_binding.py')
archived=r/'source_snapshot/gs_prompt_binding_call.py'
assert b.sha(archived)==pinned[script]
for p,h in pinned.items():
 if p!=script:assert b.sha(p)==h,p
raw=b.read(out/'calls/binding/response.json');state=b.read(out/'calls/binding/status.json')
result=b.materialize(raw,b.read(out/'prompt_registry.json'),b.read(case/'global_entities/global_entities.json'))
usage=state['usage'];result.update(usage=usage,total_tokens=sum(u['input_tokens']+u['output_tokens'] for u in usage),
 standard_api_equivalent_usd=cost(usage),cost_basis='Existing pipeline Astra rates USD10/1/12.5/50 per million uncached/cache-read/cache-write/output; standard API equivalent, not actual bill.',
 source_case=str(case),seconds=state['seconds'],development_recovery='Original sole response unchanged. Initial validator incorrectly restricted valid registry-wide fact IDs to matched entry; corrected local validation only, zero extra API calls.')
b.save(out/'results.json',result)
b.save(r/'recovery.json',dict(original_script_sha256=pinned[script],original_script_snapshot=str(archived),final_script_sha256=b.sha(script),raw_response_sha256=b.sha(out/'calls/binding/response.json'),new_calls=0,validation='All original non-code input hashes unchanged; response not edited'))
lines=['# Study3 prompt binding','','| Global entity | Name | Binding | Prompt ID | Reason |','|---|---|---|---|---|']
for row in result['bindings']:
 lines.append('| '+' | '.join(str(row[k] or '').replace('|','\\|').replace('\n',' ') for k in ('global_entity_id','name','status','prompt_entity_id','reason'))+' |')
(out/'bindings.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(result['counts']))
