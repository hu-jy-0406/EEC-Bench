import subprocess,time,json,os
from pathlib import Path
r=Path(__file__).resolve().parent;root=r.parents[2]
assert (r/'storymem_first_keyframe_recovery.json').exists()
assert list((r/'outputs/storymem_official').glob('*keyframe*.jpg'))
start=time.time();print('MEMORY_PHASE_START',start,'CPU',sorted(os.sched_getaffinity(0)),flush=True)
py='/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python'
with (r/'logs/storymem_memory_terminal.log').open('w') as f:
 rc=subprocess.call([py,str(root/'EECBench/experiments/study2_detection_only_fresh_20260918/guard_gpu.py'),'4','GPU-24ee801b7c402006','bash',str(r/'run_storymem.sh')],stdout=f,stderr=subprocess.STDOUT)
(r/'storymem_memory_status.json').write_text(json.dumps(dict(phase='memory',start=start,end=time.time(),seconds=time.time()-start,returncode=rc,cpus=sorted(os.sched_getaffinity(0)),job=206117)))
print('MEMORY_PHASE_END',rc,flush=True);raise SystemExit(rc)
