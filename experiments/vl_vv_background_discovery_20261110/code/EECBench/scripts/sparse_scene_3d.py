"""Sparse cuboid scene contracts and proper-frame geometry; no dense reconstruction."""
import itertools
import math
import numpy as np
from partial_scene_contract import obj,arr,enum,STR,INT,BOOL,BOX,POINT,EVIDENCE,schema_validate,require,check_region

VERSION='sparse_scene_3d_v0.3'
NUM={'type':'number'}
def vec(n):return {'type':'array','items':NUM,'minItems':n,'maxItems':n}
def nullable(s):return {'anyOf':[s,{'type':'null'}]}
CORNERS=['xminus_yminus','xplus_yminus','xplus_yplus','xminus_yplus']
OBB=obj(center_world=vec(3),size_xyz=vec(3),rotation_wxyz=vec(4),center_halfwidth_xyz=vec(3),
    size_halfwidth_xyz=vec(3),orientation_error_deg=NUM,symmetry=enum('none','rotation_about_z','unknown'))
RAW_SCHEMA=obj(shot_id=STR,
    reference=obj(entity_id=STR,frame_id=STR,origin_description=STR,x_positive_description=STR,y_positive_description=STR,
        width_ratio=NUM,width_ratio_halfwidth=NUM,reason=STR,
        corners_by_frame=arr(obj(frame_id=INT,**{k:obj(xy=POINT,observed=BOOL,reason=STR) for k in CORNERS}))),
    cameras=arr(obj(frame_id=INT,fx=NUM,fy=NUM,cx=NUM,cy=NUM,position_world=vec(3),look_at_world=vec(3),up_hint_world=vec(3),reason=STR)),
    entities=arr(obj(entity_id=STR,alignment_role=enum('structural_candidate','movable','unknown'),
        states=arr(obj(frame_ids=arr(INT),bbox3d=nullable(OBB),support_parent_id=nullable(STR),
            basis=enum('visual_amodal_estimate','within_shot_propagation','unresolved'),evidence=arr(EVIDENCE),reason=STR)))))


def unit(v):
    v=np.asarray(v,float);n=np.linalg.norm(v)
    require(np.isfinite(n) and n>1e-9,'Degenerate direction');return v/n


def camera_matrix(c):
    pos=np.array(c['position_world'],float);forward=unit(np.array(c['look_at_world'])-pos)
    right=unit(np.cross(forward,c['up_hint_world']));down=np.cross(forward,right)
    r=np.stack([right,down,forward]);return r,-r@pos


def K(c):return np.array([[c['fx'],0,c['cx']],[0,c['fy'],c['cy']],[0,0,1]],float)


def quat_matrix(q):
    w,x,y,z=unit(q)
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                     [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                     [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])


def reference_corners(width):
    return np.array([[-.5,-width/2,0],[.5,-width/2,0],[.5,width/2,0],[-.5,width/2,0]])


def box_corners(box):
    local=np.array(list(itertools.product((-.5,.5),repeat=3)))*box['size_xyz']
    return local@quat_matrix(box['rotation_wxyz']).T+box['center_world']


def project(points,c,rt=None):
    r,t=camera_matrix(c) if rt is None else rt
    pc=np.asarray(points)@r.T+t;h=pc@K(c).T
    out=np.full((len(pc),2),np.nan);mask=pc[:,2]>1e-8
    out[mask]=h[mask,:2]/h[mask,2,None]
    return out,pc[:,2]


def sim3(points,rotation,translation,scale):
    r=np.asarray(rotation,float)
    require(r.shape==(3,3) and np.allclose(r.T@r,np.eye(3),atol=1e-6) and abs(np.linalg.det(r)-1)<1e-6,'Alignment must be a proper rotation, not reflection')
    require(math.isfinite(scale) and scale>0,'Scale must be positive')
    return scale*np.asarray(points)@r.T+np.asarray(translation)


def coordinate_interval(box,axis):
    a=unit(axis);center=float(a@box['center_world']);rad=float(np.abs(a)@box['center_halfwidth_xyz'])
    return center-rad,center+rad


def relative_order(a,b,axis,epsilon=1e-3):
    aa=coordinate_interval(a,axis);bb=coordinate_interval(b,axis)
    lo,hi=aa[0]-bb[1],aa[1]-bb[0]
    values=[]
    if lo < -epsilon:values.append('less')
    if hi >= -epsilon and lo <= epsilon:values.append('aligned')
    if hi > epsilon:values.append('greater')
    return dict(delta_interval=[lo,hi],allowed_orders=values)


def validate(raw,payload):
    schema_validate(raw,RAW_SCHEMA)
    require(raw['shot_id']==payload['shot_id'],'Wrong 3D shot')
    ids=[e['entity_id'] for e in payload['entities']];nodes={e['entity_id']:e for e in payload['entities']}
    require([e['entity_id'] for e in raw['entities']]==ids,'3D entity coverage/order')
    require(raw['reference']['entity_id'] in ids,'Unknown reference entity')
    require(0<raw['reference']['width_ratio']<=1 and 0<=raw['reference']['width_ratio_halfwidth']<1,'Invalid reference aspect uncertainty')
    frames={f['frame_id']:f for f in payload['frames']};fids=list(frames)
    for key,rows in [('cameras',raw['cameras']),('corners',raw['reference']['corners_by_frame'])]:
        require([r['frame_id'] for r in rows]==fids,'3D '+key+' frame coverage')
    for c in raw['cameras']:
        require(c['fx']>0 and c['fy']>0,'Invalid focal length');camera_matrix(c)
    for row in raw['reference']['corners_by_frame']:
        for k in CORNERS:
            check_region(row[k]['xy'],frames[row['frame_id']],True)
            require(not row[k]['observed'] or row[k]['xy'] is not None,'Observed corner missing pixel')
    for e in raw['entities']:
        covered=[]
        for s in e['states']:
            require(s['frame_ids'] and set(s['frame_ids'])<=set(fids),'Invalid state frames');covered+=s['frame_ids']
            require(s['support_parent_id'] is None or (s['support_parent_id'] in ids and s['support_parent_id']!=e['entity_id']),'Invalid support parent')
            if s['bbox3d'] is not None:
                b=s['bbox3d'];require(np.all(np.array(b['size_xyz'])>0),'Nonpositive extent')
                require(np.all(np.array(b['center_halfwidth_xyz'])>=0) and np.all(np.array(b['size_halfwidth_xyz'])>=0),'Negative uncertainty')
                require(0<=b['orientation_error_deg']<=180,'Invalid angular uncertainty')
                require(abs(np.linalg.norm(b['rotation_wxyz'])-1)<.1,'Nonunit quaternion');quat_matrix(b['rotation_wxyz'])
                require(s['basis']!='unresolved' and s['evidence'],'Box without stated basis/evidence')
            visible={o['frame_id'] for o in nodes[e['entity_id']]['observations'] if o['visible']}
            for ev in s['evidence']:
                require(ev['frame_id'] in visible,'Invisible 3D evidence frame');check_region(ev['region_xyxy'],frames[ev['frame_id']])
        require(sorted(covered)==sorted(fids),'State frames must partition all input frames')
    # Reject nonfinite values even if a permissive JSON parser accepted NaN/Inf.
    def finite(x):
        if isinstance(x,float):require(math.isfinite(x),'Nonfinite 3D parameter')
        elif isinstance(x,dict):
            for v in x.values():finite(v)
        elif isinstance(x,list):
            for v in x:finite(v)
    finite(raw);return raw


def homography(src,dst):
    a=[];b=[]
    for (x,y),(u,v) in zip(src,dst):
        a.extend([[x,y,1,0,0,0,-u*x,-u*y],[0,0,0,x,y,1,-v*x,-v*y]]);b.extend([u,v])
    return np.r_[np.linalg.solve(np.array(a),np.array(b)),1].reshape(3,3)


def camera_from_plane(c,world,pixels):
    h=homography(world[:,:2],pixels);a=np.linalg.solve(K(c),h)
    scale=2/(np.linalg.norm(a[:,0])+np.linalg.norm(a[:,1]))
    if a[2,2]*scale<0:scale=-scale
    r1=a[:,0]*scale;r2=a[:,1]*scale
    raw=np.stack([r1,r2,np.cross(r1,r2)],axis=1);u,_,vt=np.linalg.svd(raw)
    r=u@np.diag([1,1,np.linalg.det(u@vt)])@vt;t=a[:,2]*scale
    return r,t


def envelope_iou(a,b):
    a=np.asarray(a);b=np.asarray(b)
    inter=np.maximum(0,np.minimum(a[2:],b[2:])-np.maximum(a[:2],b[:2])).prod()
    aa=np.maximum(0,a[2:]-a[:2]).prod();bb=np.maximum(0,b[2:]-b[:2]).prod()
    return float(inter/max(aa+bb-inter,1e-9)),float(inter/max(bb,1e-9))


def audit_geometry(raw,payload):
    refs=reference_corners(raw['reference']['width_ratio']);nodes={e['entity_id']:e for e in payload['entities']}
    states={(e['entity_id'],f):s for e in raw['entities'] for s in e['states'] for f in s['frame_ids']}
    cameras=[];boxes=[]
    for c,row in zip(raw['cameras'],raw['reference']['corners_by_frame']):
        fid=c['frame_id'];obs=[k for k in CORNERS if row[k]['observed'] and row[k]['xy'] is not None]
        projected,depth=project(refs,c);reference_row=dict(frame_id=fid,observed_corners=len(obs),
            camera_above_surface=c['position_world'][2]>0,raw_camera=c)
        errors=[float(np.linalg.norm(projected[CORNERS.index(k)]-row[k]['xy'])) for k in obs if depth[CORNERS.index(k)]>0]
        reference_row['raw_corner_rmse_px']=float(np.sqrt(np.mean(np.square(errors)))) if len(errors)==len(obs) and errors else None
        variants=[('raw',None)]
        if len(obs)==4:
            pixels=np.array([row[k]['xy'] for k in CORNERS],float)
            try:
                rt=camera_from_plane(c,refs,pixels);uv,z=project(refs,c,rt)
                reference_row.update(plane_calibrated_R_cw=rt[0].tolist(),plane_calibrated_t_cw=rt[1].tolist(),
                    plane_camera_center=(-rt[0].T@rt[1]).tolist(),plane_corner_rmse_px=float(np.sqrt(np.mean(np.sum((uv-pixels)**2,axis=1)))) if np.all(z>0) else None)
                variants.append(('plane_calibrated',rt))
            except (ValueError,np.linalg.LinAlgError) as exc:reference_row['plane_error']=str(exc)
        cameras.append(reference_row)
        for e in raw['entities']:
            s=states[(e['entity_id'],fid)];b=s['bbox3d'];f=next(o for o in nodes[e['entity_id']]['observations'] if o['frame_id']==fid)
            if b is None or not f['visible'] or f['box_xyxy'] is None:continue
            for variant,rt in variants:
                uv,z=project(box_corners(b),c,rt)
                record=dict(entity_id=e['entity_id'],frame_id=fid,camera_variant=variant,all_corners_in_front=bool(np.all(z>0)))
                if np.all(z>0):
                    env=np.r_[uv.min(axis=0),uv.max(axis=0)];iou,cover=envelope_iou(env,f['box_xyxy'])
                    record.update(projected_envelope=env.tolist(),visible_detection_box=f['box_xyxy'],envelope_iou=iou,visible_box_coverage=cover)
                boxes.append(record)
    summary={}
    for variant in ('raw','plane_calibrated'):
        rows=[r for r in boxes if r['camera_variant']==variant];valid=[r for r in rows if 'envelope_iou' in r]
        summary[variant]=dict(rows=len(rows),in_front=len(valid),median_envelope_iou=float(np.median([r['envelope_iou'] for r in valid])) if valid else None,
            median_visible_box_coverage=float(np.median([r['visible_box_coverage'] for r in valid])) if valid else None)
    return dict(protocol_version=VERSION,cameras=cameras,projected_boxes=boxes,summary=summary,
        limitation='Projection is a consistency diagnostic, not 3D GT. Visible detection boxes are not amodal boxes. Plane calibration depends on model corners, aspect and focal guesses; below-plane cameras invalidate the hypothesis.')


ALIGN_SCHEMA=obj(hypotheses=arr(obj(hypothesis_id=STR,rotation_wxyz=vec(4),translation_xyz=vec(3),scale=NUM,
    rotation_error_deg=NUM,translation_halfwidth_xyz=vec(3),scale_halfwidth=NUM,
    anchor_group_ids=arr(STR),evidence_a=arr(EVIDENCE),evidence_b=arr(EVIDENCE),reason=STR)),
    unresolved_axes=arr(enum('x','y','z')),reason=STR)


def validate_3d_alignment(raw,allowed_groups):
    schema_validate(raw,ALIGN_SCHEMA)
    ids=[]
    for h in raw['hypotheses']:
        ids.append(h['hypothesis_id']);require(h['scale']>0 and 0<=h['scale_halfwidth']<h['scale'],'Invalid Sim3 scale interval')
        require(abs(np.linalg.norm(h['rotation_wxyz'])-1)<.1,'Invalid alignment quaternion')
        r=quat_matrix(h['rotation_wxyz']);require(np.allclose(r@np.array([0,0,1]),[0,0,1],atol=.05),'Aligned up axes disagree')
        require(0<=h['rotation_error_deg']<=180 and np.all(np.array(h['translation_halfwidth_xyz'])>=0),'Invalid alignment uncertainty')
        require(h['anchor_group_ids'] and set(h['anchor_group_ids'])<=set(allowed_groups),'Movable or unknown alignment anchor')
        require(h['evidence_a'] and h['evidence_b'],'Alignment lacks visual evidence')
    require(len(ids)==len(set(ids)),'Duplicate alignment hypothesis')
    return raw


def transformed_relative(a,b,transform,axis):
    r=quat_matrix(transform['rotation_wxyz']);s=transform['scale'];d=np.array(a['center_world'])-b['center_world']
    error=np.array(a['center_halfwidth_xyz'])+b['center_halfwidth_xyz'];ax=unit(axis)
    theta=math.radians(transform['rotation_error_deg']);lower=[];upper=[]
    # For each rotation a linear functional attains its extrema at a box vertex.
    # Swap extrema over vertices and the SO(3) angular ball, then solve the latter
    # analytically. This keeps correlated rotation effects rather than adding a
    # loose radius penalty. Positive scale cannot reverse a sign.
    for signs in itertools.product((-1,1),repeat=3):
        v=r@(d+error*np.array(signs));n=float(np.linalg.norm(v))
        if n<1e-12:lower.append(0.);upper.append(0.);continue
        angle=math.acos(float(np.clip(ax@v/n,-1,1)))
        lower.append(n*math.cos(min(math.pi,angle+theta)))
        upper.append(n*math.cos(max(0.,angle-theta)))
    lo,hi=min(lower),max(upper);sm,sp=s-transform['scale_halfwidth'],s+transform['scale_halfwidth']
    endpoints=[lo*sm,lo*sp,hi*sm,hi*sp];lo,hi=min(endpoints),max(endpoints)
    return dict(delta_interval=[lo,hi],allowed_orders=interval_orders(lo,hi))


def interval_orders(lo,hi,eps=1e-3):
    return (['less'] if lo < -eps else [])+(['aligned'] if hi>=-eps and lo<=eps else [])+(['greater'] if hi>eps else [])


def compare_order_hypotheses(a1,a2,b1,b2,axis,transforms,geometry_qualified=True):
    source=relative_order(a1,a2,axis);targets=[transformed_relative(b1,b2,h,axis) for h in transforms]
    if not transforms:return dict(status='alignment_unresolved',source=source,targets=[])
    sa=set(source['allowed_orders']);opposed=[not(sa&set(t['allowed_orders'])) for t in targets]
    if not geometry_qualified:status='geometry_unverified'
    elif all(opposed):status='conflict'
    elif any(opposed):status='alignment_dependent'
    elif len(sa)==1 and all(set(t['allowed_orders'])==sa for t in targets):status='compatible'
    else:status='position_uncertain'
    return dict(status=status,source=source,targets=targets)
