"""No-model regression coverage for ablation execution and durable accounting."""

import concurrent.futures
from contextlib import ExitStack
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock


DRIVER_PATH = (
    Path(__file__).resolve().parents[1]
    / "experiments/study_inconsistent_2/entity_discovery_iterations"
    / "run_verifier_view_ablation.py"
)
SPEC = importlib.util.spec_from_file_location("verifier_view_ablation_driver_tested", DRIVER_PATH)
DRIVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DRIVER)
TOKEN_KEYS = ("input_tokens", "cached_input_tokens", "output_tokens", "total_tokens")
USAGE = dict(zip(TOKEN_KEYS, (13, 3, 7, 20)))


class VerifierViewAblationDriverTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "ablation"
        self.source_batch = Path(self.temporary.name) / "source"
        self.root.mkdir()
        self.source_batch.mkdir()
        (self.root / "sources").mkdir()
        shutil.copyfile(DRIVER_PATH, self.root / "sources" / DRIVER_PATH.name)
        self.schema = self.root / "schema.json"
        self.schema.write_text('{"type":"object"}')
        self.args = SimpleNamespace(output_root=self.root, source_batch=self.source_batch)
        self.invocations = []
        self.invocations_lock = threading.Lock()
        self.runtime = SimpleNamespace(
            TOKEN_KEYS=TOKEN_KEYS,
            _codex_version=mock.Mock(return_value="mock-no-model"),
            run_codex_json=mock.Mock(side_effect=self.fake_invocation),
            validate_verifier_report=mock.Mock(),
            _codex_attempt_accounting=mock.Mock(side_effect=self.fake_accounting),
        )
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.patches.enter_context(mock.patch.object(DRIVER, "load_runtime", return_value=self.runtime))
        self.patches.enter_context(mock.patch.dict(sys.modules, {
            "jsonschema": SimpleNamespace(validate=mock.Mock()),
        }))
        self.patches.enter_context(mock.patch.dict(os.environ))

    def prepared(self, count):
        calls = []
        for index in range(count):
            directory = self.root / f"call_{index}"
            directory.mkdir()
            (directory / "workdir").mkdir()
            prompt = directory / "prompt.txt"
            prompt.write_text("synthetic verifier input")
            context = directory / "context.json"
            context.write_text("{}")
            calls.append({
                "call_id": f"call_{index}",
                "directory": str(directory),
                "prompt": str(prompt),
                "context": str(context),
                "attachments": [],
                "verifier_id": "verifier_1",
            })
        DRIVER.write(self.root / "manifest.json", {
            "status": "prepared",
            "source_batch": str(self.source_batch),
            "schema": str(self.schema),
            "hashes": {},
            "max_workers": 2,
            "model": "mock-no-model",
            "calls": calls,
            "results": [],
        })

    def fake_invocation(self, **kwargs):
        """A paid-call-shaped result, without a subprocess, image, or API call."""
        with self.invocations_lock:
            self.invocations.append(kwargs["output_path"].parent.name)
        kwargs["events_path"].write_text(json.dumps({
            "type": "turn.completed", "usage": USAGE,
        }) + "\n")
        kwargs["stderr_path"].write_text("")
        payload = {"reviews": []}
        kwargs["output_path"].write_text(json.dumps(payload))
        return SimpleNamespace(payload=payload, token_usage=dict(USAGE))

    @staticmethod
    def fake_accounting(*, invocation, error, events_path):
        if invocation is None:
            raise AssertionError("This fixture must account a completed fake invocation")
        return {
            "subprocess_started": True,
            "token_usage": invocation.token_usage,
            "runtime_seconds": 0.01,
            "thread_id": "mock-thread",
            "returncode": 0,
            "failure_kind": "python_validation" if error else None,
        }

    def manifest(self):
        return DRIVER.read(self.root / "manifest.json")

    def test_concurrent_execute_claim_launches_batch_only_once(self):
        self.prepared(1)
        # Both callers have already read "prepared" when the barrier releases.
        # The filesystem claim, rather than the status read, must arbitrate them.
        ready = threading.Barrier(2, timeout=10)

        def rendezvous(_batch):
            ready.wait()
            return self.runtime

        outcomes = []
        with mock.patch.object(DRIVER, "load_runtime", side_effect=rendezvous):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(DRIVER.execute, self.args) for _ in range(2)]
                for future in futures:
                    try:
                        outcomes.append(future.result(timeout=20))
                    except FileExistsError as exc:
                        outcomes.append(exc)

        self.assertEqual(sum(outcome == 0 for outcome in outcomes), 1)
        self.assertEqual(sum(isinstance(outcome, FileExistsError) for outcome in outcomes), 1)
        self.assertEqual(self.invocations, ["call_0"])
        self.assertEqual(self.manifest()["model_invocations"], 1)
        self.assertEqual(self.manifest()["token_usage"], USAGE)
        self.assertEqual(self.manifest()["status"], "success")

    def test_worker_error_after_paid_attempt_preserves_all_call_accounting(self):
        self.prepared(3)
        write = DRIVER.write

        def fail_report_write(path, data):
            path = Path(path)
            if path == self.root / "call_0" / "report.json":
                # Fault occurs after attempt accounting was persisted but before
                # that worker returns its logical result to the main collector.
                raise OSError("injected report publication failure")
            return write(path, data)

        with mock.patch.object(DRIVER, "write", side_effect=fail_report_write):
            self.assertEqual(DRIVER.execute(self.args), 1)

        manifest = self.manifest()
        results = {result["call_id"]: result for result in manifest["results"]}
        self.assertCountEqual(self.invocations, ["call_0", "call_1", "call_2"])
        self.assertEqual(len(results), 3)
        self.assertEqual(results["call_0"]["status"], "failed")
        self.assertIn("injected report publication failure", results["call_0"]["worker_error"])
        self.assertEqual(results["call_1"]["status"], "success")
        self.assertEqual(results["call_2"]["status"], "success")
        self.assertEqual(len(results["call_0"]["attempts"]), 1)
        self.assertTrue(results["call_0"]["attempts"][0]["subprocess_started"])
        self.assertEqual(manifest["model_invocations"], 3)
        self.assertEqual(manifest["token_usage"], {key: value * 3 for key, value in USAGE.items()})
        self.assertEqual(manifest["unaccounted_attempt_starts"], [])
        self.assertEqual(manifest["status"], "incomplete")

    def test_unaccounted_started_attempt_has_unknown_total_cost(self):
        self.prepared(1)
        # Simulate loss between a completed call and durable accounting. The
        # started marker must stop the empty known-attempt sum becoming zero cost.
        with mock.patch.object(
            self.runtime, "_codex_attempt_accounting",
            side_effect=OSError("injected accounting failure"),
        ):
            self.assertEqual(DRIVER.execute(self.args), 1)

        manifest = self.manifest()
        self.assertEqual(self.invocations, ["call_0"])
        self.assertEqual(manifest["status"], "incomplete")
        self.assertEqual(manifest["token_usage"], dict.fromkeys(TOKEN_KEYS))
        self.assertEqual(len(manifest["unaccounted_attempt_starts"]), 1)
        marker = manifest["unaccounted_attempt_starts"][0]
        self.assertEqual((marker["call_id"], marker["attempt"]), ("call_0", 1))
        self.assertTrue(Path(marker["marker"]).is_file())
        self.assertEqual(manifest["results"][0]["attempts"], [])


if __name__ == "__main__":
    unittest.main()
