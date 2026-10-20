"""Synthetic CPU-only tests for read-only physical proof obligation views."""

import copy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


F = load("obligation_fixtures", Path(__file__).with_name("test_physical_identity_review.py"))
U = load("obligation_pair_fixtures", Path(__file__).with_name("test_undirected_distinct_revision.py"))
M = load("physical_review_obligations_tested", ROOT / "scripts/physical_review_obligations.py")


def preview(initial, candidate, reports, consensus=None, reasons=None):
    return F.M.apply_physical_identity_gate(
        candidate, initial_decisions=initial, verifier_reports=reports,
        verification_target_reasons=(reasons if reasons is not None else
                                     {c["cluster_id"]: ["test"] for c in initial["clusters"]}),
        intra_cluster_split_consensus=consensus)[1]


def build(initial, candidate, reports, audit=None, **kwargs):
    return M.build_physical_review_obligations(
        initial_decisions=initial, candidate_decisions=candidate, verifier_reports=reports,
        gate_audit=preview(initial, candidate, reports, **kwargs) if audit is None else audit)


def unary():
    initial = F.ledger(F.cluster())
    return initial, copy.deepcopy(initial), F.two_reports(*initial["clusters"])


class PhysicalReviewObligationTests(unittest.TestCase):
    def test_empty_checklist_for_passed_gate_and_for_no_accepts(self):
        for no_accepts in (False, True):
            initial, candidate, reports = unary()
            if no_accepts:
                candidate["clusters"][0].update(decision="abstain", final_entity=None)
            result = build(initial, candidate, reports)
            self.assertFalse(result["has_obligations"])
            self.assertEqual(result["cluster_obligations"], [])
            self.assertEqual(result["pair_obligations"], [])
            self.assertFalse(result["pixel_truth_verified"])

    def test_salience_keeps_confirmed_existence_separate(self):
        initial, candidate, reports = unary()
        reports[1]["reviews"][0]["salience_judgment"] = "background_integrated"
        result = build(initial, candidate, reports)
        row = result["cluster_obligations"][0]
        self.assertEqual([x["axis"] for x in row["axis_obligations"]], ["physical_entity"])
        facts = row["separate_axis_facts"][-1]
        self.assertEqual(facts["existence"], "confirmed")
        self.assertEqual(facts["graph_worthiness"], "background_integrated")
        self.assertTrue(facts["positive_exact_scope_scope_cue_present"])
        self.assertEqual(row["axis_obligations"][0]["initial_target_cluster_ids"], ["c1"])

    def test_integrated_cue_is_distinct_from_resolved_scope_enum(self):
        initial, candidate, reports = unary()
        reports[1]["reviews"][0]["salience_judgment"] = "background_integrated"
        reports[1]["reviews"][0]["evidence"][0]["cue_type"] = "integrated_component"
        row = build(initial, candidate, reports)["cluster_obligations"][0]
        self.assertEqual([x["axis"] for x in row["axis_obligations"]], ["physical_entity", "proposal_scope"])
        facts = row["separate_axis_facts"][-1]
        self.assertEqual(facts["existence"], "confirmed")
        self.assertEqual(facts["proposal_scope"], "resolved_single_scope")
        self.assertFalse(facts["positive_exact_scope_scope_cue_present"])

    def test_candidate_existence_and_unresolved_identity_are_reported_as_such(self):
        initial, candidate, reports = unary()
        candidate["clusters"][0].update(existence_judgment="uncertain", identity_status="ambiguous")
        row = build(initial, candidate, reports)["cluster_obligations"][0]
        self.assertEqual(row["candidate_assessment"]["existence_judgment"], "uncertain")
        self.assertEqual({x["axis"] for x in row["axis_obligations"]}, {"physical_entity", "proposal_scope"})

    def test_source_blind_whitelist_and_deep_input_immutability(self):
        initial, candidate, reports = unary()
        reports[1]["reviews"][0]["salience_judgment"] = "ambiguous"
        marker = "FORBIDDEN_PRIVATE_SOURCE_REGISTRY_EXPECTATION"
        for ledger in (initial, candidate):
            ledger["warnings"] = [marker]
            ledger["expected_count"] = marker
            ledger["clusters"][0].update(canonical_name=marker, aliases=[marker], source=marker)
            ledger["clusters"][0]["adjudicator_evidence"][0].update(observation=marker, coarse_locator=marker)
        reports[0]["reviews"][0].update(reason=marker, private_provenance=marker)
        reports[0]["reviews"][0]["evidence"][0]["observation"] = marker
        audit = preview(initial, candidate, reports)
        audit["private_metadata"] = marker
        before = copy.deepcopy((initial, candidate, reports, audit))
        result = build(initial, candidate, reports, audit)
        self.assertNotIn(marker, json.dumps(result))
        result["cluster_obligations"][0]["anonymous_proposal_ids"].append("changed")
        result["cluster_obligations"][0]["verifier_assessments"][0]["exact_scope_physical_cue_records"][0]["anonymous_proposal_ids"].clear()
        self.assertEqual((initial, candidate, reports, audit), before)
        self.assertIn("Never invent evidence", M.REVIEW_INSTRUCTION)

    def test_missing_resolution_deduplicates_pair_without_copying_witness(self):
        initial, candidate, reports = U.fixture()
        candidate["clusters"][0]["revision_resolutions"] = []
        result = build(initial, candidate, reports)
        self.assertEqual(len(result["cluster_obligations"]), 2)
        self.assertEqual(len(result["pair_obligations"]), 1)
        pair = result["pair_obligations"][0]
        self.assertEqual(pair["cluster_ids"], ["a", "b"])
        self.assertEqual(pair["initial_target_cluster_ids"], ["a", "b"])
        self.assertEqual(pair["union_anonymous_proposal_ids"], ["p1", "p2", "q1", "q2"])
        donor, receiver = pair["endpoint_records"]
        self.assertEqual(donor["comparison_status"], "exact_union_distinct_comparison")
        self.assertEqual(donor["resolution_status"], "missing_resolution")
        self.assertEqual(donor["existing_exact_union_distinct_records_to_recheck"][0]["evidence_index"], 1)
        self.assertEqual(receiver["comparison_status"], "missing_comparison")
        self.assertFalse(pair["either_endpoint_has_complete_revision_proof"])

    def test_existing_one_sided_complete_proof_needs_no_reverse_row(self):
        for side in ("a", "b"):
            result = build(*U.fixture(side))
            self.assertEqual(result["pair_obligations"], [])
            self.assertFalse(result["has_obligations"])

    def test_explicit_unresolved_remains_distinct_from_missing_comparison(self):
        initial, candidate, reports = U.fixture()
        U.unresolved(candidate["clusters"][1], "a", "adjudicator_evidence")
        pair = build(initial, candidate, reports)["pair_obligations"][0]
        self.assertTrue(pair["either_endpoint_has_complete_revision_proof"])
        self.assertTrue(pair["final_explicit_unresolved_or_same_scope"])
        self.assertEqual(pair["endpoint_records"][1]["comparison_status"], "explicit_unresolved")

    def test_pair_scope_relation_conflict_is_preserved(self):
        initial, candidate, reports = U.fixture()
        F.comparison(candidate["clusters"][1], "a", (), "unresolved", relation="whole_part", evidence_key="adjudicator_evidence")
        pair = build(initial, candidate, reports)["pair_obligations"][0]
        self.assertTrue(pair["final_scope_relation_conflict"])
        self.assertEqual(pair["endpoint_records"][1]["comparison_status"], "noncomparable_or_unresolved_scope_relation")

    def test_missing_both_comparisons_and_wrong_target_resolution_are_not_rebound(self):
        initial, candidate, reports = U.fixture()
        candidate["clusters"][0]["identity_comparisons"] = []
        candidate["clusters"][0]["revision_resolutions"][0]["target_cluster_ids"] = ["a"]
        pair = build(initial, candidate, reports)["pair_obligations"][0]
        self.assertTrue(all(x["comparison_status"] == "missing_comparison" for x in pair["endpoint_records"]))
        self.assertEqual(pair["endpoint_records"][0]["resolution_status"], "missing_exact_scope_and_target_resolution")
        self.assertEqual(pair["endpoint_records"][0]["instance_resolution_records"][0]["target_cluster_ids"], ["a"])

    def test_split_child_uses_child_axes_not_parent_confirmation(self):
        initial, candidate, reports, consensus = F.PhysicalIdentityReviewTests().split_fixture()
        reports[1]["reviews"][0]["proposed_physical_units"][0]["existence_judgment"] = "uncertain"
        result = build(initial, candidate, reports, consensus=consensus)
        row = next(x for x in result["cluster_obligations"] if x["cluster_id"] == "u1")
        v2 = row["verifier_assessments"][1]
        self.assertEqual(v2["scope_kind"], "exact_consensus_split_unit")
        self.assertEqual(v2["parent_review_axes"]["existence_judgment"], "confirmed")
        self.assertEqual(v2["existence_judgment"], "uncertain")
        self.assertEqual(v2["anonymous_proposal_ids"], ["p0001"])
        self.assertTrue(next(x for x in row["axis_obligations"] if x["axis"] == "split_authorization")["revision_cannot_override"])

    def test_authorized_split_is_empty_but_unauthorized_split_stays_hard(self):
        initial, candidate, reports, consensus = F.PhysicalIdentityReviewTests().split_fixture()
        self.assertFalse(build(initial, candidate, reports, consensus=consensus)["has_obligations"])
        result = build(initial, candidate, reports)
        self.assertEqual(len(result["cluster_obligations"]), 2)
        self.assertTrue(all(any(x["axis"] == "split_authorization" for x in row["axis_obligations"])
                            for row in result["cluster_obligations"]))

    def test_merge_obligation_keeps_complete_initial_lineage(self):
        initial = F.ledger(F.cluster("a", ["p1"]), F.cluster("b", ["q1"]))
        candidate = F.ledger(F.cluster("merged", ["p1", "q1"]))
        result = build(initial, candidate, F.two_reports(*initial["clusters"]))
        row = result["cluster_obligations"][0]
        self.assertEqual([x["cluster_id"] for x in row["initial_targets"]], ["a", "b"])
        self.assertEqual(row["axis_obligations"][0]["axis"], "instance_correspondence")
        self.assertEqual(row["axis_obligations"][0]["anonymous_proposal_ids"], ["p1", "q1"])

    def test_missing_required_verifier_record_is_a_coverage_fact(self):
        initial, candidate, reports = unary()
        reports[1]["reviews"] = []
        row = build(initial, candidate, reports)["cluster_obligations"][0]
        self.assertFalse(row["verifier_assessments"][1]["record_present"])
        self.assertIsNone(row["verifier_assessments"][1]["existence_judgment"])

    def test_stale_unknown_duplicate_scope_and_gate_inputs_fail_closed(self):
        for mutation in ("gate_scope", "gate_targets", "gate_unknown", "gate_duplicate", "gate_result",
                         "gate_reason", "gate_review_scope", "gate_review_axis", "gate_policy", "unknown_verifier",
                         "duplicate_proposal", "unknown_proposal", "unknown_resolution_target", "invalid_index"):
            with self.subTest(mutation=mutation):
                initial, candidate, reports = unary()
                reports[1]["reviews"][0]["salience_judgment"] = "ambiguous"
                audit = preview(initial, candidate, reports)
                row = audit["records"][0]
                if mutation == "gate_scope":
                    row["anonymous_proposal_ids"] = ["other"]
                elif mutation == "gate_targets":
                    row["initial_target_cluster_ids"] = ["other"]
                elif mutation == "gate_unknown":
                    row["cluster_id"] = "other"
                elif mutation == "gate_duplicate":
                    audit["records"].append(copy.deepcopy(row))
                elif mutation == "gate_result":
                    row["result"] = "accept"
                elif mutation == "gate_reason":
                    row["failure_reasons"].append("unknown_visual_claim")
                elif mutation == "gate_review_scope":
                    row["verifier_judgments"][0]["anonymous_proposal_ids"] = ["other"]
                elif mutation == "gate_review_axis":
                    row["verifier_judgments"][0]["physical_confirmed"] = False
                elif mutation == "gate_policy":
                    audit["distinct_revision_proof_policy"] = "old"
                elif mutation == "unknown_verifier":
                    reports[1]["reviews"][0]["cluster_id"] = "other"
                elif mutation == "duplicate_proposal":
                    candidate["clusters"].append(F.cluster("extra"))
                elif mutation == "unknown_proposal":
                    candidate["clusters"][0]["anonymous_proposal_ids"] = ["other"]
                elif mutation == "unknown_resolution_target":
                    F.resolution(candidate["clusters"][0], "physical_entity", ["other"])
                elif mutation == "invalid_index":
                    F.resolution(candidate["clusters"][0], "physical_entity", ["c1"], True)
                with self.assertRaises(M.PhysicalReviewObligationError):
                    build(initial, candidate, reports, audit)

    def test_pair_gate_must_match_current_raw_claim_and_both_directions(self):
        for mutation in ("stale_raw", "missing_reverse_gate", "missing_failure", "wrong_proof_flag"):
            initial, candidate, reports = U.fixture()
            U.unresolved(candidate["clusters"][1], "a", "adjudicator_evidence")
            audit = preview(initial, candidate, reports)
            if mutation == "stale_raw":
                candidate["clusters"][1]["identity_comparisons"] = []
            elif mutation == "missing_reverse_gate":
                audit["records"][1]["identity_pair_judgments"] = []
            elif mutation == "missing_failure":
                audit["records"][1].update(failure_reasons=[], result="accept")
            else:
                audit["records"][0]["identity_pair_judgments"][0]["revision_confirms_distinct"] = False
            with self.assertRaises(M.PhysicalReviewObligationError):
                build(initial, candidate, reports, audit)

    def test_current_axes_and_resolution_cannot_reuse_a_stale_gate(self):
        initial, candidate, reports = unary()
        audit = preview(initial, candidate, reports)
        candidate["clusters"][0]["existence_judgment"] = "uncertain"
        with self.assertRaises(M.PhysicalReviewObligationError):
            build(initial, candidate, reports, audit)
        initial, candidate, reports = unary()
        reports[1]["reviews"][0]["salience_judgment"] = "ambiguous"
        audit = preview(initial, candidate, reports)
        F.resolution(candidate["clusters"][0], "physical_entity", ["c1"])
        with self.assertRaises(M.PhysicalReviewObligationError):
            build(initial, candidate, reports, audit)

    def test_reordering_inputs_preserves_bound_obligation_sets(self):
        initial, candidate, reports = U.fixture()
        candidate["clusters"][0]["revision_resolutions"] = []
        expected = build(initial, candidate, reports)
        candidate["clusters"].reverse()
        initial["clusters"].reverse()
        reports.reverse()
        self.assertEqual(build(initial, candidate, reports), expected)


if __name__ == "__main__":
    unittest.main()
