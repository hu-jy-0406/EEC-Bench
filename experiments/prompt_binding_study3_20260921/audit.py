import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import gs_prompt_binding as b
import run_gs_temporal as pipeline
r=Path(__file__).resolve().parent
case=ROOT/'experiments/pipeline_parallel_20260921/run'
out=r/'binding'
result=b.read(out/'results.json');reg=b.read(r/'prompt_registry.json');visual=b.read(case/'global_entities/global_entities.json')
raw=b.read(out/'calls/binding/response.json')
checked=b.materialize(raw,reg,visual)
assert all(result[k]==v for k,v in checked.items())
recovery=b.read(r/'recovery.json')
for path,digest in b.read(out/'source_hashes.json').items():
 if path==str(ROOT/'scripts/gs_prompt_binding.py'):
  assert b.sha(recovery['original_script_snapshot'])==digest
  assert b.sha(path)==recovery['final_script_sha256']
 else:assert b.sha(path)==digest,path
assert b.sha(out/'calls/binding/response.json')==recovery['raw_response_sha256']
request=b.read(out/'calls/binding/input.json')
frames=[dict(f,shot_id=s['shot_id']) for s in b.read(case/'raw_manifest.json')['shots'] for f in s['frames']]
assert len(request['image_order'])==len(frames)==18
for v,e in zip(request['visual_entities'],visual['entities']):
 assert v['global_entity_id']==e['global_entity_id']
 for a,orig in zip(v['appearances'],e['appearances']):
  assert a['observations']==[dict(frame_id=o['frame_id'],box_xyxy=o['box_xyxy']) for o in orig['observations']]
usage=b.io.audit_events(out/'calls/binding/events.jsonl')
assert usage==result['usage']
assert result['total_tokens']==sum(u['input_tokens']+u['output_tokens'] for u in usage)
groups=b.grouped_report(out/'results.json',case/'appearance/report/entities.csv',out/'appearance_groups.json')
assert sum(g['count'] for g in groups['groups'].values())==len(visual['entities'])
plan=b.read(r/'integrated_plan.json');jobs={j['stage']:j for j in plan}
assert jobs['prompt_binding']['depends']==['global_entity_table']
assert jobs['prompt_binding_report']['depends']==['prompt_binding','appearance_report']
assert jobs['prompt_binding']['api_slots']==1 and not jobs['prompt_binding']['gpu']
# No-registry compatibility: exact legacy plan from the saved pre-change runner.
shots=b.read(case/'raw_manifest.json')['shots']
old=b.read(case/'execution_plan.json')
new=pipeline.plan(case,shots,6,'GPU-9bd66cc06860c5b4',runtime_name='temporal_spatial_v1')
assert new==old,'No-registry plan changed'
report=dict(passed=True,original_frames=18,global_records=len(visual['entities']),prompt_entities=len(reg['entities']),
 exact_original_boxes=True,complete_inventory=True,source_hashes_passed=True,no_registry_plan_exact=True,
 audited_isolated_calls=1,tests=22,classification_counts=result['counts'],tokens=result['total_tokens'],
 standard_api_equivalent_usd=result['standard_api_equivalent_usd'],full_frontend_rerun=False)
b.save(r/'audit.json',report)
print(json.dumps(report,ensure_ascii=False,indent=2))
