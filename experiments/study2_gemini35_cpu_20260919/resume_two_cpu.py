"""Explicit CPU-only rescheduling of this run's remaining RoMa pairs and suffix.

Existing fresh same-run pair files are kept; index modulo partition preserves
all 36 pairs and the original per-index random seed. No model judgment repeats.
"""
import json,os,signal,subprocess,sys,time,shutil,traceback
from pathlib import Path
import psutil
R=Path(__file__).resolve().parent;B=R.parents[1];C=R/'run01';sys.path.insert(0,str(B/'scripts'))
from run_gs_integrated import read,save,sha,summarize,GEOM,CPU
from run_isolated_shot_static_3d import owned_compute_job
GROUPS=[[21,22,23,24],[20,26,27,28]]
ALL=set(sum(GROUPS,[]));A=B/'experiments/study3/cpu_adapters/roma_cpu.py'

def preflight():
 assert owned_compute_job()=='191764'
 assert ALL <= (set(range(32))|set(range(64,96))) & os.sched_getaffinity(0)
 busy=psutil.cpu_percent(interval=2,percpu=True)
 extra=set(sum(GROUPS[1:],[]))
 assert all(busy[c]<15 for c in extra),{c:busy[c] for c in extra}
 rss=sum(p.info['memory_info'].rss for p in psutil.process_iter(['uids','memory_info']) if p.info['uids'].real==os.getuid())
 assert rss<38*1024**3,'Insufficient headroom inside the 64 GiB allocation'
 save(R/'parallel_cpu_preflight.json',dict(groups=GROUPS,extra_core_busy={c:busy[c] for c in extra},owned_resident_rss_bytes=rss,stage_rss_limit_gib=24,gpu_visible_count=0))
 os.sched_setaffinity(0,ALL)

def monitor(commands,env,logs):
 processes=[];handles=[];started=time.time();peak=0
 try:
  for command,log in zip(commands,logs):
   h=Path(log).open('w');handles.append(h)
   processes.append(subprocess.Popen(command,env=env,stdout=h,stderr=subprocess.STDOUT,start_new_session=True))
  while any(p.poll() is None for p in processes):
   rss=0
   for p in processes:
    try:
     root=psutil.Process(p.pid)
     for child in [root,*root.children(recursive=True)]:
      try:rss+=child.memory_info().rss
      except psutil.NoSuchProcess:pass
    except psutil.NoSuchProcess:pass
   peak=max(peak,rss)
   save(C/'cpu_monitor.json',dict(pids=[p.pid for p in processes],rss_bytes=rss,peak_rss_bytes=peak,commands=commands,cpu_groups=GROUPS if len(commands)==len(GROUPS) else [GROUPS[0]],seconds=time.time()-started))
   if rss>24*1024**3:raise RuntimeError('Combined CPU stage process trees exceeded 24 GiB')
   if any(p.poll() not in (None,0) for p in processes):raise RuntimeError('A CPU subprocess failed')
   time.sleep(2)
  if any(p.returncode for p in processes):raise RuntimeError('CPU subprocess failed')
 finally:
  for p in processes:
   if p.poll() is None:
    os.killpg(p.pid,signal.SIGTERM)
    try:p.wait(timeout=15)
    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
  for h in handles:h.close()

def main():
 preflight()
 state=read(C/'pipeline_runtime.json');assert state['status']=='failed' and state['stages'][-1]['stage']=='roma_matches'
 latest=state
 save(R/'runtime_before_two_workers.json',state)
 save(R/'cpu_reschedule_two_workers.json',dict(status='rescheduling',started=time.time(),groups=GROUPS,reason='Four-worker RSS guard stopped its own workers; resume with two workers under the unchanged 24 GiB cap',preserves_all_pairs_settings_seeds=True))
 import numpy as np
 completed=[]
 for path in (C/'registration/roma').glob('*.npz'):
  with np.load(path) as data:
   assert len(data.files)>0
   for key in data.files:data[key]
  completed.append(path.name)
 # All original pair outputs belong to this fresh experiment, not another run.
 save(R/'same_run_pair_checkpoint.json',dict(files=completed,hashes={str(C/'registration/roma'/name):sha(C/'registration/roma'/name) for name in completed}))
 env=os.environ.copy();env.update(ROCR_VISIBLE_DEVICES='-1',HIP_VISIBLE_DEVICES='-1',CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',OPENBLAS_NUM_THREADS='1',XFORMERS_DISABLED='1',TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD='1',TOKENIZERS_PARALLELISM='false',CASE_ROOT=str(C),PYTHONPATH=str(B/'experiments/shot_scene_boxes_goal_20260916/deps'))
 for key,name in [('MPLCONFIGDIR','matplotlib'),('XDG_CACHE_HOME','cache'),('YOLO_CONFIG_DIR','yolo')]:env[key]=str(C/'runtime_cache'/name)
 jobs=read(C/'plan.json');suffix=jobs[next(i for i,j in enumerate(jobs) if j['stage']=='roma_matches'):]
 state['stages']=state['stages'][:-1];state['cpu_reschedule_two_workers']=read(R/'cpu_reschedule_two_workers.json');state['status']='running';state.pop('error',None);state.pop('finished',None);state.pop('seconds',None)
 profile=read(C/'runtime_profile.json');profile['roma_cpu_workers']=2;profile['roma_cpu_groups']=GROUPS;save(C/'runtime_profile.json',profile)
 provenance=read(C/'provenance.json');provenance['source_hashes'][str(Path(__file__))]=sha(__file__);dest=C/'code_snapshot'/Path(__file__).relative_to(B);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(__file__,dest);save(C/'provenance.json',provenance)
 save(C/'pipeline_runtime.json',state)
 try:
  for spec in suffix:
   if spec['stage']=='roma_matches':
    commands=[['taskset','-c',','.join(map(str,cores)),str(GEOM),str(A),'--method','roma','--part',str(i),'--parts',str(len(GROUPS))] for i,cores in enumerate(GROUPS)]
    logs=[C/f'roma_cpu_two_part{i}.log' for i in range(len(GROUPS))]
    record=dict(stage='roma_matches',command=commands,started=latest['stages'][-1]['started'],resumed=time.time(),status='running',prior_attempt_record=str(R/'runtime_before_two_workers.json'))
   else:
    commands=[['taskset','-c',','.join(map(str,GROUPS[0])),*spec['command']]];logs=[C/(spec['stage']+'.log')];record=dict(spec,started=time.time(),status='running')
   state['stages'].append(record);save(C/'pipeline_runtime.json',state);print('START',spec['stage'],flush=True)
   monitor(commands,env,logs);record.update(status='success',seconds=time.time()-record['started'],returncode=0);save(C/'pipeline_runtime.json',state);print('END',spec['stage'],record['seconds'],flush=True)
  state['status']='success'
 except BaseException as exc:
  state.update(status='failed',error=repr(exc));state['stages'][-1].update(status='failed',seconds=time.time()-state['stages'][-1]['started']);traceback.print_exc();raise
 finally:
  state.update(finished=time.time(),seconds=time.time()-state['started']);save(C/'pipeline_runtime.json',state);summarize(C,state)
 if state['status']=='success':subprocess.run([CPU,str(R/'report.py')],env=env,check=True)

if __name__=='__main__':main()
