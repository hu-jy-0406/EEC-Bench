#!/usr/bin/env python3
"""Materialize named coordinate frames and OBB states without averaging hypotheses."""
import argparse
import json
from pathlib import Path
import numpy as np
from sparse_scene_3d import camera_matrix,quat_matrix,K


def materialize(root,alignment_root):
    read=lambda p:json.loads(p.read_text())
    run=read(root/'run.json');identity=read(root/'source_snapshot/alignment.json');frames=[];entities=[];constraints=[]
    for side,sid in zip(('a','b'),run['shots']):
        raw=read(root/('scene_'+sid)/'response.json');frozen=read(root/'source_snapshot'/('graph_'+sid+'.json'))
        world=sid+'/world';ref=raw['reference'];groups={eid:g['group_id'] for g in identity['groups'] for eid in g[side+'_ids']}
        frames.append(dict(frame_id=world,kind='shot_world',parent_frame_id=None,pose_parent_from_frame=None,
            unit=dict(kind='relative_length',reference_entity_id=sid+'/'+ref['entity_id'],reference_extent='long_side',value=1),
            axes=dict(x=ref['x_positive_description'],y=ref['y_positive_description'],z='physical_up'),
            origin=ref['origin_description'],raw_reference_identifier=ref['frame_id']))
        for c in raw['cameras']:
            r,t=camera_matrix(c)
            frames.append(dict(frame_id=sid+'/camera/'+str(c['frame_id']),kind='camera',parent_frame_id=world,
                pose_parent_from_frame=dict(rotation=r.T.tolist(),translation=(-r.T@t).tolist(),scale=1),
                intrinsics=K(c).tolist(),observation_frame_id=c['frame_id'],quality='model_estimated'))
        names={e['entity_id']:e for e in frozen['entities']};scopes={e['entity_id']:e['scope'] for e in frozen['entity_scopes']}
        for e in raw['entities']:
            global_id=sid+'/'+e['entity_id'];states=[]
            for i,s in enumerate(e['states']):
                b=s['bbox3d'];fid=global_id+'/state/'+str(i)
                if b:
                    frames.append(dict(frame_id=fid,kind='entity_state',parent_frame_id=world,
                        pose_parent_from_frame=dict(rotation=quat_matrix(b['rotation_wxyz']).tolist(),translation=b['center_world'],scale=1),
                        observation_frame_ids=s['frame_ids'],quality='visual_amodal_hypothesis'))
                states.append(dict(state_id=global_id+'/'+str(i),observation_frame_ids=s['frame_ids'],geometry_frame_id=fid if b else None,
                    box=dict(kind='oriented_box',center_in_geometry_frame=[0,0,0],size_xyz=b['size_xyz'],symmetry=b['symmetry']) if b else None,
                    uncertainty=dict(kind='heuristic_interval',center_frame_id=world,center_halfwidth_xyz=b['center_halfwidth_xyz'],size_halfwidth_xyz=b['size_halfwidth_xyz'],orientation_error_deg=b['orientation_error_deg'],calibrated_probability=False) if b else None,
                    evidence=s['evidence'],basis=s['basis'],reason=s['reason']))
                if s['support_parent_id']:
                    constraints.append(dict(predicate='supported_by',subject=global_id,object=sid+'/'+s['support_parent_id'],
                        frame_ids=s['frame_ids'],status='model_observed_or_inferred',source_state_id=global_id+'/'+str(i)))
            entities.append(dict(entity_id=global_id,local_id=e['entity_id'],shot_id=sid,name=names[e['entity_id']]['name'],
                scope=scopes[e['entity_id']],identity_group_id=groups[e['entity_id']],observations=names[e['entity_id']]['observations'],states=states))
    alignment=read(alignment_root/'alignment.json')
    hypotheses=[dict(hypothesis_id=h['hypothesis_id'],source_frame_id=run['shots'][1]+'/world',target_frame_id=run['shots'][0]+'/world',
        transform_target_from_source=dict(rotation=quat_matrix(h['rotation_wxyz']).tolist(),translation=h['translation_xyz'],scale=h['scale']),
        uncertainty={k:h[k] for k in ('rotation_error_deg','translation_halfwidth_xyz','scale_halfwidth')},
        anchor_group_ids=h['anchor_group_ids'],evidence_a=h['evidence_a'],evidence_b=h['evidence_b'],reason=h['reason']) for h in alignment['hypotheses']]
    result=read(alignment_root/'comparison_tight_bounds.json')
    scene=dict(schema_version='sparse_scene_graph_v0.3',conventions=dict(handedness='right',up_axis='Z',camera_axes='x_right_y_down_z_forward',transform_direction='target_from_source',rotation_storage='matrix_rows',length_unit='reference_long_side'),
        frames=frames,entities=entities,identity_groups=identity['groups'],constraints=constraints,
        cross_shot_alignment=dict(status='provisional' if alignment['unresolved_axes'] else 'model_supported',hypotheses=hypotheses,
            unresolved_axes=alignment['unresolved_axes'],reason=alignment['reason']),
        derived_relations=result,notes=['All boxes are hypotheses, not ground-truth geometry.','Each shot gauge and entity state has a globally unique coordinate-frame ID.','No averaging across alternative alignments.','Presence conflicts from older runs are not re-evaluated here.'])
    validate_frames(scene);return scene


def validate_frames(scene):
    frames={f['frame_id']:f for f in scene['frames']}
    if len(frames)!=len(scene['frames']):raise ValueError('Duplicate coordinate frame ID')
    for fid,f in frames.items():
        ancestors={fid};p=f['parent_frame_id']
        while p is not None:
            if p not in frames or p in ancestors:raise ValueError('Invalid frame parent or cycle')
            ancestors.add(p);p=frames[p]['parent_frame_id']
        pose=f['pose_parent_from_frame']
        if pose:
            r=np.array(pose['rotation'])
            if not (np.allclose(r.T@r,np.eye(3),atol=1e-6) and abs(np.linalg.det(r)-1)<1e-6):raise ValueError('Invalid frame rotation')
            if pose['scale']<=0:raise ValueError('Invalid frame scale')
    for e in scene['entities']:
        for s in e['states']:
            if s['geometry_frame_id'] is not None and s['geometry_frame_id'] not in frames:raise ValueError('Unknown geometry frame')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--alignment',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.write_text(json.dumps(materialize(a.run,a.alignment),ensure_ascii=False,indent=2)+'\n')
