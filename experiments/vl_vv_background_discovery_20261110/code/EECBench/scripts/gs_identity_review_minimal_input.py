"""Export the experimentally validated compact identity evidence (no inference).

Full original frames and inventories, original 2D boxes, aligned representative
center/side lengths, initial matching and story remain. Canonical geometry stays
on disk for scoring and validation. The production runner selects this builder
explicitly; the standalone exporter never changes runtime configuration.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

PROFILE = 'aligned_centers_sizes_v1'
PROFILES = ('aligned_centers_sizes_v1', 'aligned_center_trajectories_v1', 'aligned_center_trajectories_min_v1')

def build(canonical, images, profile=PROFILE):
    if profile not in PROFILES:
        raise ValueError('Unknown identity input profile')
    payload = copy.deepcopy(canonical)
    for shot in payload['shots']:
        shot.pop('own_scene_cameras', None)
        source_shot = next(s for s in canonical['shots'] if s['shot_id'] == shot['shot_id'])
        originals = {e['entity_id']: e for e in source_shot['entities']}
        for entity in shot['entities']:
            for key in ('own_scene_geometry', 'frame_evidence',
                        'projected_center_in_other_shot', 'aggregation',
                        'motion_evidence', 'motion_status_role',
                        'motion_classification_protocol'):
                entity.pop(key, None)
            entity['observations'] = [
                {key: row[key] for key in ('frame_id', 'exist', 'visible', 'box_xyxy') if key in row}
                for row in entity['observations']]
            box = entity['aligned_geometry']
            if box is not None:
                entity['aligned_geometry'] = {key: box[key] for key in ('center_world', 'size_xyz')}
            original = originals[entity['entity_id']]
            if profile != 'aligned_centers_sizes_v1':
                entity['aligned_trajectory'] = [dict(
                    frame_id=f['frame_id'], visible=f.get('visible'),
                    aligned_center=None if f.get('aligned_geometry') is None else
                    copy.deepcopy(f['aligned_geometry']['center_world'])) for f in original['frame_evidence']]
            if profile == 'aligned_center_trajectories_v1':
                entity['aggregation'] = {k: copy.deepcopy(original['aggregation'][k]) for k in (
                    'status', 'center_mad_xyz', 'size_mad_xyz', 'selected_frame_ids',
                    'rejected_frame_ids', 'confidence_is_calibrated') if k in original['aggregation']}
    if profile != 'aligned_center_trajectories_v1':
        payload.pop('all_initial_paired_group_diagnostics', None)
    for key in ('frozen_transform', 'diagnostic_attachment'):
        payload.pop(key, None)
    attachments = [copy.deepcopy(row) for row in images if row['shot_id'] != 'aligned_diagnostic']
    # Removing the trailing diagram must not change any original attachment index.
    assert [(r['shot_id'], r['frame_id']) for r in attachments] == [
        (r['shot_id'], r['frame_id']) for r in payload['images']]
    assert payload['initial_matching'] == canonical['initial_matching']
    assert payload['normal_story_prompt'] == canonical['normal_story_prompt']
    for source, target in zip(canonical['shots'], payload['shots']):
        assert [e['entity_id'] for e in source['entities']] == [e['entity_id'] for e in target['entities']]
        for before, after in zip(source['entities'], target['entities']):
            assert before['motion_status'] == after['motion_status']
            assert len(before['observations']) == len(after['observations'])
            for a, b in zip(before['observations'], after['observations']):
                assert a['frame_id'] == b['frame_id'] and a.get('box_xyxy') == b.get('box_xyxy')
    return payload, attachments


def export(case, out, profile=PROFILE):
    case, out = Path(case).resolve(), Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    read = lambda p: json.loads(p.read_text())
    write = lambda name, data: (out / name).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    source = case / 'identity_review_payload.json'
    image_source = case / 'identity_review_images.json'
    original = read(source)
    payload, images = build(original, read(image_source), profile)
    for row in images:
        assert hashlib.sha256(Path(row['path']).read_bytes()).hexdigest() == row['sha256']
    write('input.json', payload)
    write('images.json', images)
    write('manifest.json', dict(profile=profile, source_case=str(case),
          source_hashes={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, image_source)},
          image_count=len(images), entity_count=sum(len(s['entities']) for s in payload['shots']),
          canonical_geometry_unchanged=True, production_default_changed=False,
          caveat='Finite frozen-input validation; not human ground truth or a universal quality guarantee.'))
    return payload, images


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--profile', choices=PROFILES, default=PROFILE)
    args = parser.parse_args()
    payload, images = export(args.case, args.out, args.profile)
    print(json.dumps(dict(profile=args.profile, original_frames=len(images),
                         entities=sum(len(s['entities']) for s in payload['shots'])), ensure_ascii=False))

if __name__ == '__main__':
    main()
