import os,socket,signal,json,time
from pathlib import Path
from campaign import ROOT,read,write
node=socket.gethostname();rows=[]
for f in (ROOT/'workers').glob('*.json'):
 w=read(f)
 if w['node']!=node or w['mode']!='mapped' or node.endswith('-306'):continue
 pid=w['pid'];p=Path('/proc')/str(pid);d={'worker':w['worker'],'pid':pid}
 try:
  d['status_before']=(p/'status').read_text();args=(p/'cmdline').read_bytes().split(b'\0')
  d['smaps_rollup']=(p/'smaps_rollup').read_text()
  if str(ROOT/'campaign.py').encode() in args and w['worker'].encode() in args and p.stat().st_uid==os.getuid():os.kill(pid,signal.SIGTERM);d['terminated']=True
 except (FileNotFoundError,ProcessLookupError):d['already_exited']=True
 rows.append(d)
write(ROOT/'memory_incident'/f'{node}.json',dict(node=node,time=time.time(),workers=rows));print(node,'stopped',len(rows))
