#!/usr/bin/env python3
"""Compact read-only progress and known-cost snapshot."""
import collections,json,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_text())
batch_states=collections.Counter();complete=0;active=[];usage=collections.Counter();calls=0;failed=[]
for p in (HERE/'batches').glob('*/status.json'):
    s=read(p);batch_states[s['status']]+=1
    if s['status']=='success':complete+=s['episodes']
    elif s['status']=='failed':failed.append(s)
for p in (HERE/'batches').glob('*/calls/*/status.json'):
    s=read(p)
    if s['status']=='running':active.append({'call':str(p.parent.relative_to(HERE)), 'seconds':round(time.time()-s['started'],1)});continue
    calls+=1
    for u in s.get('usage',s.get('known_usage',[])):
        if u:usage.update({k:v for k,v in u.items() if type(v) in (int,float)})
prices=read(HERE/'pricing.json')
cost=((usage['input_tokens']-usage['cached_input_tokens'])*prices['input_usd_per_million']+
      usage['cached_input_tokens']*prices['cached_input_usd_per_million']+usage['output_tokens']*prices['output_usd_per_million'])/1e6
print(json.dumps({'completed_episodes':complete,'batch_states':dict(batch_states),'active':active,
    'finished_calls':calls,'known_tokens':usage['input_tokens']+usage['output_tokens'],
    'known_standard_api_equivalent_usd_not_bill':cost,'inflight_excluded':True,'failed':failed},ensure_ascii=False,indent=2))
