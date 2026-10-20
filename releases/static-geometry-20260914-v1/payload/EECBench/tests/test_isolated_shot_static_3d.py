"""Isolation and adjudication contracts; synthetic inputs, no model calls."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_isolated_shot_static_3d as m

FRAMES = [0, 24, 48, 72, 96, 120]
IDENTITY = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]


def shot(sid='shot1'):
    images = [dict(frame_id=i, timestamp_sec=i/24, sha256=str(i), path='/private/'+sid+'/'+str(i)) for i in FRAMES]
    entities = []
    for n in range(2):
        entities.append(dict(entity_id=sid+'/'+str(n), name='object'+str(n), old_verdict='STALE_LABEL',
            observations=[dict(frame_id=i, exist=True, visible=True, box_xyxy=[1, 2, 30, 40], reason='STALE_LABEL') for i in FRAMES],
            states=[dict(frame_id=i, geometry=dict(center_world=[i/24, 0, 0], size_xyz=[4, 2, 1],
                R_world_from_object=IDENTITY, previous_status='STALE_LABEL')) for i in FRAMES]))
    return dict(shot_id=sid, entities=entities, frames=[dict(frame_id=i, image_sha256=str(i), K=IDENTITY, old_review='STALE_LABEL',
        R_world_from_camera=IDENTITY, translation_world_from_camera=[0, 0, 0]) for i in FRAMES],
        calibration=dict(images=images, fixed_camera_consensus=dict(R_world_from_camera=IDENTITY)),
        world_frame_id=sid+'_world', scale='uncalibrated', old_review='STALE_LABEL')


def review(payload):
    return dict(shot_id=payload['shot_id'], camera_assessment='Fixed view evidence', entities=[dict(
        entity_id=e['entity_id'], status='static', visual_evidence='Fixed landmarks',
        image_box_evidence='Occlusion explained', geometry_evidence='Depth jitter',
        reviewed_frame_ids=FRAMES.copy(), observed_frame_ids=FRAMES.copy(),
        motion_intervals=[], uncertainty='Between frames unobserved') for e in payload['entities']])


class IsolatedShotTests(unittest.TestCase):
    def setUp(self):
        self.source = shot()
        self.payload = m.make_payload(self.source)
        self.review = review(self.payload)

    def test_payload_excludes_other_shot_paths_and_old_entity_labels(self):
        whole_source = dict(shots=[self.source, shot('shot3')], old_review='STALE_LABEL')
        payload = m.make_payload(whole_source['shots'][0])
        text = json.dumps(payload)
        for forbidden in ('shot3', '/private/', 'STALE_LABEL', 'old_review', 'old_verdict'):
            self.assertNotIn(forbidden, text)
        self.assertEqual([f['attachment_index'] for f in payload['frames']], list(range(1, 7)))
        self.assertEqual(len(payload['entities'][0]['states']), 6)

    def test_foreign_entity_rejected(self):
        self.source['entities'][0]['entity_id'] = 'shot3/0'
        with self.assertRaises(ValueError):
            m.make_payload(self.source)

    def test_input_requires_six_unique_chronological_images(self):
        for ids in (FRAMES[:-1], [0, 0, 48, 72, 96, 120], list(reversed(FRAMES))):
            bad = copy.deepcopy(self.source)
            bad['calibration']['images'] = [dict(frame_id=i) for i in ids]
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                m.make_payload(bad)

    def test_input_frame_coverage_rejects_foreign_missing_and_duplicate(self):
        for group in ('frames', 'observations', 'states'):
            for mode in ('foreign', 'missing', 'duplicate'):
                bad = copy.deepcopy(self.source)
                rows = bad['frames'] if group == 'frames' else bad['entities'][0][group]
                if mode == 'missing':
                    rows.pop()
                else:
                    rows[-1]['frame_id'] = 999 if mode == 'foreign' else 0
                with self.subTest(group=group, mode=mode), self.assertRaises(ValueError):
                    m.make_payload(bad)

    def test_duplicate_source_entity_rejected(self):
        self.source['entities'][1]['entity_id'] = self.source['entities'][0]['entity_id']
        with self.assertRaises(ValueError):
            m.make_payload(self.source)

    def test_valid_review(self):
        m.validate_review(self.review, self.payload)

    def test_wrong_shot_rejected(self):
        self.review['shot_id'] = 'shot3'
        with self.assertRaises(ValueError):
            m.validate_review(self.review, self.payload)

    def test_missing_duplicate_or_foreign_entity_rejected(self):
        for mode in ('missing', 'duplicate', 'foreign'):
            bad = copy.deepcopy(self.review)
            if mode == 'missing':
                bad['entities'].pop()
            elif mode == 'duplicate':
                bad['entities'][1] = copy.deepcopy(bad['entities'][0])
            else:
                bad['entities'][1]['entity_id'] = 'shot3/1'
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                m.validate_review(bad, self.payload)

    def test_review_requires_all_frames(self):
        self.review['entities'][0]['reviewed_frame_ids'].pop()
        with self.assertRaises(ValueError):
            m.validate_review(self.review, self.payload)

    def test_visible_frames_must_match_observations(self):
        self.payload['entities'][0]['observations'][2]['visible'] = False
        with self.assertRaises(ValueError):
            m.validate_review(self.review, self.payload)
        self.review['entities'][0]['observed_frame_ids'].remove(48)
        m.validate_review(self.review, self.payload)

    def test_static_movement_veto(self):
        self.review['entities'][0]['motion_intervals'] = [[0, 24]]
        with self.assertRaises(ValueError):
            m.validate_review(self.review, self.payload)

    def test_moving_requires_in_range_forward_interval(self):
        self.review['entities'][0]['status'] = 'moving'
        for intervals in ([], [[0, 999]], [[24, 0]], [[24, 24]], [[0, 24, 48]]):
            self.review['entities'][0]['motion_intervals'] = intervals
            with self.subTest(intervals=intervals), self.assertRaises(ValueError):
                m.validate_review(self.review, self.payload)
        self.review['entities'][0]['motion_intervals'] = [[0, 120]]
        m.validate_review(self.review, self.payload)

    def test_blank_evidence_rejected(self):
        for field in ('visual_evidence', 'image_box_evidence', 'geometry_evidence', 'uncertainty'):
            bad = copy.deepcopy(self.review)
            bad['entities'][0][field] = ' '
            with self.subTest(field=field), self.assertRaises(ValueError):
                m.validate_review(bad, self.payload)

    def test_single_shot_fusion_has_one_graph_and_one_box_per_static_entity(self):
        self.review['entities'][1]['status'] = 'unknown'
        graph = m.fusion.build(dict(shots=[self.source]), dict(shots=[self.review]))
        self.assertEqual(len(graph['shots']), 1)
        result = graph['shots'][0]
        self.assertEqual(result['shot_id'], 'shot1')
        self.assertEqual(len(result['entities']), 1)
        self.assertEqual(result['entities'][0]['aggregation']['source_frame_ids'], FRAMES)
        self.assertEqual(result['entities'][0]['geometry']['center_world'], [2.5, 0, 0])
        self.assertEqual(len(result['entities'][0]['geometry']['corners_world']), 8)


if __name__ == '__main__':
    unittest.main()
