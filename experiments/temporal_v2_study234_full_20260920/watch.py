import json,time
from pathlib import Path
r=Path(__file__).resolve().parent
for n in ['study2','study3','study4']:
 p=r/n/'pipeline_runtime.json'
 if not p.exists():continue
 d=json.loads(p.read_text());print(n,d['status'],round(time.time()-d['started']),[(s['stage'],s['status'],round(s.get('seconds',time.time()-s['started']),1)) for s in d['stages'][-4:]])
 for s in d['stages']:
  if s['status']=='failed':print((r/n/(s['stage']+'.log')).read_text()[-4000:])
