"""No-model regressions using real physical-gate dispositions and invented scopes."""

import copy
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


F = load("pending_audit_fixtures", ROOT / "tests/test_physical_identity_review.py")
M = load("pending_audit_tested", ROOT / "scripts/pending_identity_review_audit.py")


def set_comparison(record, partner, union, judgment, key="evidence"):
    record["identity_comparisons"] = [x for x in record["identity_comparisons"] if x["other_cluster_id"] != partner]
    F.comparison(record, partner, union, judgment, evidence_key=key)


def setup_pair(*, merge=False, revision=False, rename=False):
    initial = F.ledger(F.cluster("a", ("p1", "p2")), F.cluster("b", ("q1", "q2")))
    union = ("p1", "p2", "q1", "q2")
    for own, other in ((initial["clusters"][0], "b"), (initial["clusters"][1], "a")):
        set_comparison(own, other, union, "unresolved", "adjudicator_evidence")
    reports = F.two_reports(*initial["clusters"])
    for report in reports:
        for row, other in zip(report["reviews"], ("b", "a")):
            set_comparison(row, other, union, "unresolved" if revision else
                           "confirmed_same_scope" if merge else "confirmed_distinct")
    if merge:
        final = F.ledger(F.cluster("merged", union))
        if revision:
            final["clusters"][0]["adjudicator_evidence"].append(F.evidence(union, "same_instance_continuity"))
            F.resolution(final["clusters"][0], "instance_correspondence", ("a", "b"), 1)
    else:
        final = copy.deepcopy(initial)
        names = ("renamed_a", "renamed_b") if rename else ("a", "b")
        for row, name, other in zip(final["clusters"], names, reversed(names)):
            row["cluster_id"] = name
            row["identity_comparisons"] = []
            set_comparison(row, other, union, "confirmed_distinct", "adjudicator_evidence")
            if revision:
                F.resolution(row, "instance_correspondence", ("a", "b"), 1)
    pending = [{"cluster_id_a": "a", "cluster_id_b": "b", "own_cluster_id": "a", "other_cluster_id": "b",
                "own_anonymous_proposal_ids": ["p1", "p2"], "other_anonymous_proposal_ids": ["q1", "q2"],
                "union_anonymous_proposal_ids": list(union), "source_judgment": "confirmed_same_scope",
                "derived_judgment": "unresolved", "scope_relation": "comparable", "evidence_indices": [0]}]
    return initial, final, reports, pending


def gate(initial, final, reports):
    return F.M.apply_physical_identity_gate(final, initial_decisions=initial, verifier_reports=reports,
                                          verification_target_reasons={x["cluster_id"]: ["pending_pair"] for x in initial["clusters"]})


def audit(initial, final, reports, pending, gate_audit):
    return M.audit_pending_identity_dispositions(initial_decisions=initial, final_decisions=final,
                                                pending_comparisons=pending, physical_gate_audit=gate_audit,
                                                verifier_reports=reports)


class PendingIdentityAuditTests(unittest.TestCase):
    def check(self, *, merge=False, revision=False, rename=False):
        initial, final, reports, pending = setup_pair(merge=merge, revision=revision, rename=rename)
        final, proof = gate(initial, final, reports)
        self.assertTrue(all(x["decision"] == "accept" for x in final["clusters"]))
        outcome = audit(initial, final, reports, pending, proof)
        self.assertTrue(outcome["all_pending_pairs_contract_resolved"], outcome)
        self.assertFalse(outcome["unresolved_coverage_risk"])
        self.assertFalse(outcome["pixel_truth_verified"])
        record = outcome["records"][0]
        self.assertEqual(record["gate_disposition"], "exact_merged_alias" if merge else "exact_separate_pair")
        self.assertEqual(record["proof_basis"], "adjudicator_revision" if revision else "independent_verifier_agreement")
        self.assertEqual(record["independent_verifier_agreement"], not revision)
        return initial, final, reports, pending, proof, outcome

    def assert_risk(self, outcome):
        self.assertFalse(outcome["all_pending_pairs_contract_resolved"], outcome)
        self.assertTrue(outcome["unresolved_coverage_risk"])
        self.assertTrue(outcome["records"][0]["reason"])

    def test_no_pending_default(self):
        outcome = audit({}, {}, [], [], {})
        self.assertTrue(outcome["no_pending"])
        self.assertTrue(outcome["all_pending_pairs_contract_resolved"])
        self.assertEqual(outcome["records"], [])

    def test_exact_separate_follows_proposal_scope_after_id_rename(self):
        self.check(rename=True)

    def test_exact_merged_two_verifier_agreement(self):
        self.check(merge=True)

    def test_exact_merged_revision_preserves_coverage_without_claiming_agreement(self):
        self.check(merge=True, revision=True)

    def test_exact_separate_revision_is_existing_contract_resolution(self):
        self.check(revision=True)

    def test_one_original_union_revision_witness_resolves_both_directions(self):
        initial, final, reports, pending = setup_pair(revision=True, rename=True)
        other = final["clusters"][1]
        other["identity_comparisons"] = []
        other["revision_resolutions"] = []
        other["adjudicator_evidence"] = other["adjudicator_evidence"][:1]
        before = copy.deepcopy(final)
        final, proof = gate(initial, final, reports)
        self.assertEqual(final, before)
        outcome = audit(initial, final, reports, pending, proof)
        self.assertTrue(outcome["all_pending_pairs_contract_resolved"], outcome)
        record = outcome["records"][0]
        self.assertEqual(record["proof_basis"], "adjudicator_revision")
        self.assertFalse(record["independent_verifier_agreement"])
        sources = [row["revision_distinct_proof"]["source_cluster_id"]
                   for row in record["gate_pair_dispositions"]]
        self.assertEqual(sources, ["renamed_a", "renamed_a"])
        self.assertEqual(final["clusters"][1]["identity_comparisons"], [])

    def test_union_revision_provenance_tampering_is_an_explicit_risk(self):
        initial, final, reports, pending, proof, _ = self.check(revision=True)
        mutations = [
            ("source_cluster_id", "unknown"), ("comparison_index", 999),
            ("resolution_index", -1), ("comparison_evidence_indices", [0]),
            ("resolution_exact_union_witness_indices", []),
            ("source_anonymous_proposal_ids", ["p1"]),
            ("union_anonymous_proposal_ids", ["p1", "q1"]),
            ("independent_observation", True), ("evidence_copied_or_rebound", True),
        ]
        mutations += [(field, [value]) for field in (
            "comparison_evidence_indices", "comparison_exact_union_witness_indices",
            "resolution_evidence_indices", "resolution_exact_union_witness_indices")
            for value in (True, 1.0)]
        for field, value in mutations:
            with self.subTest(field=field):
                changed = copy.deepcopy(proof)
                changed["records"][0]["identity_pair_judgments"][0]["revision_distinct_proof"][field] = value
                self.assert_risk(audit(initial, final, reports, pending, changed))

    def test_original_union_witness_cannot_resolve_a_later_opposite_claim(self):
        for revision in (False, True):
            initial, final, reports, pending, proof, _ = self.check(revision=revision)
            for judgment, relation in (("unresolved", "comparable"),
                                       ("confirmed_same_scope", "comparable"),
                                       ("unresolved", "whole_part"),
                                       ("unresolved", "group_member")):
                with self.subTest(revision=revision, judgment=judgment, relation=relation):
                    changed = copy.deepcopy(final)
                    changed["clusters"][1]["identity_comparisons"][0].update(
                        judgment=judgment, scope_relation=relation, evidence_indices=[])
                    self.assert_risk(audit(initial, changed, reports, pending, proof))

    def test_unary_revision_dependency_is_not_labeled_independent_agreement(self):
        initial, final, reports, pending = setup_pair(merge=True)
        reports[1]["reviews"][0]["existence_judgment"] = "uncertain"
        F.resolution(final["clusters"][0], "physical_entity", ("a", "b"), 0)
        final, proof = gate(initial, final, reports)
        self.assertEqual(final["clusters"][0]["decision"], "accept")
        outcome = audit(initial, final, reports, pending, proof)
        self.assertTrue(outcome["all_pending_pairs_contract_resolved"], outcome)
        self.assertEqual(outcome["records"][0]["proof_basis"], "adjudicator_revision")
        self.assertFalse(outcome["records"][0]["independent_verifier_agreement"])
        final["clusters"][0]["revision_resolutions"][0]["evidence_indices"] = [999]
        self.assert_risk(audit(initial, final, reports, pending, proof))

    def test_raw_withdrawn_same_or_distinct_does_not_control_disposition(self):
        initial, final, reports, pending, proof, _ = self.check()
        pending[0]["source_judgment"] = "confirmed_distinct"
        self.assertTrue(audit(initial, final, reports, pending, proof)["all_pending_pairs_contract_resolved"])

    def test_reciprocal_pending_rows_form_one_pair_and_inputs_are_immutable(self):
        initial, final, reports, pending, proof, _ = self.check(merge=True, revision=True)
        reverse = copy.deepcopy(pending[0])
        reverse.update(own_cluster_id="b", other_cluster_id="a", own_anonymous_proposal_ids=["q1", "q2"],
                       other_anonymous_proposal_ids=["p1", "p2"])
        pending.append(reverse)
        before = copy.deepcopy((initial, final, reports, pending, proof))
        outcome = audit(initial, final, reports, pending, proof)
        self.assertEqual(len(outcome["records"]), 1)
        self.assertEqual(len(outcome["records"][0]["pending_sources"]), 2)
        outcome["records"][0]["pending_sources"][0]["evidence_indices"].append(100)
        outcome["records"][0]["gate_records"][0]["failure_reasons"].append("changed output")
        self.assertEqual((initial, final, reports, pending, proof), before)

    def test_missing_duplicate_or_partial_verifier_coverage_is_risk(self):
        initial, final, reports, pending, proof, _ = self.check(merge=True, revision=True)
        bad = []
        bad.append(reports[:1])
        bad.append(reports + [copy.deepcopy(reports[0])])
        partial = copy.deepcopy(reports)
        partial[1]["reviews"][0]["evidence"][0]["anonymous_proposal_ids"] = ["p1"]
        bad.append(partial)
        duplicate = copy.deepcopy(reports)
        duplicate[1]["reviews"].append(copy.deepcopy(duplicate[1]["reviews"][0]))
        bad.append(duplicate)
        for variant in bad:
            with self.subTest(variant=variant):
                self.assert_risk(audit(initial, final, variant, pending, proof))

    def test_reject_or_abstain_endpoint_does_not_discharge_pending(self):
        for decision in ("reject", "abstain"):
            initial, final, reports, pending = setup_pair()
            final["clusters"][1]["decision"] = decision
            final["clusters"][1]["final_entity"] = None
            final, proof = gate(initial, final, reports)
            outcome = audit(initial, final, reports, pending, proof)
            self.assert_risk(outcome)
            self.assertEqual(final["clusters"][0]["decision"], "accept")
            self.assertIn("final_endpoint_rejected_or_abstained", outcome["records"][0]["reason"])

    def test_unary_coverage_without_pair_review_cannot_be_discharged_by_revision(self):
        for merge in (False, True):
            initial, final, reports, pending, proof, _ = self.check(merge=merge, revision=True)
            reports[1]["reviews"][0]["identity_comparisons"] = []
            self.assert_risk(audit(initial, final, reports, pending, proof))

    def test_partial_missing_or_duplicate_final_proposal_ownership_is_risk(self):
        initial, final, reports, pending, proof, _ = self.check()
        variants = []
        split = copy.deepcopy(final)
        split["clusters"][0]["anonymous_proposal_ids"] = ["p1"]
        split["clusters"].append(F.cluster("fragment", ("p2",)))
        variants.append(split)
        missing = copy.deepcopy(final)
        missing["clusters"][0]["anonymous_proposal_ids"] = ["p1"]
        variants.append(missing)
        duplicate = copy.deepcopy(final)
        duplicate["clusters"].append(F.cluster("duplicate", ("p2",)))
        variants.append(duplicate)
        for variant in variants:
            self.assert_risk(audit(initial, variant, reports, pending, proof))

    def test_third_scope_accepted_merge_is_not_exact_pending_pair_resolution(self):
        initial, _, _, pending = setup_pair()
        initial["clusters"].append(F.cluster("c", ("r1",)))
        reports = F.two_reports(*initial["clusters"])
        for report in reports:
            for own in report["reviews"]:
                for other in report["reviews"]:
                    if own is other:
                        continue
                    scopes = {x["cluster_id"]: x["anonymous_proposal_ids"] for x in initial["clusters"]}
                    union = scopes[own["cluster_id"]] + scopes[other["cluster_id"]]
                    set_comparison(own, other["cluster_id"], union, "confirmed_same_scope")
        final = F.ledger(F.cluster("merged", ("p1", "p2", "q1", "q2", "r1")))
        final, proof = gate(initial, final, reports)
        self.assertEqual(final["clusters"][0]["decision"], "accept")
        self.assert_risk(audit(initial, final, reports, pending, proof))

    def test_missing_or_inconsistent_gate_record_does_not_resolve(self):
        initial, final, reports, pending, proof, _ = self.check()
        variants = []
        empty = copy.deepcopy(proof)
        empty["records"] = []
        variants.append(empty)
        bad_scope = copy.deepcopy(proof)
        bad_scope["records"][0]["anonymous_proposal_ids"] = ["p1"]
        variants.append(bad_scope)
        missing_pair = copy.deepcopy(proof)
        missing_pair["records"][1]["identity_pair_judgments"] = []
        variants.append(missing_pair)
        missing_coverage = copy.deepcopy(proof)
        missing_coverage["records"][0]["verifier_judgments"].pop()
        variants.append(missing_coverage)
        for variant in variants:
            self.assert_risk(audit(initial, final, reports, pending, variant))

    def test_gate_marker_cannot_forge_revision_exact_scope_or_indices(self):
        for merge in (False, True):
            initial, final, reports, pending, proof, _ = self.check(merge=merge, revision=True)
            for mutation in ("partial_scope", "bad_indices", "wrong_cue", "unreferenced_cue"):
                bad = copy.deepcopy(final)
                row = bad["clusters"][0]
                if mutation == "partial_scope":
                    row["revision_resolutions"][0]["anonymous_proposal_ids"] = ["p1"]
                elif mutation == "bad_indices":
                    row["revision_resolutions"][0]["evidence_indices"] = [True]
                elif mutation == "wrong_cue":
                    row["adjudicator_evidence"][1]["cue_type"] = "category_only"
                else:
                    row["revision_resolutions"][0]["evidence_indices"] = [0]
                self.assert_risk(audit(initial, bad, reports, pending, proof))

    def test_pending_reference_mismatch_cannot_silently_retarget(self):
        initial, final, reports, pending, proof, _ = self.check()
        pending[0]["own_anonymous_proposal_ids"] = ["p1"]
        self.assert_risk(audit(initial, final, reports, pending, proof))

    def test_review_changed_after_gate_cannot_borrow_its_confirmation(self):
        initial, final, reports, pending, proof, _ = self.check()
        reports[1]["reviews"][0]["existence_judgment"] = "uncertain"
        self.assert_risk(audit(initial, final, reports, pending, proof))

    def test_malformed_pending_direction_is_recorded_as_risk(self):
        initial, final, reports, pending, proof, _ = self.check()
        pending[0]["own_cluster_id"] = ["a"]
        self.assert_risk(audit(initial, final, reports, pending, proof))

    def test_forged_verifier_agreement_marker_requires_referenced_exact_pair_evidence(self):
        for merge in (False, True):
            initial, final, reports, pending, proof, _ = self.check(merge=merge)
            reports[1]["reviews"][0]["identity_comparisons"][0]["evidence_indices"] = [0]
            self.assert_risk(audit(initial, final, reports, pending, proof))


if __name__ == "__main__":
    unittest.main()
