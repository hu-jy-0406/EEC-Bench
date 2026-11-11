"""Experimental sparse/corner/hybrid 3D-distance objectives. Production unchanged."""
import numpy as np
from scipy.optimize import linear_sum_assignment,minimize
from gs_registration_3d import rotation,parameters,objective_and_gradient

def select_pairs(data,count,strategy='fps',min_confidence=.2):
    pool=np.flatnonzero(data[:,13]>=min_confidence)
    if count>len(pool):raise ValueError(f'{len(pool)} pairs meet confidence threshold; need {count}')
    if strategy=='top_confidence':
        return pool[np.lexsort((pool,-data[pool,13]))[:count]]
    if strategy!='fps':raise ValueError(strategy)
    # Joint 6D endpoint coverage. One isotropic spread scale per shot, so an
    # arbitrary shot reconstruction scale cannot dominate coverage selection.
    x=data[pool,7:13].copy()
    for sl in [slice(0,3),slice(3,6)]:
        x[:,sl]-=np.median(x[:,sl],axis=0)
        spread=np.sqrt(np.mean(np.sum(x[:,sl]**2,axis=1)))
        x[:,sl]/=max(float(spread),1e-12)
    chosen=[];minimum=np.full(len(pool),np.inf);index=int(np.argmax(data[pool,13]))
    for _ in range(count):
        chosen.append(index);minimum=np.minimum(minimum,np.sum((x-x[index])**2,axis=1));minimum[chosen]=-1
        index=int(np.argmax(minimum))
    return pool[np.array(chosen)]

def corner_pairs(x,anchor_boxes):
    scale,rot,t=parameters(x);targets=[];sources=[];assignments=[]
    for item in anchor_boxes:
        a=np.asarray(item['target']);b=np.asarray(item['source']);tb=scale*b@rot.T+t
        cost=np.linalg.norm(a[:,None,:]-tb[None,:,:],axis=2)
        ia,ib=linear_sum_assignment(cost)
        targets.append(a[ia]);sources.append(b[ib]);assignments.append(dict(group_id=item['group_id'],target_indices=ia.tolist(),source_indices=ib.tolist(),sum_distance=float(cost[ia,ib].sum())))
    return np.concatenate(targets),np.concatenate(sources),assignments

def hybrid_objective(x,anchor_boxes,key_target,key_source):
    a,b,_=corner_pairs(x,anchor_boxes)
    target=np.concatenate([a,key_target]);source=np.concatenate([b,key_source])
    return objective_and_gradient(x,target,source)

def fit_corners(anchor_boxes,key_target=None,key_source=None,yaw_starts=24):
    key_target=np.empty((0,3)) if key_target is None else np.asarray(key_target,float)
    key_source=np.empty((0,3)) if key_source is None else np.asarray(key_source,float)
    assert key_target.shape==key_source.shape
    for item in anchor_boxes:
        assert np.asarray(item['target']).shape==np.asarray(item['source']).shape==(8,3)
    pc=np.array([np.mean(a['target'],axis=0) for a in anchor_boxes]);qc=np.array([np.mean(a['source'],axis=0) for a in anchor_boxes])
    source_sizes=[np.linalg.norm(np.asarray(a['source'])-np.mean(a['source'],axis=0)) for a in anchor_boxes]
    target_sizes=[np.linalg.norm(np.asarray(a['target'])-np.mean(a['target'],axis=0)) for a in anchor_boxes]
    scale=float(np.clip(np.median(np.array(target_sizes)/np.array(source_sizes)),.1,10))
    attempts=[];solutions=[]
    for i,yaw in enumerate(np.linspace(-np.pi,np.pi,yaw_starts,endpoint=False)):
        x=np.r_[np.log(scale),yaw,np.median(pc-scale*qc@rotation(yaw).T,axis=0)]
        opt=minimize(hybrid_objective,x,args=(anchor_boxes,key_target,key_source),method='L-BFGS-B',jac=True,
                     bounds=[(np.log(.1),np.log(10)),(None,None)]+[(None,None)]*3,
                     options={'ftol':1e-13,'gtol':1e-8,'maxiter':3000,'maxls':60})
        value=hybrid_objective(opt.x,anchor_boxes,key_target,key_source)[0]
        attempts.append(dict(start=i,value=value,success=bool(opt.success),iterations=int(opt.nit),message=str(opt.message)));solutions.append((value,opt.x,i))
    value,x,index=min(solutions,key=lambda v:v[0]);s,r,t=parameters(x);a,b,mapping=corner_pairs(x,anchor_boxes)
    return dict(parameters=x.tolist(),scale=s,rotation=r.tolist(),translation=t.tolist(),yaw_deg=float((np.degrees(x[1])+180)%360-180),objective_value=value,
                objective='sum_corner_euclidean_distances_plus_sum_keypoint_euclidean_distances',
                corner_correspondence='minimum-sum-distance bijection within each frozen anchor, evaluated at each transform',
                corner_pairs=len(a),keypoint_pairs=len(key_target),point_weights='uniform_1',distance_power=1,points_removed=0,
                assignments=mapping,attempts=attempts,selected_start=index,solver_success=attempts[index]['success'],global_optimum_certified=False)
