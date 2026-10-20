#!/usr/bin/env python3
"""Run after an audited waiting worker has been paused; always restore it."""
import fcntl, os, subprocess, sys, time
from pathlib import Path

R=Path(__file__).resolve().parent; B=R.parents[1]; sys.path.insert(0,str(B/'scripts'))
from run_gs_integrated import save, sha, CPU, FRONT, GEOM
H=B/'experiments/holocine_generation_200_20260922'; worker='node284_gpu0'; gpu=0; uuid='GPU-62c7c36f3046f723'; cores=[0,1,2,4]
statefile=H/'workers'/f'{worker}.json'
import json
ws=json.loads(statefile.read_text()); old_pid=int(ws['pid'])
assert ws['state']=='waiting_for_phase_barrier' and not Path(f'/proc/{old_pid}').exists(), 'worker must already be safely paused'
lock=H/'gpu_leases'/f'{os.uname().nodename}_{uuid}.lock'; fd=os.open(lock,os.O_RDWR|os.O_CREAT,0o600); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
env=os.environ.copy(); env.update(ROCR_VISIBLE_DEVICES=uuid,OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='4',OMP_NUM_THREADS='4')
for k in ['HIP_VISIBLE_DEVICES','CUDA_VISIBLE_DEVICES','GPU_DEVICE_ORDINAL']: env.pop(k,None)
os.sched_setaffinity(0,cores); os.nice(10)
state=dict(status='running',started=time.time(),worker_prepaused=True,worker_pid_before=old_pid,gpu=gpu,uuid=uuid,stages=[])
def run(label,cmd):
 t=time.time()
 with (R/(label+'_parking4.log')).open('w') as log: p=subprocess.run(list(map(str,cmd)),env=env,stdout=log,stderr=subprocess.STDOUT)
 row=dict(stage=label,seconds=time.time()-t,returncode=p.returncode);state['stages'].append(row);save(R/'runtime_parking4.json',state)
 if p.returncode:raise RuntimeError(row)
try:
 run('hip_probe',[CPU,FRONT/'guard_gpu.py',gpu,uuid,GEOM,'-c','import torch; assert torch.cuda.device_count()==1; x=torch.ones(1024,device="cuda"); torch.cuda.synchronize(); print(torch.cuda.get_device_name(),float(x.sum()))'])
 run('frontend',[CPU,R/'frontend.py',gpu,uuid])
 run('direct_prompt_bound_luna',[CPU,R/'registration.py'])
 state['status']='success'
except BaseException as exc:
 state.update(status='failed',error=repr(exc));raise
finally:
 state.update(finished=time.time(),seconds=time.time()-state['started']);save(R/'runtime_parking4.json',state);os.close(fd)
 restore=[str(R/'restore_worker.sbatch.sh'),worker,ws['mode'],str(gpu),uuid,','.join(map(str,ws['cpus']))]
 with (R/'restore_parking4.log').open('w') as log: p=subprocess.Popen(['bash',*restore],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 save(R/'restore_requested.json',dict(worker=worker,pid=p.pid,requested=time.time(),command=restore))
