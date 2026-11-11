"""Gravity-preserving global similarity: R @ [0,0,1] == [0,0,1].

Uses the same fixed-identity OBB corner loss and entity Huber IRLS as the free
rotation pilot. The weighted update restricts R to yaw about Z, leaving one
positive uniform scale and three translations. Both input worlds must be Z-up.
"""
import itertools
import numpy as np
from robust_box_registration import (SIGNS, PERMUTATIONS, corners, identity,
    transform, scene_baseline, box_residuals, huber, diagnostics)
from robust_box_registration import model_record as free_model_record


def weighted_similarity(x, y, weights=None):
    """Exact weighted least squares update under the hard gravity constraint.

    For centered pairs, their XY cross-correlation determines yaw. Scale then
    minimizes all three dimensions together; translation aligns the means.
    """
    x,y=np.asarray(x,float),np.asarray(y,float)
    weights=np.ones(len(x)) if weights is None else np.asarray(weights,float)
    if x.shape!=y.shape or x.ndim!=2 or x.shape[1]!=3 or len(x)<3:
        raise ValueError('At least three corresponding 3D points required')
    if weights.shape!=(len(x),) or not np.isfinite(weights).all() or np.any(weights<0) or weights.sum()<=0:
        raise ValueError('Invalid weights')
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('Nonfinite points')
    weights=weights/weights.sum()
    mx,my=weights@x,weights@y
    xc,yc=x-mx,y-my
    c=float(np.sum(weights*(xc[:,0]*yc[:,0]+xc[:,1]*yc[:,1])))
    q=float(np.sum(weights*(xc[:,0]*yc[:,1]-xc[:,1]*yc[:,0])))
    horizontal_norm=float(np.sqrt(np.sum(weights*np.sum(xc[:,:2]**2,axis=1))*np.sum(weights*np.sum(yc[:,:2]**2,axis=1))))
    if horizontal_norm<1e-12 or np.hypot(c,q)<1e-12*horizontal_norm:
        raise ValueError('Horizontal correspondence cannot determine yaw')
    yaw=np.arctan2(q,c);co,si=np.cos(yaw),np.sin(yaw)
    rotation=np.array([[co,-si,0.],[si,co,0.],[0.,0.,1.]])
    denominator=float(np.sum(weights[:,None]*xc**2))
    numerator=float(np.sum(weights[:,None]*(xc@rotation.T)*yc))
    scale=numerator/denominator
    if scale<=1e-12 or not np.isfinite(scale):
        raise ValueError('No positive-scale interior solution')
    return scale,rotation,my-scale*rotation@mx


def refine(a, b, initial, baseline, delta=.05, max_iterations=160):
    model = initial; history = []
    for iteration in range(max_iterations):
        errors, target, _ = box_residuals(a,b,model)
        normalized = errors / baseline
        cost = float(huber(normalized,delta).mean()); history.append(cost)
        weights = np.ones(len(a)) if delta is None else np.minimum(1.,delta / np.maximum(normalized,1e-12))
        new = weighted_similarity(a.reshape(-1,3),target.reshape(-1,3),np.repeat(weights/8,8))
        new_error,_,_ = box_residuals(a,b,new)
        new_cost=float(huber(new_error/baseline,delta).mean())
        if new_cost > cost + 1e-11:
            raise AssertionError('IRLS objective increased')
        prediction_change = np.max(np.linalg.norm(transform(a,new)-transform(a,model),axis=-1))/baseline
        model = new
        if prediction_change < 1e-9 or abs(cost-new_cost) < 1e-14:
            break
    errors,_,choices=box_residuals(a,b,model)
    normalized=errors/baseline
    return dict(model=model,cost=float(huber(normalized,delta).mean()),iterations=iteration+1,
                converged=iteration+1<max_iterations,objective_history=history,
                weights=np.ones(len(a)) if delta is None else np.minimum(1.,delta/np.maximum(normalized,1e-12)),
                corner_permutations=choices)


def fit_boxes(a,b,delta=.05,baseline=None,starts=8):
    a,b=np.asarray(a,float),np.asarray(b,float)
    if a.shape != b.shape or a.ndim != 3 or a.shape[1:] != (8,3) or len(a)<3:
        raise ValueError('Need at least three matched boxes')
    baseline=scene_baseline(b) if baseline is None else baseline
    ca,cb=a.mean(axis=1),b.mean(axis=1)
    seeds=[identity(),weighted_similarity(ca,cb)]
    # Enumerate minimal center fits only as initializations. Every final objective
    # uses every supplied entity; no anchor eligibility gate or identity changes.
    for indices in itertools.combinations(range(len(a)),3):
        idx=list(indices)
        try:seeds.append(weighted_similarity(ca[idx],cb[idx]))
        except ValueError:continue
    ranked=sorted(seeds,key=lambda m:float(huber(box_residuals(a,b,m)[0]/baseline,delta).mean()))
    results=[refine(a,b,m,baseline,delta) for m in ranked[:starts]]
    best=min(results,key=lambda r:r['cost'])
    best.update(baseline=baseline,initializations_generated=len(seeds),starts_refined=len(results),
                final_costs=[r['cost'] for r in results],
                start_solution_prediction_spread=float(max(np.max(np.linalg.norm(transform(a,r['model'])-transform(a,best['model']),axis=-1)) for r in results)/baseline))
    return best


def model_record(model):
    record=free_model_record(model)
    record.update(rotation_constraint='R_times_up_equals_up',
                  yaw_deg=float(np.degrees(np.arctan2(model[1][1,0],model[1][0,0]))),
                  up_rotation_angle_deg=0.0)
    return record
