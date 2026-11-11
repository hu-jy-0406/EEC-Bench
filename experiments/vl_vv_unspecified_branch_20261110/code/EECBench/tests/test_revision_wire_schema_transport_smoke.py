"""Same-thread schema admission and fault accounting, with no CLI/model calls."""
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import physical_revision_wire as W
import test_physical_identity_pipeline as pipeline
import test_single_frame_schema_transport_smoke as single


E = pipeline.ENSEMBLE
spec = importlib.util.spec_from_file_location(
    "revision_wire_admission_tested", single.DIRECTORY / "run_revision_wire_schema_transport_smoke.py")
D = importlib.util.module_from_spec(spec)
with mock.patch.dict(sys.modules, {"run_frozen_batch": single.H,
                                  "run_single_frame_schema_transport_smoke": single.D}):
    spec.loader.exec_module(D)
USAGE = dict(zip(E.TOKEN_KEYS, (100, 20, 10, 110)))


class RevisionWireSchemaTransportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.calls, self.checkpoints, self.cases = [], [], []
        self.modes = {}
        self.failing_persistence = None
        self.checkpoint_success = True
        self.stdout = io.StringIO()
        for role, schema, payload in zip(
            ("initial", "revision"), (W.CANONICAL_SCHEMA_PATH, W.SCHEMA_PATH), D.payloads(E, W)
        ):
            directory = self.root / role
            (directory / "workdir").mkdir(parents=True)
            prompt = directory / "prompt.txt"
            prompt.write_text(role)
            self.cases.append({"role": role, "schema": str(schema), "expected": payload,
                               "directory": str(directory), "prompt": str(prompt)})
        self.preflight = mock.Mock()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.object(E, "run_codex_json", side_effect=self.invoke))
        self.stack.enter_context(redirect_stdout(self.stdout))

    def invoke(self, **kwargs):
        index = len(self.calls)
        self.calls.append(kwargs)
        mode = self.modes.get(index)
        if mode == "unknown_start":
            # An empty log can exist before or after Popen; startup is unknown.
            kwargs["events_path"].write_text("")
            raise OSError("synthetic unconfirmed startup")
        payload = deepcopy(self.cases[index]["expected"])
        thread = None if mode == "missing_thread" else (
            "different-thread" if mode == "different_thread" else "synthetic-thread")
        events = [{"type": "thread.started", "thread_id": thread},
                  {"type": "turn.completed", "usage": USAGE}]
        if mode == "tool":
            events.insert(1, {"type": "item.completed", "item": {"type": "command_execution"}})
        kwargs["events_path"].write_text("\n".join(json.dumps(row) for row in events) + "\n")
        raw = json.dumps(payload)
        if mode == "duplicate":
            raw = raw.replace('"clusters": []', '"clusters": [], "clusters": []')
        if mode == "wrong_header":
            payload["schema_version"] = W.CANONICAL_VERSION
            raw = json.dumps(payload)
        kwargs["output_path"].write_bytes(raw.encode())
        kwargs["stderr_path"].write_text("synthetic stderr\n")
        return E.CodexInvocation(payload, deepcopy(USAGE), thread, 0.2)

    def persist(self, path, value):
        if path.name == self.failing_persistence:
            return False
        single.H.write(path, value)
        return True

    def checkpoint(self, rows):
        self.checkpoints.append(deepcopy(rows))
        return self.checkpoint_success

    def run_turns(self):
        rows = D.run_turns(E, W, {"codex_wrapper": "unused", "model": "gpt-5.6-sol"},
                           self.cases, self.persist, self.checkpoint, self.preflight)
        return rows, D.admission.aggregate_usage(E, rows)

    def assert_usage(self, totals, count):
        expected = {key: value * count for key, value in USAGE.items()}
        self.assertEqual(totals["model_invocations"], count)
        self.assertEqual(totals["token_usage"], expected)
        self.assertEqual(totals["known_token_usage_subtotal"], expected)
        self.assertEqual(totals["retry_count"], 0)

    def test_two_complete_schemas_same_thread_and_materialization(self):
        rows, totals = self.run_turns()
        self.assertEqual([row["status"] for row in rows], ["success", "success"])
        self.assert_usage(totals, 2)
        first, second = self.calls
        self.assertTrue(first["persistent"])
        self.assertNotIn("resume_thread_id", first)
        self.assertFalse(second["persistent"])
        self.assertEqual(second["resume_thread_id"], "synthetic-thread")
        self.assertEqual(first["schema_path"], W.CANONICAL_SCHEMA_PATH)
        self.assertEqual(second["schema_path"], W.SCHEMA_PATH)
        for call in self.calls:
            self.assertEqual(call["attachments"], [])
            self.assertEqual(call["timeout_sec"], 180)
        self.assertEqual([len(rows) for rows in self.checkpoints], [1, 2])
        self.assertEqual(json.loads((self.root / "revision/materialized.json").read_text()),
                         self.cases[0]["expected"])
        self.assertTrue(rows[1]["materialization_audit"]["duplicate_key_check_performed"])
        self.assertFalse(rows[1]["materialization_audit"]["visual_proof_created"])
        self.assertEqual(json.loads((self.root / "revision/attempt1.json").read_text())["schema_version"],
                         W.WIRE_VERSION)

    def test_initial_duplicate_is_paid_failure_without_second_turn(self):
        self.modes[0] = "duplicate"
        rows, totals = self.run_turns()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(rows[0]["status"], "failed")
        self.assertIn("Duplicate", rows[0]["error"])
        self.assert_usage(totals, 1)

    def test_missing_initial_thread_stops_after_paid_call(self):
        self.modes[0] = "missing_thread"
        rows, totals = self.run_turns()
        self.assertEqual(len(self.calls), 1)
        self.assertIn("resumable", rows[0]["error"])
        self.assert_usage(totals, 1)

    def test_different_returned_revision_thread_is_not_admitted(self):
        self.modes[1] = "different_thread"
        rows, totals = self.run_turns()
        self.assertEqual([r["status"] for r in rows], ["success", "failed"])
        self.assertIn("initial admission thread", rows[1]["error"])
        self.assertEqual(rows[1]["requested_resume_thread_id"], "synthetic-thread")
        self.assertEqual(rows[1]["thread_id"], "different-thread")
        self.assert_usage(totals, 2)

    def test_revision_duplicate_rejected_from_raw_bytes_keeps_both_costs(self):
        self.modes[1] = "duplicate"
        rows, totals = self.run_turns()
        self.assertIn("Duplicate", rows[1]["error"])
        self.assertIn('"clusters": [], "clusters": []', (self.root / "revision/attempt1.json").read_text())
        self.assertFalse((self.root / "revision/materialized.json").exists())
        self.assert_usage(totals, 2)

    def test_old_revision_header_is_failed_without_repair(self):
        self.modes[1] = "wrong_header"
        rows, totals = self.run_turns()
        self.assertEqual(rows[1]["status"], "failed")
        self.assertEqual(len(self.calls), 2)
        self.assert_usage(totals, 2)

    def test_tool_guard_stops_dependent_turn_and_preserves_paid_usage(self):
        self.modes[0] = "tool"
        rows, totals = self.run_turns()
        self.assertEqual(len(self.calls), 1)
        self.assertIn("prohibited tools", rows[0]["error"])
        self.assert_usage(totals, 1)

    def test_first_result_persistence_failure_prints_and_checkpoints_paid_row(self):
        self.failing_persistence = "result.json"
        rows, totals = self.run_turns()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.checkpoints, [rows])
        self.assertEqual(json.loads(self.stdout.getvalue()), rows[0])
        self.assert_usage(totals, 1)

    def test_first_manifest_checkpoint_failure_stops_second_turn(self):
        self.checkpoint_success = False
        rows, totals = self.run_turns()
        self.assertEqual(len(self.calls), 1)
        self.assertTrue((self.root / "initial/result.json").exists())
        self.assertEqual(self.checkpoints, [rows])
        self.assert_usage(totals, 1)

    def test_revision_sidecar_failure_preserves_both_paid_rows(self):
        self.failing_persistence = "materialization_audit.json"
        rows, totals = self.run_turns()
        self.assertEqual(rows[1]["status"], "failed")
        self.assertIn("persist", rows[1]["error"])
        self.assertTrue((self.root / "revision/materialized.json").exists())
        self.assert_usage(totals, 2)

    def test_unexpected_worker_exception_recovers_native_usage(self):
        real_invoke = D.admission.invoke_case

        def worker(*args, **kwargs):
            row = real_invoke(*args, **kwargs)
            if row["role"] == "revision":
                raise RuntimeError("synthetic unexpected post-return exception")
            return row

        with mock.patch.object(D.admission, "invoke_case", side_effect=worker):
            rows, totals = self.run_turns()
        self.assertEqual([r["status"] for r in rows], ["success", "failed"])
        self.assert_usage(totals, 2)

    def test_unconfirmed_second_start_retains_first_subtotal_with_null_total(self):
        self.modes[1] = "unknown_start"
        rows, totals = self.run_turns()
        self.assertEqual([r["status"] for r in rows], ["success", "failed"])
        self.assertEqual(totals["unknown_subprocess_starts"], ["revision"])
        self.assertEqual(totals["known_token_usage_subtotal"], USAGE)
        self.assertEqual(totals["token_usage"], dict.fromkeys(E.TOKEN_KEYS))
        self.assertEqual(len(self.calls), 2)

    def test_frozen_input_drift_prevents_second_call_without_losing_first(self):
        self.preflight.side_effect = [None, RuntimeError("synthetic frozen input drift")]
        rows, totals = self.run_turns()
        self.assertEqual(rows[1]["failure_kind"], "preflight")
        self.assertFalse(rows[1]["subprocess_started"])
        self.assertFalse(rows[1]["subprocess_start_unknown"])
        self.assertEqual(len(self.calls), 1)
        self.assert_usage(totals, 1)

    def test_stdout_failure_keeps_paid_row_on_disk_and_skips_second(self):
        with mock.patch("builtins.print", side_effect=BrokenPipeError("synthetic closed stdout")):
            rows, totals = self.run_turns()
        self.assertEqual(len(self.calls), 1)
        saved = json.loads((self.root / "initial/result.json").read_text())
        self.assertEqual(saved, rows[0])
        self.assertIn("closed stdout", saved["stdout_error"])
        self.assertEqual(saved["status"], "failed")
        self.assert_usage(totals, 1)

    def test_explicit_startup_states_survive_normal_and_failed_accounting(self):
        for accounting_failure in (False, True):
            for started in (False, None, True):
                with self.subTest(accounting_failure=accounting_failure, started=started):
                    (self.root / "initial/attempt1.started.json").unlink(missing_ok=True)
                    error = E.CodexCallError(
                        "synthetic explicit startup", failure_kind="subprocess_error",
                        runtime_seconds=0.2, token_usage=deepcopy(USAGE) if started else None,
                        thread_id=None, returncode=None, subprocess_started=started)
                    with ExitStack() as stack:
                        stack.enter_context(mock.patch.object(E, "run_codex_json", side_effect=error))
                        if accounting_failure:
                            stack.enter_context(mock.patch.object(
                                E, "_codex_attempt_accounting", side_effect=OSError("accounting failure")))
                        row = D.admission.invoke_case(E, {"codex_wrapper": "unused", "model": "unused"},
                                                      self.cases[0])
                    self.assertIs(row["subprocess_started"], started)
                    self.assertIs(row["subprocess_start_unknown"], started is None)
                    self.assertEqual(row["status"], "failed")
                    totals = D.admission.aggregate_usage(E, [row])
                    self.assertEqual(totals["model_invocations"], int(started is True))
                    if started is None:
                        self.assertEqual(totals["token_usage"], dict.fromkeys(E.TOKEN_KEYS))
                    elif started is False:
                        self.assertEqual(totals["token_usage"], dict.fromkeys(E.TOKEN_KEYS, 0))
                    else:
                        self.assert_usage(totals, 1)


if __name__ == "__main__":
    unittest.main()
