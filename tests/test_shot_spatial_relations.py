"""Spatial extraction contracts and offline orchestration checks; no API/GPU."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

SCRIPTS = Path(__file__).parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import run_shot_spatial_relations as m


class SpatialTests(unittest.TestCase):
    def setUp(self):
        self.shot = dict(shot_id='s1', frames=[dict(frame_id=i, timestamp_sec=i / 10,
                         sha256='fixture', path='fixture.jpg') for i in (0, 10, 20)])
        self.frozen = dict(shot_id='s1', entities=[dict(entity_id=eid, name=eid,
            observations=[dict(frame_id=i, exist=True, visible=visible,
                box_xyxy=[0, 0, 5, 5] if visible else None) for i, visible in zip((0, 10, 20), flags)])
            for eid, flags in (('e1', (True, True, True)), ('e2', (True, False, True)),
                               ('e3', (False, False, False)))])
        self.payload = m.make_payload(self.shot, self.frozen, {i: dict(image_size=[10, 10]) for i in (0, 10, 20)})
        self.raw = dict(shot_id='s1', pair_reviews=[dict(pair_id='p0001',
            assessment='relations_found', reason='Direct support is observable.')], relations=[
                dict(subject_id='e1', predicate='supported_by', object_id='e2', observations=[
                    dict(frame_id=i, status=s, reason='Pixel evidence or endpoint visibility.')
                    for i, s in ((0, 'present'), (10, 'not_observable'), (20, 'absent'))])])

    def test_coverage_time_and_reference(self):
        self.assertEqual(len(self.payload['pair_candidates']), 1)
        self.assertEqual(len(self.payload['unobservable_pairs']), 2)
        original = copy.deepcopy(self.raw)
        final = m.validate_result(self.raw, self.payload)
        self.assertEqual(self.raw, original)
        self.assertEqual(final['coverage'], dict(total_pairs=3, reviewed_pairs=1,
            pairs_with_relations=1, no_joint_visibility_pairs=2))
        edge = final['relations'][0]
        self.assertEqual(edge['present_frame_ids'], [0])
        self.assertEqual(edge['absent_frame_ids'], [20])
        self.assertEqual(edge['not_observable_frame_ids'], [10])
        self.assertEqual(edge['reference_frame'], 'intrinsic')
        self.raw['relations'][0]['predicate'] = 'in_front_of'
        self.assertEqual(m.validate_result(self.raw, self.payload)['relations'][0]['reference_frame'], 'camera')

    def test_unsupported_and_uncertain_pairs_are_not_negative_edges(self):
        for assessment in ('none_supported', 'insufficient_evidence'):
            self.raw['relations'] = []
            self.raw['pair_reviews'][0]['assessment'] = assessment
            self.assertEqual(m.validate_result(self.raw, self.payload)['relations'], [])

    def test_invalid_contracts(self):
        changes = [
            lambda r: r.update(shot_id='other'),
            lambda r: r['relations'][0].update(subject_id='new'),
            lambda r: r['relations'][0].update(subject_id='e2'),
            lambda r: r['relations'][0].update(object_id='e3'),
            lambda r: r['pair_reviews'].clear(),
            lambda r: r['pair_reviews'].append(copy.deepcopy(r['pair_reviews'][0])),
            lambda r: r['pair_reviews'][0].update(assessment='none_supported'),
            lambda r: r['relations'][0]['observations'].pop(),
            lambda r: r['relations'][0]['observations'][1].update(status='present'),
            lambda r: r['relations'][0]['observations'][0].update(status='not_observable'),
            lambda r: r['relations'][0]['observations'][0].update(status='uncertain'),
            lambda r: r['relations'][0]['observations'][0].update(reason=' '),
            lambda r: r['relations'].append(copy.deepcopy(r['relations'][0])),
        ]
        for change in changes:
            with self.subTest(change=change):
                value = copy.deepcopy(self.raw)
                change(value)
                with self.assertRaises(ValueError):
                    m.validate_result(value, self.payload)

    def test_symmetric_contact_and_overlapping_predicates(self):
        contact = copy.deepcopy(self.raw['relations'][0])
        contact['predicate'] = 'touching'
        self.raw['relations'].append(contact)
        self.assertEqual(len(m.validate_result(self.raw, self.payload)['relations']), 2)
        contact.update(subject_id='e2', object_id='e1')
        with self.assertRaisesRegex(ValueError, 'Symmetric'):
            m.validate_result(self.raw, self.payload)

    def test_inverse_conflict_is_frame_specific(self):
        self.raw['relations'][0]['predicate'] = 'in_front_of'
        reverse = copy.deepcopy(self.raw['relations'][0])
        reverse.update(subject_id='e2', object_id='e1')
        self.raw['relations'].append(reverse)
        with self.assertRaisesRegex(ValueError, 'Opposite'):
            m.validate_result(self.raw, self.payload)
        reverse['observations'][0]['status'] = 'absent'
        reverse['observations'][2]['status'] = 'present'
        self.assertEqual(len(m.validate_result(self.raw, self.payload)['relations']), 2)

    def test_fresh_tool_free_single_shot_invocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / 'source.jpg'
            image.write_bytes(b'fake image for offline command check')
            for frame in self.shot['frames']:
                frame.update(path=str(image), sha256=m.entities.sha(image))
            args = SimpleNamespace(prepare_only=False, codex_bin='codex', model='gpt-6-astra', reasoning='medium', timeout=30)
            calls = []
            def fake(command, prompt, cwd, stdout, stderr, timeout):
                calls.append((command, prompt, str(cwd)))
                self.assertEqual(sorted(p.name for p in cwd.iterdir()), ['image_1.jpg', 'image_2.jpg', 'image_3.jpg'])
                Path(command[command.index('--output-last-message') + 1]).write_text(json.dumps(self.raw))
                stdout.write_text(json.dumps(dict(type='turn.completed', usage=dict(input_tokens=1, output_tokens=1))) + '\n')
                stderr.write_text('')
            with mock.patch.object(m.entities, 'run_process', side_effect=fake), mock.patch.object(m.entities, 'disabled_skills_config', return_value='skills.config=[]'):
                for run in ('first', 'second'):
                    result = m.review((self.shot, self.frozen, self.payload, {}), args, root / run)
                    self.assertEqual(result['calls'], 1)
                    graph = m.entities.read(root / run / 'graph.json')
                    self.assertEqual(graph['entities'], self.frozen['entities'])
            self.assertNotEqual(calls[0][2], calls[1][2])
            for command, prompt, _ in calls:
                self.assertIn('--ephemeral', command)
                self.assertIn('--ignore-user-config', command)
                self.assertNotIn('resume', command)
                self.assertNotIn('candidate_ids', prompt)
                self.assertNotIn('rejected_detections', prompt)

    def test_load_inputs_requires_completed_hash_verified_entities(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            m.entities.dump(source / 'run.json', dict(status='failed', shots=[]))
            with self.assertRaisesRegex(ValueError, 'completed'):
                m.load_inputs(source)
            m.entities.dump(source / 'run.json', dict(status='running', shots=[]))
            with self.assertRaisesRegex(ValueError, 'completed'):
                m.load_inputs(source)
            image = source / 'frame.jpg'
            image.write_bytes(b'fixture')
            shot = dict(shot_id='s1', frames=[dict(frame_id=0, timestamp_sec=0,
                path=str(image), sha256=m.entities.sha(image))])
            m.entities.dump(source / 'manifest.json', dict(shots=[shot]))
            m.entities.dump(source / 'shots/s1/entities.json', {})
            with self.assertRaisesRegex(ValueError, 'Incomplete'):
                m.load_inputs(source, allow_running=True)
            m.entities.dump(source / 'run.json', dict(status='success', shots=[dict(
                shot_id='s1', status='success', output_sha256=m.entities.sha(source / 'shots/s1/entities.json'))]))
            m.entities.dump(source / 'shots/s1/response.json', {})
            m.entities.dump(source / 'shots/s1/input.json', dict(shot_id='s1', frames=[dict(frame_id=0), dict(frame_id=10)]))
            with self.assertRaisesRegex(ValueError, 'frame coverage'):
                m.load_inputs(source)

    def test_failed_call_keeps_known_usage_and_immutable_source_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp) / 'source', Path(tmp) / 'output'
            m.entities.dump(source / 'run.json', dict(status='running', shots=[]))
            args = SimpleNamespace(prepare_only=False, shot_workers=1, model='gpt-6-astra', reasoning='medium')
            def failed_review(item, args, directory):
                directory.mkdir(parents=True)
                m.entities.dump(directory / 'request.json', {})
                events = [dict(type='turn.completed', usage=dict(input_tokens=9, output_tokens=2)),
                          dict(type='turn.failed')]
                (directory / 'events.jsonl').write_text('\n'.join(json.dumps(e) for e in events))
                raise ValueError('injected failure')
            with mock.patch.object(m.entities, 'safe_compute', return_value='owned'), mock.patch.object(
                    m, 'load_inputs', return_value=[(self.shot, self.frozen, self.payload, {})]), mock.patch.object(
                    m, 'review', side_effect=failed_review):
                with self.assertRaisesRegex(RuntimeError, 'Spatial reviews failed'):
                    m.run(source, out, args, allow_running=True)
            state = m.entities.read(out / 'run.json')
            record = state['shots'][0]
            self.assertEqual(record['attempted_calls'], 1)
            self.assertEqual(record['usage'], [dict(input_tokens=9, output_tokens=2)])
            self.assertFalse(record['usage_complete'])
            self.assertIn('audit_error', record)
            m.entities.dump(source / 'run.json', dict(status='success'))
            self.assertEqual(m.entities.sha(out / state['source_run_snapshot']), state['source_run_snapshot_sha256'])

    def test_pipeline_starts_relations_only_after_entity_success(self):
        for fail_entities in (False, True):
            with self.subTest(fail_entities=fail_entities), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                detector = root / 'detector'
                m.entities.dump(detector / 'run.json', {})
                out = root / 'output'
                argv = ['runner', '--manifest', str(root / 'manifest.json'), '--detections', str(detector),
                        '--output', str(out), '--spatial-relations']
                milestones = []
                def entity_stage(shots, detections, args, output, state):
                    if fail_entities:
                        raise RuntimeError('entity failure')
                    milestones.append('entities_complete')
                def relation_stage(source, output, args, allow_running):
                    self.assertEqual(milestones, ['entities_complete'])
                    self.assertTrue(allow_running)
                    self.assertEqual(source, out)
                    return dict(status='success')
                with mock.patch.object(sys, 'argv', argv), mock.patch.object(m.entities, 'load_manifest', return_value=[self.shot]), mock.patch.object(
                        m.entities, 'safe_compute', return_value='owned'), mock.patch.object(m.entities, 'load_detections', return_value={}), mock.patch.object(
                        m.entities, 'review_shots', side_effect=entity_stage), mock.patch.object(m, 'run', side_effect=relation_stage) as stage, mock.patch('builtins.print'):
                    if fail_entities:
                        with self.assertRaisesRegex(RuntimeError, 'entity failure'):
                            m.entities.main()
                        stage.assert_not_called()
                    else:
                        m.entities.main()
                        stage.assert_called_once()


if __name__ == '__main__':
    unittest.main()
