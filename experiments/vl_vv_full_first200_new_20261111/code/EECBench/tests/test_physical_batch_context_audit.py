"""Bounded synthetic context-envelope artifact audits; no API or image gold."""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest import mock


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LEGACY = load("context_batch_legacy_fixture", "test_physical_batch_audit.py")
C = load("context_batch_projection_fixture", "test_initial_context_review_audit.py")
A = LEGACY.AUDIT


class PhysicalBatchContextAuditTests(unittest.TestCase):
    def setUp(self):
        self.f = LEGACY.PhysicalBatchAuditTests("test_complete_valid_graph_merge_is_integrity_only")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.raw, self.projected, self.quarantine = C.example()
        self.reports = C.reports(self.raw)
        self.usage = {"input_tokens": 30, "cached_input_tokens": 2, "output_tokens": 10, "total_tokens": 40}
        f = self.f
        for name in A.CONTEXT_SOURCES:
            path = f.root / "frozen_workspace" / name
            path.write_text("raise AssertionError('Frozen code must never execute')\n")
            f.batch["source_hashes"][name] = A.file_hash(path)
            f.manifest["stage_source_hashes"][str(path)] = A.file_hash(path)
        self.set_contract_version("v0.1")
        frame = f.folder / "input_bundle/frame_000010.jpg"
        frame.parent.mkdir()
        frame.write_bytes(b"synthetic attachment, not image gold")
        f.manifest["input_hashes"] = {str(frame): A.file_hash(frame)}
        f.batch["input_hashes"] = {"synthetic/" + frame.name: A.file_hash(frame)}
        self.prepare()

    def set_contract_version(self, version):
        self.version = version
        context, pending = "initial_context_quarantine_" + version, "initial_identity_pending_" + version
        self.quarantine.update(policy_version=context, shadow_validation_policy=pending)
        self.f.manifest["initial_evidence_preparation"] = {
            "version": "initial_context_then_pending_" + version, "context_policy": context,
            "pending_policy": pending, "raw_output_preserved": True,
            "final_and_verifier_validators_unchanged": True}
        for module, constant, value in (
            ("physical_identity_review", "INITIAL_PREPARATION_VERSION", pending),
            ("initial_context_quarantine", "POLICY_VERSION", context),
            ("initial_context_review_audit", "PROJECTION_AUDIT_VERSION", "independent_initial_context_projection_audit_" + version),
        ):
            name = "EECBench/scripts/" + module + ".py"
            path = self.f.root / "frozen_workspace" / name
            path.write_text(f"{constant} = {value!r}\nraise AssertionError('Frozen code must never execute')\n")
            self.f.batch["source_hashes"][name] = A.file_hash(path)
            self.f.manifest["stage_source_hashes"][str(path)] = A.file_hash(path)

    def save_artifact(self, key, payload):
        path = self.f.directory / (key + ".json")
        self.f.write(path, payload)
        self.f.manifest["artifacts"][key] = {"path": str(path), "sha256": A.file_hash(path)}

    def prepare(self):
        f = self.f
        self.quarantine.update(raw_sha256=C.digest(self.raw), projected_sha256=C.digest(self.projected))
        independent = C.validate(self.raw, self.projected, self.quarantine)
        # Construction uses the working preparer on manually validated fixtures;
        # v0.1 fixtures never use its new empty-reference exception. The auditor
        # must reconstruct the delta and enforce the frozen version independently.
        self.initial, pending = C.F.M.prepare_initial_adjudication_for_review(
            self.projected, valid_frame_ids=[10], expected_proposal_ids=["p0001", "p0002", "p0003", "p0004"])
        pending["policy_version"] = "initial_identity_pending_" + self.version
        self.final = copy.deepcopy(self.initial)
        f.physical, f.graph = self.final, copy.deepcopy(self.final)
        ids = [p for c in self.final["clusters"] for p in c["anonymous_proposal_ids"]]
        nodes = [{"graph_cluster_id": c["cluster_id"], "graph_cluster_sha256": A.content_hash(c),
                  "anonymous_proposal_ids": sorted(c["anonymous_proposal_ids"]),
                  "physical_anchor_cluster_ids": [c["cluster_id"]],
                  "physical_anchors": [{"anchor_cluster_id": c["cluster_id"], "anchor_cluster_sha256": A.content_hash(c),
                                        "anonymous_proposal_ids": sorted(c["anonymous_proposal_ids"])}],
                  "is_synthetic_graph_group": False, "same_instance_evidence_from_grouping": False}
                 for c in self.final["clusters"]]
        f.lineage.update(physical_baseline_content_sha256=A.content_hash(self.final),
                         derived_graph_content_sha256=A.content_hash(f.graph), accepted_physical_anchor_count=3,
                         accepted_graph_node_count=3, accepted_physical_anchor_ids=["a", "b", "c"],
                         accepted_physical_proposal_ids=sorted(ids), nodes=nodes)
        f.payloads.update(anonymized_candidates={"proposals": [{"anonymous_proposal_id": p} for p in ids]},
                          adjudicator_pre_granularity=f.physical, adjudicator_decisions=f.graph,
                          physical_identity_gate={"schema_version": A.SCHEMA, "records": [
                              {"cluster_id": c["cluster_id"], "anonymous_proposal_ids": sorted(c["anonymous_proposal_ids"]),
                               "result": c["decision"]} for c in self.final["clusters"]]})
        raw_path = f.folder / "codex_attempts/adjudicator_initial.json"
        f.write(raw_path, self.raw)
        initial_path = f.directory / "adjudicator_initial.json"
        self.save_artifact("adjudicator_initial", self.initial)
        self.save_artifact("initial_context_projection", self.projected)
        self.save_artifact("initial_context_quarantine", self.quarantine)
        self.save_artifact("initial_context_projection_audit", independent)
        context_path = f.directory / "initial_context_projection.json"
        pending.update(raw_output_path=str(context_path), raw_output_sha256=A.file_hash(context_path),
                       input_stage="context_projection", derived_output_path=str(initial_path),
                       derived_output_sha256=A.file_hash(initial_path), supplied_to_any_model=False,
                       raw_contract_valid=not bool(pending["pending_comparisons"]))
        self.save_artifact("initial_identity_review_preparation", pending)
        f.manifest["initial_identity_pending_review"] = {
            "policy_version": "initial_identity_pending_" + self.version, "pending_assertion_count": len(pending["pending_comparisons"]),
            "raw_assertions_preserved": True, "new_observations_created": False}
        raw_valid = True
        try:
            C.F.M.validate_adjudication_identity_fields(self.raw, valid_frame_ids=[10], expected_proposal_ids=ids)
        except ValueError:
            raw_valid = False
        self.raw_valid = raw_valid
        f.manifest["initial_context_review"] = {
            "policy_version": "initial_context_quarantine_" + self.version, "raw_output_path": str(raw_path),
            "raw_output_sha256": A.file_hash(raw_path), "raw_contract_valid": raw_valid,
            "quarantined_observation_count": len(self.quarantine["quarantined_evidence"]),
            "review_scope_ids": self.quarantine["review_scope_ids"], "proof_observations_created": False,
            "comparison_questions_created": False, "supplied_to_any_model": False, "pixel_truth_verified": False}
        f.manifest["adjudicator_initial_attempts"] = [{
            "attempt": 1, "status": "success" if raw_valid else "failed", "raw_contract_valid": raw_valid,
            "derived_contract_valid": True, "subprocess_started": True, "returncode": 0,
            "failure_kind": None if raw_valid else "python_validation", "error": None if raw_valid else "raw extension invalid",
            "recovery_status": None if raw_valid else ("initial_context_and_identity_review"
                                                       if self.quarantine["quarantined_evidence"] else "pending_identity_review"),
            "token_usage": copy.deepcopy(self.usage)}]
        f.write(f.folder / "codex_attempts/adjudicator_initial.events.jsonl", {"type": "turn.completed", "usage": self.usage})
        self.save_artifact("verification_targets", {
            "cluster_ids": self.quarantine["review_scope_ids"],
            "trigger_reasons": {c: ["initial_context_scope_review"] for c in self.quarantine["review_scope_ids"]}})
        f.manifest["artifacts"]["verifier_reports"] = {}
        for report in self.reports:
            key = report["verifier_id"]
            path = f.directory / (key + ".json")
            f.write(path, report)
            f.manifest["artifacts"]["verifier_reports"][key] = {"path": str(path), "sha256": A.file_hash(path)}
        self.save_dispositions()
        f.flush()

    def save_dispositions(self):
        disposition = C.M.audit_context_review_dispositions(self.initial, self.final, self.quarantine, self.reports)
        self.save_artifact("initial_context_review_dispositions", disposition)
        self.f.manifest["initial_context_review"].update(
            all_required_scopes_reviewed=disposition["all_required_scopes_reviewed"],
            unresolved_coverage_risk=disposition["unresolved_coverage_risk"])

    def result(self):
        self.f.flush()
        return A.audit(self.f.root)

    def valid(self):
        result = self.result()
        self.assertTrue(result["integrity_ok"], result["integrity_errors"])
        self.assertFalse(result["acceptance_evaluated"])
        return result["runs"][0]["initial_context_preparation"]

    def invalid(self, text):
        result = self.result()
        self.assertFalse(result["integrity_ok"])
        self.assertTrue(any(text in e for e in result["integrity_errors"]), result["integrity_errors"])

    def test_raw_failure_preserves_usage_and_complete_chain_recomputed(self):
        result = self.valid()
        self.assertFalse(self.raw_valid)
        self.assertTrue(result["projection_checked"] and result["dispositions_checked"])
        accounting = result["initial_attempt_accounting"]
        self.assertEqual(accounting["status"], "failed")
        self.assertEqual(accounting["known_usage_subtotal"], self.usage)
        self.assertTrue(accounting["usage_complete"])

    def test_legal_raw_context_is_success_not_invented_failure(self):
        for ledger in (self.raw, self.projected):
            ledger["clusters"][1]["identity_comparisons"] = [
                {"other_cluster_id": p, "judgment": "unresolved", "scope_relation": "group_member", "evidence_indices": []}
                for p in ("a", "c")]
        self.prepare()
        result = self.valid()
        self.assertTrue(self.raw_valid)
        self.assertEqual(result["initial_attempt_accounting"]["status"], "success")
        self.f.manifest["adjudicator_initial_attempts"][0]["status"] = "failed"
        self.invalid("initial attempt accounting mismatch: status")

    def test_pending_input_chain_is_independently_recomputed(self):
        for ledger in (self.raw, self.projected):
            ledger["clusters"][0]["identity_comparisons"][0]["evidence_indices"] = [0]
        self.quarantine["shadow_pending_comparison_count"] = 1
        self.prepare()
        self.assertEqual(self.valid()["recomputed_projection_audit"]["shadow_pending_comparison_count"], 1)
        self.initial["clusters"][0]["canonical_name"] = "unrelated modification"
        self.save_artifact("adjudicator_initial", self.initial)
        self.invalid("pending-derived ledger differs")

    def test_v02_empty_pending_complete_sidecar_is_recomputed_without_production_helpers(self):
        self.set_contract_version("v0.2")
        for ledger in (self.raw, self.projected):
            ledger["clusters"][0]["identity_comparisons"][0]["evidence_indices"] = []
        self.quarantine["shadow_pending_comparison_count"] = 1
        self.prepare()
        with mock.patch.object(C.M.physical, "prepare_initial_adjudication_for_review", side_effect=AssertionError("No preparer")):
            result = self.valid()
        self.assertEqual(result["version"], "initial_context_then_pending_v0.2")
        self.assertEqual(result["recomputed_projection_audit"]["shadow_pending_comparison_count"], 1)
        pending = A.read(self.f.directory / "initial_identity_review_preparation.json")
        row = pending["pending_comparisons"][0]
        self.assertEqual(row["evidence_indices"], [])
        self.assertEqual(row["own_anonymous_proposal_ids"], ["p0001", "p0002"])
        self.assertEqual(row["other_anonymous_proposal_ids"], ["p0003"])
        self.assertEqual(row["source_judgment"], "confirmed_distinct")
        original = copy.deepcopy(pending)
        for change in ("erase", "invent_index", "partial_scope"):
            pending = copy.deepcopy(original)
            if change == "erase":
                pending["pending_comparisons"] = []
            elif change == "invent_index":
                pending["pending_comparisons"][0]["evidence_indices"] = [0]
            else:
                pending["pending_comparisons"][0]["own_anonymous_proposal_ids"] = ["p0001"]
            self.save_artifact("initial_identity_review_preparation", pending)
            self.invalid("pending preparation/link mismatch")

    def test_v01_rejects_empty_even_when_v02_preparer_could_recover_it(self):
        for ledger in (self.raw, self.projected):
            ledger["clusters"][0]["identity_comparisons"][0]["evidence_indices"] = []
        self.quarantine.update(raw_sha256=C.digest(self.raw), projected_sha256=C.digest(self.projected),
                               shadow_pending_comparison_count=1)
        self.f.write(self.f.folder / "codex_attempts/adjudicator_initial.json", self.raw)
        raw_path = self.f.folder / "codex_attempts/adjudicator_initial.json"
        self.f.manifest["initial_context_review"]["raw_output_sha256"] = A.file_hash(raw_path)
        self.save_artifact("initial_context_projection", self.projected)
        self.save_artifact("initial_context_quarantine", self.quarantine)
        self.invalid("invalid evidence indices")

    def test_known_versions_cannot_mix_or_relabel_frozen_sources(self):
        old = copy.deepcopy(self.f.manifest["initial_evidence_preparation"])
        self.f.manifest["initial_evidence_preparation"]["pending_policy"] = "initial_identity_pending_v0.2"
        self.invalid("Mixed initial preparation envelope policies")
        self.f.manifest["initial_evidence_preparation"] = old
        for key in ("initial_context_quarantine", "initial_identity_review_preparation", "initial_context_projection_audit"):
            original = A.read(self.f.directory / (key + ".json"))
            altered = copy.deepcopy(original)
            field = "audit_version" if key.endswith("projection_audit") else "policy_version"
            altered[field] = altered[field].replace("v0.1", "v0.2")
            self.save_artifact(key, altered)
            self.invalid("Mixed preparation artifact policies")
            self.save_artifact(key, original)
        self.f.manifest["initial_evidence_preparation"] = {
            **old, "version": "initial_context_then_pending_v0.2",
            "context_policy": "initial_context_quarantine_v0.2", "pending_policy": "initial_identity_pending_v0.2"}
        self.invalid("Mixed initial preparation manifest policies")
        self.f.manifest["initial_context_review"]["policy_version"] = "initial_context_quarantine_v0.2"
        self.f.manifest["initial_identity_pending_review"]["policy_version"] = "initial_identity_pending_v0.2"
        self.invalid("Frozen source policy does not match")

    def test_pending_recompute_enforces_version_and_typed_reference_rules(self):
        for version in ("v0.1", "v0.2"):
            for bad in (None, [True], [0.0], [-1], [99], [0, 0]):
                projected = copy.deepcopy(self.projected)
                projected["clusters"][0]["identity_comparisons"][0]["evidence_indices"] = bad
                with self.assertRaises(ValueError):
                    A._pending_projection(projected, policy_version="initial_identity_pending_" + version)
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            A._pending_projection(self.projected, policy_version="unknown")

    def test_forged_sidecar_with_refreshed_file_hash_fails(self):
        self.quarantine["evidence_index_maps"]["a"][1] = 1
        self.save_artifact("initial_context_quarantine", self.quarantine)
        self.invalid("Quarantine audit differs")

    def test_forged_projection_with_refreshed_content_and_file_hashes_fails(self):
        self.projected["clusters"][2]["canonical_name"] = "rewritten"
        self.quarantine["projected_sha256"] = C.digest(self.projected)
        self.save_artifact("initial_context_projection", self.projected)
        self.save_artifact("initial_context_quarantine", self.quarantine)
        self.invalid("Projected ledger differs")

    def test_pending_raw_link_cannot_skip_context_stage(self):
        pending = A.read(self.f.directory / "initial_identity_review_preparation.json")
        pending["raw_output_path"] = str(self.f.folder / "codex_attempts/adjudicator_initial.json")
        self.save_artifact("initial_identity_review_preparation", pending)
        self.invalid("pending preparation/link mismatch")

    def test_declared_envelope_requires_stage_hash_and_known_version(self):
        key = str(self.f.root / "frozen_workspace" / A.CONTEXT_SOURCES[0])
        old = self.f.manifest["stage_source_hashes"].pop(key)
        self.invalid("missing/mismatched stage or schema hash")
        self.f.manifest["stage_source_hashes"][key] = old
        self.f.manifest["initial_evidence_preparation"]["version"] = "unknown"
        self.invalid("Unsupported initial preparation envelope")

    def test_cached_frozen_dependency_is_not_executed_as_trusted_auditor(self):
        frozen = mock.Mock(__file__=str(self.f.root / "frozen_workspace/EECBench/scripts/physical_identity_review.py"))
        with mock.patch.dict(sys.modules, {"physical_identity_review": frozen}):
            self.invalid("Untrusted cached audit dependency")

    def test_frame_ids_are_bound_to_frozen_input_hashes(self):
        self.f.batch["input_hashes"]["synthetic/frame_000010.jpg"] = "0" * 64
        self.invalid("frame not bound to frozen input hash")

    def test_forced_target_cannot_be_erased(self):
        target = A.read(self.f.directory / "verification_targets.json")
        target["cluster_ids"].pop()
        self.save_artifact("verification_targets", target)
        self.invalid("missing forced verifier target")

    def test_report_tampering_cannot_hide_behind_saved_coverage_true(self):
        report = copy.deepcopy(self.reports[1])
        report["reviews"].pop()
        path = self.f.directory / "verifier_2.json"
        self.f.write(path, report)
        self.f.manifest["artifacts"]["verifier_reports"]["verifier_2"]["sha256"] = A.file_hash(path)
        self.invalid("saved disposition audit mismatch")

    def test_disposition_manifest_risk_not_trusted(self):
        self.f.manifest["initial_context_review"]["unresolved_coverage_risk"] = True
        self.invalid("disposition manifest mismatch")

    def test_unknown_initial_usage_is_not_zero_or_complete(self):
        self.usage = None
        self.prepare()
        usage = self.valid()["initial_attempt_accounting"]
        self.assertFalse(usage["usage_complete"])
        self.assertIsNone(usage["token_usage"])
        self.assertTrue(all(value is None for value in usage["known_usage_subtotal"].values()))

    def test_failed_attempt_usage_erasure_is_detected_from_events(self):
        self.f.manifest["adjudicator_initial_attempts"][0]["token_usage"] = None
        self.invalid("initial event/attempt usage mismatch")

    def test_running_preparation_and_awaiting_final_are_incomplete(self):
        self.f.manifest["status"] = "running"
        self.f.manifest["artifacts"].pop("initial_context_review_dispositions")
        result = self.result()
        self.assertTrue(result["integrity_ok"], result["integrity_errors"])
        self.assertFalse(result["audit_complete"])
        self.assertEqual(result["runs"][0]["initial_context_preparation"]["stage"], "awaiting_final_physical_baseline")
        for key in A.CONTEXT_ARTIFACTS:
            self.f.manifest["artifacts"].pop(key)
        result = self.result()
        self.assertTrue(result["integrity_ok"], result["integrity_errors"])
        self.assertEqual(result["runs"][0]["initial_context_preparation"]["stage"], "preparation_not_saved")

    def test_declared_success_cannot_omit_projection_chain(self):
        self.f.manifest["artifacts"].pop("initial_context_projection")
        self.invalid("incorrect artifact path: initial_context_projection")

    def test_empty_context_noop_is_valid_without_verifier_calls(self):
        self.raw = copy.deepcopy(self.projected)
        self.quarantine.update(quarantined_evidence=[], review_scope_ids=[],
                               evidence_index_maps={"a": [0, 1], "b": [0], "c": [0]})
        self.reports = []
        self.prepare()
        result = self.valid()
        self.assertTrue(result["recomputed_dispositions"]["no_context_review_required"])


if __name__ == "__main__":
    unittest.main()
