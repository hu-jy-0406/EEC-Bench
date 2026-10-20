import copy
import unittest
from test_nonmajority_generic_identity_gate import (
    ENSEMBLE, DEFAULT_ROSTER, _cluster, _decisions, _source_map, _reports,
)


def run_gate(decisions, *, reports=None, support_scope="all_support"):
    ids = decisions["clusters"][0]["anonymous_proposal_ids"]
    return ENSEMBLE.apply_nonmajority_generic_identity_gate(
        decisions, initial_decisions=decisions,
        source_map=_source_map(dict(zip(ids, DEFAULT_ROSTER))),
        verifier_reports=reports if reports is not None else _reports(),
        verification_target_reasons={"c_initial": ["identity_uncertainty"]},
        expected_detector_ids=DEFAULT_ROSTER, support_scope=support_scope,
    )


class AllSupportIdentityGateTest(unittest.TestCase):
    def test_uncertain_placeholders_require_evidence_at_every_support(self):
        for support in range(1, 5):
            with self.subTest(support=support):
                original = _decisions(_cluster("c_initial", [f"p{i}" for i in range(support)]))
                snapshot = copy.deepcopy(original)
                result, audit = run_gate(original)
                self.assertEqual(original, snapshot)
                self.assertEqual(result["clusters"][0]["decision"], "abstain")
                self.assertEqual(audit["records"][0]["detector_support"], support)
                self.assertFalse(audit["detector_support_affects_gate_eligibility"])
                self.assertEqual(audit["support_scope"], "all_support")
                self.assertEqual(audit["policy_version"], ENSEMBLE.ALL_SUPPORT_GENERIC_IDENTITY_GATE_VERSION)

    def test_specific_category_and_supported_broad_furniture_survive(self):
        for name in ("mounted textile panel", "furniture piece"):
            original = _decisions(_cluster("c_initial", ["p1", "p2", "p3"], canonical_name=name))
            result, _ = run_gate(original)
            self.assertEqual(result, original)

    def test_complete_strong_or_independence_evidence_rescues(self):
        for reports in (_reports(qualities=("strong", "strong")),
                        _reports(independence_qualities=("moderate", "moderate"))):
            for support in range(1, 5):
                original = _decisions(_cluster("c_initial", [f"p{i}" for i in range(support)]))
                result, _ = run_gate(original, reports=reports)
                self.assertEqual(result, original)

    def test_partial_or_asymmetric_strong_review_does_not_rescue_majority(self):
        for reports in (_reports(qualities=("strong", "moderate")),
                        _reports(qualities=("strong", "strong"))[:1]):
            original = _decisions(_cluster("c_initial", ["p1", "p2", "p3"]))
            result, _ = run_gate(original, reports=reports)
            self.assertEqual(result["clusters"][0]["decision"], "abstain")

    def test_placeholder_without_identity_uncertainty_preserves_legacy_boundary(self):
        original = _decisions(_cluster("c_initial", ["p1", "p2", "p3"], flags=[]))
        result, _ = run_gate(original)
        self.assertEqual(result, original)

    def test_legacy_majority_exemption_remains_explicit_ablation(self):
        original = _decisions(_cluster("c_initial", ["p1", "p2", "p3"]))
        result, audit = run_gate(original, support_scope="nonmajority")
        self.assertEqual(result, original)
        self.assertEqual(audit["records"], [])

    def test_invalid_mode_fails(self):
        with self.assertRaises(ENSEMBLE.EnsembleError):
            run_gate(_decisions(_cluster("c_initial", ["p1"])), support_scope="invalid")
