#!/usr/bin/env python3
"""Strict extraction, alignment and materialized scene contracts."""
import json
from pathlib import Path
from partial_scene_contract import obj,arr,enum,STR,INT,BOOL,EVIDENCE,ALIGNMENT_SCHEMA
from sparse_scene_3d import RAW_SCHEMA,ALIGN_SCHEMA,NUM,vec,nullable

NULL={'type':'null'};MAT=arr(vec(3));MAT.update(minItems=3,maxItems=3)
POSE=obj(rotation=MAT,translation=vec(3),scale={'type':'number','exclusiveMinimum':0})
WORLD=obj(frame_id=STR,kind=enum('shot_world'),parent_frame_id=NULL,pose_parent_from_frame=NULL,
    unit=obj(kind=enum('relative_length'),reference_entity_id=STR,reference_extent=STR,value=NUM),
    axes=obj(x=STR,y=STR,z=STR),origin=STR,raw_reference_identifier=STR)
CAMERA=obj(frame_id=STR,kind=enum('camera'),parent_frame_id=STR,pose_parent_from_frame=POSE,
    intrinsics=MAT,observation_frame_id=INT,quality=STR)
STATE_FRAME=obj(frame_id=STR,kind=enum('entity_state'),parent_frame_id=STR,pose_parent_from_frame=POSE,
    observation_frame_ids=arr(INT),quality=STR)
OBS=obj(frame_id=INT,exist=BOOL,visible=BOOL,box_xyxy=nullable(vec(4)))
STATE=obj(state_id=STR,observation_frame_ids=arr(INT),geometry_frame_id=nullable(STR),
    box=nullable(obj(kind=enum('oriented_box'),center_in_geometry_frame=vec(3),size_xyz=vec(3),symmetry=STR)),
    uncertainty=nullable(obj(kind=enum('heuristic_interval'),center_frame_id=STR,center_halfwidth_xyz=vec(3),
        size_halfwidth_xyz=vec(3),orientation_error_deg=NUM,calibrated_probability=BOOL)),
    evidence=arr(EVIDENCE),basis=STR,reason=STR)
HYP=obj(hypothesis_id=STR,source_frame_id=STR,target_frame_id=STR,transform_target_from_source=POSE,
    uncertainty=obj(rotation_error_deg=NUM,translation_halfwidth_xyz=vec(3),scale_halfwidth=NUM),
    anchor_group_ids=arr(STR),evidence_a=arr(EVIDENCE),evidence_b=arr(EVIDENCE),reason=STR)
BASE=dict(groups=arr(STR),axis=enum('x','y','z'),scope=enum('obb_centers'),continuity_rule=STR,eligible_alignment_hypotheses=arr(STR))
INTERVAL=obj(delta_interval=vec(2),allowed_orders=arr(enum('less','aligned','greater')))
DERIVED=obj(protocol_version=STR,items=arr({'oneOf':[obj(**BASE,status=STR),obj(**BASE,status=STR,source=INTERVAL,targets=arr(INTERVAL))]}),
    summary={'type':'object','additionalProperties':INT},caveat=STR)
SCENE_SCHEMA=obj(schema_version=enum('sparse_scene_graph_v0.3'),
    conventions=obj(handedness=enum('right'),up_axis=enum('Z'),camera_axes=STR,transform_direction=STR,rotation_storage=STR,length_unit=STR),
    frames=arr({'oneOf':[WORLD,CAMERA,STATE_FRAME]}),
    entities=arr(obj(entity_id=STR,local_id=STR,shot_id=STR,name=STR,scope=STR,identity_group_id=STR,observations=arr(OBS),states=arr(STATE))),
    identity_groups=ALIGNMENT_SCHEMA['properties']['groups'],
    constraints=arr(obj(predicate=enum('supported_by'),subject=STR,object=STR,frame_ids=arr(INT),status=STR,source_state_id=STR)),
    cross_shot_alignment=obj(status=enum('provisional','model_supported'),hypotheses=arr(HYP),unresolved_axes=arr(STR),reason=STR),
    derived_relations=DERIVED,notes=arr(STR))

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]/'schemas'
    for name,schema in [('sparse_scene_3d_inference',RAW_SCHEMA),('sparse_scene_3d_alignment',ALIGN_SCHEMA),('sparse_scene_graph',SCENE_SCHEMA)]:
        (root/(name+'.v0.3.schema.json')).write_text(json.dumps(schema,ensure_ascii=False,indent=2)+'\n')
