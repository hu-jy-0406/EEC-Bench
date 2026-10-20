import sys,time,shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_gs_temporal_stage import Stage,read,save
from run_isolated_shot_static_3d import owned_compute_job
BASE=B/'experiments/temporal_v2_study234_revised_20260920'
def one(n):
 src=BASE/n;dst=R/'within_compact_medium_fixed'/n;dst.mkdir(parents=True,exist_ok=False)
 for pattern in ['narrative.json','inputs/*.json','selected/*.json','expected_motion/*.json']:
  for f in src.glob(pattern):
   p=dst/f.relative_to(src);p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,p)
 state=dict(status='running',shots={});save(dst/'screen.json',state);start=time.time()
 try:
  stage=Stage(dst,'temporal_compact_medium')
  for sid in ['shot1','shot2','shot3']:
   stage.within(sid);a=read(src/'within'/sid/'results.json');b=read(dst/'within'/sid/'results.json');diff=[]
   for kind in ['presence','spatial']:
    x={u['unit_id']:u['status'] for u in a[kind]['units']};y={u['unit_id']:u['status'] for u in b[kind]['units']};assert x.keys()==y.keys()
    diff.extend(dict(kind=kind,unit_id=k,old=x[k],new=y[k]) for k in x if x[k]!=y[k])
   x={e['event_id']:e['status'] for e in a['events']};y={e['event_id']:e['status'] for e in b['events']};assert x.keys()==y.keys()
   events=[dict(event_id=k,old=x[k],new=y[k]) for k in x if x[k]!=y[k]]
   state['shots'][sid]=dict(unit_differences=diff,event_differences=events,scores={k:b[k]['summary'] for k in ['presence','spatial']});save(dst/'screen.json',state);print(n,sid,'unitdiff',len(diff),'eventdiff',len(events),flush=True)
  state['status']='success'
 except BaseException as e:state.update(status='failed',error=repr(e))
 finally:state['seconds']=time.time()-start;save(dst/'screen.json',state)
 return state
if __name__=='__main__':
 owned_compute_job()
 with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(one,['study2','study3','study4']))
 save(R/'within_fixed_summary.json',results)
