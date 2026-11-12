#!/usr/bin/env python3
"""Run four seeds plus one same-seed control, fresh processes and GPU checks."""
import argparse,json,os,re,shutil,socket,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path,required=True);p.add_argument('--gpu',type=int,required=True);p.add_argument('--output',type=Path);p.add_argument('--models',nargs='+',choices=['yoloe','florence'],default=['yoloe','florence']);a=p.parse_args()
root=a.experiment.resolve();out=a.output.resolve() if a.output else root/'seed_sensitivity';out.mkdir(parents=True,exist_ok=True)
code=out/'code';code.mkdir(exist_ok=True)
for name in ['detect_keyframes_local.py','run_local_detector.sh']:
 target=code/name
 if target.exists():raise FileExistsError(target)
 shutil.copy2(Path(__file__).parent/name,target)
inputs=root.parent/'entity_discovery_iterations/scope_retention_batch_01_seeds1101_1202_1303/frozen_inputs'
plan=[('s0',0),('s1',1),('s42',42),('s2026',2026),('s0_repeat',0)]
state=dict(status='running',host=socket.gethostname(),pid=os.getpid(),slurm_job=os.getenv('SLURM_JOB_ID'),gpu=a.gpu,plan=plan,runs=[])
def save(): (out/'batch.json').write_text(json.dumps(state,indent=2))
save()
for model in a.models:
 for tag,seed in plan:
  name=f'{model}_{tag}';result=out/name
  if result.exists():raise FileExistsError(result)
  # Fail closed if utilization, VRAM or process ownership is not clear.
  status=subprocess.check_output(['rocm-smi','--showuse','--showmeminfo','vram','--showpidgpus'],text=True)
  (out/f'{name}.gpu_check.txt').write_text(status)
  use=re.search(rf'GPU\[{a.gpu}\].*GPU use \(%\):\s*(\d+)',status)
  mem=re.search(rf'GPU\[{a.gpu}\].*VRAM Total Used Memory \(B\):\s*(\d+)',status)
  mappings=re.findall(r'PID (\d+) is using (\d+) DRM device\(s\):\s*\n([^\n]*)',status)
  occupied=[pid for pid,n,ids in mappings if int(n)>0 and str(a.gpu) in ids.split()]
  if not use or not mem or int(use[1])!=0 or int(mem[1])>100*1024**2 or occupied:
   state.update(status='blocked_gpu_busy',pending=name);save();raise RuntimeError('GPU no longer idle; stopped without launching')
  weights=root/'weights'/('yoloe-v8l-seg-pf.pt' if model=='yoloe' else 'Florence-2-large-ft')
  cmd=['bash',str(code/'run_local_detector.sh'),str(a.gpu),str(root/'venv/bin/python'),'--model',model,'--weights',str(weights),'--input-root',str(inputs),'--output',str(result),'--seed',str(seed)]
  record=dict(name=name,seed=seed,model=model,status='running',command=cmd,start=time.time());state['runs'].append(record);save()
  env=os.environ.copy();env['PYTHONHASHSEED']=str(seed)
  with (out/f'{name}.log').open('w') as log:
   proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,env=env);record['pid']=proc.pid;save();rc=proc.wait()
  record.update(exit_code=rc,end=time.time(),status='success' if rc==0 else 'failed');save()
  print(name,record['status'],flush=True)
  if rc:state['status']='failed';save();raise SystemExit(rc)
state['status']='success';save()
