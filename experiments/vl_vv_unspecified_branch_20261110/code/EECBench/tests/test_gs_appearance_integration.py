import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_gs_temporal as pipeline
from run_gs_integrated import save, read


class AppearanceIntegrationTests(unittest.TestCase):
    shots = [dict(shot_id=s) for s in ('shot1', 'shot2', 'shot3')]

    def test_default_full_and_both_registration_methods(self):
        for method in ('roma_fps32', 'codex_direct'):
            jobs = pipeline.plan('/tmp/case', self.shots, 3, 'GPU-test', alignment_method=method)
            names = [j['stage'] for j in jobs]
            self.assertEqual(names[-5:], ['appearance_prepare', 'appearance_dino', 'appearance_compact',
                                         'appearance_codex', 'appearance_report'])
            self.assertEqual(jobs[-5]['depends'], ['global_entity_table'])
            self.assertEqual(jobs[-4]['depends'], ['appearance_prepare'])
            self.assertEqual(jobs[-3]['depends'], ['appearance_prepare'])
            self.assertEqual(jobs[-2]['depends'], ['appearance_compact'])
            self.assertEqual(jobs[-1]['depends'], ['appearance_codex','appearance_dino'])
            self.assertIn('--defer-dino',jobs[-3]['command'])
            self.assertIn('within_shot2', names)
            self.assertEqual(Path(jobs[-4]['command'][1]).name, 'guard_gpu.py')
            self.assertEqual(jobs[-4]['command'][2:4], ['3', 'GPU-test'])
            self.assertTrue(jobs[-4]['gpu'])
            self.assertEqual(sum(j['gpu'] for j in jobs[-5:]), 1)
            self.assertIn('gs_entity_appearance_scoring.py', ' '.join(jobs[-2]['command']))
            self.assertNotIn('budget', ' '.join(jobs[-2]['command']))

    def test_legacy_retains_serial_appearance(self):
        jobs=pipeline.plan('/tmp/case',self.shots,0,'GPU-test',schedule_name='legacy')
        for a,b in zip(jobs[-5:-1],jobs[-4:]):
            self.assertEqual(b['depends'],[a['stage']])
        self.assertNotIn('--defer-dino',jobs[-3]['command'])
        self.assertEqual(jobs[-2]['command'][-1],'3')

    def test_explicit_early_stops_preserve_scope(self):
        for stop in ('identity', 'presence', 'spatial'):
            jobs = pipeline.plan('/tmp/case', self.shots, 0, 'GPU-test', stop_after=stop)
            self.assertFalse(any(j['stage'].startswith('appearance_') for j in jobs))
            for j in jobs:
                if j['stage'].startswith('within_') or j['stage'].endswith('_boundary'):
                    self.assertNotEqual(stop, 'identity')
                    self.assertEqual('--presence-only' in j['command'], stop == 'presence')

    def test_singleton_scene_also_gets_appearance(self):
        jobs = pipeline.plan('/tmp/case', [dict(shot_id='only', scene_id='alone')], 0, 'GPU-test')
        self.assertEqual(jobs[-1]['stage'], 'appearance_report')
        self.assertEqual(next(j for j in jobs if j['stage'] == 'global_entity_table')['depends'],
                         ['detection_and_clustering'])

    def case(self, root):
        save(root / 'alignment_method.json', dict(method='roma_fps32'))
        save(root / 'identity_scope.json', dict(cross_shot_pairs=[], scenes={}))
        save(root / 'raw_manifest.json', dict(shots=[]))

    def test_scores_and_usage_in_summary_once(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); self.case(root)
            usage = [dict(input_tokens=100, output_tokens=10, cached_input_tokens=60)]
            for path in ('calls/expected_motion_shot1', 'appearance/compact/calls/ge1'):
                save(root / path / 'status.json', dict(status='success', seconds=1, usage=usage))
            totals = dict(codex_score=25, dino_score=.91, entities=1)
            study = dict(source=str(root / 'appearance/compact'), all_entities=totals,
                         multi_shot_entities=totals, single_shot_entities={}, reused_total_tokens=110,
                         reused_standard_api_equivalent_usd=pipeline.appearance.cost(usage))
            save(root / 'appearance/report/results.json', dict(protocol='entity_appearance_scoring_v6',
                 model_protocol='entity_appearance_compact_v3', studies=[study]))
            stages = [dict(stage=s, status='success', seconds=1) for s in
                      ('expected_motion_shot1', 'appearance_codex', 'appearance_report')]
            state = dict(status='success', seconds=3, stop_after='full', stages=stages)
            r = pipeline.summarize(root, state)
            self.assertEqual(r['total_tokens'], 220)
            self.assertAlmostEqual(r['standard_api_equivalent_usd'], 2 * pipeline.appearance.cost(usage))
            self.assertEqual([s['total_tokens'] for s in r['stages']], [110, 110, 0])
            self.assertEqual(r['appearance']['total_tokens'], 110)
            self.assertEqual(r['appearance']['all_entities'], totals)
            self.assertFalse(r['appearance']['fused_score'])
            self.assertEqual(r['appearance']['model_calls'], 1)
            study['reused_total_tokens'] = 111
            save(root / 'appearance/report/results.json', dict(protocol='entity_appearance_scoring_v6',
                 model_protocol='entity_appearance_compact_v3', studies=[study]))
            with self.assertRaisesRegex(ValueError, 'accounting mismatch'):
                pipeline.summarize(root, state)

    def test_model_failure_stops_report_and_remains_failure(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); self.case(root); invoked = []
            def run(cmd, **kwargs):
                invoked.append(cmd)
                return SimpleNamespace(returncode=2)
            jobs = [dict(stage=n, command=[n], case_root=str(root), gpu=False, depends=deps) for n, deps in
                    [('appearance_codex', []), ('appearance_report', ['appearance_codex'])]]
            with self.assertRaises(RuntimeError):
                pipeline.execute(root, jobs, {}, 'test', 'full', run_process=run)
            self.assertEqual(invoked, [['appearance_codex']])
            r = read(root / 'summary.json')
            self.assertEqual(r['status'], 'failed')
            self.assertEqual(r['appearance']['status'], 'incomplete')
            self.assertNotIn('all_entities', r['appearance'])

    def test_missing_appearance_result_prevents_full_success(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); self.case(root)
            save(root / 'global_entities/global_entities.json', dict(counts={}))
            with self.assertRaisesRegex(ValueError, 'Missing appearance scores'):
                pipeline.execute(root, [], {}, 'test', 'full')
            self.assertEqual(read(root / 'pipeline_runtime.json')['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
