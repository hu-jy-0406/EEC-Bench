#!/usr/bin/env python3
"""Register FPS-selected pairs by sum of 3D distances; CPU only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import numpy as np
from gs_registration_3d import fit_all_pairs, distances, distance_summary, OBJECTIVE

from gs_registration_variants import select_pairs

B = Path(__file__).resolve().parents[1]


def fitting_rows(data, sampling='fps', count=32):
    if sampling == 'all':
        return np.arange(len(data))
    if count < 3:
        raise ValueError('Need at least three fitting pairs')
    available = int((data[:, 13] >= .2).sum())
    if available < 3:
        raise ValueError('Fewer than three valid pairs; cannot register')
    return select_pairs(data, min(count, available), 'fps', .2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--method', choices=['roma', 'sift'], required=True)
    parser.add_argument('--case', type=Path, default=None)
    parser.add_argument('--output', type=Path, default=None)
    parser.add_argument('--sampling', choices=['fps', 'all'], default='fps')
    parser.add_argument('--sample-count', type=int, default=32)
    parser.add_argument('--rotation-model', choices=['gravity_yaw','so3'], default='gravity_yaw')
    args = parser.parse_args()
    case = (args.case or Path(os.environ['CASE_ROOT'])).resolve()
    os.environ['CASE_ROOT'] = str(case)
    # Reuse historical projection functions ONLY to report diagnostics.
    # Legacy fit(), robust weights and consensus scoring are never invoked.
    sys.path.insert(0, str(B/'experiments/study2_full_fresh_20260918'))
    from register import Geometry, summary
    from run_isolated_shot_static_3d import owned_compute_job
    job = owned_compute_job()
    source = case/'registration'/f'{args.method}_geometry'/'correspondences.npz'
    output = args.output or source.with_name('registration.json')
    if output.exists():
        raise FileExistsError('Refuse to overwrite a registration; supply a fresh --output path')
    start = time.time()
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    d = np.load(source)['data']
    if d.ndim != 2 or d.shape[1] != 19 or not np.isfinite(d).all():
        raise ValueError('Malformed selected correspondence table')
    old_path = source.with_name('registration.json')
    old = json.loads(old_path.read_text()) if old_path.exists() else None
    old_fit = old['fits']['all_structures'] if old else None
    selection_start = time.perf_counter()
    selected_rows = fitting_rows(d, args.sampling, args.sample_count)
    selection_seconds = time.perf_counter()-selection_start
    selected = d[selected_rows]
    # Same 25-start policy as validated FPS experiments; independent of old fits.
    optimization_start = time.perf_counter()
    if args.rotation_model == 'so3':
        from gs_registration_so3 import fit_all_pairs as solver, distances as metric
    else:
        solver, metric = fit_all_pairs, distances
    fit = solver(selected[:, 7:10], selected[:, 10:13])
    optimization_seconds = time.perf_counter()-optimization_start
    x = np.array(fit['parameters'])
    values = metric(x, d[:, 7:10], d[:, 10:13])
    assert abs(values[selected_rows].sum()-fit['objective_value']) < 1e-8
    fit['status'] = 'numeric_candidate'
    fit['distance_3d'] = distance_summary(values, d[:, 2])
    fit['distance_3d']['evaluation_role'] = 'full candidate pool diagnostic; not the fitting objective'
    fit['selected_distance_3d'] = distance_summary(values[selected_rows], selected[:, 2])
    # Legacy field names are retained for downstream schema compatibility.
    # FPS draws from both legacy partitions; neither is independent validation.
    geometry = Geometry(d)
    scale, rot, translation = fit['scale'], np.array(fit['rotation']), np.array(fit['translation'])
    residual = np.c_[geometry.project(scale*geometry.Q@rot.T+translation,0)-geometry.uvA,
                     geometry.project((geometry.P-translation)@rot/scale,1)-geometry.uvB]
    err = np.sqrt(np.mean(residual.reshape(-1,2,2)**2,axis=(1,2))*2)
    fit['all_correspondences'] = summary(d, err)
    for key, mask in [('train', d[:, 14] == 0), ('spatial_holdout', d[:, 14] != 0)]:
        fit[key] = summary(d[mask], err[mask])
        fit[key]['evaluation_role'] = 'legacy candidate-pool partition, may overlap fitting rows; NOT an independent holdout'
    result = dict(method=args.method, objective=OBJECTIVE,
                  selection='minimum unweighted sum of Euclidean 3D distances over ALL preselected fitting pairs',
                  fit_population='all saved rows' if args.sampling == 'all' else 'FPS subset of full valid pool, fixed before optimization',
                  sampling=dict(method=args.sampling, requested_count=args.sample_count if args.sampling == 'fps' else None,
                                selected_count=len(selected_rows), candidate_count=len(d), confidence_floor=.2 if args.sampling == 'fps' else None,
                                selected_rows=selected_rows.tolist(), insufficient_count_policy='use all eligible up to requested count; fewer than 3 fails'),
                  selection_seconds=selection_seconds, optimization_seconds=optimization_seconds,
                  independent_holdout=False, fits={'all_structures': fit},
                  transform_model=('positive scale + full proper SO(3) rotation + 3D translation, Shot3 to Shot1' if args.rotation_model=='so3' else 'positive scale + gravity-axis yaw + 3D translation, Shot3 to Shot1'),
                  rotation_model=args.rotation_model,
                  allocation=job, seconds=time.time()-start, source_case=str(case),
                  correspondences_sha256=digest, inference_reuse=bool(old_fit),
                  reuse_scope='historical case registration replay' if old_fit else 'same-run upstream correspondences; no historical registration reused',
                  reprojection_metrics_role='diagnostics only; never used in optimization or candidate selection')
    if old_fit:
        before = np.linalg.norm(old_fit['scale']*d[:,10:13]@np.array(old_fit['rotation']).T+old_fit['translation']-d[:,7:10],axis=1)
        result['previous_registration'] = dict(path=str(old_path), sha256=hashlib.sha256(old_path.read_bytes()).hexdigest(),
                                               distance_3d=distance_summary(before, d[:, 2]),
                                               scale=old_fit['scale'], yaw_deg=old_fit['yaw_deg'], translation=old_fit['translation'])
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
    result['source_hashes'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in [Path(__file__), B/'scripts/gs_registration_3d.py', B/'scripts/gs_registration_so3.py', B/'scripts/gs_registration_variants.py']}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(dict(output=str(output), seconds=result['seconds'], n=len(d), fitted_pairs=len(selected_rows),
                          previous_full_pool_sum=result.get('previous_registration',{}).get('distance_3d',{}).get('sum'),
                          selected_objective_sum=fit['objective_value'], full_pool_sum=float(values.sum()), scale=fit['scale'], yaw=fit['yaw_deg'],
                          solver_success=fit['selected_solver_success']), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
