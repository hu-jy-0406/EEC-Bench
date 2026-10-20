"""No-model subprocess tests for direct, crash-surviving Codex event files."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import ensemble_shot_entity_detection as runner  # noqa: E402

USAGE = {"input_tokens": 31, "cached_input_tokens": 7,
         "output_tokens": 11, "total_tokens": 42}
FAKE_CLI = r'''
import json, os, pathlib, sys, time
raw_input = sys.stdin.read()
config = json.loads(raw_input)
output = pathlib.Path(sys.argv[sys.argv.index("--output-last-message") + 1])
root = output.parent
(root / "received.json").write_text(json.dumps({"argv": sys.argv[1:], "stdin": raw_input}))
os.write(1, b'{"type":"thread.started","thread_id":"fake-thread"}\n')
os.write(2, b'early stderr\n')
mode = config.get("mode", "success")
if mode != "early":
    os.write(1, (json.dumps({"type":"turn.completed", "usage": {
        "input_tokens":31, "cached_input_tokens":7, "output_tokens":11,
        "total_tokens":42}}) + "\n").encode())
if mode in ("early", "timeout"):
    os.write(1, b'{"type":"partial","text":"\xf0\x9f')
    (root / "ready.json").write_text(json.dumps({"pid":os.getpid(), "parent":os.getppid()}))
    parent = os.getppid()
    while os.getppid() == parent:
        time.sleep(.01)
    sys.exit(0)
if mode != "missing":
    output.write_text("bad json" if mode == "invalid" else
                      "[]" if mode == "array" else '{"ok":true}')
sys.exit(17 if mode == "nonzero" else 0)
'''


class CodexStreamingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cli = self.root / "fake_codex"
        self.cli.write_text("#!" + sys.executable + "\n" + FAKE_CLI)
        self.cli.chmod(0o755)
        self.schema = self.root / "schema.json"
        self.schema.write_text("{}")
        self.images = []
        for i in range(6):
            image = self.root / f"frame_{i}.jpg"
            image.write_bytes(b"fake CLI does not decode images")
            self.images.append(image)

    def arguments(self, mode="success", **extra):
        return {"prompt": json.dumps({"mode": mode, "text": "中文\nsecond line"}),
                "attachments": self.images, "schema_path": self.schema,
                "output_path": self.root / "answer.json",
                "events_path": self.root / "events.jsonl",
                "stderr_path": self.root / "stderr.log", "codex_bin": str(self.cli),
                "model": "gpt-5.6-sol", "timeout_sec": 5, "work_dir": self.root,
                **extra}

    def account(self, error):
        return runner._codex_attempt_accounting(
            invocation=None, error=error, events_path=self.root / "events.jsonl")

    def test_original_argv_stdin_and_session_modes_remain_exact(self):
        for extra in ({}, {"persistent": True}, {"resume_thread_id": "prior-thread"}):
            with self.subTest(extra=extra):
                args = self.arguments(**extra)
                stdout, stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    result = runner.run_codex_json(**args)
                received = json.loads((self.root / "received.json").read_text())
                expected = (["exec", "resume", "--json", "--output-schema", str(self.schema),
                             "--output-last-message", str(args["output_path"])]
                            if "resume_thread_id" in extra else
                            ["--ask-for-approval", "never", "exec"]
                            + ([] if extra.get("persistent") else ["--ephemeral"])
                            + ["--color", "never", "--json", "--sandbox", "read-only",
                               "--output-schema", str(self.schema), "--output-last-message",
                               str(args["output_path"]), "--cd", str(self.root)])
                expected += ["--model", "gpt-5.6-sol"]
                for image in self.images:
                    expected += ["--image", str(image)]
                if "resume_thread_id" in extra:
                    expected.append("prior-thread")
                expected.append("-")
                self.assertEqual(received, {"argv": expected, "stdin": args["prompt"]})
                self.assertEqual(result.payload, {"ok": True})
                self.assertEqual(result.token_usage, USAGE)
                self.assertEqual((stdout.getvalue(), stderr.getvalue()), ("", ""))

    def test_events_survive_forced_death_of_only_test_runner(self):
        # A dedicated test session is the only process tree eligible for cleanup.
        # Production run_codex_json does not create sessions or signal groups.
        args = self.arguments("early", timeout_sec=20)
        serial = {k: [str(p) for p in v] if k == "attachments" else
                  str(v) if isinstance(v, Path) else v for k, v in args.items()}
        harness = (
            "import json,sys;from pathlib import Path;"
            f"sys.path.insert(0,{str(SCRIPTS)!r});"
            "import ensemble_shot_entity_detection as r;"
            f"a=json.loads({json.dumps(serial)!r});"
            "a['attachments']=[Path(p) for p in a['attachments']];"
            "a.update({k:Path(a[k]) for k in "
            "('schema_path','output_path','events_path','stderr_path','work_dir')});"
            "r.run_codex_json(**a)"
        )
        parent = subprocess.Popen([sys.executable, "-B", "-c", harness],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  start_new_session=True)
        child = None
        try:
            deadline = time.monotonic() + 10
            ready = self.root / "ready.json"
            while not ready.exists() and parent.poll() is None and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(ready.exists(), "fake CLI did not reach its write checkpoint")
            child = json.loads(ready.read_text())["pid"]
            before = (self.root / "events.jsonl").read_bytes()
            self.assertIn(b"thread.started", before)
            self.assertEqual((self.root / "stderr.log").read_bytes(), b"early stderr\n")
            parent.kill()
            self.assertEqual(parent.wait(timeout=5), -signal.SIGKILL)
            self.assertEqual((self.root / "events.jsonl").read_bytes(), before)
            self.assertFalse((self.root / "answer.json").exists())
            record = self.account(RuntimeError("test runner was killed"))
            self.assertTrue(record["subprocess_started"])
            self.assertEqual(record["thread_id"], "fake-thread")
            self.assertIsNone(record["token_usage"])
        finally:
            if parent.poll() is None:
                parent.kill()
                parent.wait(timeout=5)
            # Signal only the recorded fake child's PID if it still belongs to
            # this test's private session. Never signal an inherited/shared group.
            if child is not None:
                try:
                    if os.getsid(child) == parent.pid:
                        os.kill(child, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_timeout_retains_bytes_completed_usage_and_reaps_child(self):
        with self.assertRaises(runner.CodexCallError) as caught:
            runner.run_codex_json(**self.arguments("timeout", timeout_sec=1))
        error = caught.exception
        self.assertEqual(error.failure_kind, "timeout")
        self.assertEqual(error.token_usage, USAGE)
        self.assertEqual(error.thread_id, "fake-thread")
        self.assertIsNone(error.returncode)
        self.assertTrue((self.root / "events.jsonl").read_bytes().endswith(b"\xf0\x9f"))
        pid = json.loads((self.root / "ready.json").read_text())["pid"]
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_completed_usage_survives_nonzero_missing_and_invalid_outputs(self):
        for mode, kind in [("nonzero", "nonzero_exit"), ("missing", "missing_output"),
                           ("invalid", "invalid_json"), ("array", "invalid_payload_type")]:
            with self.subTest(mode=mode):
                (self.root / "answer.json").unlink(missing_ok=True)
                with self.assertRaises(runner.CodexCallError) as caught:
                    runner.run_codex_json(**self.arguments(mode))
                self.assertEqual(caught.exception.failure_kind, kind)
                self.assertEqual(self.account(caught.exception)["token_usage"], USAGE)
                self.assertTrue(caught.exception.subprocess_started)

    def test_completed_usage_survives_later_stderr_read_failure(self):
        original = Path.read_bytes

        def fail_stderr(path):
            if path == self.root / "stderr.log":
                raise OSError("injected stderr read failure")
            return original(path)
        with mock.patch.object(Path, "read_bytes", fail_stderr):
            with self.assertRaises(runner.CodexCallError) as caught:
                runner.run_codex_json(**self.arguments())
        self.assertEqual(caught.exception.failure_kind, "artifact_read")
        self.assertEqual(caught.exception.token_usage, USAGE)

    def test_completed_usage_survives_final_payload_read_failure(self):
        original = Path.read_text

        def fail_output(path, *args, **kwargs):
            if path == self.root / "answer.json":
                raise OSError("injected output read failure")
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, "read_text", fail_output):
            with self.assertRaises(runner.CodexCallError) as caught:
                runner.run_codex_json(**self.arguments())
        self.assertEqual(caught.exception.failure_kind, "artifact_read")
        self.assertEqual(self.account(caught.exception)["token_usage"], USAGE)

    def test_spawn_failure_is_known_not_started_despite_empty_streams(self):
        with mock.patch.object(runner.subprocess, "Popen", side_effect=OSError("exec failed")):
            with self.assertRaises(runner.CodexCallError) as caught:
                runner.run_codex_json(**self.arguments())
        self.assertEqual((self.root / "events.jsonl").read_bytes(), b"")
        record = self.account(caught.exception)
        self.assertIs(record["subprocess_started"], False)
        self.assertFalse(record["subprocess_start_unknown"])
        self.assertIsNone(record["token_usage"])

    def test_unclassified_launch_exception_retains_unknown_start(self):
        with mock.patch.object(runner.subprocess, "Popen", side_effect=RuntimeError("unknown launch")):
            with self.assertRaises(runner.CodexCallError) as caught:
                runner.run_codex_json(**self.arguments())
        record = self.account(caught.exception)
        self.assertIsNone(record["subprocess_started"])
        self.assertTrue(record["subprocess_start_unknown"])
        self.assertEqual(runner._aggregate_usage([USAGE, record["token_usage"]]),
                         {k: None for k in USAGE})

    def test_empty_streams_without_launch_evidence_are_unknown(self):
        (self.root / "events.jsonl").write_bytes(b"")
        record = self.account(OSError("lost lifecycle information"))
        self.assertIsNone(record["subprocess_started"])
        self.assertTrue(record["subprocess_start_unknown"])

    def test_prelaunch_file_failure_does_not_spawn_or_reuse_old_usage(self):
        original = Path.open
        (self.root / "events.jsonl").write_text(json.dumps({"usage": USAGE}))

        def fail_open(path, *args, **kwargs):
            if path == self.root / "stderr.log":
                raise OSError("injected open failure")
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, "open", fail_open), \
                mock.patch.object(runner.subprocess, "Popen") as popen:
            with self.assertRaises(runner.CodexCallError) as caught:
                runner.run_codex_json(**self.arguments())
        popen.assert_not_called()
        self.assertIs(self.account(caught.exception)["subprocess_started"], False)
        self.assertIsNone(caught.exception.token_usage)

    def test_main_manifest_retains_false_unknown_and_paid_failure_accounting(self):
        from PIL import Image
        from test_prompt_unbound_pipelines import ensemble_ledger, ensemble_proposal

        Image.new("RGB", (20, 20), "white").save(self.images[0])
        sample = runner.shot_graph.VideoSample(
            frames={10: None}, frame_paths={10: self.images[0]}, num_frames=11, fps=5.)
        for state in (False, None, True):
            with self.subTest(start_state=state):
                directory = self.root / ("main_" + str(state))

                def invoke(**kwargs):
                    role = kwargs["output_path"].name.split(".")[0]
                    if role == "detector_4":
                        raise runner.CodexCallError(
                            "injected detector failure", failure_kind="subprocess_error",
                            runtime_seconds=.01, token_usage=USAGE if state is True else None,
                            thread_id=None, returncode=None, subprocess_started=state)
                    return runner.CodexInvocation(
                        ensemble_ledger(role, "detector", [ensemble_proposal(role + "_e1")]),
                        USAGE, role + "_thread", .01)

                with mock.patch.object(runner, "_codex_version", return_value="fake"), \
                        mock.patch.object(runner, "run_codex_json", side_effect=invoke), \
                        contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(runner.EnsembleIncompleteError):
                        runner.run_ensemble_detection(
                            sample=sample, shot_id="shot1", prompt_entities=[],
                            run_dir=directory, codex_bin=str(self.cli), model=None,
                            timeout_sec=5, max_workers=1)
                manifest = json.loads((directory / "run_manifest.json").read_text())
                failed = [r for r in manifest["detector_attempts"]
                          if r["detector_id"] == "detector_4"]
                self.assertEqual(len(failed), 2)
                for row in failed:
                    self.assertIs(row["subprocess_started"], state)
                    self.assertEqual(row["subprocess_start_unknown"], state is None)
                expected = {k: None if state is None else v * (5 if state else 3)
                            for k, v in USAGE.items()}
                self.assertEqual(manifest["token_usage"], expected)

    def test_closure_manifest_retains_false_unknown_and_paid_failure_accounting(self):
        from test_detector_closure_stage import FRAMES, PATHS, delta, ledger

        for state in (False, None, True):
            with self.subTest(start_state=state):
                source, calls = ledger(), []

                def invoke(**kwargs):
                    calls.append(kwargs)
                    if len(calls) == 1:
                        raise runner.CodexCallError(
                            "injected closure failure", failure_kind="subprocess_error",
                            runtime_seconds=.01, token_usage=USAGE if state is True else None,
                            thread_id=None, returncode=None, subprocess_started=state)
                    return runner.CodexInvocation(delta(source), USAGE, "retry-thread", .01)

                result = runner.detector_closure_stage.run_stage(
                    ledgers=[source], shot_id="shot1", valid_frame_ids=FRAMES,
                    allowed_input_paths=PATHS, attachments=[Path(p) for p in PATHS],
                    detector_policy_text="Unchanged fixture policy.", shot_manifest={},
                    run_dir=self.root / ("closure_" + str(state)), max_rounds=1,
                    max_workers=1, invoke_json=invoke, validate_ledger=runner.validate_ledger,
                    invocation_kwargs={}, account_attempt=runner._codex_attempt_accounting)
                self.assertEqual(result["status"], "complete")
                self.assertEqual(len(calls), 2)
                self.assertEqual(calls[0]["prompt"], calls[1]["prompt"])
                first = result["attempts"][0]
                self.assertIs(first["subprocess_started"], state)
                self.assertEqual(first["subprocess_start_unknown"], state is None)
                expected = ([USAGE] if state is False else
                            [None, USAGE] if state is None else [USAGE, USAGE])
                self.assertEqual(result["token_usages"], expected)


if __name__ == "__main__":
    unittest.main()
