"""Synthetic artifact corruption checks; no model, image gold, or pipeline import."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


PATH = Path(__file__).resolve().parents[1] / (
    "experiments/study_inconsistent_2/entity_discovery_iterations/audit_physical_batch.py"
)
SPEC = importlib.util.spec_from_file_location("physical_batch_audit_tested", PATH)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class PhysicalBatchAuditTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.shot = "synthetic"
        self.folder = self.root / "seed_7" / self.shot
        self.directory = self.folder / "adjudication"
        self.directory.mkdir(parents=True)
        self.config = {"model": "test-model", "reasoning_effort": "high",
                       "codex_wrapper": str(self.root / "execution_config/codex.sh")}
        config_path = self.root / "execution_config/model_config.json"
        self.write(config_path, self.config)
        self.batch = {"status": "success", "seeds": [7], "shots": [self.shot],
                      "identity_review_policy": AUDIT.POLICY, "model": "test-model", "reasoning_effort": "high",
                      "model_config": self.config, "execution_hashes": {str(config_path): AUDIT.file_hash(config_path)},
                      "source_hashes": {}}
        self.manifest = {"status": "success", "shot_id": self.shot, "shuffle_seed": 7, "model": "test-model",
                         "identity_review_policy": AUDIT.POLICY, "schema_hashes": {}, "stage_source_hashes": {},
                         "single_detector_consensus_gate": {"applied": False},
                         "nonmajority_generic_identity_gate": {"applied": False},
                         "physical_identity_gate": {"policy_version": AUDIT.SCHEMA}, "artifacts": {}}
        for name, group in AUDIT.CRITICAL_SOURCES.items():
            path = self.root / "frozen_workspace" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic frozen source, never imported or executed\n")
            self.batch["source_hashes"][name] = AUDIT.file_hash(path)
            if group:
                self.manifest[group][str(path)] = AUDIT.file_hash(path)
        self.launch = {"seed": 7, "command": ["python", "synthetic-replay",
                       "--codex-model", "test-model", "--ensemble-identity-review-policy", AUDIT.POLICY,
                       "--ensemble-shuffle-seed", "7", "--codex-bin", self.config["codex_wrapper"]]}
        self.physical = {"shot_id": self.shot, "protocol_version": AUDIT.BASE_PROTOCOL,
                         "schema_version": AUDIT.SCHEMA, "clusters": [
                             {"cluster_id": "a", "anonymous_proposal_ids": ["p1", "p2"], "decision": "accept"},
                             {"cluster_id": "b", "anonymous_proposal_ids": ["p3"], "decision": "accept"},
                             {"cluster_id": "r", "anonymous_proposal_ids": ["p4"], "decision": "reject"}]}
        self.graph = {**copy.deepcopy(self.physical), "clusters": [
            {"cluster_id": "g", "anonymous_proposal_ids": ["p1", "p2", "p3"], "decision": "accept"},
            copy.deepcopy(self.physical["clusters"][2])]}
        self.lineage = {
            "protocol_version": "single_shot_graph_physical_anchor_lineage_v0.1", "shot_id": self.shot,
            "physical_baseline_content_sha256": AUDIT.content_hash(self.physical),
            "derived_graph_content_sha256": AUDIT.content_hash(self.graph),
            "physical_baseline_schema_version": AUDIT.SCHEMA,
            "accepted_physical_anchor_count": 2, "accepted_graph_node_count": 1,
            "accepted_physical_anchor_ids": ["a", "b"], "accepted_physical_proposal_ids": ["p1", "p2", "p3"],
            "every_physical_anchor_mapped_exactly_once": True, "complete_proposal_universe_preserved": True,
            "graph_scopes_equal_exact_frozen_anchor_unions": True,
            "synthetic_groups_are_same_instance_evidence": False, "physical_inventory_mutated": False,
            "nodes": [{"graph_cluster_id": "g", "graph_cluster_sha256": AUDIT.content_hash(self.graph["clusters"][0]),
                       "anonymous_proposal_ids": ["p1", "p2", "p3"], "physical_anchor_cluster_ids": ["a", "b"],
                       "physical_anchors": [{"anchor_cluster_id": c["cluster_id"],
                                             "anchor_cluster_sha256": AUDIT.content_hash(c),
                                             "anonymous_proposal_ids": c["anonymous_proposal_ids"]}
                                            for c in self.physical["clusters"][:2]],
                       "is_synthetic_graph_group": True, "same_instance_evidence_from_grouping": False}]}
        self.payloads = {
            "anonymized_candidates": {"proposals": [{"anonymous_proposal_id": p} for p in ("p1", "p2", "p3", "p4")]},
            "adjudicator_pre_granularity": self.physical, "adjudicator_decisions": self.graph,
            "graph_physical_anchor_lineage": self.lineage,
            "physical_identity_gate": {"schema_version": AUDIT.SCHEMA, "records": [
                {"cluster_id": c["cluster_id"], "anonymous_proposal_ids": c["anonymous_proposal_ids"], "result": "accept"}
                for c in self.physical["clusters"][:2]]},
            "single_detector_consensus_gate": {"status": "superseded_by_physical_identity_gate", "records": []},
            "nonmajority_generic_identity_gate_private": {"status": "superseded_by_physical_identity_gate", "records": []}}
        self.flush()

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value) + "\n")

    def flush(self):
        for key, payload in self.payloads.items():
            path = self.directory / AUDIT.ARTIFACTS[key]
            self.write(path, payload)
            self.manifest["artifacts"][key] = {"path": str(path), "sha256": AUDIT.file_hash(path)}
        self.manifest["artifacts"]["adjudicator_pre_granularity"].update(
            physical_identity_gate_already_applied=True, single_detector_gate_already_applied=False,
            nonmajority_generic_identity_gate_already_applied=False)
        self.manifest["artifacts"]["graph_physical_anchor_lineage"].update(
            physical_inventory_path=str(self.directory / AUDIT.ARTIFACTS["adjudicator_pre_granularity"]),
            physical_inventory_file_sha256=self.manifest["artifacts"]["adjudicator_pre_granularity"]["sha256"],
            derived_graph_is_physical_adjudication=False, grouping_establishes_same_instance_identity=False)
        self.write(self.root / "robustness_manifest.json", self.batch)
        self.write(self.root / "seed_7.launch.json", self.launch)
        self.write(self.folder / "run_manifest.json", self.manifest)

    def assert_error(self, fragment):
        result = AUDIT.audit(self.root)
        self.assertFalse(result["integrity_ok"])
        self.assertTrue(any(fragment in error for error in result["integrity_errors"]),
                        result["integrity_errors"])
        return result

    def test_complete_valid_graph_merge_is_integrity_only(self):
        result = AUDIT.audit(self.root)
        self.assertTrue(result["integrity_ok"], result["integrity_errors"])
        self.assertTrue(result["audit_complete"])
        self.assertFalse(result["acceptance_evaluated"])
        self.assertFalse(result["pixels_reviewed"])
        self.assertTrue(result["verified_file_hashes"])

    def test_mode_and_model_transport_tampering(self):
        for owner, field, value, fragment in (
            (self.batch, "identity_review_policy", "legacy", "was not selected"),
            (self.manifest, "identity_review_policy", "legacy", "mode transport"),
            (self.manifest, "model", "different-model", "model transport"),
        ):
            original = owner[field]
            owner[field] = value
            self.flush()
            self.assert_error(fragment)
            owner[field] = original
        for flag, value in (("--codex-model", "different-model"), ("--ensemble-identity-review-policy", "legacy")):
            position = self.launch["command"].index(flag) + 1
            original = self.launch["command"][position]
            self.launch["command"][position] = value
            self.flush()
            self.assert_error("incorrect launch option " + flag)
            self.launch["command"][position] = original

    def test_legacy_gate_and_schema_claims_are_checked(self):
        self.manifest["single_detector_consensus_gate"]["applied"] = True
        self.flush()
        self.assert_error("legacy gate applied")
        self.manifest["single_detector_consensus_gate"]["applied"] = False
        self.payloads["single_detector_consensus_gate"]["records"] = [{"result": "accept"}]
        self.flush()
        self.assert_error("nonempty/applied legacy artifact")
        self.payloads["single_detector_consensus_gate"]["records"] = []
        self.manifest["schema_hashes"].clear()
        self.flush()
        self.assert_error("missing/mismatched physical schema")

    def test_partial_anchor_fails_after_outer_hashes_are_updated(self):
        self.graph["clusters"][0]["anonymous_proposal_ids"] = ["p1", "p3"]
        self.graph["clusters"].append({"cluster_id": "fragment", "anonymous_proposal_ids": ["p2"], "decision": "accept"})
        self.lineage["derived_graph_content_sha256"] = AUDIT.content_hash(self.graph)
        self.flush()
        self.assert_error("partial physical anchor")

    def test_duplicate_proposal_or_lineage_record_fails(self):
        self.graph["clusters"].append({"cluster_id": "duplicate", "anonymous_proposal_ids": ["p1"], "decision": "accept"})
        self.flush()
        self.assert_error("duplicate proposal ownership")
        self.graph["clusters"].pop()
        self.lineage["nodes"].append(copy.deepcopy(self.lineage["nodes"][0]))
        self.flush()
        self.assert_error("duplicate graph record")

    def test_forged_record_hashes_fail_even_after_file_hash_refresh(self):
        node = self.lineage["nodes"][0]
        for record, key in ((node, "graph_cluster_sha256"), (node["physical_anchors"][0], "anchor_cluster_sha256")):
            original = record[key]
            record[key] = "0" * 64
            self.flush()
            result = self.assert_error("incorrect scope/hash/anchor record")
            self.assertFalse(any("file hash mismatch" in error for error in result["integrity_errors"]))
            record[key] = original
        self.lineage["physical_baseline_content_sha256"] = "0" * 64
        self.flush()
        self.assert_error("incorrect physical_baseline_content_sha256")

    def test_complete_universe_includes_rejected_proposals(self):
        self.graph["clusters"].pop()
        self.lineage["derived_graph_content_sha256"] = AUDIT.content_hash(self.graph)
        self.flush()
        self.assert_error("complete proposal universe changed")

    def test_shared_ledger_omission_cannot_hide_behind_matching_lineage(self):
        self.physical["clusters"].pop()
        self.graph["clusters"].pop()
        self.lineage["physical_baseline_content_sha256"] = AUDIT.content_hash(self.physical)
        self.lineage["derived_graph_content_sha256"] = AUDIT.content_hash(self.graph)
        self.flush()
        self.assert_error("does not conserve original anonymous proposal universe")

    def test_artifact_hash_mismatch_and_missing_terminal_artifact(self):
        path = self.directory / AUDIT.ARTIFACTS["graph_physical_anchor_lineage"]
        path.write_text(path.read_text() + " ")
        self.assert_error("file hash mismatch")
        path.unlink()
        self.assert_error("malformed/missing artifact")

    def test_running_and_not_started_are_explicitly_incomplete(self):
        self.batch["status"] = self.manifest["status"] = "running"
        self.flush()
        result = AUDIT.audit(self.root)
        self.assertTrue(result["integrity_ok"], result["integrity_errors"])
        self.assertFalse(result["audit_complete"])
        self.assertFalse(result["runs"][0]["lineage_checked"])
        (self.folder / "run_manifest.json").unlink()
        result = AUDIT.audit(self.root)
        self.assertTrue(result["integrity_ok"], result["integrity_errors"])
        self.assertFalse(result["audit_complete"])
        self.assertEqual(result["runs"][0]["status"], "not_started")


if __name__ == "__main__":
    unittest.main()
