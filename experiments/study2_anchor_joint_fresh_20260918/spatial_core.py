import sys,os,json,time,copy,itertools,math
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import numpy as np
H=Path(__file__).resolve().parent;B=H.parents[1];sys.path.insert(0,str(B/'scripts'))
import run_partial_scene_comparison as transport
import run_wedetect_shot_entities as io
from run_isolated_shot_static_3d import owned_compute_job
from contracts import MATCH,PRESENCE,VERIFY,GATES
from gs_relation_contract import SHOT_SCHEMA
from run_gs_spatial_consistency import validate_single
from gs_spatial_relations import basis
from score_gs_spatial_consistency import VERIFY_GATES,validate_witnesses
transport.PROMPTS=H/'prompts'
def read(p):return json.loads(p.read_text())
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def score(rows, *, spatial=False):
 d={s:sum(r['status']==s for r in rows) for s in ['compatible','conflict','unknown','exempt']};c,k,u,e=[d[s] for s in d];n=c+k+u
 return dict(score=100.0 if spatial and k==0 else (100*(1-k/n) if n and c+k else None),coverage=(c+k)/n if n else None,N=n,C=c,K=k,U=u,E=e,identification_interval=[100*c/n,100*(c+u)/n] if n else None)
def clean(g):
 r={k:copy.deepcopy(g[k]) for k in ['shot_id','method','coordinate_system','cameras']};r['entities']=[]
 for e in g['entities']:
  if e['motion_status']!='static':continue
  n={k:copy.deepcopy(e[k]) for k in ['entity_id','name','geometry','motion_status']};n['center_mad_xyz']=e['aggregation'].get('center_mad_xyz');n['frame_evidence']=[{k:f[k] for k in ['frame_id','visible','box_xyxy','eligible','selected','geometry','projection_iou'] if k in f} for f in e['frame_evidence']];r['entities'].append(n)
 return r
class Eval:
 def __init__(self,case):
  self.out=H/case;self.sources=[read(self.out/'inputs'/f'{s}.json') for s in ['shot1','shot3']];self.full=[read(self.out/'selected'/f'{s}_scene.json') for s in ['shot1','shot3']];self.graphs=[clean(g) for g in self.full];self.nodes=[{e['entity_id']:e for e in g['entities']} for g in self.graphs]
  self.images=[[dict(f,shot_id=s['shot_id']) for f in s['frames']] for s in self.sources];self.allimages=sum(self.images,[]);self.ix=[dict(attachment_index=i+1,shot_id=f['shot_id'],frame_id=f['frame_id'],image_size=next(c['image_size'] for g in self.graphs if g['shot_id']==f['shot_id'] for c in g['cameras'] if c['frame_id']==f['frame_id'])) for i,f in enumerate(self.allimages)]
  self.args=SimpleNamespace(out=self.out/'calls',model='gpt-6-astra',reasoning='medium',codex_bin='/vast/users/guangyi.chen/.local/bin/codex',timeout=1800,disabled_skills=io.disabled_skills_config());self.story=read(self.out/'narrative.json');self.factids={f['fact_id'] for f in self.story['facts']}
 def call(self,stage,prompt,payload,images,schema):
  d=self.args.out/stage
  if d.exists():
   assert read(d/'input.json')==payload and read(d/'status.json')['status']=='success','Changed/failed request '+stage
   return read(d/'response.json')
  return transport.call(stage,prompt,payload,images,schema,self.args)
 def match(self):
  m=self.call('matching','match.txt',dict(graphs=self.graphs,images=self.ix),self.allimages,MATCH);gs=m['groups'];ids=[g['group_id'] for g in gs];assert len(ids)==len(set(ids))
  for side,nodes in zip(['a','b'],self.nodes):
   assigned=[eid for g in gs for eid in g[side+'_ids']];assert len(assigned)==len(set(assigned)) and set(assigned)==set(nodes)
  for g in gs:
   if g['identity']=='matched':assert len(g['a_ids'])==len(g['b_ids'])==1
  gm={g['group_id']:g for g in gs};assert set(m['structural_anchor_group_ids'])<=set(gm)
  assert all(gm[k]['identity']=='matched' and gm[k]['anchor_eligible'] for k in m['structural_anchor_group_ids'])
  for key in ['local_origin_group_id','local_reference_group_id']:assert not m[key] or m[key] in m['structural_anchor_group_ids']
  assert not m['local_origin_group_id'] or m['local_origin_group_id']!=m['local_reference_group_id']
  save(self.out/'matching.json',m);print('MATCH',len(gs),m['structural_anchor_group_ids'],flush=True)
 def review_identity(self):
  from review_aligned_entity_identities import run_case
  original_prompts=transport.PROMPTS
  try:return run_case(self.out,self.args)
  finally:transport.PROMPTS=original_prompts
 def presence(self):
  m=read(self.out/'matching.json');aux=[]
  for g,s in zip(self.full,self.sources):
   obs={s['shot_id']+'/'+e['entity_id']:e['observations'] for e in s['entities']}
   aux.append(dict(shot_id=g['shot_id'],entities=[dict(entity_id=e['entity_id'],name=e['name'],motion_status=e['motion_status'],observations=obs[e['entity_id']]) for e in g['entities']]))
  payload=dict(graphs=self.graphs,matching=m,auxiliary_full_motion_inventories=aux,normal_story_prompt=self.story,images=self.ix)
  if (self.out/'identity_review.json').exists():
   review=read(self.out/'identity_review.json');aligned=read(self.out/'identity_review_payload.json')
   assert review['matching']==m, 'Identity revision mismatch'
   payload['post_alignment_evidence']=dict(aligned_frame=aligned['aligned_frame'],frozen_transform=aligned['frozen_transform'],registration_quality=aligned['registration_quality'],shots=aligned['shots'],identity_review=review)
  with ThreadPoolExecutor(max_workers=2) as pool:reviews=list(pool.map(lambda i:self.call('presence_'+str(i),'presence.txt',payload,self.allimages,PRESENCE),[1,2]))
  gm={g['group_id']:g for g in m['groups']};rows=[];expected=list(gm)
  for review in reviews:assert [r['group_id'] for r in review['checks']]==expected
  for g,r1,r2 in zip(m['groups'],reviews[0]['checks'],reviews[1]['checks']):
   p='common_static' if g['identity']=='matched' else ('noncommon_static' if g['identity']=='unmatched' and len(g['a_ids'])+len(g['b_ids'])==1 else 'unresolved')
   valid=[]
   for r in [r1,r2]:
    assert r['partition']==p;assert set(r['prompt_fact_references'])<=self.factids
    fids={s:set() for s in ['shot1','shot3']}
    for w in r['witnesses']:
     f=next(f for f in self.ix if f['shot_id']==w['shot_id'] and f['frame_id']==w['frame_id']);W,Hh=f['image_size'];b=w['region_xyxy'];assert len(b)==4 and 0<=b[0]<b[2]<=W and 0<=b[1]<b[3]<=Hh;fids[w['shot_id']].add(w['frame_id'])
    witness=all(len(fs)>=2 for fs in fids.values());prompt=r['prompt_review_completed'] and bool(r['prompt_fact_references']) and bool(r['prompt_explanation'].strip())
    ok=True
    if r['status']=='conflict':ok=witness and prompt and all(r[k] for k in GATES) and r['cause']=='inconsistency' and r['conflict_kind'] in (['required_absent_but_present'] if p=='common_static' else ['unexplained_missing','unexplained_added'])
    elif r['status']=='compatible':ok=p=='common_static' and r['joint_presence_reasonable'] and r['identity_supported'] and all(len(fs)>=1 for fs in fids.values()) and prompt
    elif r['status']=='exempt':ok=p=='noncommon_static' and r['cause'] in ['viewpoint','motion'] and bool(r['witnesses']) and prompt
    valid.append(ok)
   same=r1['status']==r2['status'] and r1['cause']==r2['cause'] and r1['conflict_kind']==r2['conflict_kind'];status=r1['status'] if same and all(valid) and p!='unresolved' else 'unknown'
   rows.append(dict(group_id=g['group_id'],partition=p,status=status,cause=r1['cause'] if same else 'none',conflict_kind=r1['conflict_kind'] if status=='conflict' else 'none',joint_presence_reasonable=p=='common_static' and status=='compatible',independent_review_agreement=same,evidence_gates_pass=valid,reason=[r1['reason'],r2['reason']],reviews=[r1,r2]))
  result=dict(aggregation_version='positive_presence_witness_v1',summary=score(rows),groups=rows,rule='two independent judgments must agree; disagreements and failed witness/Prompt gates remain unknown');save(self.out/'presence.json',result);print('PRESENCE',result['summary'],flush=True)
 def spatial(self):
  assert read(self.out/'presence.json')['aggregation_version']=='joint_single_presence_witness_v1'
  m=read(self.out/'matching.json');presence={r['group_id']:r for r in read(self.out/'presence.json')['groups']};common=[g for g in m['groups'] if g['identity']=='matched' and presence[g['group_id']]['joint_presence_reasonable']];gm={g['group_id']:g for g in common};anchors=[m['local_origin_group_id'],m['local_reference_group_id']];fit=read(self.out/'registration/roma_geometry/registration.json')['fits']['all_structures'];rows=[]
  transform_ok=fit['status']=='numeric_candidate'
  if transform_ok:
   R=np.array(fit['rotation']);scale=fit['scale'];t=np.array(fit['translation'])
   def converted(box,side):
    if box is None:return None
    b=copy.deepcopy(box)
    if side==1:
     b['center_world']=(scale*R@np.array(box['center_world'])+t).tolist();b['size_xyz']=(scale*np.array(box['size_xyz'])).tolist();b['R_world_from_object']=(R@np.array(box['R_world_from_object'])).tolist()
     if 'corners_world' in box:b['corners_world']=(scale*np.array(box['corners_world'])@R.T+t).tolist()
    return b
   aligned=[]
   for side,g in enumerate(self.full):
    aligned.append(dict(shot_id=g['shot_id'],entities=[dict(entity_id=e['entity_id'],name=e['name'],motion_status=e['motion_status'],geometry=converted(e['geometry'],side),trajectory=[dict(frame_id=f['frame_id'],geometry=converted(f.get('geometry'),side)) for f in e['frame_evidence']]) for e in g['entities']]))
   save(self.out/'aligned_entities.json',dict(coordinate_system='fixed Shot1 scene, Z-up',transform_shot3_to_shot1={k:fit[k] for k in ['scale','rotation','translation']},shots=aligned))
  for a,b in itertools.combinations(common,2):
   vectors=[]
   for side,n in zip(['a','b'],self.nodes):vectors.append(np.array(n[b[side+'_ids'][0]]['geometry']['center_world'])-np.array(n[a[side+'_ids'][0]]['geometry']['center_world']))
   va,vb=vectors;cos=None;aligned=None
   if transform_ok:
    aligned=fit['scale']*np.array(fit['rotation'])@vb;den=np.linalg.norm(va)*np.linalg.norm(aligned)
    if den>1e-10:cos=float(np.clip(va@aligned/den,-1,1))
   rows.append(dict(relation_id='pair_'+a['group_id']+'_'+b['group_id'],endpoint_groups=[a['group_id'],b['group_id']],anchor_groups=anchors,cosine=cos,angle_deg=float(np.degrees(np.arccos(cos))) if cos is not None else None,vector_shot1=va.tolist(),vector_shot3=vb.tolist(),vector_shot3_aligned=None if aligned is None else aligned.tolist(),status='unknown',reason='nonnegative_not_further_reviewed' if cos is not None and cos>=0 else 'not_computable' if cos is None else 'negative_candidate'))
  save(self.out/'all_pair_cosines.json',rows);proposals=[r for r in rows if r['cosine'] is not None and r['cosine']<0];save(self.out/'negative_proposals.json',proposals)
  observations=[];payloads=[];refs_ok=len(set(anchors))==2 and all(k in gm for k in anchors)
  if proposals and refs_ok:
   for i,(g,side) in enumerate(zip(self.graphs,['a','b'])):
    ids=[gm[k][side+'_ids'][0] for k in anchors]
    try:rot,L=basis(self.nodes[i][ids[0]]['geometry']['center_world'],self.nodes[i][ids[1]]['geometry']['center_world'],[0,0,1])
    except ValueError:refs_ok=False;break
    payloads.append(dict(graph=g,references=[dict(origin_anchor_id=ids[0],reference_anchor_id=ids[1],basis_world=rot.tolist(),up_world=[0,0,1],anchor_baseline=L)],target_entity_ids=[q[side+'_ids'][0] for q in common if q['group_id'] not in anchors],images=[dict(attachment_index=j+1,shot_id=g['shot_id'],frame_id=f['frame_id'],image_size=next(c['image_size'] for c in g['cameras'] if c['frame_id']==f['frame_id'])) for j,f in enumerate(self.images[i])]))
   if refs_ok:
    with ThreadPoolExecutor(max_workers=2) as pool:observations=list(pool.map(lambda i:validate_single(self.call('observe_'+self.graphs[i]['shot_id'],'gs_relation_shot_v1.txt',payloads[i],self.images[i],SHOT_SCHEMA),payloads[i]),range(2)))
  save(self.out/'shot_relations.json',observations)
  # Adapt the previously tested local gates without changing their semantics.
  import importlib.util
  spec=importlib.util.spec_from_file_location('prior_review',B/'experiments/study2_keypoint_proposal_review_20260916/run_review.py');prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior);prior.ANCHORS=anchors
  kept=[]
  for r in proposals:
   if observations:
    obs=prior.local_observations(r,gm,observations);r['local_observations']=obs;eligible=not set(r['endpoint_groups'])&set(anchors) and all(set(o)==set(prior.AXES) for o in obs)
    r['local_axis_evidence']=prior.local_gates(obs,self.ix)
   else:eligible=False
   r['common_support_eligible']=eligible;r['reason']='passed_common_support' if eligible else 'reference_entity_is_endpoint' if set(r['endpoint_groups'])&set(anchors) else 'no_verified_common_support_or_reference'
   if eligible:kept.append(r)
  verified={'relations':[],'limitations':'no eligible negative proposal'}
  if kept:
   vp=dict(graphs=self.graphs,matching=dict(groups=common),relations=kept,images=self.ix,proposed_transform_shot3_scene_to_shot1_scene={k:fit[k] for k in ['scale','rotation','translation','yaw_deg']},registration_diagnostics={k:fit[k] for k in ['train','spatial_holdout']},normal_story_prompt=self.story,numerical_interface='negative cosine proposal; global geometry may be wrong; independent local physical evidence required')
   verified=self.call('verify_relations','verify_cosine.txt',vp,self.allimages,VERIFY)
  vm={v['relation_id']:v for v in verified['relations']};assert len(vm)==len(verified['relations']) and set(vm)=={r['relation_id'] for r in kept}
  for r in kept:
   v=vm[r['relation_id']];pr=v['prompt_motion_review'];assert set(pr['prompt_fact_references'])<=self.factids
   promptok=bool(pr['prompt_fact_references']) and all(pr[k].strip() for k in ['specified_motion','causal_explanation_of_observed_relation_change']);wok=all(validate_witnesses(v['witnesses_'+side],sid,self.ix) for side,sid in zip(['a','b'],['shot1','shot3']))
   visual=v['verdict']=='conflict' and all(v[k] for k in VERIFY_GATES) and wok and any(o['opposite_supported'] for o in r['local_axis_evidence'].values())
   if promptok and pr['verdict']=='explains_change':r.update(status='exempt',reason='prompt_motion_explains_specific_relation_change')
   elif promptok and pr['verdict']=='does_not_explain_change' and visual:r.update(status='conflict',reason='negative_cosine_and_independent_local_opposite_order_and_visual_gates_and_prompt_motion_excluded')
   else:r.update(status='unknown',reason='failed_visual_or_prompt_motion_gate')
   r['verification']=v;r['prompt_gate_pass']=promptok;r['visual_gate_pass']=visual
  result=dict(summary=score(rows, spatial=True),population_group_ids=list(gm),all_pairs=len(rows),negative_proposals=len(proposals),support_pass=len(kept),relations=rows,registration=fit,excluded_presence_groups=[r['group_id'] for r in presence.values() if r['partition']=='common_static' and not r['joint_presence_reasonable']]);save(self.out/'spatial.json',result);print('SPATIAL',result['summary'],len(proposals),len(kept),flush=True)
if __name__=='__main__':
 owned_compute_job();e=Eval(sys.argv[1]);getattr(e,sys.argv[2])()
