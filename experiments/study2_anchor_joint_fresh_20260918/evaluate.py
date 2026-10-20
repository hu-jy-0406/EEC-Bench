"""Separate experimental branch; the original full-matching/dual-presence evaluator is untouched."""
import copy,json,sys,os,re,hashlib
from pathlib import Path
import numpy as np
import spatial_core as base
from anchor_joint_contract import ANCHORS,JOINT,validate_anchors,validate_joint,refit_requirement
from review_aligned_entity_identities import convert,projected
H=Path(__file__).resolve().parent;B=H.parents[1]
base.H=H;base.transport.PROMPTS=H/'prompts'
read=base.read;save=base.save

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
class Eval(base.Eval):
 def anchors(self):
  shots=[]
  for g,src in zip(self.full,self.sources):
   obs={src['shot_id']+'/'+e['entity_id']:e['observations'] for e in src['entities']}
   shots.append(dict(shot_id=g['shot_id'],coordinate_system=g['coordinate_system'],entities=[dict(entity_id=e['entity_id'],name=e['name'],motion_status='static',own_scene_geometry=e['geometry'],observations=obs[e['entity_id']]) for e in g['entities'] if e['motion_status']=='static']))
  payload=dict(stage='structural_anchors_only_v1',shots=shots,images=self.ix)
  result=self.call('anchors_only','anchors_only.txt',payload,self.allimages,ANCHORS);validate_anchors(result,payload)
  save(self.out/'anchors.json',result);save(self.out/'anchors_initial.json',result)
  self.write_anchor_matching(result)
  print('ANCHORS ONLY',[(a['anchor_id'],a['a_id'],a['b_id']) for a in result['anchors']],flush=True)
 def write_anchor_matching(self,result):
  save(self.out/'anchor_matching.json',dict(groups=[dict(group_id=a['anchor_id'],a_ids=[a['a_id']],b_ids=[a['b_id']],identity='matched',anchor_eligible=True,identity_evidence=a['reason'],anchor_reason='registration-only structural anchor') for a in result['anchors']],structural_anchor_group_ids=[a['anchor_id'] for a in result['anchors']],local_origin_group_id=result['local_origin_anchor_id'],local_reference_group_id=result['local_reference_anchor_id']))
 def joint(self):
  regp=self.out/'registration/roma_geometry/registration.json';fit=read(regp)['fits']['all_structures'];assert fit['status']=='numeric_candidate'
  anchor=read(self.out/'anchors.json');shots=[];aux=[]
  for side,(g,src) in enumerate(zip(self.full,self.sources)):
   obs={src['shot_id']+'/'+e['entity_id']:e['observations'] for e in src['entities']};entities=[]
   for e in g['entities']:
    if e['motion_status']!='static':continue
    box=convert(e['geometry'],fit,side)
    entities.append(dict(entity_id=e['entity_id'],name=e['name'],motion_status='static',own_scene_geometry=e['geometry'],aligned_geometry=box,observations=obs[e['entity_id']],aggregation=e['aggregation'],projected_center_in_other_shot=projected(box['center_world'],fit,1-side,self.full[1-side]['cameras'])))
   shots.append(dict(shot_id=g['shot_id'],coordinate_system=g['coordinate_system'],own_scene_cameras=g['cameras'],entities=entities))
   aux.append(dict(shot_id=g['shot_id'],entities=[dict(entity_id=e['entity_id'],name=e['name'],motion_status=e['motion_status'],observations=obs[e['entity_id']]) for e in g['entities']]))
  payload=dict(stage='aligned_joint_identity_presence_v1',registration_anchors=anchor,shots=shots,auxiliary_full_motion_inventories=aux,aligned_frame='fixed Shot1 scene, Z-up; uncertain model units',frozen_transform={k:fit[k] for k in ['scale','rotation','translation','yaw_deg']},registration_quality={k:fit[k] for k in ['train','spatial_holdout']},normal_story_prompt=self.story,images=self.ix)
  # A neutral plot shows EVERY static entity; only structural hypotheses get links.
  import matplotlib
  matplotlib.use('Agg')
  import matplotlib.pyplot as plt
  from matplotlib.lines import Line2D
  fig,ax=plt.subplots(figsize=(11,8));colors=['#1769ba','#df6b17'];lookup={e['entity_id']:e for s in shots for e in s['entities']}
  edges=[(i,j) for i in range(8) for j in range(i+1,8) if bin(i^j).count('1')==1]
  for side,s in enumerate(shots):
   for e in s['entities']:
    b=e['aligned_geometry'];c=np.array(b['corners_world']);v=np.array(b['center_world']);ax.scatter(*v[:2],s=14,c=colors[side]);ax.annotate(e['entity_id'],v[:2],xytext=(3,4 if side==0 else -10),textcoords='offset points',fontsize=6,color=colors[side])
    for i,j in edges:ax.plot(*c[[i,j],:2].T,color=colors[side],lw=.5,alpha=.3)
  for a in anchor['anchors']:
   xy=np.array([lookup[a[k]]['aligned_geometry']['center_world'][:2] for k in ['a_id','b_id']]);ax.plot(*xy.T,':',c='gray',lw=.7)
  ax.set_aspect('equal');ax.grid(alpha=.15);ax.set_xlabel('X: fixed Shot1 scene');ax.set_ylabel('Y: fixed Shot1 scene');ax.set_title('All static entities / proposed scene alignment\nDotted links: registration anchors only; all other identities unassigned');ax.legend(handles=[Line2D([0],[0],color=c,label=s) for c,s in zip(colors,['Shot1','Shot3'])]);fig.tight_layout()
  round_id=int(os.environ.get('JOINT_ROUND','1'));plot=self.out/f'joint_alignment_round{round_id}.png';fig.savefig(plot,dpi=130);plt.close(fig)
  images=self.allimages+[dict(path=str(plot.resolve()),sha256=sha(plot),shot_id='aligned_diagnostic',frame_id=-1)];payload['diagnostic_attachment']=dict(attachment_index=len(images),description='All static boxes in XY, no non-anchor cross-shot matching implied')
  sources=[regp,self.out/'anchors.json',*[self.out/'inputs'/f'{s}.json' for s in ['shot1','shot3']],*[self.out/'selected'/f'{s}_scene.json' for s in ['shot1','shot3']]];hashes={str(p):sha(p) for p in sources}
  stage='joint_identity_presence' if round_id==1 else f'joint_identity_presence_round{round_id}'
  result=self.call(stage,'joint_identity_presence.txt',payload,images,JOINT);rows=validate_joint(result,payload)
  for p,h in hashes.items():assert sha(p)==h,'Frozen source changed during joint judgment'
  req=refit_requirement(anchor['anchors'],result['anchor_audits'],read(self.out/'registration/roma_geometry/schema.json')['groups'])
  save(self.out/f'joint_round{round_id}.json',dict(result=result,refit=req,sources=hashes))
  if req['refit_required']:
   remaining=[a for a in anchor['anchors'] if a['anchor_id'] not in req['rejected_or_uncertain']]
   save(self.out/'refit_request.json',dict(round=round_id,**req,remaining_anchors=remaining))
   print('REFIT REQUIRED',req,flush=True);return
  save(self.out/'joint_identity_presence.json',result);save(self.out/'matching.json',result['matching']);save(self.out/'joint_sources.json',hashes)
  save(self.out/'presence.json',dict(aggregation_version='joint_single_presence_witness_v1',summary=base.score(rows),groups=rows,rule='one joint identity/presence judgment; original per-row image and Prompt gates retained; no duplicate consensus stage'))
  save(self.out/'joint_audit.json',dict(passed=True,inventory_conserved=True,registration_frozen=True,refit_requirement=req,round=round_id,model_calls_this_round=1))
  (self.out/'refit_request.json').unlink(missing_ok=True)
  print('JOINT COMPLETE',len(result['matching']['groups']),base.score(rows),flush=True)
if __name__=='__main__':
 base.owned_compute_job();assert sys.argv[2] in ['anchors','joint','spatial'];getattr(Eval(sys.argv[1]),sys.argv[2])()
