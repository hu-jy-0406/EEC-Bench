"""Discrete event scheduling estimate from frozen prior durations, not a fresh measurement."""
import heapq,json,sys
from pathlib import Path
R=Path(__file__).resolve().parent;sys.path.insert(0,str(R.parents[1]/'scripts'))
import run_gs_temporal as m
old=R.parent/'study3_appearance_full_20260921/run';s=m.read(old/'summary.json')
durations={x['stage']:x['seconds'] for x in s['stages']};shots=m.read(old/'raw_manifest.json')['shots']
def simulate(name):
 jobs=m.plan('/tmp/estimate',shots,6,'GPU-test',schedule_name=name);cfg=m.scheduling(name)
 ds=durations.copy()
 if name=='parallel_v1':
  cs={Path(c['call']).name:c['seconds'] for c in s['calls']}
  boundary_api=max(cs['boundary_local_shot1'],cs['boundary_local_shot3'])+cs['boundary_spatial_verify']
  overhead=ds['pair_000_boundary']-cs['boundary_review_000']-boundary_api
  ds['pair_000_boundary']=max(cs['boundary_review_000'],boundary_api)+overhead
  slots=[0.0]*cfg['appearance_workers'];heapq.heapify(slots)
  for c in s['calls']:
   if c['call'].startswith('appearance/'):
    heapq.heappush(slots,heapq.heappop(slots)+c['seconds'])
  ds['appearance_codex']=max(slots)+5 # fixed orchestration overhead assumption
 pending=jobs.copy();active=[];done=set();t=0;records=[]
 while pending or active:
  for j in pending.copy():
   if len(active)>=cfg['stage_workers']:break
   if not set(j['depends'])<=done:continue
   if j['gpu'] and any(x[1]['gpu'] for x in active):continue
   if j['api_slots']+sum(x[1]['api_slots'] for x in active)>cfg['api_slots']:continue
   records.append(dict(stage=j['stage'],start=t,end=t+ds[j['stage']]))
   active.append((t+ds[j['stage']],j));pending.remove(j)
  assert active
  t=min(e for e,j in active)
  for e,j in active.copy():
   if e<=t:active.remove((e,j));done.add(j['stage'])
 return dict(seconds=t,timeline=records)
a,b=simulate('legacy'),simulate('parallel_v1')
r=dict(estimate_only=True,source=str(old),legacy=a,parallel_v1=b,saving_percent=100*(1-b['seconds']/a['seconds']),new_model_calls=0,new_tokens=0,new_api_usd=0)
m.save(R/'schedule_estimate.json',r);print(json.dumps({k:v for k,v in r.items() if k not in ('legacy','parallel_v1')},indent=2));print(a['seconds'],b['seconds'])
