import os,time,subprocess,json
from pathlib import Path
r=Path(__file__).resolve().parent;root=r.parents[2]
# Own CPU process runs inside the existing Slurm allocation. It never reserves a GPU while waiting.
need=[r/'models'/x/'download_complete.json' for x in ['Wan2.2-T2V-A14B','HPSv3','Qwen2-VL-7B-Instruct']]
need.append(r/'models/CLIP/provenance.json')
while not all(p.exists() for p in need) or not (r/'storymem_import_ready.json').exists():
 print('WAIT',time.time(),[str(p.parent.name) for p in need if not p.exists()],flush=True);time.sleep(30)
py='/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python'
guard=root/'EECBench/experiments/study2_detection_only_fresh_20260918/guard_gpu.py'
for phase,args in [('first',['--t2v_first_shot']),('memory',[])]:
 if phase=='memory':
  while not all((r/'models'/x/'download_complete.json').exists() for x in ['Wan2.2-I2V-A14B','StoryMem']):time.sleep(30)
 start=time.time();log=r/'logs'/f'storymem_{phase}_terminal.log'
 with log.open('w') as f:
  rc=subprocess.call([py,str(guard),'4','GPU-24ee801b7c402006','bash',str(r/'run_storymem.sh'),*args],stdout=f,stderr=subprocess.STDOUT)
 (r/f'storymem_{phase}_status.json').write_text(json.dumps(dict(phase=phase,start=start,end=time.time(),seconds=time.time()-start,returncode=rc)))
 print('PHASE',phase,rc,flush=True)
 if rc:raise SystemExit(rc)
