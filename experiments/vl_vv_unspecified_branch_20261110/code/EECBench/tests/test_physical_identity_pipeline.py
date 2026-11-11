"""Exercise the real physical-review orchestration with synthetic model outputs."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from PIL import Image

from test_prompt_unbound_pipelines import ENSEMBLE, ensemble_ledger, ensemble_proposal
from test_physical_identity_review import cluster, comparison, ledger, report, review


USAGE = {"input_tokens": 13, "cached_input_tokens": 3, "output_tokens": 7, "total_tokens": 20}


class PhysicalIdentityPipelineTest(unittest.TestCase):
    def run_pipeline(self, corruption=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        run_dir = root / 'run'
        frame = Image.new('RGB', (16, 16), 'gray')
        frame_path = root / 'frame_10.png'
        frame.save(frame_path)
        sample = ENSEMBLE.shot_graph.VideoSample(
            frames={10: frame},
            frame_paths={10: frame_path}, num_frames=11, fps=5.0,
        )
        calls = []
        lock = threading.Lock()
        registry_marker = 'PRIVATE_REGISTRY_ONLY_SENTINEL'

        def invoke(**kwargs):
            stem = kwargs['output_path'].stem
            if stem.startswith('detector_'):
                role = stem.split('.')[0]
                payload = ensemble_ledger(role, 'detector', [ensemble_proposal(role + '_e1')], shot_id='synthetic')
            else:
                proposals = json.loads((run_dir / 'adjudication/anonymized_candidates.json').read_text())['proposals']
                ids = [p['anonymous_proposal_id'] for p in proposals]
                anchor = cluster(scope=ids)
                anchor['category_resolution'] = 'category_unresolved'
                anchor['uncertainty_flags'] = ['category_unresolved']
                anchors = [anchor]
                pending_pair = corruption == 'pending_identity_pair'
                declared_pair = corruption == 'declared_identity_pair'
                context_mode = corruption in {
                    'context_missing_partner', 'context_already_legal',
                    'context_positive_reference', 'context_partial_review',
                    'context_positive_with_valid_pair',
                    'context_union_review_repair',
                }
                if pending_pair or declared_pair:
                    anchors = [cluster('ca', ids[:2], name='fixture alpha'),
                               cluster('cb', ids[2:], name='fixture beta')]
                if context_mode:
                    anchors = [cluster('ca', ids[:2], name='fixture alpha'),
                               cluster('cb', ids[2:3], name='fixture beta'),
                               cluster('cc', ids[3:], name='fixture gamma')]
                if stem.startswith('adjudicator_'):
                    self.assertEqual(kwargs['schema_path'].name, 'codex_entity_adjudication_v0.6.schema.json')
                    payload = ledger(*anchors)
                    if context_mode and stem == 'adjudicator_initial':
                        observation = copy.deepcopy(anchors[0]['adjudicator_evidence'][0])
                        observation.update(anonymous_proposal_ids=ids,
                                           cue_type='simultaneous_separation',
                                           observation='PRIVATE_WIDE_CONTEXT_SENTINEL')
                        anchors[0]['adjudicator_evidence'].append(observation)
                        partners = (['cb', 'cc'] if corruption in {
                            'context_already_legal', 'context_positive_with_valid_pair'} else ['cb'])
                        anchors[0]['identity_comparisons'] = [{
                            'other_cluster_id': partner, 'judgment': 'unresolved',
                            'scope_relation': 'group_member', 'evidence_indices': [1],
                        } for partner in partners]
                        if corruption in {'context_positive_reference', 'context_positive_with_valid_pair'}:
                            anchors[0]['identity_comparisons'][0].update(
                                judgment='confirmed_distinct', scope_relation='comparable')
                        if corruption == 'context_positive_with_valid_pair':
                            pair_evidence = copy.deepcopy(observation)
                            pair_evidence['anonymous_proposal_ids'] = ids[:3]
                            anchors[0]['adjudicator_evidence'].append(pair_evidence)
                            anchors[0]['identity_comparisons'][0]['evidence_indices'] = [1, 2]
                            anchors[0]['identity_comparisons'][1]['evidence_indices'] = []
                    if context_mode and stem.startswith('adjudicator_revision'):
                        if stem == 'adjudicator_revision':
                            self.assertIn('current indices', kwargs['prompt'])
                        else:
                            self.assertEqual(stem, 'adjudicator_revision.attempt2')
                            self.assertEqual(kwargs.get('resume_thread_id'), 'synthetic_thread')
                            self.assertIn('single accounting-repair retry', kwargs['prompt'])
                        self.assertNotIn('PRIVATE_WIDE_CONTEXT_SENTINEL', kwargs['prompt'])
                    if pending_pair or declared_pair:
                        if stem == 'adjudicator_initial' and pending_pair:
                            anchors[0]['identity_comparisons'] = [{
                                'other_cluster_id': 'cb', 'judgment': 'confirmed_distinct',
                                'scope_relation': 'comparable', 'evidence_indices': [0],
                            }]
                        else:
                            for own, other in ((anchors[0], anchors[1]), (anchors[1], anchors[0])):
                                comparison(own, other['cluster_id'], ids, 'confirmed_distinct',
                                           evidence_key='adjudicator_evidence')
                    if corruption == 'initial_null_comparison' and stem == 'adjudicator_initial':
                        payload['clusters'][0]['identity_comparisons'] = [None]
                elif stem.startswith('verifier_'):
                    role = stem.split('.')[0]
                    self.assertEqual(kwargs['schema_path'].name, 'codex_entity_verification_v0.6.schema.json')
                    reviews = [review(item) for item in anchors]
                    if context_mode:
                        targets = json.loads((run_dir / 'adjudication/verification_targets.json').read_text())
                        self.assertEqual(targets['cluster_ids'], ['ca', 'cb', 'cc'])
                        expected_pairs = 2 if corruption == 'context_already_legal' else 1
                        self.assertEqual(len(targets['identity_challenge_pairs']), expected_pairs)
                        for pair in targets['identity_challenge_pairs']:
                            for own, other in ((pair['cluster_id_a'], pair['cluster_id_b']),
                                               (pair['cluster_id_b'], pair['cluster_id_a'])):
                                target = next(row for row in reviews if row['cluster_id'] == own)
                                comparison(target, other, [], 'unresolved', relation='group_member')
                        self.assertNotIn('initial_context_scope_review', kwargs['prompt'])
                        self.assertNotIn('PRIVATE_WIDE_CONTEXT_SENTINEL', kwargs['prompt'])
                        if corruption == 'context_partial_review' and role == 'verifier_1':
                            reviews[0]['evidence'][0]['anonymous_proposal_ids'] = ids[:1]
                        if corruption == 'context_union_review_repair' and stem == 'verifier_1.attempt1':
                            reviews[0]['evidence'][0]['anonymous_proposal_ids'] = ids[:3]
                            reviews[0]['evidence'][0]['cue_type'] = 'unresolved'
                    if pending_pair or declared_pair:
                        for own, other in ((reviews[0], reviews[1]), (reviews[1], reviews[0])):
                            comparison(own, other['cluster_id'], ids, 'confirmed_distinct')
                        targets = json.loads((run_dir / 'adjudication/verification_targets.json').read_text())
                        self.assertEqual(targets['cluster_ids'], ['ca', 'cb'])
                        self.assertEqual(len(targets['identity_challenge_pairs']), 1)
                        self.assertNotIn('pending_identity_contract_review', kwargs['prompt'])
                        self.assertNotIn('source_judgment', kwargs['prompt'])
                    payload = report(role, *reviews)
                    self.assertNotIn(registry_marker, kwargs['prompt'])
                    self.assertNotIn('frozen-inventory prompt-bound matching', kwargs['prompt'].lower())
                    self.assertNotIn('verification_target_reasons', kwargs['prompt'])
                    if corruption == 'verifier_null_comparison' and stem == 'verifier_1.attempt1':
                        payload['reviews'][0]['identity_comparisons'] = [None]
                elif stem.startswith('prompt_bound_matcher'):
                    self.assertIn(registry_marker, kwargs['prompt'])
                    accepted = [item for item in json.loads(
                        (run_dir / 'adjudication/adjudicator_decisions.json').read_text())['clusters']
                                if item['decision'] == 'accept']
                    payload = {'protocol_version': ENSEMBLE.PROTOCOL_VERSION, 'shot_id': 'synthetic',
                               'matcher_id': 'prompt_bound_matcher',
                               'matches': [{'cluster_id': item['cluster_id'], 'status': 'unbound',
                                            'matched_registry_ids': [], 'evidence_frame_ids': [10],
                                            'reason': 'Distinct from every registry claim.'}
                                           for item in accepted], 'warnings': []}
                else:
                    raise AssertionError('Unexpected model role: ' + stem)
            if not stem.startswith('prompt_bound_matcher'):
                self.assertNotIn(registry_marker, kwargs['prompt'])
            kwargs['output_path'].parent.mkdir(parents=True, exist_ok=True)
            kwargs['output_path'].write_text(json.dumps(payload))
            kwargs['events_path'].write_text(json.dumps({'type': 'turn.completed', 'usage': USAGE}) + '\n')
            kwargs['stderr_path'].write_text('')
            with lock:
                calls.append(stem)
            return ENSEMBLE.CodexInvocation(copy.deepcopy(payload), copy.deepcopy(USAGE), 'synthetic_thread', 0.01)

        with contextlib.ExitStack() as stack, \
             mock.patch.object(ENSEMBLE, '_codex_version', return_value='mock-no-model'), \
             mock.patch.object(ENSEMBLE, 'run_codex_json', side_effect=invoke), \
             mock.patch.object(ENSEMBLE, 'apply_single_detector_consensus_gate', side_effect=AssertionError('legacy gate called')), \
             mock.patch.object(ENSEMBLE, 'apply_nonmajority_generic_identity_gate', side_effect=AssertionError('legacy gate called')), \
             contextlib.redirect_stdout(io.StringIO()):
            if corruption in {'pending_identity_pair', 'context_missing_partner',
                              'context_already_legal', 'context_positive_reference', 'context_partial_review',
                              'context_union_review_repair',
                              'context_positive_with_valid_pair'}:
                # Suppress heuristic selection while retaining explicit initial
                # declaration obligations required by the physical contract.
                original_select = ENSEMBLE.select_verification_targets
                def select_declared(decisions, sources, anonymous, splits, **kwargs):
                    if not kwargs.get('include_initial_comparisons'):
                        return [], {}
                    targets, reasons = original_select(decisions, sources, None, (), **kwargs)
                    reasons = {key: [reason for reason in values if reason == 'initial_declared_identity_comparison']
                               for key, values in reasons.items()}
                    reasons = {key: values for key, values in reasons.items() if values}
                    return sorted(reasons), reasons
                stack.enter_context(mock.patch.object(ENSEMBLE, 'select_verification_targets', side_effect=select_declared))
                stack.enter_context(mock.patch.object(ENSEMBLE, 'build_identity_challenge_pairs',
                    side_effect=lambda decisions, anonymous, **kwargs:
                    ENSEMBLE._initial_declared_identity_pairs(decisions)[0]
                    if kwargs.get('include_initial_comparisons') else []))
            try:
                result = ENSEMBLE.run_ensemble_detection(
                    sample=sample, shot_id='synthetic',
                    prompt_entities=[{'id': 'pb1', 'name': registry_marker,
                                      'description': registry_marker, 'entity_type': 'object'}],
                    run_dir=run_dir, codex_bin='unused', model='mock-no-model',
                    timeout_sec=5, identity_review_policy='physical_v0.6',
                )
            except ENSEMBLE.EnsembleError:
                if corruption not in {'initial_null_comparison', 'context_positive_reference', 'context_partial_review',
                                      'context_positive_with_valid_pair'}:
                    raise
                result = None
        manifest = json.loads((run_dir / 'run_manifest.json').read_text())
        return result, manifest, calls, run_dir

    def test_broad_identity_survives_real_role_and_artifact_boundaries(self):
        result, manifest, calls, root = self.run_pipeline()
        self.assertEqual(len(result.semantics['entities']), 1)
        self.assertEqual(manifest['status'], 'success')
        self.assertFalse(manifest['single_detector_consensus_gate']['applied'])
        self.assertFalse(manifest['nonmajority_generic_identity_gate']['applied'])
        self.assertEqual(manifest['physical_identity_gate']['changed_to_abstain_count'], 0)
        lineage = json.loads((root / 'adjudication/graph_physical_anchor_lineage.json').read_text())
        self.assertTrue(lineage['every_physical_anchor_mapped_exactly_once'])
        self.assertEqual(lineage['accepted_physical_anchor_count'], 1)
        self.assertEqual(manifest['token_usage']['total_tokens'], 20 * len(calls))

    def test_invalid_verifier_schema_retains_failed_and_peer_usage(self):
        result, manifest, calls, _ = self.run_pipeline('verifier_null_comparison')
        self.assertEqual(len(result.semantics['entities']), 1)
        rows = manifest['verifier_attempts']
        self.assertEqual(len(rows), 3)
        self.assertEqual(sum(r['status'] == 'failed' for r in rows), 1)
        self.assertTrue(all(r['subprocess_started'] and r['token_usage'] == USAGE for r in rows))
        self.assertEqual(manifest['token_usage']['total_tokens'], 20 * len(calls))

    def test_valid_initial_declared_pair_reaches_both_verifiers_without_pending_repair(self):
        result, manifest, calls, root = self.run_pipeline('declared_identity_pair')
        self.assertEqual(manifest['status'], 'success')
        self.assertEqual(len(result.semantics['entities']), 2)
        self.assertEqual(manifest['initial_identity_pending_review']['pending_assertion_count'], 0)
        targets = json.loads((root / 'adjudication/verification_targets.json').read_text())
        handoff = manifest['initial_declared_identity_review']
        self.assertEqual(handoff, targets['initial_declared_identity_review'])
        self.assertEqual(handoff['declared_pair_count'], 1)
        self.assertEqual(handoff['source_comparison_count'], 2)
        self.assertEqual(handoff['required_partners_by_cluster'], {'ca': ['cb'], 'cb': ['ca']})
        self.assertEqual(handoff['required_verifier_ids'], ['verifier_1', 'verifier_2'])
        self.assertEqual(handoff['initial_output_sha256'], ENSEMBLE._sha256(Path(handoff['initial_output_path'])))
        self.assertEqual(len([name for name in calls if name.startswith('verifier_')]), 2)
        self.assertEqual(manifest['token_usage']['total_tokens'], 20 * len(calls))

    def test_invalid_initial_schema_stops_with_usage_accounted(self):
        result, manifest, calls, root = self.run_pipeline('initial_null_comparison')
        self.assertIsNone(result)
        self.assertEqual(manifest['status'], 'failed')
        self.assertEqual(manifest['adjudicator_initial_attempts'][0]['status'], 'failed')
        self.assertEqual(manifest['adjudicator_initial_attempts'][0]['token_usage'], USAGE)
        self.assertEqual(manifest['token_usage']['total_tokens'], 20 * len(calls))
        self.assertFalse((root / 'final_semantics.json').exists())

    def test_pending_pair_preserves_failed_raw_call_and_forces_both_complete_reviews(self):
        result, manifest, calls, root = self.run_pipeline('pending_identity_pair')
        self.assertEqual(manifest['status'], 'success')
        self.assertEqual(len(result.semantics['entities']), 2)
        self.assertEqual(len(calls), 9)
        self.assertEqual(manifest['token_usage']['total_tokens'], 20 * len(calls))
        initial = manifest['adjudicator_initial_attempts']
        self.assertEqual(len(initial), 1)
        self.assertEqual(initial[0]['status'], 'failed')
        self.assertEqual(initial[0]['failure_kind'], 'python_validation')
        self.assertEqual(initial[0]['recovery_status'], 'pending_identity_review')
        self.assertFalse(initial[0]['raw_contract_valid'])
        self.assertTrue(initial[0]['derived_contract_valid'])
        self.assertEqual(initial[0]['token_usage'], USAGE)
        raw = json.loads((root / 'codex_attempts/adjudicator_initial.json').read_text())
        derived = json.loads((root / 'adjudication/adjudicator_initial.json').read_text())
        preparation = json.loads((root / 'adjudication/initial_identity_review_preparation.json').read_text())
        self.assertEqual(len(preparation['pending_comparisons']), 1)
        self.assertEqual(raw['clusters'][0]['identity_comparisons'][0]['judgment'], 'confirmed_distinct')
        self.assertEqual(derived['clusters'][0]['identity_comparisons'][0]['judgment'], 'unresolved')
        self.assertEqual(raw['clusters'][0]['adjudicator_evidence'], derived['clusters'][0]['adjudicator_evidence'])
        dispositions = json.loads((root / 'adjudication/pending_identity_review_dispositions.json').read_text())
        self.assertTrue(dispositions['all_pending_pairs_contract_resolved'])
        self.assertFalse(dispositions['unresolved_coverage_risk'])

    def test_context_projection_preserves_raw_failure_and_forces_all_scopes_without_invented_pairs(self):
        result, manifest, calls, root = self.run_pipeline('context_missing_partner')
        self.assertEqual(manifest['status'], 'success')
        self.assertEqual(len(result.semantics['entities']), 3)
        self.assertEqual(len(calls), 9)
        self.assertEqual(manifest['token_usage']['total_tokens'], 20 * len(calls))
        attempt = manifest['adjudicator_initial_attempts'][0]
        self.assertEqual(attempt['status'], 'failed')
        self.assertEqual(attempt['failure_kind'], 'python_validation')
        self.assertEqual(attempt['recovery_status'], 'initial_context_and_identity_review')
        self.assertFalse(attempt['raw_contract_valid'])
        self.assertTrue(attempt['derived_contract_valid'])
        raw = json.loads((root / 'codex_attempts/adjudicator_initial.json').read_text())
        projected = json.loads((root / 'adjudication/initial_context_projection.json').read_text())
        quarantine = json.loads((root / 'adjudication/initial_context_quarantine.json').read_text())
        self.assertEqual(len(raw['clusters'][0]['adjudicator_evidence']), 2)
        self.assertEqual(len(projected['clusters'][0]['adjudicator_evidence']), 1)
        self.assertEqual(quarantine['evidence_index_maps']['ca'], [0, None])
        self.assertEqual(quarantine['review_scope_ids'], ['ca', 'cb', 'cc'])
        pending = json.loads((root / 'adjudication/initial_identity_review_preparation.json').read_text())
        self.assertEqual(pending['input_stage'], 'context_projection')
        self.assertEqual(pending['pending_comparisons'], [])
        self.assertEqual(pending['raw_output_path'], str(root / 'adjudication/initial_context_projection.json'))
        self.assertTrue(manifest['initial_context_review']['all_required_scopes_reviewed'])
        # The original ca-cb question is now explicitly reviewed as group/member;
        # the context-only ca-cc/cb-cc pairs are never invented by this routing.
        self.assertFalse(manifest['initial_context_review']['unresolved_coverage_risk'])
        handoff = manifest['initial_declared_identity_review']
        self.assertEqual(handoff['required_partners_by_cluster'], {'ca': ['cb'], 'cb': ['ca']})
        physical = json.loads((root / 'adjudication/adjudicator_pre_granularity.json').read_text())
        self.assertEqual(len(physical['clusters']), 3)
        self.assertEqual(sum(c['decision'] == 'abstain' for c in physical['clusters']), 0)

    def test_legal_wide_context_is_not_relabelled_as_a_failed_model_call(self):
        result, manifest, calls, _ = self.run_pipeline('context_already_legal')
        self.assertEqual(len(result.semantics['entities']), 3)
        self.assertEqual(manifest['adjudicator_initial_attempts'][0]['status'], 'success')
        self.assertTrue(manifest['adjudicator_initial_attempts'][0]['raw_contract_valid'])
        self.assertIsNone(manifest['adjudicator_initial_attempts'][0]['recovery_status'])
        self.assertEqual(manifest['initial_context_review']['quarantined_observation_count'], 1)
        self.assertEqual(manifest['token_usage']['total_tokens'], 20 * len(calls))

    def test_positive_context_reference_cannot_be_downgraded_before_quarantine(self):
        result, manifest, calls, root = self.run_pipeline('context_positive_reference')
        self.assertIsNone(result)
        self.assertEqual(manifest['status'], 'failed')
        self.assertEqual(len(calls), 5)
        self.assertEqual(manifest['token_usage']['total_tokens'], 20 * len(calls))
        self.assertEqual(manifest['verifier_attempts'], [])
        self.assertFalse((root / 'final_semantics.json').exists())

    def test_partial_scope_evidence_cannot_discharge_mandatory_context_review(self):
        result, manifest, calls, root = self.run_pipeline('context_partial_review')
        self.assertIsNone(result)
        self.assertEqual(manifest['status'], 'failed')
        self.assertEqual(manifest['token_usage']['total_tokens'], 20 * len(calls))
        attempts = manifest['verifier_attempts']
        self.assertEqual([row['status'] for row in attempts if row['verifier_id'] == 'verifier_1'], ['failed', 'failed'])
        self.assertEqual([row['status'] for row in attempts if row['verifier_id'] == 'verifier_2'], ['success'])
        self.assertFalse(any(name.startswith('adjudicator_revision') for name in calls))
        self.assertFalse((root / 'adjudication/initial_context_review_dispositions.json').exists())
        self.assertFalse((root / 'final_semantics.json').exists())

    def test_union_only_context_review_repairs_before_revision_with_original_budget(self):
        result, manifest, calls, root = self.run_pipeline('context_union_review_repair')
        self.assertIsNotNone(result)
        self.assertEqual(manifest['status'], 'success')
        attempts = manifest['verifier_attempts']
        failed = [row for row in attempts if row['status'] == 'failed']
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]['verifier_id'], 'verifier_1')
        self.assertIn('Missing complete original-scope observations', failed[0]['error'])
        self.assertEqual(failed[0]['token_usage'], USAGE)
        self.assertEqual(len([name for name in calls if name.startswith('verifier_2')]), 1)
        self.assertLess(calls.index('verifier_1.attempt2'), calls.index('adjudicator_revision'))
        self.assertEqual(len(manifest['adjudicator_revision_attempts']), 1)
        self.assertEqual(manifest['token_usage']['total_tokens'], 20 * len(calls))
        self.assertTrue(manifest['initial_context_review']['all_required_scopes_reviewed'])
        prompt = (root / 'prompts/verifier_1.attempt1.txt').read_text()
        self.assertIn('An unresolved cue', prompt)
        self.assertNotIn('PRIVATE_WIDE_CONTEXT_SENTINEL', prompt)
        self.assertIn('Validation error:', (root / 'prompts/verifier_1.attempt2.txt').read_text())

    def test_preparation_failure_does_not_falsify_successful_raw_strict_validation(self):
        result, manifest, calls, root = self.run_pipeline('context_positive_with_valid_pair')
        self.assertIsNone(result)
        attempt = manifest['adjudicator_initial_attempts'][0]
        self.assertEqual(attempt['status'], 'failed')
        self.assertTrue(attempt['raw_contract_valid'])
        self.assertFalse(attempt['derived_contract_valid'])
        self.assertIsNone(attempt['recovery_status'])
        self.assertEqual(len(calls), 5)
        self.assertEqual(manifest['token_usage']['total_tokens'], 20 * len(calls))
        self.assertFalse((root / 'final_semantics.json').exists())


if __name__ == '__main__':
    unittest.main()
