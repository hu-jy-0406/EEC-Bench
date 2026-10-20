#!/usr/bin/env python3
"""Transfer unstarted episodes using exclusive call-directory reservations.

The original runner atomically creates calls/draft_1 before any API request.
A non-API reservation there makes its queued future return without sending.
Transferred work uses calls/parallel_* and a separate state ledger. No active
request is killed or duplicated; canonical status is reconciled after drain.
"""
import concurrent.futures,json,pathlib,socket,threading,time
import run
from run import HERE,read,dump,io,process,tokenizer,usage

io.safe_compute();assert read(HERE/'authorization.json')['authorized']
selected=[]
for j in read(HERE/'manifest.json')['jobs']:
    d=HERE/'episodes'/j['episode_id']
    if (d/'status.json').exists():continue
    folder=d/'calls'/'draft_1'
    try:folder.mkdir(parents=True,exist_ok=False)
    except FileExistsError:continue
    reservation=dict(status='scheduler_handoff_no_api_call',not_an_api_call=True,started=time.time(),seconds=0,reason='Unstarted episode transferred to parallel64 coordinator after explicit user request. Original queued task must not make an API call.',episode_id=j['episode_id'])
    dump(folder/'status.json',reservation)
    dump(d/'parallel_status.json',dict(status='pending',episode_id=j['episode_id']))
    selected.append(j)
dump(HERE/'parallel_takeover.json',dict(created=time.time(),host=socket.gethostname(),user_request='并行处理加快速度',workers_after_drain=64,workers_during_drain=32,episodes=[j['episode_id'] for j in selected],mechanism='exclusive non-API draft_1 reservations; transferred API attempts use parallel_* call folders',no_active_calls_cancelled=True))
print(json.dumps(dict(transferred=len(selected),initial_workers=32,target_workers=64)),flush=True)
original_call=run.call
def isolated_call(folder,p,kind):
    return original_call(folder.parent/('parallel_'+folder.name),p,kind)
run.call=isolated_call
tokenizer();run.DISABLED=io.disabled_skills_config();sem=threading.Semaphore(32)
done=threading.Event()
runtime=HERE/'runtime_parallel64.json';started=time.time()
dump(runtime,dict(status='running',started=started,episodes=len(selected),workers=32,planned_workers=64))
def grow():
    while not done.wait(5):
        p=HERE/'runtime_full396.json'
        if p.exists() and read(p).get('status')=='complete':
            for _ in range(32):sem.release()
            dump(runtime,dict(status='running',started=started,episodes=len(selected),workers=64,old_coordinator_drained=True))
            print(json.dumps(dict(expanded_to=64,old_coordinator_drained=True)),flush=True);return
threading.Thread(target=grow,daemon=True).start()
def work(j):
    d=HERE/'episodes'/j['episode_id']
    with sem:
        dump(d/'parallel_status.json',dict(status='running',episode_id=j['episode_id'],started=time.time()))
        state=process(j,3)
        dump(d/'parallel_status.json',state)
        return state
try:
    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as pool:states=list(pool.map(work,selected))
finally:done.set()
dump(runtime,dict(status='complete',started=started,finished=time.time(),episodes=len(selected),workers=64,active_task_processes=False))
dump(HERE/'parallel64_summary.json',dict(states=states,seconds=time.time()-started))
print(json.dumps(dict(complete=len(states))),flush=True)
