"""No-model integration checks for a partial, advisory first-revision preview."""

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import test_physical_identity_pipeline as pipeline
import test_physical_identity_review as fixtures
import test_prompt_unbound_pipelines as legacy
import physical_identity_review as identity
import physical_review_obligations as obligations


E = pipeline.ENSEMBLE


class FirstRevisionObligationPreviewTests(unittest.TestCase):
    def run_pipeline(self, corruption=None):
        return pipeline.PhysicalIdentityPipelineTest.run_pipeline(self, corruption)

    def read(self, root, name):
        return json.loads((root / 'adjudication' / name).read_text())

    def assert_accounting(self, manifest, calls):
        self.assertEqual(manifest['status'], 'success')
        self.assertEqual(manifest['token_usage']['total_tokens'], 20 * len(calls))
        self.assertEqual(len(manifest['adjudicator_revision_attempts']), 1)
        self.assertEqual(len([c for c in calls if c.startswith('verifier_')]), 2)

    def test_ready_preview_is_compact_and_preserves_full_original_revision_prefix(self):
        _, manifest, calls, root = self.run_pipeline()
        self.assert_accounting(manifest, calls)
        self.assertEqual(len(calls), 9)
        status = manifest['first_revision_obligation_preview']
        self.assertEqual(status['status'], 'ready')
        self.assertTrue(status['included_in_revision_prompt'])
        checklist = self.read(root, 'first_revision_obligation_checklist.json')
        private = self.read(root, 'first_revision_obligation_preview_provenance.private.json')
        prompt = (root / 'prompts/adjudicator_revision.txt').read_text()
        suffix = '\n\n' + obligations.first_revision_preview_prompt(checklist)
        self.assertTrue(prompt.endswith(suffix))
        original = prompt[:-len(suffix)]
        self.assertEqual(hashlib.sha256(original.encode()).hexdigest(), private['base_revision_prompt_sha256'])
        self.assertEqual(hashlib.sha256(suffix[2:].encode()).hexdigest(), status['supplement_sha256'])
        self.assertIn('not an exhaustive list', suffix)
        self.assertIn('Absence from this checklist does not mean reviewed', suffix)
        self.assertIn('even if proposal\nscope is unchanged', checklist['review_instruction'])
        self.assertFalse(private['preview_gated_candidate_used'])
        self.assertFalse(checklist['has_obligations'])
        self.assertNotIn('PRIVATE_REGISTRY_ONLY_SENTINEL', suffix)
        for key in ('raw_initial', 'prepared_initial', 'split_consensus', 'verification_targets'):
            reference = private[key]
            self.assertEqual(E._sha256(Path(reference['path'])), reference['sha256'])
            self.assertEqual(E._strict_json_sha256(json.loads(Path(reference['path']).read_text())), reference['content_sha256'])
        for reference in private['verifier_reports'].values():
            self.assertEqual(E._sha256(Path(reference['path'])), reference['sha256'])
        for path, expected in private['source_hashes'].items():
            self.assertEqual(E._sha256(Path(path)), expected)
        self.assertIn(str(Path(obligations.__file__).resolve()), manifest['stage_source_hashes'])

    def test_preview_abstention_does_not_replace_original_candidate_or_relax_final_gate(self):
        original_review = pipeline.review

        def uncertain_salience(anchor):
            row = original_review(anchor)
            row['salience_judgment'] = 'ambiguous'
            return row

        with mock.patch.object(pipeline, 'review', side_effect=uncertain_salience), \
             mock.patch.object(obligations, 'build_physical_review_obligations',
                               wraps=obligations.build_physical_review_obligations) as build:
            _, manifest, calls, root = self.run_pipeline()
        self.assert_accounting(manifest, calls)
        kwargs = build.call_args.kwargs
        self.assertTrue(all(c['decision'] == 'accept' for c in kwargs['candidate_decisions']['clusters']))
        self.assertEqual(kwargs['candidate_decisions'], kwargs['initial_decisions'])
        self.assertEqual(kwargs['gate_audit']['records'][0]['result'], 'abstain')
        row = self.read(root, 'first_revision_obligation_checklist.json')['cluster_obligations'][0]
        facts = row['separate_axis_facts'][-1]
        self.assertEqual(facts['existence'], 'confirmed')
        self.assertEqual(facts['graph_worthiness'], 'ambiguous')
        self.assertEqual(manifest['physical_identity_gate']['changed_to_abstain_count'], 1)
        self.assertEqual(self.read(root, 'adjudicator_initial.json')['clusters'][0]['decision'], 'accept')

    def test_pending_preparation_is_the_preview_candidate_and_raw_remains_distinct(self):
        with mock.patch.object(obligations, 'build_physical_review_obligations',
                               wraps=obligations.build_physical_review_obligations) as build:
            _, manifest, calls, root = self.run_pipeline('pending_identity_pair')
        self.assert_accounting(manifest, calls)
        raw = json.loads((root / 'codex_attempts/adjudicator_initial.json').read_text())
        prepared = self.read(root, 'adjudicator_initial.json')
        self.assertEqual(raw['clusters'][0]['identity_comparisons'][0]['judgment'], 'confirmed_distinct')
        self.assertEqual(prepared['clusters'][0]['identity_comparisons'][0]['judgment'], 'unresolved')
        self.assertEqual(build.call_args.kwargs['candidate_decisions'], prepared)
        self.assertEqual(build.call_args.kwargs['initial_decisions'], prepared)
        private = self.read(root, 'first_revision_obligation_preview_provenance.private.json')
        self.assertNotEqual(private['raw_initial']['content_sha256'], private['prepared_initial']['content_sha256'])
        self.assertIn('initial_identity_review_preparation', private['preparation_artifacts'])
        self.assertIn('The supplied initial ledger is authoritative', (root / 'prompts/adjudicator_revision.txt').read_text())

    def test_local_helper_failure_omits_prompt_and_keeps_paid_usage(self):
        with mock.patch.object(obligations, 'build_physical_review_obligations', side_effect=ValueError('synthetic stale audit')):
            _, manifest, calls, root = self.run_pipeline()
        self.assert_accounting(manifest, calls)
        status = manifest['first_revision_obligation_preview']
        self.assertEqual(status['status'], 'unavailable')
        self.assertEqual(status['error_stage'], 'build_obligation_checklist')
        self.assertEqual(status['error'], 'synthetic stale audit')
        self.assertFalse(status['included_in_revision_prompt'])
        self.assertNotIn('has_obligations', status)
        private = self.read(root, 'first_revision_obligation_preview_provenance.private.json')
        prompt = (root / 'prompts/adjudicator_revision.txt').read_text()
        self.assertNotIn('partial_obligation_preview', prompt)
        self.assertEqual(hashlib.sha256(prompt.encode()).hexdigest(), private['base_revision_prompt_sha256'])
        self.assertFalse((root / 'adjudication/first_revision_obligation_checklist.json').exists())

    def test_each_sidecar_failure_is_unavailable_never_stale_partial_success(self):
        original_write = E._atomic_write_json
        names = ('first_revision_physical_gate_preview.private.json',
                 'first_revision_obligation_checklist.json',
                 'first_revision_obligation_preview_provenance.private.json')
        for name in names:
            with self.subTest(name=name):
                def fail_selected(path, data):
                    if path.name == name:
                        raise OSError('synthetic optional sidecar failure')
                    return original_write(path, data)

                with mock.patch.object(E, '_atomic_write_json', side_effect=fail_selected):
                    _, manifest, calls, root = self.run_pipeline()
                self.assert_accounting(manifest, calls)
                status = manifest['first_revision_obligation_preview']
                self.assertEqual(status['status'], 'unavailable')
                self.assertFalse(status['included_in_revision_prompt'])
                self.assertNotIn('has_obligations', status)
                self.assertNotIn('first_revision_obligation_checklist', manifest['artifacts'])
                prompt = (root / 'prompts/adjudicator_revision.txt').read_text()
                self.assertNotIn('partial_obligation_preview', prompt)
                if name.endswith('provenance.private.json'):
                    self.assertEqual(status['unavailable_provenance_write_error']['type'], 'OSError')
                else:
                    private = self.read(root, 'first_revision_obligation_preview_provenance.private.json')
                    self.assertEqual(hashlib.sha256(prompt.encode()).hexdigest(), private['base_revision_prompt_sha256'])

    def test_no_verifier_branch_never_builds_preview_or_adds_revision_call(self):
        with mock.patch.object(E, 'select_verification_targets', return_value=([], {})), \
             mock.patch.object(E, '_prepare_first_revision_obligation_preview', side_effect=AssertionError('must not run')):
            _, manifest, calls, root = self.run_pipeline()
        self.assertEqual(manifest['first_revision_obligation_preview']['status'], 'not_applicable')
        self.assertEqual(manifest['status'], 'success')
        self.assertFalse(any(c.startswith(('verifier_', 'adjudicator_revision')) for c in calls))
        self.assertFalse((root / 'prompts/adjudicator_revision.txt').exists())
        self.assertEqual(manifest['token_usage']['total_tokens'], 20 * len(calls))

    def test_existing_revision_repair_does_not_recompute_or_repeat_preview(self):
        real_lineage = E.validate_deferred_partition_lineage
        attempts = []

        def fail_first(initial, revised):
            attempts.append(1)
            if len(attempts) == 1:
                raise E.EnsembleError('synthetic revision lineage repair')
            return real_lineage(initial, revised)

        with mock.patch.object(E, 'validate_deferred_partition_lineage', side_effect=fail_first), \
             mock.patch.object(E, '_prepare_first_revision_obligation_preview', wraps=E._prepare_first_revision_obligation_preview) as preview:
            _, manifest, calls, root = self.run_pipeline()
        self.assertEqual(preview.call_count, 1)
        self.assertEqual([r['status'] for r in manifest['adjudicator_revision_attempts']], ['failed', 'success'])
        self.assertEqual(len(calls), 10)
        self.assertEqual(manifest['token_usage']['total_tokens'], 20 * len(calls))
        repair_path = root / 'prompts/adjudicator_revision.attempt2.txt'
        self.assertNotIn('partial_obligation_preview', repair_path.read_text())

    def test_required_target_mismatch_and_manifest_failure_keep_fatal_behavior(self):
        original_write = E._atomic_write_json
        for failure in ('target_mismatch', 'manifest_write'):
            with self.subTest(failure=failure):
                recorded = []
                injected = []

                def write(path, payload):
                    if path.name == 'verification_targets.json' and failure == 'target_mismatch':
                        payload = copy.deepcopy(payload)
                        payload['trigger_reasons'] = {'c1': ['stale_private_reason']}
                    if path.name == 'run_manifest.json':
                        recorded.append(copy.deepcopy(payload))
                        if (failure == 'manifest_write' and not injected
                                and payload.get('first_revision_obligation_preview', {}).get('status') == 'ready'):
                            injected.append(1)
                            raise OSError('synthetic required manifest failure')
                    return original_write(path, payload)

                with mock.patch.object(E, '_atomic_write_json', side_effect=write):
                    with self.assertRaises(E.EnsembleError):
                        self.run_pipeline()
                final = recorded[-1]
                self.assertEqual(final['status'], 'failed')
                self.assertEqual(final['token_usage']['total_tokens'], 7 * 20)
                self.assertEqual(final['adjudicator_revision_attempts'], [])
                if failure == 'target_mismatch':
                    self.assertIn('target input mismatch', final['error'])
                else:
                    self.assertIn('required manifest failure', final['error'])

    def test_legacy_real_retry_pipeline_never_enters_physical_preview(self):
        with mock.patch.object(E, '_prepare_first_revision_obligation_preview', side_effect=AssertionError('legacy preview forbidden')):
            legacy.PromptUnboundPipelineTest.test_ensemble_runner_targeted_verifies_weak_candidate(self)

    def prepare(self, initial, reports, consensus=None, gate=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        kwargs = dict(initial_decisions=initial, verifier_reports=reports,
                      target_reasons={c['cluster_id']: ['synthetic_review'] for c in initial['clusters']},
                      split_consensus=consensus or {'exact_consensus_partitions': []},
                      identity_review=identity, obligation_review=obligations,
                      output_dir=root, provenance={'source': 'synthetic-private-only'})
        if gate is None:
            return E._prepare_first_revision_obligation_preview(**kwargs), root
        with mock.patch.object(identity, 'apply_physical_identity_gate', side_effect=gate):
            return E._prepare_first_revision_obligation_preview(**kwargs), root

    def test_actual_split_consensus_and_full_parent_reports_are_forwarded_without_projection(self):
        initial, children, reports, consensus = fixtures.PhysicalIdentityReviewTests().split_fixture()
        before = copy.deepcopy((initial, children, reports, consensus))
        with mock.patch.object(identity, 'apply_physical_identity_gate', wraps=identity.apply_physical_identity_gate) as gate:
            (supplement, status, _), root = self.prepare(initial, reports, consensus)
        self.assertEqual(status['status'], 'ready')
        self.assertEqual(gate.call_args.args[0], initial)
        self.assertEqual(gate.call_args.kwargs['intra_cluster_split_consensus'], consensus)
        self.assertEqual(gate.call_args.kwargs['verifier_reports'], reports)
        self.assertEqual((initial, children, reports, consensus), before)
        checklist = json.loads((root / 'first_revision_obligation_checklist.json').read_text())
        self.assertEqual([r['cluster_id'] for r in checklist['cluster_obligations']], ['c1'])
        self.assertNotIn('"cluster_id":"u1"', supplement)
        # The unchanged final gate still uses each child's own review. Parent
        # evidence/checklist does not repair a missing exact unit confirmation.
        reports[1]['reviews'][0]['proposed_physical_units'][0]['existence_judgment'] = 'uncertain'
        gated, audit = identity.apply_physical_identity_gate(
            children, initial_decisions=initial, verifier_reports=reports,
            verification_target_reasons={'c1': ['split']}, intra_cluster_split_consensus=consensus)
        self.assertEqual(gated['clusters'][0]['decision'], 'abstain')
        self.assertTrue(audit['records'][0]['exact_split_firewall_failed'])

    def test_deferred_reject_scope_is_retained_in_full_inputs_not_promoted_by_preview(self):
        initial = fixtures.ledger(fixtures.cluster('a', ['p1']), fixtures.cluster('deferred', ['q1'], decision='reject'))
        initial['clusters'][1]['uncertainty_flags'] = ['group_member_alternative']
        reports = fixtures.two_reports(*initial['clusters'])
        with mock.patch.object(obligations, 'build_physical_review_obligations', wraps=obligations.build_physical_review_obligations) as build:
            (_, status, _), root = self.prepare(initial, reports)
        self.assertEqual(status['status'], 'ready')
        self.assertEqual(build.call_args.kwargs['candidate_decisions'], initial)
        checklist = json.loads((root / 'first_revision_obligation_checklist.json').read_text())
        self.assertNotIn('deferred', [r['cluster_id'] for r in checklist['cluster_obligations']])
        self.assertEqual(initial['clusters'][1]['decision'], 'reject')

    def test_mutating_preview_is_discarded_and_interrupts_are_not_caught(self):
        initial = fixtures.ledger(fixtures.cluster())
        reports = fixtures.two_reports(*initial['clusters'])
        before = copy.deepcopy(initial)
        real_gate = identity.apply_physical_identity_gate

        def mutate(candidate, **kwargs):
            result = real_gate(candidate, **kwargs)
            candidate['clusters'][0]['decision'] = 'abstain'
            return result

        (supplement, status, _), _ = self.prepare(initial, reports, gate=mutate)
        self.assertIsNone(supplement)
        self.assertEqual(status['error_stage'], 'physical_gate_preview')
        self.assertEqual(initial, before)
        with self.assertRaises(KeyboardInterrupt):
            self.prepare(initial, reports, gate=KeyboardInterrupt())

    def test_required_original_input_mismatch_remains_fatal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'required.json'
            path.write_text('{"clusters": []}')
            with self.assertRaisesRegex(E.EnsembleError, 'differs from saved pipeline input'):
                E._revision_preview_input(path, {'clusters': ['different']})
            path.unlink()
            with self.assertRaises(FileNotFoundError):
                E._revision_preview_input(path, {})


if __name__ == '__main__':
    unittest.main()
