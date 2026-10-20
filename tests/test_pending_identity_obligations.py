"""Pending pair obligations bypass heuristic target omission without leaking verdicts."""
import copy
import json
import unittest

from test_prompt_unbound_pipelines import ENSEMBLE
from test_physical_identity_review import cluster, ledger


class PendingIdentityObligationsTest(unittest.TestCase):
    def inputs(self):
        left = cluster('a', ['p1', 'p2'], name='unrelated alpha', decision='reject')
        left['uncertainty_flags'] = ['group_member_conflict']
        right = cluster('b', ['p3'], name='unrelated beta')
        pending = {
            'own_cluster_id': 'a', 'other_cluster_id': 'b',
            'own_anonymous_proposal_ids': ['p1', 'p2'],
            'other_anonymous_proposal_ids': ['p3'],
            'source_judgment': 'confirmed_same_scope',
            'reason': 'PRIVATE_UNSUPPORTED_ASSERTION',
        }
        return ledger(left, right), pending

    def test_both_endpoints_are_forced_even_if_rejected_and_deferred(self):
        decisions, pending = self.inputs()
        before = copy.deepcopy(decisions)
        pairs, targets, reasons = ENSEMBLE.add_pending_identity_review_obligations(
            decisions=decisions, pending_comparisons=[pending],
            identity_challenge_pairs=[], target_ids=[], target_reasons={},
        )
        self.assertEqual(targets, ['a', 'b'])
        self.assertEqual(len(pairs), 1)
        self.assertEqual({pairs[0]['cluster_id_a'], pairs[0]['cluster_id_b']}, {'a', 'b'})
        self.assertEqual(pairs[0]['trigger_bases'], ['physical_scope_comparison'])
        self.assertEqual(set(reasons), {'a', 'b'})
        self.assertNotIn('PRIVATE_UNSUPPORTED_ASSERTION', json.dumps(pairs))
        self.assertNotIn('confirmed_same_scope', json.dumps(pairs))
        self.assertEqual(decisions, before)

    def test_reciprocal_and_existing_challenges_are_not_duplicated(self):
        decisions, pending = self.inputs()
        reverse = {**pending, 'own_cluster_id': 'b', 'other_cluster_id': 'a',
                   'own_anonymous_proposal_ids': ['p3'], 'other_anonymous_proposal_ids': ['p2', 'p1']}
        existing = [{'cluster_id_a': 'b', 'cluster_id_b': 'a', 'trigger_bases': ['original']}]
        before = copy.deepcopy(existing)
        pairs, targets, reasons = ENSEMBLE.add_pending_identity_review_obligations(
            decisions=decisions, pending_comparisons=[pending, reverse],
            identity_challenge_pairs=existing, target_ids=['b'], target_reasons={'b': ['original']},
        )
        self.assertEqual(len(pairs), 1)
        self.assertEqual(existing, before)
        self.assertEqual(targets, ['a', 'b'])
        self.assertEqual(reasons['b'].count('pending_identity_contract_review'), 1)

    def test_changed_obligation_scope_cannot_silently_enter_review(self):
        decisions, pending = self.inputs()
        pending['own_anonymous_proposal_ids'] = ['p1']
        with self.assertRaisesRegex(ENSEMBLE.EnsembleError, 'complete initial scopes'):
            ENSEMBLE.add_pending_identity_review_obligations(
                decisions=decisions, pending_comparisons=[pending],
                identity_challenge_pairs=[], target_ids=[], target_reasons={},
            )


if __name__ == '__main__':
    unittest.main()
