"""Actual local CLI request routing and failure accounting, without any API."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ensemble_shot_entity_detection as E  # noqa: E402
import role_model_routing as R  # noqa: E402


FAKE = '''
import json, pathlib, sys, time
task = json.loads(sys.stdin.read())
out = pathlib.Path(sys.argv[sys.argv.index('--output-last-message') + 1])
(out.parent / (out.stem + '.received.json')).write_text(json.dumps(sys.argv[1:]))
print(json.dumps({'type':'thread.started','thread_id':task.get('thread','initial-thread')}), flush=True)
print(json.dumps({'type':'turn.completed','usage':{'input_tokens':11,'cached_input_tokens':3,'output_tokens':7}}), flush=True)
if task.get('timeout'): time.sleep(5)
out.write_text('invalid' if task.get('invalid') else '{}')
sys.exit(17 if task.get('nonzero') else 0)
'''


class RoleModelTransportTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.cli = self.root / 'fake codex'
        self.cli.write_text('#!' + sys.executable + '\n' + FAKE)
        self.cli.chmod(0o755)
        self.schema = self.root / 'schema.json'
        self.schema.write_text('{}')
        self.image = self.root / 'frame.png'
        self.image.write_bytes(b'fixed image bytes not decoded by fake CLI')
        self.routing = R.resolve_model_routing('primary-test', 'review-test')

    def args(self, role='detector', role_id='detector_1', attempt=1, *, binding=None, task=None):
        stem = role_id if role in ('adjudicator_initial', 'adjudicator_revision') and attempt == 1 else f'{role_id}.attempt{attempt}'
        c = R.request_context(self.routing, role=role, role_id=role_id, attempt=attempt,
                              shot_id='synthetic', initial_request=binding)
        return dict(prompt=json.dumps(task or {}), attachments=[self.image], schema_path=self.schema,
                    output_path=self.root / (stem + '.json'),
                    events_path=self.root / (stem + '.events.jsonl'),
                    stderr_path=self.root / (stem + '.stderr.log'), codex_bin=str(self.cli),
                    model=c['requested_model'], timeout_sec=2, work_dir=self.root,
                    persistent=role == 'adjudicator_initial',
                    resume_thread_id=None if binding is None else binding['thread_id'],
                    request_context=c)

    def account(self, args, invocation=None, error=None):
        return E._codex_attempt_accounting(invocation=invocation, error=error,
                                         events_path=args['events_path'], request_context=args['request_context'])

    def initial(self):
        args = self.args('adjudicator_initial', 'adjudicator_initial')
        call = E.run_codex_json(**args)
        path = R.request_path(args['events_path'])
        return {'path': str(path), 'sha256': R.file_hash(path), 'thread_id': call.thread_id}

    def test_inheritance_and_role_map(self):
        self.assertIsNone(R.resolve_model_routing(None))
        self.assertIsNone(R.resolve_model_routing('legacy'))
        self.assertEqual(R.request_kwargs(None), {})
        for role, group in R.ROLE_GROUPS.items():
            self.assertEqual(self.routing['role_models'][role], group + '-test')
        self.assertIsNone(R.resolve_model_routing(None, 'review')['role_models']['detector'])
        for bad in ('', ' ', True, 7):
            with self.assertRaises(ValueError):
                R.resolve_model_routing('primary', bad)

    def test_actual_fresh_and_resume_argv_matches_private_sidecars(self):
        binding = self.initial()
        for args in [self.args(), self.args('adjudicator_revision', 'adjudicator_revision', binding=binding),
                     self.args('adjudicator_revision', 'adjudicator_revision', 2, binding=binding)]:
            invocation = E.run_codex_json(**args)
            request = json.loads(R.request_path(args['events_path']).read_text())
            received = json.loads(args['output_path'].with_name(args['output_path'].stem + '.received.json').read_text())
            self.assertEqual(request['argv'], [str(self.cli), *received])
            self.assertEqual(received[received.index('--model') + 1], args['model'])
            self.assertEqual(request['prompt_sha256'], __import__('hashlib').sha256(args['prompt'].encode()).hexdigest())
            self.assertEqual(request['attachments'][0]['sha256'], R.file_hash(self.image))
            self.assertEqual(self.account(args, invocation)['model_request']['status'], 'persisted')
            self.assertNotIn('model_group', args['prompt'])
        self.assertEqual(request['initial_request'], binding)
        self.assertEqual(request['argv'][1:3], ['exec', 'resume'])

    def test_default_none_has_no_model_switch_or_sidecar(self):
        args = self.args()
        args.pop('request_context')
        args['model'] = None
        E.run_codex_json(**args)
        received = json.loads(self.root.joinpath('detector_1.attempt1.received.json').read_text())
        self.assertNotIn('--model', received)
        self.assertFalse(R.request_path(args['events_path']).exists())

    def test_wrong_model_or_initial_binding_prevents_spawn(self):
        binding = self.initial()
        for mode in ('wrong_model', 'wrong_thread', 'changed_initial_model', 'changed_hash'):
            with self.subTest(mode=mode):
                current = copy.deepcopy(binding)
                args = self.args('adjudicator_revision', 'adjudicator_revision', binding=current)
                if mode == 'wrong_model':
                    args['model'] = 'primary-test'
                elif mode == 'wrong_thread':
                    args['resume_thread_id'] = 'foreign'
                elif mode == 'changed_hash':
                    args['request_context']['initial_request']['sha256'] = '0' * 64
                else:
                    origin = json.loads(Path(binding['path']).read_text())
                    origin['requested_model'] = 'foreign-model'
                    Path(binding['path']).write_text(json.dumps(origin))
                    args['request_context']['initial_request']['sha256'] = R.file_hash(binding['path'])
                with mock.patch.object(E.subprocess, 'Popen') as spawn:
                    with self.assertRaises(E.EnsembleError):
                        E.run_codex_json(**args)
                    spawn.assert_not_called()

    def test_request_write_failure_does_not_start_or_invent_usage(self):
        args = self.args()
        with mock.patch.object(E, '_atomic_write_json', side_effect=OSError('sidecar refused')):
            with mock.patch.object(E.subprocess, 'Popen') as spawn:
                with self.assertRaises(E.EnsembleError) as caught:
                    E.run_codex_json(**args)
                spawn.assert_not_called()
        row = self.account(args, error=caught.exception)
        self.assertIs(row['subprocess_started'], False)
        self.assertIsNone(row['token_usage'])
        self.assertEqual(row['model_request']['status'], 'not_materialized')

    def test_spawn_false_unknown_and_paid_failures_keep_model_attribution(self):
        args = self.args()
        with mock.patch.object(E.subprocess, 'Popen', side_effect=OSError('spawn refused')):
            with self.assertRaises(E.CodexCallError) as caught:
                E.run_codex_json(**args)
        row = self.account(args, error=caught.exception)
        self.assertIs(row['subprocess_started'], False)
        self.assertIsNone(row['token_usage'])
        self.assertEqual(row['requested_model'], 'primary-test')
        self.assertEqual(row['model_request']['status'], 'persisted')
        unknown = E.CodexCallError('unknown', failure_kind='subprocess_error', runtime_seconds=.1,
                                 token_usage=None, thread_id=None, returncode=None, subprocess_started=None)
        self.assertTrue(self.account(args, error=unknown)['subprocess_start_unknown'])
        for task, kind in [({'invalid': True}, 'invalid_json'), ({'nonzero': True}, 'nonzero_exit'),
                           ({'timeout': True}, 'timeout')]:
            args = self.args('verifier', 'verifier_1', task=task)
            if task.get('timeout'):
                args['timeout_sec'] = .2
            with self.assertRaises(E.CodexCallError) as caught:
                E.run_codex_json(**args)
            row = self.account(args, error=caught.exception)
            self.assertEqual(row['failure_kind'], kind)
            self.assertEqual(row['requested_model'], 'review-test')
            self.assertEqual(row['token_usage']['total_tokens'], 18)
            self.assertIs(row['subprocess_started'], True)

    def test_returned_resume_thread_mismatch_preserves_native_usage(self):
        binding = self.initial()
        args = self.args('adjudicator_revision', 'adjudicator_revision', binding=binding,
                         task={'thread': 'different-returned-thread'})
        with self.assertRaises(E.CodexCallError) as caught:
            E.run_codex_json(**args)
        row = self.account(args, error=caught.exception)
        self.assertEqual(row['failure_kind'], 'thread_mismatch')
        self.assertEqual(row['thread_id'], 'different-returned-thread')
        self.assertEqual(row['token_usage']['total_tokens'], 18)
        self.assertEqual(row['requested_model'], 'review-test')

    def test_post_call_validation_failure_keeps_paid_usage(self):
        args = self.args()
        call = E.run_codex_json(**args)
        row = self.account(args, call, E.EnsembleError('synthetic schema failure'))
        self.assertEqual(row['failure_kind'], 'python_validation')
        self.assertEqual(row['token_usage']['total_tokens'], 18)
        self.assertEqual(row['model_request']['sha256'], R.file_hash(R.request_path(args['events_path'])))


if __name__ == '__main__':
    unittest.main()
