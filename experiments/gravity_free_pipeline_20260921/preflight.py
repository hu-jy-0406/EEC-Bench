import os,json,time
from pathlib import Path
print('allowed_cpus',sorted(os.sched_getaffinity(0)),flush=True)
print(Path('/proc/self/cgroup').read_text(),flush=True)
def sample():
 return {a[0]:list(map(int,a[1:])) for line in Path('/proc/stat').read_text().splitlines() if (a:=line.split()) and a[0].startswith('cpu')}
a=sample();time.sleep(1);b=sample()
print('cpu_8_15', {i:round(100*(1-(b['cpu'+str(i)][3]-a['cpu'+str(i)][3])/max(1,sum(b['cpu'+str(i)])-sum(a['cpu'+str(i)]))),2) for i in range(8,16)},flush=True)
for line in Path('/proc/self/cgroup').read_text().splitlines():
 _,ctrl,rel=line.split(':',2)
 if 'memory' in ctrl:
  d=Path('/sys/fs/cgroup/memory')/rel.lstrip('/')
  for folder in (d,d.parent,d.parent.parent):
   for n in ('memory.limit_in_bytes','memory.usage_in_bytes','memory.stat'):
    p=folder/n
    if p.exists():print(str(p),p.read_text()[:1800],flush=True)
