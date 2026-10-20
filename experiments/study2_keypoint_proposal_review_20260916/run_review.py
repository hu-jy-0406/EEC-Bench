"""Frozen RoMa cosine proposals through adapted v1.2 visual review gates."""
import argparse,copy,csv,difflib,itertools,json,os,shutil,sys,time
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import numpy as np
HERE=Path(__file__).resolve().parent;BASE=HERE.parents[1];sys.path.insert(0,str(BASE/'scripts'))
import run_partial_scene_comparison as transport
import run_wedetect_shot_entities as io
from run_isolated_shot_static_3d import owned_compute_job
from run_gs_consistency import read,save,sha
from run_gs_spatial_consistency import validate_single
from gs_spatial_relations import basis
from gs_relation_contract import SHOT_SCHEMA,VERIFY_SCHEMA
from score_gs_spatial_consistency import VERIFY_GATES,validate_witnesses
OLD=BASE/'experiments/shot_scene_boxes_goal_20260916';SOURCE=BASE/'experiments/study2_multiframe_image_registration_20260916/run01';FROZEN=BASE/'releases/gs-consistency-v1.2/payload/EECBench';MATCH=BASE/'experiments/study2_static_set_consistency_20260916/run01/matching.json'
AXES=['cross_anchor_up','toward_reference','vertical'];ANCHORS=['g04','g12']

def clean(g):
 result={k:copy.deepcopy(g[k]) for k in ['shot_id','method','coordinate_system','cameras']};result['entities']=[]
 for e in g['entities']:
  if e['motion_status']!='static':continue
  n={k:copy.deepcopy(e[k]) for k in ['entity_id','name','geometry','motion_status']};n['center_mad_xyz']=e['aggregation'].get('center_mad_xyz');n['frame_evidence']=[{k:r[k] for k in ['frame_id','visible','box_xyxy','eligible','selected','geometry','projection_iou'] if k in r} for r in e['frame_evidence']];result['entities'].append(n)
 return result

def local_observations(proposal,matching,observations):
 out=[]
 for side,raw in zip(['a','b'],observations):
  ids=[matching[x][side+'_ids'][0] for x in proposal['endpoint_groups']];refs=[matching[x][side+'_ids'][0] for x in ANCHORS];byaxis={}
  for r in raw['relations']:
   if [r['subject_id'],r['object_id']]==sorted(ids) and [r['origin_anchor_id'],r['reference_anchor_id']]==refs:
    o=copy.deepcopy(r)
    if ids!=sorted(ids):o['order']={'positive':'negative','negative':'positive','unknown':'unknown'}[o['order']]
    o['canonical_center_subtraction']='first endpoint group center minus second endpoint group center';byaxis[r['axis']]=o
  out.append(byaxis)
 return out

def local_gates(obs,image_index):
 details={}
 for axis in AXES:
  checks=[];orders=[]
  for sid,m in zip(['shot1','shot3'],obs):
   o=m.get(axis)
   if not o:checks.append(False);orders.append(0);continue
   enough=validate_witnesses(o['evidence'],sid,image_index);orders.append({'negative':-1,'positive':1,'unknown':0}[o['order']]);checks.append(bool(enough and o['reference_direction_verified'] and o['common_support_verified'] and o['center_order_supported'] and not o['geometry_error_can_reverse'] and orders[-1]!=0))
  details[axis]={'per_shot_evidence_pass':checks,'orders':orders,'opposite_supported':all(checks) and orders[0]*orders[1]==-1}
 return details

def main():
 p=argparse.ArgumentParser();p.add_argument('--resume',action='store_true');a=p.parse_args();job=owned_compute_job();out=HERE/'run01';out.mkdir(exist_ok=True)
 if os.getloadavg()[0]>max(8,(os.cpu_count() or 1)*.5):raise RuntimeError('Busy compute node')
 transport.PROMPTS=HERE/'prompts';args=SimpleNamespace(out=out,model='gpt-6-astra',reasoning='medium',codex_bin='codex',timeout=1800,disabled_skills=io.disabled_skills_config())
 graphs=[clean(read(OLD/'selected'/f'{s}_scene.json')) for s in ['shot1','shot3']];nodes=[{e['entity_id']:e for e in g['entities']} for g in graphs]
 common=[g for g in read(MATCH)['groups'] if g['identity']=='matched' and len(g['a_ids'])==len(g['b_ids'])==1 and g['a_ids'][0] in nodes[0] and g['b_ids'][0] in nodes[1]];assert len(common)==11;matching={g['group_id']:g for g in common}
 # Only numeric fields go to candidate selection. No historical labels/ranks/target summaries.
 source_rows=read(SOURCE/'results/relations.json');proposals=[]
 for r in sorted(source_rows,key=lambda r:(r['group_a'],r['group_b'])):
  if r['cosine']<0:proposals.append({'relation_id':'pair_'+r['group_a']+'_'+r['group_b'],'endpoint_groups':[r['group_a'],r['group_b']],'anchor_groups':ANCHORS,'cosine':r['cosine'],'angle_deg':r['angle_deg'],'vector_shot1':r['vector_shot1'],'vector_shot3_aligned':r['vector_shot3_aligned'],'vector_subtraction':'second endpoint center minus first endpoint center in BOTH shots; cosine invariant to reversing BOTH'})
 assert len(proposals)==31;save(out/'proposals.json',proposals)
 sourcepaths=[SOURCE/'results/relations.json',SOURCE/'roma_geometry/registration.json',MATCH]+[OLD/'selected'/f'{s}_scene.json' for s in ['shot1','shot3']]+[OLD/'inputs'/f'{s}.json' for s in ['shot1','shot3']]
 sourcehash={str(p):sha(p) for p in sourcepaths};save(out/'source_hashes.json',sourcehash)
 imagegroups=[];payloads=[]
 for i,(g,side) in enumerate(zip(graphs,['a','b'])):
  fs=read(OLD/'inputs'/f'{g["shot_id"]}.json')['frames'];images=[dict(f,shot_id=g['shot_id']) for f in fs]
  for f in images:assert sha(f['path'])==f['sha256']
  imagegroups.append(images);ids=[matching[k][side+'_ids'][0] for k in ANCHORS];rot,L=basis(nodes[i][ids[0]]['geometry']['center_world'],nodes[i][ids[1]]['geometry']['center_world'],[0,0,1])
  refs=[dict(origin_anchor_id=ids[0],reference_anchor_id=ids[1],basis_world=rot.tolist(),up_world=[0,0,1],anchor_baseline=L)]
  targets=[m[side+'_ids'][0] for m in common if m['group_id'] not in ANCHORS]
  ix=[dict(attachment_index=j+1,shot_id=g['shot_id'],frame_id=f['frame_id'],image_size=next(c['image_size'] for c in g['cameras'] if c['frame_id']==f['frame_id'])) for j,f in enumerate(images)]
  payloads.append(dict(graph=g,references=refs,target_entity_ids=targets,images=ix))
 save(out/'input_manifest.json',{'sources':sourcehash,'images':imagegroups,'candidate_rule':'all and only cosine < 0 among 55 frozen unordered static-intersection pairs','proposal_count':31,'no_frame_reencoding':True})
 state={'status':'running','started':time.time(),'allocation':job,'model':args.model,'reasoning':args.reasoning,'expected_labels_provided':False,'proposal_count':31};save(out/'run.json',state)
 def call(stage,prompt,payload,images,schema):
  d=out/stage
  if d.exists():
   if not a.resume or read(d/'input.json')!=payload or read(d/'status.json')['status']!='success':raise RuntimeError('Refusing changed/failed stage reuse '+stage)
   return read(d/'response.json')
  return transport.call(stage,prompt,payload,images,schema,args)
 try:
  def observe(i):return validate_single(call('observe_'+graphs[i]['shot_id'],'gs_relation_shot_v1.txt',payloads[i],imagegroups[i],SHOT_SCHEMA),payloads[i])
  with ThreadPoolExecutor(max_workers=2) as pool:observations=list(pool.map(observe,range(2)))
  save(out/'shot_relations.json',observations);print('SHOT_OBSERVATIONS_COMPLETE',[(o['shot_id'],len(o['relations'])) for o in observations],flush=True)
  ledger=[];kept=[]
  for p in proposals:
   obs=local_observations(p,matching,observations);eligible=not set(p['endpoint_groups'])&set(ANCHORS) and all(set(o)==set(AXES) for o in obs)
   r={**p,'local_observations':obs,'common_support_eligible':bool(eligible),'filter_reason':'passed_common_support' if eligible else ('reference_entity_is_endpoint' if set(p['endpoint_groups'])&set(ANCHORS) else 'no_verified_common_support_in_both_shots')};ledger.append(r)
   if eligible:kept.append(r)
  save(out/'support_filter.json',ledger);print('COMMON_SUPPORT_SURVIVORS',len(kept),[r['relation_id'] for r in kept],flush=True)
  images=[f for fs in imagegroups for f in fs];image_index=[]
  for j,f in enumerate(images):image_index.append(dict(attachment_index=j+1,shot_id=f['shot_id'],frame_id=f['frame_id'],image_size=[852,480]))
  fit=read(SOURCE/'roma_geometry/registration.json')['fits']['all_structures']
  transform={k:fit[k] for k in ['scale','rotation','translation','yaw_deg']};diag={k:fit[k] for k in ['train','spatial_holdout']}
  verify_payload={'graphs':graphs,'matching':{'groups':common},'relations':kept,'images':image_index,'proposed_transform_shot3_scene_to_shot1_scene':transform,'registration_diagnostics':diag,'numerical_interface':'negative cosine shortlist only; no calibrated uncertainty interval; per-shot local axes are independently defined by their own structural references'}
  if kept:verified=call('verify_relations','verify_cosine.txt',verify_payload,images,VERIFY_SCHEMA)
  else:verified={'relations':[],'limitations':'No candidate survived same-support gate'}
  save(out/'verified_relations.json',verified)
  import jsonschema
  jsonschema.validate(verified,VERIFY_SCHEMA);vr={v['relation_id']:v for v in verified['relations']};assert len(vr)==len(verified['relations']) and set(vr)=={r['relation_id'] for r in kept}
  for r in ledger:
   r['local_axis_evidence']=local_gates(r['local_observations'],image_index);v=vr.get(r['relation_id']);r['verification']=v;ok=False
   if v:
    witness_checks=[validate_witnesses(v['witnesses_'+side],sid,image_index) for side,sid in zip(['a','b'],['shot1','shot3'])];r['verifier_witnesses_pass']=witness_checks
    ok=v['verdict']=='conflict' and all(v[k] for k in VERIFY_GATES) and all(witness_checks) and any(x['opposite_supported'] for x in r['local_axis_evidence'].values())
   r['status']='conflict' if ok else 'unknown';r['final_reason']='negative_cosine_candidate_plus_independent_local_order_and_cross_shot_visual_evidence' if ok else (r['filter_reason'] if not r['common_support_eligible'] else 'failed_single_shot_or_cross_shot_visual_gate')
  save(out/'results.json',ledger)
  summary={'proposals':31,'common_support_pass':len(kept),'cross_shot_reviewed':len(vr),'verifier_conflict_count':sum(v['verdict']=='conflict' for v in vr.values()),'admitted_conflicts':[r['relation_id'] for r in ledger if r['status']=='conflict'],'unknown':sum(r['status']=='unknown' for r in ledger),'scope':'31 frozen negative-cosine proposals; remaining 24 not judged; unchanged existence results not recomputed','method_change':'cosine proposal interface replaces v1.2 numeric interval gate; same single-shot prompt and original seven visual verifier gates; local opposite-order evidence required','global_alignment_validated':False,'historical_scores_modified':False};save(out/'summary.json',summary)
  # Audit source/frame integrity and actual isolated requests.
  assert sourcehash=={str(p):sha(p) for p in sourcepaths}
  for i,g in enumerate(graphs):
   req=read(out/('observe_'+g['shot_id'])/'request.json');assert len(req['images'])==6 and all(f['shot_id']==g['shot_id'] for f in req['images']);assert all('shot'+str(3 if i==0 else 1)+'/' not in json.dumps(e) for e in payloads[i]['graph']['entities'])
   assert 'matching' not in payloads[i] and 'cosine' not in json.dumps(payloads[i])
  for fs in imagegroups:
   for f in fs:assert sha(f['path'])==f['sha256']
  assert sha(HERE/'prompts/gs_relation_shot_v1.txt')==sha(FROZEN/'prompts/gs_relation_shot_v1.txt')
  snap=out/'code_snapshot';snap.mkdir(exist_ok=True)
  for src in [Path(__file__),HERE/'PLAN.md',*list((HERE/'prompts').glob('*.txt')),*[BASE/'scripts'/n for n in ['run_partial_scene_comparison.py','run_gs_spatial_consistency.py','gs_relation_contract.py','gs_spatial_relations.py','score_gs_spatial_consistency.py']]]:shutil.copy2(src,snap/src.name)
  diff=''.join(difflib.unified_diff((FROZEN/'prompts/gs_relation_verify_v1.txt').read_text().splitlines(True),(HERE/'prompts/verify_cosine.txt').read_text().splitlines(True),fromfile='frozen_v1.2',tofile='cosine_interface'));(out/'verify_prompt.diff').write_text(diff)
  audit={'passed':True,'source_hashes_unchanged':True,'original_jpegs_unchanged':12,'per_shot_contexts_independent':True,'single_shot_prompt_byte_identical_v1_2':True,'proposal_coverage':31,'verifier_exact_survivor_coverage':len(vr),'schema_and_witness_coordinates_checked':True,'code_hashes':{x.name:sha(x) for x in snap.iterdir()}};save(out/'audit.json',audit)
  state['status']='success';state['summary']=summary;print('COMPLETE',json.dumps(summary,ensure_ascii=False),flush=True)
 except BaseException as ex:state.update(status='failed',error=repr(ex));raise
 finally:
  state.update(ended=time.time(),calls=[dict(stage=p.parent.name,**read(p)) for p in out.glob('*/status.json')]);save(out/'run.json',state)
if __name__=='__main__':main()
