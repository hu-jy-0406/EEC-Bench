import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


PATH = Path(__file__).resolve().parents[1] / 'experiments/study_inconsistent_2/entity_discovery_iterations/owned_allocation_fake_launcher.py'
SPEC = importlib.util.spec_from_file_location('owned_fake_launcher_test', PATH)
L = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(L)


class FakeLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'control with spaces'
        L.prepare(self.root)
        self.root, self.plan = L.load_plan(self.root)

    def rewrite_plan(self, value):
        (self.root / 'plan.json').write_text(json.dumps(value))
        (self.root / 'plan.sha256').write_text(L.digest(self.root / 'plan.json'))

    def identity(self):
        current = {'pid': 1234, 'uid': 2012, 'start_ticks': 888,
                   'argv': self.plan['task_argv'],
                   'cgroup': '0::/system.slice/slurmstepd.scope/job_175467/step_123/user/task_0'}
        saved = {'host': L.NODE, 'job_id': L.JOB, 'step_id': '123',
                 'process': copy.deepcopy(current),
                 'plan_sha256': L.digest(self.root / 'plan.json')}
        return saved, current

    def test_reject_arbitrary_argv_model_mode_or_budget_even_with_rehashed_plan(self):
        changes = [dict(task_argv=['codex', 'exec']), dict(mode='model'),
                   dict(max_fake_seconds=61), dict(max_fake_seconds=True),
                   dict(model_invocations=1), dict(automatic_restart=True), dict(extra='field')]
        for update in changes:
            with self.subTest(update=update):
                value = {**self.plan, **update}
                self.rewrite_plan(value)
                with self.assertRaises(ValueError):
                    L.load_plan(self.root)

    def test_source_or_plan_lock_drift_rejected(self):
        (self.root / L.SOURCE_NAME).write_text('raise SystemExit(0)\n')
        with self.assertRaises(ValueError):
            L.load_plan(self.root)
        (self.root / L.SOURCE_NAME).write_bytes(PATH.read_bytes())
        (self.root / 'plan.sha256').write_text('0' * 64)
        with self.assertRaises(ValueError):
            L.load_plan(self.root)

    def test_duplicate_keys_nonfinite_and_extra_header_rejected(self):
        for text in ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}']:
            with self.subTest(text=text):
                (self.root / 'bad.json').write_text(text)
                with self.assertRaises(ValueError):
                    L.read_json(self.root / 'bad.json')

    def test_internal_node_phases_reject_working_source_execution(self):
        with self.assertRaisesRegex(ValueError, 'frozen helper'):
            L.load_plan(self.root, require_frozen=True)

    def test_prepare_and_launch_claim_are_exclusive(self):
        with self.assertRaises(FileExistsError):
            L.prepare(self.root)
        with mock.patch.object(L, 'node_preflight', return_value=(self.root, self.plan, {})), \
                mock.patch.object(L, 'run_read', return_value={'returncode': 0}) as run, \
                mock.patch.object(L, 'proc_identity', return_value={}):
            L.node_launch(self.root)
            with self.assertRaises(FileExistsError):
                L.node_launch(self.root)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][0], 'tmux')

    def test_allocation_owner_state_and_node_must_match(self):
        valid = 'JobId=175467 UserId=guangyi.chen(2012) JobState=RUNNING NodeList=auh7-1b-gpu-289'
        L.verify_allocation_text(valid)
        for old, new in [('175467', '175468'), ('2012', '2013'),
                         ('RUNNING', 'COMPLETED'), ('gpu-289', 'gpu-288')]:
            with self.subTest(old=old), self.assertRaises(ValueError):
                L.verify_allocation_text(valid.replace(old, new))

    def test_cancel_identity_rejects_pid_reuse_other_owner_argv_and_cgroup(self):
        saved, current = self.identity()
        self.assertEqual(L.verify_task_identity(self.plan, saved, current), '175467.123')
        changes = [dict(pid=1235), dict(start_ticks=889), dict(uid=2013),
                   dict(argv=['python', 'unrelated.py']),
                   dict(cgroup=current['cgroup'].replace('step_123', 'step_124'))]
        for update in changes:
            with self.subTest(update=update), self.assertRaises(ValueError):
                L.verify_task_identity(self.plan, saved, {**current, **update})
        for step in ['extern', 'batch', '123;175467', True]:
            with self.subTest(step=step), self.assertRaises(ValueError):
                L.verify_task_identity(self.plan, {**saved, 'step_id': step}, current)

    def test_exact_cancel_only_after_identity_and_step_confirmation(self):
        saved, current = self.identity()
        L.write_new(self.root / 'fake_task_start.json', saved)
        responses = [{'returncode': 0, 'stdout': 'StepId=175467.123 State=RUNNING'},
                     {'returncode': 0, 'stdout': '', 'stderr': ''}]
        with mock.patch.object(L, 'node_preflight', return_value=(self.root, self.plan, {})), \
                mock.patch.object(L, 'proc_identity', return_value=current), \
                mock.patch.object(L, 'run_read', side_effect=responses) as run:
            result = L.node_cancel(self.root)
        self.assertEqual(result['step'], '175467.123')
        self.assertEqual(run.call_args_list[-1].args[0], ['scancel', '175467.123'])
        self.assertEqual(L.read_json(self.root / 'cancel.claim.json')['process'], current)

    def test_cancel_mismatch_never_calls_scancel(self):
        saved, current = self.identity()
        L.write_new(self.root / 'fake_task_start.json', saved)
        with mock.patch.object(L, 'node_preflight', return_value=(self.root, self.plan, {})), \
                mock.patch.object(L, 'proc_identity', return_value={**current, 'start_ticks': 1}), \
                mock.patch.object(L, 'run_read') as run:
            with self.assertRaises(ValueError):
                L.node_cancel(self.root)
        run.assert_not_called()

    def test_cancel_missing_step_never_calls_scancel(self):
        saved, current = self.identity()
        L.write_new(self.root / 'fake_task_start.json', saved)
        with mock.patch.object(L, 'node_preflight', return_value=(self.root, self.plan, {})), \
                mock.patch.object(L, 'proc_identity', return_value=current), \
                mock.patch.object(L, 'run_read', return_value={'returncode': 1, 'stdout': ''}) as run:
            with self.assertRaises(ValueError):
                L.node_cancel(self.root)
        self.assertEqual(run.call_count, 1)
        self.assertFalse((self.root / 'cancel.claim.json').exists())

    def test_fake_term_preserves_heartbeat_and_exit_with_sixty_second_alarm(self):
        _, current = self.identity()
        with mock.patch.object(L, 'load_plan', return_value=(self.root, self.plan)), \
                mock.patch.object(L, 'proc_identity', return_value=current), \
                mock.patch.object(L, 'memory_snapshot', return_value=[]), \
                mock.patch.object(L.socket, 'gethostname', return_value=L.NODE), \
                mock.patch.dict(L.os.environ, SLURM_JOB_ID=L.JOB, SLURM_STEP_ID='123'), \
                mock.patch.object(L.signal, 'signal'), mock.patch.object(L.signal, 'alarm') as alarm, \
                mock.patch.object(L.time, 'sleep', side_effect=SystemExit(143)):
            result = L.fake_task(self.root)
        self.assertEqual(result['returncode'], 143)
        self.assertEqual(alarm.call_args_list, [mock.call(60), mock.call(0)])
        events = (self.root / 'fake_native.events.jsonl').read_text().splitlines()
        self.assertEqual(len(events), 1)
        self.assertEqual(json.loads(events[0])['model_invocations'], 0)
        self.assertEqual(L.read_json(self.root / 'fake_task_exit.json')['returncode'], 143)

    def test_srun_is_fixed_fake_no_gpu_and_has_hard_time_cap(self):
        argv = L.srun_argv(self.root, self.plan)
        self.assertIn('--gres=none', argv)
        self.assertIn('--time=00:01:00', argv)
        self.assertIn('--input=/dev/null', argv)
        self.assertEqual(argv[-len(self.plan['task_argv']):], self.plan['task_argv'])
        self.assertNotIn('--pty', argv)

    def test_stuck_own_srun_controller_is_bounded_without_global_kill(self):
        process = mock.Mock(pid=1234)
        process.wait.side_effect = [subprocess.TimeoutExpired('srun', 90), -15]
        with mock.patch.object(L, 'node_preflight', return_value=(self.root, self.plan, {})), \
                mock.patch.object(L, 'proc_identity', return_value={'cgroup': 'session.scope'}), \
                mock.patch.object(L.subprocess, 'Popen', return_value=process):
            result = L.run_srun(self.root)
        process.terminate.assert_called_once()
        process.kill.assert_not_called()
        self.assertEqual(result['returncode'], -15)
        self.assertTrue((self.root / 'node_controller_exit.json').exists())

    def test_post_spawn_identity_read_or_write_failure_still_reaps_child(self):
        for failure in ('proc_missing', 'identity_write'):
            with self.subTest(failure=failure):
                root = self.root / failure
                L.prepare(root)
                _, plan = L.load_plan(root)
                process = mock.Mock(pid=1234)
                process.wait.return_value = 0
                original_write = L.write_new

                def write(path, value):
                    if failure == 'identity_write' and path.name == 'srun_client_identity.json':
                        raise OSError('injected post-spawn write failure')
                    original_write(path, value)

                def identity(pid):
                    if failure == 'proc_missing' and pid == 1234:
                        raise FileNotFoundError('short-lived own srun child')
                    return {'cgroup': 'session.scope'}

                with mock.patch.object(L, 'node_preflight', return_value=(root, plan, {})), \
                        mock.patch.object(L, 'proc_identity', side_effect=identity), \
                        mock.patch.object(L, 'write_new', side_effect=write), \
                        mock.patch.object(L.subprocess, 'Popen', return_value=process):
                    result = L.run_srun(root)
                process.wait.assert_called_once_with(timeout=90)
                process.terminate.assert_not_called()
                self.assertEqual(result['status'], 'incomplete')
                self.assertEqual(result['srun_returncode'], 0)
                audit = L.read_json(root / 'node_controller_exit.json')
                self.assertEqual(len(audit['post_spawn_errors']), 1)


if __name__ == '__main__':
    unittest.main()
