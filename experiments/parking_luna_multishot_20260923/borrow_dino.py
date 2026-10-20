#!/usr/bin/env python3
import fcntl,json,os,signal,socket,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
EEC=HERE.parents[1]
HOLO=EEC/'experiments'/'holocine_generation_200_20260922'
CASE=HERE/'shared'/'parking4'
GPU_PYTHON='/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python'
CPU_PYTHON='/vast/users/guangyi.chen/anaconda3/bin/python'
def read(p): return json.loads(Path(p).read_text())
def write(p,x): Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
worker=sys.argv[1]; state_path=HOLO/'workers'/f'{worker}.json'; before=read(state_path)
pid,uuid=before['pid'],before['uuid']; audit=dict(worker=worker,pid=pid,uuid=uuid,job=before['job'],started=time.time(),status='checking')
write(HERE/'dino_handoff.json',audit); paused=False; lockfd=None; leasefd=None
try:
 if before['node']!=socket.gethostname() or before['job']!=os.environ['SLURM_JOB_ID']: raise RuntimeError('wrong node/job')
 if not (Path('/proc')/str(pid)).exists(): raise RuntimeError('worker absent')
 cmd=(Path('/proc')/str(pid)/'cmdline').read_bytes().replace(b'\0',b' ')
 if b'holocine_generation_200_20260922/campaign.py' not in cmd or worker.encode() not in cmd: raise RuntimeError('wrong process')
 lockfd=os.open(HOLO/'queue.lock',os.O_RDWR|os.O_CREAT,0o600); fcntl.flock(lockfd,fcntl.LOCK_EX)
 current=read(state_path); queue=read(HOLO/'queue.json')
 # campaign.py writes completion evidence to attempts/*/result.json, then clears task; queue.json does not retain completed worker/result rows. A fresh phase-barrier heartbeat plus no running claim is the reliable completion boundary.
 if current['pid']!=pid or current['state']!='waiting_for_phase_barrier' or time.time()-current['heartbeat']>=90 or any(x.get('worker')==worker and x.get('status')=='running' for x in queue['tasks']): raise RuntimeError('not a completed idle worker')
 audit.update(status='pausing_completed_worker',worker_before=current); write(HERE/'dino_handoff.json',audit)
 os.kill(pid,signal.SIGSTOP); os.kill(pid,signal.SIGTERM); os.kill(pid,signal.SIGCONT); paused=True
 deadline=time.time()+60
 while (Path('/proc')/str(pid)).exists() and (Path('/proc')/str(pid)/'stat').read_text().split()[2] != 'Z' and time.time()<deadline: time.sleep(.25)
 if (Path('/proc')/str(pid)).exists() and (Path('/proc')/str(pid)/'stat').read_text().split()[2] != 'Z': raise RuntimeError('worker did not exit')
 lease=HOLO/'gpu_leases'/f'{socket.gethostname()}_{uuid}.lock'; leasefd=os.open(lease,os.O_RDWR|os.O_CREAT,0o600); fcntl.flock(leasefd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 fcntl.flock(lockfd,fcntl.LOCK_UN); os.close(lockfd); lockfd=None
 audit['status']='leased'; write(HERE/'dino_handoff.json',audit)
 cache=Path('/tmp')/'eecbench_parking_dino_miopen'/uuid; cache.mkdir(parents=True,exist_ok=True)
 env=os.environ.copy(); env.update(ROCR_VISIBLE_DEVICES=uuid,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',MIOPEN_USER_DB_PATH=str(cache),MIOPEN_CUSTOM_CACHE_DIR=str(cache))
 for k in ('HIP_VISIBLE_DEVICES','CUDA_VISIBLE_DEVICES','GPU_DEVICE_ORDINAL'): env.pop(k,None)
 with (HERE/'dino_run.log').open('w') as log: subprocess.run([GPU_PYTHON,str(EEC/'scripts'/'gs_entity_appearance.py'),'dino','--runs',str(CASE/'appearance'/'canonical')],check=True,env=env,stdout=log,stderr=subprocess.STDOUT)
 subprocess.run([CPU_PYTHON,str(EEC/'scripts'/'gs_entity_appearance_scoring.py'),'report','--runs',str(CASE/'appearance'/'compact'),'--out',str(CASE/'appearance'/'report')],check=True,env=env)
 audit['status']='success'
except BaseException as e:
 audit.update(status='failed',error=repr(e)); raise
finally:
 audit['finished']=time.time(); write(HERE/'dino_handoff.json',audit)
 if lockfd is not None:
  fcntl.flock(lockfd,fcntl.LOCK_UN); os.close(lockfd)
 if leasefd is not None: os.close(leasefd)
 if paused:
  restore=['bash',str(HERE/'restore_worker.sbatch.sh'),worker,before['mode'],str(worker.rsplit('gpu',1)[1]),uuid,','.join(map(str,before['cpus']))]
  subprocess.Popen(restore,stdout=(HERE/'dino_restore.log').open('w'),stderr=subprocess.STDOUT,start_new_session=True)
