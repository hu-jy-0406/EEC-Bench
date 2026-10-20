import json,sys,time,shutil,hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_gs_temporal_stage import Stage,read,save
from run_isolated_shot_static_3d import owned_compute_job
BASE=B/'experiments/temporal_v2_study234_revised_20260920'
def one(name):
 src=BASE/name;dst=R/'shots_compact_medium'/name;dst.mkdir(parents=True,exist_ok=False)
 for pattern in ['narrative.json','inputs/*.json']:
  for f in src.glob(pattern):
   t=dst/f.relative_to(src);t.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,t)
 (dst/'pi3x').symlink_to((src/'pi3x').resolve(),target_is_directory=True)
 state=dict(status='running',shots={});save(dst/'screen.json',state);start=time.time()
 try:
  stage=Stage(dst,'temporal_compact_medium')
  for sid in ['shot1','shot2','shot3']:
   stage.expectation(sid)
   a=read(src/'expected_motion'/f'{sid}.json');b=read(dst/'expected_motion'/f'{sid}.json');diff=[]
   for x,y in zip(a['entities'],b['entities']):
    assert x['entity_id']==y['entity_id']
    if x['observed_status']!=y['observed_status']:diff.append(dict(entity_id=x['entity_id'],field='observed_status',old=x['observed_status'],new=y['observed_status']))
    for i,(p,q) in enumerate(zip(x['intervals'],y['intervals'])):
     for f in ['expected','observed','basis']:
      if p[f]!=q[f]:diff.append(dict(entity_id=x['entity_id'],interval=i,field=f,old=p[f],new=q[f]))
   stage.within(sid)
   a=read(src/'within'/sid/'results.json');b=read(dst/'within'/sid/'results.json')
   units=[]
   for kind in ['presence','spatial']:
    x={u['unit_id']:u['status'] for u in a[kind]['units']};y={u['unit_id']:u['status'] for u in b[kind]['units']};assert x.keys()==y.keys()
    units.extend(dict(kind=kind,unit_id=k,old=x[k],new=y[k]) for k in x if x[k]!=y[k])
   state['shots'][sid]=dict(expectation_differences=diff,unit_differences=units,scores={k:b[k]['summary'] for k in ['presence','spatial']})
   save(dst/'screen.json',state);print(name,sid,'expectation_diffs',len(diff),'unit_diffs',len(units),flush=True)
  state['status']='success'
 except BaseException as e:state.update(status='failed',error=repr(e));print(name,repr(e),flush=True)
 finally:state['seconds']=time.time()-start;save(dst/'screen.json',state)
 return state
if __name__=='__main__':
 owned_compute_job()
 with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(one,['study2','study3','study4']))
 save(R/'shots_screen_summary.json',results)
