import json,shutil,sys,time,traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parent;B=ROOT.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_gs_temporal_stage import Stage,read,save
from gs_temporal_review import validate_checks
from gs_temporal_core import aggregate
from gs_entity_appearance_compact import cost
from run_isolated_shot_static_3d import owned_compute_job

def run(study):
 start=time.time();out=ROOT/(study+'_presence');out.mkdir()
 case=B/'experiments/within_negative_review_20260920/full'/study/'pairs/pair_000'
 shutil.copy2(case/'narrative.json',out/'narrative.json')
 try:
  original=Stage(case,'temporal_spatial_v1');images=sum([original.source_images(s)[1] for s in ('shot1','shot3')],[])
  proposals=read(case/'boundary/proposals.json');proposals['events']=[e for e in proposals['events'] if e['kind']=='presence']
  payload=read(case/'calls/boundary_review_000/input.json');payload['events']=proposals['events']
  s=Stage(out,'scoring_efficiency_v1');raw=s.review_events('boundary_review',payload,images)
  checks=validate_checks(raw,proposals,images,s.story,boundary=True,presence_only_schema=True)
  old=read(case/'boundary/results.json');oldchecks={e['event_id']:e for e in old['events'] if e['kind']=='presence'}
  result=dict(status='success',source_case=str(case),old_summary=old['presence']['summary'],new_summary=aggregate(proposals['presence_units'],checks)['summary'],
    differences=[dict(event_id=k,old=oldchecks[k]['status'],new=v['status'],old_reason=oldchecks[k]['review']['reason'],new_reason=v['review']['reason']) for k,v in checks.items() if oldchecks[k]['status']!=v['status']],
    old_conflicts=[k for k,v in oldchecks.items() if v['status']=='conflict'],new_conflicts=[k for k,v in checks.items() if v['status']=='conflict'],checks=checks)
 except BaseException as exc:result=dict(status='failed',error=repr(exc),traceback=traceback.format_exc())
 result['seconds']=time.time()-start;us=[]
 for p in (out/'calls').glob('*/status.json'):
  d=read(p);us+=d.get('usage',d.get('known_usage',[]))
 result.update(total_tokens=sum(u.get('input_tokens',0)+u.get('output_tokens',0) for u in us),standard_api_equivalent_usd=cost(us),usage=us)
 save(out/'results.json',result);return {k:v for k,v in result.items() if k!='checks'}
owned_compute_job()
with ThreadPoolExecutor(max_workers=2) as pool:results=dict(zip(('study2','study4'),pool.map(run,('study2','study4'))))
save(ROOT/'additional_presence_validation.json',results);print(json.dumps(results,ensure_ascii=False,indent=2))
if any(r['status']!='success' for r in results.values()):raise SystemExit(1)
