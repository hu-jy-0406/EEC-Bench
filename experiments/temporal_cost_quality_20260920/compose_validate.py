"""Compose unchanged canonical stages with validated spatial responses, no new API calls."""
import json,sys,shutil,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_gs_temporal_stage import Stage,read,save
from run_isolated_shot_static_3d import owned_compute_job
BASE=B/'experiments/temporal_v2_study234_revised_20260920'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def one(n):
 src=BASE/n/'pairs/pair_000';spatial=R/'spatial_efficient_low'/n;dst=R/'selected_replay'/n;dst.mkdir(parents=True,exist_ok=False)
 for pattern in ['narrative.json','matching.json','inputs/*.json','selected/*.json','registration/roma_geometry/registration.json']:
  for f in src.glob(pattern):
   p=dst/f.relative_to(src);p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,p)
 chosen=[];stage=Stage(dst,'temporal_cost_v1')
 def call(name,prompt,payload,images,schema):
  root=src if name.startswith('boundary_review_') else spatial
  c=root/'calls'/name;canonical=dict(payload,images=[dict(attachment_index=i+1,shot_id=f['shot_id'],frame_id=f['frame_id'],image_size=f['image_size']) for i,f in enumerate(images)])
  assert canonical==read(c/'input.json'),(n,name,'input mismatch')
  assert schema==read(c/'output.schema.json'),(n,name,'schema mismatch')
  current=Path(prompt) if Path(prompt).is_absolute() else B/'prompts/gs_flow1'/prompt
  assert (c/'prompt.txt').read_text().startswith(current.read_text()),(n,name,'decision prompt changed')
  req=read(c/'request.json');assert [(f['shot_id'],f['frame_id'],f['sha256']) for f in images]==[(f['shot_id'],f['frame_id'],f['sha256']) for f in req['images']]
  assert all(sha(f['path'])==f['sha256'] for f in images)
  chosen.append(dict(call=name,source=str(c),input_sha256=sha(c/'input.json'),response_sha256=sha(c/'response.json')))
  return read(c/'response.json')
 stage.call=call;stage.boundary();a=read(src/'boundary/results.json');b=read(dst/'boundary/results.json')
 assert a['target_frames']==b['target_frames']
 for k in ['presence','spatial']:
  assert a[k]['summary']==b[k]['summary'],(n,k,'score drift')
  assert a[k]['units']==b[k]['units'],(n,k,'unit drift')
 assert {e['event_id']:e['status'] for e in a['events']}=={e['event_id']:e['status'] for e in b['events']}
 save(dst/'composition_audit.json',dict(status='success',original_images=True,exact_canonical_inputs=True,decision_prompt_prefixes_unchanged=True,schemas_unchanged=True,full_event_status_match=True,complete_units_match=True,selected_calls=chosen,scope='frozen-upstream composition; spatial calls fresh in candidate screen, other stages retain immutable baseline results; not a new end-to-end run'))
 return dict(study=n,status='success',presence=b['presence']['summary'],spatial=b['spatial']['summary'])
if __name__=='__main__':
 owned_compute_job();save(R/'selected_validation.json',[one(n) for n in ['study2','study3','study4']]);print('All 3 compositions passed; no new API calls.')
