import sys,json,time,os
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import numpy as np
H=Path(__file__).resolve().parent;B=H.parents[1];sys.path.insert(0,str(B/'scripts'))
import run_partial_scene_comparison as transport
import run_wedetect_shot_entities as io
from run_isolated_shot_static_3d import SCHEMA,make_payload,validate_review,owned_compute_job
from build_three_method_static_scenes import candidate_rows,fuse_rows,projection_iou
transport.PROMPTS=H/'prompts'
def read(p):return json.loads(p.read_text())
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def run(case,sid):
 out=H/case;src=read(out/'inputs'/f'{sid}.json');root=out/'pi3x'/sid;g=read(root/'complete.json')
 frames=[read(root/'boxer_depth'/f'frame_{f["frame_id"]:06d}.json') for f in src['frames']];cams={f['frame_id']:f['camera'] for f in frames};pred={f['frame_id']:{e['entity_id']:dict(geometry=e['geometry'],confidence=e['confidence'],source_group=f'{sid}/{e["entity_id"]}/frame{f["frame_id"]}',source_path=str(root/'boxer_depth'/f'frame_{f["frame_id"]:06d}.json')) for e in f['entities']} for f in frames}
 entities=[]
 for e in src['entities']:
  entities.append(dict(entity_id=sid+'/'+e['entity_id'],name=e['name'],observations=e['observations'],states=[dict(frame_id=f['frame_id'],geometry=pred[f['frame_id']].get(e['entity_id'],{}).get('geometry')) for f in frames]))
 payload=make_payload(dict(shot_id=sid,calibration=dict(images=src['frames']),frames=[dict(frame_id=f['frame_id'],image_sha256=f['sha256'],K=cams[f['frame_id']]['K'],R_world_from_camera=cams[f['frame_id']]['R_world_from_camera'],translation_world_from_camera=cams[f['frame_id']]['position_world']) for f in src['frames']],entities=entities,world_frame_id=g['scene_frame_id'],scale=g['scale']))
 args=SimpleNamespace(out=out/'calls',model='gpt-6-astra',reasoning='medium',codex_bin='/vast/users/guangyi.chen/.local/bin/codex',timeout=1800,disabled_skills=io.disabled_skills_config())
 stage='motion_'+sid;d=args.out/stage
 if d.exists():
  assert read(d/'input.json')==payload and read(d/'status.json')['status']=='success';raw=read(d/'response.json')
 else:raw=transport.call(stage,'shot_motion_isolated_v0.2.txt',payload,[dict(f,shot_id=sid) for f in src['frames']],SCHEMA,args)
 validate_review(raw,payload);labels={e['entity_id']:e['status'] for e in raw['entities']};nodes=[]
 for source in src['entities']:
  e=dict(source,local_id=source['entity_id'],entity_id=sid+'/'+source['entity_id']);rows=candidate_rows(e,pred,cams);status=labels[e['entity_id']];box,info=fuse_rows(rows) if status=='static' else (None,None)
  if box is None:
   valid=[r for r in rows if r.get('geometry')]
   if valid:
    best=max(valid,key=lambda r:r.get('raw_quality',0));box=best['geometry'];info=dict(status='representative_frame',frame_id=best['frame_id'],reason='moving_or_unknown' if status!='static' else 'insufficient_fusion_support')
   else:info=dict(status='missing_geometry');status='unknown'
  nodes.append(dict(entity_id=e['entity_id'],name=e['name'],motion_status=status,geometry=box,aggregation=info,frame_evidence=rows,motion_label_source=str(d/'response.json')))
 graph=dict(schema_version='all_entity_scene_v1',shot_id=sid,method='pi3x_boxer_depth',coordinate_system=dict(world_frame_id=g['scene_frame_id'],origin='fixed own-shot scene cloud median',z_axis='up',per_frame_camera_poses=True,scale=g['scale']),cameras=list(cams.values()),entities=nodes,counts=dict(entities=len(nodes),static=sum(e['motion_status']=='static' for e in nodes)))
 save(out/'selected'/f'{sid}_scene.json',graph);save(out/'selected'/f'{sid}_static_scene.json',dict(graph,entities=[e for e in nodes if e['motion_status']=='static']))
 print(case,sid,graph['counts'],flush=True)
if __name__=='__main__':
 owned_compute_job();case=sys.argv[1]
 with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda s:run(case,s),['shot1','shot3']))
