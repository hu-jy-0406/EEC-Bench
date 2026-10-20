"""Deterministic evidence/score audit; explicitly frozen downstream composition."""
import copy,json,shutil,sys
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_gs_temporal_stage import read,save
from gs_flow1_compact_payload import unpack,equivalent
from gs_temporal_contract import GATES
from gs_temporal_review import validate_checks
from gs_temporal_core import boundary_proposals,aggregate
from gs_boundary_spatial_review import finalize
from gs_entity_displacement import evaluate,write
from gs_episode_entities import export_registry
from run_isolated_shot_static_3d import owned_compute_job
owned_compute_job()
base=B/'experiments/study3_final_integrated_20260921/run';pair=base/'pairs/pair_000';checks={}
for name,old,new in [('identity',pair/'calls/identity_review',R/'identity/calls/identity_review'),('presence',pair/'calls/boundary_review_000',R/'presence/calls/boundary_review_000')]+[('alignment_'+p.name,base/'prompt_alignment/calls'/p.name,p) for p in sorted((R/'alignment/calls').iterdir())]:
    canonical=read(new/'input.json');assert canonical==read(old/'input.json'),name
    equivalent(canonical,unpack(read(new/'wire_input.json')))
    oldimages=read(old/'request.json')['images'];newimages=read(new/'request.json')['images']
    assert [(f['shot_id'],f['frame_id'],f['sha256']) for f in oldimages]==[(f['shot_id'],f['frame_id'],f['sha256']) for f in newimages],name
    checks[name]=dict(canonical_input_identical=True,encoding_roundtrip=True,all_original_image_hashes_identical=True)
# Removing unused presence fields changes no finalized judgment on existing responses.
payload=read(pair/'calls/boundary_review_000/input.json');raw=read(pair/'calls/boundary_review_000/response.json');images=[]
for sid in ('shot1','shot3'):
    src=read(pair/'inputs'/f'{sid}.json');images += [dict(f,shot_id=sid,image_size=size) for f,size in zip(src['frames'],src['image_sizes'])]
slim=copy.deepcopy(raw)
for row in slim['checks']:
    for k in GATES[5:]:del row[k]
a=validate_checks(raw,payload,images,payload['normal_story_prompt'],boundary=True)
b=validate_checks(slim,payload,images,payload['normal_story_prompt'],boundary=True,presence_only_schema=True)
assert {k:{x:y for x,y in r.items() if x!='review'} for k,r in a.items()}=={k:{x:y for x,y in r.items() if x!='review'} for k,r in b.items()}
# Compose the changed identity map with fresh per-event presence answers whose exact
# event rows remain unchanged. Changed/unresolved identities use core base_status.
case=R/'composition_case_v3';case.mkdir();dest=case/'pairs/pair_000';dest.mkdir(parents=True)
for name in ('raw_manifest.json','identity_scope.json'):shutil.copy2(base/name,case/name)
for name in ('entities','selected'):(case/name).symlink_to(base/name,target_is_directory=True)
for name in ('selected','inputs','registration'):(dest/name).symlink_to(pair/name,target_is_directory=True)
for name in ('matching.json','identity_review.json','identity_review_audit.json'):shutil.copy2(R/'identity'/name,dest/name)
shutil.copy2(pair/'pair_scope.json',dest/'pair_scope.json')
graphs=[read(dest/'selected'/f'{s}_scene.json') for s in ('shot1','shot3')];matching=read(dest/'matching.json');reg=read(dest/'registration/roma_geometry/registration.json')
prop=boundary_proposals(graphs,matching,reg['fits']['all_structures']);oldprop=read(pair/'boundary/proposals.json');assert prop['spatial_units']==oldprop['spatial_units']
old_events={e['event_id']:e for e in oldprop['events']};fresh=read(R/'presence/results.json')['checks'];presence={}
for ev in prop['events']:
    if ev['kind']!='presence':continue
    assert ev==old_events[ev['event_id']]
    presence[ev['event_id']]=fresh[ev['event_id']]
spatial=finalize([e for e in prop['events'] if e['kind']=='spatial'],read(pair/'calls/boundary_spatial_verify/response.json'),read(pair/'boundary/local_support.json'),prop,images,payload['normal_story_prompt'],{v['group_id']:v['status'] for v in presence.values()})
rows=dict(presence,**spatial);boundary=dict(status='success',events=list(rows.values()),presence=aggregate(prop['presence_units'],rows),spatial=aggregate(prop['spatial_units'],rows,spatial=True),source='offline_composition_not_new_full_boundary_call')
save(dest/'boundary/results.json',boundary)
oldboundary=read(pair/'boundary/results.json');assert boundary['spatial']==oldboundary['spatial']
position=evaluate(case);oldposition=read(base/'displacement/results.json');assert {k:v['score'] for k,v in position['episode'].items()}=={k:v['score'] for k,v in oldposition['episode'].items()};assert [r for r in position['records'] if r['r_e'] is not None]==[r for r in oldposition['records'] if r['r_e'] is not None];write(position,case/'displacement')
export_registry(case,case/'global_entities');registry=read(case/'global_entities/global_entities.json');oldregistry=read(base/'global_entities/global_entities.json')
def occurrences(r):return [(e['global_entity_id'],[(a['shot_id'],a['local_entity_id']) for a in e['appearances']]) for e in r['entities']]
assert occurrences(registry)==occurrences(oldregistry)
result=dict(status='pass',input_checks=checks,legacy_presence_projection_exact=True,confirmed_identity_links_unchanged=True,global_visual_occurrences_exact=True,
    old_registry_counts=oldregistry['counts'],new_registry_counts=registry['counts'],all_scored_raw_position_records_exact=True,position_scores_exact=True,old_position_counts=oldposition['episode'],new_position_counts=position['episode'],boundary_spatial_exact=True,
    old_presence=oldboundary['presence']['summary'],composed_presence=boundary['presence']['summary'],
    limitation='One plant pair changes unmatched to ambiguous. Two former exempt presence units become one unresolved unit; presence denominator changes. Composition reuses old local-spatial judgments and new fixed-old-map presence judgments for identical events only; not a fresh end-to-end evaluation. Appearance/binding/alignment calls were not rerun on this composed registry.',model_calls=0,tokens=0,api_usd=0)
save(R/'audit.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))
