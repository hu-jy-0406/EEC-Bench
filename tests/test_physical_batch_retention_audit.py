"""Enabled retention auditor against actual orchestration with fake transport.

These fixtures add explicit synthetic native final messages; they authenticate
no real model or pixels. Production/frozen files are never edited or executed.
"""
import copy
import json
from pathlib import Path
import unittest
from unittest import mock

import test_physical_batch_audit as legacy
import test_scope_retention_pipeline as pipeline

A = legacy.AUDIT
E = pipeline.E


class _BatchFixtureRoot(type(Path())):
    """Give the reused single-shot fixture the actual batch directory contract.

    Its temporary root builds a child named 'run', while its input shot is
    'synthetic'. Resolve that one child before orchestration writes anything;
    every artifact, prompt and provenance hash then uses the real final path.
    """
    def __truediv__(self, child):
        return Path(super().__truediv__("synthetic" if child == "run" else child))


class PhysicalBatchRetentionAuditTests(unittest.TestCase):
    def prepare(self, *, empty_targets=False, **kwargs):
        fixture = pipeline.ScopeRetentionPipelineTests()
        self.addCleanup(fixture.doCleanups)
        selection = (mock.patch.object(E, "select_verification_targets", return_value=([], {})) if empty_targets
                     else mock.patch.object(E, "select_verification_targets", wraps=E.select_verification_targets))
        with selection, mock.patch.object(pipeline.P, "Path", _BatchFixtureRoot):
            _, self.manifest, self.calls, self.folder = fixture.run_fixture(**kwargs)
        self.assertEqual(self.folder.name, self.manifest["shot_id"])
        self.root = self.folder.parent
        workspace = Path(E.__file__).resolve().parents[2]
        self.batch = {"identity_review_policy": A.POLICY, "scope_retention_policy": A.RETENTION_POLICY,
                      "model_config": {"scope_retention_policy": A.RETENTION_POLICY},
                      "source_hashes": {}, "input_hashes": {},
                      "revision_output_policy": self.manifest.get("revision_output_policy", "canonical")}
        mapping = {}
        relatives = (set(A.RETENTION_SOURCES) | set(A.WIRE_SOURCES) | set(A.CONTEXT_SOURCES)
                     | set(A.PREVIEW_SOURCES) | set(A.CRITICAL_SOURCES))
        for relative in relatives:
            original = workspace / relative
            frozen = self.root / "frozen_workspace" / relative
            frozen.parent.mkdir(parents=True, exist_ok=True)
            frozen.write_bytes(original.read_bytes())
            mapping[str(original)] = str(frozen)
            self.batch["source_hashes"][relative] = A.file_hash(frozen)

        def rewrite(value):
            if type(value) is str:
                return mapping.get(value, value)
            if type(value) is list:
                return [rewrite(v) for v in value]
            if type(value) is dict:
                return {mapping.get(k, k): rewrite(v) for k, v in value.items()}
            return value

        self.manifest = rewrite(self.manifest)
        for path in (self.folder / "adjudication").glob("*.json"):
            original = A.read(path)
            updated = rewrite(original)
            if updated != original:
                self.write(path, updated)
        for path, digest in self.manifest["input_hashes"].items():
            if Path(path).name.startswith("frame_"):
                self.batch["input_hashes"][self.folder.name + "/" + Path(path).name] = digest
        # The orchestration fixture intentionally emits only thread + usage;
        # add synthetic final messages for independent raw/native comparisons.
        for row in self.manifest.get("verifier_attempts", []) + self.manifest.get("adjudicator_revision_attempts", []):
            stem = (f"{row['verifier_id']}.attempt{row['attempt']}" if "verifier_id" in row
                    else "adjudicator_revision" + ("" if row["attempt"] == 1 else ".attempt2"))
            events = self.folder / "codex_attempts" / (stem + ".events.jsonl")
            raw = events.with_name(stem + ".json")
            if events.is_file() and events.stat().st_size and raw.is_file():
                native = [json.loads(line) for line in events.read_text().splitlines()]
                native.insert(-1, {"type": "item.completed", "item": {"type": "agent_message", "text": raw.read_text()}})
                events.write_text("".join(json.dumps(e) + "\n" for e in native))
        self.refresh(self.manifest)
        provenance = self.manifest.get("artifacts", {}).get("scope_retention_provenance")
        if provenance:
            value = A.read(provenance["path"])
            value.update(verifier_successful_attempts={r["verifier_id"]: copy.deepcopy(r)
                         for r in self.manifest["verifier_attempts"] if r["status"] == "success"},
                         core_verifier_reports=copy.deepcopy(self.manifest["artifacts"]["verifier_reports"]),
                         consensus=copy.deepcopy(self.manifest["artifacts"]["scope_retention_consensus"]),
                         schema_hashes=copy.deepcopy(self.manifest["schema_hashes"]),
                         source_hashes=copy.deepcopy(self.manifest["stage_source_hashes"]),
                         reference=copy.deepcopy(self.manifest["scope_retention"]["reference"]))
            self.write(Path(provenance["path"]), value)
        self.refresh(self.manifest)
        return self

    @staticmethod
    def write(path, value):
        Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")

    def refresh(self, value):
        if type(value) is dict:
            for child in value.values():
                self.refresh(child)
            if "path" in value and "sha256" in value and Path(value["path"]).is_file():
                value["sha256"] = A.file_hash(value["path"])
        elif type(value) is list:
            for child in value:
                self.refresh(child)

    def checks(self):
        errors = []

        def check(ok, message):
            if not ok:
                errors.append(message)

        def verify(path, digest, message):
            check(A.file_hash(path) == digest, message + ": hash mismatch")
        return errors, check, verify

    def audit(self, *, terminal=True, context=False, wire=False):
        before = copy.deepcopy(self.manifest)
        errors, check, verify = self.checks()
        result = A.audit_scope_retention(self.root, self.batch, self.folder, self.manifest, check, verify)
        try:
            if context:
                A.audit_context_envelope(self.root, self.batch, self.folder, self.manifest, check, verify, retention=result)
            if wire:
                A.audit_revision_wire(self.root, self.batch, self.folder, self.manifest, check, verify, retention=result)
            if terminal and self.manifest["status"] == "success" and result is not None:
                payloads = {k: A.read(self.manifest["artifacts"][k]["path"])
                            for k in ("physical_identity_gate", "adjudicator_pre_granularity", "adjudicator_decisions")}
                A.audit_scope_retention_gate(self.folder, self.manifest, result, payloads, check, verify)
        except (ValueError, RuntimeError, KeyError, OSError) as error:
            errors.append(str(error))
        self.assertEqual(before, self.manifest, "audit must not rewrite accounting or production artifacts")
        return result, errors

    def valid(self, **kwargs):
        result, errors = self.audit(**kwargs)
        self.assertEqual(errors, [])
        return result

    def invalid(self, fragment):
        result, errors = self.audit()
        self.assertTrue(any(fragment in str(e) for e in errors), errors)
        return result

    def alter(self, key, mutate):
        link = self.manifest["artifacts"][key]
        value = A.read(link["path"])
        mutate(value)
        self.write(Path(link["path"]), value)
        self.refresh(self.manifest)

    def test_real_canonical_retention_replayed_without_routing_sidecars(self):
        self.prepare()
        result = self.valid()
        self.assertTrue(result["summary"]["gate_replayed"])
        self.assertEqual(result["summary"]["accounting"]["total_tokens"], 40)
        self.assertEqual(len(result["summary"]["transition_audit"]["audited_transitions"]), 1)
        self.assertFalse(result["summary"]["pixel_truth_verified"])
        self.assertNotIn("model_routing", self.manifest)

    def test_wire_retry_and_context_share_rebuilt_inputs(self):
        self.prepare(wire=True, context=True, fault="residual_promotion")
        result = self.valid(context=True, wire=True)
        self.assertEqual([r["status"] for r in self.manifest["adjudicator_revision_attempts"]], ["failed", "success"])
        self.assertTrue(result["summary"]["gate_replayed"])

    def test_projection_or_consensus_positive_flags_cannot_replace_replay(self):
        for location in ("core_projection", "projection_audit", "consensus"):
            with self.subTest(location=location):
                self.prepare()
                if location == "consensus":
                    self.alter("scope_retention_consensus", lambda value: value.update(automatic_acceptance=True))
                    self.invalid("native-bound rebuild")
                else:
                    link = self.manifest["verifier_attempts"][0]["scope_retention_transport"]["artifacts"][location]
                    value = A.read(link["path"])
                    if location == "core_projection":
                        value["reviews"][0]["reason"] = "forged explanation"
                    else:
                        value["core_fields_unchanged"] = False
                    self.write(Path(link["path"]), value)
                    self.refresh(self.manifest)
                    self.invalid("raw/core" if location == "core_projection" else "false projection audit")

    def test_native_mismatch_or_shared_thread_cannot_authorize(self):
        for kind in ("message", "thread"):
            with self.subTest(kind=kind):
                self.prepare()
                row = self.manifest["verifier_attempts"][0]
                path = Path(row["scope_retention_transport"]["native_events"]["path"])
                events = [json.loads(line) for line in path.read_text().splitlines()]
                if kind == "message":
                    next(e for e in events if e["type"] == "item.completed")["item"]["text"] = "{}"
                else:
                    events[0]["thread_id"] = "another-thread"
                path.write_text("".join(json.dumps(e) + "\n" for e in events))
                self.refresh(self.manifest)
                result = self.invalid("native")
                self.assertEqual(result["summary"]["accounting"]["known_usage_subtotal"]["total_tokens"], 40)

    def test_failed_validation_persistence_and_unknown_keep_all_peer_costs(self):
        for fault in ("invalid_request", "projection_persistence", "native_io", "unknown_attempt", "core_publication"):
            with self.subTest(fault=fault):
                self.prepare(fault=fault)
                result = self.valid()
                accounting = result["summary"]["accounting"]
                expected = 40 if fault in ("unknown_attempt", "core_publication") else 60
                self.assertEqual(accounting["known_usage_subtotal"]["total_tokens"], expected)
                self.assertEqual(accounting["total_tokens"], None if fault == "unknown_attempt" else expected)
                if fault == "core_publication":
                    self.assertEqual(result["summary"]["state"], "incomplete_verifier_or_consensus_persistence")
                    self.assertFalse(result["summary"]["inputs_verified"])

    def test_disabled_unknown_and_mixed_policy_rejected_without_losing_cost(self):
        for change in ("shot", "batch", "config", "unknown"):
            with self.subTest(change=change):
                self.prepare()
                if change == "shot":
                    self.manifest.pop("scope_retention_policy")
                elif change == "batch":
                    self.batch.pop("scope_retention_policy")
                elif change == "config":
                    self.batch["model_config"].clear()
                else:
                    self.manifest["scope_retention_policy"] = "future_policy"
                result = self.invalid("policy")
                self.assertEqual(result["summary"]["accounting"]["total_tokens"], 40)
        self.prepare()
        self.manifest.pop("scope_retention_policy")
        self.manifest.pop("scope_retention")
        self.batch.pop("scope_retention_policy")
        self.batch["model_config"].clear()
        for row in self.manifest["verifier_attempts"]:
            row.pop("scope_retention_transport")
        for key in list(self.manifest["artifacts"]):
            if key.startswith("scope_retention"):
                del self.manifest["artifacts"][key]
        self.invalid("disabled report contains extension")

    def test_targets_empty_has_no_fake_consensus_and_old_disabled_path_is_unchanged(self):
        self.prepare(empty_targets=True)
        result = self.valid()
        self.assertIsNone(result["consensus"])
        self.assertEqual(result["summary"]["accounting"]["total_tokens"], 0)
        self.assertIsNone(result["summary"]["transition_audit"])
        self.assertFalse(any(c["stem"].startswith("verifier_") for c in self.calls))
        errors, check, verify = self.checks()
        self.assertIsNone(A.audit_scope_retention(self.root, {}, self.folder, {"status": "success"}, check, verify))
        self.assertEqual(errors, [])

    def test_rehashed_transition_gate_or_graph_residual_tamper_rejected(self):
        for key in ("scope_retention_transition", "physical_identity_gate", "scope_retention_graph_residual_lineage"):
            with self.subTest(key=key):
                self.prepare()
                def mutate(value):
                    if key == "scope_retention_transition":
                        value["audited_transitions"] = []
                    elif key == "physical_identity_gate":
                        value["scope_retention"]["final_relation_proofs"] = [{"fabricated": True}]
                    else:
                        value["residual_proposal_owners"] = {}
                self.alter(key, mutate)
                self.invalid("replay" if key != "scope_retention_graph_residual_lineage" else "residual")
        self.prepare()
        self.alter("adjudicator_decisions", lambda value: value["clusters"][1].update(final_entity="invented"))
        self.invalid("promoted residual")

    def test_frame_eligibility_and_private_success_row_binding(self):
        for key in ("frame", "eligible", "provenance"):
            with self.subTest(key=key):
                self.prepare()
                if key == "frame":
                    self.batch["input_hashes"][next(iter(self.batch["input_hashes"]))] = "0" * 64
                elif key == "eligible":
                    self.manifest["scope_retention"]["eligible_parent_ids"] = []
                else:
                    self.alter("scope_retention_provenance", lambda value: value["verifier_successful_attempts"]["verifier_1"].update(attempt=2))
                self.invalid("frame" if key == "frame" else "eligible" if key == "eligible" else "provenance")

    def test_repair_permissions_cannot_be_rehashed_into_different_subset(self):
        self.prepare(wire=True, fault="residual_promotion")
        path = self.folder / "prompts/adjudicator_revision.attempt2.txt"
        path.write_text(path.read_text().replace('"automatic_acceptance": false', '"automatic_acceptance": true'))
        self.manifest["prompt_hashes"][path.name] = A.file_hash(path)
        self.invalid("repair changed retention permission")

    def test_frozen_semantic_drift_is_rejected_without_execution_or_cost_loss(self):
        self.prepare()
        relative = "EECBench/scripts/proposal_scope_retention.py"
        path = self.root / "frozen_workspace" / relative
        path.write_text(path.read_text() + "\nraise AssertionError('never execute frozen audit input')\n")
        self.batch["source_hashes"][relative] = A.file_hash(path)
        self.manifest["stage_source_hashes"][str(path)] = A.file_hash(path)
        result = self.invalid("unsupported frozen semantic source")
        self.assertEqual(result["summary"]["accounting"]["total_tokens"], 40)

    def test_false_persisted_and_not_reached_states_cannot_authorize(self):
        self.prepare()
        row = self.manifest["verifier_attempts"][0]
        row["scope_retention_transport"]["status"] = "not_projected"
        self.invalid("false successful projection")
        self.prepare()
        self.manifest["artifacts"].pop("verification_targets")
        self.manifest["scope_retention"]["status"] = "not_reached"
        self.invalid("false not-reached")


if __name__ == "__main__":
    unittest.main()
