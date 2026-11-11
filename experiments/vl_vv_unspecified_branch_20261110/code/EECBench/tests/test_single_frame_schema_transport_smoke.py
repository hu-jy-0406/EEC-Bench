"""One-call admission orchestration with fake in-process returns, never a CLI."""
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from copy import deepcopy
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


DIRECTORY = Path(__file__).resolve().parents[1] / "experiments/study_inconsistent_2/entity_discovery_iterations"
SCHEMA = Path(__file__).resolve().parents[1] / "schemas/single-frame-pixel-survey.v0.1.schema.json"
KEYS = ("input_tokens", "cached_input_tokens", "output_tokens", "total_tokens")
USAGE = dict(zip(KEYS, (100, 20, 10, 110)))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


H = load("single_admission_config_fixture", DIRECTORY / "run_frozen_batch.py")
C = load("single_admission_context_fixture", DIRECTORY / "observer_context_controls.py")
with mock.patch.dict(sys.modules, {"run_frozen_batch": H, "observer_context_controls": C}):
    D = load("single_frame_admission_driver_tested", DIRECTORY / "run_single_frame_schema_transport_smoke.py")


class PaidFailure(RuntimeError):
    def __init__(self):
        super().__init__("Synthetic launched call failure")
        self.token_usage = deepcopy(USAGE)
        self.runtime_seconds = 0.2
        self.thread_id = "synthetic-thread"
        self.returncode = 1
        self.failure_kind = "nonzero_exit"
        self.subprocess_started = True


class SingleFrameSchemaTransportSmokeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.workspace = self.base / "workspace"
        scripts = self.workspace / "EECBench/scripts"
        scripts.mkdir(parents=True)
        (scripts / "ensemble_shot_entity_detection.py").write_text("# fake module; no CLI code\n")
        schemas = self.workspace / "EECBench/schemas"
        schemas.mkdir()
        shutil.copyfile(SCHEMA, schemas / SCHEMA.name)
        self.driver_copy = self.workspace / "EECBench/experiments/study_inconsistent_2/entity_discovery_iterations" / Path(D.__file__).name
        self.driver_copy.parent.mkdir(parents=True)
        shutil.copyfile(D.__file__, self.driver_copy)
        self.binary = self.base / "unexecuted-cli"
        self.binary.write_text("#!/bin/sh\nexit 99\n")
        self.binary.chmod(0o755)
        self.evidence = self.base / "offline_evidence.json"
        self.evidence.write_text('{"synthetic_offline_evidence":true}\n')
        self.controls = self.base / "controls.json"
        self.controls.write_text(json.dumps({
            "version": C.VERSION, "pinned_cli_sha256": H.digest(self.binary),
            "disabled_skill_paths": [str(self.base / "unexecuted_skill/SKILL.md")],
            "project_doc_max_bytes": 0,
            "offline_evidence": {"path": str(self.evidence), "sha256": H.digest(self.evidence)},
        }))
        self.root = self.base / "admission"
        self.stdout = io.StringIO()
        self.mode = "success"
        self.runtime = SimpleNamespace(
            TOKEN_KEYS=KEYS, CodexCallError=PaidFailure,
            validate_codex_schema_transport=mock.Mock(side_effect=lambda p: json.loads(Path(p).read_text())),
            run_codex_json=mock.Mock(side_effect=self.invoke),
            _codex_attempt_accounting=mock.Mock(side_effect=self.account))
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.patches.enter_context(mock.patch.object(D, "WORKSPACE", self.workspace))
        self.patches.enter_context(mock.patch.object(D, "__file__", str(self.driver_copy)))
        self.patches.enter_context(mock.patch.object(D, "freeze_codex_config", side_effect=self.freeze_config))
        self.patches.enter_context(mock.patch.dict(os.environ))
        self.patches.enter_context(redirect_stdout(self.stdout))
        previous_path, previous_bytecode = list(sys.path), sys.dont_write_bytecode
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), previous_path))
        self.addCleanup(setattr, sys, "dont_write_bytecode", previous_bytecode)
        original_import = importlib.import_module

        def import_runtime(name, *args, **kwargs):
            if name == "ensemble_shot_entity_detection":
                self.runtime.__file__ = str(self.root / "frozen_workspace/EECBench/scripts/ensemble_shot_entity_detection.py")
                return self.runtime
            return original_import(name, *args, **kwargs)
        self.patches.enter_context(mock.patch.object(D.importlib, "import_module", side_effect=import_runtime))

    def freeze_config(self, root, ignored_binary, model, effort, **kwargs):
        return H.freeze_codex_config(root, str(self.binary), model, effort, **kwargs)

    def invoke(self, **kwargs):
        if self.mode == "unknown_start":
            raise OSError("Start could not be confirmed")
        payload = {"schema_version": "single_frame_pixel_survey_v0.1", "regions": [],
                   "coverage_notes": "Synthetic schema admission only."}
        if self.mode == "wrong_payload":
            payload["coverage_notes"] = "Unexpected response"
        usage = None if self.mode == "unknown_usage" else deepcopy(USAGE)
        events = [{"type": "thread.started", "thread_id": "synthetic-thread"}]
        if self.mode == "tool":
            events.append({"type": "item.completed", "item": {"type": "command_execution"}})
        events.append({"type": "turn.completed", "usage": usage})
        Path(kwargs["events_path"]).write_text("\n".join(json.dumps(row) for row in events) + "\n")
        Path(kwargs["output_path"]).write_text(json.dumps(payload))
        Path(kwargs["stderr_path"]).write_text("Synthetic stderr retained\n")
        if self.mode == "hash_drift":
            with Path(kwargs["schema_path"]).open("a") as stream:
                stream.write("\n")
        if self.mode == "paid_failure":
            raise PaidFailure()
        return SimpleNamespace(payload=payload, token_usage=usage, runtime_seconds=0.2, thread_id="synthetic-thread")

    @staticmethod
    def account(*, invocation, error, events_path):
        source = invocation if invocation is not None else error if isinstance(error, PaidFailure) else None
        return {"subprocess_started": source is not None,
                "token_usage": deepcopy(source.token_usage) if source is not None else None,
                "runtime_seconds": source.runtime_seconds if source is not None else None,
                "thread_id": source.thread_id if source is not None else None,
                "returncode": 0 if invocation is not None else getattr(source, "returncode", None)}

    def run_main(self, *, with_controls=True):
        argv = [str(self.driver_copy), "--output-root", str(self.root)]
        if with_controls:
            argv += ["--observer-context-controls", str(self.controls)]
        with mock.patch.object(sys, "argv", argv):
            return D.main()

    def manifest(self):
        return json.loads((self.root / "manifest.json").read_text())

    def last_stdout(self):
        return json.loads(self.stdout.getvalue().splitlines()[-1])

    def assert_known_usage(self, record):
        self.assertEqual(record["model_invocations"], 1)
        self.assertEqual(record["token_usage"], USAGE)
        self.assertEqual(record["known_token_usage_subtotal"], USAGE)
        self.assertEqual(self.runtime.run_codex_json.call_count, 1)

    def test_one_fresh_noimage_full_schema_and_real_context_freeze(self):
        self.assertEqual(self.run_main(), 0)
        manifest = self.manifest()
        self.assert_known_usage(manifest)
        self.assertEqual((manifest["maximum_invocations"], manifest["maximum_retries"], manifest["max_workers"]), (1, 0, 1))
        self.assertEqual(manifest["images"], [])
        call = self.runtime.run_codex_json.call_args.kwargs
        self.assertFalse(call["persistent"])
        self.assertEqual(call["attachments"], [])
        self.assertEqual(call["timeout_sec"], 180)
        self.assertEqual(call["model"], "gpt-5.6-sol")
        self.assertEqual(Path(call["schema_path"]).read_bytes(), SCHEMA.read_bytes())
        self.assertEqual(set(json.loads(SCHEMA.read_text())["$defs"]), {"scope", "region"})
        self.assertIn("Synthetic schema admission only.", call["prompt"])
        wrapper = Path(call["codex_bin"]).read_text()
        self.assertIn("project_doc_max_bytes=0", wrapper)
        self.assertIn("enabled=false", wrapper)
        self.assertIn('model_reasoning_effort="high"', wrapper)
        self.assertFalse(manifest["model_config"]["observer_context_controls"]["base_cli_context_removed"])
        for path, digest in {**manifest["hashes"], **manifest["output_hashes"]}.items():
            self.assertEqual(H.digest(Path(path)), digest)
        self.assertEqual({Path(p).name for p in manifest["output_hashes"]},
                         {"attempt1.json", "attempt1.events.jsonl", "attempt1.stderr.log", "result.json"})
        self.assertTrue((self.root / "execute_claim.json").is_file())

    def test_required_context_argument_fails_before_any_preparation_or_call(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            self.run_main(with_controls=False)
        self.assertEqual(caught.exception.code, 2)
        self.assertFalse(self.root.exists())
        self.runtime.run_codex_json.assert_not_called()

    def test_invalid_context_evidence_prevents_calls(self):
        self.evidence.write_text("changed evidence\n")
        with self.assertRaisesRegex(RuntimeError, "evidence changed"):
            self.run_main()
        self.runtime.run_codex_json.assert_not_called()

    def test_existing_root_cannot_start_a_second_attempt(self):
        self.assertEqual(self.run_main(), 0)
        before = (self.root / "execute_claim.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.run_main()
        self.assertEqual((self.root / "execute_claim.json").read_bytes(), before)
        self.assertEqual(self.runtime.run_codex_json.call_count, 1)

    def test_unknown_start_totals_null_not_zero(self):
        self.mode = "unknown_start"
        self.assertEqual(self.run_main(), 1)
        manifest = self.manifest()
        self.assertEqual(manifest["unknown_subprocess_starts"], ["survey"])
        self.assertFalse(manifest["model_invocation_count_complete"])
        self.assertTrue(all(v is None for v in manifest["token_usage"].values()))
        self.assertEqual(manifest["known_token_usage_subtotal"], dict.fromkeys(KEYS, 0))
        self.assertEqual(self.runtime.run_codex_json.call_count, 1)

    def test_known_start_unknown_usage_totals_null(self):
        self.mode = "unknown_usage"
        self.assertEqual(self.run_main(), 1)
        manifest = self.manifest()
        self.assertEqual(manifest["model_invocations"], 1)
        self.assertTrue(manifest["model_invocation_count_complete"])
        self.assertEqual(manifest["unknown_usage_attempts"], ["survey"])
        self.assertTrue(all(v is None for v in manifest["token_usage"].values()))

    def test_paid_failure_keeps_known_usage(self):
        self.mode = "paid_failure"
        self.assertEqual(self.run_main(), 1)
        self.assert_known_usage(self.manifest())
        self.assertEqual(self.manifest()["attempts"][0]["status"], "failed")

    def test_tool_guard_failure_keeps_paid_usage(self):
        self.mode = "tool"
        self.assertEqual(self.run_main(), 1)
        self.assert_known_usage(self.manifest())
        self.assertIn("prohibited tools", self.manifest()["attempts"][0]["error"])

    def test_schema_valid_but_inexact_synthetic_response_fails(self):
        self.mode = "wrong_payload"
        self.assertEqual(self.run_main(), 1)
        self.assert_known_usage(self.manifest())
        self.assertIn("exact synthetic payload", self.manifest()["attempts"][0]["error"])

    def test_final_frozen_hash_change_is_incomplete_with_paid_usage(self):
        self.mode = "hash_drift"
        self.assertEqual(self.run_main(), 1)
        self.assertFalse(self.manifest()["hashes_unchanged"])
        self.assert_known_usage(self.manifest())

    def test_result_write_failure_keeps_stdout_and_complete_account(self):
        def write(path, value):
            if path.name == "result.json":
                raise OSError("Injected result persistence failure")
            return H.write(path, value)
        with mock.patch.object(D, "write", side_effect=write):
            self.assertEqual(self.run_main(), 1)
        self.assert_known_usage(self.last_stdout())
        self.assertEqual(self.last_stdout()["status"], "incomplete")
        self.assertTrue(self.last_stdout()["persistence_errors"])
        self.assertFalse((self.root / "survey/result.json").exists())

    def test_final_manifest_failure_keeps_full_stdout_and_never_stale_success(self):
        def write(path, value):
            if path.name == "manifest.json" and "end_utc" in value:
                raise OSError("Injected final manifest failure")
            return H.write(path, value)
        with mock.patch.object(D, "write", side_effect=write):
            self.assertEqual(self.run_main(), 1)
        self.assert_known_usage(self.last_stdout())
        self.assertEqual(self.last_stdout()["status"], "incomplete")
        self.assertNotEqual(self.manifest()["status"], "success")
        self.assertEqual(len(self.last_stdout()["attempts"]), 1)

    def test_accounting_helper_failure_preserves_available_returned_usage(self):
        self.runtime._codex_attempt_accounting.side_effect = RuntimeError("Injected accounting failure")
        self.assertEqual(self.run_main(), 1)
        self.assert_known_usage(self.last_stdout())
        self.assertEqual(self.last_stdout()["status"], "incomplete")

    def test_accounting_helper_failure_preserves_known_failed_call_usage(self):
        self.mode = "paid_failure"
        self.runtime._codex_attempt_accounting.side_effect = RuntimeError("Injected accounting failure")
        self.assertEqual(self.run_main(), 1)
        self.assert_known_usage(self.last_stdout())
        self.assertEqual(self.last_stdout()["status"], "incomplete")


if __name__ == "__main__":
    unittest.main()
