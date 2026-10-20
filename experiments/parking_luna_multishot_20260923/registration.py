#!/usr/bin/env python3
"""Incremental prompt-bound-gated direct registration for one multi-shot scene."""
import json, math, os, sys, time
from pathlib import Path
from types import SimpleNamespace

R=Path(__file__).resolve().parent; B=R.parents[1]
sys.path.insert(0,str(B/'scripts'))
import run_partial_scene_comparison as transport
import run_wedetect_shot_entities as io
from gs_consistency_contract import obj, arr, enum, S, N

case=R/'shared'/'parking4'; sids=['Shot1','Shot2','Shot3','Shot4']
def read(p): return json.loads(Path(p).read_text())
def save(p,x): io.dump(p,x)
SCHEMA=obj(decision=enum('register','new_group'),scale=dict(type=['number','null'],minimum=.1,maximum=10),yaw_deg=dict(type=['number','null']),translation=dict(type=['array','null'],items=N,minItems=3,maxItems=3),confidence=enum('low','medium','high'),reasoning=S,limitations=S)

matching=read(case/'global_initial/results.json')
bindings={sid:{x['entity_id']:x for x in read(case/'shot_prompt_recovery/shots'/sid/'binding_final.json')['bindings']} for sid in sids}
groups=[]
for g in matching['groups']:
    by={x.split('/',1)[0]:x.split('/',1)[1] for x in g['entity_ids']}
    groups.append((g['group_id'],by))

def shared(a,b):
    rows=[]
    for gid,by in groups:
        if a not in by or b not in by: continue
        x,y=bindings[a].get(by[a]),bindings[b].get(by[b])
        if x and y and x['status']=='bound' and y['status']=='bound' and x['prompt_entity_id']==y['prompt_entity_id']:
            rows.append(dict(global_group_id=gid,prompt_entity_id=x['prompt_entity_id'],prototype_local_id=by[a],new_local_id=by[b]))
    return rows

def shot_payload(sid, wanted):
    scene=read(case/'selected'/f'{sid}_scene.json'); inp=read(case/'inputs'/f'{sid}.json'); own={e['entity_id']:e for e in inp['entities']}
    entities=[]
    for e in scene['entities']:
        lid=e['entity_id'].split('/',1)[-1]
        if lid in wanted: entities.append(dict(local_entity_id=lid,name=e['name'],motion_status=e['motion_status'],geometry=e['geometry'],observations=own[lid]['observations']))
    return dict(shot_id=sid,coordinate_system=scene['coordinate_system'],cameras=scene['cameras'],entities=entities), [dict(f,shot_id=sid) for f in inp['frames']]

out=case/'direct_prompt_bound_luna'; out.mkdir()
roots=['Shot1']; rows=[dict(shot_id='Shot1',coordinate_group_id='group_01',prototype_shot_id='Shot1',status='root',attempts=[])]
start=time.time()
for sid in sids[1:]:
    attempts=[]; accepted=None
    for root in roots:
        common=shared(root,sid)
        if not common:
            attempts.append(dict(prototype_shot_id=root,status='skipped_no_shared_confirmed_prompt_bound_entity')); continue
        pids_root={x['prototype_local_id'] for x in common}; pids_new={x['new_local_id'] for x in common}
        ps,im1=shot_payload(root,pids_root); ns,im2=shot_payload(sid,pids_new); images=im1+im2
        payload=dict(new_shot_id=sid,prototype_shot_id=root,normal_story_prompt=read(case/'narrative.json'),shared_prompt_bound_entities=common,
                     shots=[ps,ns],image_order=[dict(attachment_index=i+1,shot_id=f['shot_id'],frame_id=f['frame_id']) for i,f in enumerate(images)],
                     transform_convention=f'{sid} to {root}: p_root=s Rz(yaw) p_new+t')
        args=SimpleNamespace(out=out/'calls',codex_bin='/vast/users/guangyi.chen/.local/bin/codex',disabled_skills=io.disabled_skills_config(),model=os.environ.get('EECBENCH_STAGE_MODEL','gpt-6-luna'),reasoning=os.environ.get('EECBENCH_REASONING','low'),timeout=1800)
        transport.PROMPTS=B/'prompts'; raw=transport.call(f'{sid}_to_{root}','gs_identity_guided_registration_v1.txt',payload,images,SCHEMA,args)
        attempt=dict(prototype_shot_id=root,shared_prompt_bound_entities=common,response=raw); attempts.append(attempt)
        if raw['decision']=='register':
            vals=[raw['scale'],raw['yaw_deg'],*raw['translation']]
            if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in vals): raise ValueError('nonfinite transform')
            accepted=attempt; break
    if accepted:
        gi=next(x['coordinate_group_id'] for x in rows if x['shot_id']==accepted['prototype_shot_id'])
        rows.append(dict(shot_id=sid,coordinate_group_id=gi,prototype_shot_id=accepted['prototype_shot_id'],status='registered',attempts=attempts,transform=accepted['response']))
    else:
        roots.append(sid); rows.append(dict(shot_id=sid,coordinate_group_id=f'group_{len(roots):02d}',prototype_shot_id=sid,status='new_group',attempts=attempts))
    save(out/'results.json',dict(status='running',roots=roots,shots=rows,seconds=time.time()-start))
save(out/'results.json',dict(status='success',method='incremental_codex_identity_guided_prompt_bound',model=os.environ.get('EECBENCH_API_MODEL','gpt-6-luna'),reasoning=os.environ.get('EECBENCH_REASONING','low'),roots=roots,shots=rows,seconds=time.time()-start,rule='A transform call is allowed only for a pair with one or more confirmed shared prompt-bound identities. Moving entities remain visible evidence but are not declared static anchors.'))
