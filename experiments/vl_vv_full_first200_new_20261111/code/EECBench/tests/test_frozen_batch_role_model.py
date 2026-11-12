"""Real batch parsing/freezing with fake replay processes; no model calls."""

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock


WORKSPACE = Path(__file__).resolve().parents[2]
ITERATIONS = WORKSPACE / 'EECBench/experiments/study_inconsistent_2/entity_discovery_iterations'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BATCH = load('role_batch_tested', ITERATIONS / 'run_frozen_batch.py')
LAUNCHER = load('role_batch_launcher_tested', ITERATIONS / 'owned_allocation_batch_launcher.py')


class FrozenBatchRoleModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source_workspace'
        self.inputs = self.root / 'inputs'
        script_dir = self.source / 'EECBench/scripts'
        script_dir.mkdir(parents=True)
        shutil.copyfile(WORKSPACE / 'EECBench/scripts/role_model_routing.py', script_dir / 'role_model_routing.py')
        (script_dir / 'replay_ensemble_entity_detection.py').write_text('# never executed\n')
        schema_dir = self.source / 'EECBench/schemas'
        schema_dir.mkdir()
        (schema_dir / 'fixture.json').write_text('{}')
        skill = self.source / '.agents/skills/ensemble-shot-entity-detection'
        (skill / 'references').mkdir(parents=True)
        (skill / 'SKILL.md').write_text('fixture policy')
        (skill / 'references/fixture.md').write_text('fixture reference')
        for shot in BATCH.SHOTS:
            bundle = self.inputs / shot / 'input_bundle'
            bundle.mkdir(parents=True)
            frames = []
            for index in range(6):
                image = bundle / f'frame_{index:06d}.jpg'
                image.write_bytes(b'fixture image bytes' + bytes([index]))
                frames.append({'frame_id': index, 'path': str(image)})
            (bundle / 'shot_manifest.json').write_text(json.dumps({'reference_frames': frames}))
            (bundle / 'prompt_bound_registry_semantic.json').write_text('{}')
        self.output = self.root / 'role_model_pilot_01/review_astra'
        self.argv = ['run_frozen_batch.py', '--source', str(self.inputs),
                     '--output-root', str(self.output), '--seeds', '1001', '--parallel-repeats', '1',
                     '--closure-rounds', '3', '--model', 'gpt-5.6-sol', '--reasoning-effort', 'high',
                     '--codex-bin', '/bin/true', '--identity-review-policy', 'physical_v0.6',
                     '--revision-output-policy', 'implicit_owner_wire_v0.1']

    def run_batch(self, review_model=None, code=0):
        argv = self.argv + ([] if review_model is None else ['--review-model', review_model])
        process = mock.Mock(pid=123456, wait=mock.Mock(return_value=code))
        with mock.patch.object(BATCH, 'WORKSPACE', self.source), mock.patch.object(sys, 'argv', argv), \
                mock.patch.object(BATCH.subprocess, 'Popen', return_value=process) as spawn, \
                redirect_stdout(io.StringIO()):
            result = BATCH.main()
        manifest = json.loads((self.output / 'robustness_manifest.json').read_text())
        return result, manifest, spawn.call_args.args[0]

    def test_explicit_routing_binds_frozen_helper_config_and_exact_launch_argv(self):
        result, manifest, command = self.run_batch('gpt-6-astra')
        self.assertEqual(result, 0)
        config = manifest['model_config']
        routing = manifest['model_routing']
        self.assertEqual(routing, config['model_routing'])
        self.assertEqual(routing['role_models']['detector'], 'gpt-5.6-sol')
        self.assertEqual(routing['role_models']['adjudicator_revision'], 'gpt-6-astra')
        self.assertEqual(manifest['review_model'], config['review_model'])
        config_path = self.output / 'execution_config/model_config.json'
        self.assertEqual(json.loads(config_path.read_text()), config)
        self.assertTrue(all(BATCH.digest(Path(p)) == h for p, h in manifest['execution_hashes'].items()))
        helper = 'EECBench/scripts/role_model_routing.py'
        self.assertEqual(manifest['source_hashes'][helper], BATCH.digest(self.source / helper))
        options = {'--output-root': str(self.output), '--model': 'gpt-5.6-sol',
                   '--review-model': 'gpt-6-astra', '--closure-rounds': '3',
                   '--identity-review-policy': 'physical_v0.6',
                   '--revision-output-policy': 'implicit_owner_wire_v0.1'}
        with mock.patch.object(LAUNCHER, 'PYTHON', sys.executable):
            self.assertEqual(command, LAUNCHER.expected_role_replay_argv(options, 1001))
        launch = json.loads((self.output / 'seed_1001.launch.json').read_text())
        self.assertEqual(launch['command'], command)
        self.assertEqual(command.count('--codex-review-model'), 1)
        self.assertNotIn('--ensemble-review-model', command)

    def test_same_model_control_is_explicit_and_failed_replay_stays_recorded(self):
        result, manifest, command = self.run_batch('gpt-5.6-sol', code=137)
        self.assertEqual(result, 1)
        self.assertEqual(manifest['status'], 'incomplete')
        self.assertEqual(manifest['results'][0]['returncode'], 137)
        self.assertEqual(set(manifest['model_routing']['role_models'].values()), {'gpt-5.6-sol'})
        self.assertEqual(command[command.index('--codex-review-model') + 1], 'gpt-5.6-sol')
        self.assertNotIn('token_usage', manifest)  # Batch exit never invents model accounting.

    def test_default_has_no_routing_fields_and_identical_wrapper_bytes(self):
        _, manifest, command = self.run_batch()
        for value in (manifest, manifest['model_config']):
            self.assertNotIn('review_model', value)
            self.assertNotIn('model_routing', value)
        self.assertNotIn('--codex-review-model', command)
        expected = self.root / 'baseline'
        expected.mkdir()
        config, _ = BATCH.freeze_codex_config(expected, '/bin/true', 'gpt-5.6-sol', 'high')
        self.assertEqual(Path(config['codex_wrapper']).read_bytes(),
                         Path(manifest['model_config']['codex_wrapper']).read_bytes())

    def test_none_does_not_require_new_helper_or_rewrite_config(self):
        self.output.mkdir(parents=True)
        config, locks = BATCH.freeze_codex_config(self.output, '/bin/true', 'gpt-5.6-sol', 'high')
        before = dict(locks)
        self.assertIsNone(BATCH.freeze_role_model_config(self.output, self.root / 'absent', config, locks, None))
        self.assertEqual(locks, before)
        self.assertTrue(all(BATCH.digest(Path(p)) == h for p, h in locks.items()))

    def test_invalid_review_rejected_by_parser_before_output_creation(self):
        for model in ('', ' ', ' gpt-6-astra'):
            with self.subTest(model=model), mock.patch.object(sys, 'argv', self.argv + ['--review-model', model]), \
                    redirect_stdout(io.StringIO()), mock.patch('sys.stderr', io.StringIO()):
                with self.assertRaises(SystemExit):
                    BATCH.main()
            self.assertFalse(self.output.exists())

    def test_routing_config_write_failure_prevents_any_replay_start(self):
        original = BATCH.write

        def fail_routing(path, value):
            if path.name == 'model_config.json' and 'model_routing' in value:
                raise OSError('injected routing persistence failure')
            original(path, value)

        with mock.patch.object(BATCH, 'WORKSPACE', self.source), \
                mock.patch.object(sys, 'argv', self.argv + ['--review-model', 'gpt-6-astra']), \
                mock.patch.object(BATCH, 'write', side_effect=fail_routing), \
                mock.patch.object(BATCH.subprocess, 'Popen') as spawn:
            with self.assertRaisesRegex(OSError, 'routing persistence'):
                BATCH.main()
        spawn.assert_not_called()
        self.assertFalse((self.output / 'seed_1001.launch.json').exists())

    def test_emitted_command_is_accepted_by_actual_replay_parser_before_io(self):
        _, _, command = self.run_batch('gpt-6-astra')
        scripts = str(WORKSPACE / 'EECBench/scripts')
        with mock.patch.object(sys, 'path', [scripts, *sys.path]):
            replay = load('role_actual_replay_parser_tested', WORKSPACE / 'EECBench/scripts/replay_ensemble_entity_detection.py')
        class ParsedOnly(Exception):
            pass
        with mock.patch.object(sys, 'argv', command[1:]), \
                mock.patch.object(replay, '_shot_dirs', side_effect=ParsedOnly) as parsed, \
                mock.patch.object(replay, 'run_ensemble_detection') as model:
            with self.assertRaises(ParsedOnly):
                replay.main()
        parsed.assert_called_once_with(self.output / 'frozen_inputs', BATCH.SHOTS)
        model.assert_not_called()


if __name__ == '__main__':
    unittest.main()
