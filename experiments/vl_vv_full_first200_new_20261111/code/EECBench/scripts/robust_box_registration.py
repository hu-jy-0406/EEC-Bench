"""Global proper-Sim(3) registration of fixed matched OBBs; diagnostic, not scoring.

Each entity contributes its mean squared eight-corner distance. Cuboid corner
labels are resolved over the 24 orientation-preserving cube symmetries. A single
transform applies to every box. Group Huber IRLS limits the influence of a whole
bad entity, without discarding it from the output inventory.
"""
import itertools
import numpy as np
from scipy.spatial.transform import Rotation

SIGNS = np.array(list(itertools.product([-1., 1.], repeat=3)))


def corner_permutations():
    permutations = []
    for axes in itertools.permutations(range(3)):
        for signs in itertools.product([-1, 1], repeat=3):
            rotation = np.eye(3)[:, axes] @ np.diag(signs)
            if np.linalg.det(rotation) < .5:
                continue
            transformed = SIGNS @ rotation.T
            permutations.append([int(np.flatnonzero(np.all(SIGNS == row, axis=1))[0])
                                 for row in transformed])
    return np.array(permutations)


PERMUTATIONS = corner_permutations()


def corners(geometry):
    center = np.asarray(geometry['center_world'], float)
    size = np.asarray(geometry['size_xyz'], float)
    rotation = np.asarray(geometry['R_world_from_object'], float)
    if not np.all(size > 0) or not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-5):
        raise ValueError('Invalid OBB geometry')
    return (SIGNS * size / 2) @ rotation.T + center


def identity():
    return (1., np.eye(3), np.zeros(3))


def transform(points, model):
    scale, rotation, translation = model
    return scale * np.asarray(points) @ rotation.T + translation


def weighted_similarity(x, y, weights=None):
    x, y = np.asarray(x, float), np.asarray(y, float)
    weights = np.ones(len(x)) if weights is None else np.asarray(weights, float)
    if x.shape != y.shape or x.shape[1] != 3 or len(x) < 3:
        raise ValueError('At least three corresponding 3D points required')
    if np.any(weights < 0) or not np.isfinite(x).all() or not np.isfinite(y).all() or weights.sum() <= 0:
        raise ValueError('Invalid fit inputs')
    weights = weights / weights.sum()
    mx, my = weights @ x, weights @ y
    xc, yc = x - mx, y - my
    if np.linalg.svd(xc * np.sqrt(weights[:, None]), compute_uv=False)[1] < 1e-10:
        raise ValueError('Collinear or coincident points')
    u, values, vt = np.linalg.svd((yc * weights[:, None]).T @ xc)
    sign = np.ones(3); sign[-1] = np.linalg.det(u @ vt)
    rotation = u @ np.diag(sign) @ vt
    scale = float(np.dot(values, sign) / np.sum(weights[:, None] * xc**2))
    if scale <= 0:
        raise ValueError('Nonpositive scale')
    return scale, rotation, my - scale * rotation @ mx


def scene_baseline(boxes):
    centers = np.asarray(boxes).mean(axis=1)
    distances = [np.linalg.norm(a-b) for a,b in itertools.combinations(centers, 2)]
    baseline = float(np.median(distances))
    if baseline <= 1e-8:
        raise ValueError('No spatial baseline')
    return baseline


def box_residuals(a, b, model):
    aligned = transform(a, model)
    candidates = b[:, PERMUTATIONS, :]
    squared = ((aligned[:, None] - candidates)**2).sum(axis=-1).mean(axis=-1)
    choices = squared.argmin(axis=1)
    selected = candidates[np.arange(len(a)), choices]
    return np.sqrt(squared[np.arange(len(a)), choices]), selected, choices


def huber(errors, delta):
    if delta is None:
        return .5 * errors**2
    return np.where(errors <= delta, .5 * errors**2, delta * (errors - .5*delta))


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
    s,r,t=model
    return dict(scale=float(s),R_b_from_a=r.tolist(),translation_b=t.tolist(),
                rotation_angle_deg=float(np.linalg.norm(Rotation.from_matrix(r).as_rotvec())*180/np.pi),
                determinant=float(np.linalg.det(r)))


def diagnostics(a,b,model,baseline):
    err,_,_=box_residuals(a,b,model)
    center=np.linalg.norm(transform(a.mean(axis=1),model)-b.mean(axis=1),axis=1)
    return dict(corner_rmse=float(np.sqrt(np.mean(err**2))),corner_median=float(np.median(err)),
                center_rmse=float(np.sqrt(np.mean(center**2))),center_median=float(np.median(center)),
                normalized_corner_rmse=float(np.sqrt(np.mean(err**2))/baseline),
                normalized_corner_median=float(np.median(err)/baseline),
                per_entity_corner_rmse=err.tolist(),per_entity_center_error=center.tolist())
