"""Positive Sim(3), full proper rotation, exact unweighted unsquared distance sum.

No gravity, residual trimming, robust loss, or outcome-based point selection.
Least squares supplies one initializer only; every candidate is ranked by the
same exact Euclidean distance sum. Multi-start is not a global certificate.
"""
import numpy as np
from scipy.optimize import minimize
from scipy.spatial.transform import Rotation
from gs_registration_3d import OBJECTIVE


def skew(v):
    x,y,z=v
    return np.array([[0.,-z,y],[z,0.,-x],[-y,x,0.]])


def parameters(x):
    return float(np.exp(x[0])), Rotation.from_rotvec(x[1:4]).as_matrix(), np.asarray(x[4:7])


def distances(x, target, source):
    s,R,t=parameters(x)
    return np.linalg.norm(s*source@R.T+t-target,axis=1)


def objective_and_gradient(x, target, source):
    s,R,t=parameters(x); transformed=s*source@R.T
    residual=transformed+t-target; length=np.linalg.norm(residual,axis=1)
    unit=np.divide(residual,length[:,None],out=np.zeros_like(residual),where=length[:,None]>0)
    w=np.asarray(x[1:4]); theta=np.linalg.norm(w); W=skew(w)
    if theta<1e-5:
        a=.5-theta**2/24+theta**4/720
        b=1/6-theta**2/120+theta**4/5040
    else:
        a=(1-np.cos(theta))/theta**2; b=(theta-np.sin(theta))/theta**3
    left=np.eye(3)+a*W+b*(W@W)
    grad=np.r_[np.sum(unit*transformed),left.T@np.cross(transformed,unit).sum(0),unit.sum(0)]
    return float(length.sum()),grad


def fit_all_pairs(target, source, scale_bounds=(.1,10.), extra_starts=()):
    p,q=np.asarray(target,float),np.asarray(source,float)
    if p.shape!=q.shape or p.ndim!=2 or p.shape[1]!=3 or len(p)<3:
        raise ValueError('Need equally sized N x 3 arrays with at least 3 pairs')
    if not np.isfinite(p).all() or not np.isfinite(q).all():
        raise ValueError('Nonfinite points; no silent deletion')
    if not 0<scale_bounds[0]<scale_bounds[1]:raise ValueError('Invalid scale bounds')
    pc,qc=p-p.mean(0),q-q.mean(0)
    if min(np.linalg.matrix_rank(pc),np.linalg.matrix_rank(qc))<2:
        raise ValueError('Collinear/coincident points cannot determine full rotation')
    U,_,Vt=np.linalg.svd(qc.T@pc)
    R0=Vt.T@np.diag([1.,1.,np.linalg.det(Vt.T@U.T)])@U.T
    rotations=[R0]+list(Rotation.create_group('O').as_matrix())
    den=np.sum(qc*qc); starts=[]
    for R in rotations:
        s=float(np.clip(np.sum((qc@R.T)*pc)/den,*scale_bounds))
        starts.append(np.r_[np.log(s),Rotation.from_matrix(R).as_rotvec(),np.median(p-s*q@R.T,axis=0)])
    starts += [np.asarray(x,float) for x in extra_starts]
    bounds=[tuple(np.log(scale_bounds))]+[(None,None)]*6
    attempts=[]; candidates=[]
    for i,x in enumerate(starts):
        x=x.copy();x[0]=np.clip(x[0],*bounds[0])
        before=objective_and_gradient(x,p,q)[0]
        opt=minimize(objective_and_gradient,x,args=(p,q),jac=True,method='L-BFGS-B',bounds=bounds,
                     options=dict(ftol=1e-13,gtol=1e-8,maxiter=3000,maxls=60))
        after=objective_and_gradient(opt.x,p,q)[0]
        candidates.extend([(before,x,i,'initial'),(after,opt.x,i,'optimized')])
        attempts.append(dict(start=i,initial_sum=before,final_sum=after,success=bool(opt.success),
                             message=str(opt.message),iterations=int(opt.nit),evaluations=int(opt.nfev)))
    value,x,i,kind=min(candidates,key=lambda row:row[0]);s,R,t=parameters(x)
    return dict(objective=OBJECTIVE,objective_value=value,parameters=x.tolist(),parameterization='log_scale_rotvec_xyz_translation_xyz',
                scale=s,rotation=R.tolist(),translation=t.tolist(),yaw_deg=None,
                rotation_model='so3',rotation_angle_deg=float(np.degrees(Rotation.from_matrix(R).magnitude())),
                selected_start=i,selected_candidate=kind,selected_solver_success=attempts[i]['success'],
                fit_rows=len(p),all_selected_pairs_used=True,points_removed=0,point_weights='uniform_1',distance_power=1,
                scale_bounds=list(scale_bounds),scale_at_bound=bool(np.isclose(s,scale_bounds).any()),
                point_rank_target=int(np.linalg.matrix_rank(pc)),point_rank_source=int(np.linalg.matrix_rank(qc)),
                global_optimum_certified=False,attempts=attempts)
