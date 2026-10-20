from collections import Counter
import json,time
from campaign import ROOT,read
q=read(ROOT/'queue.json');ws=[read(p) for p in (ROOT/'workers').glob('*.json')];ms=[read(p) for p in (ROOT/'managers').glob('*.json') if not p.name.endswith('_error.json')]
x=dict(utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),episodes=200,stages={str(s):dict(Counter(t['status'] for t in q['tasks'] if t['stage']==s)) for s in [1,2]},workers=dict(Counter(w['state'] for w in ws)),live_worker_heartbeats=sum(time.time()-w['heartbeat']<90 and w['state'] in ['loading','ready','generating','denoising','validating','waiting_for_phase_barrier'] for w in ws),sampling_steps_completed=sum(w.get('step',0)>0 and w['state']=='denoising' for w in ws),managers=len(ms),controller_age_seconds=time.time()-read(ROOT/'controller_status.json')['heartbeat'] if (ROOT/'controller_status.json').exists() else None,failures=[{'worker':w['worker'],'error':w.get('error','')[-1000:]} for w in ws if w['state']=='failed'],complete=(ROOT/'complete.json').exists())
print(json.dumps(x,indent=2))
