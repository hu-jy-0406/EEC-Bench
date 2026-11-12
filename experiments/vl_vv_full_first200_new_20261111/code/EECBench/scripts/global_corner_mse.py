"""Global gravity-constrained cuboid registration under plain eight-corner MSE.

For fixed identities and the 24 proper corner labellings, eliminate translation
and positive scale analytically. Every per-box correlation is a sinusoid in yaw.
Partition the circle at ALL pairwise sinusoid crossings; inside each interval
the maximizing corner labellings are fixed, so its maximum is analytic as well.
This enumerates the full 1-D yaw domain, subject to documented float precision.
No Huber weights, center-only term, axis term, filtering, or GT anomaly input.
"""
import numpy as np
from robust_box_registration import PERMUTATIONS, transform


def correlation_coefficients(a,b):
    a,b=np.asarray(a,float),np.asarray(b,float)
    if a.shape!=b.shape or a.ndim!=3 or a.shape[1:]!=(8,3) or not len(a):
        raise ValueError('Expected same nonempty N x 8 x 3 arrays')
    if not np.isfinite(a).all() or not np.isfinite(b).all():raise ValueError('Nonfinite corners')
    ma,mb=a.mean((0,1)),b.mean((0,1));x,y=a-ma,b-mb
    A=float(np.sum(x*x));B=float(np.sum(y*y))
    if min(A,B)<=1e-20:raise ValueError('Degenerate scene radius')
    p=y[:,PERMUTATIONS,:]
    coeff=np.stack([(x[:,None,:,0]*p[:,:,:,0]+x[:,None,:,1]*p[:,:,:,1]).sum(-1),
                    (x[:,None,:,0]*p[:,:,:,1]-x[:,None,:,1]*p[:,:,:,0]).sum(-1),
                    (x[:,None,:,2]*p[:,:,:,2]).sum(-1)],axis=-1)
    return coeff,ma,mb,A,B


def correlation_at(coeff,theta):
    theta=np.atleast_1d(theta)
    basis=np.stack([np.cos(theta),np.sin(theta),np.ones_like(theta)],-1)
    vals=np.einsum('npc,kc->knp',coeff,basis)
    return vals.max(-1).sum(-1)


def fit(a,b):
    a,b=np.asarray(a,float),np.asarray(b,float)
    coeff,ma,mb,A,B=correlation_coefficients(a,b)
    # Every crossing, including crossings of inactive candidates: excess work
    # is harmless and avoids an approximate angular grid/globality claim.
    ii,jj=np.triu_indices(len(PERMUTATIONS),1)
    dif=(coeff[:,ii]-coeff[:,jj]).reshape(-1,3)
    radii=np.hypot(dif[:,0],dif[:,1]);valid=radii>1e-14*max(A,B)
    dif,radii=dif[valid],radii[valid]
    ratios=-dif[:,2]/radii;valid=np.abs(ratios)<=1+1e-12
    dif,ratios=dif[valid],np.clip(ratios[valid],-1,1)
    phase=np.arctan2(dif[:,1],dif[:,0]);offset=np.arccos(ratios)
    crossings=np.concatenate([(phase+offset)%(2*np.pi),(phase-offset)%(2*np.pi),[0.,2*np.pi]])
    boundaries=np.unique(crossings)
    left,right=boundaries[:-1],boundaries[1:];mid=(left+right)/2
    basis=np.stack([np.cos(mid),np.sin(mid),np.ones_like(mid)],-1)
    choices=np.einsum('npc,kc->knp',coeff,basis).argmax(-1)
    totals=coeff[np.arange(len(a))[None,:],choices].sum(1)
    theta=np.arctan2(totals[:,1],totals[:,0])%(2*np.pi)
    valid=(theta>=left-1e-13)&(theta<=right+1e-13)
    candidates=np.concatenate([boundaries,theta[valid]])
    values=correlation_at(coeff,candidates);best=int(np.argmax(values));yaw=float(candidates[best]);C=float(values[best])
    if C<=0:raise ValueError('No positive-scale minimizer')
    c,sn=np.cos(yaw),np.sin(yaw);R=np.array([[c,-sn,0],[sn,c,0],[0,0,1.]])
    scale=C/A;t=mb-scale*R@ma
    p=b[:,PERMUTATIONS,:];pred=transform(a,(scale,R,t))
    errors=((pred[:,None]-p)**2).mean((2,3));which=errors.argmin(1)
    per_entity=errors[np.arange(len(a)),which];mse=float(per_entity.mean())
    analytic=(B-C*C/A)/a.size
    if not np.isclose(mse,max(analytic,0),atol=1e-10*B/a.size,rtol=1e-8):raise AssertionError('Analytic/direct MSE mismatch')
    radius2=B/(len(a)*8)
    return dict(scale=float(scale),rotation=R.tolist(),translation=t.tolist(),yaw_deg=float(np.degrees((yaw+np.pi)%(2*np.pi)-np.pi)),
        mse_xyz=mse,mean_squared_corner_distance=3*mse,normalized_mse=mse/radius2,
        normalized_rmse_distance=float(np.sqrt(3*mse/radius2)),target_rms_radius=float(np.sqrt(radius2)),
        source_rms_radius=float(np.sqrt(A/(len(a)*8))),per_entity_mse=per_entity.tolist(),corner_permutation_indices=which.tolist(),
        entity_count=len(a),corner_count=len(a)*8,loss='mean_squared_xyz_error_equal_entity_eight_corners',
        rotation_constraint='hard_gravity_yaw_only',corner_symmetries=24,
        solver='complete_pairwise_sinusoid_crossing_intervals_and_stationary_points',
        intervals=len(mid),candidate_angles=len(candidates),analytic_mse=float(analytic),
        globality='full_yaw_domain_enumerated_for_declared_model_up_to_float64_tolerances')
