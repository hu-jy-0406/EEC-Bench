"""User-authorized handoff ONLY after a HoloCine worker finished its episode."""
import os,sys,socket,json,time,signal,fcntl,subprocess,traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
R=Path(__file__).resolve().parent;B=R.parents[1];H=B/'experiments/holocine_generation_200_20260922';sys.path.insert(0,str(B/'scripts'))
from run_gs_integrated import read,save,sha,CPU,FRONT,GEOM
name,worker=sys.argv[1:];statefile=H/'workers'/f'{worker}.json';worker_state=read(statefile);pid=worker_state['pid'];uuid=worker_state['uuid'];gpu=int(worker.rsplit('gpu',1)[1]);assert worker_state['node']==socket.gethostname();assert worker_state['job']==os.environ['SLURM_JOB_ID']
cmdline=(Path('/proc')/str(pid)/'cmdline').read_bytes().replace(b'\0',b' ');assert b'holocine_generation_200_20260922/campaign.py' in cmdline and worker.encode() in cmdline
assert (Path('/proc')/str(pid)).stat().st_uid==os.getuid()
lease=H/'gpu_leases'/f'{socket.gethostname()}_{uuid}.lock';lease.parent.mkdir(exist_ok=True);fd=os.open(lease,os.O_RDWR|os.O_CREAT,0o600)
lease_owned=False
try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);lease_owned=True
except BlockingIOError:pass
# Queue lock prevents the selected process from claiming a new episode between
# proving no active assignment and stopping it. Other worker tasks are unchanged.
with (H/'queue.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 q=read(H/'queue.json');ws=read(statefile);assert ws['pid']==pid and ws['state']=='waiting_for_phase_barrier' and time.time()-ws['heartbeat']<90,ws
 assert not any(t['status']=='running' and t.get('worker')==worker for t in q['tasks'])
 completed=[t for t in q['tasks'] if t.get('worker')==worker and t['status']=='done']; assert completed, 'No completed worker episode provenance'; last=completed[-1]; assert last['result']['full_decode'] and last['result']['finite_latents_and_decoder']
 audit=dict(worker_before=ws,queue_sha256=sha(H/'queue.json'),completed_episode=last,original_cmdline=cmdline.decode(),authorization='User approved temporary single-card loan for recovered parking geometry rerun after episode completion',started=time.time(),status='pausing_completed_worker')
 save(R/'handoff'/f'{name}.json',audit)
 os.kill(pid,signal.SIGSTOP);os.kill(pid,signal.SIGTERM);os.kill(pid,signal.SIGCONT)
# No GPU process is launched until original process exit and fresh idle guard.
deadline=time.time()+60
while Path(f'/proc/{pid}').exists() and time.time()<deadline:
 try:
  if Path(f'/proc/{pid}/stat').read_text().split()[2]=='Z':break
 except FileNotFoundError:break
 time.sleep(.25)
assert not Path(f'/proc/{pid}').exists() or Path(f'/proc/{pid}/stat').read_text().split()[2]=='Z','Selected completed worker has not exited'
if not lease_owned:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
audit.update(status='leased_after_completed_episode',paused=time.time());save(R/'handoff'/f'{name}.json',audit)
# Reuse released worker cores only after a fresh utilization/process check.
cores=ws['cpus'];allowed=os.sched_getaffinity(0);assert set(cores)<=allowed
ps=subprocess.check_output(['ps','-eo','pid,psr,pcpu,rss,comm','--sort=-pcpu'],text=True)
def sample():
 return {int(t[0][3:]):list(map(int,t[1:])) for l in Path('/proc/stat').read_text().splitlines() if (t:=l.split())[0].startswith('cpu') and t[0][3:].isdigit()}
a=sample();time.sleep(1);b=sample();loads={c:1-(b[c][3]+b[c][4]-a[c][3]-a[c][4])/max(1,sum(b[c][:8])-sum(a[c][:8])) for c in cores}
assert max(loads.values())<.3,('Released cores unexpectedly busy',loads)
os.sched_setaffinity(0,cores);os.nice(10)
cg=Path('/sys/fs/cgroup')/Path('/proc/self/cgroup').read_text().strip().split(':')[-1].lstrip('/');jobcg=next(p for p in [cg,*cg.parents] if p.name.startswith('job_'));mem={k:(jobcg/k).read_text() for k in ['memory.max','memory.current','memory.stat','memory.events']};anon=int(dict(x.split() for x in mem['memory.stat'].splitlines())['anon']);assert int(mem['memory.max'])-anon>16*2**30
save(R/'handoff'/f'{name}_resources.json',dict(cpus=cores,cpu_loads=loads,processes=ps.splitlines()[:20],memory=mem,job=os.environ['SLURM_JOB_ID'],gpu=gpu,uuid=uuid))
env=os.environ.copy();env.update(ROCR_VISIBLE_DEVICES=uuid,OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='4',OMP_NUM_THREADS='4')
for k in ['HIP_VISIBLE_DEVICES','CUDA_VISIBLE_DEVICES','GPU_DEVICE_ORDINAL']:env.pop(k,None)
state=dict(status='running',started=time.time(),worker_borrowed=worker,job=os.environ['SLURM_JOB_ID'],gpu=gpu,uuid=uuid,stages=[],source_hashes={str(p):sha(p) for p in list(R.glob('*.py'))+list(R.glob('*.txt'))})
def run(label,cmd):
 t=time.time();print(name,'START',label,flush=True)
 with (R/(label+'_'+name+'.log')).open('x') as f:p=subprocess.run(list(map(str,cmd)),env=env,stdout=f,stderr=subprocess.STDOUT)
 row=dict(stage=label,seconds=time.time()-t,returncode=p.returncode);state['stages'].append(row);save(R/f'runtime_{name}.json',state);print(name,'END',label,row,flush=True)
 if p.returncode:raise RuntimeError(row)
try:
 run('hip_probe',[CPU,FRONT/'guard_gpu.py',gpu,uuid,GEOM,'-c',"import torch; assert torch.cuda.device_count()==1; x=torch.ones(1024,device='cuda'); torch.cuda.synchronize(); print(torch.cuda.get_device_name(),float(x.sum()))"])
 run('frontend',[CPU,R/'frontend.py',name,gpu,uuid]);case=R/'shared'/name
 with ThreadPoolExecutor(max_workers=2) as pool:
  initial=pool.submit(run,'initial',[CPU,R/'model_stages.py','initial',case]);direct=pool.submit(run,'direct',[CPU,R/'model_stages.py','direct',case])
  initial.result();run('optimization',[CPU,R/'optimize.py',case,gpu,uuid]);direct.result()
 state['status']='success'
except BaseException as e:state.update(status='failed',error=repr(e));raise
finally:
 state.update(finished=time.time(),seconds=time.time()-state['started']);save(R/f'runtime_{name}.json',state)
 audit.update(status='experiment_finished_lease_released',experiment_status=state['status'],released=time.time());save(R/'handoff'/f'{name}.json',audit);os.close(fd)
