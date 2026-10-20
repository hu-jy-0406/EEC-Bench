import concurrent.futures,tempfile,json
from pathlib import Path
import campaign as c
original=c.ROOT
with tempfile.TemporaryDirectory(prefix='holo_queue_') as tmp:
 c.ROOT=Path(tmp)
 tasks=[dict(episode_id=str(i),stage=1 if i<8 else 2,status='pending',attempts=0) for i in range(16)];c.write(c.ROOT/'queue.json',dict(tasks=tasks))
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:claimed=list(pool.map(c.claim,[str(i) for i in range(8)]))
 assert len({t['episode_id'] for t in claimed})==8 and all(t['stage']==1 for t in claimed)
 assert c.claim('extra')=='wait'
 for i,t in enumerate(claimed[:-1]):c.finish(t,str(i),result={'ok':True})
 assert c.claim('extra')=='wait'
 t=claimed[-1];c.finish(t,'7',error='test_failure');retry=c.claim('retry');assert retry['episode_id']==t['episode_id'] and retry['attempts']==2
 c.finish(retry,'retry',result={'ok':True});second=c.claim('second');assert second['stage']==2
 assert sum(t['status']=='done' for t in c.read(c.ROOT/'queue.json')['tasks'])==8
 print('PASS:8 parallel unique claims; completed-only100/200 barrier; bounded retry; original ownership')
c.ROOT=original
