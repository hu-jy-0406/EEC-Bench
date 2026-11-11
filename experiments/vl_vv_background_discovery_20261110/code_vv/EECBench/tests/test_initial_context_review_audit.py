"""Independent, synthetic context provenance/coverage audits; no model calls."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import initial_context_review_audit as M  # noqa: E402

SPEC = importlib.util.spec_from_file_location("context_audit_fixtures", Path(__file__).with_name("test_physical_identity_review.py"))
F = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(F)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def example(version="v0.1"):
    a, b, c = F.cluster("a", ["p0001", "p0002"]), F.cluster("b", ["p0003"]), F.cluster("c", ["p0004"])
    wide = F.evidence(["p0001", "p0002", "p0003", "p0004"], "simultaneous_separation", "A broad contextual observation; no individual verdict follows.")
    a["adjudicator_evidence"] += [copy.deepcopy(wide), F.evidence(["p0001", "p0002", "p0003"], "simultaneous_separation"), copy.deepcopy(wide)]
    a["identity_comparisons"] = [
        {"other_cluster_id": "b", "judgment": "confirmed_distinct", "scope_relation": "comparable", "evidence_indices": [2]},
        {"other_cluster_id": "c", "judgment": "unresolved", "scope_relation": "group_member", "evidence_indices": [1, 3, 0]},
    ]
    b["adjudicator_evidence"].append(copy.deepcopy(wide))
    raw = F.ledger(a, b, c)
    projected = copy.deepcopy(raw)
    projected["clusters"][0]["adjudicator_evidence"] = [copy.deepcopy(a["adjudicator_evidence"][i]) for i in (0, 2)]
    projected["clusters"][0]["identity_comparisons"][0]["evidence_indices"] = [1]
    projected["clusters"][0]["identity_comparisons"][1]["evidence_indices"] = [0]
    projected["clusters"][1]["adjudicator_evidence"] = [copy.deepcopy(b["adjudicator_evidence"][0])]
    contexts = []
    for owner, position, ei in (("a", 0, 1), ("a", 0, 3), ("b", 1, 1)):
        item = raw["clusters"][position]["adjudicator_evidence"][ei]
        refs = [] if owner == "b" else [{
            "comparison_index": 1, "json_pointer": "/clusters/0/identity_comparisons/1/evidence_indices",
            "other_cluster_id": "c", "judgment": "unresolved", "scope_relation": "group_member",
            "original_evidence_indices": [1, 3, 0], "projected_evidence_indices": [0],
        }]
        contexts.append({"owner_cluster_id": owner, "original_evidence_index": ei,
                         "original_json_pointer": f"/clusters/{position}/adjudicator_evidence/{ei}",
                         "observation": copy.deepcopy(item), "observation_sha256": digest(item),
                         "scope_owner_ids": ["a", "b", "c"], "references": refs})
    audit = {"policy_version": "initial_context_quarantine_" + version, "stage": "initial_adjudication",
             "raw_sha256": digest(raw), "projected_sha256": digest(projected), "visual_correction": False,
             "quarantined_evidence": contexts, "evidence_index_maps": {"a": [0, None, 1, None], "b": [0, None], "c": [0]},
             "review_scope_ids": ["a", "b", "c"], "shadow_pending_comparison_count": 0,
             "shadow_validation_policy": "initial_identity_pending_" + version, "strict_shadow_validation_passed": True,
             "requires_pending_preparation_before_use": True}
    return raw, projected, audit


def validate(raw, projected, audit):
    return M.audit_initial_context_projection(raw, projected, audit, valid_frame_ids=[10],
                                             expected_proposal_ids=["p0001", "p0002", "p0003", "p0004"])


def reports(raw):
    clean = copy.deepcopy(raw)
    for row in clean["clusters"]:
        row["adjudicator_evidence"] = [F.evidence(row["anonymous_proposal_ids"], "unresolved", "The entire original scope was inspected; correspondence remains uncertain.")]
        row.update(existence_judgment="uncertain", salience_judgment="ambiguous", proposal_scope_judgment="unresolved")
        row["identity_comparisons"] = []
    return F.two_reports(*clean["clusters"])


class InitialContextReviewAuditTests(unittest.TestCase):
    def test_manual_projection_recomputed_without_projector_and_inputs_unchanged(self):
        raw, projected, audit = example()
        before = copy.deepcopy((raw, projected, audit))
        result = validate(raw, projected, audit)
        self.assertTrue(result["projection_contract_valid"])
        self.assertEqual(result["quarantined_evidence_count"], 3)
        self.assertFalse(result["projector_or_pending_preparer_called"])
        self.assertEqual((raw, projected, audit), before)
        self.assertNotIn("initial_context_quarantine", M.__dict__)

    def test_mutated_maps_hashes_references_metadata_and_omitted_quarantine_fail(self):
        mutations = [
            lambda a: a["quarantined_evidence"].pop(),
            lambda a: a["quarantined_evidence"][0]["references"].clear(),
            lambda a: a["quarantined_evidence"][0]["references"][0].update(projected_evidence_indices=[]),
            lambda a: a["quarantined_evidence"][0].update(original_json_pointer="/clusters/1/adjudicator_evidence/1"),
            lambda a: a["quarantined_evidence"][0].update(scope_owner_ids=["a", "b"]),
            lambda a: a["evidence_index_maps"]["a"].__setitem__(2, True),
            lambda a: a["evidence_index_maps"]["a"].__setitem__(2, 1.0),
            lambda a: a.update(raw_sha256="0" * 64),
            lambda a: a.update(projected_sha256="0" * 64),
            lambda a: a.update(review_scope_ids=["a", "b"]),
            lambda a: a.update(shadow_pending_comparison_count=False),
            lambda a: a.update(strict_shadow_validation_passed=1),
            lambda a: a.update(extra_transport_metadata="not the audited sidecar"),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                raw, projected, audit = example()
                mutation(audit)
                with self.assertRaises(M.InitialContextAuditError):
                    validate(raw, projected, audit)

    def test_projection_cannot_change_unrelated_fields_or_copy_rebind_evidence(self):
        for mutation in (
            lambda p: p["clusters"].reverse(),
            lambda p: p["clusters"][2].update(canonical_name="changed"),
            lambda p: p["clusters"][2].update(decision_reason="changed"),
            lambda p: p["clusters"][0]["adjudicator_evidence"][0].update(observation="rewritten"),
            lambda p: p["clusters"][0]["adjudicator_evidence"].append(copy.deepcopy(p["clusters"][1]["adjudicator_evidence"][0])),
            lambda p: p["clusters"][0]["identity_comparisons"][0].update(judgment="unresolved"),
        ):
            raw, projected, audit = example()
            mutation(projected)
            audit["projected_sha256"] = digest(projected)
            with self.assertRaises(M.InitialContextAuditError):
                validate(raw, projected, audit)

    def test_illegal_context_references_cannot_be_quarantined_even_with_other_proof(self):
        for judgment, relation, indices in (
            ("confirmed_distinct", "comparable", [2, 1]),
            ("confirmed_same_scope", "comparable", [1]),
            ("unresolved", "comparable", [1]),
            ("unresolved", "unresolved", [1]),
        ):
            raw, projected, audit = example()
            raw["clusters"][0]["identity_comparisons"][0].update(judgment=judgment, scope_relation=relation, evidence_indices=indices)
            with self.assertRaises(M.InitialContextAuditError):
                validate(raw, projected, audit)

    def test_partial_unknown_and_nonfirst_malformed_raw_records_remain_fatal(self):
        for mutation in (
            lambda r: r["clusters"][0]["adjudicator_evidence"][1].update(anonymous_proposal_ids=["p0001", "p0003", "p0004"]),
            lambda r: r["clusters"][1]["adjudicator_evidence"][1].update(anonymous_proposal_ids=["p0001", "p0003", "p0004"]),
            lambda r: r["clusters"][1]["adjudicator_evidence"][1].update(anonymous_proposal_ids=["p0001", "p0002", "unknown"]),
            lambda r: r["clusters"][1]["adjudicator_evidence"][1].update(frame_id=True),
            lambda r: r["clusters"][1]["adjudicator_evidence"][1].update(frame_id=10.0),
            lambda r: r["clusters"][0]["identity_comparisons"][1].update(evidence_indices=[True]),
            lambda r: r["clusters"][0]["identity_comparisons"][1].update(evidence_indices=[3.0]),
            lambda r: r["clusters"][2].update(revision_resolutions=[{"axis": "physical_entity", "target_cluster_ids": ["c"], "anonymous_proposal_ids": ["p0004"], "evidence_indices": [0]}]),
        ):
            raw, projected, audit = example()
            mutation(raw)
            with self.assertRaises(M.InitialContextAuditError):
                validate(raw, projected, audit)

    def test_old_pending_shadow_is_counted_but_projection_keeps_original_judgment(self):
        raw, projected, audit = example()
        raw["clusters"][0]["identity_comparisons"][0]["evidence_indices"] = [0]
        projected["clusters"][0]["identity_comparisons"][0]["evidence_indices"] = [0]
        audit.update(raw_sha256=digest(raw), projected_sha256=digest(projected), shadow_pending_comparison_count=1)
        self.assertEqual(validate(raw, projected, audit)["shadow_pending_comparison_count"], 1)
        self.assertEqual(projected["clusters"][0]["identity_comparisons"][0]["judgment"], "confirmed_distinct")

    def test_v02_empty_confirmation_is_counted_without_borrowing_reverse_witness(self):
        for judgment in ("confirmed_same_scope", "confirmed_distinct"):
            raw, projected, audit = example("v0.2")
            for ledger in (raw, projected):
                ledger["clusters"][0]["identity_comparisons"][0].update(judgment=judgment, evidence_indices=[])
                b = ledger["clusters"][1]
                b["adjudicator_evidence"].append(F.evidence(
                    ["p0001", "p0002", "p0003"],
                    "same_instance_continuity" if judgment == "confirmed_same_scope" else "simultaneous_separation"))
                b["identity_comparisons"] = [{"other_cluster_id": "a", "judgment": judgment,
                                              "scope_relation": "comparable",
                                              "evidence_indices": [len(b["adjudicator_evidence"]) - 1]}]
            audit["evidence_index_maps"]["b"] = [0, None, 1]
            audit.update(raw_sha256=digest(raw), projected_sha256=digest(projected),
                         shadow_pending_comparison_count=1)
            before = copy.deepcopy((raw, projected, audit))
            with mock.patch.object(M.physical, "prepare_initial_adjudication_for_review", side_effect=AssertionError("No preparer")):
                result = validate(raw, projected, audit)
            self.assertEqual(result["audit_version"], "independent_initial_context_projection_audit_v0.2")
            self.assertEqual(result["shadow_pending_comparison_count"], 1)
            self.assertEqual((raw, projected, audit), before)
            audit["shadow_pending_comparison_count"] = 0
            with self.assertRaisesRegex(M.InitialContextAuditError, "Quarantine audit differs"):
                validate(raw, projected, audit)

    def test_old_empty_confirmation_is_fatal_despite_new_working_policy(self):
        raw, projected, audit = example()
        for ledger in (raw, projected):
            ledger["clusters"][0]["identity_comparisons"][0]["evidence_indices"] = []
        audit.update(raw_sha256=digest(raw), projected_sha256=digest(projected), shadow_pending_comparison_count=1)
        with self.assertRaisesRegex(M.InitialContextAuditError, "invalid evidence indices"):
            validate(raw, projected, audit)

    def test_v02_empty_does_not_hide_other_reference_structure_or_scope_errors(self):
        mutations = {
            "null": lambda r: r["clusters"][0]["identity_comparisons"][0].update(evidence_indices=None),
            "missing": lambda r: r["clusters"][0]["identity_comparisons"][0].pop("evidence_indices"),
            "bool": lambda r: r["clusters"][0]["identity_comparisons"][0].update(evidence_indices=[True]),
            "float": lambda r: r["clusters"][0]["identity_comparisons"][0].update(evidence_indices=[0.0]),
            "out_of_bounds": lambda r: r["clusters"][0]["identity_comparisons"][0].update(evidence_indices=[4]),
            "duplicate": lambda r: r["clusters"][0]["identity_comparisons"][0].update(evidence_indices=[0, 0]),
            "noncomparable": lambda r: r["clusters"][0]["identity_comparisons"][0].update(scope_relation="whole_part"),
            "unknown": lambda r: r["clusters"][0]["identity_comparisons"][1].update(other_cluster_id="absent"),
            "self": lambda r: r["clusters"][0]["identity_comparisons"][1].update(other_cluster_id="a"),
            "duplicate_partner": lambda r: r["clusters"][0]["identity_comparisons"][1].update(other_cluster_id="b"),
            "later_frame": lambda r: r["clusters"][2]["adjudicator_evidence"][0].update(frame_id=True),
            "ownership": lambda r: r["clusters"][2].update(anonymous_proposal_ids=["p0003"]),
            "wide_positive": lambda r: r["clusters"][0]["identity_comparisons"][1].update(
                judgment="confirmed_distinct", scope_relation="comparable"),
        }
        for name, mutation in mutations.items():
            with self.subTest(name=name):
                raw, projected, audit = example("v0.2")
                for ledger in (raw, projected):
                    ledger["clusters"][0]["identity_comparisons"][0]["evidence_indices"] = []
                mutation(raw)
                audit.update(raw_sha256=digest(raw), projected_sha256=digest(projected), shadow_pending_comparison_count=1)
                with self.assertRaises(M.InitialContextAuditError):
                    validate(raw, projected, audit)

    def test_unknown_and_mixed_policies_are_not_audit_flags(self):
        for context, pending in (("v0.1", "v0.2"), ("v0.2", "v0.1"), ("v9", "v9")):
            raw, projected, audit = example()
            audit.update(policy_version="initial_context_quarantine_" + context,
                         shadow_validation_policy="initial_identity_pending_" + pending)
            with self.assertRaisesRegex(M.InitialContextAuditError, "Unsupported or mixed"):
                validate(raw, projected, audit)
            result = M.audit_context_review_dispositions(projected, projected, audit, reports(raw))
            self.assertFalse(result["all_required_scopes_reviewed"])

    def test_v02_disposition_accepts_honest_uncertain_context_coverage(self):
        raw, projected, audit = example("v0.2")
        result = M.audit_context_review_dispositions(projected, projected, audit, reports(raw))
        self.assertTrue(result["all_required_scopes_reviewed"])
        self.assertFalse(result["pixel_truth_verified"])

    def test_projection_no_context_is_identity_and_cannot_overwrite_original_audit(self):
        raw, projected, audit = example()
        clean_audit = {**audit, "raw_sha256": digest(projected), "projected_sha256": digest(projected),
                       "quarantined_evidence": [], "review_scope_ids": [],
                       "evidence_index_maps": {"a": [0, 1], "b": [0], "c": [0]}}
        self.assertEqual(validate(projected, projected, clean_audit)["quarantined_evidence_count"], 0)
        with self.assertRaises(M.InitialContextAuditError):
            validate(raw, projected, clean_audit)

    def test_honest_uncertain_exact_scope_reviews_are_complete_not_visual_truth(self):
        raw, projected, audit = example()
        views = reports(raw)
        before = copy.deepcopy((projected, audit, views))
        result = M.audit_context_review_dispositions(projected, projected, audit, views)
        self.assertTrue(result["all_required_scopes_reviewed"])
        self.assertEqual(len(result["records"]), 3)
        self.assertFalse(result["pixel_truth_verified"])
        self.assertEqual((projected, audit, views), before)
        self.assertEqual(result["records"][0]["verifier_coverage"][0]["judgments"]["existence_judgment"], "uncertain")

    def test_missing_partial_union_or_duplicate_reviews_and_same_verifier_id_fail_coverage(self):
        for variant in ("missing_report", "same_id", "missing_scope", "duplicate_scope", "partial", "two_partials", "union", "bad_enum", "bad_frame"):
            raw, projected, audit = example()
            views = reports(raw)
            if variant == "missing_report":
                views.pop()
            elif variant == "same_id":
                views[1]["verifier_id"] = views[0]["verifier_id"]
            elif variant == "missing_scope":
                views[1]["reviews"].pop()
            elif variant == "duplicate_scope":
                views[1]["reviews"].append(copy.deepcopy(views[1]["reviews"][0]))
            elif variant == "bad_enum":
                views[1]["reviews"][0]["existence_judgment"] = "made_up"
            elif variant == "bad_frame":
                views[1]["reviews"][0]["evidence"][0]["frame_id"] = 10.0
            else:
                evidence = views[1]["reviews"][0]["evidence"]
                evidence[0]["anonymous_proposal_ids"] = ["p0001"] if variant != "union" else ["p0001", "p0002", "p0003"]
                if variant == "two_partials":
                    evidence.append(F.evidence(["p0002"], "unresolved"))
            with self.subTest(variant=variant):
                result = M.audit_context_review_dispositions(projected, projected, audit, views)
                self.assertFalse(result["all_required_scopes_reviewed"])
                self.assertTrue(result["unresolved_coverage_risk"])
                self.assertTrue(result["errors"])

    def test_reject_abstain_and_scope_changes_preserve_coverage_but_keep_risk(self):
        for variant in ("reject", "abstain", "merge", "split"):
            raw, projected, audit = example()
            final = copy.deepcopy(projected)
            if variant in {"reject", "abstain"}:
                final["clusters"][0].update(decision=variant, final_entity=None)
            elif variant == "merge":
                final["clusters"][0]["anonymous_proposal_ids"] += final["clusters"][1]["anonymous_proposal_ids"]
                final["clusters"].pop(1)
            else:
                final["clusters"][0]["anonymous_proposal_ids"] = ["p0001"]
                final["clusters"].append(F.cluster("child", ["p0002"]))
            result = M.audit_context_review_dispositions(projected, final, audit, reports(raw))
            self.assertTrue(result["all_required_scopes_reviewed"])
            self.assertTrue(result["unresolved_coverage_risk"])
            self.assertTrue(all(row["all_proposals_accounted_for"] for row in result["records"]))

    def test_changed_cluster_id_at_same_exact_scope_preserves_complete_destination(self):
        raw, projected, audit = example()
        final = copy.deepcopy(projected)
        final["clusters"][0]["cluster_id"] = "new_id"
        result = M.audit_context_review_dispositions(projected, final, audit, reports(raw))
        self.assertTrue(result["all_required_scopes_reviewed"])
        self.assertFalse(result["unresolved_coverage_risk"])
        self.assertEqual(result["records"][0]["final_dispositions"][0]["cluster_id"], "new_id")

    def test_tampered_forced_scope_and_final_missing_or_duplicate_proposals_are_invalid(self):
        for variant in ("missing_forced", "bad_observation_hash", "missing_final", "duplicate_final"):
            raw, projected, audit = example()
            final = copy.deepcopy(projected)
            if variant == "missing_forced":
                audit["review_scope_ids"].pop()
            elif variant == "bad_observation_hash":
                audit["quarantined_evidence"][0]["observation_sha256"] = "0" * 64
            elif variant == "missing_final":
                final["clusters"].pop()
            else:
                final["clusters"].append(F.cluster("extra", ["p0004"]))
            result = M.audit_context_review_dispositions(projected, final, audit, reports(raw))
            self.assertFalse(result["all_required_scopes_reviewed"])
            self.assertTrue(result["errors"])

    def test_typed_but_invalid_positive_verifier_reference_does_not_count_as_coverage(self):
        raw, projected, audit = example()
        views = reports(raw)
        views[1]["reviews"][2]["identity_comparisons"] = [{
            "other_cluster_id": "a", "judgment": "confirmed_distinct", "scope_relation": "comparable",
            "evidence_indices": [0],
        }]
        result = M.audit_context_review_dispositions(projected, projected, audit, views)
        self.assertFalse(result["all_required_scopes_reviewed"])
        self.assertTrue(result["unresolved_coverage_risk"])
        self.assertTrue(result["errors"])

    def test_no_context_requires_no_verifier_and_no_changes(self):
        raw, projected, audit = example()
        audit.update(quarantined_evidence=[], review_scope_ids=[])
        result = M.audit_context_review_dispositions(projected, projected, audit, [])
        self.assertTrue(result["no_context_review_required"])
        self.assertTrue(result["all_required_scopes_reviewed"])
        self.assertFalse(result["unresolved_coverage_risk"])


if __name__ == "__main__":
    unittest.main()
