"""Pure CPU tests for reuse of an existing unordered exact-scope pair proof."""

import copy
import importlib.util
from itertools import permutations
from pathlib import Path
import unittest


SPEC = importlib.util.spec_from_file_location(
    "undirected_revision_fixtures", Path(__file__).with_name("test_physical_identity_review.py"))
F = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(F)
M = F.M


def unresolved(record, other, key="evidence"):
    record["identity_comparisons"] = [x for x in record["identity_comparisons"] if x["other_cluster_id"] != other]
    F.comparison(record, other, (), "unresolved", evidence_key=key)


def prove(record, other, union, targets):
    record["identity_comparisons"] = [x for x in record["identity_comparisons"] if x["other_cluster_id"] != other]
    F.comparison(record, other, union, "confirmed_distinct", evidence_key="adjudicator_evidence")
    F.resolution(record, "instance_correspondence", targets, len(record["adjudicator_evidence"]) - 1)


def fixture(source="a"):
    initial = F.ledger(F.cluster("a", ("p1", "p2")), F.cluster("b", ("q1", "q2")))
    for row, other in zip(initial["clusters"], ("b", "a")):
        unresolved(row, other, "adjudicator_evidence")
    reports = F.two_reports(*initial["clusters"])
    for report in reports:
        for row, other in zip(report["reviews"], ("b", "a")):
            unresolved(row, other)
    final = copy.deepcopy(initial)
    for row in final["clusters"]:
        row["identity_comparisons"] = []
    donor = next(row for row in final["clusters"] if row["cluster_id"] == source)
    prove(donor, "b" if source == "a" else "a", ("p1", "p2", "q1", "q2"), ("a", "b"))
    return initial, final, reports


def gate(initial, final, reports, consensus=None):
    return M.apply_physical_identity_gate(
        final, initial_decisions=initial, verifier_reports=reports,
        verification_target_reasons={x["cluster_id"]: ["synthetic_identity_review"] for x in initial["clusters"]},
        intra_cluster_split_consensus=consensus)


class UndirectedDistinctRevisionTests(unittest.TestCase):
    def test_either_endpoint_proves_pair_without_creating_reverse_evidence(self):
        for source in ("a", "b"):
            initial, final, reports = fixture(source)
            before = copy.deepcopy((initial, final, reports))
            M.validate_adjudication_identity_fields(final, valid_frame_ids=[10],
                                                    expected_proposal_ids=["p1", "p2", "q1", "q2"])
            output, audit = gate(initial, final, reports)
            self.assertEqual(output, final)
            self.assertEqual((initial, final, reports), before)
            self.assertEqual(audit["distinct_revision_proof_policy"], M.DISTINCT_REVISION_PROOF_POLICY)
            for row in audit["records"]:
                pair = row["identity_pair_judgments"][0]
                proof = pair["revision_distinct_proof"]
                self.assertTrue(pair["revision_distinct_proof_used"])
                self.assertEqual(proof["source_cluster_id"], source)
                self.assertEqual(proof["comparison_index"], 0)
                self.assertEqual(proof["comparison_evidence_indices"], [1])
                self.assertEqual(proof["comparison_exact_union_witness_indices"], [1])
                self.assertEqual(proof["resolution_index"], 0)
                self.assertEqual(proof["resolution_evidence_indices"], [1])
                self.assertEqual(proof["union_anonymous_proposal_ids"], ["p1", "p2", "q1", "q2"])
                self.assertFalse(proof["independent_observation"])
                self.assertFalse(proof["evidence_copied_or_rebound"])
                self.assertFalse(proof["reciprocal_comparison_created"])
            receiver = next(x for x in output["clusters"] if x["cluster_id"] != source)
            self.assertEqual(receiver["identity_comparisons"], [])
            audit["records"][0]["identity_pair_judgments"][0]["revision_distinct_proof"]["comparison_evidence_indices"].append(99)
            self.assertEqual((initial, final, reports), before)

    def test_valid_proof_selection_is_deterministic_when_both_endpoints_supply_it(self):
        initial, final, reports = fixture()
        prove(final["clusters"][1], "a", ("p1", "p2", "q1", "q2"), ("a", "b"))
        for order in permutations(final["clusters"]):
            output, audit = gate(initial, dict(final, clusters=list(order)), list(reversed(reports)))
            self.assertTrue(all(x["decision"] == "accept" for x in output["clusters"]))
            self.assertTrue(all(row["identity_pair_judgments"][0]["revision_distinct_proof"]["source_cluster_id"] == "a"
                                for row in audit["records"]))

    def test_explicit_reverse_unresolved_or_same_scope_still_blocks_both_endpoints(self):
        for judgment in ("unresolved", "confirmed_same_scope"):
            initial, final, reports = fixture()
            F.comparison(final["clusters"][1], "a", ("p1", "p2", "q1", "q2"), judgment,
                         evidence_key="adjudicator_evidence")
            output, audit = gate(initial, final, reports)
            self.assertEqual([x["decision"] for x in output["clusters"]], ["abstain", "abstain"])
            self.assertTrue(all(not r["identity_pair_judgments"][0]["revision_distinct_proof_used"] for r in audit["records"]))

    def test_conflicting_whole_part_or_group_member_claim_is_not_overwritten(self):
        for relation in ("whole_part", "group_member", "unresolved"):
            initial, final, reports = fixture()
            F.comparison(final["clusters"][1], "a", (), "unresolved", relation=relation,
                         evidence_key="adjudicator_evidence")
            output, audit = gate(initial, final, reports)
            self.assertEqual([x["decision"] for x in output["clusters"]], ["abstain", "abstain"])
            self.assertTrue(all(r["identity_pair_judgments"][0]["final_pair_scope_relation_conflict"] for r in audit["records"]))

    def test_unchanged_whole_part_bypass_does_not_require_alias_proof(self):
        initial, final, reports = fixture()
        for row, other in zip(final["clusters"], ("b", "a")):
            row["identity_comparisons"] = []
            row["revision_resolutions"] = []
            F.comparison(row, other, (), "unresolved", relation="whole_part", evidence_key="adjudicator_evidence")
        for report in reports:
            for row in report["reviews"]:
                row["identity_comparisons"][0]["scope_relation"] = "whole_part"
        output, audit = gate(initial, final, reports)
        self.assertTrue(all(row["decision"] == "accept" for row in output["clusters"]))
        self.assertTrue(all(row["identity_pair_judgments"] == [] for row in audit["records"]))

    def test_incomplete_or_unreferenced_proof_never_confirms_the_pair(self):
        for mutation in ("no_comparison", "no_resolution", "partial_own_scope", "partial_initial_targets",
                         "partial_union", "wrong_cue", "comparison_unreferenced", "resolution_unreferenced",
                         "bool_index", "out_of_range", "duplicate_index"):
            initial, final, reports = fixture()
            row = final["clusters"][0]
            if mutation == "no_comparison":
                row["identity_comparisons"] = []
            elif mutation == "no_resolution":
                row["revision_resolutions"] = []
            elif mutation == "partial_own_scope":
                row["revision_resolutions"][0]["anonymous_proposal_ids"] = ["p1"]
            elif mutation == "partial_initial_targets":
                row["revision_resolutions"][0]["target_cluster_ids"] = ["a"]
            elif mutation == "partial_union":
                row["adjudicator_evidence"][1]["anonymous_proposal_ids"] = ["p1", "p2", "q1"]
            elif mutation == "wrong_cue":
                row["adjudicator_evidence"][1]["cue_type"] = "same_instance_continuity"
            elif mutation == "comparison_unreferenced":
                row["identity_comparisons"][0]["evidence_indices"] = [0]
            elif mutation == "resolution_unreferenced":
                row["revision_resolutions"][0]["evidence_indices"] = [0]
            else:
                row["revision_resolutions"][0]["evidence_indices"] = {
                    "bool_index": [True], "out_of_range": [999], "duplicate_index": [1, 1]}[mutation]
            # Malformed-reference variants would fail the caller's strict
            # validator too; the read-only proof lookup must not accept them.
            output, audit = gate(initial, final, reports)
            self.assertEqual([x["decision"] for x in output["clusters"]], ["abstain", "abstain"], mutation)
            self.assertTrue(all(r["identity_pair_judgments"][0]["revision_distinct_proof"] is None for r in audit["records"]), mutation)

    def test_pair_only_failure_does_not_make_proof_lookup_iteration_dependent(self):
        initial, final, reports = fixture("b")
        extra = F.cluster("c", ("r1",))
        initial["clusters"].append(copy.deepcopy(extra))
        final["clusters"].append(copy.deepcopy(extra))
        unresolved(initial["clusters"][1], "c", "adjudicator_evidence")
        unresolved(initial["clusters"][2], "b", "adjudicator_evidence")
        unresolved(final["clusters"][1], "c", "adjudicator_evidence")
        unresolved(final["clusters"][2], "b", "adjudicator_evidence")
        for report in reports:
            report["reviews"].append(F.review(extra))
            unresolved(report["reviews"][1], "c")
            unresolved(report["reviews"][2], "b")
        for order in permutations(final["clusters"]):
            output, _ = gate(initial, dict(final, clusters=list(order)), reports)
            self.assertEqual({x["cluster_id"]: x["decision"] for x in output["clusters"]},
                             {"a": "accept", "b": "abstain", "c": "abstain"})

    def test_ineligible_counterpart_is_not_promoted_by_pair_proof(self):
        for decision in ("reject", "abstain", "unary_failure"):
            initial, final, reports = fixture("b")
            if decision == "unary_failure":
                final["clusters"][1]["salience_judgment"] = "ambiguous"
            else:
                final["clusters"][1]["decision"] = decision
                final["clusters"][1]["final_entity"] = None
            output, audit = gate(initial, final, reports)
            self.assertEqual(output["clusters"][0]["decision"], "accept")
            self.assertNotEqual(output["clusters"][1]["decision"], "accept")
            self.assertTrue(all(row["identity_pair_judgments"] == [] for row in audit["records"]))

    def test_distinct_revision_cannot_bypass_exact_split_authorization(self):
        initial, final, reports = fixture("b")
        final["clusters"][0]["anonymous_proposal_ids"] = ["p1"]
        final["clusters"][0]["adjudicator_evidence"] = [F.evidence(("p1",))]
        final["clusters"].append(F.cluster("fragment", ("p2",)))
        source = final["clusters"][1]
        source["adjudicator_evidence"][1]["anonymous_proposal_ids"] = ["p1", "q1", "q2"]
        output, audit = gate(initial, final, reports)
        self.assertEqual({x["cluster_id"]: x["decision"] for x in output["clusters"]},
                         {"a": "abstain", "b": "accept", "fragment": "abstain"})
        self.assertTrue(all(r["identity_pair_judgments"] == [] for r in audit["records"]))

    def test_graph_worthiness_disagreement_requires_existing_physical_axis_resolution(self):
        initial, final, reports = fixture()
        reports[1]["reviews"][1]["salience_judgment"] = "ambiguous"
        output, _ = gate(initial, final, reports)
        self.assertEqual(output["clusters"][1]["decision"], "abstain")
        F.resolution(final["clusters"][1], "physical_entity", ("b",), 0)
        output, _ = gate(initial, final, reports)
        self.assertEqual([x["decision"] for x in output["clusters"]], ["accept", "accept"])
        self.assertIn("salience disagreement", M.ADJUDICATION_FIELDS_INSTRUCTION)


if __name__ == "__main__":
    unittest.main()
