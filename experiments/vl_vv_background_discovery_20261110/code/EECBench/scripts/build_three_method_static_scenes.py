#!/usr/bin/env python3
"""Build six quality-weighted shot-static estimates from frozen three-method outputs."""
import argparse
from collections import Counter
import hashlib
import itertools
import json
from pathlib import Path
import numpy as np
from sparse_scene_3d import camera_matrix, K, quat_matrix
from run_isolated_shot_static_3d import owned_compute_job

CASE = Path(__file__).resolve().parents[1] / 'experiments/study_inconsistent_3'
LABELS = CASE/'shot_static_3d_isolated_20260914/run01'
BOXER = CASE/'geocalib_boxer_20260913'
DEFAULT_OUT = CASE/'three_method_static_3d_20260914/run01'
METHODS = ('codex', 'boxer_codex_camera', 'boxer_geocalib')
SIGNS = np.array(list(itertools.product((-1., 1.), repeat=3)))


def load(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def corners(box):
    return (SIGNS*np.array(box['size_xyz'])/2) @ np.array(box['R_world_from_object']).T + box['center_world']


def proper_permutations():
    values=[]
    for perm in itertools.permutations(range(3)):
        for signs in itertools.product((-1,1),repeat=3):
            p=np.eye(3)[:,perm] @ np.diag(signs)
            if np.linalg.det(p)>.99: values.append(p)
    return values


PERMUTATIONS=proper_permutations()


def weighted_median(values, weights):
    values=np.asarray(values,float);weights=np.asarray(weights,float)
    if values.ndim==2:
        return np.array([weighted_median(values[:,i],weights) for i in range(values.shape[1])])
    if len(values)==0 or np.any(weights<0) or weights.sum()<=0:
        raise ValueError('Nonempty positive weight mass required')
    order=np.argsort(values,kind='stable');v=values[order];w=weights[order];cum=np.cumsum(w)
    i=int(np.searchsorted(cum,w.sum()/2))
    if i+1<len(v) and abs(cum[i]-w.sum()/2)<1e-12:
        return float((v[i]+v[i+1])/2)
    return float(v[i])


def align_box(box, reference):
    r=np.asarray(box['R_world_from_object']);s=np.asarray(box['size_xyz'])
    rr=np.asarray(reference['R_world_from_object']);ss=np.asarray(reference['size_xyz'])
    options=[]
    for p in PERMUTATIONS:
        rot=r@p;size=np.abs(p).T@s
        loss=np.linalg.norm(rot-rr)**2 + .1*np.linalg.norm(np.log(size/ss))**2
        options.append((loss,rot,size))
    _,rot,size=min(options,key=lambda x:x[0])
    return rot,size


def projection_iou(box, camera, target, image_size):
    if target is None:return 0.
    p=corners(box);r=np.array(camera['R_world_from_camera']);pos=np.array(camera['position_world'])
    cam=(p-pos)@r
    if not np.isfinite(cam).all() or np.any(cam[:,2]<=1e-6):return 0.
    uv=cam@np.array(camera['K']).T;uv=uv[:,:2]/uv[:,2:]
    a=np.r_[uv.min(0),uv.max(0)];b=np.array(target,float);w,h=image_size
    a[[0,2]]=np.clip(a[[0,2]],0,w);a[[1,3]]=np.clip(a[[1,3]],0,h)
    b[[0,2]]=np.clip(b[[0,2]],0,w);b[[1,3]]=np.clip(b[[1,3]],0,h)
    area=lambda v:float(np.prod(np.maximum(0,v[2:]-v[:2])))
    intersection=area(np.r_[np.maximum(a[:2],b[:2]),np.minimum(a[2:],b[2:])])
    union=area(a)+area(b)-intersection
    return intersection/union if union>0 else 0.


def camera_record(fid, intrinsic, rotation, position, image_size):
    rot=np.array(rotation,float);pos=np.array(position,float)
    return dict(frame_id=fid,K=np.asarray(intrinsic).tolist(),R_world_from_camera=rot.tolist(),
                position_world=pos.tolist(),forward_world=rot[:,2].tolist(),up_world=(-rot[:,1]).tolist(),
                image_size=image_size,convention='OpenCV camera: X right, Y down, Z forward')


def frame_inputs(method, sid, source):
    paths=[];frames={};cameras={}
    if method=='codex':
        path=CASE/'sparse_scene_3d_20260913/run01'/('scene_'+sid)/'scene.json';paths.append(path)
        proposal=load(path)['proposal'];index={e['entity_id']:e for e in proposal['entities']}
        for cam in proposal['cameras']:
            r,_=camera_matrix(cam);fid=cam['frame_id']
            cameras[fid]=camera_record(fid,K(cam),r.T,cam['position_world'],[852,480])
            frames[fid]={}
            for entity in source['entities']:
                eid=entity['local_id'];matches=[(i,s) for i,s in enumerate(index[eid]['states']) if fid in s['frame_ids']]
                if len(matches)!=1:raise ValueError('Codex source states must partition frames')
                i,state=matches[0];b=state['bbox3d']
                if b is None:continue
                geometry=dict(center_world=b['center_world'],size_xyz=b['size_xyz'],R_world_from_object=quat_matrix(b['rotation_wxyz']).tolist())
                diagonal=np.linalg.norm(b['size_xyz'])
                relative_error=(np.linalg.norm(b['center_halfwidth_xyz'])+np.linalg.norm(b['size_halfwidth_xyz']))/diagonal
                confidence=1/(1+relative_error+b['orientation_error_deg']/90)
                frames[fid][eid]=dict(geometry=geometry,confidence=confidence,
                    raw_confidence=dict(center_halfwidth_xyz=b['center_halfwidth_xyz'],size_halfwidth_xyz=b['size_halfwidth_xyz'],orientation_error_deg=b['orientation_error_deg']),
                    source_group=f'{sid}/{eid}/state{i}',source_path=str(path),source_state_index=i)
        coordinate=dict(world_frame_id=sid+'/codex_table_local',origin=proposal['reference']['origin_description'],
                        x_axis=proposal['reference']['x_positive_description'],y_axis=proposal['reference']['y_positive_description'],z_axis='up',
                        scale='table long edge approximately 1; not measured metric',shared_state_warning='A state may span several frames; repeated copies are not independent predictions.')
    else:
        variant='codex_camera' if method=='boxer_codex_camera' else 'geocalib'
        for frame in source['frames']:
            fid=frame['frame_id'];path=BOXER/'predictions'/variant/sid/f'frame_{fid:06d}.json';paths.append(path);p=load(path)
            cameras[fid]=camera_record(fid,p['K_original'],p['R_world_from_camera'],p['translation_world_from_camera'],p['image_size'])
            frames[fid]={e['entity_id']:dict(geometry={k:e[k] for k in ('center_world','size_xyz','R_world_from_object')},
                confidence=float(e['model_score']),raw_confidence=dict(model_score=e['model_score']),
                source_group=f'{sid}/{e["entity_id"]}/frame{fid}',source_path=str(path)) for e in p['entities']}
        coordinate=dict(world_frame_id=sid+'/'+variant+'_camera_origin',origin='camera center',z_axis='up',
            scale='monocular model metric prior; not measured',shared_state_warning='Frame-local predictions; nearly identical views remain correlated.')
    return frames,cameras,coordinate,paths


def candidate_rows(entity, frame_predictions, cameras):
    areas=[max(0,o['box_xyxy'][2]-o['box_xyxy'][0])*max(0,o['box_xyxy'][3]-o['box_xyxy'][1]) for o in entity['observations'] if o['visible'] and o['box_xyxy'] is not None]
    maxarea=max(areas,default=1);rows=[]
    for o in entity['observations']:
        fid=o['frame_id'];row=dict(frame_id=fid,visible=o['visible'],box_xyxy=o['box_xyxy'],eligible=False,selected=False,weight=0.)
        pred=frame_predictions[fid].get(entity['local_id'])
        if not o['visible'] or o['box_xyxy'] is None:row['reason']='not_visible'
        elif pred is None:row['reason']='no_geometry'
        else:
            row.update(pred);g=pred['geometry'];r=np.array(g['R_world_from_object']);size=np.array(g['size_xyz']);center=np.array(g['center_world'])
            valid=(np.isfinite(r).all() and np.isfinite(size).all() and np.isfinite(center).all() and np.all(size>0) and np.allclose(r.T@r,np.eye(3),atol=1e-5) and np.linalg.det(r)>.999)
            if not valid:row['reason']='invalid_geometry'
            else:
                iou=projection_iou(g,cameras[fid],o['box_xyxy'],cameras[fid]['image_size'])
                b=o['box_xyxy'];area=max(0,b[2]-b[0])*max(0,b[3]-b[1]);complete=np.sqrt(area/maxarea)
                w,h=cameras[fid]['image_size'];boundary=any([b[0]<=1,b[1]<=1,b[2]>=w-1,b[3]>=h-1])
                q=iou*complete*(.75 if boundary else 1.)*(.5+.5*np.clip(pred['confidence'],0,1))
                row.update(projection_iou=iou,visible_extent_ratio=float(complete),boundary_truncated=boundary,raw_quality=float(q))
                row.update(eligible=iou>0,reason='eligible' if iou>0 else 'no_positive_projection_overlap')
        rows.append(row)
    return rows


def fuse_rows(rows):
    candidates=[r for r in rows if r['eligible']]
    if not candidates:return None,dict(status='unresolved',reason='no supported visible geometry')
    counts=Counter(r['source_group'] for r in candidates)
    # A shared Codex state gets its mean evidence weight, not six independent votes.
    weights=np.array([max(r['raw_quality'],1e-9)/counts[r['source_group']] for r in candidates])
    center=np.array([r['geometry']['center_world'] for r in candidates]);sizes=np.array([r['geometry']['size_xyz'] for r in candidates])
    typical=float(np.median(np.linalg.norm(sizes,axis=1)))
    med=weighted_median(center,weights);mad=weighted_median(np.abs(center-med),weights)
    residual=np.linalg.norm((center-med)/np.maximum(1.4826*mad,.15*typical),axis=1)
    keep=residual<=4.5 if len(candidates)>=3 else np.ones(len(candidates),dtype=bool)
    if not np.any(keep):keep[:]=True
    for i,row in enumerate(candidates):
        row['center_robust_residual']=float(residual[i]);row['selected']=bool(keep[i])
        if not keep[i]:row['reason']='robust_center_outlier'
    used=[r for r in candidates if r['selected']]
    counts=Counter(r['source_group'] for r in used)
    weights=np.array([max(r['raw_quality'],1e-9)/counts[r['source_group']] for r in used]);weights/=weights.sum()
    for row,weight in zip(used,weights):row['weight']=float(weight)
    ref=used[int(np.argmax(weights))]['geometry'];aligned=[align_box(r['geometry'],ref) for r in used]
    rotations=np.array([a[0] for a in aligned]);sizes=np.array([a[1] for a in aligned]);centers=np.array([r['geometry']['center_world'] for r in used])
    center=weighted_median(centers,weights);size=weighted_median(sizes,weights)
    mean=np.einsum('i,ijk->jk',weights,rotations);u,_,vt=np.linalg.svd(mean);d=np.diag([1,1,np.linalg.det(u@vt)]);rotation=u@d@vt
    box=dict(center_world=center.tolist(),size_xyz=size.tolist(),R_world_from_object=rotation.tolist())
    box['corners_world']=corners(box).tolist()
    info=dict(status='fused',selected_frame_ids=[r['frame_id'] for r in used],rejected_frame_ids=[r['frame_id'] for r in rows if not r['selected']],
              distinct_geometry_sources=len(counts),weights=[r['weight'] for r in used],
              center_mad_xyz=weighted_median(np.abs(centers-center),weights).tolist(),size_mad_xyz=weighted_median(np.abs(sizes-size),weights).tolist(),
              orientation_reference_frame_id=used[int(np.argmax(weights))]['frame_id'],
              aggregation='quality-weighted medians; 24 equivalent box parameterizations; SO(3) weighted rotation projection',
              confidence_is_calibrated=False)
    return box,info


def build(method,sid):
    source_path=LABELS/sid/'source_shot.json';review_path=LABELS/sid/'agent_review.json'
    source=load(source_path)['shots'][0];review=load(review_path)['shots'][0]
    assert source['shot_id']==review['shot_id']==sid
    static={e['entity_id'] for e in review['entities'] if e['status']=='static'}
    predictions,cameras,coordinate,paths=frame_inputs(method,sid,source)
    nodes=[];gs_frames=[dict(frame_id=f['frame_id'],entities=[]) for f in source['frames']]
    for entity in source['entities']:
        if entity['entity_id'] not in static:continue
        rows=candidate_rows(entity,predictions,cameras);box,info=fuse_rows(rows)
        fits=[]
        for row,frame in zip(rows,gs_frames):
            assert row['frame_id']==frame['frame_id']
            frame['entities'].append(dict(entity_id=entity['entity_id'],geometry=row.get('geometry'),evidence=row))
            if box and row['visible'] and row['box_xyxy'] is not None:
                fits.append(projection_iou(box,cameras[row['frame_id']],row['box_xyxy'],cameras[row['frame_id']]['image_size']))
        fit=float(np.median(fits)) if fits else 0.
        dispersion=(np.linalg.norm(info.get('center_mad_xyz',[0,0,0]))/np.linalg.norm(box['size_xyz'])) if box else None
        reliability='unresolved' if box is None else ('limited' if fit<.35 or dispersion>.5 else 'supported_estimate')
        nodes.append(dict(entity_id=entity['entity_id'],name=entity['name'],motion_status='static',geometry=box,
                          reliability=reliability,fused_projection_median_iou=fit,center_dispersion_relative=dispersion,aggregation=info,frame_evidence=rows))
    counts=Counter(e['reliability'] for e in nodes)
    graph=dict(schema_version='three_method_static_3d_v0.1',method=method,shot_id=sid,coordinate_system=coordinate,
               cameras=list(cameras.values()),entities=nodes,source_frame_ids=list(cameras),partition='fixed independent single-shot motion labels',
               counts=dict(static_entities=len(nodes),geometry_boxes=sum(e['geometry'] is not None for e in nodes),**dict(counts)),
               median_fused_projection_iou=float(np.median([e['fused_projection_median_iou'] for e in nodes])),
               limitations=['Quality weights are heuristic, not calibrated correctness probabilities.',
                            'Projection overlap uses the 2D input and is not independent 3D accuracy.',
                            'No cross-shot alignment or joint contact/depth optimization.'])
    paths += [source_path,review_path,Path(__file__),Path(__file__).with_name('sparse_scene_3d.py')]
    graph['provenance']=[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths]
    return graph,dict(method=method,shot_id=sid,frames=gs_frames)


def main(out):
    job=owned_compute_job();out.mkdir(parents=True,exist_ok=True);graphs=[]
    for method in METHODS:
        for sid in ('shot1','shot3'):
            graph,frames=build(method,sid);save(out/method/sid/'Gs_global.json',graph);save(out/method/sid/'Gs_frames.json',frames)
            graphs.append(graph);print(method,sid,graph['counts'],flush=True)
    save(out/'summary.json',dict(allocation=job,graphs=[dict(method=g['method'],shot_id=g['shot_id'],counts=g['counts'],median_fused_projection_iou=g['median_fused_projection_iou']) for g in graphs],
        notation='G=Gm+Gs is a fixed node partition, not arithmetic addition; cross-partition relations would need separate treatment.',
        new_model_calls=0,source_mode='reuse frozen three-method geometry; newly quality-weighted fusion',weights='IoU * sqrt(visible-box area / max visible-box area) * boundary factor * (0.5+0.5 native reliability); shared-state duplicate correction; robust center outlier gate'))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=DEFAULT_OUT)
    main(parser.parse_args().out)
