"""Small compute-node concurrency test for phase barriers and retry ownership."""
import concurrent.futures
import json
from pathlib import Path
import tempfile
import threading
import time
import campaign

with tempfile.TemporaryDirectory(prefix='queue_test_',dir=campaign.ROOT) as d:
    campaign.ROOT=Path(d)
    tasks=[dict(key=f'e{i}/Shot1',episode_id=f'e{i}',shot_id='Shot1',rank=i+1,
        stage=1+i//12,status='pending',attempts=0) for i in range(36)]
    campaign.write_json(campaign.ROOT/'queue.json',dict(stage=1,tasks=tasks))
    events=[];lock=threading.Lock()
    def run(w):
        while True:
            t=campaign.claim(str(w))
            if t is None:return
            if t=='wait':time.sleep(.01);continue
            with lock:events.append(('claim',t['key'],t['stage']))
            time.sleep(.005*(1+w%3))
            # One real retry exercises ownership and stage1 failure handling.
            if t['key']=='e0/Shot1' and t['attempts']==1:
                campaign.finish(t['key'],str(w),error='intentional test failure')
                continue
            campaign.finish(t['key'],str(w),result={'test':True})
            with lock:events.append(('done',t['key'],t['stage']))
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(run,range(8)))
    q=json.loads((campaign.ROOT/'queue.json').read_text())
    assert all(t['status']=='done' for t in q['tasks'])
    assert sum(t['attempts'] for t in q['tasks'])==37
    # State is authoritative: each new-stage claim requires every earlier task done.
    completed=set()
    for action,key,stage in events:
        if action=='done':completed.add(key)
        elif stage>1:
            assert all(t['key'] in completed for t in tasks if t['stage']<stage)
    print('PASS: 36 tasks, 8 concurrent workers, strict 3-stage barrier, exact ownership, one retry.')
