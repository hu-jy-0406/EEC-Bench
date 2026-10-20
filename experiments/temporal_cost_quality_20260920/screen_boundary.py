import json,sys,time,shutil,hashlib,os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_gs_temporal_stage import Stage,read,save
from gs_flow1_compact_payload import pack,unpack,equivalent,dump
from run_isolated_shot_static_3d import owned_compute_job
BASE=B/'experiments/temporal_v2_study234_revised_20260920'
def one(name):
 src=BASE/name/'pairs/pair_000';dst=R/'boundary_compact_medium'/name;dst.mkdir(parents=True,exist_ok=False)
 provenance={}
 for pattern in ['narrative.json','matching.json','inputs/*.json','selected/*.json','registration/roma_geometry/registration.json']:
  for f in src.glob(pattern):
   target=dst/f.relative_to(src);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,target);provenance[str(f)]=hashlib.sha256(f.read_bytes()).hexdigest()
 save(dst/'frozen_upstream.json',provenance)
 start=time.time();state=dict(status='running',started=start);save(dst/'screen.json',state)
 try:
  Stage(dst,'temporal_compact_medium').boundary();a=read(src/'boundary/results.json');b=read(dst/'boundary/results.json')
  old={e['event_id']:e for e in a['events']};new={e['event_id']:e for e in b['events']};assert old.keys()==new.keys()
  diffs=[dict(event_id=k,old={f:old[k].get(f) for f in ['status','gate_reason']},new={f:new[k].get(f) for f in ['status','gate_reason']}) for k in old if old[k]['status']!=new[k]['status']]
  state.update(status='success',status_differences=diffs,exact_event_status_match=not diffs,scores={k:b[k]['summary'] for k in ['presence','spatial']})
 except BaseException as e:state.update(status='failed',error=repr(e))
 finally:
  state.update(seconds=time.time()-start);save(dst/'screen.json',state);print(name,json.dumps(state),flush=True)
 return state
if __name__=='__main__':
 owned_compute_job();start=time.time()
 # Read-only codec audit over every actual temporal input, without model calls.
 audit=[]
 for n in ['study2','study3','study4']:
  for root in [BASE/n/'calls',BASE/n/'pairs/pair_000/calls']:
   for p in root.glob('*/input.json'):
    if p.parent.name in ['matching','identity_review']:continue
    value=read(p);wire=pack(value);equivalent(value,unpack(wire));audit.append(dict(study=n,call=p.parent.name,canonical_chars=len(json.dumps(value,ensure_ascii=False)),wire_chars=len(dump(wire)),derived_boxes=wire.get('derived_geometry')))
 save(R/'transport_audit.json',audit)
 with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(one,['study2','study3','study4']))
 save(R/'boundary_screen_summary.json',dict(seconds=time.time()-start,results=results))
