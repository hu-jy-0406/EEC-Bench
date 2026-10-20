from pathlib import Path
import socket,json
from campaign import ROOT,read,write
node=socket.gethostname();out=[]
for f in (ROOT/'workers').glob('*.json'):
 w=read(f)
 if w['node']!=node or w.get('transport')!='shared_mmap_v2':continue
 try:s=(Path('/proc')/str(w['pid'])/'smaps').read_text()
 except FileNotFoundError:continue
 sections=[];cur=None
 for line in s.splitlines():
  if '-' in line.split()[0] and len(line.split())>=5:
   cur={'mapping':line};sections.append(cur)
  elif cur is not None:
   a=line.split()
   if a[0] in ['Size:','Rss:','Anonymous:','Private_Dirty:','Shared_Dirty:']:cur[a[0][:-1]]=int(a[1])
 big=sorted(sections,key=lambda x:x.get('Anonymous',0),reverse=True)[:8];mapped=[x for x in sections if 'mapped_weights' in x['mapping']]
 out.append(dict(worker=w['worker'],pid=w['pid'],big_anon=big,mapped_weights=mapped))
write(ROOT/'memory_probes'/f'maps_{node}.json',out);print(json.dumps(out))
