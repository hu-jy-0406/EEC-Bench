import os,time,json,subprocess
from pathlib import Path
r=Path(__file__).resolve().parent;root=r.parents[2];cpus=set(range(28,32));assert os.sched_getaffinity(0)==cpus

def stat():
 return {int(x[0][3:]):list(map(int,x[1:])) for row in Path('/proc/stat').read_text().splitlines() if (x:=row.split()) and x[0].startswith('cpu') and x[0][3:].isdigit()}
a=stat();time.sleep(2);b=stat();util={i:100*(1-(b[i][3]+b[i][4]-a[i][3]-a[i][4])/sum(y-x for x,y in zip(a[i],b[i]))) for i in cpus}
print('CAPACITY_CPU_CHECK',util,flush=True);assert max(util.values())<10,util
py='/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python';st=time.time()
rc=subprocess.call([py,str(root/'EECBench/experiments/study2_detection_only_fresh_20260918/guard_gpu.py'),'2','GPU-aabcddaa244a3d6e','bash',str(r/'run_storymem_capacity.sh')])
(r/'storymem_capacity_status.json').write_text(json.dumps(dict(returncode=rc,seconds=time.time()-st,job=206117,gpu=2,uuid='GPU-aabcddaa244a3d6e',cpus=sorted(cpus),pre_cpu_util=util)))
raise SystemExit(rc)
