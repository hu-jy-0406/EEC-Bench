"""Batch controller evaluator-chain selection; no Slurm, GPU or API calls."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'run_batch', ROOT / 'experiments/vl_vv_multimodel_first200_20260926/run_batch.py')
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)


def finished(root, protocol):
    (root / 'episode_scoring').mkdir(parents=True)
    (root / 'run.json').write_text(json.dumps({'status': 'success'}))
    (root / 'episode_scoring/result.json').write_text(json.dumps({'status': 'success', 'protocol': protocol}))
    return {'output_dir': str(root)}


class BatchProtocolSelection(unittest.TestCase):
    def test_legacy_directory_resumes_as_v1_and_refuses_v2(self):
        legacy = {'cohort_protocol': 'vl_vv_first200_multimodel_v1', 'tasks': {}}
        self.assertEqual(batch.resolve_discovery_protocol(legacy, None), 'v1')
        self.assertEqual(batch.resolve_discovery_protocol(legacy, 'v1'), 'v1')
        with self.assertRaisesRegex(ValueError, 'fresh --exp-dir'):
            batch.resolve_discovery_protocol(legacy, 'v2')

    def test_recorded_v2_directory_keeps_v2(self):
        recorded = {'discovery_protocol': 'v2'}
        self.assertEqual(batch.resolve_discovery_protocol(recorded, None), 'v2')
        with self.assertRaisesRegex(ValueError, 'fresh --exp-dir'):
            batch.resolve_discovery_protocol(recorded, 'v1')

    def test_new_directory_requires_an_explicit_choice(self):
        with self.assertRaisesRegex(ValueError, 'Choose --discovery-protocol'):
            batch.resolve_discovery_protocol(None, None)
        self.assertEqual(batch.resolve_discovery_protocol(None, 'v2'), 'v2')

    def test_success_check_accepts_only_the_chain_scoring_protocol(self):
        with tempfile.TemporaryDirectory() as temporary:
            v1_row = finished(Path(temporary) / 'old', 'vl_vv_episode_scoring_v2')
            v2_row = finished(Path(temporary) / 'new', 'vl_vv_episode_scoring_v3')
            self.assertTrue(batch.valid_success(v1_row))
            self.assertFalse(batch.valid_success(v2_row))
            self.assertTrue(batch.valid_success(v2_row, batch.SCORING_PROTOCOLS['v2']))
            self.assertFalse(batch.valid_success(v1_row, batch.SCORING_PROTOCOLS['v2']))


if __name__ == '__main__':
    unittest.main()
