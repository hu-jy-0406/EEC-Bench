#!/usr/bin/env python3
"""Independent artifact checks; no imports from the fusion implementation."""
import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
from statistics import median


def read(path):
    return json.loads(path.read_text())


def check(ok, message):
    if not ok:
        raise ValueError(message)


def audit(source_path, output):
    source = read(source_path)
    reviews = read(output / 'agent_review.json')
    graph = read(output / 'static_scene_graph.json')
    source_shots = {s['shot_id']: s for s in source['shots']}
    review_shots = {s['shot_id']: s for s in reviews['shots']}
    final_shots = {s['shot_id']: s for s in graph['shots']}
    check(len(final_shots) == len(graph['shots']), 'duplicate output shot')
    check(len(review_shots) == len(reviews['shots']), 'duplicate review shot')
    check(set(source_shots) == set(review_shots) == set(final_shots), 'shot coverage')
    totals = {'classified_entities': 0, 'static_boxes': 0, 'images_verified': 0}
    counts = {}
    for entry in graph['provenance']:
        check(hashlib.sha256(Path(entry['path']).read_bytes()).hexdigest() == entry['sha256'], 'provenance hash mismatch')
    for sid, src in source_shots.items():
        rev, dst = review_shots[sid], final_shots[sid]
        entities = {e['entity_id']: e for e in src['entities']}
        labels = {e['entity_id']: e for e in rev['entities']}
        boxes = {e['entity_id']: e for e in dst['entities']}
        check(len(labels) == len(rev['entities']), f'{sid}: duplicate review entity')
        check(len(boxes) == len(dst['entities']), f'{sid}: duplicate geometry entity')
        check(set(labels) == set(entities), f'{sid}: classification coverage')
        check(all(e['status'] in ('static', 'moving', 'unknown') for e in labels.values()), 'invalid status')
        static = {eid for eid, e in labels.items() if e['status'] == 'static'}
        check(set(boxes) == static, f'{sid}: static-only membership')
        check(dst['world_frame_id'] == src['world_frame_id'], 'changed coordinate frame')
        fids = [f['frame_id'] for f in src['frames']]
        check(dst['source_frame_ids'] == fids, 'shot frame coverage')
        check(dst.get('coordinate_system'), 'missing coordinate convention')
        check(dst.get('scale'), 'missing scale semantics')
        for f in src['calibration']['images']:
            digest = hashlib.sha256(Path(f['path']).read_bytes()).hexdigest()
            check(digest == f['sha256'], f'changed source image: {sid}/{f["frame_id"]}')
            totals['images_verified'] += 1
        for eid, label in labels.items():
            check(label.get('visual_evidence'), f'{eid}: missing visual evidence')
            check(set(label['observed_frame_ids']) <= set(fids), f'{eid}: unknown evidence frame')
        for eid, obj in boxes.items():
            check(obj['status'] == 'static' and 'states' not in obj, f'{eid}: not one static geometry')
            check(not labels[eid]['motion_intervals'], f'{eid}: static despite observed movement')
            b, agg = obj['geometry'], obj['aggregation']
            center, size, rot, corners = (b[k] for k in ('center_world', 'size_xyz', 'R_world_from_object', 'corners_world'))
            check(len(center) == len(size) == len(rot) == 3 and all(len(r) == 3 for r in rot), f'{eid}: dimensions')
            check(len(corners) == 8 and all(len(p) == 3 for p in corners), f'{eid}: corners')
            numbers = center + size + list(itertools.chain.from_iterable(rot + corners))
            check(all(math.isfinite(v) for v in numbers) and min(size) > 0, f'{eid}: invalid values')
            for i in range(3):
                for j in range(3):
                    check(abs(sum(rot[k][i] * rot[k][j] for k in range(3)) - (i == j)) < 1e-5, f'{eid}: nonorthogonal rotation')
            det = sum(rot[0][i] * (rot[1][(i+1)%3] * rot[2][(i+2)%3] - rot[1][(i+2)%3] * rot[2][(i+1)%3]) for i in range(3))
            check(abs(det - 1) < 1e-5, f'{eid}: improper rotation')
            expected = [[center[i] + sum(rot[i][j] * signs[j] * size[j] / 2 for j in range(3)) for i in range(3)] for signs in itertools.product((-1, 1), repeat=3)]
            remaining = list(corners)
            for p in expected:
                distances = [sum((p[i]-q[i])**2 for i in range(3)) for q in remaining]
                k = min(range(len(distances)), key=distances.__getitem__)
                check(distances[k] < 1e-8, f'{eid}: inconsistent corners')
                remaining.pop(k)
            states = {s['frame_id']: s['geometry'] for s in entities[eid]['states'] if s['geometry'] is not None}
            used = agg['source_frame_ids']
            check(len(used) == len(set(used)) == agg['source_count'] and len(used) >= 2, f'{eid}: not multi-frame fusion')
            check(set(used) == set(states), f'{eid}: all-visible-frame fusion source mismatch')
            center_median = [median(states[f]['center_world'][i] for f in used) for i in range(3)]
            check(max(abs(center[i]-center_median[i]) for i in range(3)) < 1e-6, f'{eid}: center median replay')
            canonical_sizes = [[max(g['size_xyz'][:2]), min(g['size_xyz'][:2]), g['size_xyz'][2]] for g in states.values()]
            size_median = [median(v[i] for v in canonical_sizes) for i in range(3)]
            check(max(abs(size[i]-size_median[i]) for i in range(3)) < 1e-6, f'{eid}: size median replay')
            check('center_mad_xyz' in agg and 'size_mad_xyz' in agg and 'yaw_deviation_deg' in agg, 'missing dispersion')
        counts[sid] = {status: sum(e['status'] == status for e in labels.values()) for status in ('static', 'moving', 'unknown')}
        totals['classified_entities'] += len(labels)
        totals['static_boxes'] += len(boxes)
    return {'status': 'pass', 'source_sha256': hashlib.sha256(source_path.read_bytes()).hexdigest(), 'counts': counts, **totals,
            'checks': ['all input entities classified exactly once', 'exact static-only membership', 'one graph per shot and one box per static entity', 'all provenance and source image hashes', 'shot-local coordinate frame preserved', 'finite positive sizes and proper rotation', 'eight corners independently recomputed', 'all-visible multi-frame sources and median center/size replay', 'visual evidence and geometry dispersion recorded'],
            'limits': 'Structural and numerical validation; not independent motion-label accuracy or 3D ground truth.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = audit(args.source, args.output)
    (args.output / 'independent_audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))
