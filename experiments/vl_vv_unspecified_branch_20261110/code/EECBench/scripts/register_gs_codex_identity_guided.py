#!/usr/bin/env python3
"""Prompt-bound identity-gated direct Shot3->Shot1 Codex registration."""
import argparse, hashlib, json, math
from pathlib import Path
from types import SimpleNamespace
from gs_consistency_contract import obj,S,N,enum,arr
import run_partial_scene_comparison as transport
import run_wedetect_shot_entities as io
B=Path(__file__).resolve().parents[1]
SCHEMA=obj(decision=enum('register','abstain'),scale=dict(type=['number','null'],minimum=.1,maximum=10),yaw_deg=dict(type=['number','null']),translation=dict(type=['array','null'],items=N,minItems=3,maxItems=3),confidence=enum('low','medium','high'),reasoning=S,limitations=S)
def read(p): return json.loads(Path(p).read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--case',type=Path,required=True);p.add_argument('--matching',type=Path,required=True);p.add_argument('--bindings',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--model',default='gpt-6-astra');p.add_argument('--reasoning',default='medium');a=p.parse_args();case=a.case.resolve();out=a.output.resolve()
 if out.exists(): raise FileExistsError('use a fresh output directory')
 match=read(a.matching); bind={sid:{x['entity_id']:x for x in read(a.bindings/sid/'binding_final.json')['bindings']} for sid in ('Shot1','Shot3')}
 shared=[]
 for g in match['groups']:
  ids={x.split('/')[0]:x.split('/')[1] for x in g['entity_ids']}
  if not {'Shot1','Shot3'}<=set(ids): continue
  x,y=bind['Shot1'].get(ids['Shot1']),bind['Shot3'].get(ids['Shot3'])
  if not x or not y or x['status']!='bound' or y['status']!='bound' or x['prompt_entity_id']!=y['prompt_entity_id']: continue
  shared.append(dict(global_group_id=g['group_id'],prompt_entity_id=x['prompt_entity_id'],shot1_local_id=ids['Shot1'],shot3_local_id=ids['Shot3']))
 if not shared: raise ValueError('no confirmed shared prompt-bound entity; Codex call forbidden')
 shots=[];images=[]
 for sid in ('Shot1','Shot3'):
  scene=read(case/'selected'/f'{sid}_scene.json');inp=read(case/'inputs'/f'{sid}.json');own={e['entity_id']:e for e in inp['entities']};needed={r['shot1_local_id'] if sid=='Shot1' else r['shot3_local_id'] for r in shared}
  ents=[]
  for e in scene['entities']:
   lid=e['entity_id'].split('/')[-1]
   if lid in needed: ents.append(dict(local_entity_id=lid,name=e['name'],motion_status=e['motion_status'],geometry=e['geometry'],observations=own[lid]['observations']))
  shots.append(dict(shot_id=sid,coordinate_system=scene['coordinate_system'],cameras=scene['cameras'],entities=ents))
  images += [dict(f,shot_id=sid) for f in inp['frames']]
 payload=dict(normal_story_prompt=read(case/'narrative.json'),shared_prompt_bound_entities=shared,shots=shots,image_order=[dict(attachment_index=i+1,shot_id=f['shot_id'],frame_id=f['frame_id']) for i,f in enumerate(images)],transform_convention='Shot3 to Shot1: p1=s Rz(yaw) p3+t')
 args=SimpleNamespace(out=out/'calls',codex_bin='/vast/users/guangyi.chen/.local/bin/codex',disabled_skills=io.disabled_skills_config(),model=a.model,reasoning=a.reasoning,timeout=1800);transport.PROMPTS=B/'prompts';raw=transport.call('identity_guided_registration','gs_identity_guided_registration_v1.txt',payload,images,SCHEMA,args)
 result=dict(method='codex_identity_guided',model=a.model,reasoning=a.reasoning,shared_prompt_bound_entities=shared,response=raw)
 if raw['decision']=='register':
  v=[raw['scale'],raw['yaw_deg'],*raw['translation']];
  if not all(math.isfinite(z) for z in v):raise ValueError('nonfinite transform')
 out.mkdir(parents=True,exist_ok=True);(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));(out/'payload.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__': main()
