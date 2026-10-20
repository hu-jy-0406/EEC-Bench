"""Construct a scene-attached coordinate frame using ONE source graph only."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np

def frame_from_points(origin,reference,up=(0.,0.,1.)):
    origin,reference,up=map(lambda x:np.asarray(x,float),(origin,reference,up))
    if not all(np.isfinite(x).all() and x.shape==(3,) for x in [origin,reference,up]):raise ValueError('Invalid reference vectors')
    norm=np.linalg.norm(up)
    if norm<1e-9:raise ValueError('Missing up direction')
    z=up/norm;d=reference-origin;d=d-z*np.dot(d,z);length=float(np.linalg.norm(d))
    if length<1e-8:raise ValueError('References have no horizontal separation')
    y=d/length;x=np.cross(y,z);basis=np.column_stack([x,y,z])
    return dict(origin_in_input=origin.tolist(),axes_in_input_columns_xyz=basis.tolist(),unit_length_in_input=length,
                R_scene_from_input=basis.T.tolist(),translation_scene=(-basis.T@origin/length).tolist(),scale_scene_from_input=1/length)

def to_scene(points,frame):
    p=np.asarray(points,float);o=np.asarray(frame['origin_in_input']);basis=np.asarray(frame['axes_in_input_columns_xyz'])
    return (p-o)@basis/frame['unit_length_in_input']

def from_scene(points,frame):
    return np.asarray(points,float)@np.asarray(frame['axes_in_input_columns_xyz']).T*frame['unit_length_in_input']+frame['origin_in_input']

def build(graph,origin_id,direction_id):
    entities={e['entity_id']:e for e in graph['entities']}
    a,b=[entities[k] for k in [origin_id,direction_id]]
    assert graph['coordinate_system']['z_axis']=='up'
    frame=frame_from_points(a['geometry']['center_world'],b['geometry']['center_world'])
    frame.update(shot_id=graph['shot_id'],origin_entity_id=origin_id,direction_entity_id=direction_id,
        origin_name=a['name'],direction_name=b['name'],construction='origin=desk center; Z=up; Y=horizontal desk-to-radiator; X=Y cross Z',
        scale_convention='horizontal desk-to-radiator separation = one scene unit',
        input_graphs_used=1,cross_shot_inputs_used=False,all_box_optimization_used=False)
    boxes=[]
    for e in graph['entities']:
        assert e['geometry'] is not None
        g=e['geometry'];c=to_scene(g['corners_world'],frame);center=to_scene(g['center_world'],frame)
        boxes.append(dict(id=e['entity_id'],name=e['name'],corners=c.tolist(),center=center.tolist(),
            size=(np.asarray(g['size_xyz'])/frame['unit_length_in_input']).tolist(),
            R_scene_from_object=(np.asarray(frame['R_scene_from_input'])@np.asarray(g['R_world_from_object'])).tolist(),
            reference_used_for_frame=e['entity_id'] in [origin_id,direction_id]))
    cams=[]
    for c in graph['cameras']:
        rot=np.asarray(frame['R_scene_from_input'])
        cams.append(dict(frame_id=c['frame_id'],position_scene=to_scene(c['position_world'],frame).tolist(),
                         forward_scene=(rot@c['forward_world']).tolist(),up_scene=(rot@c['up_world']).tolist()))
    return dict(frame=frame,boxes=boxes,cameras=cams)

def main(args):
    graph=json.loads(args.graph.read_text());out=build(graph,args.origin_id,args.direction_id)
    out['provenance']=dict(source=str(args.graph.resolve()),sha256=hashlib.sha256(args.graph.read_bytes()).hexdigest())
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(graph['shot_id'],len(out['boxes']),out['frame']['unit_length_in_input'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--graph',type=Path,required=True);p.add_argument('--origin-id',required=True);p.add_argument('--direction-id',required=True);p.add_argument('--out',type=Path,required=True);main(p.parse_args())
