"""Three frozen-front experiments, bounded API parallelism, one leased GPU."""
import os,sys,json,time,subprocess,fcntl,socket,re,traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_gs_integrated import CPU,FRONT,save,read
# Slurm allocation-owned physical index only. Never guess visibility ordinals.
ids=os.environ.get('SLURM_JOB_GPUS','');assert re.fullmatch(r'\d+',ids),('Expected one explicit allocated physical GPU',ids)
# Capture scheduler and kernel device mapping before choosing the ROCm index.
probe_cmd="""hostname
printenv | sort | grep -E '^(SLURM.*GPU|ROCR|HIP_VISIBLE|CUDA_VISIBLE)='
ls -l /dev/dri
cat /etc/slurm/gres.conf 2>/dev/null || true
for p in /sys/class/drm/card[0-9]*/device/unique_id; do echo "$p $(cat "$p")"; done
rocm-smi --showuniqueid --showbus
"""
probe=subprocess.run(['bash','-c',probe_cmd],capture_output=True,text=True)
save(R/('device_probe_'+os.environ['SLURM_JOB_ID']+'.json'),dict(stdout=probe.stdout,stderr=probe.stderr,env={k:v for k,v in os.environ.items() if k.startswith(('SLURM_', 'ROCR_', 'HIP_VISIBLE', 'CUDA_VISIBLE'))}))
out=subprocess.check_output(['rocm-smi','--showuniqueid'],text=True)
visible=re.findall(r'GPU\[(\d+)\].*Unique ID:\s*0x([0-9a-fA-F]+)',out)
# GRES indices enumerate the node's configured File entries, including /dev/kfd
# on this cluster. Resolve the allocated render node, then compare numeric UUIDs.
entries=[]
for line in Path('/etc/slurm/gres.conf').read_text().splitlines():
 fields=dict(x.split('=',1) for x in line.split() if '=' in x)
 if fields.get('Name')=='gpu' and fields.get('Type')=='mi210':entries.append(fields['File'])
assert int(ids)<len(entries),('Unknown GRES file index',ids,entries)
device=entries[int(ids)]
assert re.fullmatch(r'/dev/dri/renderD\d+',device),('Allocated GRES is not a render GPU',device)
kernel_uuid=(Path('/sys/class/drm')/Path(device).name/'device/unique_id').read_text().strip()
matches=[x for x in visible if int(x[1],16)==int(kernel_uuid,16)]
assert len(matches)==1,('Allocated kernel UUID not uniquely visible',device,kernel_uuid,visible)
gpu=int(matches[0][0]);uuid='GPU-'+format(int(kernel_uuid,16),'016x')
save(R/('verified_device_'+os.environ['SLURM_JOB_ID']+'.json'),dict(smi_index=gpu,uuid=uuid,slurm_gres_index=int(ids),gres_file=device,kernel_uuid=kernel_uuid,proof='actual gres.conf ordered File entries and sysfs render-device UUID match visible ROCm numeric UUID'))
save(R/('gpu_mapping_'+os.environ['SLURM_JOB_ID']+'.json'),dict(slurm_job_gpus=ids,visible_cards=visible,selected_smi_index=gpu,uuid=uuid,host=socket.gethostname()))
lease=B/'experiments/holocine_generation_200_20260922/gpu_leases'/f'{socket.gethostname()}_{uuid}.lock';lease.parent.mkdir(exist_ok=True)
fd=os.open(lease,os.O_RDWR|os.O_CREAT,0o600);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
subprocess.run([CPU,str(FRONT/'guard_gpu.py'),str(gpu),uuid,CPU,'-c','print("initial GPU guard passed")'],check=True)
os.environ['ROCR_VISIBLE_DEVICES']=uuid
for k in ['HIP_VISIBLE_DEVICES','CUDA_VISIBLE_DEVICES']:os.environ.pop(k,None)
os.environ.update(OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='4',OMP_NUM_THREADS='4')
state=dict(status='running',started=time.time(),job=os.environ.get('SLURM_JOB_ID'),node=socket.gethostname(),gpu=gpu,uuid=uuid,steps=[])
def run(label,cmd):
 t=time.time();print('START',label,flush=True)
 with (R/(label+'.log')).open('x') as f:p=subprocess.run(list(map(str,cmd)),stdout=f,stderr=subprocess.STDOUT)
 row=dict(stage=label,seconds=time.time()-t,returncode=p.returncode);state['steps'].append(row);print('END',label,row,flush=True)
 if p.returncode:raise RuntimeError(row)
 return row
try:
 with ThreadPoolExecutor(max_workers=4) as pool:
  api={}
  for name in ['parking4','bedroom4','diner8']:
   run('frontend_'+name,[CPU,R/'frontend.py',name,gpu,uuid]);case=R/'shared'/name
   api[name]=(pool.submit(run,'initial_'+name,[CPU,R/'model_stages.py','initial',case]),pool.submit(run,'direct_'+name,[CPU,R/'model_stages.py','direct',case]))
   save(R/'runtime.json',state)
  for name in ['parking4','bedroom4','diner8']:
   api[name][0].result();run('optimization_'+name,[CPU,R/'optimize.py',R/'shared'/name,gpu,uuid]);save(R/'runtime.json',state)
  for fs in api.values():
   for f in fs:f.result()
 run('analysis',[CPU,R/'analyze.py']);state['status']='success'
except BaseException as e:state.update(status='failed',error=repr(e));raise
finally:state.update(finished=time.time(),seconds=time.time()-state['started']);save(R/'runtime.json',state);os.close(fd)
