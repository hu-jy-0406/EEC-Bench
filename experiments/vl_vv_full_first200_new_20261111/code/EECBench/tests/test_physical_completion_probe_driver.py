"""No-model probes for the bounded completion driver and failure accounting."""

import concurrent.futures
from contextlib import ExitStack, redirect_stdout
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock


DIRECTORY = (Path(__file__).resolve().parents[1]
             / "experiments/study_inconsistent_2/entity_discovery_iterations")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HELPER = load("completion_probe_configuration_fixture", DIRECTORY / "run_frozen_batch.py")
with mock.patch.dict(sys.modules, {"run_frozen_batch": HELPER}):
    D = load("physical_completion_probe_driver_tested", DIRECTORY / "run_physical_completion_probe.py")
TOKEN_KEYS = ("input_tokens", "cached_input_tokens", "output_tokens", "total_tokens")
USAGE = dict(zip(TOKEN_KEYS, (13, 3, 7, 20)))


class PhysicalCompletionProbeDriverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.workspace = self.base / "workspace"
        scripts = self.workspace / "EECBench/scripts"
        scripts.mkdir(parents=True)
        (scripts / "synthetic_runtime.py").write_text("# frozen no-model fixture\n")
        schemas = self.workspace / "EECBench/schemas"
        schemas.mkdir()
        self.inventory_schema = {
            "type": "object", "properties": {"shot_id": {"type": "string"}, "clusters": {"type": "array"}},
            "required": ["shot_id", "clusters"], "additionalProperties": False}
        self.verifier_schema = {
            "type": "object", "properties": {"shot_id": {"type": "string"}, "verifier_id": {"type": "string"},
                                                "reviews": {"type": "array"}},
            "required": ["shot_id", "verifier_id", "reviews"], "additionalProperties": False}
        D.write(schemas / "codex_entity_adjudication_v0.6.schema.json", self.inventory_schema)
        D.write(schemas / "codex_entity_verification_v0.6.schema.json", self.verifier_schema)
        policy = self.workspace / ".agents/skills/ensemble-shot-entity-detection"
        (policy / "references").mkdir(parents=True)
        (policy / "SKILL.md").write_text("full_skill_not_model_input")
        (policy / "references/verifier-protocol.md").write_text("frozen verifier policy")
        self.batch = self.base / "batch"
        original = self.batch / "frozen_workspace"
        original.mkdir(parents=True)
        marker = original / "old_source.txt"
        marker.write_text("original immutable source")
        D.write(self.batch / "robustness_manifest.json", {
            "identity_review_policy": "physical_v0.6", "source_hashes": {"old_source.txt": D.digest(marker)}})
        self.binary = self.base / "fake-cli"
        self.binary.write_text("#!/bin/sh\nexit 95\n")
        self.binary.chmod(0o755)
        self.helper_source = self.base / "run_frozen_batch.py"
        shutil.copyfile(DIRECTORY / "run_frozen_batch.py", self.helper_source)
        self.runtime = SimpleNamespace(
            VERIFIER_IDS=("verifier_1", "verifier_2"), TOKEN_KEYS=TOKEN_KEYS,
            validate_codex_schema_transport=mock.Mock(side_effect=D.read),
            validate_decisions=mock.Mock(), validate_verifier_report=mock.Mock(),
            validate_deferred_partition_lineage=mock.Mock(),
            enforce_intra_cluster_split_consensus=mock.Mock(return_value={"checked": True}),
            run_codex_json=mock.Mock(side_effect=self.invoke),
            _codex_attempt_accounting=mock.Mock(side_effect=self.account),
        )
        self.identity = SimpleNamespace(
            PHYSICAL_IDENTITY_RULE="isolated physical rule", ADJUDICATION_FIELDS_INSTRUCTION="typed contract",
            validate_adjudication_identity_fields=mock.Mock(), validate_verifier_identity_fields=mock.Mock(),
            apply_physical_identity_gate=mock.Mock(side_effect=lambda candidate, **kw: (copy.deepcopy(candidate), {"records": []})),
        )
        self.obligations = SimpleNamespace(build_physical_review_obligations=mock.Mock(return_value={"unfinished": True}))
        self.completion = SimpleNamespace(build_completion_prompt=mock.Mock(side_effect=lambda **kw: json.dumps(kw)),
                                          validate_completion_scope=mock.Mock(return_value={"checked": True}))
        self.modules = [self.runtime, self.identity, self.obligations, self.completion]
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.patches.enter_context(mock.patch.object(D, "WORKSPACE", self.workspace))
        self.patches.enter_context(mock.patch.object(D, "load_runtime", return_value=self.modules))
        self.patches.enter_context(mock.patch.dict(HELPER.__dict__, {"__file__": str(self.helper_source)}))
        self.patches.enter_context(mock.patch.dict(os.environ))
        self.patches.enter_context(redirect_stdout(io.StringIO()))
        self.invocations = []
        for seed in D.SEEDS:
            root = self.batch / f"seed_{seed}" / D.SHOT
            for sub in ("input_bundle", "adjudication", "codex_attempts"):
                (root / sub).mkdir(parents=True)
            frames = []
            for frame_id in range(6):
                frame = root / f"input_bundle/frame_{frame_id}.jpg"
                frame.write_bytes(f"unchanged {seed}/{frame_id}".encode())
                frames.append({"frame_id": frame_id, "path": str(frame)})
            D.write(root / "input_bundle/shot_manifest.json", {
                "reference_frames": frames, "prompt_bound_registry": "registry_must_not_be_loaded"})
            D.write(root / "run_manifest.json", {
                "status": "success", "adjudicator_revision_attempts": [{"attempt": 1, "status": "success"}],
                "input_hashes": {f["path"]: D.digest(Path(f["path"])) for f in frames}})
            inventory = {"shot_id": D.SHOT, "clusters": [{"cluster_id": "a", "anonymous_proposal_ids": ["p1"]}]}
            for path in (root / "adjudication/adjudicator_initial.json", root / "codex_attempts/adjudicator_revision.json"):
                D.write(path, inventory)
            D.write(root / "adjudication/anonymized_candidates.json", {
                "proposals": [{"anonymous_proposal_id": "p1", "proposed_name": "synthetic candidate"}]})
            D.write(root / "adjudication/verification_targets.json", {
                "cluster_ids": ["a"], "identity_challenge_pairs": [], "trigger_reasons": {"a": ["review"]}})
            D.write(root / "adjudication/intra_cluster_split_consensus.json", {"exact_consensus_partitions": []})
            for verifier in self.runtime.VERIFIER_IDS:
                D.write(root / "adjudication" / f"{verifier}.json", {
                    "shot_id": D.SHOT, "verifier_id": verifier, "reviews": [{"cluster_id": "a"}]})
            (root / "adjudication/adjudicator_final.json").write_text("invalid json: forbidden final read")
            (root / "input_bundle/prompt_bound_registry.json").write_text("invalid json: forbidden registry read")
        self.args = SimpleNamespace(source_batch=self.batch, output_root=self.base / "probe", codex_bin=str(self.binary))

    def invoke(self, **kwargs):
        self.invocations.append(kwargs)
        context = D.read(kwargs["output_path"].parent / "context.json")
        payload = copy.deepcopy(context["candidate"])
        kwargs["output_path"].write_text(json.dumps(payload))
        kwargs["events_path"].write_text(json.dumps({"type": "turn.completed", "usage": USAGE}) + "\n")
        kwargs["stderr_path"].write_text("")
        return SimpleNamespace(payload=payload, token_usage=dict(USAGE))

    @staticmethod
    def account(*, invocation, error, events_path):
        return {"subprocess_started": True, "token_usage": invocation.token_usage if invocation else None,
                "thread_id": events_path.parent.name, "returncode": 0 if invocation else 1,
                "runtime_seconds": 0.01, "failure_kind": "python_validation" if invocation and error else "transport" if error else None}

    def prepared(self):
        D.prepare(self.args)
        return D.read(self.args.output_root / "manifest.json")

    def manifest(self):
        return D.read(self.args.output_root / "manifest.json")

    def enable_typed_mode(self):
        """Use the real pure materializer, fake prompt builder and no-model calls."""
        scripts = Path(__file__).resolve().parents[1] / "scripts"
        with mock.patch.object(sys, "path", [str(scripts), *sys.path]):
            patch_core = importlib.import_module("physical_completion_patch")
        fixture = load("typed_driver_inventory_fixture", Path(__file__).with_name("test_physical_identity_review.py"))
        self.args.output_mode = "typed_patch"
        for name in ("physical_completion_patch.py", "physical_completion_patch_prompt.py", "physical_review_completion.py"):
            shutil.copyfile(scripts / name, self.workspace / "EECBench/scripts" / name)
        schemas = scripts.parent / "schemas"
        for name in ("codex_entity_adjudication_v0.6.schema.json", "codex_entity_verification_v0.6.schema.json",
                     "codex_physical_completion_patch_v0.1.schema.json"):
            shutil.copyfile(schemas / name, self.workspace / "EECBench/schemas" / name)
        candidate = fixture.ledger(fixture.cluster("a", ["p0001", "p0002"]),
                                   fixture.cluster("untouched", ["p0003", "p0004"]))
        candidate["shot_id"] = D.SHOT
        for cluster in candidate["clusters"]:
            cluster["adjudicator_evidence"][0]["frame_id"] = 0
            cluster["frame_presence"] = [{"frame_id": i, "status": "visible", "description": "Synthetic visible unit"}
                                         for i in range(6)]
            cluster["final_entity"]["evidence_frame_ids"] = [0]
        obligations = {"policy_version": patch_core.completion.OBLIGATION_POLICY, "shot_id": D.SHOT,
            "cluster_obligations": [{"cluster_id": "a", "anonymous_proposal_ids": ["p0001", "p0002"],
                "candidate_decision": "accept", "gate_result": "abstain", "axis_obligations": [{
                    "axis": "physical_entity", "anonymous_proposal_ids": ["p0001", "p0002"],
                    "initial_target_cluster_ids": ["a"], "revision_cannot_override": False,
                    "requires_exact_scope_revision_resolution": True, "gate_failure_reasons": ["synthetic"]}]}],
            "pair_obligations": []}
        self.obligations.build_physical_review_obligations.return_value = obligations
        for seed in D.SEEDS:
            root = self.batch / f"seed_{seed}" / D.SHOT
            D.write(root / "adjudication/adjudicator_initial.json", candidate)
            D.write(root / "codex_attempts/adjudicator_revision.json", candidate)
            D.write(root / "adjudication/anonymized_candidates.json", {"proposals": [
                {"anonymous_proposal_id": pid, "proposed_name": "synthetic bounded unit"}
                for cluster in candidate["clusters"] for pid in cluster["anonymous_proposal_ids"]]})
            D.write(root / "adjudication/verification_targets.json", {
                "cluster_ids": ["a", "untouched"], "identity_challenge_pairs": [],
                "trigger_reasons": {"a": ["review"], "untouched": ["review"]}})
            for report in fixture.two_reports(*candidate["clusters"]):
                report["shot_id"] = D.SHOT
                D.write(root / "adjudication" / (report["verifier_id"] + ".json"), report)
        self.patch_module = SimpleNamespace(PATCH_SCHEMA=patch_core.PATCH_SCHEMA,
            build_completion_patch_slots=patch_core.build_completion_patch_slots,
            apply_completion_patch=mock.Mock(wraps=patch_core.apply_completion_patch))
        self.patch_prompt = SimpleNamespace(build_patch_completion_prompt=mock.Mock(side_effect=lambda **kw: (
            "Typed patch only: " + json.dumps(kw),
            patch_core.build_completion_patch_slots(kw["candidate_decisions"], kw["obligations"]))))
        self.patches.enter_context(mock.patch.object(D, "load_patch_runtime", return_value=(self.patch_module, self.patch_prompt)))
        self.patch_transform = lambda patch, directory: patch

        def invoke_patch(**kw):
            invocation = self.invoke(**kw)
            directory = kw["output_path"].parent
            slots = D.read(directory / "patch_slots.json")
            payload = {"schema_version": patch_core.PATCH_VERSION, "shot_id": D.SHOT,
                "slot_table_sha256": slots["slot_table_sha256"], "cluster_updates": [], "new_evidence": [],
                "comparison_updates": [], "resolution_updates": []}
            invocation.payload = self.patch_transform(payload, directory)
            kw["output_path"].write_text(json.dumps(invocation.payload))
            return invocation
        self.runtime.run_codex_json.side_effect = invoke_patch

    def test_prepare_two_calls_pins_config_and_uses_only_declared_completion_inputs(self):
        manifest = self.prepared()
        self.assertEqual([c["seed"] for c in manifest["calls"]], [101, 202])
        self.assertEqual(manifest["maximum_model_calls"], 2)
        self.assertEqual(manifest["maximum_retries"], 0)
        self.assertEqual(manifest["model_config"]["model"], "gpt-5.6-sol")
        self.assertEqual(manifest["model_config"]["reasoning_effort"], "high")
        self.assertEqual(manifest["model_config"]["disabled_features"], ["shell_tool"])
        self.assertEqual(manifest["model_config"]["codex_binary"], str(self.binary))
        self.assertEqual(manifest["output_mode"], "full_ledger")
        self.assertEqual(manifest["model_output_schema"], manifest["materialized_schema"])
        self.assertEqual(D.read(self.args.output_root / "execution_plan.json")["model_config"],
                         manifest["model_config"])
        self.assertEqual(D.read(self.args.output_root / "execution_config/model_config.json"),
                         manifest["model_config"])
        self.assertNotIn(str(self.batch / "robustness_manifest.json"), manifest["hashes"])
        for call in self.completion.build_completion_prompt.call_args_list:
            self.assertEqual(set(call.kwargs), {
                "candidate_decisions", "initial_scope_map", "verifier_reports", "obligations", "anonymous_view",
                "reference_frames", "allowed_input_paths", "physical_identity_rule"})
            self.assertEqual(call.kwargs["initial_scope_map"], {"a": ["p1"]})
            serialized = json.dumps(call.kwargs)
            self.assertNotIn("full_skill_not_model_input", serialized)
            self.assertNotIn("registry_must_not_be_loaded", serialized)
            self.assertNotIn("adjudicator_final", serialized)
        self.runtime.run_codex_json.assert_not_called()

    def test_default_helper_wrapper_bytes_and_configuration_stay_compatible(self):
        root = self.base / "legacy configuration"
        root.mkdir()
        config, hashes = HELPER.freeze_codex_config(root, str(self.binary), "other-model", "high")
        expected_wrapper = ('#!/bin/sh\nexec ' + shlex.quote(str(self.binary.resolve()))
                            + ' -c ' + shlex.quote('model_reasoning_effort="high"') + ' "$@"\n')
        self.assertEqual(Path(config["codex_wrapper"]).read_bytes(), expected_wrapper.encode())
        self.assertEqual(set(config), {
            "model", "reasoning_effort", "codex_binary", "codex_binary_sha256", "codex_wrapper"})
        self.assertEqual(D.read(root / "execution_config/model_config.json"), config)
        D.verify(hashes)

    def test_real_runtime_and_fake_cli_preserve_six_images_schema_and_pinned_configuration(self):
        # Execute only this local fake binary, through the real argv builder.
        # Metacharacters in paths must survive as literal arguments.
        self.binary = self.base / "fake CLI's $(not_a_command)"
        self.args.codex_bin = str(self.binary)
        self.args.output_root = self.base / "probe's $literal space"
        payload = D.read(self.batch / f"seed_101/{D.SHOT}/adjudication/adjudicator_initial.json")
        self.binary.write_text(
            '#!' + sys.executable + '\nimport json, sys\nfrom pathlib import Path\n'
            'args = sys.argv[1:]\n'
            'output = Path(args[args.index("--output-last-message") + 1])\n'
            'output.with_suffix(".argv.json").write_text(json.dumps(args))\n'
            'output.with_suffix(".stdin.txt").write_text(sys.stdin.read())\n'
            'output.write_text(' + repr(json.dumps(payload)) + ')\n'
            'print(' + repr(json.dumps({"type": "turn.completed", "usage": USAGE})) + ')\n')
        self.binary.chmod(0o755)
        manifest = self.prepared()
        plan = D.read(self.args.output_root / "execution_plan.json")
        scripts = Path(__file__).resolve().parents[1] / "scripts"
        with mock.patch.object(sys, "path", [str(scripts), *sys.path]):
            real_runtime = importlib.import_module("ensemble_shot_entity_detection")
        self.assertEqual(Path(real_runtime.__file__).resolve().parent, scripts.resolve())
        with mock.patch.object(self.runtime, "run_codex_json", side_effect=real_runtime.run_codex_json):
            result = D.run_one(self.runtime, self.identity, self.completion, plan["calls"][0], plan)
        self.assertEqual(result["status"], "success")
        spec = plan["calls"][0]
        directory = Path(spec["directory"])
        expected = ["--disable", "shell_tool", "-c", 'model_reasoning_effort="high"',
                    "--ask-for-approval", "never", "exec", "--ephemeral", "--color", "never", "--json",
                    "--sandbox", "read-only", "--output-schema", plan["schema"],
                    "--output-last-message", str(directory / "attempt1.json"),
                    "--cd", str(directory / "workdir"), "--model", "gpt-5.6-sol"]
        for path in spec["attachments"]:
            expected.extend(["--image", path])
        expected.append("-")
        self.assertEqual(D.read(directory / "attempt1.argv.json"), expected)
        self.assertEqual((directory / "attempt1.stdin.txt").read_text(), Path(spec["prompt"]).read_text())
        D.verify(manifest["hashes"])

    def test_execute_passes_frozen_plan_configuration_to_workers(self):
        self.prepared()
        with mock.patch.object(D, "run_one", wraps=D.run_one) as worker:
            self.assertEqual(D.execute(self.args), 0)
        plan = D.read(self.args.output_root / "execution_plan.json")
        self.assertEqual(worker.call_count, 2)
        for call in worker.call_args_list:
            self.assertEqual(call.args[-1], plan)
            self.assertNotIn("results", call.args[-1])

    def test_schema_invalid_selected_verifier_is_rejected_before_prompt_or_call(self):
        path = self.batch / f"seed_101/{D.SHOT}/adjudication/verifier_1.json"
        report = D.read(path)
        report["unsupported_extra_field"] = True
        D.write(path, report)
        with self.assertRaises(Exception):
            D.prepare(self.args)
        self.completion.build_completion_prompt.assert_not_called()
        self.runtime.run_codex_json.assert_not_called()

    def test_prepare_inventory_schema_base_and_identity_validation_all_apply(self):
        self.prepared()
        self.assertEqual(self.runtime.validate_decisions.call_count, 4)
        self.assertEqual(self.identity.validate_adjudication_identity_fields.call_count, 4)
        self.assertEqual(self.runtime.validate_verifier_report.call_count, 4)
        self.assertEqual(self.identity.validate_verifier_identity_fields.call_count, 4)

    def test_run_one_uses_fresh_ephemeral_context_and_retains_one_marker(self):
        manifest = self.prepared()
        result = D.run_one(self.runtime, self.identity, self.completion, manifest["calls"][0], manifest)
        self.assertEqual(result["status"], "success")
        call = self.invocations[0]
        self.assertFalse(call["persistent"])
        self.assertNotIn("resume_thread_id", call)
        self.assertEqual(call["model"], "gpt-5.6-sol")
        self.assertEqual(call["timeout_sec"], 1800)
        self.assertEqual(len(call["attachments"]), 6)
        self.assertTrue((call["output_path"].parent / "attempt1.started.json").exists())
        self.assertEqual(len(self.invocations), 1)

    def test_guard_failure_keeps_raw_usage_without_publishing_successful_gate(self):
        manifest = self.prepared()
        self.completion.validate_completion_scope.side_effect = ValueError("scope rewrite forbidden")
        result = D.run_one(self.runtime, self.identity, self.completion, manifest["calls"][0], manifest)
        directory = Path(manifest["calls"][0]["directory"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["token_usage"], USAGE)
        self.assertEqual(result["failure_kind"], "python_validation")
        self.assertTrue((directory / "attempt1.json").exists())
        self.assertTrue((directory / "attempt1.events.jsonl").exists())
        self.assertFalse((directory / "completion_gated_ledger.json").exists())
        self.assertEqual(len(self.invocations), 1)

    def test_prohibited_tool_event_still_fails_with_raw_usage_and_no_retry(self):
        manifest = self.prepared()
        invoke = self.invoke
        def with_tool_event(**kwargs):
            invocation = invoke(**kwargs)
            with kwargs["events_path"].open("a") as handle:
                handle.write(json.dumps({"type": "item.completed", "item": {
                    "type": "command_execution", "command": "rg --files"}}) + "\n")
            return invocation
        self.runtime.run_codex_json.side_effect = with_tool_event
        result = D.run_one(self.runtime, self.identity, self.completion, manifest["calls"][0], manifest)
        directory = Path(manifest["calls"][0]["directory"])
        self.assertEqual(result["status"], "failed")
        self.assertIn("prohibited tools", result["error"])
        self.assertEqual(result["token_usage"], USAGE)
        self.assertTrue((directory / "attempt1.json").exists())
        self.assertTrue((directory / "attempt1.started.json").exists())
        self.assertFalse((directory / "completion_gated_ledger.json").exists())
        self.assertEqual(len(self.invocations), 1)

    def test_inventory_schema_base_identity_and_split_failures_are_accounted(self):
        manifest = self.prepared()
        for label in ("schema", "base", "identity", "lineage", "split"):
            with self.subTest(label=label), ExitStack() as patches:
                if label == "schema":
                    patches.enter_context(mock.patch.object(D, "validate_inventory", side_effect=ValueError("schema")))
                else:
                    obj, field = {
                        "base": (self.runtime, "validate_decisions"),
                        "identity": (self.identity, "validate_adjudication_identity_fields"),
                        "lineage": (self.runtime, "validate_deferred_partition_lineage"),
                        "split": (self.runtime, "enforce_intra_cluster_split_consensus"),
                    }[label]
                    patches.enter_context(mock.patch.object(obj, field, side_effect=ValueError(label)))
                # Distinct synthetic directories; this never reuses a real call slot.
                spec = copy.deepcopy(manifest["calls"][0])
                directory = self.args.output_root / f"synthetic_{label}"
                directory.mkdir()
                shutil.copyfile(spec["context"], directory / "context.json")
                spec["directory"] = str(directory)
                result = D.run_one(self.runtime, self.identity, self.completion, spec, manifest)
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["token_usage"], USAGE)
                self.assertTrue((directory / "attempt1.json").exists())

    def test_transport_failure_preserves_partial_raw_and_unknown_usage(self):
        self.prepared()
        invoke = self.invoke
        def partial(**kw):
            if kw["output_path"].parent.name == "seed_101":
                kw["output_path"].write_text('{"partial":true}')
                kw["events_path"].write_text('{"type":"thread.started"}\n')
                kw["stderr_path"].write_text("transport interrupted")
                raise RuntimeError("transport failed without usage")
            return invoke(**kw)
        self.runtime.run_codex_json.side_effect = partial
        self.assertEqual(D.execute(self.args), 1)
        manifest = self.manifest()
        self.assertEqual(manifest["model_invocations"], 2)
        self.assertEqual(manifest["unknown_usage_attempts"], [101])
        self.assertEqual(manifest["status"], "incomplete")
        self.assertEqual(manifest["known_token_usage_subtotal"], USAGE)
        self.assertEqual(manifest["token_usage"], dict.fromkeys(TOKEN_KEYS))
        self.assertTrue((self.args.output_root / "seed_101/attempt1.json").exists())
        self.assertEqual(self.runtime.run_codex_json.call_count, 2)

    def test_worker_accounting_failure_cannot_turn_unknown_usage_into_zero(self):
        self.prepared()
        original = self.account
        def fail_one(**kw):
            if kw["events_path"].parent.name == "seed_101":
                raise OSError("accounting unavailable after paid call")
            return original(**kw)
        self.runtime._codex_attempt_accounting.side_effect = fail_one
        self.assertEqual(D.execute(self.args), 1)
        manifest = self.manifest()
        self.assertEqual(manifest["unaccounted_attempt_starts"], [101])
        self.assertEqual(manifest["status"], "incomplete")
        self.assertFalse(manifest["model_invocation_count_complete"])
        self.assertEqual(manifest["known_token_usage_subtotal"], USAGE)
        self.assertEqual(manifest["token_usage"], dict.fromkeys(TOKEN_KEYS))
        self.assertEqual(len(manifest["results"]), 2)

    def test_plain_io_failure_without_events_cannot_prove_subprocess_never_started(self):
        self.prepared()
        invoke, account = self.invoke, self.account
        def lost_events(**kw):
            if kw["output_path"].parent.name == "seed_101":
                raise OSError("events persistence failed after possible paid completion")
            return invoke(**kw)
        def frozen_accounting(**kw):
            if kw["invocation"] is None:
                return {"subprocess_started": False, "token_usage": None,
                        "failure_kind": "orchestration_error", "runtime_seconds": None,
                        "thread_id": None, "returncode": None}
            return account(**kw)
        self.runtime.run_codex_json.side_effect = lost_events
        self.runtime._codex_attempt_accounting.side_effect = frozen_accounting
        self.assertEqual(D.execute(self.args), 1)
        manifest = self.manifest()
        self.assertTrue(manifest["unknown_subprocess_starts"])
        self.assertEqual(manifest["status"], "incomplete")
        self.assertFalse(manifest["model_invocation_count_complete"])
        self.assertEqual(manifest["known_token_usage_subtotal"], USAGE)
        self.assertEqual(manifest["token_usage"], dict.fromkeys(TOKEN_KEYS))
        bad = next(r for r in manifest["results"] if r["seed"] == 101)
        self.assertTrue(bad["subprocess_start_unknown"])

    def test_successful_outputs_with_unknown_usage_leave_batch_incomplete(self):
        self.prepared()
        invoke = self.invoke
        def missing_usage(**kwargs):
            invocation = invoke(**kwargs)
            if kwargs["output_path"].parent.name == "seed_101":
                invocation.token_usage = None
                kwargs["events_path"].write_text(json.dumps({"type": "turn.completed"}) + "\n")
            return invocation
        self.runtime.run_codex_json.side_effect = missing_usage
        self.assertEqual(D.execute(self.args), 1)
        manifest = self.manifest()
        self.assertEqual([row["status"] for row in manifest["results"]], ["success", "success"])
        self.assertEqual(manifest["status"], "incomplete")
        self.assertEqual(manifest["unknown_usage_attempts"], [101])
        self.assertEqual(manifest["known_token_usage_subtotal"], USAGE)
        self.assertEqual(manifest["token_usage"], dict.fromkeys(TOKEN_KEYS))
        self.assertEqual(manifest["model_invocations"], 2)
        self.assertTrue(manifest["model_invocation_count_complete"])
        self.assertEqual(manifest["retry_count"], 0)
        for seed in D.SEEDS:
            self.assertTrue((self.args.output_root / f"seed_{seed}/completion_gated_ledger.json").exists())

    def test_atomic_claim_and_zero_retry_limit_actual_invocations_to_two(self):
        self.prepared()
        ready = threading.Barrier(2, timeout=10)
        def rendezvous(_root):
            ready.wait()
            return self.modules
        self.completion.validate_completion_scope.side_effect = ValueError("guard fail")
        with mock.patch.object(D, "load_runtime", side_effect=rendezvous):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(D.execute, self.args) for _ in range(2)]
                outcomes = []
                for future in futures:
                    try:
                        outcomes.append(future.result(timeout=20))
                    except FileExistsError:
                        outcomes.append("claimed")
        self.assertCountEqual(outcomes, [1, "claimed"])
        self.assertEqual(self.runtime.run_codex_json.call_count, 2)
        self.assertEqual(self.manifest()["retry_count"], 0)

    def test_plan_drift_is_rejected_before_claim_or_call(self):
        manifest = self.prepared()
        changes = [{"maximum_retries": 1},
                   {"model_config": {**manifest["model_config"], "disabled_features": []}}]
        for change in changes:
            with self.subTest(change=change):
                D.write(self.args.output_root / "manifest.json", {**manifest, **change})
                with self.assertRaisesRegex(RuntimeError, "configuration"):
                    D.execute(self.args)
        self.runtime.run_codex_json.assert_not_called()
        self.assertFalse((self.args.output_root / "execute_claim.json").exists())

    def test_current_configuration_helper_drift_is_rejected(self):
        self.prepared()
        self.helper_source.write_text(self.helper_source.read_text() + "\n# changed live helper\n")
        with self.assertRaises(RuntimeError):
            D.execute(self.args)
        self.runtime.run_codex_json.assert_not_called()

    def test_typed_prepare_separates_output_and_inventory_schemas_and_freezes_slots(self):
        self.enable_typed_mode()
        manifest = self.prepared()
        self.assertEqual(manifest["output_mode"], "typed_patch")
        self.assertEqual(manifest["protocol_version"], D.PATCH_PROTOCOL)
        self.assertEqual(manifest["schema"], manifest["model_output_schema"])
        self.assertNotEqual(manifest["model_output_schema"], manifest["materialized_schema"])
        self.assertEqual(D.read(manifest["model_output_schema"]), self.patch_module.PATCH_SCHEMA)
        self.completion.build_completion_prompt.assert_not_called()
        for call in self.patch_prompt.build_patch_completion_prompt.call_args_list:
            self.assertEqual(call.kwargs["physical_identity_rule"], self.identity.PHYSICAL_IDENTITY_RULE)
            self.assertNotIn(self.identity.ADJUDICATION_FIELDS_INSTRUCTION, call.kwargs["physical_identity_rule"])
        for spec in manifest["calls"]:
            self.assertIn(spec["patch_slots"], manifest["hashes"])
            self.assertEqual(len(D.read(spec["context"])["anonymous_ids"]), 4)
        for name in ("physical_completion_patch.py", "physical_completion_patch_prompt.py", "physical_review_completion.py"):
            self.assertIn(str(self.args.output_root / "frozen_workspace/EECBench/scripts" / name), manifest["hashes"])
        self.assertEqual(self.runtime.validate_decisions.call_count, 4)
        self.runtime.run_codex_json.assert_not_called()

    def test_typed_empty_patch_materializes_complete_inventory_through_existing_validators(self):
        self.enable_typed_mode()
        prepared = self.prepared()
        self.assertEqual(D.execute(self.args), 0)
        manifest = self.manifest()
        self.assertEqual(manifest["model_invocations"], 2)
        self.assertEqual(manifest["retry_count"], 0)
        self.assertEqual(manifest["token_usage"], {key: value * 2 for key, value in USAGE.items()})
        for spec in prepared["calls"]:
            directory = Path(spec["directory"])
            candidate = D.read(spec["context"])["candidate"]
            raw = D.read(directory / "attempt1.json")
            self.assertNotIn("clusters", raw)
            self.assertEqual(raw, D.read(directory / "completion_raw_patch.json"))
            self.assertEqual(D.read(directory / "completion_materialized_ledger.json"), candidate)
            self.assertEqual(D.read(directory / "completion_candidate.json"), candidate)
            self.assertEqual(D.read(directory / "completion_gated_ledger.json"), candidate)
            self.assertTrue((directory / "completion_patch_materialization_audit.json").exists())
            self.assertEqual(sum(len(c["anonymous_proposal_ids"]) for c in candidate["clusters"]), 4)
        self.assertEqual(self.runtime.validate_decisions.call_count, 6)
        self.assertEqual(self.identity.validate_adjudication_identity_fields.call_count, 6)
        self.assertEqual(self.completion.validate_completion_scope.call_count, 2)
        for invocation in self.invocations:
            self.assertEqual(str(invocation["schema_path"]), manifest["model_output_schema"])
            self.assertFalse(invocation["persistent"])
            self.assertEqual(len(invocation["attachments"]), 6)
        self.assertTrue(all("clusters" in call.args[0] for call in self.runtime.validate_decisions.call_args_list))

    def test_typed_invalid_model_transport_is_failed_and_peer_usage_is_preserved(self):
        self.enable_typed_mode()
        self.prepared()
        self.patch_transform = lambda patch, directory: ({"clusters": []} if directory.name == "seed_101" else patch)
        self.assertEqual(D.execute(self.args), 1)
        manifest = self.manifest()
        self.assertEqual([row["status"] for row in manifest["results"]], ["failed", "success"])
        self.assertEqual(manifest["token_usage"], {key: value * 2 for key, value in USAGE.items()})
        self.assertEqual(manifest["model_invocations"], 2)
        directory = self.args.output_root / "seed_101"
        self.assertEqual(D.read(directory / "attempt1.json"), {"clusters": []})
        self.assertTrue((directory / "completion_raw_patch.json").exists())
        self.assertFalse((directory / "completion_materialized_ledger.json").exists())
        self.assertFalse((directory / "completion_gated_ledger.json").exists())

    def test_typed_assembler_failure_retains_raw_and_known_usage_without_success(self):
        self.enable_typed_mode()
        manifest = self.prepared()
        self.patch_transform = lambda patch, _: {**patch, "resolution_updates": [{
            "slot_id": "not_an_authorized_slot", "evidence_refs": [{"kind": "existing", "index": 0, "new_evidence_id": None}]}]}
        result = D.run_one(self.runtime, self.identity, self.completion, manifest["calls"][0], manifest,
                           patch_module=self.patch_module)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["token_usage"], USAGE)
        directory = Path(manifest["calls"][0]["directory"])
        self.assertTrue((directory / "completion_raw_patch.json").exists())
        self.assertFalse((directory / "completion_materialized_ledger.json").exists())

    def test_typed_materialization_does_not_bypass_full_schema_or_physical_validation(self):
        for failure in ("full_schema", "physical"):
            with self.subTest(failure=failure):
                # Independent synthetic roots; no real calls or experiment roots.
                self.args.output_root = self.base / ("typed_" + failure)
                self.enable_typed_mode()
                manifest = self.prepared()
                if failure == "full_schema":
                    apply = self.patch_module.apply_completion_patch
                    def invalid_materialization(*args):
                        payload, audit = apply(*args)
                        return {**payload, "unexpected_ledger_field": True}, audit
                    module = SimpleNamespace(apply_completion_patch=invalid_materialization)
                else:
                    module = self.patch_module
                    self.identity.validate_adjudication_identity_fields.side_effect = ValueError("physical witness invalid")
                result = D.run_one(self.runtime, self.identity, self.completion, manifest["calls"][0], manifest,
                                   patch_module=module)
                self.identity.validate_adjudication_identity_fields.side_effect = None
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["token_usage"], USAGE)
                directory = Path(manifest["calls"][0]["directory"])
                self.assertTrue((directory / "completion_raw_patch.json").exists())
                self.assertTrue((directory / "completion_materialized_ledger.json").exists())
                self.assertTrue((directory / "completion_patch_materialization_audit.json").exists())
                self.assertFalse((directory / "completion_gated_ledger.json").exists())

    def test_typed_transport_error_keeps_raw_and_unknown_usage_instead_of_zero(self):
        self.enable_typed_mode()
        self.prepared()
        invoke = self.runtime.run_codex_json.side_effect
        def lost_response(**kw):
            invocation = invoke(**kw)
            if kw["output_path"].parent.name == "seed_101":
                raise OSError("transport disconnected after partial response")
            return invocation
        self.runtime.run_codex_json.side_effect = lost_response
        self.assertEqual(D.execute(self.args), 1)
        manifest = self.manifest()
        self.assertEqual(manifest["unknown_usage_attempts"], [101])
        self.assertEqual(manifest["status"], "incomplete")
        self.assertEqual(manifest["known_token_usage_subtotal"], USAGE)
        self.assertEqual(manifest["token_usage"], dict.fromkeys(TOKEN_KEYS))
        self.assertTrue((self.args.output_root / "seed_101/attempt1.json").exists())
        self.assertEqual(self.runtime.run_codex_json.call_count, 2)

    def test_typed_slot_module_prompt_and_schema_drift_fail_before_any_call(self):
        self.enable_typed_mode()
        manifest = self.prepared()
        paths = [Path(manifest["calls"][0]["patch_slots"]), Path(manifest["model_output_schema"]),
                 Path(manifest["materialized_schema"]),
                 *(self.args.output_root / "frozen_workspace/EECBench/scripts" / name
                   for name in ("physical_completion_patch.py", "physical_completion_patch_prompt.py"))]
        for path in paths:
            with self.subTest(path=path):
                original = path.read_bytes()
                path.write_bytes(original + b"\n")
                with self.assertRaisesRegex(RuntimeError, "Changed frozen"):
                    D.execute(self.args)
                path.write_bytes(original)
                self.assertFalse((self.args.output_root / "execute_claim.json").exists())
        self.runtime.run_codex_json.assert_not_called()

    def test_typed_schema_module_disagreement_stops_prepare_before_call(self):
        self.enable_typed_mode()
        path = self.workspace / "EECBench/schemas/codex_physical_completion_patch_v0.1.schema.json"
        schema = D.read(path)
        schema["title"] = "different schema snapshot"
        D.write(path, schema)
        with self.assertRaisesRegex(RuntimeError, "schema disagree"):
            D.prepare(self.args)
        self.runtime.run_codex_json.assert_not_called()

    def test_typed_prompt_slot_numeric_type_drift_is_rejected_during_prepare(self):
        self.enable_typed_mode()
        build = self.patch_prompt.build_patch_completion_prompt.side_effect
        def changed_slots(**kwargs):
            prompt, slots = build(**kwargs)
            slots["new_evidence_budget"]["per_owner"] = float(slots["new_evidence_budget"]["per_owner"])
            return prompt, slots
        self.patch_prompt.build_patch_completion_prompt.side_effect = changed_slots
        with self.assertRaisesRegex(RuntimeError, "slot tables disagree"):
            D.prepare(self.args)
        self.runtime.run_codex_json.assert_not_called()

    def test_patch_loader_rejects_any_module_loaded_outside_probe_freeze(self):
        names = ("physical_completion_patch", "physical_completion_patch_prompt", "physical_review_completion")
        scripts = self.args.output_root / "frozen_workspace/EECBench/scripts"
        for outside in names:
            with self.subTest(outside=outside):
                def imported(name):
                    path = (self.workspace / "EECBench/scripts" if name == outside else scripts) / (name + ".py")
                    return SimpleNamespace(__file__=str(path))
                with mock.patch.object(D.importlib, "import_module", side_effect=imported), mock.patch.object(sys, "path", list(sys.path)):
                    with self.assertRaisesRegex(RuntimeError, "outside its frozen"):
                        D.load_patch_runtime(self.args.output_root)


if __name__ == "__main__":
    unittest.main()
