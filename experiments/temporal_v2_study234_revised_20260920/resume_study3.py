"""Resume only unexecuted stages after a guard-only stop; preserve first attempt."""
import os,sys,shutil,time,threading,signal
from pathlib import Path
import psutil
R=Path(__file__).resolve().parent; B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_gs_temporal import execute,summarize,read,save
from run_isolated_shot_static_3d import owned_compute_job
case=R/'study3';old=read(case/'pipeline_runtime.json');archive=case/'guard_stop_attempt1';archive.mkdir()
for name in ['pipeline_runtime.json','summary.json','stages.csv','calls.csv','boxer_shot2.log']:
 shutil.copy2(case/name,archive/name)
assert old['status']=='failed'
failed=[r for r in old['stages'] if r['status']!='success'];assert len(failed)==1 and failed[0]['stage']=='boxer_shot2'
log=(case/'boxer_shot2.log').read_text();assert 'GPU not idle or UUID mismatch' in log and 'GUARD PASS' not in log
completed=[r for r in old['stages'] if r['status']=='success'];done={r['stage'] for r in completed}
rows=read(case/'execution_plan.json');pending=[]
for r in rows:
 if r['stage'] in done:continue
 r['depends']=[d for d in r['depends'] if d not in done]
 if r['gpu']:
  assert r['command'][3]=='GPU-d2218b471577c2c7';r['command'][2]='3'
 pending.append(r)
env=os.environ.copy();env.update(CASE_ROOT=str(case),PYTHONPATH=str(B/'experiments/shot_scene_boxes_goal_20260916/deps'),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='4')
for k in ['HIP_VISIBLE_DEVICES','CUDA_VISIBLE_DEVICES','ROCR_VISIBLE_DEVICES']:env.pop(k,None)
for k,n in [('MIOPEN_USER_DB_PATH','miopen_db'),('MIOPEN_CUSTOM_CACHE_DIR','miopen_cache'),('MPLCONFIGDIR','matplotlib')]:env[k]=str(case/'runtime_cache'/n)
stop=threading.Event()
def guard():
 while not stop.wait(3):
  pids={os.getpid()}
  for pid in [os.getpid(),37822]:
   try:pids.update(p.pid for p in psutil.Process(pid).children(recursive=True))
   except psutil.Error:pass
  rss=0
  for pid in pids:
   try:rss+=psutil.Process(pid).memory_info().rss
   except psutil.Error:pass
  if rss>52*1024**3:
   save(R/'resume_resource_stop.json',dict(rss=rss,time=time.time()))
   for p in psutil.Process().children(recursive=True):
    try:p.terminate()
    except psutil.Error:pass
   os.kill(os.getpid(),signal.SIGTERM)
threading.Thread(target=guard,daemon=True).start()
save(R/'study3_recovery.json',dict(status='running',pid=os.getpid(),reason='guard stopped before boxer inference; completed fresh stages preserved',pending=[r['stage'] for r in pending],physical_gpu=3,uuid='GPU-d2218b471577c2c7'))
try:execute(case,pending,env,owned_compute_job(),'spatial')
finally:
 stop.set();new=read(case/'pipeline_runtime.json');new['stages']=completed+new['stages'];new['started']=old['started'];new['seconds']=new['finished']-old['started'];new['recovery']=dict(archive=str(archive),previous_failed_stage='boxer_shot2',inference_before_guard_stop=False)
 save(case/'pipeline_runtime.json',new);summarize(case,new);save(R/'study3_recovery.json',dict(status=new['status'],finished=time.time(),reason='resumed only remaining stages after GPU guard stop'))
