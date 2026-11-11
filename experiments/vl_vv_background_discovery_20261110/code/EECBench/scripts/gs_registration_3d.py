"""Fit every selected 3D pair with an unweighted sum of Euclidean distances.

Direction: P (Shot1) ~= s Rz(yaw) Q (Shot3) + t. No trimming, squared
distance objective, confidence/group weights, residual caps, or reprojection
objective. Multiple starts reduce local-minimum sensitivity, not certify a
global optimum. Existing positive-scale bounds [0.1, 10] are preserved.
"""
import numpy as np
from scipy.optimize import minimize

OBJECTIVE = 'sum_all_pair_euclidean_3d_distances_v1'


def rotation(yaw):
    c, s = np.cos(yaw), np.sin(yaw)
    return np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])


def parameters(x):
    return float(np.exp(x[0])), rotation(x[1]), np.asarray(x[2:5])


def distances(x, target, source):
    scale, rot, translation = parameters(x)
    return np.linalg.norm(scale * source @ rot.T + translation - target, axis=1)


def objective_and_gradient(x, target, source):
    scale, rot, translation = parameters(x)
    transformed = scale * source @ rot.T
    residual = transformed + translation - target
    length = np.linalg.norm(residual, axis=1)
    # Zero is a valid subgradient at an exactly zero Euclidean residual.
    # No epsilon is added to the objective, and no nonzero point is omitted.
    unit = np.divide(residual, length[:, None], out=np.zeros_like(residual),
                     where=length[:, None] > 0)
    yaw_derivative = np.column_stack((-transformed[:, 1], transformed[:, 0],
                                      np.zeros(len(source))))
    gradient = np.r_[np.sum(unit * transformed), np.sum(unit * yaw_derivative),
                     unit.sum(axis=0)]
    return float(length.sum()), gradient


def fit_all_pairs(target, source, yaw_starts=24, scale_bounds=(0.1, 10.0),
                  extra_starts=()):
    target, source = np.asarray(target, dtype=float), np.asarray(source, dtype=float)
    if target.shape != source.shape or target.ndim != 2 or target.shape[1] != 3:
        raise ValueError('Expected equally sized N x 3 point arrays')
    if len(target) < 3 or not np.isfinite(target).all() or not np.isfinite(source).all():
        raise ValueError('Need at least three finite pairs; invalid pairs are not silently removed')
    if yaw_starts < 4 or not 0 < scale_bounds[0] < scale_bounds[1]:
        raise ValueError('Invalid solver settings')
    pc, qc = target - target.mean(0), source - source.mean(0)
    denominator = np.sum(qc * qc)
    if denominator <= 1e-20:
        raise ValueError('Source points have no spatial spread; scale/yaw are unidentifiable')
    covariance_cos = np.sum(qc[:, 0] * pc[:, 0] + qc[:, 1] * pc[:, 1])
    covariance_sin = np.sum(qc[:, 0] * pc[:, 1] - qc[:, 1] * pc[:, 0])
    # Least-squares quantities initialize only; every solve/selection uses the
    # exact unsquared distance sum across the complete, unchanged population.
    angles = [float(np.arctan2(covariance_sin, covariance_cos))]
    angles += list(np.linspace(-np.pi, np.pi, yaw_starts, endpoint=False))
    starts = []
    for yaw in angles:
        rot = rotation(yaw)
        scale = float(np.clip(np.sum((qc @ rot.T) * pc) / denominator, *scale_bounds))
        starts.append(np.r_[np.log(scale), yaw, np.median(target-scale*source@rot.T, axis=0)])
    starts += [np.asarray(x, dtype=float) for x in extra_starts]
    bounds = [(np.log(scale_bounds[0]), np.log(scale_bounds[1])), (None, None)] + [(None, None)]*3
    attempts = []
    candidates = []
    for i, initial in enumerate(starts):
        initial = initial.copy(); initial[0] = np.clip(initial[0], *bounds[0])
        before = objective_and_gradient(initial, target, source)[0]
        opt = minimize(objective_and_gradient, initial, args=(target, source), jac=True,
                       method='L-BFGS-B', bounds=bounds,
                       options={'ftol': 1e-13, 'gtol': 1e-8, 'maxiter': 3000, 'maxls': 60})
        after = objective_and_gradient(opt.x, target, source)[0]
        candidates.extend([(before, initial, i, 'initial'), (after, opt.x, i, 'optimized')])
        attempts.append(dict(start=i, initial_sum=before, final_sum=after,
                             success=bool(opt.success), message=str(opt.message),
                             iterations=int(opt.nit), evaluations=int(opt.nfev)))
    value, x, selected, kind = min(candidates, key=lambda c: c[0])
    scale, rot, translation = parameters(x)
    return dict(objective=OBJECTIVE, objective_value=value, parameters=x.tolist(),
                scale=scale, rotation=rot.tolist(), translation=translation.tolist(),
                yaw_deg=float((np.degrees(x[1])+180)%360-180),
                selected_start=selected, selected_candidate=kind,
                selected_solver_success=attempts[selected]['success'],
                fit_rows=len(target), all_selected_pairs_used=True, points_removed=0,
                point_weights='uniform_1', distance_power=1,
                scale_bounds=list(scale_bounds),
                scale_at_bound=bool(np.isclose(scale, scale_bounds[0]) or np.isclose(scale, scale_bounds[1])),
                global_optimum_certified=False, attempts=attempts)


def distance_summary(values, groups):
    def stats(a):
        return dict(n=len(a), sum=float(a.sum()), mean=float(a.mean()),
                    median=float(np.median(a)), p90=float(np.quantile(a, .9)), max=float(a.max()))
    result = stats(values)
    result['by_group'] = {str(int(g)): stats(values[groups == g]) for g in np.unique(groups)}
    result['units'] = 'Shot1 model coordinate units; not calibrated meters'
    return result
