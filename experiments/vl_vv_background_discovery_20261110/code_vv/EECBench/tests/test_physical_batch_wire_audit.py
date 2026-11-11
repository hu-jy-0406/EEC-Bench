"""Independent wire-artifact mutation checks; synthetic transport only."""
import copy
import json
from pathlib import Path
import unittest
from unittest import mock

import test_physical_batch_audit as legacy
import test_revision_wire_pipeline as pipeline
import physical_revision_wire as wire


A = legacy.AUDIT
E = pipeline.E


class PhysicalBatchWireAuditTests(unittest.TestCase):
    def prepare(self, **kwargs):
        _, self.manifest, self.calls, self.folder = pipeline.RevisionWirePipelineTests.run_pipeline(self, **kwargs)
        self.root = self.folder.parent
        self.batch = {"identity_review_policy": A.POLICY,
                      "revision_output_policy": A.WIRE_SELECTION, "source_hashes": {}, "input_hashes": {}}
        project = Path(E.__file__).resolve().parents[1]
        self.sources = {}
        for relative, group in A.WIRE_SOURCES.items():
            source = project.parent / relative
            target = self.root / "frozen_workspace" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            self.sources[relative] = target
            self.batch["source_hashes"][relative] = A.file_hash(target)
            if group:
                self.manifest[group][str(target)] = A.file_hash(target)
        canonical = self.sources["EECBench/schemas/codex_entity_adjudication_v0.6.schema.json"]
        selected = self.sources["EECBench/schemas/codex_entity_revision_wire_v0.1.schema.json"]
        self.manifest["revision_output_contract"].update(
            initial_schema=str(canonical), revision_model_output_schema=str(selected),
            materialized_schema=str(canonical))
        for name, digest in self.manifest["input_hashes"].items():
            if Path(name).name.startswith("frame_"):
                self.batch["input_hashes"][self.folder.name + "/" + Path(name).name] = digest
        # Existing fake transport emits usage only. Add explicitly synthetic
        # native final messages so the independent reader checks both records.
        for row in self.manifest["adjudicator_revision_attempts"]:
            stem = self.stem(row["attempt"])
            raw = (self.folder / "codex_attempts" / (stem + ".json")).read_bytes().decode()
            events = [
                {"type": "thread.started", "thread_id": row["thread_id"]},
                {"type": "turn.started"},
                {"type": "item.completed", "item": {"type": "agent_message", "text": raw}},
                {"type": "turn.completed", "usage": row["token_usage"]},
            ]
            self.write(self.event_path(row["attempt"]), events, jsonl=True)
        return self

    def stem(self, number):
        return "adjudicator_revision" + ("" if number == 1 else ".attempt2")

    def event_path(self, number):
        return self.folder / "codex_attempts" / (self.stem(number) + ".events.jsonl")

    def write(self, path, value, *, jsonl=False):
        path.write_text("".join(json.dumps(row) + "\n" for row in value)
                        if jsonl else json.dumps(value, indent=2) + "\n")

    def materialization(self, number=1):
        return self.manifest["adjudicator_revision_attempts"][number - 1]["wire_materialization"]

    def update_artifact(self, label, value, number=1):
        link = self.materialization(number)["artifacts"][label]
        path = Path(link["path"])
        if type(value) is bytes:
            path.write_bytes(value)
        else:
            self.write(path, value)
        link["sha256"] = A.file_hash(path)
        key = self.stem(number) + ("_wire_raw" if label == "raw" else "_" + label)
        self.manifest["artifacts"][key] = copy.deepcopy(link)

    def check_audit(self):
        errors = []
        before = copy.deepcopy(self.manifest)

        def check(ok, message):
            if not ok:
                errors.append(message)

        def verify(path, expected, label):
            try:
                check(A.file_hash(path) == expected, label + ": hash mismatch")
            except OSError as error:
                errors.append(str(error))

        try:
            result = A.audit_revision_wire(self.root, self.batch, self.folder, self.manifest, check, verify)
        except (ValueError, TypeError, KeyError, AttributeError, OSError) as error:
            result = None
            errors.append(str(error))
        self.assertEqual(before, self.manifest)
        return result, errors

    def valid(self):
        result, errors = self.check_audit()
        self.assertEqual(errors, [])
        self.assertFalse(result["pixel_truth_verified"])
        return result

    def invalid(self, fragment):
        _, errors = self.check_audit()
        self.assertTrue(any(fragment in error for error in errors), errors)

    def test_real_materialization_reconstructed_without_producer_or_frozen_execution(self):
        self.prepare()
        path = self.sources["EECBench/scripts/physical_revision_wire.py"]
        path.write_text(path.read_text() + "\nraise AssertionError('must not execute frozen')\n")
        self.batch["source_hashes"]["EECBench/scripts/physical_revision_wire.py"] = A.file_hash(path)
        self.manifest["stage_source_hashes"][str(path)] = A.file_hash(path)
        with mock.patch.object(wire, "materialize_revision_wire_json", side_effect=AssertionError("independent audit")):
            result = self.valid()
        self.assertEqual(result["revision_accounting"]["recorded_revision_total_tokens"], 20)
        self.assertTrue(result["attempts"][0]["native"]["agent_output_checked"])
        self.assertFalse(result["frozen_code_executed"])

    def test_failed_raw_is_legitimate_and_both_paid_attempts_remain(self):
        self.prepare(failures=["adjudicator_revision", "adjudicator_revision.attempt2"])
        result = self.valid()
        self.assertEqual([r["materialization_state"] for r in result["attempts"]], ["not_materialized"] * 2)
        self.assertTrue(all(r["materialization_replay_error"] for r in result["attempts"]))
        self.assertEqual(result["revision_accounting"]["recorded_revision_total_tokens"], 40)

    def test_duplicate_raw_keys_cannot_be_hidden_by_transport_dict(self):
        self.prepare(duplicate=True)
        result = self.valid()
        self.assertTrue(all("duplicate" in r["materialization_replay_error"] for r in result["attempts"]))
        row = self.manifest["adjudicator_revision_attempts"][0]
        row["status"] = "success"
        row["wire_materialization"]["status"] = "persisted"
        self.invalid("false validated/materialized")

    def test_rehashed_extra_semantic_change_is_not_owner_materialization(self):
        self.prepare()
        path = Path(self.materialization()["artifacts"]["canonical"]["path"])
        original = A.read(path)
        for mutate in (
            lambda c: c["clusters"][0].update(canonical_name="retargeted object"),
            lambda c: c["clusters"][0]["adjudicator_evidence"][0].update(coarse_locator="invented observation"),
            lambda c: c["clusters"][0]["revision_resolutions"][0].update(anonymous_proposal_ids=["p9999"]),
        ):
            changed = copy.deepcopy(original)
            mutate(changed)
            self.update_artifact("canonical", changed)
            self.invalid("forbidden raw-to-canonical")
        self.update_artifact("canonical", original)
        self.valid()

    def test_private_audit_flags_pointers_and_input_rehash_do_not_override_replay(self):
        self.prepare()
        path = Path(self.materialization()["artifacts"]["materialization_audit"]["path"])
        original = A.read(path)
        for mutate in (
            lambda a: a.update(duplicate_key_check_performed=False),
            lambda a: a.update(visual_proof_created=True),
            lambda a: a["resolution_owner_insertions"][0].update(source_json_pointer="/wrong_owner"),
            lambda a: a["input_provenance"].update(initial_cluster_ids=[]),
        ):
            changed = copy.deepcopy(original)
            mutate(changed)
            self.update_artifact("materialization_audit", changed)
            self.invalid("audit replay mismatch")

    def test_input_universe_and_original_frames_cannot_be_replaced_by_selected_subset(self):
        self.prepare()
        provenance = self.materialization()["input_provenance"]
        original = copy.deepcopy(provenance)
        for key, value in (("expected_proposal_ids", provenance["expected_proposal_ids"][:1]),
                           ("initial_cluster_ids", []), ("valid_frame_ids", [True]),
                           ("shot_manifest", {**provenance["shot_manifest"], "sha256": "0" * 64})):
            provenance[key] = value
            self.invalid("full initial/proposal/frame")
            provenance.clear()
            provenance.update(copy.deepcopy(original))
        frame = next(k for k in self.manifest["input_hashes"] if Path(k).name.startswith("frame_"))
        self.manifest["input_hashes"][frame] = "0" * 64
        self.invalid("frame not bound")

    def test_all_states_and_selection_are_explicit_and_canonical_cannot_masquerade(self):
        self.prepare()
        for value in ("future_v3", None):
            self.manifest["revision_output_policy"] = value
            self.invalid("unsupported")
        self.manifest["revision_output_policy"] = "canonical"
        self.invalid("wire artifacts/claims under canonical")
        self.manifest["revision_output_policy"] = A.WIRE_SELECTION
        self.materialization()["status"] = "success"
        self.invalid("unknown materialization state")

    def test_false_contract_schema_and_source_are_rejected(self):
        self.prepare()
        contract = self.manifest["revision_output_contract"]
        contract["strict_raw_json_text_entry"] = False
        self.invalid("false/unknown output contract")
        contract["strict_raw_json_text_entry"] = True
        path = self.sources["EECBench/schemas/codex_entity_revision_wire_v0.1.schema.json"]
        schema = A.read(path)
        schema["$defs"]["revision_resolution"]["required"].remove("evidence_indices")
        self.write(path, schema)
        self.batch["source_hashes"]["EECBench/schemas/codex_entity_revision_wire_v0.1.schema.json"] = A.file_hash(path)
        self.manifest["schema_hashes"][str(path)] = A.file_hash(path)
        self.invalid("required resolution fields")

    def test_first_and_repair_prompt_formats_must_match_actual_selected_contract(self):
        self.prepare(failures=["adjudicator_revision"])
        self.valid()
        for number in (1, 2):
            path = self.folder / "prompts" / (self.stem(number) + ".txt")
            original = path.read_text()
            path.write_text(original.replace("CURRENT REVISION OUTPUT FORMAT", "incorrect format"))
            self.manifest["prompt_hashes"][path.name] = A.file_hash(path)
            self.invalid("prompt missing/duplicate")
            path.write_text(original)
            self.manifest["prompt_hashes"][path.name] = A.file_hash(path)
        self.manifest["adjudicator_revision_attempts"][0]["error"] = "different original error"
        self.invalid("incorrect repair")

    def test_native_message_and_usage_are_checked_independently(self):
        self.prepare()
        path = self.event_path(1)
        events = [json.loads(x) for x in path.read_text().splitlines()]
        original = copy.deepcopy(events)
        payload = json.loads(events[2]["item"]["text"])
        payload["clusters"][0]["canonical_name"] = "another object"
        events[2]["item"]["text"] = json.dumps(payload)
        self.write(path, events, jsonl=True)
        self.invalid("native final message differs")
        events = original
        events[-1]["usage"]["total_tokens"] = 900
        events[-1]["usage"]["output_tokens"] = 887
        self.write(path, events, jsonl=True)
        self.invalid("event/attempt usage mismatch")

    def test_legal_persistence_failures_have_distinct_state_and_paid_cost(self):
        for suffix in (".materialized.json", ".materialization_audit.json"):
            with self.subTest(suffix=suffix):
                self.prepare(persist_failure=suffix)
                result = self.valid()
                self.assertEqual(result["attempts"][0]["materialization_state"], "validated_in_memory")
                self.assertTrue(result["attempts"][0]["reconstructible"])
                self.assertEqual(result["attempts"][1]["materialization_state"], "persisted")
                self.assertEqual(result["revision_accounting"]["recorded_revision_total_tokens"], 40)

    def test_persisted_schema_valid_does_not_mean_base_valid(self):
        def change(stem, payload, _root):
            if stem.startswith("adjudicator_revision"):
                payload["clusters"][0]["frame_presence"][0]["frame_id"] = 999
            return payload
        self.prepare(transform=change)
        result = self.valid()
        self.assertTrue(all(r["materialization_state"] == "persisted" for r in result["attempts"]))
        self.assertTrue(all(r["base_deferred_split_replay_error"] for r in result["attempts"]))
        self.manifest["adjudicator_revision_attempts"][0]["status"] = "success"
        self.invalid("successful attempt fails")

    def test_unknown_cost_is_null_but_known_failed_spawn_is_not_paid(self):
        self.prepare(helper_error=True)
        for row in self.manifest["adjudicator_revision_attempts"]:
            row["token_usage"] = None
            row["subprocess_started"] = None
            row["subprocess_start_unknown"] = True
            row["failure_kind"] = "orchestration_error"
            raw = row["wire_materialization"]["artifacts"].pop("raw")
            Path(raw["path"]).unlink()
            self.manifest["artifacts"].pop(self.stem(row["attempt"]) + "_wire_raw")
            self.event_path(row["attempt"]).write_text("")
        repair_path = self.folder / "prompts/adjudicator_revision.attempt2.txt"
        prompt = repair_path.read_text()
        head, rest = prompt.rsplit("\nproposal_accounting_diagnostics:\n", 1)
        _, suffix = rest.split("\n\nCURRENT REVISION OUTPUT FORMAT", 1)
        repair_path.write_text(head + "\nproposal_accounting_diagnostics:\n{}"
                               + "\n\nCURRENT REVISION OUTPUT FORMAT" + suffix)
        self.manifest["prompt_hashes"][repair_path.name] = A.file_hash(repair_path)
        result = self.valid()
        self.assertIsNone(result["revision_accounting"]["recorded_revision_total_tokens"])
        for row in self.manifest["adjudicator_revision_attempts"]:
            row["subprocess_started"] = False
            row["subprocess_start_unknown"] = False
        result = self.valid()
        self.assertEqual(result["revision_accounting"]["recorded_revision_total_tokens"], 0)

    def test_repair_exact_split_payload_cannot_be_changed_with_outer_rehash(self):
        self.prepare(failures=["adjudicator_revision"])
        path = self.folder / "prompts/adjudicator_revision.attempt2.txt"
        text = path.read_text().replace('"automatic_split": false', '"automatic_split": true')
        path.write_text(text)
        self.manifest["prompt_hashes"][path.name] = A.file_hash(path)
        self.invalid("repair changed exact split obligations")

    def test_false_spawn_cannot_erase_native_paid_call(self):
        self.prepare(helper_error=True)
        self.manifest["adjudicator_revision_attempts"][0]["subprocess_started"] = False
        self.invalid("known failed spawn conflicts")

    def test_retry_budget_success_then_retry_and_thread_remap_fail(self):
        self.prepare(failures=["adjudicator_revision"])
        self.manifest["adjudicator_revision_attempts"][1]["thread_id"] = "different-thread"
        self.invalid("retain initial adjudicator thread")
        self.manifest["adjudicator_revision_attempts"][1]["thread_id"] = "synthetic_thread"
        self.manifest["adjudicator_revision_attempts"][0]["status"] = "success"
        self.invalid("retry after successful")
        self.manifest["adjudicator_revision_attempts"].append(
            copy.deepcopy(self.manifest["adjudicator_revision_attempts"][-1]))
        self.invalid("retry budget")

    def test_old_canonical_batch_absent_field_remains_supported(self):
        f = legacy.PhysicalBatchAuditTests("test_complete_valid_graph_merge_is_integrity_only")
        f.setUp()
        self.addCleanup(f.doCleanups)
        result = A.audit(f.root)
        self.assertTrue(result["integrity_ok"], result["integrity_errors"])
        f.batch["revision_output_policy"] = "future-wire"
        f.flush()
        result = A.audit(f.root)
        self.assertFalse(result["integrity_ok"])
        self.assertTrue(any("unsupported revision" in error for error in result["integrity_errors"]))


if __name__ == "__main__":
    unittest.main()
