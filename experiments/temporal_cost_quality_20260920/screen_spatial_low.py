import json,sys,time,shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_gs_temporal_stage import Stage,read,save
from run_isolated_shot_static_3d import owned_compute_job
BASE=B/'experiments/temporal_v2_study234_revised_20260920'
def one(n):
 src=BASE/n/'pairs/pair_000';dst=R/'spatial_compact_low'/n;dst.mkdir(parents=True,exist_ok=False)
 for pattern in ['narrative.json','matching.json','inputs/*.json','selected/*.json','registration/roma_geometry/registration.json']:
  for f in src.glob(pattern):
   p=dst/f.relative_to(src);p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,p)
 stage=Stage(dst,'temporal_compact_low');original=stage.call
 def call(name,prompt,payload,images,schema):
  if name.startswith('boundary_review_'):
   save(dst/'frozen_presence_dependency.json',dict(source=str(src/'calls'/name/'response.json'),purpose='keep unmodified presence stage fixed; never supplied to local spatial judges'))
   return read(src/'calls'/name/'response.json')
  return original(name,prompt,payload,images,schema)
 stage.call=call;start=time.time();state=dict(status='running');save(dst/'screen.json',state)
 try:
  stage.boundary();a=read(src/'boundary/results.json');b=read(dst/'boundary/results.json');old={e['event_id']:e['status'] for e in a['events']};new={e['event_id']:e['status'] for e in b['events']};assert old.keys()==new.keys()
  state.update(status='success',differences=[dict(event_id=k,old=old[k],new=new[k]) for k in old if old[k]!=new[k]],scores={k:b[k]['summary'] for k in ['presence','spatial']})
 except BaseException as e:state.update(status='failed',error=repr(e))
 finally:state['seconds']=time.time()-start;save(dst/'screen.json',state);print(n,json.dumps(state),flush=True)
 return state
if __name__=='__main__':
 owned_compute_job()
 with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(one,['study2','study3','study4']))
 save(R/'spatial_low_summary.json',results)
