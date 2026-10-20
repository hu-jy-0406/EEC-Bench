"""Apply final deterministic gates to saved model responses, without new calls."""
import sys,json,shutil,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_gs_temporal_stage import Stage,read,save
from gs_temporal_review import validate_checks
from gs_temporal_core import aggregate
from run_isolated_shot_static_3d import owned_compute_job
owned_compute_job();case=R/'replay';stage=Stage(case,'safe_spatial_medium');changes=[]
state=read(R/'replay_status.json');assert state['status']=='success'
for sid in ('shot1','shot3',None):
 boundary=sid is None;dest=case/'boundary' if boundary else case/'within'/sid
 proposals=read(dest/'proposals.json');previous=read(dest/'results.json')
 images=sum([stage.source_images(s)[1] for s in ('shot1','shot3')],[]) if boundary else stage.source_images(sid)[1]
 story=stage.story if boundary else stage.own_story(sid)
 prefix='boundary_review_' if boundary else 'within_'+sid+'_'
 checks=[]
 for p in sorted((case/'calls').glob(prefix+'*/response.json')):checks.extend(read(p)['checks'])
 support=read(dest/'local_support.json') if boundary else None
 decisions=validate_checks(dict(checks=checks,limitations='saved canonical judgments'),proposals,images,story,boundary,support)
 result=dict(previous,presence=aggregate(proposals['presence_units'],decisions),spatial=aggregate(proposals['spatial_units'],decisions,True),events=list(decisions.values()))
 old={e['event_id']:e['status'] for e in previous['events']}
 changed=[dict(event_id=k,before=old[k],after=e['status'],reason=e['gate_reason']) for k,e in decisions.items() if old[k]!=e['status']]
 if not (dest/'results_before_final_gate_audit.json').exists():shutil.copyfile(dest/'results.json',dest/'results_before_final_gate_audit.json')
 save(dest/'results.json',result);changes.append(dict(scope=sid or 'boundary',changed_decisions=changed))
save(R/'final_gate_audit.json',dict(success=True,new_model_calls=0,changes=changes,reason='revalidate saved canonical judgments against final expected-motion and boundary witness/joint-presence contracts'))
print(json.dumps(changes))
