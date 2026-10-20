"""One shared yaw refinement of frozen, independently constructed scene frames."""
import copy
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SOURCE = BASE.parent / 'study2_scene_frames_20260915'
MATCHING = BASE.parent / 'study_inconsistent_3/gs_consistency_20260914/run02/matching.json'
sys.path.insert(0, str(ROOT / 'EECBench/scripts'))
import robust_box_registration as reg
from run_isolated_shot_static_3d import owned_compute_job


def read(p):
    return json.loads(p.read_text())


def save(p, x):
    p.write_text(json.dumps(x, ensure_ascii=False, indent=2) + '\n')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def wrap_axis(angle):
    """Undirected horizontal axes: opposite directions represent the same line."""
    return (np.asarray(angle) + np.pi / 2) % np.pi - np.pi / 2


def rz(theta):
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.]])


def long_axis(box):
    """Use the longer of the two horizontal OBB edges, never the vertical height.

    Frozen inputs are upright boxes. Reject tilted inputs instead of silently
    substituting a projected diagonal for an actual box edge.
    """
    R = np.asarray(box['R_scene_from_object'])
    sizes = np.asarray(box['size'])
    if R.shape != (3, 3) or sizes.shape != (3,) or np.any(sizes <= 0):
        raise ValueError('invalid box')
    np.testing.assert_allclose(R.T @ R, np.eye(3), atol=1e-8)
    assert np.linalg.det(R) > 0
    horizontal = np.flatnonzero(np.abs(R[2]) < 1e-8)
    if len(horizontal) != 2:
        raise ValueError('requires two horizontal box edges')
    short, long = horizontal[np.argsort(sizes[horizontal])]
    vector = R[:, long]
    return dict(axis_index=int(long), direction=vector.tolist(),
                heading_rad=float(np.arctan2(vector[1], vector[0])),
                horizontal_aspect_ratio=float(sizes[long] / sizes[short]))


def fit(deltas):
    """Exact minimizer of mean sin²(theta - delta), modulo 180 degrees.

    Each eligible matched entity has equal weight. Select the solution nearest
    the existing scene alignment; long edges alone cannot resolve 180 degrees.
    """
    deltas = np.asarray(deltas, dtype=float)
    if deltas.ndim != 1 or len(deltas) == 0 or not np.all(np.isfinite(deltas)):
        raise ValueError('no valid observations')
    resultant = np.mean(np.exp(2j * deltas))
    if abs(resultant) < 1e-10:
        raise ValueError('yaw unidentifiable: axial observations cancel')
    return float(wrap_axis(np.angle(resultant) / 2))


def rotate_record(rec, theta):
    out = copy.deepcopy(rec)
    R = rz(theta)
    for b in out['boxes']:
        for key in ['center', 'corners']:
            b[key] = (np.asarray(b[key]) @ R.T).tolist()
        b['R_scene_from_object'] = (R @ b['R_scene_from_object']).tolist()
    for cam in out['cameras']:
        for key in ['position_scene', 'forward_scene', 'up_scene']:
            cam[key] = (R @ cam[key]).tolist()
    out['alignment_to_shot3_scene'] = dict(scale=1, R=R.tolist(), t=[0, 0, 0],
        yaw_deg=float(np.degrees(theta)), original_frame_metadata_preserved=True)
    return out


def main():
    owned_compute_job()
    records = [read(SOURCE / n) for n in ['shot1_scene.json', 'shot3_scene.json']]
    paths = [SOURCE / n for n in ['shot1_scene.json', 'shot3_scene.json', 'overlay_data.json']]
    paths += [MATCHING] + [Path(r['provenance']['source']) for r in records]
    hashes = {str(p): sha(p) for p in paths}
    for rec in records:
        assert sha(Path(rec['provenance']['source'])) == rec['provenance']['sha256']
    groups = [g for g in read(MATCHING)['groups'] if g['identity'] == 'matched']
    assert all(len(g['a_ids']) == len(g['b_ids']) == 1 for g in groups)
    boxmap = {b['id']: b for r in records for b in r['boxes']}
    rows = []
    # Set geometrical eligibility independently of the observed angular errors.
    threshold = 1.2
    for g in groups:
        a, b = [boxmap[g[k][0]] for k in ['a_ids', 'b_ids']]
        la, lb = long_axis(a), long_axis(b)
        ratio = min(la['horizontal_aspect_ratio'], lb['horizontal_aspect_ratio'])
        delta = float(wrap_axis(lb['heading_rad'] - la['heading_rad']))
        rows.append(dict(group_id=g['group_id'], a_id=a['id'], b_id=b['id'],
            name=a['name'], axes=[la, lb], minimum_aspect_ratio=ratio,
            eligible=ratio >= threshold, required_shared_yaw_deg=float(np.degrees(delta)),
            delta_rad=delta, exclusion_reason=None if ratio >= threshold else
            'horizontal footprint near square in at least one shot'))
    eligible = [r for r in rows if r['eligible']]
    deltas = np.array([r['delta_rad'] for r in eligible])
    theta = fit(deltas)
    R = rz(theta)
    for row in rows:
        row['absolute_angle_before_deg'] = float(abs(np.degrees(wrap_axis(row['delta_rad']))))
        row['absolute_angle_after_deg'] = float(abs(np.degrees(wrap_axis(row['delta_rad'] - theta))))
    refined = rotate_record(records[0], theta)
    save(BASE / 'shot1_aligned_scene.json', refined)
    # The fixed target record is copied so the complete final graph pair is explicit.
    save(BASE / 'shot3_aligned_scene.json', records[1])
    a, b = [np.array([boxmap[g[k][0]]['corners'] for g in groups]) for k in ['a_ids', 'b_ids']]
    ca, cb = [np.array([boxmap[g[k][0]]['center'] for g in groups]) for k in ['a_ids', 'b_ids']]
    metrics = {}
    for label, rotation, angle in [('before', np.eye(3), 0.), ('after', R, theta)]:
        corner = reg.box_residuals(a, b, (1., rotation, np.zeros(3)))[0]
        center = np.linalg.norm(ca @ rotation.T - cb, axis=1)
        for row, cr, ce in zip(rows, corner, center):
            row[f'corner_rmse_{label}'] = float(cr)
            row[f'center_distance_{label}'] = float(ce)
        angle_errors = np.degrees(wrap_axis(deltas - angle))
        metrics[label] = dict(angle_mae_deg=float(np.mean(abs(angle_errors))),
            angle_rmse_deg=float(np.sqrt(np.mean(angle_errors**2))),
            direction_loss=float(np.mean(np.sin(deltas - angle)**2)),
            all_11_corner_rmse=float(np.sqrt(np.mean(corner**2))),
            all_11_center_rmse=float(np.sqrt(np.mean(center**2))),
            excluded_7_corner_rmse=float(np.sqrt(np.mean([r[f'corner_rmse_{label}']**2 for r in rows if not r['eligible']]))))
    loo = []
    for i, row in enumerate(eligible):
        angle = fit(np.delete(deltas, i))
        loo.append(dict(heldout=row['group_id'], yaw_deg=float(np.degrees(angle)),
            heldout_angle_deg=float(abs(np.degrees(wrap_axis(deltas[i] - angle))))))
    sensitivity = []
    for cutoff in [1.1, 1.2, 1.3, 1.5, 2.0]:
        selected = [r for r in rows if r['minimum_aspect_ratio'] >= cutoff]
        sensitivity.append(dict(aspect_threshold=cutoff, groups=[r['group_id'] for r in selected],
            yaw_deg=float(np.degrees(fit([r['delta_rad'] for r in selected])))))
    # Dense independent objective replay checks the analytic global minimum.
    sweep = np.linspace(-np.pi / 2, np.pi / 2, 36001)
    losses = np.mean(np.sin(sweep[:, None] - deltas)**2, axis=1)
    assert metrics['after']['direction_loss'] <= float(losses.min()) + 1e-12
    # Verify ONE proper, gravity-preserving rigid rotation of all boxes and cameras.
    np.testing.assert_allclose(R.T @ R, np.eye(3), atol=1e-12)
    np.testing.assert_allclose(R @ [0, 0, 1], [0, 0, 1], atol=1e-12)
    for old, new in zip(records[0]['boxes'], refined['boxes']):
        np.testing.assert_allclose(np.asarray(new['corners']) @ R, old['corners'], atol=1e-12)
        np.testing.assert_allclose(np.asarray(new['center']) @ R, old['center'], atol=1e-12)
        np.testing.assert_allclose(R.T @ new['R_scene_from_object'], old['R_scene_from_object'], atol=1e-12)
        assert new['size'] == old['size'] and new['id'] == old['id']
    for old, new in zip(records[0]['cameras'], refined['cameras']):
        for key in ['position_scene', 'forward_scene', 'up_scene']:
            np.testing.assert_allclose(R.T @ new[key], old[key], atol=1e-12)
    # Exact composition back into the original input coordinates, for provenance.
    frames = [r['frame'] for r in records]
    A, B = [np.asarray(f['axes_in_input_columns_xyz']) for f in frames]
    scale = frames[1]['unit_length_in_input'] / frames[0]['unit_length_in_input']
    original_R = B @ R @ A.T
    original_t = np.asarray(frames[1]['origin_in_input']) - scale * original_R @ frames[0]['origin_in_input']
    for old, new in zip(records[0]['boxes'], refined['boxes']):
        raw = np.asarray(old['corners']) @ A.T * frames[0]['unit_length_in_input'] + frames[0]['origin_in_input']
        expected = np.asarray(new['corners']) @ B.T * frames[1]['unit_length_in_input'] + frames[1]['origin_in_input']
        np.testing.assert_allclose(scale * raw @ original_R.T + original_t, expected, atol=1e-12)
    overlay = read(SOURCE / 'overlay_data.json')
    after = copy.deepcopy(overlay)
    for box in after['boxes']:
        if box['shot'] == 0:
            for key in ['center', 'corners']:
                box[key] = (np.asarray(box[key]) @ R.T).tolist()
            box['R_scene_from_object'] = (R @ box['R_scene_from_object']).tolist()
    for cam in after['cameras']:
        if cam['shot'] == 0:
            for key in ['position', 'forward']:
                cam[key] = (R @ cam[key]).tolist()
    after['coordinate_frame'] = 'shot3_scene_with_shared_yaw_refined_shot1'
    after['alignment'] = refined['alignment_to_shot3_scene']
    save(BASE / 'overlay_before.json', overlay)
    save(BASE / 'overlay_after.json', after)
    summary = dict(method='independent_scene_frames_then_shared_long_axis_yaw',
        transformation=refined['alignment_to_shot3_scene'],
        objective='mean[1-(u_b dot Rz(theta) u_a)^2] = mean[sin^2(theta-delta)]',
        entity_weights='equal per eligible matched entity', aspect_threshold=threshold,
        matched_pairs=len(rows), eligible_pairs=len(eligible), eligible_groups=[r['group_id'] for r in eligible],
        direction_ambiguity='180 degrees; choose minimizer nearest the existing frame alignment',
        translation_fixed=[0, 0, 0], scale_fixed=1, theta_regularization=False,
        per_entity_rotations=False, metrics=metrics,
        equivalent_input_transform=dict(scale=scale, R=original_R.tolist(), t=original_t.tolist(),
            yaw_deg=float(np.degrees(np.arctan2(original_R[1, 0], original_R[0, 0])))),
        loo=loo, sensitivity=sensitivity,
        reference_radiator_center_after=next(v['center'] for v in refined['boxes'] if v['id']=='shot1/e14'),
        caveat='Improved fitted axis agreement is not an independent consistency score or human ground truth.')
    save(BASE / 'entity_diagnostics.json', rows)
    save(BASE / 'summary.json', summary)
    assert hashes == {str(p): sha(p) for p in paths}
    save(BASE / 'audit.json', dict(status='pass', source_hashes=hashes,
        source_unchanged=True, single_shared_yaw_inverse_replay=True,
        camera_position_and_directions_replayed=True, equivalent_raw_transform_replayed=True,
        fixed_origin_scale_and_gravity=True, analytic_minimum_checked_on_36001_grid=True,
        no_scores_changed=True, no_model_calls=True, no_gpu=True,
        browser_execution_tested=False))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
