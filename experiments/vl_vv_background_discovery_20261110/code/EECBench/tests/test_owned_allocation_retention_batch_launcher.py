"""Offline contract/dependency/identity regressions; every process call is mocked."""

from contextlib import ExitStack
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'EECBench/experiments/study_inconsistent_2/entity_discovery_iterations/owned_allocation_retention_batch_launcher.py'
SPEC = importlib.util.spec_from_file_location('retention_launcher_tested', SOURCE)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
B = M.B


class RetentionBatchLauncherTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.workspace = self.root / M.PACKAGE_NAME / 'source_workspace'
        self.inputs = self.root / M.PACKAGE_NAME / 'frozen_inputs'
        self.output = self.root / M.OUTPUT_NAME
        self.control = self.root / M.CONTROL_NAME
        self.binary = self.root / 'codex'
        self.binary.write_bytes(b'nonexecutable synthetic binary')
        patches = ExitStack()
        self.addCleanup(patches.close)
        patches.enter_context(mock.patch.object(B, 'PYTHON', '/synthetic/python'))
        patches.enter_context(mock.patch.object(B, 'CODEX', str(self.binary)))
        patches.enter_context(mock.patch.object(B, 'CODEX_SHA256', B.sha(self.binary)))
        real_sha = B.sha
        patches.enter_context(mock.patch.object(B, 'sha', side_effect=lambda p:
                               '1' * 64 if str(p) == B.PYTHON else real_sha(p)))
        self.patches = patches
        paths = [str(B.RUNNER), *M.SEMANTIC_FILES,
                 '.agents/skills/ensemble-shot-entity-detection/SKILL.md',
                 '.agents/skills/ensemble-shot-entity-detection/references/scope-retention-protocol.md']
        for relative in paths:
            path = self.workspace / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('synthetic frozen bytes ' + relative)
        for shot in B.SHOTS:
            bundle = self.inputs / shot / 'input_bundle'
            bundle.mkdir(parents=True)
            (bundle / 'shot_manifest.json').write_text(json.dumps({'reference_frames': [{'frame_id': i} for i in range(6)]}))
            (bundle / 'prompt_bound_registry_semantic.json').write_text('{}')
            (bundle / 'historical_registry.json').write_text('{"retained": true}')
            for i in range(6):
                (bundle / f'frame_{i:06d}.jpg').write_bytes(b'opaque image fixture ' + bytes([i]))
        self.admission = self.root / 'admission'
        directory = self.admission / 'verification_retention'
        directory.mkdir(parents=True)
        raw = {'schema_version': 'physical_identity_review_v0.6', 'shot_id': 'synthetic',
               'protocol_version': 'single_shot_inventory_first_boxed_granularity_v0.5',
               'verifier_id': 'verifier_1', 'reviews': [], 'warnings': [],
               'scope_retention_policy': M.POLICY, 'retention_requests': []}
        core = {key: value for key, value in raw.items() if key not in {'scope_retention_policy', 'retention_requests'}}
        (directory / 'attempt1.json').write_text(json.dumps(raw))
        audit = {'raw_file_sha256': B.sha(directory / 'attempt1.json'), 'original_core_validators_passed': True}
        usage = {'input_tokens': 10, 'cached_input_tokens': 2, 'output_tokens': 5, 'total_tokens': 15}
        row = {'role': 'verification_retention', 'attempt': 1, 'status': 'success', 'error': None,
               'returncode': 0, 'subprocess_started': True, 'subprocess_start_unknown': False,
               'thread_id': 'synthetic-thread', 'token_usage': usage,
               'projection_status': 'persisted', 'projection_audit': audit}
        for name, value in {'core_report.json': core, 'projection_audit.json': audit,
                            'attempt1.started.json': {'started': True}, 'result.json': row}.items():
            (directory / name).write_text(json.dumps(value))
        (directory / 'attempt1.stderr.log').write_text('')
        (directory / 'attempt1.events.jsonl').write_text(json.dumps({'type': 'turn.completed', 'usage': usage}) + '\n')
        self.admitted = {
            'status': 'success', 'contract_set': 'scope-retention-verifier-v0.1',
            'scope_retention_policy': M.POLICY, 'maximum_invocations': 1, 'maximum_retries': 0,
            'max_workers': 1, 'timeout_sec_per_call': 180, 'images': [], 'hashes_unchanged': True,
            'model_invocations': 1, 'model_invocation_count_complete': True, 'retry_count': 0,
            'unknown_subprocess_starts': [], 'unknown_usage_attempts': [],
            'model_config': {'model': 'gpt-5.6-sol', 'reasoning_effort': 'high',
                             'codex_binary': B.CODEX, 'codex_binary_sha256': B.CODEX_SHA256},
            'cases': [{'role': 'verification_retention', 'directory': str(directory), 'expected': raw,
                       'schema': str(self.workspace / M.SEMANTIC_FILES[2]),
                       'schema_sha256': B.sha(self.workspace / M.SEMANTIC_FILES[2]),
                       'core_schema': str(self.workspace / M.SEMANTIC_FILES[3]),
                       'core_schema_sha256': B.sha(self.workspace / M.SEMANTIC_FILES[3])}],
            'attempts': [row], 'token_usage': usage, 'known_token_usage_subtotal': usage,
            'hashes': {str(self.workspace / name): B.sha(self.workspace / name) for name in M.SEMANTIC_FILES},
            'output_hashes': {str(path): B.sha(path) for path in directory.iterdir()},
            'execution_state': {}, 'persistence_errors': [],
        }
        self.admission_path = self.admission / 'manifest.json'
        self.admission_path.write_text(json.dumps(self.admitted))
        argv = [B.PYTHON, '-B', str(self.workspace / B.RUNNER), '--output-root', str(self.output),
                '--source', str(self.inputs), '--seeds', *M.SEEDS, '--parallel-repeats', '2',
                '--closure-rounds', '3', '--model', 'gpt-5.6-sol', '--reasoning-effort', 'high',
                '--codex-bin', B.CODEX, '--identity-review-policy', 'physical_v0.6',
                '--revision-output-policy', 'implicit_owner_wire_v0.1', M.RETENTION_OPTION, M.POLICY]
        self.contract = {'version': M.CONTRACT_VERSION, 'argv': argv, 'source_workspace': str(self.workspace),
                         'input_root': str(self.inputs), 'python_sha256': '1' * 64,
                         'codex_binary_sha256': B.CODEX_SHA256,
                         'source_hashes': {str(path.relative_to(self.workspace)): B.sha(path) for path in B.source_files(self.workspace)},
                         'input_hashes': {str(path.relative_to(self.inputs)): B.sha(path) for path in B.regular_files(self.inputs)},
                         'launcher_dependency': {'filename': M.BASE_NAME, 'sha256': M.BASE_SHA256},
                         'schema_admission': {'manifest_path': str(self.admission_path),
                                              'manifest_sha256': B.sha(self.admission_path)}}
        self.contract_path = self.root / 'contract.json'
        self.save_contract()

    def save_contract(self):
        self.contract_path.write_text(json.dumps(self.contract))

    def save_admission(self):
        self.admission_path.write_text(json.dumps(self.admitted))
        self.contract['schema_admission']['manifest_sha256'] = B.sha(self.admission_path)
        self.save_contract()

    def prepared(self):
        M.prepare(self.control, self.contract_path, B.MAX_SECONDS)
        return M.load(self.control, assets=True, fresh=True)

    def process(self, argv=None):
        return {'pid': 12345, 'uid': B.UID, 'start_ticks': 67890,
                'argv': self.contract['argv'] if argv is None else argv,
                'cgroup': f'0::/system.slice/slurmstepd.scope/job_{B.JOB}/step_77/user/task_0'}

    def node(self):
        root, plan, contract = self.prepared()
        self.patches.enter_context(mock.patch.object(B, '__file__', str(root / M.SELF_NAME)))
        self.patches.enter_context(mock.patch.object(B, 'node_check', return_value={'checked': True}))
        return root, plan, contract

    def artifacts(self):
        self.output.mkdir()
        config_path = self.output / 'execution_config/model_config.json'
        config_path.parent.mkdir()
        wrapper = config_path.with_name('codex.sh')
        wrapper.write_text('#!/bin/sh\nexec ' + B.shlex.quote(B.CODEX) + ' -c '
                           + B.shlex.quote('model_reasoning_effort="high"') + ' "$@"\n')
        config = {'model': 'gpt-5.6-sol', 'reasoning_effort': 'high', 'codex_binary': B.CODEX,
                  'codex_binary_sha256': B.CODEX_SHA256, 'codex_wrapper': str(wrapper),
                  'scope_retention_policy': M.POLICY}
        config_path.write_text(json.dumps(config))
        manifest = {'pid': 12345, 'seeds': [1101, 1202, 1303], 'shots': list(B.SHOTS),
                    'parallel_repeats': 2, 'parallel_shots': 1, 'closure_max_rounds': 3,
                    'generic_identity_support_scope': 'all_support', 'model': 'gpt-5.6-sol',
                    'reasoning_effort': 'high', 'identity_review_policy': 'physical_v0.6',
                    'revision_output_policy': 'implicit_owner_wire_v0.1', 'scope_retention_policy': M.POLICY,
                    'source_hashes': {k: v for k, v in self.contract['source_hashes'].items() if k != str(B.RUNNER)},
                    'model_config': config, 'execution_hashes': {str(config_path): B.sha(config_path), str(wrapper): B.sha(wrapper)}}
        (self.output / 'robustness_manifest.json').write_text(json.dumps(manifest))
        _, options = M.parse_argv(self.contract['argv'])
        command = M.expected_replay_argv(options, '1101')
        (self.output / 'seed_1101.launch.json').write_text(json.dumps({'seed': 1101, 'pid': 54321, 'command': command}))
        (self.output / 'seed_1101.log').write_text('started synthetic replay')
        return manifest, config_path

    def test_prepare_freezes_adapter_and_original_dependency_without_process_or_old_source_change(self):
        before = M.BASE_PATH.read_bytes()
        with mock.patch.object(B.subprocess, 'Popen') as spawn, mock.patch.object(B, 'query') as query:
            root, plan, contract = self.prepared()
        spawn.assert_not_called()
        query.assert_not_called()
        self.assertEqual((root / M.SELF_NAME).read_bytes(), SOURCE.read_bytes())
        self.assertEqual((root / M.BASE_NAME).read_bytes(), before)
        self.assertEqual(M.BASE_PATH.read_bytes(), before)
        self.assertEqual(plan['source_sha256'], B.sha(SOURCE))
        self.assertEqual(contract['launcher_dependency']['sha256'], M.BASE_SHA256)
        self.assertEqual(len(contract['input_hashes']), 27)
        self.assertFalse(self.output.exists())
        with self.assertRaises(FileExistsError):
            M.prepare(self.control, self.contract_path, B.MAX_SECONDS)

    def test_only_fixed_condition_and_explicit_flags_accepted(self):
        for option, value in (('--model', 'gpt-6-astra'), ('--seeds', '707'), ('--parallel-repeats', '1'),
                              ('--closure-rounds', '4'), ('--identity-review-policy', 'legacy'),
                              ('--revision-output-policy', 'canonical'), (M.RETENTION_OPTION, 'disabled')):
            argv = list(self.contract['argv'])
            argv[argv.index(option) + 1] = value
            with self.subTest(option=option), self.assertRaises(ValueError):
                M.parse_argv(argv)
        for suffix in (['--review-model', 'gpt-5.6-sol'], ['--resume'], ['--seeds', *M.SEEDS]):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                M.parse_argv(self.contract['argv'] + suffix)
        with self.assertRaises(ValueError):
            M.parse_argv(self.contract['argv'], contract_version='frozen_batch_launch_contract_v0.1')
        argv = list(self.contract['argv'])
        argv[-2:] = []
        with self.assertRaises(ValueError):
            M.parse_argv(argv)

    def test_wrong_control_root_cannot_create_any_files(self):
        wrong = self.workspace / M.CONTROL_NAME
        with self.assertRaises(ValueError):
            M.prepare(wrong, self.contract_path, B.MAX_SECONDS)
        self.assertFalse(wrong.exists())

    def test_admission_unknown_cost_failed_projection_or_wrong_model_fail_before_prepare(self):
        for changed in ('unknown', 'cost', 'model', 'projection', 'persistence'):
            record = copy.deepcopy(self.admitted)
            if changed == 'unknown':
                record['unknown_subprocess_starts'] = ['verification_retention']
            elif changed == 'cost':
                record['token_usage'] = None
            elif changed == 'model':
                record['model_config']['model'] = 'gpt-6-astra'
            elif changed == 'projection':
                record['attempts'][0]['projection_status'] = 'validated_in_memory'
            else:
                record['persistence_errors'] = [{'error': 'failed'}]
            self.admission_path.write_text(json.dumps(record))
            contract = copy.deepcopy(self.contract)
            contract['schema_admission']['manifest_sha256'] = B.sha(self.admission_path)
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                M.validate_contract(contract)
        self.assertFalse(self.control.exists())

    def test_actual_shared_aggregate_shape_passes_and_integer_zero_is_rejected(self):
        path = SOURCE.with_name('run_single_frame_schema_transport_smoke.py')
        spec = importlib.util.spec_from_file_location('retention_launcher_actual_aggregate', path)
        shared = importlib.util.module_from_spec(spec)
        with mock.patch.object(sys, 'path', [str(SOURCE.parent), *sys.path]):
            spec.loader.exec_module(shared)
        runtime = SimpleNamespace(TOKEN_KEYS=('input_tokens', 'cached_input_tokens', 'output_tokens', 'total_tokens'))
        self.admitted.update(shared.aggregate_usage(runtime, self.admitted['attempts']))
        self.save_admission()
        M.validate_contract(self.contract)
        for key in ('unknown_subprocess_starts', 'unknown_usage_attempts'):
            self.assertEqual(self.admitted[key], [])
            record = copy.deepcopy(self.admitted)
            record[key] = 0
            self.admission_path.write_text(json.dumps(record))
            contract = copy.deepcopy(self.contract)
            contract['schema_admission']['manifest_sha256'] = B.sha(self.admission_path)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'single-call contract'):
                M.validate_contract(contract)

    def test_admission_requires_output_locks_and_semantic_hashes_but_not_auxiliary_equality(self):
        extra = self.admission / 'different_auxiliary.py'
        extra.write_text('an admission-only helper')
        self.admitted['hashes'][str(extra)] = B.sha(extra)
        self.save_admission()
        M.validate_contract(self.contract)
        self.admitted['output_hashes'].pop(str(self.admission / 'verification_retention/attempt1.json'))
        self.save_admission()
        with self.assertRaisesRegex(ValueError, 'omit'):
            M.validate_contract(self.contract)
        self.admitted['output_hashes'][str(self.admission / 'verification_retention/attempt1.json')] = B.sha(
            self.admission / 'verification_retention/attempt1.json')
        self.admitted['cases'][0]['schema_sha256'] = '0' * 64
        self.save_admission()
        with self.assertRaisesRegex(ValueError, 'schemas differ'):
            M.validate_contract(self.contract)

    def test_complete_input_tree_and_source_semantics_drift_rejected(self):
        (self.inputs / B.SHOTS[0] / 'input_bundle/new_file.txt').write_text('not locked')
        with self.assertRaisesRegex(ValueError, 'complete file set'):
            M.validate_contract(self.contract)
        (self.inputs / B.SHOTS[0] / 'input_bundle/new_file.txt').unlink()
        (self.workspace / M.SEMANTIC_FILES[0]).write_text('changed semantics')
        with self.assertRaisesRegex(ValueError, 'Frozen content'):
            M.validate_contract(self.contract)

    def test_frozen_dependency_drift_prevents_status_or_start_even_without_asset_scan(self):
        root, _, _ = self.prepared()
        (root / M.BASE_NAME).write_text('tampered dependency')
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            M.load(root)
        with self.assertRaisesRegex(ValueError, 'dependency bytes changed'):
            spec = importlib.util.spec_from_file_location('invalid_frozen_retention', root / M.SELF_NAME)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

    def test_dependency_publish_failure_leaves_unlaunchable_preparation(self):
        original = Path.open
        def failing(path, mode='r', *args, **kwargs):
            if path == self.control / M.BASE_NAME and mode == 'xb':
                raise OSError('synthetic dependency write failure')
            return original(path, mode, *args, **kwargs)
        with mock.patch.object(Path, 'open', failing), mock.patch.object(B, 'query') as query:
            with self.assertRaises(OSError):
                M.prepare(self.control, self.contract_path, B.MAX_SECONDS)
        query.assert_not_called()
        with self.assertRaises(FileNotFoundError):
            M.load(self.control)
        self.assertFalse(self.output.exists())

    def test_start_claim_is_once_only_and_reuses_one_srun_controller(self):
        root, plan, _ = self.node()
        with mock.patch.object(B, 'identity', return_value=self.process()), mock.patch.object(
                B, 'query', return_value={'returncode': 0, 'stdout': '', 'stderr': ''}) as query:
            B.node_start(root)
            with self.assertRaises(FileExistsError):
                B.node_start(root)
        self.assertEqual(query.call_count, 1)
        self.assertEqual(query.call_args.args[0][:2], ['tmux', '-S'])
        self.assertIn(str(root / M.SELF_NAME), query.call_args.args[0])
        command = B.srun_command(root, plan)
        self.assertIn('--jobid=' + B.JOB, command)
        self.assertIn('--gres=none', command)
        self.assertIn('--time=06:00:00', command)
        self.assertEqual(command[-4:], [str(root / M.SELF_NAME), '_entry', '--control-dir', str(root)])

    def test_startup_requires_exact_retention_config_replay_and_unchanged_wrapper(self):
        manifest, config_path = self.artifacts()
        self.assertTrue(M.driver_artifacts(self.contract, self.process())['confirmed'])
        path = self.output / 'robustness_manifest.json'
        for changed in ('policy', 'review', 'wrapper'):
            record = copy.deepcopy(manifest)
            if changed == 'policy':
                record['scope_retention_policy'] = 'disabled'
            elif changed == 'review':
                record['review_model'] = 'gpt-5.6-sol'
            else:
                wrapper = config_path.with_name('codex.sh')
                wrapper.write_text(wrapper.read_text().replace(' -c ', ' --disable shell_tool -c '))
                record['execution_hashes'][str(wrapper)] = B.sha(wrapper)
            path.write_text(json.dumps(record))
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                M.driver_artifacts(self.contract, self.process())

    def test_replay_policy_omission_cannot_confirm_started(self):
        self.artifacts()
        path = self.output / 'seed_1101.launch.json'
        launch = B.read(path)
        launch['command'] = launch['command'][:-2]
        path.write_text(json.dumps(launch))
        with self.assertRaisesRegex(ValueError, 'replay argv'):
            M.driver_artifacts(self.contract, self.process())

    def test_precise_stop_preserves_failure_and_never_uses_allocation_cancel(self):
        root, plan, _ = self.node()
        saved = {'host': B.NODE, 'job_id': B.JOB, 'step_id': '77',
                 'entry_process': self.process(B.phase_argv(root, '_entry')),
                 'driver_argv': self.contract['argv'], 'plan_sha256': B.sha(root / 'plan.json'),
                 'contract_sha256': B.sha(root / 'contract.json'), 'phase': 'before_driver_exec',
                 'driver_start_not_yet_confirmed': True}
        B.write_new(root / 'task_identity.json', saved)
        response = {'returncode': 0, 'stdout': f'StepId={B.JOB}.77 UserId={B.UID} NodeList={B.NODE} Name=eec-batch-{plan["run_id"][:12]}', 'stderr': ''}
        with mock.patch.object(B, 'identity', return_value=self.process()), mock.patch.object(
                B, 'query', side_effect=[response, {'returncode': 1, 'stdout': '', 'stderr': 'refused'}]) as query:
            result = B.node_stop(root)
        self.assertEqual(query.call_args.args[0], ['scancel', B.JOB + '.77'])
        self.assertEqual(result['status'], 'exact_step_stop_failed')
        self.assertEqual(result['returncode'], 1)
        self.assertIsNone(result['total_model_usage'])


if __name__ == '__main__':
    unittest.main()
