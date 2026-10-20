import collections,json,time
from pathlib import Path
import run
run.io.safe_compute()
while True:
 now=time.time();paths=list((run.HERE/'episodes').glob('*/final.json'));counts=collections.Counter();fail=[];notes=0
 for p in (run.HERE/'episodes').glob('*/calls/*/status.json'):
  s=run.read(p);counts[s['status']]+=1
  if s['status']=='running':counts['active_'+s['stage']]+=1
 for p in (run.HERE/'episodes').glob('*/status.json'):
  s=run.read(p)
  if s['status']=='failed':fail.append(dict(episode_id=s['episode_id'],error=s['error'][:220]))
 result=dict(time=now,completed=len(paths),remaining=400-len(paths),drafted=sum(1 for p in (run.HERE/'episodes').glob('*/draft.json')),last5min=sum(p.stat().st_mtime>=now-300 for p in paths),calls=dict(counts),failed_episodes=fail,capacity64_released=(run.HERE/'scaling_released.json').exists())
 run.dump(run.HERE/'progress.json',result);print(json.dumps(result,ensure_ascii=False),flush=True)
 if len(paths)==400 and counts['running']==0:break
 time.sleep(45)
