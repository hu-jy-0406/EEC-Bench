import collections,json,time
from pathlib import Path
import run
counts=collections.Counter();active=[];failed=[]
for p in (run.HERE/'episodes').glob('*/calls/*/status.json'):
 s=run.read(p);counts[s['status']]+=1
 if s['status']=='running':active.append([p.parent.parent.parent.name,p.parent.name,round(time.time()-s['started'])])
 if (p.parent/'validation.json').exists():
  v=run.read(p.parent/'validation.json')
  if v['status']=='failed':failed.append([p.parent.parent.parent.name,p.parent.name,v['error'][:450]])
print(json.dumps(dict(finals=sum(1 for p in (run.HERE/'episodes').glob('*/final.json')),drafts=sum(1 for p in (run.HERE/'episodes').glob('*/draft.json')),calls=dict(counts),active=active,validation_failures=failed[-10:]),ensure_ascii=False))
