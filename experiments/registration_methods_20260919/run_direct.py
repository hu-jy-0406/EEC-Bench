"""Two independent, tools-disabled Codex direct-transform calls; no optimizer."""
import json,hashlib,sys,time
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parents[1];sys.path.insert(0,str(BASE/'scripts'))
import run_wedetect_shot_entities as io
from run_partial_scene_comparison import call
from run_isolated_shot_static_3d import owned_compute_job
from gs_consistency_contract import obj,S,N,enum
CASES={'study2':BASE/'experiments/study2_integrated_full_fresh_20260919/study2','study3':BASE/'experiments/study3/run_cpu02'}
read=lambda p:json.loads(p.read_text())
SCHEMA=obj(scale=dict(type='number',minimum=.1,maximum=10),yaw_deg=N,translation=dict(type='array',items=N,minItems=3,maxItems=3),confidence=enum('low','medium','high'),reasoning=S,limitations=S)

def run_case(name,disabled):
 case=CASES[name];out=ROOT/name;out.mkdir(parents=True,exist_ok=True);shots=[];images=[]
 for sid in ['shot1','shot3']:
  scene=read(case/'selected'/f'{sid}_scene.json');inp=read(case/'inputs'/f'{sid}.json')
  shots.append(dict(shot_id=sid,coordinate_system=scene['coordinate_system'],cameras=scene['cameras'],
                    entities=[dict(entity_id=e['entity_id'],name=e['name'],motion_status=e['motion_status'],geometry=e['geometry'],observations=next(v['observations'] for v in inp['entities'] if v['entity_id']==e['entity_id'].split('/')[-1])) for e in scene['entities']]))
  images += [dict(f,shot_id=sid) for f in inp['frames']]
 payload=dict(stage='direct_scene_transform_estimate',normal_story_prompt=read(case/'narrative.json'),shots=shots,
              images=[dict(attachment_index=i+1,shot_id=f['shot_id'],frame_id=f['frame_id']) for i,f in enumerate(images)],
              transform_convention='Shot3 to Shot1, positive scale, right-handed Z yaw, xyz translation; model units')
 args=SimpleNamespace(out=out,codex_bin='/vast/users/guangyi.chen/.local/bin/codex',disabled_skills=disabled,model='gpt-6-astra',reasoning='medium',timeout=1800)
 result=call('m2_direct','gs_direct_registration_v1.txt',payload,images,SCHEMA,args)
 io.dump(out/'m2_direct/transform.json',result);return name

if __name__=='__main__':
 owned_compute_job();start=time.time();disabled=io.disabled_skills_config()
 with ThreadPoolExecutor(max_workers=2) as pool:
  for name in pool.map(lambda n:run_case(n,disabled),CASES):print('DONE',name,flush=True)
 print('direct wall seconds',time.time()-start,flush=True)
