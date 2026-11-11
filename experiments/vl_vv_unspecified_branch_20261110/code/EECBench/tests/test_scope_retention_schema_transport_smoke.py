"""Retention admission with real validators and synthetic calls; no model or CLI."""
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import scope_retention_transport as T  # noqa: E402
import physical_identity_review as P  # noqa: E402
import test_revision_wire_schema_transport_smoke as prior  # noqa: E402


E, W, S = prior.E, prior.W, prior.single
with mock.patch.dict(sys.modules, {"run_frozen_batch": S.H, "observer_context_controls": S.C,
                                  "run_revision_wire_schema_transport_smoke": prior.D}):
    D = S.load("scope_retention_admission_tested", S.DIRECTORY / "run_scope_retention_schema_transport_smoke.py")


class ScopeRetentionAdmissionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / "verification_retention"
        (self.directory / "workdir").mkdir(parents=True)
        prompt = self.directory / "prompt.txt"
        prompt.write_text(D.prompt_text(D.payloads()[2]))
        self.spec = {"role": "verification_retention", "schema": str(T.SCHEMA_PATH),
                     "expected": D.payloads()[2], "directory": str(self.directory), "prompt": str(prompt)}
        self.rows, self.state, self.calls, self.checkpoints = [], {}, [], []
        self.mode, self.persistence_failure = None, None
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.stack.enter_context(mock.patch.object(E, "run_codex_json", side_effect=self.invoke))

    def invoke(self, **kwargs):
        self.calls.append(kwargs)
        if self.mode in {"unknown", "not_started"}:
            started = None if self.mode == "unknown" else False
            raise E.CodexCallError("synthetic startup failure", failure_kind="transport",
                runtime_seconds=.01, token_usage=None, thread_id=None, returncode=None,
                subprocess_started=started)
        payload = deepcopy(self.spec["expected"])
        if self.mode == "wrong_policy":
            payload["scope_retention_policy"] = "disabled"
        events = [{"type": "thread.started", "thread_id": "synthetic-admission-thread"},
                  {"type": "turn.completed", "usage": prior.USAGE}]
        if self.mode == "missing_thread":
            events.pop(0)
        if self.mode == "tool":
            events.insert(1, {"type": "item.completed", "item": {"type": "command_execution"}})
        kwargs["events_path"].write_text("\n".join(json.dumps(row) for row in events) + "\n")
        raw = json.dumps(payload)
        if self.mode == "duplicate":
            raw = raw.replace('"reviews": []', '"reviews": [], "reviews": []')
        kwargs["output_path"].write_text(raw)
        kwargs["stderr_path"].write_text("synthetic stderr\n")
        if self.mode == "interrupted":
            raise KeyboardInterrupt("synthetic interruption after native completion")
        return E.CodexInvocation(payload, deepcopy(prior.USAGE), "synthetic-admission-thread", .2)

    def persist(self, path, value):
        if path.name == self.persistence_failure:
            self.state["stop_reason"] = "persistence_failure"
            return False
        S.H.write(path, value)
        return True

    def checkpoint(self, rows):
        self.checkpoints.append(deepcopy(rows))
        return True

    def run_case(self, preflight=lambda: None):
        D.run_case(E, T, W, P, {"codex_wrapper": "unused", "model": D.MODEL}, self.spec,
                   self.persist, self.checkpoint, preflight, self.rows, self.state)
        return D.shared._aggregate_eight_usage(E, self.rows)

    def test_full_selected_schema_one_fresh_call_and_exact_core_projection(self):
        totals = self.run_case()
        self.assertEqual(len(self.calls), 1)
        call = self.calls[0]
        self.assertEqual(call["model"], "gpt-5.6-sol")
        self.assertEqual(call["schema_path"], T.SCHEMA_PATH)
        self.assertEqual(call["attachments"], [])
        self.assertEqual(call["timeout_sec"], 180)
        self.assertFalse(call["persistent"])
        self.assertNotIn("resume_thread_id", call)
        self.assertEqual(totals["token_usage"], prior.USAGE)
        self.assertEqual(totals["retry_count"], 0)
        self.assertEqual(self.rows[0]["projection_status"], "persisted")
        self.assertEqual(json.loads((self.directory / "core_report.json").read_text()), D.payloads()[1])
        audit = json.loads((self.directory / "projection_audit.json").read_text())
        self.assertTrue(audit["core_fields_unchanged"])
        self.assertTrue(audit["original_core_validators_passed"])
        self.assertFalse(audit["pixel_truth_verified"])
        self.assertEqual(audit["raw_file_sha256"], D.digest(self.directory / "attempt1.json"))
        self.assertEqual(audit["native_source"]["thread_id"], "synthetic-admission-thread")
        self.assertEqual(json.loads((self.directory / "attempt1.json").read_text()), self.spec["expected"])

    def test_invalid_actual_raw_native_or_tools_keep_paid_failure_without_retry(self):
        for mode in ("duplicate", "wrong_policy", "missing_thread", "tool"):
            with self.subTest(mode=mode):
                self.mode = mode
                self.rows.clear()
                self.state.clear()
                (self.directory / "attempt1.started.json").unlink(missing_ok=True)
                totals = self.run_case()
                self.assertEqual(self.rows[0]["status"], "failed")
                self.assertEqual(totals["token_usage"], prior.USAGE)
                self.assertEqual(totals["model_invocations"], 1)
                self.assertEqual(totals["retry_count"], 0)
                self.assertFalse((self.directory / "core_report.json").exists())
        self.assertEqual(len(self.calls), 4)

    def test_unknown_start_remains_unknown_and_explicit_no_start_has_no_paid_call(self):
        for mode in ("unknown", "not_started"):
            with self.subTest(mode=mode):
                self.mode = mode
                self.rows.clear()
                self.state.clear()
                (self.directory / "attempt1.started.json").unlink(missing_ok=True)
                totals = self.run_case()
                self.assertEqual(totals["model_invocations"], 0)
                self.assertEqual(self.rows[0]["subprocess_start_unknown"], mode == "unknown")
                self.assertEqual(totals["model_invocation_count_complete"], mode != "unknown")
                self.assertEqual(totals["token_usage"]["total_tokens"], None if mode == "unknown" else 0)

    def test_core_publication_failure_keeps_raw_and_paid_usage(self):
        self.persistence_failure = "core_report.json"
        totals = self.run_case()
        self.assertEqual(self.rows[0]["status"], "failed")
        self.assertEqual(self.rows[0]["projection_status"], "validated_in_memory")
        self.assertEqual(totals["token_usage"], prior.USAGE)
        self.assertEqual(json.loads((self.directory / "attempt1.json").read_text()), self.spec["expected"])
        self.assertFalse((self.directory / "core_report.json").exists())
        self.assertEqual(len(self.checkpoints), 1)

    def test_preflight_failure_does_not_start_a_call(self):
        totals = self.run_case(mock.Mock(side_effect=ValueError("source tamper")))
        self.assertEqual(self.calls, [])
        self.assertEqual(self.rows[0]["status"], "not_started")
        self.assertEqual(totals["model_invocations"], 0)
        self.assertEqual(self.rows[0]["error"], "source tamper")

    def test_interruption_after_native_return_preserves_actual_usage(self):
        self.mode = "interrupted"
        with self.assertRaises(KeyboardInterrupt):
            self.run_case()
        self.assertEqual(len(self.rows), 1)
        self.assertEqual(self.rows[0]["status"], "incomplete")
        self.assertEqual(self.rows[0]["token_usage"], prior.USAGE)
        self.assertEqual(len(self.checkpoints), 1)

    def test_execute_requires_frozen_runner_before_any_import_or_request(self):
        with self.assertRaisesRegex(RuntimeError, "captured admission runner"):
            D.load_runtime(self.root)
        self.assertFalse(self.calls)

    def test_terminal_manifest_locks_outputs_and_execution_claim_prevents_reuse(self):
        plan = {"cases": [self.spec], "model_config": {"codex_wrapper": "unused", "model": D.MODEL}}
        manifest = {**plan, "status": "prepared", "attempts": []}
        S.H.write(self.root / "manifest.json", manifest)
        with mock.patch.object(D, "load_runtime", return_value=(E, T, W, P)), \
                mock.patch.object(D, "validate_plan", return_value=(plan, {})):
            self.assertEqual(D.execute(self.root), 0)
            terminal = json.loads((self.root / "manifest.json").read_text())
            self.assertEqual(terminal["status"], "success")
            self.assertEqual(terminal["token_usage"], prior.USAGE)
            self.assertEqual(terminal["model_invocations"], 1)
            self.assertTrue(terminal["hashes_unchanged"])
            self.assertEqual(len(terminal["output_hashes"]), 7)
            S.H.write(self.root / "manifest.json", manifest)
            with self.assertRaises(FileExistsError):
                D.execute(self.root)
        self.assertEqual(len(self.calls), 1)


class ScopeRetentionAdmissionCaptureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = self.root / "admission"
        self.binary = self.root / "fake-codex-not-executed"
        self.binary.write_text("#!/bin/sh\nexit 91\n")
        self.binary.chmod(0o755)
        evidence = self.root / "evidence.json"
        evidence.write_text("{}\n")
        self.controls = self.root / "controls.json"
        S.H.write(self.controls, {"version": S.C.VERSION, "pinned_cli_sha256": D.digest(self.binary),
            "disabled_skill_paths": [], "project_doc_max_bytes": 0,
            "offline_evidence": {"path": str(evidence), "sha256": D.digest(evidence)}})
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.object(D, "CLI", self.binary))
        self.stack.enter_context(mock.patch.object(D, "CLI_SHA256", D.digest(self.binary)))
        self.forbid = self.stack.enter_context(mock.patch.object(E, "run_codex_json",
                                                               side_effect=AssertionError("No model in capture")))

    def prepare(self):
        return D.prepare(self.output, self.controls)

    def adapters(self):
        frozen = self.output / "frozen_workspace/EECBench/scripts"
        runtime = SimpleNamespace(__file__=str(frozen / "ensemble_shot_entity_detection.py"),
                                  validate_codex_schema_transport=E.validate_codex_schema_transport,
                                  validate_verifier_report=E.validate_verifier_report)
        transport = SimpleNamespace(__file__=str(frozen / "scope_retention_transport.py"),
            SCHEMA_PATH=self.output / "frozen_workspace/EECBench/schemas" / D.SCHEMA_NAME,
            CORE_SCHEMA_PATH=self.output / "frozen_workspace/EECBench/schemas" / D.CORE_SCHEMA_NAME,
            validate_and_project_verifier=T.validate_and_project_verifier,
            build_projection_audit=T.build_projection_audit)
        wire = SimpleNamespace(__file__=str(frozen / "physical_revision_wire.py"),
                               parse_revision_wire_json=W.parse_revision_wire_json)
        physical = SimpleNamespace(__file__=str(frozen / "physical_identity_review.py"),
                                   validate_verifier_identity_fields=P.validate_verifier_identity_fields)
        return runtime, transport, wire, physical

    def test_prepare_captures_actual_helpers_schema_and_controls_without_call(self):
        runner = self.prepare()
        self.forbid.assert_not_called()
        manifest = json.loads((self.output / "manifest.json").read_text())
        self.assertEqual(manifest["status"], "prepared")
        self.assertEqual(manifest["attempts"], [])
        self.assertFalse(manifest["nonempty_retention_model_output_tested"])
        self.assertEqual(runner.read_bytes(), Path(D.__file__).read_bytes())
        for module in (D, D.shared, D.shared.admission, D.configuration, D.observer):
            source = Path(module.__file__).resolve()
            self.assertEqual(manifest["original_source_hashes_at_freeze"][str(source)], D.digest(source))
        self.assertTrue(all(D.digest(Path(path)) == value for path, value in manifest["hashes"].items()))
        with self.assertRaises(FileExistsError):
            self.prepare()
        self.assertFalse((self.output / "execute_claim.json").exists())

    def test_rehashed_prompt_cannot_change_selected_case_and_source_tamper_rejected(self):
        self.prepare()
        manifest = json.loads((self.output / "manifest.json").read_text())
        # Live imports belong to the test process; dependency rejection is
        # independently checked below, rather than disabled in production.
        with mock.patch.object(D, "loaded_source_hashes", return_value={}):
            D.validate_plan(self.output, manifest, *self.adapters())
            schema = Path(manifest["cases"][0]["schema"])
            old = schema.read_bytes()
            schema.write_bytes(old + b"\n")
            with self.assertRaisesRegex(RuntimeError, "asset changed"):
                D.validate_plan(self.output, manifest, *self.adapters())
            schema.write_bytes(old)
            prompt = Path(manifest["cases"][0]["prompt"])
            prompt.write_text("Changed task")
            capture_path = self.output / "execution_capture.json"
            capture = json.loads(capture_path.read_text())
            capture["hashes"][str(prompt)] = D.digest(prompt)
            S.H.write(capture_path, capture)
            plan_path = self.output / "execution_plan.json"
            plan = json.loads(plan_path.read_text())
            plan["capture_sha256"] = D.digest(capture_path)
            S.H.write(plan_path, plan)
            manifest.update(plan)
            manifest["hashes"] = {**capture["hashes"], str(capture_path): D.digest(capture_path),
                                  str(plan_path): D.digest(plan_path)}
            with self.assertRaisesRegex(RuntimeError, "Selected admission case changed"):
                D.validate_plan(self.output, manifest, *self.adapters())

    def test_loaded_helper_outside_capture_and_symlink_sources_are_rejected(self):
        self.prepare()
        manifest = json.loads((self.output / "manifest.json").read_text())
        frozen = self.output / "frozen_workspace"
        with self.assertRaisesRegex(RuntimeError, "outside captured"):
            D.loaded_source_hashes(frozen, manifest["hashes"], [D.shared])
        copied = frozen / D.EXPERIMENT / "run_revision_wire_schema_transport_smoke.py"
        self.assertEqual(D.loaded_source_hashes(frozen, manifest["hashes"],
                         [SimpleNamespace(__file__=str(copied))]), {str(copied): D.digest(copied)})
        extra = frozen / "EECBench/scripts/unlocked_extra.py"
        extra.symlink_to(copied)
        with self.assertRaisesRegex(ValueError, "symlinked"):
            D.source_files(frozen)


if __name__ == "__main__":
    unittest.main()
