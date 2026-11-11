"""Fixed-correspondence gravity-preserving similarity with separate center/axis losses.

Experimental numerical alignment, not a consistency verdict. Long axes are
unoriented; scale is positive; no independently adjustable entity transforms.
"""
import numpy as np
from scipy.optimize import minimize


def rz(theta):
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])


def wrap(theta):
    return (np.asarray(theta) + np.pi) % (2*np.pi) - np.pi


def axis_angle(theta):
    return (np.asarray(theta) + np.pi/2) % np.pi - np.pi/2


def baseline(points):
    p = np.asarray(points)
    d = np.linalg.norm(p[:, None] - p[None, :], axis=-1)
    b = float(np.median(d[np.triu_indices(len(p), 1)]))
    if b < 1e-10:
        raise ValueError('No center baseline')
    return b


def long_axis(g):
    r = np.asarray(g['R_world_from_object'], float)
    s = np.asarray(g['size_xyz'], float)
    horizontal = np.flatnonzero(np.abs(r[2]) < 1e-6)
    if len(horizontal) != 2:
        raise ValueError('Requires upright OBBs')
    short, long = horizontal[np.argsort(s[horizontal])]
    return np.arctan2(r[1, long], r[0, long]), float(s[long]/s[short])


def rho(r, delta):
    if delta is None:
        return .5*r*r
    return np.where(r <= delta, .5*r*r, delta*(r-.5*delta))


def transform(p, model):
    s, r, t = model
    return s*np.asarray(p)@r.T+t


def inverse(model):
    s, r, t = model
    return 1/s, r.T, -r.T@t/s


def compose(after, before):
    s, r, t = after
    q, u, v = before
    return s*q, r@u, s*r@v+t


def objective(params, x, y, deltas, axis_weight, delta):
    """Analytic gradient; x/y are isotropically normalized centered point sets."""
    theta, logscale = params[:2]
    s = np.exp(logscale)
    rot = rz(theta)
    p = s*x@rot.T
    e = p+params[2:]-y
    norms = np.linalg.norm(e, axis=1)
    w = np.ones(len(x)) if delta is None else np.minimum(1., delta/np.maximum(norms, 1e-15))
    de = w[:, None]*e/len(x)
    dp = np.column_stack([-p[:, 1], p[:, 0], np.zeros(len(p))])
    center_cost = float(rho(norms, delta).mean())
    angle_cost = float(np.mean(np.sin(theta-deltas)**2)) if len(deltas) else 0.
    grad = np.r_[np.sum(de*dp), np.sum(de*p), de.sum(0)]
    if len(deltas):
        grad[0] += axis_weight*np.mean(np.sin(2*(theta-deltas)))
    return center_cost+axis_weight*angle_cost, grad


def fit(x, y, deltas=(), axis_weight=0., delta=.05, target_baseline=None,
        fixed_yaw=None, fixed_scale=None, starts=12):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if x.shape != y.shape or x.ndim != 2 or x.shape[1] != 3 or len(x) < 2:
        raise ValueError('Need corresponding 3D centers')
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('Nonfinite centers')
    deltas = np.asarray(deltas, float)
    if np.max(np.linalg.norm(x[:,:2]-x[:,:2].mean(0),axis=1))<1e-10 and not len(deltas):
        raise ValueError("Yaw unidentifiable from vertical/coincident centers")
    lx = baseline(x)
    ly = baseline(y) if target_baseline is None else target_baseline
    mx, my = x.mean(0), y.mean(0)
    xx, yy = (x-mx)/lx, (y-my)/ly
    seeds = list(np.linspace(-np.pi, np.pi, starts, endpoint=False))
    cross = np.sum(xx[:, 0]*yy[:, 1]-xx[:, 1]*yy[:, 0])
    dot = np.sum(xx[:, :2]*yy[:, :2])
    seeds.append(float(np.arctan2(cross, dot)))
    if len(deltas):
        axial = float(np.angle(np.mean(np.exp(2j*deltas)))/2)
        seeds += [axial, axial+np.pi]
    if fixed_yaw is not None:
        seeds = [fixed_yaw]
    scale_bounds=(-4., 4.) if fixed_scale is None else (float(np.log(fixed_scale*lx/ly)),)*2
    results = []
    for theta in seeds:
        z = np.r_[theta, 0. if fixed_scale is None else scale_bounds[0], 0., 0., 0.]
        if fixed_yaw is None:
            opt = minimize(objective, z, args=(xx, yy, deltas, axis_weight, delta),
                jac=True, method='L-BFGS-B', bounds=[(None, None), scale_bounds]+[(None, None)]*3,
                options=dict(ftol=1e-14, gtol=1e-9, maxiter=500))
            p = opt.x
        else:
            def fun(q):
                value, grad = objective(np.r_[fixed_yaw, q], xx, yy, deltas, axis_weight, delta)
                return value, grad[1:]
            opt = minimize(fun, z[1:], jac=True, method='L-BFGS-B',
                bounds=[scale_bounds]+[(None, None)]*3,
                options=dict(ftol=1e-14, gtol=1e-9, maxiter=500))
            p = np.r_[fixed_yaw, opt.x]
        cost, gradient = objective(p, xx, yy, deltas, axis_weight, delta)
        s = np.exp(p[1])*ly/lx
        rot = rz(p[0]); trans = my+ly*p[2:]-s*rot@mx
        results.append(dict(model=(s, rot, trans), cost=float(cost), success=bool(opt.success),
            message=str(opt.message), iterations=int(opt.nit), yaw_deg=float(np.degrees(wrap(p[0]))),
            gradient_norm=float(np.linalg.norm(gradient if fixed_yaw is None else gradient[1:])),
            normalized_scale_bound_hit=bool(abs(p[1])>3.999),
            center_cost=float(rho(np.linalg.norm(transform(x,(s,rot,trans))-y,axis=1)/ly,delta).mean()),
            axis_cost=float(np.mean(np.sin(p[0]-deltas)**2)) if len(deltas) else None))
    best=min(results,key=lambda f:f['cost'])
    return dict(**best, starts=[{k:v for k,v in r.items() if k!='model'} for r in results],
                normalization=ly, source_normalization=lx)


def record(model):
    s, r, t = model
    return dict(scale=float(s), rotation=r.tolist(), translation=t.tolist(),
                yaw_deg=float(np.degrees(np.arctan2(r[1,0], r[0,0]))))


def pair_cosines(x, y, model):
    aligned = transform(x, model)
    rows = []
    for i in range(len(x)):
        for j in range(i+1,len(x)):
            a, b = aligned[i]-aligned[j], y[i]-y[j]
            den = np.linalg.norm(a)*np.linalg.norm(b)
            value = None if den<1e-12 else float(np.clip(a@b/den,-1,1))
            rows.append(dict(i=i,j=j,cosine=value))
    return rows
