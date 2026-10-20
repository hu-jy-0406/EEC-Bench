import os,time,json
from pathlib import Path
pid=3862738; chosen=set(range(24,28)); root=Path('/sys/fs/cgroup/system.slice/slurmstepd.scope/job_206117')
def stat():
 out={}
 for row in Path('/proc/stat').read_text().splitlines():
  x=row.split()
  if x and x[0].startswith('cpu') and x[0][3:].isdigit():out[int(x[0][3:])]=list(map(int,x[1:]))
 return out
a=stat();time.sleep(2);b=stat();util={i:100*(1-(b[i][3]+b[i][4]-a[i][3]-a[i][4])/sum(y-x for x,y in zip(a[i],b[i]))) for i in sorted(chosen)}
print('CPU_UTIL',util,flush=True)
def expand(s):
 out=set()
 for part in s.strip().split(','):
  if '-' in part:l,h=map(int,part.split('-'));out.update(range(l,h+1))
  elif part:out.add(int(part))
 return out
allowed=expand((root/'cpuset.cpus.effective').read_text());cg=Path('/proc')/str(pid)/'cgroup';rel=cg.read_text().strip().split('::')[-1];effective=expand((Path('/sys/fs/cgroup')/rel.lstrip('/')/'cpuset.cpus.effective').read_text())
assert chosen<=allowed and chosen<=effective,(allowed,effective)
assert max(util.values())<10,util
old={};new={}
for task in (Path('/proc')/str(pid)/'task').iterdir():
 tid=int(task.name);old[tid]=sorted(os.sched_getaffinity(tid));os.sched_setaffinity(tid,chosen);new[tid]=sorted(os.sched_getaffinity(tid))
out=dict(pid=pid,time=time.time(),selected=sorted(chosen),pre_bind_util=util,old=old,new=new,scope='own recovery process only; no restart; do not call total recovery time unmodified baseline')
Path(__file__).with_name('storymem_cpu_binding.json').write_text(json.dumps(out,indent=2));print('BOUND',out,flush=True)
