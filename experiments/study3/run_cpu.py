"""CPU-only Study3, bounded to four quiet allocated cores and 24 GiB process RSS."""
import hashlib,json,os,shutil,socket,subprocess,sys,time,traceback,signal
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_gs_integrated import read,save,sha,CPU,GEOM,FRONT,REG,prepare,plan,execute
from gs_runtime_profile import profile
from run_isolated_shot_static_3d import owned_compute_job
CASE=R/'run_cpu02';D=R/'cpu_adapters'

def choose_cores():
 # Allocation191764 owns these cores; do not use the unallocated half of the node.
 allowed=(set(range(32))|set(range(64,96))) & os.sched_getaffinity(0)
 def counters():
  result={}
  for line in Path('/proc/stat').read_text().splitlines():
   cols=line.split()
   if cols[0].startswith('cpu') and cols[0][3:].isdigit():
    vals=list(map(int,cols[1:]));result[int(cols[0][3:])]=(sum(vals[:8]),vals[3]+vals[4])
  return result
 before=counters();time.sleep(1);after=counters();busy={c:1-(after[c][1]-before[c][1])/max(1,after[c][0]-before[c][0]) for c in allowed}
 cores=sorted(allowed,key=lambda c:(busy[c],c))[:4]
 assert len(cores)==4 and all(busy[c]<.15 for c in cores),'No four quiet allocated CPU cores'
 os.sched_setaffinity(0,cores);return dict(cores=cores,sampled_busy={str(c):busy[c] for c in cores})

def monitored_run(command,**kw):
 import psutil
 p=subprocess.Popen(command,start_new_session=True,**kw);peak=0.;start=time.time();process=psutil.Process(p.pid)
 while p.poll() is None:
  try:
   children=process.children(recursive=True);rss=sum(x.memory_info().rss for x in [process,*children] if x.is_running());peak=max(peak,rss)
   if rss>24*1024**3:
    for child in reversed(children):
     try:child.terminate()
     except psutil.NoSuchProcess:pass
    p.terminate();p.wait(timeout=20);raise RuntimeError('CPU process tree exceeded 24 GiB RSS safety limit')
   save(R/'cpu_stage_monitor.json',dict(pid=p.pid,seconds=time.time()-start,rss_bytes=rss,peak_rss_bytes=peak,command=command,device='cpu'))
  except psutil.NoSuchProcess:pass
  time.sleep(5)
 return subprocess.CompletedProcess(command,p.returncode)

def main():
 state=dict(status='starting',device='cpu',started=time.time(),host=socket.gethostname(),pid=os.getpid(),cancelled_gpu_job=200642,case_directory=str(CASE))
 save(R/'status.json',state)
 try:
  job=owned_compute_job();assert job=='191764' or str(job)=='191764',repr(job)
  assert socket.gethostname().split('.')[0]=='auh7-1b-gpu-306'
  state.update(job_id=str(job),cpu_binding=choose_cores());save(R/'status.json',state)
  env=os.environ.copy();env.update(ROCR_VISIBLE_DEVICES='-1',HIP_VISIBLE_DEVICES='-1',CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',OPENBLAS_NUM_THREADS='1',XFORMERS_DISABLED='1',TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD='1',TOKENIZERS_PARALLELISM='false',CASE_ROOT=str(CASE),PYTHONPATH=str(B/'experiments/shot_scene_boxes_goal_20260916/deps'))
  for k,n in [('MPLCONFIGDIR','matplotlib_cpu'),('XDG_CACHE_HOME','cache_cpu'),('YOLO_CONFIG_DIR','yolo_cpu')]:
   d=R/'runtime_cache'/n;d.mkdir(parents=True,exist_ok=True);env[k]=str(d)
  subprocess.run([GEOM,'-c','import torch; assert not torch.cuda.is_available() and torch.cuda.device_count()==0; print("CPU_ONLY_CONFIRMED",torch.__version__)'],env=env,check=True)
  from run import prepare_inputs
  prepare_inputs()
  prepare(CASE,R/'manifest.json',R/'narrative.json',FRONT/'study2/yyfz233--Pi3X_download.json',B/'experiments/study_inconsistent_3/geocalib_boxer_20260913/weights/geocalib-pinhole.tar')
  runtime=profile('safe_spatial_medium');runtime.update(execution_device='cpu',cpu_threads=4,precision='FP32 local models; device-dependent numerical differences possible',overlap_roma_with_identity=False);save(CASE/'runtime_profile.json',runtime)
  jobs=plan(CASE,0,'unused-cpu','identity','safe_spatial_medium')
  for spec in jobs:
   c=spec['command']
   if len(c)>1 and Path(c[1]).name=='guard_gpu.py':c=c[4:]
   stage=spec['stage']
   if stage=='detection_and_clustering':
    i=c.index('--gpu');c[i:i+2]=['--device','cpu'];c+=['--detector-timeout','7200']
   elif stage=='geocalib':c=[GEOM,str(D/'calibrate_cpu.py'),str(CASE)]
   elif stage.startswith('pi3x_'):c[1]=str(D/'geometry_cpu.py')
   elif stage.startswith('boxer_'):c[1]=str(D/'boxer_cpu.py')
   elif stage=='roma_matches':c[1]=str(D/'roma_cpu.py')
   spec['command']=list(map(str,c))
  save(R/'cpu_plan.json',jobs)
  provenance=read(CASE/'provenance.json');sources=set(provenance['source_hashes'])|{str(p) for p in D.glob('*') if p.is_file()}|{str(Path(__file__)),str(R/'report.py')}
  snapshot=R/'code_snapshot_cpu';snapshot.mkdir()
  hashes={}
  for source in sorted(sources):
   p=Path(source);dst=snapshot/p.relative_to(B);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst);hashes[str(p)]=sha(p)
  save(R/'source_hashes.json',hashes)
  state.update(status='running',cpu_threads=4,rss_limit_gib=24);save(R/'status.json',state)
  execute(CASE,jobs,env,job,run=monitored_run,overlap_roma=False);state['status']='success'
 except BaseException as exc:state.update(status='failed',error=repr(exc));traceback.print_exc()
 finally:
  state.update(ended=time.time(),seconds=time.time()-state['started']);save(R/'status.json',state)
  result=subprocess.run([CPU,str(R/'report.py')])
  if result.returncode:state.update(status='failed',report_returncode=result.returncode);save(R/'status.json',state)
 return 0 if state['status']=='success' else 1
if __name__=='__main__':raise SystemExit(main())
