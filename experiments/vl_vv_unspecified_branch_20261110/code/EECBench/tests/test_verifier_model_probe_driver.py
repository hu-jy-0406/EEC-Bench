"""No-model regression coverage for ablation execution and durable accounting."""

import concurrent.futures
from contextlib import ExitStack
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock


DRIVER_PATH = (
    Path(__file__).resolve().parents[1]
    / "experiments/study_inconsistent_2/entity_discovery_iterations"
    / "run_verifier_model_probe.py"
)
SPEC = importlib.util.spec_from_file_location("verifier_model_probe_driver_tested", DRIVER_PATH)
DRIVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DRIVER)
TOKEN_KEYS = ("input_tokens", "cached_input_tokens", "output_tokens", "total_tokens")
USAGE = dict(zip(TOKEN_KEYS, (13, 3, 7, 20)))


class VerifierModelProbeDriverTests(unittest.TestCase):
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
        self.reference = Path(self.temporary.name) / "view_reference"
        self.args = SimpleNamespace(output_root=self.root, source_batch=self.source_batch,
                                    reference_view_experiment=self.reference)
        self.wrapper = self.root / "sources/codex_reasoning_high.sh"
        self.wrapper.write_text(DRIVER.wrapper_text())
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
            config = directory / "model_config.json"
            model = DRIVER.MODELS[index % 2]
            DRIVER.write(config, {"model": model, "reasoning_effort": "high",
                                  "timeout_sec": 1800, "codex_bin": str(self.wrapper)})
            calls.append({
                "model": model, "reasoning_effort": "high", "model_config": str(config),
                "call_id": f"call_{index}",
                "directory": str(directory),
                "prompt": str(prompt),
                "context": str(context),
                "attachments": [],
                "verifier_id": "verifier_1",
            })
        plan = {
            "source_batch": str(self.source_batch),
            "reference_view_experiment": str(self.reference),
            "schema": str(self.schema), "codex_wrapper": str(self.wrapper),
            "max_workers": 2, "calls": calls,
        }
        plan_path = self.root / "execution_plan.json"
        DRIVER.write(plan_path, plan)
        hashes = {str(plan_path): DRIVER.sha(plan_path)}
        hashes.update({spec["model_config"]: DRIVER.sha(spec["model_config"]) for spec in calls})
        DRIVER.write(self.root / "manifest.json", {
            **plan, "status": "prepared", "execution_plan": str(plan_path),
            "hashes": hashes, "results": [],
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


    def test_concurrent_calls_keep_model_and_config_isolated(self):
        self.prepared(2)
        ready = threading.Barrier(2, timeout=10)
        captured = []

        def concurrent_invocation(**kwargs):
            captured.append(kwargs)
            ready.wait()
            return self.fake_invocation(**kwargs)

        with mock.patch.object(self.runtime, "run_codex_json", side_effect=concurrent_invocation):
            self.assertEqual(DRIVER.execute(self.args), 0)
        by_call = {item["output_path"].parent.name: item for item in captured}
        for index, model in enumerate(DRIVER.MODELS):
            invocation = by_call[f"call_{index}"]
            self.assertEqual(invocation["model"], model)
            self.assertEqual(invocation["codex_bin"], str(self.wrapper))
            self.assertEqual(invocation["timeout_sec"], 1800)
            self.assertFalse(invocation["persistent"])
        self.assertEqual({r["model"] for r in self.manifest()["results"]}, set(DRIVER.MODELS))

    def test_manifest_routing_mutation_fails_before_claim_or_call(self):
        self.prepared(2)
        manifest = self.manifest()
        manifest["calls"][0]["model"] = DRIVER.MODELS[1]
        DRIVER.write(self.root / "manifest.json", manifest)
        with self.assertRaisesRegex(RuntimeError, "frozen plan"):
            DRIVER.execute(self.args)
        self.runtime.run_codex_json.assert_not_called()
        self.assertFalse((self.root / "execute_claim.json").exists())

    def test_retry_keeps_exact_prompt_attachments_model_and_config(self):
        self.prepared(1)
        with mock.patch.object(self.runtime, "validate_verifier_report",
                               side_effect=[ValueError("synthetic validation failure"), None]):
            self.assertEqual(DRIVER.execute(self.args), 0)
        calls = self.runtime.run_codex_json.call_args_list
        self.assertEqual(len(calls), 2)
        for key in ("prompt", "attachments", "schema_path", "model", "codex_bin", "timeout_sec"):
            self.assertEqual(calls[0].kwargs[key], calls[1].kwargs[key])
        self.assertEqual(self.manifest()["retry_count"], 1)
        self.assertEqual(self.manifest()["model_invocations"], 2)

    def test_config_mutation_fails_before_claim_or_call(self):
        self.prepared(1)
        spec = self.manifest()["calls"][0]
        config = DRIVER.read(spec["model_config"])
        config["reasoning_effort"] = "low"
        DRIVER.write(spec["model_config"], config)
        with self.assertRaisesRegex(RuntimeError, "changed"):
            DRIVER.execute(self.args)
        self.runtime.run_codex_json.assert_not_called()
        self.assertFalse((self.root / "execute_claim.json").exists())

    def test_wrapper_pins_high_and_preserves_exact_argument_boundaries(self):
        fake = self.root / "fake codex"
        fake.write_text('#!' + sys.executable + '\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n')
        fake.chmod(0o755)
        self.wrapper.write_text(DRIVER.wrapper_text(str(fake)))
        self.wrapper.chmod(0o755)
        args = ["--ask-for-approval", "never", "exec", "--model", "gpt-6-astra", "--image", "image path; $HOME.png", "-"]
        result = subprocess.run([str(self.wrapper), *args], check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout), ["-c", 'model_reasoning_effort="high"', *args])


class VerifierModelProbePrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.batch = self.base / "batch"
        self.reference = self.base / "reference"
        self.reference.mkdir()
        scripts = self.batch / "frozen_workspace/EECBench/scripts"
        scripts.mkdir(parents=True)
        policy = scripts / "policy.txt"
        policy.write_text("synthetic policy")
        self.schema = scripts / "schema.json"
        self.schema.write_text('{"type":"object"}')
        self.runtime = SimpleNamespace(
            VERIFIER_IDS=("verifier_1", "verifier_2"), VERIFICATION_SCHEMA=self.schema,
            _verification_view=mock.Mock(return_value={}),
            _load_skill=mock.Mock(return_value=("synthetic policy", {})),
            _inventory_base_prompt=mock.Mock(side_effect=lambda **kw: kw["shot_id"]),
            _verifier_prompt=mock.Mock(side_effect=lambda **kw: self.prompt(kw["base"], kw["verifier_id"])),
            run_codex_json=mock.Mock(),
        )
        DRIVER.write(self.batch / "robustness_manifest.json", {
            "source_hashes": {"EECBench/scripts/policy.txt": DRIVER.sha(policy),
                              "EECBench/scripts/schema.json": DRIVER.sha(self.schema)},
            "model": DRIVER.MODELS[0], "shots": list(DRIVER.SHOTS), "seeds": list(DRIVER.SEEDS),
        })
        hashes = {}
        calls = []
        for seed in DRIVER.SEEDS:
            for shot in DRIVER.SHOTS:
                shot_root = self.batch / f"seed_{seed}" / shot
                inputs = shot_root / "input_bundle"
                adjud = shot_root / "adjudication"
                prompts = shot_root / "prompts"
                for directory in (inputs, adjud, prompts):
                    directory.mkdir(parents=True)
                frames = []
                for frame_id in range(6):
                    frame = inputs / f"frame_{frame_id}.jpg"
                    frame.write_bytes(f"immutable fixture {seed} {shot} {frame_id}".encode())
                    frames.append({"frame_id": frame_id, "path": str(frame)})
                    hashes[str(frame)] = DRIVER.sha(frame)
                DRIVER.write(inputs / "shot_manifest.json", {"reference_frames": frames})
                DRIVER.write(shot_root / "run_manifest.json", {
                    "status": "success", "input_hashes": {f["path"]: hashes[f["path"]] for f in frames},
                })
                initial = {"clusters": [{"cluster_id": "c1", "anonymous_proposal_ids": ["p1"]}]}
                targets = {"cluster_ids": ["c1"], "identity_challenge_pairs": []}
                for name, payload in (("adjudicator_initial.json", initial),
                                      ("anonymized_candidates.json", {}), ("verification_targets.json", targets)):
                    DRIVER.write(adjud / name, payload)
                    hashes[str(adjud / name)] = DRIVER.sha(adjud / name)
                context = {
                    "shot_id": shot, "valid_frame_ids": list(range(6)),
                    "target_cluster_ids": ["c1"], "all_cluster_ids": ["c1"],
                    "target_proposal_ids_by_cluster": {"c1": ["p1"]},
                    "intra_cluster_split_challenges": [],
                }
                context_path = self.reference / f"context_{seed}_{shot}.json"
                DRIVER.write(context_path, context)
                hashes[str(context_path)] = DRIVER.sha(context_path)
                for verifier in self.runtime.VERIFIER_IDS:
                    old = prompts / f"{verifier}.attempt1.txt"
                    old.write_text(self.prompt(shot, verifier))
                    ref_prompt = self.reference / f"prompt_{seed}_{shot}_{verifier}.txt"
                    shutil.copyfile(old, ref_prompt)
                    hashes[str(old)] = DRIVER.sha(old)
                    hashes[str(ref_prompt)] = DRIVER.sha(ref_prompt)
                    calls.append({
                        "condition": "original", "seed": seed, "shot": shot,
                        "verifier_id": verifier, "call_id": f"ref_{seed}_{shot}_{verifier}",
                        "attachments": [f["path"] for f in frames],
                        "context": str(context_path), "prompt": str(ref_prompt),
                    })
        DRIVER.write(self.reference / "manifest.json", {
            "status": "success", "source_batch": str(self.batch), "model": DRIVER.MODELS[0],
            "schema": str(self.schema), "calls": calls, "hashes": hashes,
        })
        self.args = SimpleNamespace(source_batch=self.batch, reference_view_experiment=self.reference,
                                    output_root=self.base / "prepared")
        self.cli_binary = self.base / "frozen-cli-executable"
        self.cli_binary.write_text("#!/bin/sh\nexit 93\n")
        self.cli_binary.chmod(0o755)
        cli_link = self.base / "mutable-cli-link"
        cli_link.symlink_to(self.cli_binary)
        cli_patch = mock.patch.object(DRIVER, "CODEX_BIN", str(cli_link))
        cli_patch.start()
        self.addCleanup(cli_patch.stop)
        patch = mock.patch.object(DRIVER, "load_runtime", return_value=self.runtime)
        patch.start()
        self.addCleanup(patch.stop)

    @staticmethod
    def prompt(shot, verifier):
        return f"Synthetic immutable 原图 prompt {shot} {verifier}\n"

    def test_prepare_freezes_complete_matrix_with_byte_identical_inputs(self):
        DRIVER.prepare(self.args)
        manifest = DRIVER.read(self.args.output_root / "manifest.json")
        self.assertEqual(len(manifest["calls"]), 16)
        self.assertEqual(sum(c["model"] == DRIVER.MODELS[0] for c in manifest["calls"]), 8)
        self.assertEqual([c["model"] for c in manifest["calls"][:6]],
                         [*DRIVER.MODELS, *DRIVER.MODELS, *reversed(DRIVER.MODELS)])
        reference = DRIVER.read(self.reference / "manifest.json")
        lookup = {c["call_id"]: c for c in reference["calls"]}
        for call in manifest["calls"]:
            original = lookup[call["reference_call_id"]]
            self.assertEqual(Path(call["prompt"]).read_bytes(), Path(original["prompt"]).read_bytes())
            self.assertEqual(Path(call["context"]).read_bytes(), Path(original["context"]).read_bytes())
            self.assertEqual(call["attachments"], original["attachments"])
            self.assertEqual(len(call["attachments"]), 6)
            self.assertEqual(call["reasoning_effort"], "high")
        DRIVER.verify_hashes(manifest["hashes"])
        DRIVER.validate_execution_plan(manifest)
        self.assertEqual(manifest["codex_binary"], str(self.cli_binary))
        self.assertEqual(manifest["codex_binary_sha256"], DRIVER.sha(self.cli_binary))
        self.assertEqual(Path(manifest["codex_wrapper"]).read_text(), DRIVER.wrapper_text(str(self.cli_binary)))
        self.runtime.run_codex_json.assert_not_called()
        self.assertFalse((self.args.output_root / "execute_claim.json").exists())

    def test_prepare_rejects_reordered_reference_attachments(self):
        path = self.reference / "manifest.json"
        manifest = DRIVER.read(path)
        manifest["calls"][0]["attachments"].reverse()
        DRIVER.write(path, manifest)
        with self.assertRaisesRegex(RuntimeError, "attachment order"):
            DRIVER.prepare(self.args)
        self.runtime.run_codex_json.assert_not_called()

    def test_resolved_binary_mutation_stops_execute_before_any_call(self):
        DRIVER.prepare(self.args)
        self.cli_binary.write_text("#!/bin/sh\nexit 94\n")
        with self.assertRaisesRegex(RuntimeError, "changed"):
            DRIVER.execute(self.args)
        self.runtime.run_codex_json.assert_not_called()
        self.assertFalse((self.args.output_root / "execute_claim.json").exists())

    def test_prepare_rejects_prompt_drift_even_with_fresh_reference_hash(self):
        path = self.reference / "manifest.json"
        manifest = DRIVER.read(path)
        prompt = Path(manifest["calls"][0]["prompt"])
        prompt.write_text(prompt.read_text() + "additional text")
        manifest["hashes"][str(prompt)] = DRIVER.sha(prompt)
        DRIVER.write(path, manifest)
        with self.assertRaisesRegex(RuntimeError, "original initial verifier prompt"):
            DRIVER.prepare(self.args)
        self.runtime.run_codex_json.assert_not_called()


if __name__ == "__main__":
    unittest.main()
