"""Exercise opt-in routing through existing nonempty pipeline/stage fixtures."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import test_physical_identity_pipeline as F
import test_revision_wire_pipeline as W
import test_granularity_family_ablation as G
import test_accepted_compact_assembly_integration as A
import test_detector_closure_stage as C
import role_model_routing as R
import replay_ensemble_entity_detection as REPLAY
import run_prompt_unbound_prefilter as PREFILTER

E = F.ENSEMBLE


class RoleModelPipelineTests(unittest.TestCase):
    def run_fixture(self, *, review='review-test', primary='primary-test', corruption=None,
                    wire=False, closure=False):
        fixture = W.RevisionWirePipelineTests() if wire else F.PhysicalIdentityPipelineTest()
        self.addCleanup(fixture.doCleanups)
        original = E.run_ensemble_detection
        captured = []
        stage_calls = []

        def run(**kwargs):
            invoke = E.run_codex_json.side_effect

            def capture(**call):
                captured.append(copy.deepcopy(call))
                # The fixture replaces transport; persist its private declaration
                # so real initial->revision lineage still has an immutable anchor.
                context = call.get('request_context')
                if context is not None:
                    path = R.request_path(call['events_path'])
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps({'policy_version': R.REQUEST_VERSION, **context,
                        'persistent': call.get('persistent', False),
                        'resume_thread_id': call.get('resume_thread_id')}))
                if context is not None and context['role'] == 'detector_closure':
                    source = json.loads((call['output_path'].parent / 'input_ledger.json').read_text())
                    payload = C.delta(source)
                    payload['shot_id'] = 'synthetic'
                    coverage = payload['coverage_audit']
                    coverage['reviewed_frame_ids'] = [10]
                    coverage['frame_cell_checks'] = [r for r in coverage['frame_cell_checks'] if r['frame_id'] == 10]
                    coverage['endpoint_checks'][1]['frame_id'] = 10
                    coverage['temporal_checks'] = []
                    call['output_path'].write_text(json.dumps(payload))
                    call['events_path'].write_text(json.dumps({'type': 'turn.completed', 'usage': F.USAGE}) + '\n')
                    call['stderr_path'].write_text('')
                    return E.CodexInvocation(payload, copy.deepcopy(F.USAGE), 'closure-thread', .01)
                return invoke(**call)

            kwargs['model'] = primary
            if review is not None:
                kwargs['review_model'] = review
            if closure:
                kwargs['detector_closure_max_rounds'] = 1
            with contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(E, 'run_codex_json', side_effect=capture))
                for owner, name in ((E, 'run_group_member_family_stage'),
                                    (E, 'run_accepted_compact_assembly_stage'),
                                    (E.detector_closure_stage, 'run_stage')):
                    original_stage = getattr(owner, name)

                    def captured_stage(*, _original=original_stage, _name=name, **stage_kwargs):
                        stage_calls.append((_name, stage_kwargs))
                        return _original(**stage_kwargs)

                    stack.enter_context(mock.patch.object(owner, name, side_effect=captured_stage))
                return original(**kwargs)

        with mock.patch.object(E, 'run_ensemble_detection', side_effect=run):
            value = (fixture.run_pipeline(failures=('adjudicator_revision',)) if wire
                     else fixture.run_pipeline(corruption))
        self.stage_calls = stage_calls
        return value, captured

    def test_nonempty_initial_verifier_revision_and_matcher_route_and_keep_failures(self):
        (result, manifest, _, _), calls = self.run_fixture(corruption='verifier_null_comparison', closure=True)
        self.assertEqual(manifest['status'], 'success')
        self.assertTrue(result.semantics['entities'])
        self.assertEqual(manifest['model_routing'], R.resolve_model_routing('primary-test', 'review-test'))
        self.assertEqual(len([c for c in calls if c['request_context']['role'] == 'detector']), 4)
        self.assertEqual(len([c for c in calls if c['request_context']['role'] == 'detector_closure']), 4)
        self.assertEqual(len([c for c in calls if c['request_context']['role'] == 'verifier']), 3)
        stages = dict(self.stage_calls)
        for name in ('run_group_member_family_stage', 'run_accepted_compact_assembly_stage'):
            self.assertEqual(stages[name]['model'], 'review-test')
            self.assertEqual(stages[name]['model_routing'], manifest['model_routing'])
        self.assertEqual(stages['run_stage']['invocation_kwargs']['model'], 'primary-test')
        self.assertEqual(stages['run_stage']['request_context_factory']('detector_1', 1, 1),
                         R.request_context(manifest['model_routing'], role='detector_closure',
                                           role_id='detector_1', round_index=1, attempt=1, shot_id='synthetic'))
        for call in calls:
            role = call['request_context']['role']
            self.assertEqual(call['model'], R.ROLE_GROUPS[role] + '-test')
            self.assertNotIn('review-test', call['prompt'])
            self.assertNotIn('primary-test', call['prompt'])
        revision = next(c for c in calls if c['request_context']['role'] == 'adjudicator_revision')
        self.assertEqual(revision['resume_thread_id'], 'synthetic_thread')
        self.assertEqual(revision['request_context']['initial_request']['thread_id'], 'synthetic_thread')
        failed = [r for r in manifest['verifier_attempts'] if r['status'] == 'failed']
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]['requested_model'], 'review-test')
        self.assertEqual(failed[0]['token_usage'], F.USAGE)

    def test_nonempty_wire_revision_repair_stays_on_review_and_initial_thread(self):
        (_, manifest, _, _), calls = self.run_fixture(wire=True)
        revisions = [c for c in calls if c['request_context']['role'] == 'adjudicator_revision']
        self.assertEqual(len(revisions), 2)
        self.assertEqual([r['status'] for r in manifest['adjudicator_revision_attempts']], ['failed', 'success'])
        for c in revisions:
            self.assertEqual(c['model'], 'review-test')
            self.assertEqual(c['resume_thread_id'], 'synthetic_thread')
            self.assertEqual(c['schema_path'], W.W.SCHEMA_PATH)
        self.assertTrue(all(r['token_usage'] == F.USAGE for r in manifest['adjudicator_revision_attempts']))

    def test_default_none_and_explicit_equal_preserve_request_models(self):
        (_, manifest, _, _), calls = self.run_fixture(review=None, primary=None)
        self.assertNotIn('model_routing', manifest)
        self.assertTrue(all(c['model'] is None and 'request_context' not in c for c in calls))
        (_, equal_manifest, _, _), equal_calls = self.run_fixture(review='primary-test')
        self.assertTrue(all(c['model'] == 'primary-test' for c in equal_calls))
        self.assertEqual(manifest['token_usage'], equal_manifest['token_usage'])

    def test_real_group_and_accepted_planner_calls_with_existing_nonempty_candidate_fixtures(self):
        routing = R.resolve_model_routing('primary-test', 'review-test')
        methods = [
            (G.GranularityFamilyConsensusIntegrationTest,
             'test_two_planners_are_identical_input_isolated_and_consensus_gated',
             'run_group_member_family_stage'),
            (A.AcceptedCompactAssemblyHelperIntegrationTests,
             'test_two_planners_are_input_identical_isolated_and_fully_accounted',
             'run_accepted_compact_assembly_stage'),
            (A.AcceptedCompactAssemblyHelperIntegrationTests,
             'test_failed_planner_returns_complete_attempt_and_usage_ledger',
             'run_accepted_compact_assembly_stage'),
        ]
        for cls, method, name in methods:
            with self.subTest(method=method):
                fixture = cls(method)
                original = getattr(E, name)
                calls = []

                def routed(**kwargs):
                    invoke = E.run_codex_json.side_effect

                    def capture(**call):
                        calls.append(call)
                        return invoke(**call)

                    with mock.patch.object(E, 'run_codex_json', side_effect=capture):
                        return original(**{**kwargs, 'model': 'review-test', 'model_routing': routing})

                with mock.patch.object(E, name, side_effect=routed), contextlib.redirect_stdout(io.StringIO()):
                    getattr(fixture, method)()
                self.assertGreaterEqual(len(calls), 2)
                self.assertTrue(all(c['model'] == 'review-test' for c in calls))
                self.assertTrue(all(c['request_context']['model_group'] == 'review' for c in calls))
                self.assertTrue(all('review-test' not in c['prompt'] for c in calls))

    def test_all_four_closure_sources_and_retry_keep_primary_without_new_votes(self):
        routing = R.resolve_model_routing('primary-test', 'review-test')
        calls = []

        def invoke(**kwargs):
            calls.append(kwargs)
            context = kwargs['request_context']
            source = json.loads((kwargs['output_path'].parent / 'input_ledger.json').read_text())
            payload = C.delta(source)
            if context['role_id'] == 'detector_2' and context['attempt'] == 1:
                payload['coverage_audit']['frame_cell_checks'].pop()
            return E.CodexInvocation(payload, F.USAGE, 'closure-thread', .01)

        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            out = C.STAGE.run_stage(
                ledgers=[C.ledger(f'detector_{i}') for i in range(1, 5)], shot_id='shot1',
                valid_frame_ids=C.FRAMES, allowed_input_paths=C.PATHS, attachments=[Path(x) for x in C.PATHS],
                detector_policy_text='Fixed policy', shot_manifest={}, run_dir=Path(tmp),
                max_rounds=1, max_workers=1, invoke_json=invoke, validate_ledger=E.validate_ledger,
                invocation_kwargs={'model': 'primary-test'}, account_attempt=E._codex_attempt_accounting,
                request_context_factory=lambda source, round_index, attempt: R.request_context(
                    routing, role='detector_closure', role_id=source, round_index=round_index,
                    attempt=attempt, shot_id='shot1'),
            )
        self.assertEqual(len(calls), 5)
        self.assertEqual(out['source_count_after'], 4)
        self.assertTrue(all(c['model'] == c['request_context']['requested_model'] == 'primary-test' for c in calls))
        self.assertEqual(sum(r['status'] == 'failed' for r in out['attempts']), 1)
        self.assertTrue(all(r['token_usage'] == F.USAGE for r in out['attempts']))

    def test_replay_passes_option_and_keeps_terminal_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / 'out'
            calls = []

            def run(**kwargs):
                calls.append(kwargs)
                return SimpleNamespace(run_dir=kwargs['run_dir'], semantics={'entities': []},
                                       runtime_seconds=0, token_usage=None)

            argv = ['replay', str(root), '--output-root', str(out), '--codex-model', 'primary-test',
                    '--codex-review-model', 'review-test']
            with mock.patch('sys.argv', argv), mock.patch.object(REPLAY, '_shot_dirs', return_value=[root/'a']), \
                    mock.patch.object(REPLAY, '_load_replay_input', return_value=(None, [])), \
                    mock.patch.object(REPLAY, 'run_ensemble_detection', side_effect=run), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(REPLAY.main(), 0)
            self.assertEqual(calls[0]['review_model'], 'review-test')
            self.assertEqual(json.loads((out/'replay_manifest.json').read_text())['model_routing'],
                             R.resolve_model_routing('primary-test', 'review-test'))

    def test_prefilter_single_rejects_review_before_input_or_model_work(self):
        with mock.patch.object(PREFILTER.episode_graphs, 'discover_shots') as discover:
            with self.assertRaisesRegex(ValueError, 'requires.*ensemble'):
                PREFILTER.main(['/nonexistent', '--codex-review-model', 'review-test'])
            discover.assert_not_called()


if __name__ == '__main__':
    unittest.main()
