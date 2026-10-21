"""Local checks for the integrated VL/VV runner; no GPU or API calls."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_vl_vv_pipeline as pipeline


class PipelinePlanTests(unittest.TestCase):
    def make_case(self, root, status='complete', with_registry=True):
        case = root / 'case'
        case.mkdir()
        frames = []
        for index in range(6):
            frame = root / f'frame_{index}.jpg'
            frame.write_bytes(b'image fixture')
            frames.append(dict(frame_id=index, path=str(frame)))
        (case / 'raw_manifest.json').write_text(json.dumps(dict(
            shots=[dict(shot_id='Shot1', frames=frames)])))
        (case / 'contract.json').write_text('{}')
        (case / 'run.json').write_text(json.dumps(dict(
            protocol='vl_vv_detection_v1', status=status)))
        if with_registry:
            (case / 'episode_entities.json').write_text(json.dumps(dict(
                protocol='vl_vv_detection_v1', status='matched')))
        return case

    def test_registry_plan_uses_fresh_outputs_as_next_stage_inputs(self):
        # The single-issue-list chain (discovery v4); the default branch chain is tested in
        # test_vl_vv_branch_pipeline.py.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = self.make_case(root)
            output = root / 'new_run'
            plan = pipeline.build_plan(case, output, 'from-registry', discovery_protocol='v4')
            self.assertEqual([stage['name'] for stage in plan['stages']],
                             ['issue_discovery', 'issue_review', 'episode_scoring'])
            review = plan['stages'][1]['command']
            score = plan['stages'][2]['command']
            self.assertEqual(review[review.index('--issues') + 1],
                             str(output / 'issue_discovery/result.json'))
            self.assertEqual(score[score.index('--review') + 1],
                             str(output / 'issue_review/result.json'))
            self.assertEqual(plan['discovery_prompt'], str(pipeline.STAGE_FILES['v4']['discovery_prompt']))
            self.assertFalse(output.exists())

    def test_full_plan_requires_prepared_case_and_gpu_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = self.make_case(root, status='prepared', with_registry=False)
            with self.assertRaisesRegex(ValueError, 'physical --gpu'):
                pipeline.build_plan(case, root / 'run', 'full')
            plan = pipeline.build_plan(case, root / 'run', 'full', 2, 'GPU-abcdef', discovery_protocol='v4')
            self.assertEqual([stage['name'] for stage in plan['stages']],
                             list(pipeline.FULL_STAGES))

    def test_refuses_existing_output_and_incomplete_registry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = self.make_case(root)
            (root / 'existing').mkdir()
            with self.assertRaises(FileExistsError):
                pipeline.build_plan(case, root / 'existing', 'from-registry')
            (case / 'run.json').write_text(json.dumps(dict(
                protocol='vl_vv_detection_v1', status='matched')))
            with self.assertRaisesRegex(ValueError, 'completed detection case'):
                pipeline.build_plan(case, root / 'new', 'from-registry')

    def test_execute_refuses_login_node_before_creating_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = self.make_case(root)
            output = root / 'new_run'
            plan = pipeline.build_plan(case, output, 'from-registry')
            old = pipeline.os.environ.pop('SLURM_JOB_ID', None)
            try:
                with self.assertRaisesRegex(RuntimeError, 'Slurm allocation'):
                    pipeline.execute(plan)
            finally:
                if old is not None:
                    pipeline.os.environ['SLURM_JOB_ID'] = old
            self.assertFalse(output.exists())

    def test_execute_refuses_unlabeled_images_without_the_historical_flag(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = self.make_case(root)
            output = root / 'new_run'
            plan = pipeline.build_plan(case, output, 'from-registry')
            with mock.patch.dict(pipeline.os.environ, {
                    'SLURM_JOB_ID': 'fixture-job', 'EECBENCH_IMAGE_LABELS': 'off'}):
                with self.assertRaisesRegex(RuntimeError, 'allow-unlabeled-images'):
                    pipeline.execute(plan)
            self.assertFalse(output.exists())

    def test_full_execution_refuses_shared_gpu_override(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = self.make_case(root, status='prepared', with_registry=False)
            output = root / 'new_run'
            plan = pipeline.build_plan(case, output, 'full', 2, 'GPU-abcdef')
            with mock.patch.dict(pipeline.os.environ, {
                    'SLURM_JOB_ID': 'fixture-job', 'EECBENCH_ALLOW_SHARED_GPU': '1'}):
                with self.assertRaisesRegex(RuntimeError, 'shared-GPU mode'):
                    pipeline.execute(plan)
            self.assertFalse(output.exists())

    def test_registry_execution_connects_all_three_stages_without_api(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = self.make_case(root)
            output = root / 'new_run'
            plan = pipeline.build_plan(case, output, 'from-registry', discovery_protocol='v1')
            seen = []

            def fake_run(command, **kwargs):
                seen.append(command)
                if str(pipeline.DISCOVERY) in command:
                    target = output / 'issue_discovery/result.json'
                    value = {'status': 'success'}
                elif str(pipeline.REVIEW) in command:
                    target = output / 'issue_review/result.json'
                    value = {'review_run': {'status': 'success'}}
                else:
                    target = output / 'episode_scoring/result.json'
                    value = {'status': 'success', 'protocol': 'vl_vv_episode_scoring_v2'}
                target.parent.mkdir(parents=True)
                target.write_text(json.dumps(value))
                return mock.Mock(returncode=0)

            with mock.patch.dict(pipeline.os.environ, {'SLURM_JOB_ID': 'fixture-job'}), \
                 mock.patch.object(pipeline.subprocess, 'run', side_effect=fake_run):
                result = pipeline.execute(plan)
            self.assertEqual(result['status'], 'success')
            self.assertEqual([row['name'] for row in result['stage_results']],
                             list(pipeline.REGISTRY_STAGES))
            self.assertEqual(len(seen), 3)
            self.assertEqual(json.loads((output / 'run.json').read_text())['status'], 'success')

    def test_full_execution_connects_detection_through_v2_scoring(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = self.make_case(root, status='prepared', with_registry=False)
            output = root / 'new_run'
            plan = pipeline.build_plan(case, output, 'full', 2, 'GPU-abcdef', discovery_protocol='v1')
            seen = []

            def save_json(path, value):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(value))

            def fake_run(command, **kwargs):
                name = pipeline.FULL_STAGES[len(seen)]
                seen.append((name, command))
                if name == 'detect':
                    save_json(case / 'run.json', {'protocol': 'vl_vv_detection_v1',
                                                  'status': 'detected'})
                    save_json(case / 'entities/run.json', {'status': 'success'})
                    save_json(case / 'shot_prompt_recovery/results.json', {'status': 'success'})
                elif name == 'match':
                    save_json(case / 'run.json', {'protocol': 'vl_vv_detection_v1',
                                                  'status': 'matched'})
                    save_json(case / 'episode_entities.json', {'status': 'matched'})
                elif name == 'dino_prepare':
                    save_json(case / 'dino/canonical/manifest.json', {})
                elif name == 'attach_dino':
                    save_json(case / 'run.json', {'protocol': 'vl_vv_detection_v1',
                                                  'status': 'complete'})
                elif name == 'issue_discovery':
                    save_json(output / 'issue_discovery/result.json', {'status': 'success'})
                elif name == 'issue_review':
                    save_json(output / 'issue_review/result.json',
                              {'review_run': {'status': 'success'}})
                elif name == 'episode_scoring':
                    save_json(output / 'episode_scoring/result.json',
                              {'status': 'success', 'protocol': 'vl_vv_episode_scoring_v2'})
                return mock.Mock(returncode=0)

            with mock.patch.dict(pipeline.os.environ, {'SLURM_JOB_ID': 'fixture-job',
                                                      'EECBENCH_ALLOW_SHARED_GPU': '0'},
                                 clear=False), mock.patch.object(pipeline.subprocess, 'run',
                                                                  side_effect=fake_run):
                result = pipeline.execute(plan)
            self.assertEqual(result['status'], 'success')
            self.assertEqual([name for name, _ in seen], list(pipeline.FULL_STAGES))
            self.assertEqual(len(result['stage_results']), 8)

    def test_failed_stage_is_recorded_and_later_stages_do_not_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = self.make_case(root)
            output = root / 'new_run'
            plan = pipeline.build_plan(case, output, 'from-registry', discovery_protocol='v4')
            calls = []

            def fake_run(command, **kwargs):
                calls.append(command)
                if len(calls) == 1:
                    target = output / 'issue_discovery/result.json'
                    target.parent.mkdir(parents=True)
                    target.write_text(json.dumps({'status': 'success'}))
                    return mock.Mock(returncode=0)
                return mock.Mock(returncode=2)

            with mock.patch.dict(pipeline.os.environ, {'SLURM_JOB_ID': 'fixture-job'}), \
                 mock.patch.object(pipeline.subprocess, 'run', side_effect=fake_run):
                with self.assertRaisesRegex(RuntimeError, 'issue_review exited 2'):
                    pipeline.execute(plan)
            self.assertEqual(len(calls), 2)
            saved = json.loads((output / 'run.json').read_text())
            self.assertEqual(saved['status'], 'failed')
            self.assertEqual([row['exit_code'] for row in saved['stage_results']], [0, 2])


if __name__ == '__main__':
    unittest.main()
