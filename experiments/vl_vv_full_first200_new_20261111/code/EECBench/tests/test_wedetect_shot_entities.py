"""Behavioral contract checks; no GPU or API required."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location('new_entities', Path(__file__).parents[1] / 'scripts/run_wedetect_shot_entities.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ContractTests(unittest.TestCase):
    def test_floor_coverings_are_candidates_by_default(self):
        # Owner, 2026-11-11: floor coverings are entities again; the exclusion is only for historical reproduction.
        self.assertFalse(m.EXCLUDE_FLOOR_COVERINGS)
        shot = dict(shot_id='s1', frames=[dict(frame_id=0, timestamp_sec=0, sha256='image')])
        labels = ['地毯', '地垫', '桌子']
        payload = m.make_payload(shot, {('s1', 0): dict(image_size=[100, 100], detections=[
            dict(id=i + 1, label=label, box_xyxy=[1, 2, 30, 40], score=.9) for i, label in enumerate(labels)])})
        self.assertEqual([d['name'] for d in payload['frames'][0]['detections']], labels)
        self.assertEqual(payload['candidate_filter']['excluded_detections'], [])
        self.assertEqual(payload['candidate_filter']['policy'], 'none_2026_11_11')

    @mock.patch.object(m, 'EXCLUDE_FLOOR_COVERINGS', True)
    def test_floor_covering_filter_preserves_raw_evidence_and_accounting(self):
        removed = ['地毯', '红地毯', '地垫', '脚垫', '浴垫', '瑜伽垫']
        retained = ['毯子/覆盖层', '软垫', '床垫', '挂毯', '餐具垫', '鼠标垫', '桌子']
        shot = dict(shot_id='s1', frames=[dict(frame_id=0, timestamp_sec=0, sha256='image')])
        ds = [dict(id=i+1, label=label, box_xyxy=[1, 2, 30, 40], score=.9)
              for i,label in enumerate(removed+retained)]
        detections = {('s1',0):dict(image_size=[100,100],detections=ds)}
        before = copy.deepcopy(detections)
        payload = m.make_payload(shot, detections)
        self.assertEqual(detections, before)
        self.assertEqual([d['name'] for d in payload['frames'][0]['detections']],retained)
        excluded = payload['candidate_filter']['excluded_detections']
        self.assertEqual([r['detection'] for r in excluded],ds[:len(removed)])
        self.assertEqual(payload['frames'][0]['detections'][0]['candidate_id'],'f0:d7')
        wire, mapping = m.compact_payload(payload)
        self.assertEqual(wire['labels'],retained)
        self.assertNotIn('candidate_filter',wire)
        raw = dict(entities=[dict(name=label,ids=[i+1]) for i,label in enumerate(retained)],rejected=[])
        decoded = m.decode_response(raw,payload)
        result = m.validate_result(decoded,payload)
        self.assertEqual(len(result['entities']),len(retained))
        self.assertEqual(set(mapping.values()),{f'f0:d{i+1}' for i in range(6,13)})

    @mock.patch.object(m, 'EXCLUDE_FLOOR_COVERINGS', True)
    def test_all_filtered_frame_is_retained_with_empty_candidates(self):
        shot = dict(shot_id='s1',frames=[dict(frame_id=0,timestamp_sec=0,sha256='image')])
        payload = m.make_payload(shot,{('s1',0):dict(image_size=[100,100],detections=[
            dict(id=1,label='地毯',box_xyxy=[1,2,30,40],score=.9)])})
        self.assertEqual(len(payload['frames']),1)
        self.assertEqual(payload['frames'][0]['detections'],[])
        self.assertEqual(len(payload['candidate_filter']['excluded_detections']),1)
        decoded = m.decode_response(dict(entities=[],rejected=[]),payload)
        self.assertEqual(m.validate_result(decoded,payload)['entities'],[])

    def setUp(self):
        self.payload = dict(shot_id='s1', frames=[
            dict(frame_id=i, image_size=[100, 100], detections=[
                dict(candidate_id=f'f{i}:d1', name='person', box_xyxy=[1.25, 2, 20, 40], score=.8)]
                if i in (1, 2, 4) else []) for i in (1, 2, 3, 4)])
        self.result = dict(shot_id='s1', entities=[dict(entity_id='e1', name='person',
            candidate_ids=['f1:d1', 'f2:d1', 'f4:d1'])], rejected_detections=[])

    def test_missing_detection_stays_null_and_existence_unknown(self):
        value = m.validate_result(self.result, self.payload)['entities'][0]
        self.assertEqual(value['exist_frame_ids'], [1, 2, 4])
        self.assertEqual(value['visible_frame_ids'], [1, 2, 4])
        self.assertEqual([r['visible'] for r in value['observations']], [True, True, False, True])
        row = value['observations'][2]
        self.assertIsNone(row['exist'])
        self.assertIsNone(row['box_xyxy'])
        self.assertIsNone(row['box_candidate_id'])
        self.assertEqual(row['candidate_ids'], [])
        self.assertEqual(value['boxes_by_frame'], [
            dict(frame_id=i, box_xyxy=[1.25, 2, 20, 40] if i != 3 else None)
            for i in (1, 2, 3, 4)])
        self.assertNotIn('observations', self.result['entities'][0])

    def test_original_coordinates_and_provenance_preserved(self):
        payload_before = copy.deepcopy(self.payload)
        value = m.validate_result(self.result, self.payload)['entities'][0]
        for row in value['observations']:
            if row['box_candidate_id'] is not None:
                frame = next(f for f in self.payload['frames'] if f['frame_id'] == row['frame_id'])
                source = next(d for d in frame['detections'] if d['candidate_id'] == row['box_candidate_id'])
                self.assertEqual(row['box_xyxy'], source['box_xyxy'])
                self.assertIsNot(row['box_xyxy'], source['box_xyxy'])
                self.assertTrue(row['exist'])
        self.assertEqual(self.payload, payload_before)

    def test_multiple_candidates_select_original_without_union(self):
        self.payload['frames'][0]['detections'].append(
            dict(candidate_id='f1:d2', name='person', box_xyxy=[30, 40, 60, 70], score=.9))
        self.result['entities'][0]['candidate_ids'].append('f1:d2')
        value = m.validate_result(self.result, self.payload)['entities'][0]['observations'][0]
        self.assertEqual(value['box_candidate_id'], 'f1:d2')
        self.assertEqual(value['box_xyxy'], [30, 40, 60, 70])
        self.assertCountEqual(value['candidate_ids'], ['f1:d1', 'f1:d2'])
        # Equal scores choose by candidate ID, not response or detector order.
        self.payload['frames'][0]['detections'][1]['score'] = .8
        self.payload['frames'][0]['detections'].reverse()
        self.result['entities'][0]['candidate_ids'].reverse()
        value = m.validate_result(self.result, self.payload)['entities'][0]['observations'][0]
        self.assertEqual(value['box_candidate_id'], 'f1:d1')
        self.assertEqual(value['box_xyxy'], [1.25, 2, 20, 40])

    def test_model_cannot_supply_frames_boxes_or_visibility(self):
        import jsonschema
        for key, extra in [('observations', [dict(frame_id=3, box_xyxy=[1, 2, 20, 40])]),
                           ('box_xyxy', [1, 2, 20, 40]), ('visible', True), ('exist', True)]:
            value = copy.deepcopy(self.result)
            value['entities'][0][key] = extra
            with self.subTest(key=key), self.assertRaises(jsonschema.ValidationError):
                m.validate_result(value, self.payload)

    def test_invalid_contracts_rejected(self):
        changes = [
            lambda r: r['entities'][0].update(candidate_ids=[]),
            lambda r: r['entities'][0].update(name=' '),
            lambda r: r.update(shot_id='s2'),
            lambda r: r['entities'][0]['candidate_ids'].append('f2:d1'),
            lambda r: r['entities'][0]['candidate_ids'].append('f3:d999'),
            lambda r: r['entities'][0]['candidate_ids'].pop(),
            lambda r: r['entities'].append(copy.deepcopy(r['entities'][0])),
        ]
        for change in changes:
            with self.subTest(change=change):
                value = copy.deepcopy(self.result)
                change(value)
                with self.assertRaises(ValueError):
                    m.validate_result(value, self.payload)

    def test_invalid_detector_coordinates_and_scores_rejected(self):
        for field, value in [('box_xyxy', []), ('box_xyxy', [0, 0, 200, 200]),
                             ('box_xyxy', [0, 0, float('nan'), 20]),
                             ('score', float('nan')), ('score', -1), ('score', True)]:
            payload = copy.deepcopy(self.payload)
            payload['frames'][0]['detections'][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                m.validate_result(self.result, payload)

    def test_rejected_detection_leaves_no_box(self):
        self.result['entities'][0]['candidate_ids'].remove('f2:d1')
        self.result['rejected_detections'].append(dict(candidate_id='f2:d1', reason='False detection'))
        value = m.validate_result(self.result, self.payload)['entities'][0]['observations'][1]
        self.assertIsNone(value['box_xyxy'])
        self.assertIsNone(value['exist'])
        self.assertFalse(value['visible'])

    def test_compact_input_roundtrip_preserves_semantic_fields(self):
        wire, mapping = m.compact_payload(self.payload)
        for frame, packed in zip(self.payload['frames'], wire['frames']):
            self.assertEqual(frame['frame_id'], packed['id'])
            self.assertEqual(frame['image_size'], packed['size'])
            for original, row in zip(frame['detections'], packed['d']):
                self.assertEqual(mapping[row[0]], original['candidate_id'])
                self.assertEqual(wire['labels'][row[1]], original['name'])
                self.assertEqual(row[2:6], original['box_xyxy'])
                self.assertEqual(row[6], original['score'])
        decoded = m.decode_response(dict(entities=[dict(name='person', ids=[1, 2, 3])], rejected=[]), self.payload)
        self.assertEqual(decoded, self.result)
        self.assertEqual(m.validate_result(decoded, self.payload), m.validate_result(self.result, self.payload))

    def test_compact_rejections_expand_and_invalid_accounting_fails(self):
        wire = dict(entities=[dict(name='person', ids=[1])], rejected=[dict(ids=[2, 3], reason='False detections')])
        decoded = m.decode_response(wire, self.payload)
        self.assertEqual([d['candidate_id'] for d in decoded['rejected_detections']], ['f2:d1', 'f4:d1'])
        m.validate_result(decoded, self.payload)
        for ids in ([], [2], [2, 2, 3], [2, 99]):
            bad = copy.deepcopy(wire)
            bad['rejected'][0]['ids'] = ids
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                m.decode_response(bad, self.payload)

    def test_tool_events_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'events.jsonl'
            path.write_text(json.dumps(dict(type='item.started', item=dict(type='command_execution'))) + '\n')
            with self.assertRaises(ValueError):
                m.audit_events(path)

    def test_reviews_use_fresh_single_shot_contexts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'pixel.jpg'
            source.write_bytes(b'fixture-image')
            contexts = []
            args = SimpleNamespace(prepare_only=False, codex_bin='codex',
                                   model='gpt-6-astra', reasoning='medium', timeout=30)
            def fake_cli(command, prompt, cwd, stdout, stderr, timeout):
                contexts.append((command, prompt, cwd, sorted(p.name for p in cwd.iterdir())))
                stderr.write_text('')
                payload = json.loads(prompt.split('<shot>\n')[1].split('\n</shot>')[0])
                response = dict(entities=[], rejected=[])
                Path(command[command.index('--output-last-message') + 1]).write_text(json.dumps(response))
                stdout.write_text(json.dumps(dict(type='turn.completed', usage={})) + '\n')
            with mock.patch.object(m, 'run_process', side_effect=fake_cli):
                for sid in ('private_shot_A', 'private_shot_B'):
                    shot = dict(shot_id=sid, frames=[dict(frame_id=0, path=str(source), sha256=m.sha(source))])
                    payload = dict(shot_id=sid, frames=[dict(frame_id=0, image_size=[1, 1], detections=[])])
                    m.review(shot, payload, args, root / 'shots' / sid)
                args.reuse_reviews = root
                result = m.review(shot, payload, args, root / 'reused')
                self.assertEqual(result['calls'], 0)
                self.assertTrue(result['reused_from'])
                changed = copy.deepcopy(payload)
                changed['frames'][0]['image_size'] = [2, 2]
                with self.assertRaises(ValueError):
                    m.review(shot, changed, args, root / 'mismatched')
            self.assertEqual(len(contexts), 2)
            self.assertNotEqual(contexts[0][2], contexts[1][2])
            for index, (command, prompt, cwd, files) in enumerate(contexts):
                self.assertNotIn(('private_shot_B', 'private_shot_A')[index], prompt)
                self.assertIn('--ephemeral', command)
                self.assertIn('--ignore-user-config', command)
                self.assertNotIn('resume', command)
                self.assertEqual(files, ['image_1.jpg'])

    def test_cli_diagnostic_is_not_a_tool_or_failed_turn(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'events.jsonl'
            diagnostic = dict(type='item.completed', item=dict(type='error', message='Skill descriptions shortened'))
            path.write_text(json.dumps(diagnostic) + '\n' + json.dumps(dict(type='turn.completed', usage={})) + '\n')
            self.assertEqual(m.audit_events(path), [{}])
            path.write_text(json.dumps(diagnostic) + '\n' + json.dumps(dict(type='turn.failed')) + '\n')
            with self.assertRaises(ValueError):
                m.audit_events(path)

    def test_parallel_reviews_overlap_and_preserve_order(self):
        shots = [dict(shot_id=s) for s in ('A', 'B', 'C')]
        barrier = threading.Barrier(2)
        lock = threading.Lock()
        running = 0
        peak = 0
        seen = []
        def fake_review(shot, payload, args, directory):
            nonlocal running, peak
            self.assertEqual(payload, {'shot_id': shot['shot_id']})
            self.assertEqual(directory.name, shot['shot_id'])
            with lock:
                running += 1
                peak = max(peak, running)
                seen.append(shot['shot_id'])
            if shot['shot_id'] in ('A', 'B'):
                barrier.wait(timeout=5)
            with lock:
                running -= 1
            return dict(shot_id=shot['shot_id'], status='success')
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(m, 'review', side_effect=fake_review), mock.patch.object(m, 'make_payload', side_effect=lambda shot, _: dict(shot_id=shot['shot_id'])):
            state = dict(shots=[])
            m.review_shots(shots, {}, SimpleNamespace(shot_workers=2), Path(tmp), state)
        self.assertEqual(peak, 2)
        self.assertCountEqual(seen, ['A', 'B', 'C'])
        self.assertEqual([r['shot_id'] for r in state['shots']], ['A', 'B', 'C'])
        self.assertEqual(state['active_shots'], [])

    def test_failed_review_stops_new_work(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(m, 'review', side_effect=ValueError('bad response')) as review, mock.patch.object(m, 'make_payload', return_value={}):
            state = dict(shots=[])
            with self.assertRaisesRegex(RuntimeError, 'A'):
                m.review_shots([dict(shot_id='A'), dict(shot_id='B')], {}, SimpleNamespace(shot_workers=1), Path(tmp), state)
            self.assertEqual(review.call_count, 1)
            self.assertEqual(state['shots'][0]['status'], 'failed')
            self.assertEqual(state['active_shots'], [])

    def test_empty_detector_output_cannot_spawn_entity(self):
        for frame in self.payload['frames']:
            frame['detections'] = []
        with self.assertRaises(ValueError):
            m.validate_result(self.result, self.payload)
        self.result['entities'] = []
        m.validate_result(self.result, self.payload)


if __name__ == '__main__':
    unittest.main()
