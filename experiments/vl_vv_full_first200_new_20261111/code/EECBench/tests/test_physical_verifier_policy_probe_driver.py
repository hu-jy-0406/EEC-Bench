"""Bounded no-model tests for frozen policy isolation and paid-failure accounting."""

import concurrent.futures
from contextlib import ExitStack
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock


PATH = (Path(__file__).resolve().parents[1]
        / "experiments/study_inconsistent_2/entity_discovery_iterations/run_physical_verifier_policy_probe.py")
SPEC = importlib.util.spec_from_file_location("physical_policy_probe_tested", PATH)
D = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(D)
TOKEN_KEYS = ("input_tokens", "cached_input_tokens", "output_tokens", "total_tokens")
USAGE = dict(zip(TOKEN_KEYS, (13, 3, 7, 20)))


class PhysicalVerifierPolicyProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.batch = self.base / "source"
        frozen = self.batch / "frozen_workspace"
        scripts = frozen / "EECBench/scripts"
        scripts.mkdir(parents=True)
        for name in ("ensemble_shot_entity_detection.py", "physical_identity_review.py"):
            (scripts / name).write_text("# immutable synthetic runtime fixture\n")
        old = frozen / D.POLICY_RELATIVE
        old.parent.mkdir(parents=True)
        old.write_text("isolated policy\n")
        schema = frozen / D.SCHEMA_RELATIVE
        schema.parent.mkdir(parents=True)
        schema.write_text('{"type":"object"}')
        self.new_policy = self.base / "clarified.md"
        self.new_policy.write_text("isolated policy\nexplicit salience scope\n")
        self.old_policy = old
        self.binary = self.base / "real-cli"
        self.binary.write_text("#!/bin/sh\nexit 92\n")
        self.binary.chmod(0o755)
        link = self.base / "cli-link"
        link.symlink_to(self.binary)
        D.write(self.batch / "robustness_manifest.json", {
            "model": D.MODEL, "shots": [D.SHOT], "seeds": list(D.SEEDS),
            "source_hashes": {str(p.relative_to(frozen)): D.sha(p)
                              for p in (old, schema, scripts / "ensemble_shot_entity_detection.py",
                                        scripts / "physical_identity_review.py")}})
        self.runtime = SimpleNamespace(
            __file__=str(scripts / "ensemble_shot_entity_detection.py"),
            VERIFIER_IDS=D.VERIFIERS, TOKEN_KEYS=TOKEN_KEYS,
            _verification_view=mock.Mock(side_effect=self.view),
            _load_skill=mock.Mock(side_effect=AssertionError("Full Skill must not be loaded")),
            validate_codex_schema_transport=mock.Mock(side_effect=D.read),
            validate_verifier_report=mock.Mock(),
            _codex_version=mock.Mock(return_value="mock-no-model"),
            run_codex_json=mock.Mock(side_effect=self.invoke),
            _codex_attempt_accounting=mock.Mock(side_effect=self.account),
        )
        self.physical = SimpleNamespace(
            __file__=str(scripts / "physical_identity_review.py"),
            build_verifier_prompt=mock.Mock(side_effect=self.prompt),
            validate_verifier_identity_fields=mock.Mock(),
        )
        self.invocations = []
        self.lock = threading.Lock()
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.patches.enter_context(mock.patch.object(D, "CODEX_BIN", str(link)))
        self.patches.enter_context(mock.patch.object(D, "load_runtime", return_value=(self.runtime, self.physical)))
        self.patches.enter_context(mock.patch.dict(os.environ))
        for seed in D.SEEDS:
            root = self.batch / f"seed_{seed}" / D.SHOT
            for name in ("input_bundle", "adjudication", "prompts"):
                (root / name).mkdir(parents=True)
            frames = []
            for frame_id in range(6):
                path = root / f"input_bundle/frame_{frame_id}.jpg"
                path.write_bytes(f"synthetic unchanged {seed}:{frame_id}".encode())
                frames.append({"frame_id": frame_id, "path": str(path)})
            D.write(root / "input_bundle/shot_manifest.json", {"reference_frames": frames})
            D.write(root / "run_manifest.json", {
                "status": "success", "model": D.MODEL, "identity_review_policy": "physical_v0.6",
                "input_hashes": {f["path"]: D.sha(f["path"]) for f in frames}})
            initial = {"clusters": [{"cluster_id": "a", "anonymous_proposal_ids": ["p1"],
                                      "decision": "prior_verdict_forbidden"},
                                     {"cluster_id": "b", "anonymous_proposal_ids": ["p2"]}]}
            targets = {"cluster_ids": ["a", "b"], "identity_challenge_pairs": [
                {"cluster_id_a": "a", "cluster_id_b": "b"}],
                "intra_cluster_divergent_footprint_challenges": []}
            for name, payload in (("adjudicator_initial.json", initial),
                                  ("anonymized_candidates.json", {"proposals": []}),
                                  ("verification_targets.json", targets)):
                D.write(root / "adjudication" / name, payload)
            for verifier in D.VERIFIERS:
                prompt = self.prompt(shot_id=D.SHOT, verifier_id=verifier,
                                     verification_view=self.view(initial, {}, targets["cluster_ids"],
                                                                 targets["identity_challenge_pairs"], []),
                                     valid_frame_ids=list(range(6)), reference_frames=frames,
                                     allowed_input_paths=[f["path"] for f in frames], policy_text=old.read_text())
                (root / f"prompts/{verifier}.attempt1.txt").write_text(prompt)
        self.args = SimpleNamespace(source_batch=self.batch, clarified_policy=self.new_policy,
                                    output_root=self.base / "prepared")

    @staticmethod
    def view(initial, anonymous, targets, pairs, splits):
        return {"targets": [{"cluster_id": c["cluster_id"],
                              "anonymous_proposal_ids": c["anonymous_proposal_ids"]}
                             for c in initial["clusters"] if c["cluster_id"] in targets],
                "identity_challenge_pairs": pairs, "intra_cluster_divergent_footprint_challenges": splits}

    @staticmethod
    def prompt(**kwargs):
        policy = kwargs.pop("policy_text")
        return "isolated verifier\n" + policy + json.dumps(kwargs, sort_keys=True)

    def invoke(self, **kwargs):
        with self.lock:
            self.invocations.append(copy.copy(kwargs))
        kwargs["events_path"].write_text(json.dumps({"type": "turn.completed", "usage": USAGE}) + "\n")
        kwargs["stderr_path"].write_text("")
        payload = {"reviews": [], "raw_kept": True}
        kwargs["output_path"].write_text(json.dumps(payload))
        return SimpleNamespace(payload=payload, token_usage=dict(USAGE))

    @staticmethod
    def account(*, invocation, error, events_path):
        return {"subprocess_started": True,
                "token_usage": invocation.token_usage if invocation else None,
                "runtime_seconds": 0.01, "returncode": 0 if invocation else 1,
                "thread_id": events_path.parent.name,
                "failure_kind": "python_validation" if invocation and error else "transport" if error else None}

    def prepared(self):
        D.prepare(self.args)
        return D.read(self.args.output_root / "manifest.json")

    def manifest(self):
        return D.read(self.args.output_root / "manifest.json")

    def test_prepare_freezes_eight_policy_only_calls_and_resolved_binary(self):
        manifest = self.prepared()
        self.assertEqual(len(manifest["calls"]), 8)
        self.assertEqual(manifest["maximum_identical_input_retries"], 0)
        self.assertEqual(manifest["codex_binary"], str(self.binary))
        self.runtime._load_skill.assert_not_called()
        self.runtime.run_codex_json.assert_not_called()
        old, new = self.old_policy.read_text(), self.new_policy.read_text()
        for seed in D.SEEDS:
            for verifier in D.VERIFIERS:
                calls = {c["condition"]: c for c in manifest["calls"]
                         if c["seed"] == seed and c["verifier_id"] == verifier}
                a, b = (calls[c] for c in D.CONDITIONS)
                self.assertEqual(a["attachments"], b["attachments"])
                self.assertEqual(a["context"], b["context"])
                baseline, changed = Path(a["prompt"]).read_text(), Path(b["prompt"]).read_text()
                self.assertEqual(changed, baseline.replace(old, new, 1))
                self.assertNotIn("prior_verdict_forbidden", baseline)
                self.assertEqual(D.read(a["context"])["target_cluster_ids"], ["a", "b"])
        firsts = [c["condition"] for c in manifest["calls"] if c["verifier_id"] == "verifier_1"]
        self.assertEqual(firsts, [*D.CONDITIONS, *reversed(D.CONDITIONS)])
        self.assertNotIn(str(self.batch / "robustness_manifest.json"), manifest["hashes"])

    def test_baseline_drift_fails_before_any_call(self):
        path = self.batch / f"seed_101/{D.SHOT}/prompts/verifier_1.attempt1.txt"
        path.write_text(path.read_text() + "drift")
        with self.assertRaisesRegex(RuntimeError, "byte for byte"):
            D.prepare(self.args)
        self.runtime.run_codex_json.assert_not_called()

    def test_partial_targetset_is_rejected(self):
        path = self.batch / f"seed_101/{D.SHOT}/adjudication/verification_targets.json"
        payload = D.read(path)
        payload["cluster_ids"] = ["a"]
        D.write(path, payload)
        with self.assertRaisesRegex(RuntimeError, "complete unchanged"):
            D.prepare(self.args)

    def test_extension_failure_keeps_raw_usage_and_never_retries(self):
        self.prepared()
        self.physical.validate_verifier_identity_fields.side_effect = ValueError("exact union evidence missing")
        self.assertEqual(D.execute(self.args), 1)
        manifest = self.manifest()
        self.assertEqual(len(self.invocations), 8)
        self.assertEqual(self.runtime.validate_verifier_report.call_count, 8)
        self.assertEqual(self.physical.validate_verifier_identity_fields.call_count, 8)
        self.assertEqual(manifest["token_usage"], {k: v * 8 for k, v in USAGE.items()})
        self.assertEqual(manifest["retry_count"], 0)
        for spec in manifest["calls"]:
            result = D.read(Path(spec["directory"]) / "result.json")
            self.assertEqual(len(result["attempts"]), 1)
            self.assertEqual(result["attempts"][0]["failure_kind"], "python_validation")
            self.assertTrue(D.read(Path(spec["directory"]) / "attempt1.json")["raw_kept"])
            self.assertFalse((Path(spec["directory"]) / "report.json").exists())
        for invocation in self.invocations:
            self.assertEqual(invocation["model"], D.MODEL)
            self.assertEqual(invocation["timeout_sec"], D.TIMEOUT_SEC)
            self.assertFalse(invocation["persistent"])
            self.assertEqual(len(invocation["attachments"]), 6)
        for call in self.runtime.validate_verifier_report.call_args_list:
            self.assertNotIn("identity_challenge_pairs", call.kwargs)
        for call in self.physical.validate_verifier_identity_fields.call_args_list:
            self.assertEqual(call.kwargs["identity_challenge_pairs"], [{"cluster_id_a": "a", "cluster_id_b": "b"}])

    def test_schema_and_base_failures_are_also_inside_attempt_accounting(self):
        for validator in ("schema", "base"):
            with self.subTest(validator=validator):
                self.args.output_root = self.base / f"prepared_{validator}"
                self.prepared()
                self.runtime.run_codex_json.reset_mock()
                self.runtime.validate_verifier_report.reset_mock(side_effect=True)
                self.physical.validate_verifier_identity_fields.reset_mock()
                with ExitStack() as patches:
                    if validator == "schema":
                        patches.enter_context(mock.patch("jsonschema.validate", side_effect=ValueError("schema failure")))
                    else:
                        self.runtime.validate_verifier_report.side_effect = ValueError("base failure")
                    self.assertEqual(D.execute(self.args), 1)
                manifest = self.manifest()
                self.assertEqual(self.runtime.run_codex_json.call_count, 8)
                self.physical.validate_verifier_identity_fields.assert_not_called()
                self.assertEqual(manifest["token_usage"], {k: v * 8 for k, v in USAGE.items()})
                self.assertEqual(sum(len(r["attempts"]) for r in manifest["results"]), 8)

    def test_schema_transport_preflight_blocks_all_calls(self):
        self.prepared()
        self.runtime.validate_codex_schema_transport.side_effect = ValueError("unsupported schema keyword")
        with self.assertRaisesRegex(ValueError, "unsupported schema"):
            D.execute(self.args)
        self.runtime.run_codex_json.assert_not_called()
        self.assertFalse((self.args.output_root / "execute_claim.json").exists())

    def test_worker_publication_failure_preserves_peer_accounting(self):
        manifest = self.prepared()
        broken = Path(manifest["calls"][0]["directory"]) / "report.json"
        original = D.write
        def fail_once(path, data):
            if Path(path) == broken:
                raise OSError("injected publication failure")
            return original(path, data)
        with mock.patch.object(D, "write", side_effect=fail_once):
            self.assertEqual(D.execute(self.args), 1)
        manifest = self.manifest()
        self.assertEqual(len(manifest["results"]), 8)
        self.assertEqual(sum(r["status"] == "success" for r in manifest["results"]), 7)
        self.assertEqual(manifest["model_invocations"], 8)
        self.assertEqual(manifest["token_usage"], {k: v * 8 for k, v in USAGE.items()})

    def test_lost_accounting_marks_unknown_instead_of_zero(self):
        self.prepared()
        self.runtime._codex_attempt_accounting.side_effect = OSError("accounting unavailable")
        self.assertEqual(D.execute(self.args), 1)
        manifest = self.manifest()
        self.assertEqual(len(manifest["unaccounted_attempt_starts"]), 8)
        self.assertEqual(manifest["token_usage"], dict.fromkeys(TOKEN_KEYS))
        self.assertFalse(manifest["model_invocation_count_complete"])

    def test_transport_failure_unknown_usage_does_not_discard_known_peer_subtotal(self):
        self.prepared()
        invoke = self.invoke
        def mixed(**kwargs):
            if kwargs["output_path"].parent.name.endswith("frozen_policy_verifier_1"):
                kwargs["events_path"].write_text("")
                raise RuntimeError("transport terminated before usage")
            return invoke(**kwargs)
        self.runtime.run_codex_json.side_effect = mixed
        self.assertEqual(D.execute(self.args), 1)
        manifest = self.manifest()
        self.assertEqual(len(manifest["unknown_usage_attempts"]), 2)
        self.assertEqual(manifest["known_token_usage_subtotal"], {k: v * 6 for k, v in USAGE.items()})
        self.assertEqual(manifest["token_usage"], dict.fromkeys(TOKEN_KEYS))
        self.assertEqual(manifest["model_invocations"], 8)

    def test_missing_events_after_possible_subprocess_exit_is_unknown_start_not_zero(self):
        self.prepared()
        invoke, account = self.invoke, self.account
        def lost_events(**kwargs):
            if kwargs["output_path"].parent.name.endswith("frozen_policy_verifier_1"):
                raise OSError("events write failed after possible subprocess completion")
            return invoke(**kwargs)
        def frozen_accounting(**kwargs):
            if kwargs["invocation"] is None:
                return {"subprocess_started": False, "token_usage": None,
                        "failure_kind": "orchestration_error", "runtime_seconds": None,
                        "thread_id": None, "returncode": None}
            return account(**kwargs)
        self.runtime.run_codex_json.side_effect = lost_events
        self.runtime._codex_attempt_accounting.side_effect = frozen_accounting
        self.assertEqual(D.execute(self.args), 1)
        manifest = self.manifest()
        self.assertEqual(self.runtime.run_codex_json.call_count, 8)
        self.assertEqual(len(manifest["unknown_subprocess_starts"]), 2)
        self.assertEqual(manifest["model_invocations"], 6)
        self.assertFalse(manifest["model_invocation_count_complete"])
        self.assertEqual(manifest["known_token_usage_subtotal"], {k: v * 6 for k, v in USAGE.items()})
        self.assertEqual(manifest["token_usage"], dict.fromkeys(TOKEN_KEYS))
        for result in manifest["results"]:
            if result["status"] == "failed":
                self.assertTrue(result["attempts"][0]["subprocess_start_unknown"])

    def test_concurrent_atomic_claim_never_duplicates_eight_calls(self):
        self.prepared()
        barrier = threading.Barrier(2, timeout=10)
        def ready(_batch):
            barrier.wait()
            return self.runtime, self.physical
        with mock.patch.object(D, "load_runtime", side_effect=ready):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(D.execute, self.args) for _ in range(2)]
                outcomes = []
                for future in futures:
                    try:
                        outcomes.append(future.result(timeout=20))
                    except FileExistsError:
                        outcomes.append("claimed")
        self.assertCountEqual(outcomes, [0, "claimed"])
        self.assertEqual(len(self.invocations), 8)

    def test_resolved_binary_mutation_blocks_launch(self):
        self.prepared()
        self.binary.write_text("changed binary")
        with self.assertRaisesRegex(RuntimeError, "changed"):
            D.execute(self.args)
        self.runtime.run_codex_json.assert_not_called()
        self.assertFalse((self.args.output_root / "execute_claim.json").exists())

    def test_config_mutation_blocks_launch(self):
        manifest = self.prepared()
        path = Path(manifest["calls"][0]["model_config"])
        config = D.read(path)
        config["model"] = "different-model"
        D.write(path, config)
        with self.assertRaisesRegex(RuntimeError, "changed"):
            D.execute(self.args)
        self.runtime.run_codex_json.assert_not_called()

    def test_route_and_retry_budget_mutation_blocks_launch(self):
        manifest = self.prepared()
        manifest["maximum_identical_input_retries"] = 1
        D.write(self.args.output_root / "manifest.json", manifest)
        with self.assertRaisesRegex(RuntimeError, "execution fields"):
            D.execute(self.args)
        self.runtime.run_codex_json.assert_not_called()


if __name__ == "__main__":
    unittest.main()
