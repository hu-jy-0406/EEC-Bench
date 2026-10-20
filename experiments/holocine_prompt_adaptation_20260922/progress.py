#!/usr/bin/env python3
import collections,json,time
from run import HERE,read,dump,io,usage
io.safe_compute()
m=read(HERE/'manifest.json');states=[];groups=collections.defaultdict(collections.Counter)
runtime=HERE/'runtime_parallel64.json'
handoff_active=runtime.exists() and read(runtime).get('status')!='complete'
for j in m['jobs']:
    p=HERE/'episodes'/j['episode_id']/'status.json'
    handoff=p.parent/'parallel_status.json'
    s=read(handoff) if handoff_active and handoff.exists() else read(p) if p.exists() else dict(status='pending')
    states.append(s);groups[j['shot_count']][s['status']]+=1
u=usage()
result=dict(checked=time.time(),states=dict(collections.Counter(s['status'] for s in states)),by_shot_count={str(k):dict(v) for k,v in groups.items()},calls=u['calls'],total_tokens=u['total_tokens'],known_standard_api_equivalent_usd=u['known_standard_api_equivalent_usd'],unknown_or_inflight_costs=u['unknown_or_inflight'],failures=[s for s in states if s['status']=='failed'][:5])
dump(HERE/'progress.json',result);print(json.dumps(result),flush=True)
