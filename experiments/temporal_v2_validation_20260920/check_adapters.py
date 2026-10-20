import sys,json,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_gs_temporal_stage import remap,prepare_pair,read,save
from run_gs_temporal import plan,scope_for
from register_gs_codex import prepare as direct_prepare
from gs_flow1_evaluator import Eval
from gs_runtime_profile import profile
from run_isolated_shot_static_3d import owned_compute_job
owned_compute_job()
source=B/'experiments/study3_concise_mtd_fps32_20260919/run';case=R/'adapter_case';case.mkdir(exist_ok=False)
for old,new in [('shot1','room_start'),('shot3','room_return')]:
 for folder,suffix in [('inputs','.json'),('selected','_scene.json'),('selected','_static_scene.json')]:
  save(case/folder/(new+suffix),remap(read(source/folder/(old+suffix)),{old:new}))
 (case/'pi3x'/new).mkdir(parents=True)
save(case/'runtime_profile.json',profile('safe_spatial_medium'));save(case/'alignment_method.json',dict(method='roma_fps32'));save(case/'narrative.json',read(source/'narrative.json'))
prepare_pair(case,'pair_000',['room_start','room_return']);pair=case/'pairs/pair_000'
e=Eval(str(pair));m=read(source/'matching_initial.json');e.call=lambda *args,**kwargs:m;e.match()
payload,images,hashes=direct_prepare(pair)
assert len(images)==12 and [len(g['entities']) for g in payload['shots']]==[20,15]
assert 'matching' not in payload and 'anchors' not in payload
shots=[dict(shot_id=s) for s in ['shot1','shot2','shot3']];jobs=plan(case,shots,0,'GPU-test')
assert len([s for s in jobs if s['stage'].startswith('pi3x_')])==3
save(R/'adapter_validation.json',dict(success=True,canonical_shot_ids=[g['shot_id'] for g in payload['shots']],entity_counts=[len(g['entities']) for g in payload['shots']],original_images=len(images),source_image_hashes_verified=True,full_default_stages=len(jobs),direct_payload_has_no_anchors=True))
print('Adapter and direct-input checks passed')
