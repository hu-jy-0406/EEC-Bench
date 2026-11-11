import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import register_gs_codex as direct
from review_aligned_entity_identities import registration_quality


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def fixture(root):
    save(root/'narrative.json', dict(facts=[]))
    for sid in ('shot1', 'shot3'):
        image = root/f'{sid}.jpg'
        image.write_bytes(b'original bytes; mocked transport')
        save(root/'selected'/f'{sid}_scene.json', dict(coordinate_system='Z-up', cameras=[], entities=[
            dict(entity_id=sid+'/e1', name='person', motion_status='moving', geometry=None)]))
        save(root/'inputs'/f'{sid}.json', dict(entities=[dict(entity_id='e1', observations=[])],
             frames=[dict(frame_id=0, path=str(image), sha256=direct.sha(image))]))
    # These must never be read, even when they exist beside the direct inputs.
    (root/'matching.json').write_text('INVALID_JSON anchors/prior identities must not be consumed')
    return dict(scale=2., yaw_deg=90., translation=[1., 2., 3.], confidence='low',
                reasoning='Own estimate', limitations='Uncertain geometry')


class DirectRegistrationTests(unittest.TestCase):
    def test_payload_no_prior_matching_and_keeps_motion_and_missing_geometry(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); fixture(root)
            payload, images, hashes = direct.prepare(root)
            self.assertEqual(len(images), 2)
            self.assertEqual([s['shot_id'] for s in payload['shots']], ['shot1', 'shot3'])
            self.assertIsNone(payload['shots'][0]['entities'][0]['geometry'])
            self.assertEqual(payload['shots'][0]['entities'][0]['motion_status'], 'moving')
            self.assertNotIn('matching', payload)
            self.assertNotIn(str(root/'matching.json'), hashes)
            self.assertEqual(len(hashes), 7)

    def test_original_hash_failure_before_call(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); fixture(root)
            (root/'shot1.jpg').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                direct.prepare(root)

    def test_transform_convention_and_no_fictitious_metrics(self):
        response = dict(scale=2., yaw_deg=90., translation=[1., 2., 3.],
                        confidence='low', reasoning='estimate', limitations='uncertain')
        fit = direct.make_fit(response)
        self.assertAlmostEqual(fit['rotation'][0][1], -1.)
        self.assertAlmostEqual(fit['rotation'][1][0], 1.)
        self.assertEqual(fit['parameters'], [math.log(2.), math.pi/2, 1., 2., 3.])
        for name in ('train', 'spatial_holdout', 'objective_value'):
            self.assertNotIn(name, fit)
        quality = registration_quality(dict(method='codex_direct', fits={'all_structures': fit}))
        self.assertEqual(quality['geometric_diagnostics']['status'], 'unavailable')
        self.assertEqual(quality['model_confidence'], 'low')
        response['yaw_deg'] = float('nan')
        with self.assertRaises(ValueError):
            direct.make_fit(response)

    def test_numeric_quality_unchanged(self):
        fit = dict(train={'n':32}, spatial_holdout={'n':12})
        self.assertEqual(registration_quality(dict(method='roma', fits={'all_structures':fit})), fit)

    def test_run_saves_usage_sources_and_refuses_repeat_without_call(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); response = fixture(root)
            def call(stage, prompt, payload, images, schema, args):
                save(args.out/stage/'status.json', dict(status='success', seconds=1.5,
                     usage=[dict(input_tokens=10, output_tokens=2)]))
                return response
            with patch('run_isolated_shot_static_3d.owned_compute_job', return_value='test'), \
                 patch.object(direct.io, 'disabled_skills_config', return_value='disabled'), \
                 patch.object(direct.transport, 'call', side_effect=call) as mocked:
                result = direct.run(root)
                self.assertEqual(mocked.call_count, 1)
                self.assertEqual(result['usage'][0]['input_tokens'], 10)
                self.assertFalse(result['evidence_policy']['anchors_supplied'])
                self.assertTrue((root/'registration/roma_geometry/registration.json').exists())
                self.assertTrue((root/'calls/registration_direct/source_audit.json').exists())
                with self.assertRaises(FileExistsError):
                    direct.run(root)
                self.assertEqual(mocked.call_count, 1)


if __name__ == '__main__':
    unittest.main()
