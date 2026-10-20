"""Shared fresh frontend only; downstream methods consume identical frozen graphs."""
import sys,os,json,time,subprocess,traceback,shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_gs_integrated import prepare,read,save,sha,FRONT,S,CPU,GEOM
from run_gs_temporal import plan,scheduling,scope_for
from gs_runtime_profile import profile
name=sys.argv[1];gpu=int(sys.argv[2]);uuid=sys.argv[3];case=R/'shared'/name;inp=R/'inputs'/name
runtime=profile('scoring_efficiency_v1');shots=read(inp/'manifest.json')['shots']
prepare(case,inp/'manifest.json',inp/'narrative.json',FRONT/'study2/yyfz233--Pi3X_download.json',B/'experiments/study_inconsistent_3/geocalib_boxer_20260913/weights/geocalib-pinhole.tar',protocol='temporal_v2')
source=B/'experiments/parking_prompt_recovery_20260922/case/shot_prompt_recovery/entities'
shutil.copytree(source,case/'entities')
save(case/'recovered_detection_provenance.json',dict(source=str(source),hashes={str(p):sha(p) for p in source.rglob('*.json')},new_detection_calls=0))
provenance=read(case/'provenance.json');provenance.update(inference_reuse=True,reuse_scope='frozen recovered detection/clustering only; calibration, Pi3X, Boxer and motion fresh');save(case/'provenance.json',provenance)
save(case/'runtime_profile.json',runtime);save(case/'identity_scope.json',scope_for(shots));save(case/'alignment_method.json',dict(method='roma_fps32'));save(case/'scheduling.json',scheduling())
jobs=[j for j in plan(case,shots,gpu,uuid,runtime['name'],stop_after='identity') if not j['stage'].startswith('pair_') and j['stage'] not in ['global_entity_table','detection_and_clustering']];save(case/'execution_plan.json',jobs)
env=os.environ.copy();env.update(CASE_ROOT=str(case),PYTHONPATH=str(B/'experiments/shot_scene_boxes_goal_20260916/deps'),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='4')
for key,n in [('MIOPEN_USER_DB_PATH','miopen_db'),('MIOPEN_CUSTOM_CACHE_DIR','miopen_cache'),('MPLCONFIGDIR','matplotlib')]:
 p=case/'runtime_cache'/n;p.mkdir(parents=True);env[key]=str(p)
state=dict(status='running',started=time.time(),stages=[],scope='fresh geometry and motion on frozen recovered detections; not full pipeline');done={'detection_and_clustering'};pending=jobs.copy();active={};failed=[]
def worker(j):
 t=time.time();local=env.copy();local['CASE_ROOT']=j['case_root']
 with (case/(j['stage']+'.log')).open('w') as f:r=subprocess.run(j['command'],env=local,stdout=f,stderr=subprocess.STDOUT)
 return dict(seconds=time.time()-t,returncode=r.returncode,status='success' if r.returncode==0 else 'failed')
try:
 with ThreadPoolExecutor(max_workers=4) as pool:
  while pending or active:
   if not failed:
    for j in pending.copy():
     if len(active)>=4:break
     if not set(j['depends'])<=done:continue
     if j['gpu'] and any(x['gpu'] for x in active.values()):continue
     row=dict(j,status='running',started=time.time());state['stages'].append(row);active[pool.submit(worker,j)]=row;pending.remove(j);print(name,'START',j['stage'],flush=True)
   save(case/'frontend_runtime.json',state)
   if not active:break
   ended,_=wait(active,return_when=FIRST_COMPLETED)
   for f in ended:
    row=active.pop(f);row.update(f.result());print(name,'END',row['stage'],row['status'],flush=True)
    if row['status']=='success':done.add(row['stage'])
    else:failed.append(row['stage'])
 if failed or pending:raise RuntimeError((failed,[j['stage'] for j in pending]))
 hashes={str(p):sha(p) for sid in [s['shot_id'] for s in shots] for p in [case/'inputs'/f'{sid}.json',case/'selected'/f'{sid}_scene.json',case/'pi3x'/sid/'geometry.npz']}
 save(case/'frozen_frontend.json',dict(hashes=hashes,original_frames={f['path']:f['sha256'] for s in shots for f in s['frames']}));state['status']='success'
except BaseException as e:state.update(status='failed',error=repr(e));raise
finally:state.update(finished=time.time(),seconds=time.time()-state['started']);save(case/'frontend_runtime.json',state)
