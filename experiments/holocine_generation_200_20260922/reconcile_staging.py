import os,socket,time
from pathlib import Path
from campaign import ROOT,read,write,locked
node=socket.gethostname();names=[]
for f in (ROOT/'workers').glob('*.json'):
 w=read(f)
 if w['node']!=node or w['mode']!='mapped':continue
 proc=Path('/proc')/str(w['pid'])
 assert not proc.exists() or not (proc/'cmdline').read_bytes(),(w['worker'],'still alive')
 names.append(w['worker']);w.update(state='stopped_staged_copy_migration',process_exit_verified=True,stopped_at=time.time());write(f,w)
with locked():
 q=read(ROOT/'queue.json')
 for t in q['tasks']:
  if t.get('worker') in names and t['status']!='done':
   t.setdefault('interruptions',[]).append(dict(at=time.time(),reason='mapped_host_page_registration_stall_use_bounded_staging',attempts=t['attempts'],previous_status=t['status']))
   t['status']='pending';t['max_attempts']=t['attempts']+2
 write(ROOT/'queue.json',q)
print(node,'reconciled',len(names))
