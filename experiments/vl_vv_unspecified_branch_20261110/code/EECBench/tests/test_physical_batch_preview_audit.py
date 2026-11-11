"""Mutation checks for first-revision preview provenance; synthetic calls only."""
import copy
import json
from pathlib import Path
import unittest
from unittest import mock

import test_physical_batch_audit as legacy
import test_physical_identity_pipeline as pipeline
import physical_review_obligations as obligations


A = legacy.AUDIT
E = pipeline.ENSEMBLE


class PhysicalBatchPreviewAuditTests(unittest.TestCase):
    def setUp(self):
        original = pipeline.review

        def ambiguous(anchor):
            row = original(anchor)
            row["salience_judgment"] = "ambiguous"
            return row

        with mock.patch.object(pipeline, "review", side_effect=ambiguous):
            _, self.manifest, self.calls, self.folder = pipeline.PhysicalIdentityPipelineTest.run_pipeline(self)
        self.root = self.folder.parent
        self.batch = {"source_hashes": {}}
        self.adj = self.folder / "adjudication"
        self.private_path = self.adj / A.PREVIEW_FILES["first_revision_obligation_preview_provenance"]
        self.private = A.read(self.private_path)
        self.status = self.manifest["first_revision_obligation_preview"]
        self.frozen_sources = {}
        scripts = Path(E.__file__).resolve().parent
        for relative in A.PREVIEW_SOURCES:
            target = self.root / "frozen_workspace" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((scripts / target.name).read_bytes())
            digest = A.file_hash(target)
            self.batch["source_hashes"][relative] = digest
            self.frozen_sources[str(target)] = digest
            self.manifest["stage_source_hashes"][str(target)] = digest
        self.private["source_hashes"] = self.frozen_sources
        self.save_private()
        self.original_manifest = copy.deepcopy(self.manifest)

    def write(self, path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")

    def save_private(self):
        self.write(self.private_path, self.private)
        link = {"path": str(self.private_path), "sha256": A.file_hash(self.private_path)}
        self.manifest["artifacts"]["first_revision_obligation_preview_provenance"] = link
        self.status["provenance"] = copy.deepcopy(link)

    def save_prompt(self, text):
        path = self.folder / "prompts/adjudicator_revision.txt"
        path.write_text(text)
        self.manifest["prompt_hashes"][path.name] = A.file_hash(path)

    def check_audit(self):
        errors = []
        before = copy.deepcopy(self.manifest)

        def check(ok, message):
            if not ok:
                errors.append(message)

        def verify(path, expected, label):
            try:
                check(A.file_hash(path) == expected, label + ": file hash mismatch")
            except OSError as error:
                errors.append(str(error))

        try:
            result = A.audit_first_revision_preview(
                self.root, self.batch, self.folder, self.manifest, check, verify)
        except (ValueError, KeyError, TypeError, AttributeError, OSError) as error:
            errors.append(str(error))
            result = None
        self.assertEqual(self.manifest, before)
        return result, errors

    def valid(self):
        result, errors = self.check_audit()
        self.assertEqual(errors, [])
        self.assertFalse(result["acceptance_evaluated"])
        return result

    def invalid(self, fragment):
        _, errors = self.check_audit()
        self.assertTrue(any(fragment in error for error in errors), errors)

    def unavailable(self, *, provenance=True):
        checklist = A.read(self.adj / A.PREVIEW_FILES["first_revision_obligation_checklist"])
        supplement = "\n\n" + obligations.first_revision_preview_prompt(checklist)
        path = self.folder / "prompts/adjudicator_revision.txt"
        text = path.read_text()
        self.assertTrue(text.endswith(supplement))
        self.save_prompt(text[:-len(supplement)])
        self.status.update(status="unavailable", included_in_revision_prompt=False,
                           error_stage="persist_first_revision_obligation_checklist",
                           error_type="OSError", error="synthetic write failure")
        for key in ("has_obligations", "cluster_obligation_count", "pair_obligation_count", "supplement_sha256"):
            self.status.pop(key, None)
        unused = {}
        for key in ("first_revision_physical_gate_preview.private", "first_revision_obligation_checklist"):
            unused[key] = self.manifest["artifacts"].pop(key)
        self.private.update({k: v for k, v in self.status.items() if k != "provenance"})
        self.private["unused_partial_artifacts"] = unused
        if provenance:
            self.save_private()
        else:
            self.status.pop("provenance", None)
            self.status["unavailable_provenance_write_error"] = {"type": "OSError", "error": "disk unavailable"}
            self.manifest["artifacts"].pop("first_revision_obligation_preview_provenance")

    def test_actual_helper_ready_replays_without_producer_or_frozen_execution(self):
        frozen = self.root / "frozen_workspace" / A.PREVIEW_SOURCES[-1]
        frozen.write_text(frozen.read_text() + "\nraise AssertionError('never import frozen code')\n")
        digest = A.file_hash(frozen)
        self.batch["source_hashes"][A.PREVIEW_SOURCES[-1]] = digest
        self.manifest["stage_source_hashes"][str(frozen)] = digest
        self.private["source_hashes"][str(frozen)] = digest
        self.save_private()
        with mock.patch.object(E, "_prepare_first_revision_obligation_preview", side_effect=AssertionError("no producer replay")):
            result = self.valid()
        self.assertTrue(result["replayed"] and result["prompt_inclusion_checked"])
        self.assertEqual(result["revision_accounting"]["recorded_revision_total_tokens"], 20)
        self.assertEqual(self.manifest["token_usage"], self.original_manifest["token_usage"])

    def test_status_policy_source_and_summary_tampering(self):
        for key, value, fragment in (
            ("policy_version", "future_v9", "Unsupported"),
            ("status", "applied", "Unsupported"),
            ("included_in_revision_prompt", False, "invalid state flag"),
            ("cluster_obligation_count", 0, "ready summary"),
            ("additional_model_calls", 1, "invalid active state flag"),
        ):
            original = self.status[key]
            self.status[key] = value
            self.invalid(fragment)
            self.status[key] = original
        self.private["source_hashes"].clear()
        self.save_private()
        self.invalid("private frozen source")

    def test_checklist_and_gate_rehashing_cannot_forge_replay(self):
        for key, field in (("first_revision_obligation_checklist", "has_obligations"),
                           ("first_revision_physical_gate_preview.private", "changed_to_abstain_count")):
            path = self.adj / A.PREVIEW_FILES[key]
            original = path.read_bytes()
            value = A.read(path)
            value[field] = False if field == "has_obligations" else 800
            self.write(path, value)
            link = self.manifest["artifacts"][key]
            link["sha256"] = A.file_hash(path)
            self.private["artifacts"][key] = copy.deepcopy(link)
            self.save_private()
            self.invalid("replay mismatch")
            path.write_bytes(original)
            link["sha256"] = A.file_hash(path)
            self.private["artifacts"][key] = copy.deepcopy(link)
            self.save_private()

    def test_target_split_and_proposal_input_references_are_bound(self):
        for key in ("target_ids_content_sha256", "identity_pairs_content_sha256",
                    "split_challenges_content_sha256", "target_reasons_content_sha256"):
            old = self.private["verification_targets"][key]
            self.private["verification_targets"][key] = "0" * 64
            self.save_private()
            self.invalid("target field hash")
            self.private["verification_targets"][key] = old
        for key in ("prepared_initial", "raw_initial", "split_consensus"):
            old = self.private[key]["content_sha256"]
            self.private[key]["content_sha256"] = "1" * 64
            self.save_private()
            self.invalid("input content hash")
            self.private[key]["content_sha256"] = old
        self.private["preparation_artifacts"] = {}
        self.save_private()
        self.invalid("preparation links")

    def test_actual_prompt_missing_changed_duplicate_and_prefix_rehash(self):
        path = self.folder / "prompts/adjudicator_revision.txt"
        original = path.read_text()
        start = original.index("\n\n" + obligations.FIRST_REVISION_PREVIEW_INSTRUCTION)
        for text in (original[:start], original + original[start:],
                     original.replace("PARTIAL physical-contract", "COMPLETE physical-contract"),
                     "changed original prefix\n" + original):
            self.save_prompt(text)  # Outer hash alone is insufficient.
            self.invalid("supplement" if text != "changed original prefix\n" + original else "prefix hash")
        self.save_prompt(original)

    def test_unavailable_is_not_applied_and_does_not_replay_transient_error(self):
        self.unavailable()
        with mock.patch.object(obligations, "build_physical_review_obligations", side_effect=AssertionError("do not reconstruct failure")):
            result = self.valid()
        self.assertFalse(result["replayed"])
        self.assertTrue(result["prompt_inclusion_checked"])
        self.save_prompt((self.folder / "prompts/adjudicator_revision.txt").read_text() + "\npartial_obligation_preview:\n{}")
        self.invalid("unavailable supplement")

    def test_unavailable_provenance_write_failure_is_explicit(self):
        self.unavailable(provenance=False)
        result = self.valid()
        self.assertTrue(result["provenance_unavailable"])
        del self.status["unavailable_provenance_write_error"]
        self.invalid("missing provenance")

    def test_ready_before_prompt_persistence_failure_has_no_invented_call(self):
        self.manifest["status"] = "failed"
        self.manifest["adjudicator_revision_attempts"] = []
        (self.folder / "prompts/adjudicator_revision.txt").unlink()
        (self.folder / "codex_attempts/adjudicator_revision.events.jsonl").unlink()
        result = self.valid()
        self.assertTrue(result["replayed"] and result["prompt_persistence_incomplete"])
        self.assertEqual(result["revision_accounting"]["attempt_count"], 0)

    def test_failed_revision_usage_retry_limit_and_unknown_remain_visible(self):
        attempt = self.manifest["adjudicator_revision_attempts"][0]
        attempt["status"] = "failed"
        usage = copy.deepcopy(attempt["token_usage"])
        second = copy.deepcopy(attempt)
        second.update(attempt=2, status="success")
        self.manifest["adjudicator_revision_attempts"].append(second)
        event = self.folder / "codex_attempts/adjudicator_revision.attempt2.events.jsonl"
        self.write(event, {"type": "turn.completed", "usage": usage})
        self.assertEqual(self.valid()["revision_accounting"]["recorded_revision_total_tokens"], 40)
        attempt["token_usage"]["total_tokens"] = 0
        self.invalid("event/attempt usage")
        attempt["token_usage"] = usage
        self.manifest["adjudicator_revision_attempts"].append({**second, "attempt": 3})
        self.invalid("retry budget")
        self.manifest["adjudicator_revision_attempts"].pop()
        second.update(token_usage=None, subprocess_started=None)
        event.write_text("")
        result = self.valid()["revision_accounting"]
        self.assertIsNone(result["recorded_revision_total_tokens"])
        self.assertEqual(result["known_revision_usage_subtotal"]["total_tokens"], 20)

    def test_lost_attempt_record_and_missing_policy_are_not_hidden(self):
        self.manifest["adjudicator_revision_attempts"] = []
        self.invalid("lost revision attempt accounting")
        self.manifest["status"] = "running"
        result = self.valid()["revision_accounting"]
        self.assertIsNone(result["recorded_revision_total_tokens"])
        self.assertEqual(len(result["unrecorded_native_attempts"]), 1)
        del self.manifest["first_revision_obligation_preview"]
        self.invalid("without declared policy")

    def test_frozen_instruction_bytes_remain_valid_when_working_prose_changes(self):
        with mock.patch.object(obligations, "REVIEW_INSTRUCTION", "new unrun text"):
            self.assertTrue(self.valid()["replayed"])

    def test_inactive_states_do_not_claim_review_and_not_applicable_requires_no_targets(self):
        self.manifest["status"] = "failed"
        self.manifest["adjudicator_revision_attempts"] = []
        self.manifest["verifier_attempts"] = []
        self.manifest["artifacts"].pop("verifier_reports")
        for key in A.PREVIEW_FILES:
            self.manifest["artifacts"].pop(key)
        (self.folder / "prompts/adjudicator_revision.txt").unlink()
        (self.folder / "codex_attempts/adjudicator_revision.events.jsonl").unlink()
        self.status.clear()
        self.status.update(policy_version=A.PREVIEW_POLICY, enabled=True, status="not_reached",
                           included_in_revision_prompt=False, partial_current_scope_only=True)
        self.assertFalse(self.valid()["replayed"])
        self.manifest["status"] = "success"
        self.invalid("never reached")
        self.status.update(status="not_applicable", reason="no_targeted_verifier_revision")
        self.invalid("despite verification targets")
        path = self.adj / "verification_targets.json"
        targets = A.read(path)
        targets["cluster_ids"] = []
        self.write(path, targets)
        self.invalid("file hash mismatch")
        self.manifest["artifacts"]["verification_targets"]["sha256"] = A.file_hash(path)
        self.assertFalse(self.valid()["replayed"])

    def test_relabelled_frozen_policy_is_rejected_even_after_hash_updates(self):
        helper = self.root / "frozen_workspace" / A.PREVIEW_SOURCES[-1]
        text = helper.read_text()
        helper.write_text(text.replace(A.PREVIEW_POLICY, "first_revision_partial_obligation_preview_v9"))
        digest = A.file_hash(helper)
        self.batch["source_hashes"][A.PREVIEW_SOURCES[-1]] = digest
        self.manifest["stage_source_hashes"][str(helper)] = digest
        self.private["source_hashes"][str(helper)] = digest
        self.save_private()
        self.invalid("source policy mismatch")

    def test_old_batch_without_optional_field_retains_existing_audit(self):
        fixture = legacy.PhysicalBatchAuditTests("test_complete_valid_graph_merge_is_integrity_only")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        result = A.audit(fixture.root)
        self.assertTrue(result["integrity_ok"], result["integrity_errors"])
        self.assertNotIn("first_revision_obligation_preview", result["runs"][0])


if __name__ == "__main__":
    unittest.main()
