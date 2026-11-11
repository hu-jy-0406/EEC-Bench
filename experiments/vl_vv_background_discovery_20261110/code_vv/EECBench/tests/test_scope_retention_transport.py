"""Explicit optional transport: additive subset proof, unchanged parent duties."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest

import jsonschema


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import initial_context_review_audit as C  # noqa: E402
import proposal_scope_retention as R  # noqa: E402
import scope_retention_transport as T  # noqa: E402
import test_initial_context_review_audit as F  # noqa: E402


def request():
    return {
        "parent_cluster_id": "a", "parent_anonymous_proposal_ids": ["p0001", "p0002"],
        "retained_anonymous_proposal_ids": ["p0001"], "residual_anonymous_proposal_ids": ["p0002"],
        "existence_judgment": "confirmed", "salience_judgment": "graph_worthy",
        "proposal_scope_judgment": "resolved_single_scope", "residual_status": "unresolved",
        "retained_evidence": [F.F.evidence(["p0001"])],
        "physical_evidence_indices": [0], "scope_evidence_indices": [0],
        "reason": "A direct subset outline is supported; the remaining original claim is unresolved.",
    }


def example():
    _, initial, quarantine = F.example("v0.2")
    reports = F.reports(initial)
    for report in reports:
        report.update(scope_retention_policy=T.POLICY_VERSION, retention_requests=[request()])
    return initial, quarantine, reports


class ScopeRetentionTransportTests(unittest.TestCase):
    def project(self, report, initial, **kwargs):
        return T.validate_and_project_verifier(
            report, policy=kwargs.pop("policy", T.POLICY_VERSION),
            initial_decisions=initial, valid_frame_ids=kwargs.pop("valid_frame_ids", [10]), **kwargs)

    def test_full_schema_preserves_every_old_definition_and_request_fields(self):
        core = json.loads(T.CORE_SCHEMA_PATH.read_text())
        extended = json.loads(T.SCHEMA_PATH.read_text())
        schema_request = extended["$defs"]["retention_request"]
        self.assertEqual(set(schema_request["properties"]), R.REQUEST_FIELDS)
        self.assertEqual(set(schema_request["required"]), R.REQUEST_FIELDS)
        self.assertEqual(set(extended["$defs"]["evidence"]["properties"]), R.EVIDENCE_FIELDS)
        self.assertEqual(extended["properties"]["schema_version"], core["properties"]["schema_version"])
        stripped = deepcopy(extended)
        stripped["$id"], stripped["title"] = core["$id"], core["title"]
        stripped["required"] = [key for key in stripped["required"] if key not in T.EXTENSION_FIELDS]
        for key in T.EXTENSION_FIELDS:
            stripped["properties"].pop(key)
        stripped["$defs"].pop("retention_request")
        self.assertEqual(stripped, core)
        self.assertNotIn('"uniqueItems"', T.SCHEMA_PATH.read_text())

    def test_projection_only_drops_two_fields_and_never_mutates_raw_or_failed_costs(self):
        initial, _, reports = example()
        failed_attempts = [{"status": "failed", "subprocess_started": True,
                            "usage": {"input_tokens": 19, "output_tokens": 7}},
                           {"status": "failed", "subprocess_started": None, "usage": None}]
        before = deepcopy((initial, reports, failed_attempts))
        core = self.project(reports[0], initial)
        expected = {key: value for key, value in reports[0].items() if key not in T.EXTENSION_FIELDS}
        self.assertEqual(core, expected)
        jsonschema.Draft202012Validator(json.loads(T.CORE_SCHEMA_PATH.read_text())).validate(core)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(json.loads(T.CORE_SCHEMA_PATH.read_text())).validate(reports[0])
        core["reviews"][0]["evidence"].clear()
        self.assertEqual((initial, reports, failed_attempts), before)

    def test_disabled_legacy_is_exact_and_enabled_never_adopts_old_reports(self):
        initial, _, reports = example()
        old = F.reports(initial)[0]
        self.assertEqual(self.project(old, initial, policy=T.DISABLED), old)
        for policy, report in ((T.POLICY_VERSION, old), (T.DISABLED, reports[0]),
                               ("unknown_v7", old), (None, old)):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                self.project(report, initial, policy=policy)
        for field in T.EXTENSION_FIELDS:
            altered = deepcopy(reports[0])
            altered.pop(field)
            with self.assertRaises(ValueError):
                self.project(altered, initial)

    def test_empty_requests_and_independent_uncertain_parent_review_are_valid(self):
        initial, _, reports = example()
        self.assertEqual(reports[0]["reviews"][0]["existence_judgment"], "uncertain")
        reports[0]["retention_requests"][0]["retained_evidence"][0]["support_quality"] = "weak"
        core = self.project(reports[0], initial)
        self.assertEqual(core["reviews"][0]["existence_judgment"], "uncertain")
        reports[0]["retention_requests"] = []
        self.project(reports[0], initial, eligible_parent_ids=[])

    def test_protected_nonaccept_and_explicit_eligibility_cannot_be_bypassed(self):
        for variant in ("reject", "abstain", "group_member_conflict", "possible_compact_assembly_partition"):
            initial, _, reports = example()
            if variant in ("reject", "abstain"):
                initial["clusters"][0].update(decision=variant, final_entity=None)
            else:
                initial["clusters"][0]["uncertainty_flags"] = [variant]
            for eligible in (None, ["a"]):
                with self.subTest(variant=variant, eligible=eligible), self.assertRaises(ValueError):
                    self.project(reports[0], initial, eligible_parent_ids=eligible)
        initial, _, reports = example()
        self.project(reports[0], initial, eligible_parent_ids=["a"])
        for eligible in ([], ["a", "b"], ["unknown"], ["a", "a"]):
            with self.subTest(eligible=eligible), self.assertRaises(ValueError):
                self.project(reports[0], initial, eligible_parent_ids=eligible)

    def test_requests_cannot_omit_old_parent_review_or_duplicate_parent(self):
        for change in ("missing_review", "duplicate_request", "unknown_parent", "wrong_shot"):
            initial, _, reports = example()
            report = reports[0]
            if change == "missing_review":
                report["reviews"].pop(0)
            elif change == "duplicate_request":
                report["retention_requests"] *= 2
            elif change == "unknown_parent":
                report["retention_requests"][0]["parent_cluster_id"] = "other"
            else:
                report["shot_id"] = "other"
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.project(report, initial)

    def test_subset_proof_rejects_original_parent_witness_and_invalid_indices(self):
        mutations = [
            lambda r: r["retained_evidence"][0].update(anonymous_proposal_ids=["p0001", "p0002"]),
            lambda r: r["retained_evidence"][0].update(cue_type="category_only"),
            lambda r: r.update(residual_anonymous_proposal_ids=["p0001"]),
            lambda r: r.update(physical_evidence_indices=[True]),
            lambda r: r.update(scope_evidence_indices=[0.0]),
            lambda r: r.update(physical_evidence_indices=[1]),
            lambda r: r["retained_evidence"][0].update(frame_id=10.0),
            lambda r: r["retained_evidence"][0].update(frame_id=11),
            lambda r: r["retained_evidence"][0].update(observation="  "),
        ]
        for mutate in mutations:
            initial, _, reports = example()
            mutate(reports[0]["retention_requests"][0])
            before = deepcopy(reports)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                self.project(reports[0], initial)
            self.assertEqual(reports, before)

    def test_initial_universe_frame_types_and_full_old_schema_remain_strict(self):
        initial, _, reports = example()
        for frames in ([], [10, 10], [True], [10.0]):
            with self.subTest(frames=frames), self.assertRaises(ValueError):
                self.project(reports[0], initial, valid_frame_ids=frames)
        for mutate in (
            lambda x: x["clusters"][1].update(anonymous_proposal_ids=["p0001"]),
            lambda x: x["clusters"][0].update(anonymous_proposal_ids=["p0001"]),
        ):
            bad = deepcopy(initial)
            mutate(bad)
            with self.assertRaises(ValueError):
                self.project(reports[0], bad)
        for field in ("identity_comparisons", "proposed_physical_units", "pairwise_physical_separation_evidence"):
            bad = deepcopy(reports[0])
            bad["reviews"][0].pop(field)
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.project(bad, initial)

    def test_projection_audit_binds_canonical_objects_and_separate_schema_bytes(self):
        initial, _, reports = example()
        raw = reports[0]
        core = self.project(raw, initial)
        audit = T.build_projection_audit(raw, core, policy=T.POLICY_VERSION)
        self.assertEqual(audit["raw_report_sha256"], F.digest(raw))
        self.assertEqual(audit["core_report_sha256"], F.digest(core))
        self.assertNotEqual(audit["raw_report_sha256"], audit["core_report_sha256"])
        self.assertEqual(audit["selected_schema"]["sha256"], hashlib.sha256(T.SCHEMA_PATH.read_bytes()).hexdigest())
        self.assertIsNone(audit["raw_file_sha256"])
        self.assertTrue(audit["raw_file_hash_requires_caller"])
        self.assertFalse(audit["pixel_truth_verified"])
        core["reviews"][0]["reason"] = "Rewritten evidence rationale"
        with self.assertRaisesRegex(ValueError, "beyond"):
            T.build_projection_audit(raw, core, policy=T.POLICY_VERSION)


class RetentionContextCoverageTests(unittest.TestCase):
    def audit(self, initial, quarantine, reports, policy=T.POLICY_VERSION):
        return C.audit_context_review_dispositions(
            initial, initial, quarantine, reports, scope_retention_policy=policy)

    def test_extended_raw_explicit_projection_preserves_uncertain_original_coverage(self):
        initial, quarantine, reports = example()
        before = deepcopy((initial, quarantine, reports))
        result = self.audit(initial, quarantine, reports)
        self.assertTrue(result["all_required_scopes_reviewed"])
        self.assertEqual(len(result["verifier_projections"]), 2)
        self.assertEqual(result["verifier_projections"][0]["raw_report_sha256"], F.digest(reports[0]))
        coverage = C.validate_context_verifier_coverage(
            reports[0], initial_decisions=initial, required_scope_ids=["a"], verifier_id="verifier_1",
            scope_retention_policy=T.POLICY_VERSION)
        self.assertTrue(coverage[0]["complete_original_scope_review"])
        self.assertEqual(coverage[0]["judgments"]["existence_judgment"], "uncertain")
        self.assertEqual((initial, quarantine, reports), before)

    def test_retained_subset_observation_never_fills_missing_full_parent_coverage(self):
        initial, quarantine, reports = example()
        reports[0]["reviews"][0]["evidence"] = []
        result = self.audit(initial, quarantine, reports)
        self.assertFalse(result["all_required_scopes_reviewed"])
        self.assertTrue(result["errors"])
        with self.assertRaisesRegex(C.InitialContextAuditError, "Missing complete original-scope"):
            C.validate_context_verifier_coverage(
                reports[0], initial_decisions=initial, required_scope_ids=["a"], verifier_id="verifier_1",
                scope_retention_policy=T.POLICY_VERSION)

    def test_old_typed_pair_failure_is_not_laundered_by_retention_projection(self):
        initial, quarantine, reports = example()
        reports[1]["reviews"][2]["identity_comparisons"] = [{
            "other_cluster_id": "a", "judgment": "confirmed_distinct", "scope_relation": "comparable",
            "evidence_indices": [0]}]
        result = self.audit(initial, quarantine, reports)
        self.assertFalse(result["all_required_scopes_reviewed"])
        self.assertTrue(result["errors"])

    def test_disabled_unknown_and_mixed_reports_fail_even_without_forced_context(self):
        for forced in (True, False):
            initial, quarantine, reports = example()
            if not forced:
                quarantine.update(quarantined_evidence=[], review_scope_ids=[])
            for policy, rows in ((T.DISABLED, reports), ("unknown_v4", []),
                                  (T.POLICY_VERSION, [reports[0], F.reports(initial)[1]])):
                with self.subTest(forced=forced, policy=policy):
                    result = self.audit(initial, quarantine, rows, policy)
                    self.assertFalse(result["all_required_scopes_reviewed"])
                    self.assertTrue(result["errors"])
            with self.assertRaises(C.InitialContextAuditError):
                C.validate_context_verifier_coverage(
                    reports[0], initial_decisions=initial, required_scope_ids=[], verifier_id="verifier_1")

    def test_default_old_audit_has_no_retention_metadata_or_positive_requirement(self):
        for version in ("v0.1", "v0.2"):
            _, initial, quarantine = F.example(version)
            reports = F.reports(initial)
            result = C.audit_context_review_dispositions(initial, initial, quarantine, reports)
            self.assertTrue(result["all_required_scopes_reviewed"])
            self.assertNotIn("scope_retention_policy", result)
            self.assertNotIn("verifier_projections", result)
            self.assertFalse(result["pixel_truth_verified"])
        quarantine.update(quarantined_evidence=[], review_scope_ids=[])
        result = C.audit_context_review_dispositions(initial, initial, quarantine, [])
        self.assertTrue(result["all_required_scopes_reviewed"])


if __name__ == "__main__":
    unittest.main()
