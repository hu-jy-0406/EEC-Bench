"""Post-registration original-frame identity audit; frozen registration, isolated Codex."""
import copy,json,hashlib,itertools,sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from gs_consistency_contract import obj,arr,enum,S,N,B,WITNESS,GROUP
import run_partial_scene_comparison as transport
import run_wedetect_shot_entities as io
from gs_identity_population import validate_anchors
MATCH=obj(groups=arr(GROUP),scene_correspondence=S,limitations=S,structural_anchor_group_ids=arr(S),local_origin_group_id=S,local_reference_group_id=S,reference_selection_reason=S)
DECISION=obj(initial_group_id=S,action=enum('keep','split','reassign','uncertain'),result_group_ids=arr(S),geometry_interpretation=S,visual_identity_evidence=S,same_instance_motion_alternative=S,witnesses=arr(WITNESS))
SINGLE=obj(group_id=S,cause=enum('viewpoint','motion','inconsistency','none'),evidence_status=enum('supported','unknown'),counterpart_visibility=enum('outside_view','occluded','observable','uncertain'),reason=S,prompt_fact_references=arr(S),witnesses=arr(WITNESS))
SCHEMA=obj(matching=MATCH,initial_group_reviews=arr(DECISION),noncommon_checks=arr(SINGLE),registration_caveats=S,limitations=S)
FOCUSED_PROTOCOL='identity_scoring_v1'
FOCUSED_DECISION=obj(initial_group_id=S,action=enum('keep','split','reassign','uncertain'),result_group_ids=arr(S),visual_identity_evidence=S,witnesses=arr(WITNESS))
FOCUSED_SCHEMA=obj(matching=MATCH,initial_group_reviews=arr(FOCUSED_DECISION),registration_caveats=S,limitations=S)
def read(p):return json.loads(Path(p).read_text())
def save(p,x):p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def registration_quality(reg):
 fit=reg['fits']['all_structures']
 if reg.get('method')=='codex_direct':
  return dict(method='codex_direct',geometric_diagnostics=fit['geometric_diagnostics'],model_confidence=fit['confidence'],model_limitations=fit['limitations'])
 return {k:fit[k] for k in ['train','spatial_holdout']}
def convert(g,fit,side):
 if g is None:return None
 b=copy.deepcopy(g)
 if side==1:
  s=fit['scale'];R=np.array(fit['rotation']);t=np.array(fit['translation']);b['center_world']=(s*R@np.array(g['center_world'])+t).tolist();b['size_xyz']=(s*np.array(g['size_xyz'])).tolist();b['R_world_from_object']=(R@np.array(g['R_world_from_object'])).tolist()
  if 'corners_world' in g:b['corners_world']=(s*np.array(g['corners_world'])@R.T+t).tolist()
 return b
def projected(center,fit,side,cams):
 c=np.array(center)
 if side==1:c=(c-np.array(fit['translation']))@np.array(fit['rotation'])/fit['scale']
 out=[]
 for cam in cams:
  x=(c-np.array(cam['position_world']))@np.array(cam['R_world_from_camera']);front=x[2]>1e-6;uv=np.array(cam['K'])@x;uv=uv[:2]/x[2] if front else None;W,H=cam['image_size'];inside=bool(front and 0<=uv[0]<W and 0<=uv[1]<H)
  out.append(dict(frame_id=cam['frame_id'],in_front=bool(front),center_pixel=None if uv is None else uv.tolist(),center_inside_image=inside))
 return out
def prepare(case):
 case=Path(case);initp=case/'matching_initial.json'
 if not initp.exists():save(initp,read(case/'matching.json'))
 initial=read(initp);regp=case/'registration/roma_geometry/registration.json';reg=read(regp);fit=reg['fits']['all_structures'];assert fit['status']=='numeric_candidate'
 graphs=[read(case/'selected'/f'{s}_scene.json') for s in ['shot1','shot3']];inputs=[read(case/'inputs'/f'{s}.json') for s in ['shot1','shot3']];shots=[];images=[];ix=[]
 for side,(g,inp) in enumerate(zip(graphs,inputs)):
  es=[]
  for e in g['entities']:
   b=convert(e['geometry'],fit,side);own=next(x for x in inp['entities'] if x['entity_id']==e['entity_id'].split('/')[-1]);es.append(dict(entity_id=e['entity_id'],name=e['name'],motion_status=e['motion_status'],aligned_geometry=b,own_scene_geometry=e['geometry'],observations=own['observations'],aggregation=e['aggregation'],frame_evidence=[dict(f,aligned_geometry=convert(f.get('geometry'),fit,side)) for f in e['frame_evidence']],projected_center_in_other_shot=projected(b['center_world'],fit,1-side,graphs[1-side]['cameras']) if b and e['motion_status']=='static' else []))
  for original,record in zip(g['entities'],es):
   record.update({k:copy.deepcopy(original[k]) for k in ['observed_motion_status','expected_motion_status','expected_motion_intervals','anchor_observed_static','motion_classification_protocol','motion_status_role','motion_evidence'] if k in original})
  shots.append(dict(shot_id=g['shot_id'],coordinate_system=g['coordinate_system'],own_scene_cameras=g['cameras'],entities=es))
  for f in inp['frames']:
   assert sha(f['path'])==f['sha256'];images.append(dict(f,shot_id=g['shot_id']));ix.append(dict(attachment_index=len(images),shot_id=g['shot_id'],frame_id=f['frame_id'],image_size=next(c['image_size'] for c in g['cameras'] if c['frame_id']==f['frame_id'])))
 lookup={e['entity_id']:e for g in shots for e in g['entities']};diagnostics=[]
 for g in initial['groups']:
  if len(g['a_ids'])==len(g['b_ids'])==1:
   a,b=[lookup[e]['aligned_geometry'] for e in g['a_ids']+g['b_ids']]
   if a is None or b is None:continue
   v=np.array(b['center_world'])-a['center_world'];L=float(np.mean([np.linalg.norm(a['size_xyz']),np.linalg.norm(b['size_xyz'])]));diagnostics.append(dict(group_id=g['group_id'],identity_hypothesis=g['identity'],aligned_center_difference=v.tolist(),center_distance=float(np.linalg.norm(v)),distance_over_mean_box_diagonal=float(np.linalg.norm(v)/max(L,1e-9)),mean_box_diagonal=L))
 story=read(case/'narrative.json');payload=dict(stage='post_alignment_identity_review_v1',initial_matching=initial,aligned_frame='fixed Shot1 scene, arbitrary axes with NO physical-up estimate; model units, not calibrated meters' if reg.get('rotation_model')=='so3' else 'fixed Shot1 scene, Z-up; model units, not calibrated meters',shots=shots,all_initial_paired_group_diagnostics=diagnostics,frozen_transform={k:fit[k] for k in ['scale','rotation','translation','yaw_deg']},registration_quality=registration_quality(reg),normal_story_prompt=story,images=ix,diagnostic_rules='Coordinates are uncertain hypotheses. No conflict/cosine labels are supplied. Large separation alone cannot decide identity.')
 payload['registration_objective']={k:reg[k] for k in ['objective','fit_population','sampling','independent_holdout','reprojection_metrics_role'] if k in reg}
 # Generic aligned display; every paired group equally labeled, no target hints.
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 from matplotlib.lines import Line2D
 fig,ax=plt.subplots(figsize=(11,8));cols=['#1769ba','#df6b17'];ids={eid:g['group_id'] for g in initial['groups'] for eid in g['a_ids']+g['b_ids']};edges=[(i,j) for i in range(8) for j in range(i+1,8) if bin(i^j).count('1')==1]
 for side,g in enumerate(shots):
  for e in g['entities']:
   b=e['aligned_geometry']
   if b is None:continue
   c=np.array(b['corners_world']);p=np.array(b['center_world']);ax.scatter(*p[:2],s=16,c=cols[side]);ax.annotate(ids[e['entity_id']]+' / '+e['entity_id'],p[:2],xytext=(3,4 if side==0 else -10),textcoords='offset points',fontsize=6,color=cols[side])
   for i,j in edges:ax.plot(*c[[i,j],:2].T,color=cols[side],lw=.55,alpha=.3)
 for g in initial['groups']:
  if len(g['a_ids'])==len(g['b_ids'])==1:
   if any(lookup[e]['aligned_geometry'] is None for e in g['a_ids']+g['b_ids']):continue
   p=np.array([lookup[e]['aligned_geometry']['center_world'][:2] for e in g['a_ids']+g['b_ids']]);ax.plot(*p.T,color='gray',lw=.6,ls=':',alpha=.6)
 ax.set_aspect('equal');ax.grid(alpha=.15);ax.set_xlabel('X: fixed Shot1 scene');ax.set_ylabel('Y: fixed Shot1 scene');ax.set_title('Frozen estimated alignment / all entities with geometry\nDotted lines = prior identity hypotheses, not confirmed truth');ax.legend(handles=[Line2D([0],[0],color=c,lw=2,label=s) for c,s in zip(cols,['Shot1','Shot3'])]);fig.tight_layout();diagram=case/'identity_review_alignment.png';fig.savefig(diagram,dpi=130);plt.close(fig)
 images.append(dict(path=str(diagram.resolve()),sha256=sha(diagram),shot_id='aligned_diagnostic',frame_id=-1));payload['diagnostic_attachment']=dict(attachment_index=len(images),description='All entities with geometry in estimated Shot1 scene XY, prior identity links dotted; not an original frame')
 save(case/'identity_review_payload.json',payload);save(case/'identity_review_images.json',images);save(case/'identity_review_sources.json',{str(p.resolve()):sha(p) for p in [initp,regp,*[case/'selected'/f'{s}_scene.json' for s in ['shot1','shot3']],*[case/'inputs'/f'{s}.json' for s in ['shot1','shot3']]]})
 return payload,images
def validate(result,payload,protocol=None):
 import jsonschema
 if protocol not in (None,FOCUSED_PROTOCOL):raise ValueError('Unknown identity review protocol')
 jsonschema.validate(result,FOCUSED_SCHEMA if protocol==FOCUSED_PROTOCOL else SCHEMA);initial=payload['initial_matching'];m=result['matching'];groups=m['groups'];gm={g['group_id']:g for g in groups};assert len(gm)==len(groups),'duplicate group ids'
 for side,shot in zip(['a','b'],payload['shots']):
  ids=[eid for g in groups for eid in g[side+'_ids']];assert len(ids)==len(set(ids)) and set(ids)=={e['entity_id'] for e in shot['entities']},'inventory changed or duplicate'
 for g in groups:
  assert g['a_ids'] or g['b_ids']
  if g['identity']=='matched':assert len(g['a_ids'])==len(g['b_ids'])==1
  if g['identity']=='unmatched':assert len(g['a_ids'])+len(g['b_ids'])==1
 old={g['group_id']:g for g in initial['groups']};reviews=result['initial_group_reviews'];assert len(reviews)==len(old) and {r['initial_group_id'] for r in reviews}==set(old)
 idx={(f['shot_id'],f['frame_id']):f for f in payload['images']}
 def witnesses(ws):
  for w in ws:
   im=idx[(w['shot_id'],w['frame_id'])];W,H=im['image_size'];b=w['region_xyxy'];assert len(b)==4 and 0<=b[0]<b[2]<=W and 0<=b[1]<b[3]<=H
 for r in reviews:
  assert set(r['result_group_ids'])<=set(gm);before=old[r['initial_group_id']];members=set(before['a_ids']+before['b_ids']);after=set(e for gid in r['result_group_ids'] for e in gm[gid]['a_ids']+gm[gid]['b_ids']);assert members<=after
  if r['action']=='keep':assert r['result_group_ids']==[before['group_id']] and all(gm[before['group_id']][k]==before[k] for k in ['a_ids','b_ids','identity'])
  if r['action']=='split':
   assert len(before['a_ids'])==len(before['b_ids'])==1 and len(r['result_group_ids'])==2 and members==after
   assert all(gm[i]['identity']=='unmatched' for i in r['result_group_ids'])
   assert {w['shot_id'] for w in r['witnesses']}=={g['shot_id'] for g in payload['shots']},'split lacks original-frame evidence on both sides'
  witnesses(r['witnesses'])
 singles={g['group_id'] for g in groups if g['identity']=='unmatched'};checks=result.get('noncommon_checks',[])
 if protocol!=FOCUSED_PROTOCOL:assert len(checks)==len(singles) and {r['group_id'] for r in checks}==singles
 facts={f['fact_id'] for f in payload['normal_story_prompt']['facts']}
 for r in checks:
  assert set(r['prompt_fact_references'])<=facts;witnesses(r['witnesses'])
  if r['evidence_status']=='supported':assert r['cause']!='none' and r['witnesses']
 anchors=m['structural_anchor_group_ids'];assert set(anchors)<=set(initial['structural_anchor_group_ids']);assert all(gm[g]['identity']=='matched' and gm[g]['anchor_eligible'] for g in anchors)
 for k in ['local_origin_group_id','local_reference_group_id']:assert not m[k] or m[k] in anchors
 validate_anchors(m,[{e['entity_id']:dict(e,geometry=e.get('own_scene_geometry')) for e in shot['entities']} for shot in payload['shots']])
 return result
def run_case(case,args=None):
 case=Path(case).resolve()
 if args is None:args=SimpleNamespace(out=case/'calls',model='gpt-6-astra',reasoning='medium',codex_bin='/vast/users/guangyi.chen/.local/bin/codex',timeout=1800,disabled_skills=io.disabled_skills_config())
 from gs_runtime_profile import resolve_identity_review_input
 from gs_identity_review_minimal_input import build, PROFILE
 protocol=getattr(args,'identity_review_protocol',None)
 choice=resolve_identity_review_input(dict(identity_review_protocol=protocol),getattr(args,'identity_review_input',None))
 d=Path(args.out)/'identity_review'
 # Fail before prepare() writes anything: never mix results from different
 # evidence versions or silently reuse an older successful model call.
 if d.exists():raise FileExistsError('Existing identity_review call: preserve it and use a fresh case directory for a changed run.')
 payload,images=prepare(case)
 schema=FOCUSED_SCHEMA if protocol==FOCUSED_PROTOCOL else SCHEMA
 prompt='gs_aligned_identity_scoring_v1.txt' if protocol==FOCUSED_PROTOCOL else 'gs_aligned_identity_review_v1.txt'
 model_payload,model_images=payload,images
 if choice=='minimal':
  model_payload,model_images=build(payload,images)
  prompt='gs_aligned_identity_minimal_v1.txt'
 transport.PROMPTS=Path(__file__).resolve().parents[1]/'prompts'
 fingerprint=lambda value:hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest()
 request=dict(identity_review_input=choice,input_profile=PROFILE if choice=='minimal' else 'full_v1',
  matching_revision=protocol or 'all_entity_aligned_identity_review_v2',prompt=prompt,prompt_sha256=sha(transport.PROMPTS/prompt),
  model=args.model,reasoning=args.reasoning,canonical_payload_sha256=fingerprint(payload),
  model_payload_sha256=fingerprint(model_payload),output_schema_sha256=fingerprint(schema),
  images=[{k:r[k] for k in ('shot_id','frame_id','sha256')} for r in model_images],
  canonical_validation=True)
 save(case/'identity_review_request.json',request)
 result=transport.call('identity_review',prompt,model_payload,model_images,schema,args)
 try:
  validate(result,payload,protocol)
  for p,h in read(case/'identity_review_sources.json').items():assert sha(p)==h,'source changed'
 except BaseException as exc:
  status=d/'status.json'
  if status.exists():save(status,dict(read(status),status='failed',transport_status='success',validation_phase='identity_and_frozen_sources',error=repr(exc)))
  raise
 save(case/'identity_review.json',result);save(case/'matching.json',result['matching']);save(case/'identity_review_audit.json',dict(passed=True,inventory_conserved=True,source_registration_frozen=True,original_witnesses_valid=True,reviewed_initial_groups=len(result['initial_group_reviews']),final_groups=len(result['matching']['groups']),matching_revision=request['matching_revision'],identity_review_input=choice,input_profile=request['input_profile'],request_manifest='identity_review_request.json'))
 print('IDENTITY REVIEW COMPLETE',choice,[(r['initial_group_id'],r['action']) for r in result['initial_group_reviews'] if r['action']!='keep'],flush=True)
 return result
if __name__=='__main__':
 from run_isolated_shot_static_3d import owned_compute_job
 owned_compute_job();run_case(Path(sys.argv[1]))
