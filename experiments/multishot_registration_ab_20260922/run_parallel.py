"""Three episodes in parallel on separate allocated GPUs; common frozen inputs per method."""
import os,sys,re,json,socket,subprocess,fcntl,time,traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_gs_integrated import CPU,FRONT,save,read,sha
job=os.environ['SLURM_JOB_ID'];host=socket.gethostname();names=['parking4','bedroom4','diner8'];fds=[]
# The node's GRES file list explicitly includes /dev/kfd. Full allocation avoids
# the observed single-GRES HIP invisibility, without changing cgroups/devices.
indices=[]
for part in os.environ['SLURM_JOB_GPUS'].split(','):
 if '-' in part:a,b=map(int,part.split('-'));indices+=list(range(a,b+1))
 else:indices.append(int(part))
assert len(indices)>=4,indices
entries=[]
for line in Path('/etc/slurm/gres.conf').read_text().splitlines():
 d=dict(t.split('=',1) for t in line.split() if '=' in t)
 if d.get('Name')=='gpu' and d.get('Type')=='mi210':entries.append(d['File'])
permissions={}
for path in ['/dev/kfd']+[entries[i] for i in indices if entries[i].startswith('/dev/dri/render')]:
 try:f=os.open(path,os.O_RDWR);os.close(f);permissions[path]='open_ok'
 except OSError as e:permissions[path]=repr(e)
save(R/f'device_permissions_{job}.json',permissions);assert permissions['/dev/kfd']=='open_ok',permissions
smi=subprocess.check_output(['rocm-smi','--showuniqueid'],text=True);visible=re.findall(r'GPU\[(\d+)\].*Unique ID:\s*0x([0-9a-fA-F]+)',smi);cards=[]
for idx in indices:
 device=entries[idx]
 if not re.fullmatch(r'/dev/dri/renderD\d+',device):continue
 uuid0=(Path('/sys/class/drm')/Path(device).name/'device/unique_id').read_text().strip();matches=[x for x in visible if int(x[1],16)==int(uuid0,16)]
 assert len(matches)==1,(idx,device,uuid0,visible)
 cards.append(dict(gres_index=idx,device=device,smi_index=int(matches[0][0]),uuid='GPU-'+format(int(uuid0,16),'016x')))
# Reserve each chosen card through the shared nonblocking lease BEFORE guard.
selected=[]
for card in cards:
 path=B/'experiments/holocine_generation_200_20260922/gpu_leases'/f'{host}_{card["uuid"]}.lock';path.parent.mkdir(exist_ok=True)
 fd=os.open(path,os.O_RDWR|os.O_CREAT,0o600)
 try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:os.close(fd);continue
 cmd=[CPU,str(FRONT/'guard_gpu.py'),str(card['smi_index']),card['uuid'],CPU,'-c','print("guard passed")']
 with (R/f'guard_{job}_{card["smi_index"]}.log').open('w') as f:proc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
 if proc.returncode:os.close(fd);continue
 selected.append(card);fds.append(fd)
 if len(selected)==3:break
assert len(selected)==3,('Need three genuinely idle allocated cards',selected)
affinity=sorted(os.sched_getaffinity(0));assert len(affinity)>=24,affinity
save(R/f'allocated_devices_{job}.json',dict(job=job,host=host,indices=indices,gres_files=entries,visible=visible,selected=selected,allowed_cpus=affinity))
state=dict(status='running',started=time.time(),job=job,node=host,devices=selected,episodes={},stages=[],source_hashes={str(p):sha(p) for p in list(R.glob('*.py'))+list(R.glob('*.txt'))})
def run(label,cmd,env):
 t=time.time();print('START',label,flush=True)
 with (R/(label+'.log')).open('x') as f:p=subprocess.run(list(map(str,cmd)),env=env,stdout=f,stderr=subprocess.STDOUT)
 row=dict(stage=label,started=t,seconds=time.time()-t,returncode=p.returncode);state['stages'].append(row);print('END',label,row,flush=True)
 if p.returncode:raise RuntimeError(row)
 return row

def episode(i,name,card):
 env=os.environ.copy();env.update(ROCR_VISIBLE_DEVICES=card['uuid'],OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='4',OMP_NUM_THREADS='4')
 for k in ['HIP_VISIBLE_DEVICES','CUDA_VISIBLE_DEVICES','GPU_DEVICE_ORDINAL']:env.pop(k,None)
 cpus=affinity[i*8:(i+1)*8];prefix=['taskset','-c',','.join(map(str,cpus)),CPU];gpu=card['smi_index'];uuid=card['uuid'];case=R/'shared'/name
 # A tiny HIP probe verifies the UUID selects exactly one device before model loads.
 probe=B/'experiments/study_inconsistent_3/geocalib_boxer_20260913/venv/bin/python'
 run('hip_probe_'+name,['taskset','-c',','.join(map(str,cpus)),probe,'-c',"import torch; assert torch.cuda.device_count()==1; x=torch.ones(1024,device='cuda'); torch.cuda.synchronize(); print(torch.cuda.get_device_name(), float(x.sum()))"],env)
 run('frontend_'+name,prefix+[R/'frontend.py',name,gpu,uuid],env)
 with ThreadPoolExecutor(max_workers=2) as pool:
  initial=pool.submit(run,'initial_'+name,prefix+[R/'model_stages.py','initial',case],env)
  direct=pool.submit(run,'direct_'+name,prefix+[R/'model_stages.py','direct',case],env)
  initial.result();run('optimization_'+name,prefix+[R/'optimize.py',case,gpu,uuid],env);direct.result()
 return dict(status='success',gpu=card,cpus=cpus)
try:
 with ThreadPoolExecutor(max_workers=3) as pool:
  futures={pool.submit(episode,i,n,c):n for i,(n,c) in enumerate(zip(names,selected))}
  errors=[]
  for f in as_completed(futures):
   name=futures[f]
   try:state['episodes'][name]=f.result()
   except BaseException as e:state['episodes'][name]=dict(status='failed',error=repr(e));errors.append(name)
   save(R/'runtime.json',state)
 if errors:raise RuntimeError(errors)
 env=os.environ.copy();env.update(ROCR_VISIBLE_DEVICES='-1',CUDA_VISIBLE_DEVICES='',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
 run('analysis',['taskset','-c',str(affinity[0]),CPU,R/'analyze.py'],env);state['status']='success'
except BaseException as e:state.update(status='failed',error=repr(e));raise
finally:
 state.update(finished=time.time(),seconds=time.time()-state['started']);save(R/'runtime.json',state)
 for fd in fds:os.close(fd)
