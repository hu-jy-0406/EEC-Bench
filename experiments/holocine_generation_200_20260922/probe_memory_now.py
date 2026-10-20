import os,json,socket,time
from pathlib import Path
from campaign import ROOT,read,write
cg=Path('/sys/fs/cgroup')/Path('/proc/self/cgroup').read_text().strip().split(':')[-1].lstrip('/');job=next(p for p in [cg,*cg.parents] if p.name.startswith('job_'));node=socket.gethostname();rows=[]
for f in (ROOT/'workers').glob('*.json'):
 w=read(f)
 if w['node']!=node:continue
 p=Path('/proc')/str(w['pid'])
 if not p.exists():continue
 try:status=(p/'status').read_text();sm=(p/'smaps_rollup').read_text()
 except FileNotFoundError:continue
 vals={}
 for line in sm.splitlines():
  z=line.split()
  if z and z[0] in ['Anonymous:','Rss:','Pss_File:','Private_Dirty:']:vals[z[0][:-1]]=int(z[1])*1024
 rows.append(dict(worker=w['worker'],pid=w['pid'],state=w['state'],step=w.get('step'),memory=vals,transport=w.get('transport')))
d=dict(node=node,time=time.time(),workers=rows,memory={k:(job/k).read_text() for k in ['memory.stat','memory.current','memory.max','memory.events']});write(ROOT/'memory_probes'/f'{node}_{int(time.time())}.json',d);print(json.dumps(d))
