"""Existing original-scope coverage must be checked while verifier repair is possible."""

import copy
import unittest

import test_initial_context_review_audit as fixtures
import initial_context_review_audit as audit


class ContextVerifierCoverageTests(unittest.TestCase):
    def setUp(self):
        self.raw, self.initial, self.quarantine = fixtures.example('v0.2')
        self.reports = fixtures.reports(self.initial)

    def validate(self, required=None):
        return audit.validate_context_verifier_coverage(
            self.reports[0], initial_decisions=self.initial,
            required_scope_ids=self.quarantine['review_scope_ids'] if required is None else required,
            verifier_id='verifier_1')

    def test_uncertain_weak_full_scope_is_coverage_without_mutation_or_acceptance(self):
        self.initial['clusters'][0]['decision'] = 'reject'
        self.initial['clusters'][1]['decision'] = 'abstain'
        for row in self.reports[0]['reviews']:
            row['evidence'][0]['support_quality'] = 'weak'
        before = copy.deepcopy((self.initial, self.reports))
        self.assertTrue(all(row['complete_original_scope_review'] for row in self.validate()))
        self.assertEqual((self.initial, self.reports), before)

    def test_union_only_is_legal_physical_report_but_not_forced_own_scope_coverage(self):
        row = self.reports[0]['reviews'][0]
        row['evidence'][0]['anonymous_proposal_ids'].append('p0003')
        row['identity_comparisons'] = [{
            'other_cluster_id': 'b', 'judgment': 'unresolved',
            'scope_relation': 'group_member', 'evidence_indices': []}]
        audit.physical.validate_verifier_identity_fields(
            self.reports[0], target_proposal_ids_by_cluster={
                c['cluster_id']: c['anonymous_proposal_ids'] for c in self.initial['clusters']},
            identity_challenge_pairs=[], valid_frame_ids=[10])
        before = copy.deepcopy(self.reports)
        with self.assertRaisesRegex(audit.InitialContextAuditError, 'Missing complete original-scope'):
            self.validate()
        self.assertEqual(self.reports, before)
        final = audit.audit_context_review_dispositions(
            self.initial, self.initial, self.quarantine, self.reports)
        self.assertFalse(final['all_required_scopes_reviewed'])

    def test_subset_union_and_empty_cannot_replace_one_complete_observation(self):
        for ids in (['p0001'], ['p0001', 'p0002', 'p0003'], []):
            with self.subTest(ids=ids):
                self.reports = fixtures.reports(self.initial)
                self.reports[0]['reviews'][0]['evidence'][0]['anonymous_proposal_ids'] = ids
                with self.assertRaises(audit.InitialContextAuditError):
                    self.validate()

    def test_unforced_scopes_gain_no_full_scope_requirement(self):
        self.reports[0]['reviews'][0]['evidence'] = []
        self.assertEqual(len(self.validate(['b'])), 1)
        self.assertEqual(self.validate([]), [])

    def test_missing_duplicate_and_unknown_reviews_remain_errors(self):
        for mutation in (
            lambda rows: rows.pop(0),
            lambda rows: rows.append(copy.deepcopy(rows[0])),
            lambda rows: rows[0].update(cluster_id='unknown'),
        ):
            self.reports = fixtures.reports(self.initial)
            mutation(self.reports[0]['reviews'])
            with self.assertRaises(audit.InitialContextAuditError):
                self.validate()

    def test_invalid_observation_is_not_hidden_by_another_exact_observation(self):
        for frame in (True, 10.0, 99):
            self.reports = fixtures.reports(self.initial)
            bad = copy.deepcopy(self.reports[0]['reviews'][0]['evidence'][0])
            bad['frame_id'] = frame
            self.reports[0]['reviews'][0]['evidence'].append(bad)
            with self.assertRaises(audit.InitialContextAuditError):
                self.validate()

    def test_unknown_duplicate_or_nonarray_required_ids_fail(self):
        for required in (['absent'], ['a', 'a'], None, 'a'):
            with self.assertRaises(audit.InitialContextAuditError):
                audit.validate_context_verifier_coverage(
                    self.reports[0], initial_decisions=self.initial,
                    required_scope_ids=required, verifier_id='verifier_1')

    def test_other_role_or_shot_cannot_supply_coverage(self):
        for field, value in (('verifier_id', 'verifier_2'), ('shot_id', 'another_shot')):
            self.reports = fixtures.reports(self.initial)
            self.reports[0][field] = value
            with self.assertRaises(audit.InitialContextAuditError):
                self.validate()


if __name__ == '__main__':
    unittest.main()
