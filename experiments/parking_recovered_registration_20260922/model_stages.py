import sys,json,copy,math,time,os
from pathlib import Path
from types import SimpleNamespace
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from gs_consistency_contract import obj,arr,S,N,enum
from register_gs_codex import SCHEMA as OLD_TRANSFORM,make_fit
from run_gs_integrated import read,save,sha
import run_partial_scene_comparison as transport
import run_wedetect_shot_entities as io
from gs_flow1_evaluator import clean

def args(out):
 return SimpleNamespace(out=out,model=os.environ.get('EECBENCH_STAGE_MODEL','gpt-6-astra'),reasoning=os.environ.get('EECBENCH_REASONING','medium'),codex_bin='/vast/users/guangyi.chen/.local/bin/codex',timeout=1800,disabled_skills=io.disabled_skills_config())
def image_inputs(case,sids):
 images=[]
 for sid in sids:
  src=read(case/'inputs'/f'{sid}.json')
  images += [dict(f,shot_id=sid) for f in src['frames']]
 return images

def initial(case):
 sids=[s['shot_id'] for s in read(case/'raw_manifest.json')['shots']];graphs=[];images=image_inputs(case,sids)
 for sid in sids:
  g=clean(read(case/'selected'/f'{sid}_scene.json'),static_only=False);src=read(case/'inputs'/f'{sid}.json');obs={sid+'/'+e['entity_id']:e['observations'] for e in src['entities']}
  for e in g['entities']:e['observations']=obs[e['entity_id']]
  graphs.append(g)
 payload=dict(graphs=graphs,normal_story_prompt=read(case/'narrative.json'),images=[dict(attachment_index=i+1,shot_id=f['shot_id'],frame_id=f['frame_id']) for i,f in enumerate(images)])
 nodes={e['entity_id']:e for g in graphs for e in g['entities']}
 entity_list=dict(type='array',items=enum(*nodes),minItems=1)
 schema=obj(groups=arr(obj(group_id=enum(*[f'g{i:02d}' for i in range(1,len(nodes)+1)]),entity_ids=entity_list,identity_evidence=S,anchor_pairs=arr(obj(shot_a=enum(*sids),shot_b=enum(*sids),reason=S)))),unresolved=arr(obj(entity_ids=dict(entity_list,minItems=2),status=enum('ambiguous','scope_mismatch'),reason=S)),limitations=S)
 save(case/'global_initial/canonical_input.json',payload)
 # Same lossless compact tables as existing model transport. All evidence retained.
 from gs_flow1_compact_transport import call
 raw=call('global_initial',str(R/'global_match.txt'),payload,images,schema,args(case/'calls'))
 nodes={e['entity_id']:e for g in graphs for e in g['entities']};seen=[]
 for i,g in enumerate(raw['groups'],1):
  assert g['group_id']==f'g{i:02d}'
  ids=g['entity_ids'];assert ids and len({x.split('/')[0] for x in ids})==len(ids)
  assert all(x in nodes for x in ids);seen+=ids
  by={x.split('/')[0]:nodes[x] for x in ids};pairs=set()
  for p in g['anchor_pairs']:
   a,b=p['shot_a'],p['shot_b'];assert a in by and b in by and a!=b and p['reason'].strip()
   k=tuple(sorted([a,b]));assert k not in pairs;pairs.add(k)
   assert all(by[s]['motion_status']=='static' and by[s]['geometry'] for s in (a,b))
 assert len(seen)==len(set(seen)) and set(seen)==set(nodes)
 for u in raw['unresolved']:
  assert len(u['entity_ids'])>=2 and len(u['entity_ids'])==len(set(u['entity_ids'])) and set(u['entity_ids'])<=set(nodes)
 save(case/'global_initial/results.json',raw);return raw

def direct(case):
 start=time.time();sids=[s['shot_id'] for s in read(case/'raw_manifest.json')['shots']];roots=[sids[0]];rows=[dict(shot_id=sids[0],prototype=sids[0],status='root',fit=None)]
 numeric=obj(scale=dict(type='number',minimum=.1,maximum=10),yaw_deg=N,translation=dict(type='array',items=N,minItems=3,maxItems=3))
 for sid in sids[1:]:
  images=image_inputs(case,roots+[sid]);shots=[]
  for s in roots+[sid]:
   scene=read(case/'selected'/f'{s}_scene.json');src=read(case/'inputs'/f'{s}.json');own={e['entity_id']:e for e in src['entities']}
   shots.append(dict(shot_id=s,coordinate_system=scene['coordinate_system'],cameras=scene['cameras'],entities=[dict(entity_id=e['entity_id'],name=e['name'],motion_status=e['motion_status'],geometry=e['geometry'],observations=own[e['entity_id'].split('/')[-1]]['observations']) for e in scene['entities']]))
  schema=obj(decision={'anyOf':[obj(status=enum('register'),prototype_shot_id=enum(*roots),transform=numeric),obj(status=enum('new_group'),prototype_shot_id=dict(type='null'),transform=dict(type='null'))]},confidence=enum('low','medium','high'),reasoning=S,limitations=S)
  payload=dict(new_shot_id=sid,prototype_shot_ids=roots.copy(),shots=shots,normal_story_prompt=read(case/'narrative.json'),images=[dict(attachment_index=i+1,shot_id=f['shot_id'],frame_id=f['frame_id']) for i,f in enumerate(images)])
  transport.PROMPTS=R;raw=transport.call('direct_'+sid,'direct.txt',payload,images,schema,args(case/'calls'));d=raw['decision']
  if d['status']=='new_group':roots.append(sid);row=dict(shot_id=sid,prototype=sid,status='root_abstained',fit=None)
  else:
   fit=make_fit(dict(**d['transform'],**{k:raw[k] for k in ['confidence','reasoning','limitations']}));row=dict(shot_id=sid,prototype=d['prototype_shot_id'],status='numeric_candidate',fit=fit)
  rows.append(row);save(case/'direct/results.json',dict(method='codex_direct_prototype',status='running',roots=roots,shots=rows,seconds=time.time()-start))
 result=dict(method='codex_direct_prototype',status='success',roots=roots,shots=rows,seconds=time.time()-start,acceptance='model register/abstain; finite schema only, confidence is not measured accuracy')
 save(case/'direct/results.json',result);return result
if __name__=='__main__':
 case=Path(sys.argv[2]).resolve()
 from run_isolated_shot_static_3d import owned_compute_job
 owned_compute_job()
 try:{'initial':initial,'direct':direct}[sys.argv[1]](case)
 except BaseException as exc:
  # Preserve original output/usage on post-response semantic validation errors.
  calls=[case/'calls/global_initial'] if sys.argv[1]=='initial' else sorted((case/'calls').glob('direct_*'))[-1:]
  for d in calls:
   p=d/'status.json'
   if p.exists():
    status=read(p)
    if status.get('status')=='success':status.update(status='failed',validation_phase='semantic_post_response',error=repr(exc));save(p,status)
  raise
