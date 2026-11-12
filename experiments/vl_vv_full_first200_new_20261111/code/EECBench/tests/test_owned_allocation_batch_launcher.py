"""Offline launcher fault tests: all process, SSH and Slurm calls are mocked."""

from contextlib import ExitStack
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'EECBench/experiments/study_inconsistent_2/entity_discovery_iterations/owned_allocation_batch_launcher.py'
SPEC = importlib.util.spec_from_file_location('owned_batch_launcher_tested', SOURCE)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class BatchLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.workspace = self.base / 'package/source_workspace'
        self.inputs = self.base / 'package/frozen_inputs'
        self.output = self.base / M.OUTPUT_NAME
        self.control = self.base / 'control'
        self.binary = self.base / 'pinned_codex'
        self.binary.write_bytes(b'never executable, fake CLI bytes')
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.patches.enter_context(mock.patch.object(M, 'CODEX', str(self.binary)))
        self.patches.enter_context(mock.patch.object(M, 'CODEX_SHA256', M.sha(self.binary)))
        self.patches.enter_context(mock.patch.object(M, 'PYTHON', '/synthetic/pinned/python'))
        real_sha = M.sha
        self.patches.enter_context(mock.patch.object(M, 'sha', side_effect=lambda p: '1' * 64 if str(p) == M.PYTHON else real_sha(p)))
        sources = [M.RUNNER, Path('EECBench/scripts/runtime.py'), Path('EECBench/schemas/test.json'),
                   Path('.agents/skills/ensemble-shot-entity-detection/SKILL.md'),
                   Path('.agents/skills/ensemble-shot-entity-detection/references/contract.md')]
        for relative in sources:
            path = self.workspace / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('frozen test fixture only\n')
        for shot in M.SHOTS:
            bundle = self.inputs / shot / 'input_bundle'
            bundle.mkdir(parents=True)
            (bundle / 'shot_manifest.json').write_text(json.dumps({'reference_frames': [{'frame_id': i} for i in range(6)]}))
            (bundle / 'prompt_bound_registry_semantic.json').write_text('{}')
            for i in range(6):
                (bundle / f'frame_{i:06d}.jpg').write_bytes(b'original placeholder' + bytes([i]))
        extra = self.inputs / M.SHOTS[0] / 'input_bundle/extra/nested.bin'
        extra.parent.mkdir()
        extra.write_bytes(b'copytree must retain and lock this too')
        argv = [M.PYTHON, '-B', str(self.workspace / M.RUNNER), '--output-root', str(self.output),
                '--source', str(self.inputs), '--seeds', '707', '808', '909', '--parallel-repeats', '2',
                '--closure-rounds', '3', '--model', 'gpt-5.6-sol', '--reasoning-effort', 'high',
                '--codex-bin', str(self.binary), '--identity-review-policy', 'physical_v0.6',
                '--revision-output-policy', 'implicit_owner_wire_v0.1']
        self.contract = {'version': M.CONTRACT_VERSION, 'argv': argv, 'source_workspace': str(self.workspace),
                         'source_hashes': {str(p.relative_to(self.workspace)): M.sha(p) for p in M.source_files(self.workspace)},
                         'input_root': str(self.inputs),
                         'input_hashes': {str(p.relative_to(self.inputs)): M.sha(p) for p in M.regular_files(self.inputs)},
                         'python_sha256': '1' * 64, 'codex_binary_sha256': M.CODEX_SHA256}
        self.contract_path = self.base / 'contract.json'
        self.contract_path.write_text(json.dumps(self.contract))

    def prepared(self):
        M.prepare(self.control, self.contract_path, M.MAX_SECONDS)
        return M.load(self.control, assets=True, fresh=True)

    def node(self):
        root, plan, contract = self.prepared()
        self.patches.enter_context(mock.patch.object(M, '__file__', str(root / M.SELF_NAME)))
        self.patches.enter_context(mock.patch.object(M, 'node_check', return_value={'checked': True}))
        return root, plan, contract

    def process(self, argv=None):
        return {'pid': 7654321, 'uid': M.UID, 'start_ticks': 123456,
                'argv': argv or self.contract['argv'],
                'cgroup': f'0::/system.slice/slurmstepd.scope/job_{M.JOB}/step_99/user/task_0'}

    def task(self, root):
        record = {'host': M.NODE, 'job_id': M.JOB, 'step_id': '99',
                  'entry_process': self.process(M.phase_argv(root, '_entry')),
                  'driver_argv': self.contract['argv'], 'plan_sha256': M.sha(root / 'plan.json'),
                  'contract_sha256': M.sha(root / 'contract.json'), 'phase': 'before_driver_exec',
                  'driver_start_not_yet_confirmed': True}
        M.write_new(root / 'task_identity.json', record)
        return record

    def matching_manifest(self):
        return {'pid': self.process()['pid'], 'seeds': [707, 808, 909], 'shots': list(M.SHOTS),
                'parallel_repeats': 2, 'parallel_shots': 1, 'closure_max_rounds': 3,
                'generic_identity_support_scope': 'all_support', 'model': 'gpt-5.6-sol',
                'reasoning_effort': 'high', 'identity_review_policy': 'physical_v0.6',
                'revision_output_policy': 'implicit_owner_wire_v0.1',
                'source_hashes': {k: v for k, v in self.contract['source_hashes'].items() if k != str(M.RUNNER)}}

    def role_contract(self, arm='review_astra'):
        value = copy.deepcopy(self.contract)
        value['version'] = M.ROLE_CONTRACT_VERSION
        argv = value['argv']
        argv[argv.index('--output-root') + 1] = str(self.base / M.ROLE_PILOT_NAME / arm)
        index = argv.index('--seeds') + 1
        argv[index:index + 3] = ['1001']
        argv[argv.index('--parallel-repeats') + 1] = '1'
        argv.extend(['--review-model', M.ROLE_ARMS[arm]])
        return value

    def role_artifacts(self):
        self.contract = self.role_contract()
        self.output = self.base / M.ROLE_PILOT_NAME / 'review_astra'
        self.output.mkdir(parents=True)
        _, options = M.parse_argv(self.contract['argv'], contract_version=self.contract['version'])
        routing = M.requested_model_routing(options)
        config = {'model': 'gpt-5.6-sol', 'review_model': 'gpt-6-astra',
                  'reasoning_effort': 'high', 'model_routing': routing}
        config_path = self.output / 'execution_config/model_config.json'
        config_path.parent.mkdir()
        M.write_new(config_path, config)
        manifest = self.matching_manifest()
        manifest.update(seeds=[1001], parallel_repeats=1, review_model='gpt-6-astra',
                        model_routing=routing, model_config=config,
                        execution_hashes={str(config_path): M.sha(config_path)})
        M.write_new(self.output / 'robustness_manifest.json', manifest)
        command = M.expected_role_replay_argv(options, 1001)
        M.write_new(self.output / 'seed_1001.launch.json', {'pid': 8888, 'seed': 1001, 'command': command})
        (self.output / 'seed_1001.log').write_text('synthetic replay startup')
        return manifest, config_path

    def test_role_contract_accepts_only_two_fixed_arms_and_preserves_old_allowlist(self):
        for arm in M.ROLE_ARMS:
            contract = self.role_contract(arm)
            M.validate_contract(contract)
            with self.assertRaises(ValueError):
                M.parse_argv(contract['argv'])
            with self.assertRaises(ValueError):
                M.parse_argv(self.contract['argv'], contract_version=M.ROLE_CONTRACT_VERSION)
            for option, wrong in [('--review-model', 'gpt-6-astra' if arm == 'control_sol' else 'gpt-5.6-sol'),
                                  ('--seeds', '707'), ('--parallel-repeats', '2'),
                                  ('--model', 'gpt-6-astra'), ('--closure-rounds', '4')]:
                argv = list(contract['argv'])
                argv[argv.index(option) + 1] = wrong
                with self.subTest(arm=arm, option=option), self.assertRaises(ValueError):
                    M.parse_argv(argv, contract_version=M.ROLE_CONTRACT_VERSION)

    def test_role_prepare_remains_exclusive_and_does_not_start_a_process(self):
        self.contract_path.write_text(json.dumps(self.role_contract()))
        with mock.patch.object(M.subprocess, 'Popen') as spawn, mock.patch.object(M, 'query') as query:
            root, _, contract = self.prepared()
            with self.assertRaises(FileExistsError):
                M.prepare(self.control, self.contract_path, M.MAX_SECONDS)
        spawn.assert_not_called()
        query.assert_not_called()
        self.assertEqual(contract['version'], M.ROLE_CONTRACT_VERSION)
        self.assertEqual(M.read(root / 'contract.json')['argv'], self.role_contract()['argv'])
        self.assertFalse((self.base / M.ROLE_PILOT_NAME / 'review_astra').exists())

    def test_role_startup_requires_config_pair_roles_and_exact_replay_command(self):
        manifest, _ = self.role_artifacts()
        self.assertTrue(M.driver_artifacts(self.contract, self.process())['confirmed'])
        path = self.output / 'robustness_manifest.json'
        for change in ('review_model', 'primary_model', 'verifier_role'):
            value = copy.deepcopy(manifest)
            if change == 'review_model':
                value['review_model'] = 'gpt-5.6-sol'
            elif change == 'primary_model':
                value['model_config']['model'] = 'gpt-6-astra'
            else:
                value['model_config']['model_routing']['role_models']['verifier'] = 'gpt-5.6-sol'
            path.write_text(json.dumps(value))
            with self.subTest(change=change), self.assertRaises(ValueError):
                M.driver_artifacts(self.contract, self.process())
        path.write_text(json.dumps(manifest))
        launch_path = self.output / 'seed_1001.launch.json'
        launch = M.read(launch_path)
        launch['command'][-2:] = ['--ensemble-review-model', 'gpt-6-astra']
        launch_path.write_text(json.dumps(launch))
        with self.assertRaises(ValueError):
            M.driver_artifacts(self.contract, self.process())

    def test_role_config_missing_lock_or_partial_snapshot_cannot_confirm_start(self):
        manifest, config_path = self.role_artifacts()
        config_bytes = config_path.read_bytes()
        config_path.write_text('{"model":')
        self.assertIsNone(M.driver_artifacts(self.contract, self.process())['confirmed'])
        config_path.write_bytes(config_bytes)
        manifest['execution_hashes'] = {}
        (self.output / 'robustness_manifest.json').write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            M.driver_artifacts(self.contract, self.process())

    def test_prepare_exact_argv_all_copytree_files_and_no_process(self):
        with mock.patch.object(M.subprocess, 'Popen') as spawn, mock.patch.object(M, 'query') as query:
            root, plan, contract = self.prepared()
        self.assertEqual(contract['argv'], self.contract['argv'])
        self.assertEqual(len(contract['input_hashes']), 25)
        self.assertEqual(plan['max_seconds'], 21600)
        self.assertFalse(self.output.exists())
        spawn.assert_not_called()
        query.assert_not_called()
        self.assertEqual(M.sha(root / M.SELF_NAME), M.sha(SOURCE))

    def test_duplicate_launch_and_output_reservation_refused(self):
        self.prepared()
        with self.assertRaises(FileExistsError):
            M.prepare(self.control, self.contract_path, M.MAX_SECONDS)
        with self.assertRaises(FileExistsError):
            M.prepare(self.base / 'other_control', self.contract_path, M.MAX_SECONDS)

    def test_wrong_or_implicit_condition_rejected(self):
        cases = [self.contract['argv'] + ['--model', 'gpt-5.6-sol'],
                 self.contract['argv'] + ['--resume'], self.contract['argv'][:-2]]
        for key, value in [('--seeds', '404'), ('--parallel-repeats', '1'), ('--closure-rounds', '4'),
                           ('--model', 'gpt-6-astra'), ('--reasoning-effort', 'medium'),
                           ('--identity-review-policy', 'legacy'), ('--revision-output-policy', 'canonical')]:
            row = list(self.contract['argv'])
            row[row.index(key) + 1] = value
            cases.append(row)
        row = list(self.contract['argv'])
        row[row.index('--seeds') + 2] = '707'
        cases.append(row)
        row = list(self.contract['argv'])
        row[2] = str(self.base / 'run_frozen_batch.py')
        cases.append(row)
        for argv in cases:
            with self.subTest(argv=argv), self.assertRaises((ValueError, IndexError)):
                M.parse_argv(argv)

    def test_old_output_wrong_cap_and_pinned_binary_rejected(self):
        self.output.mkdir()
        with self.assertRaises(FileExistsError):
            M.prepare(self.control, self.contract_path, M.MAX_SECONDS)
        self.output.rmdir()
        with self.assertRaises(ValueError):
            M.prepare(self.control, self.contract_path, 86400)
        self.binary.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            M.prepare(self.control, self.contract_path, M.MAX_SECONDS)
        self.assertFalse(self.control.exists())

    def test_complete_hash_sets_and_content_drift(self):
        for key in ('source_hashes', 'input_hashes'):
            value = copy.deepcopy(self.contract)
            value[key].pop(next(iter(value[key])))
            with self.subTest(key=key), self.assertRaises(ValueError):
                M.validate_contract(value)
        path = self.workspace / 'EECBench/scripts/extra.py'
        path.write_text('new source')
        with self.assertRaises(ValueError):
            M.validate_contract(self.contract)
        path.unlink()
        path = self.inputs / M.SHOTS[0] / 'input_bundle/extra/nested.bin'
        path.write_bytes(b'changed extra input')
        with self.assertRaises(ValueError):
            M.validate_contract(self.contract)

    def test_symlinked_shot_parent_and_unlocked_empty_directory_rejected(self):
        shot = self.inputs / M.SHOTS[1]
        actual = self.base / 'elsewhere'
        shot.rename(actual)
        shot.symlink_to(actual, target_is_directory=True)
        with self.assertRaises(ValueError):
            M.regular_files(self.inputs)
        shot.unlink()
        actual.rename(shot)
        (shot / 'input_bundle/empty').mkdir()
        with self.assertRaises(ValueError):
            M.regular_files(self.inputs)

    def test_overlapping_control_rejected_before_frozen_writes(self):
        before = copy.deepcopy(self.contract)
        for root in (self.workspace / 'nested', self.inputs / M.SHOTS[0] / 'input_bundle/control', self.base / 'package'):
            with self.subTest(root=root), self.assertRaises(ValueError):
                M.prepare(root, self.contract_path, M.MAX_SECONDS)
        self.assertEqual({str(p.relative_to(self.workspace)): M.sha(p) for p in M.source_files(self.workspace)}, before['source_hashes'])
        self.assertEqual({str(p.relative_to(self.inputs)): M.sha(p) for p in M.regular_files(self.inputs)}, before['input_hashes'])

    def test_strict_json_and_atomic_exclusive_publish(self):
        for raw in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}'):
            self.contract_path.write_text(raw)
            with self.assertRaises(ValueError):
                M.read(self.contract_path)
        path = self.base / 'atomic.json'
        M.write_new(path, {'old': 1})
        with self.assertRaises(FileExistsError):
            M.write_new(path, {'new': 2})
        self.assertEqual(M.read(path), {'old': 1})
        self.assertFalse(list(self.base.glob('*.tmp')))

    def test_plan_and_contract_drift_rejected(self):
        root, _, _ = self.prepared()
        (root / 'contract.json').write_text('{}')
        with self.assertRaises(ValueError):
            M.load(root)

    def test_slurm_command_and_remaining_lifetime(self):
        root, plan, _ = self.prepared()
        command = M.srun_command(root, plan)
        self.assertIn('--gres=none', command)
        self.assertIn('--time=06:00:00', command)
        self.assertEqual(command[-6:], M.phase_argv(root, '_entry'))
        result = {'returncode': 0, 'stdout': f'JobId={M.JOB} UserId=guangyi.chen({M.UID}) JobState=RUNNING NodeList={M.NODE} TimeLimit=12:00:00 RunTime=07:00:00'}
        with mock.patch.object(M.os, 'getuid', return_value=M.UID), mock.patch.object(M.socket, 'gethostname', return_value=M.NODE), mock.patch.object(M, 'query', return_value=result):
            with self.assertRaises(ValueError):
                M.node_check(plan, starting=True)

    def test_start_claim_is_consumed_once(self):
        root, _, _ = self.node()
        with mock.patch.object(M, 'identity', return_value=self.process()), mock.patch.object(M, 'query', return_value={'returncode': 0}) as query:
            M.node_start(root)
            with self.assertRaises(FileExistsError):
                M.node_start(root)
        self.assertEqual(query.call_count, 1)
        self.assertEqual(query.call_args.args[0][0], 'tmux')

    def test_entry_exec_is_exact_and_metadata_is_before_exec_only(self):
        root, _, _ = self.node()
        current = self.process(M.phase_argv(root, '_entry'))
        with mock.patch.object(M, 'identity', return_value=current), mock.patch.object(M, 'memory', return_value=[]), mock.patch.dict(M.os.environ, {'SLURM_JOB_ID': M.JOB, 'SLURM_STEP_ID': '99'}), mock.patch.object(M.os, 'chdir'), mock.patch.object(M.os, 'execv', side_effect=OSError('synthetic exec failure')) as execute:
            with self.assertRaises(OSError):
                M.entry(root)
        execute.assert_called_once_with(M.PYTHON, self.contract['argv'])
        saved = M.read(root / 'task_identity.json')
        self.assertEqual(saved['entry_process']['argv'], M.phase_argv(root, '_entry'))
        self.assertTrue(saved['driver_start_not_yet_confirmed'])
        self.assertFalse(M.read(root / 'exec_failure.json')['driver_started'])

    def test_before_exec_and_driver_without_artifacts_are_not_confirmed_start(self):
        root, _, _ = self.node()
        self.task(root)
        with mock.patch.object(M, 'query', return_value={'returncode': 0}), mock.patch.object(M, 'identity', return_value=self.process(M.phase_argv(root, '_entry'))):
            value = M.node_status(root)
            self.assertFalse(value['driver_process_observed'])
            self.assertFalse(value['driver_started_confirmed_now'])
        with mock.patch.object(M, 'query', return_value={'returncode': 0}), mock.patch.object(M, 'identity', return_value=self.process()):
            value = M.node_status(root)
            self.assertTrue(value['driver_process_observed'])
            self.assertFalse(value['driver_started_confirmed_now'])

    def test_started_requires_matching_driver_manifest_and_seed_log(self):
        root, _, _ = self.node()
        self.task(root)
        self.output.mkdir()
        M.write_new(self.output / 'robustness_manifest.json', self.matching_manifest())
        M.write_new(self.output / 'seed_707.launch.json', {'pid': 8888, 'seed': 707})
        (self.output / 'seed_707.log').write_text('detector started\n')
        with mock.patch.object(M, 'query', return_value={'returncode': 0}), mock.patch.object(M, 'identity', return_value=self.process()):
            value = M.node_status(root)
            self.assertTrue(value['driver_started_confirmed_now'])
            self.assertIsNone(value['total_model_usage'])
            manifest = self.matching_manifest()
            manifest['model'] = 'different'
            (self.output / 'robustness_manifest.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                M.node_status(root)

    def test_partial_manifest_is_unknown_not_dead_or_restart(self):
        root, _, _ = self.node()
        self.task(root)
        self.output.mkdir()
        (self.output / 'robustness_manifest.json').write_text('{"status":')
        with mock.patch.object(M, 'query', return_value={'returncode': 0}) as query, mock.patch.object(M, 'identity', return_value=self.process()):
            value = M.node_status(root)
        self.assertEqual(value['status'], 'observation_incomplete')
        self.assertIsNone(value['driver_started_confirmed_now'])
        self.assertTrue(value['driver_process_observed'])
        self.assertEqual(query.call_count, 1)

    def test_stop_failure_is_durable_nonzero_and_never_widened(self):
        root, plan, _ = self.node()
        self.task(root)
        # Stopping an authenticated running step must not require source files to remain unchanged.
        (self.workspace / 'EECBench/scripts/runtime.py').write_text('drift after start')
        result = {'returncode': 0, 'stdout': f'StepId={M.JOB}.99 UserId={M.UID} NodeList={M.NODE} Name=eec-batch-{plan["run_id"][:12]}'}
        with mock.patch.object(M, 'identity', return_value=self.process()), mock.patch.object(M, 'query', side_effect=[result, {'returncode': 7, 'stderr': 'denied'}]) as query:
            value = M.node_stop(root)
        self.assertEqual(value['status'], 'exact_step_stop_failed')
        self.assertEqual(value['returncode'], 7)
        self.assertEqual(M.read(root / 'stop_result.json')['returncode'], 7)
        self.assertEqual(query.call_args.args[0], ['scancel', M.JOB + '.99'])
        self.assertEqual(query.call_count, 2)

    def test_stop_refuses_wrong_process_birth_owner_argv_or_cgroup(self):
        root, _, _ = self.node()
        self.task(root)
        for key, value in [('pid', 12), ('uid', 1000), ('start_ticks', 1), ('argv', ['/bin/other']), ('cgroup', '0::/another')]:
            current = {**self.process(), key: value}
            with self.subTest(key=key), mock.patch.object(M, 'identity', return_value=current), mock.patch.object(M, 'query') as query:
                with self.assertRaises(ValueError):
                    M.node_stop(root)
                query.assert_not_called()
        self.assertFalse((root / 'stop.claim.json').exists())

    def test_stop_refuses_slurm_step_identity_mismatch(self):
        root, _, _ = self.node()
        self.task(root)
        with mock.patch.object(M, 'identity', return_value=self.process()), mock.patch.object(M, 'query', return_value={'returncode': 0, 'stdout': 'StepId=175467.98 UserId=2012'}) as query:
            with self.assertRaises(ValueError):
                M.node_stop(root)
        self.assertEqual(query.call_count, 1)
        self.assertFalse((root / 'stop.claim.json').exists())

    def test_controller_postspawn_identity_failure_still_reaps_known_child(self):
        root, _, _ = self.node()
        child = mock.Mock(pid=123, wait=mock.Mock(return_value=0))
        with mock.patch.object(M, 'identity', side_effect=[self.process(), FileNotFoundError('short-lived child')]), mock.patch.object(M.subprocess, 'Popen', return_value=child):
            value = M.controller(root)
        child.wait.assert_called_once_with(timeout=M.MAX_SECONDS + 120)
        child.terminate.assert_not_called()
        self.assertEqual(value['srun_returncode'], 0)
        self.assertEqual(value['returncode'], 1)
        self.assertEqual(value['status'], 'incomplete')
        self.assertEqual(M.read(root / 'controller_exit.json')['errors'][0]['phase'], 'post_spawn_identity')

    def test_controller_exit_write_failure_preserves_known_exit_in_binary_stderr(self):
        root, _, _ = self.node()
        child = mock.Mock(pid=123, wait=mock.Mock(return_value=0))
        original = M.write_new

        def fail_exit(path, value):
            if Path(path).name == 'controller_exit.json':
                raise OSError('injected storage failure')
            original(path, value)

        with mock.patch.object(M, 'identity', return_value=self.process()), mock.patch.object(M.subprocess, 'Popen', return_value=child), mock.patch.object(M, 'write_new', side_effect=fail_exit):
            value = M.controller(root)
        self.assertEqual(value['returncode'], 1)
        self.assertEqual(value['srun_returncode'], 0)
        fallback = M.read(root / 'srun.stderr')
        self.assertEqual(fallback['srun_returncode'], 0)
        self.assertEqual(fallback['errors'][0]['phase'], 'exit_persistence')

    def test_controller_spawn_failure_known_false_not_model_zero(self):
        root, _, _ = self.node()
        with mock.patch.object(M, 'identity', return_value=self.process()), mock.patch.object(M.subprocess, 'Popen', side_effect=OSError('no srun')):
            value = M.controller(root)
        self.assertFalse(value['srun_subprocess_started'])
        self.assertIsNone(value['srun_returncode'])
        self.assertIsNone(value['total_model_usage'])
        self.assertEqual(value['returncode'], 1)
        self.assertEqual(M.read(root / 'controller_exit.json')['errors'][0]['phase'], 'spawn')

    def test_controller_timeout_only_manages_own_popen_child(self):
        root, _, _ = self.node()
        child = mock.Mock(pid=123, wait=mock.Mock(side_effect=[subprocess.TimeoutExpired('srun', 1), subprocess.TimeoutExpired('srun', 1), -9]))
        with mock.patch.object(M, 'identity', return_value=self.process()), mock.patch.object(M.subprocess, 'Popen', return_value=child), mock.patch.object(M, 'query') as query:
            value = M.controller(root)
        child.terminate.assert_called_once_with()
        child.kill.assert_called_once_with()
        self.assertEqual(child.wait.call_count, 3)
        query.assert_not_called()
        self.assertEqual(value['srun_returncode'], -9)
        self.assertEqual(value['returncode'], 1)
        self.assertIsNone(value['total_model_usage'])


if __name__ == '__main__':
    unittest.main()
