"""Mock six-call scheduling, isolation and loss-aware accounting; no model calls."""
from contextlib import ExitStack, redirect_stdout
import copy
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock


DIRECTORY = Path(__file__).resolve().parents[1] / "experiments/study_inconsistent_2/entity_discovery_iterations"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HELPER = load("blind_probe_config_fixture", DIRECTORY / "run_frozen_batch.py")
with mock.patch.dict(sys.modules, {"run_frozen_batch": HELPER}):
    D = load("blind_pixel_survey_probe_driver_tested", DIRECTORY / "run_blind_pixel_survey_probe.py")
USAGE = dict(zip(D.TOKEN_KEYS, (20, 3, 5, 25)))


class BlindPixelSurveyProbeDriverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.workspace = self.base / "workspace"
        scripts = self.workspace / "EECBench/scripts"
        scripts.mkdir(parents=True)
        for name in ("ensemble_shot_entity_detection", "physical_identity_review", "blind_pixel_survey", "blind_survey_binding"):
            (scripts / (name + ".py")).write_text("# frozen synthetic helper, never executes a model\n")
        schema_dir = self.workspace / "EECBench/schemas"
        schema_dir.mkdir()
        report_schema = {"type": "object", "properties": {"shot_id": {"type": "string"}, "verifier_id": {"type": "string"},
                                                         "reviews": {"type": "array"}},
                         "required": ["shot_id", "verifier_id", "reviews"], "additionalProperties": False}
        survey_schema = {"type": "object", "properties": {"regions": {"type": "array"}},
                         "required": ["regions"], "additionalProperties": False}
        wrapper_schema = {"type": "object", "properties": {"verifier_report": report_schema, "bindings": {"type": "array"}},
                          "required": ["verifier_report", "bindings"], "additionalProperties": False}
        for name, schema in (("codex_entity_adjudication_v0.6.schema.json", {"type": "object"}),
                             ("codex_entity_verification_v0.6.schema.json", report_schema),
                             ("blind-pixel-survey.v0.1.schema.json", survey_schema),
                             ("codex_blind_survey_binding_v0.1.schema.json", wrapper_schema)):
            D.write(schema_dir / name, schema)
        policy = self.workspace / ".agents/skills/ensemble-shot-entity-detection"
        (policy / "references").mkdir(parents=True)
        (policy / "SKILL.md").write_text("FULL_SKILL_NOT_MODEL_INPUT")
        (policy / "references/verifier-protocol.md").write_text("isolated verifier policy")
        self.batch = self.base / "iteration04"
        old = self.batch / "frozen_workspace/old.py"
        old.parent.mkdir(parents=True)
        old.write_text("# unchanged old source\n")
        D.write(self.batch / "robustness_manifest.json", {"identity_review_policy": "physical_v0.6", "source_hashes": {"old.py": D.digest(old)}})
        self.binary = self.base / "fake-cli"
        self.binary.write_text("#!/bin/sh\nexit 95\n")
        self.binary.chmod(0o755)
        self.args = SimpleNamespace(source_batch=self.batch, output_root=self.base / "prepared", codex_bin=str(self.binary))
        self.runtime = SimpleNamespace(
            TOKEN_KEYS=D.TOKEN_KEYS, validate_codex_schema_transport=mock.Mock(side_effect=D.read),
            validate_decisions=mock.Mock(), validate_verifier_report=mock.Mock(),
            _verification_view=mock.Mock(side_effect=self.view), run_codex_json=mock.Mock(side_effect=self.invoke),
            _codex_attempt_accounting=mock.Mock(side_effect=self.account))
        self.physical = SimpleNamespace(
            validate_adjudication_identity_fields=mock.Mock(), validate_verifier_identity_fields=mock.Mock(),
            build_verifier_prompt=mock.Mock(side_effect=lambda **kw: "STANDARD " + json.dumps(kw, sort_keys=True)))
        self.survey = SimpleNamespace(build_views=mock.Mock(side_effect=self.views),
                                      build_survey_prompt=mock.Mock(side_effect=lambda bundle: "BLIND " + json.dumps(bundle["safe_frame_ids"])),
                                      validate_survey=mock.Mock(side_effect=lambda raw, views: {**copy.deepcopy(raw), "mapped": True}))
        self.binding = SimpleNamespace(BINDING_VERSION="blind_survey_binding_v0.1", BINDING_INSTRUCTIONS="wrapper output only",
                                       build_binding_prompt=mock.Mock(side_effect=self.binding_prompt),
                                       validate_binding=mock.Mock(return_value={"all_target_proposals_bound_once": True}))
        self.modules = [self.runtime, self.physical, self.survey, self.binding]
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.patches.enter_context(mock.patch.object(D, "WORKSPACE", self.workspace))
        self.patches.enter_context(mock.patch.object(D, "load_runtime", side_effect=self.modules_at))
        self.patches.enter_context(mock.patch.dict(os.environ))
        self.stdout = io.StringIO()
        self.patches.enter_context(redirect_stdout(self.stdout))
        self.calls, self.active, self.maximum_active = [], 0, 0
        self.call_lock = threading.Lock()
        self.failures, self.unknown_usage = {}, set()
        for seed, shot in D.CONTEXTS:
            root = self.batch / f"seed_{seed}" / shot
            for sub in ("input_bundle", "adjudication"):
                (root / sub).mkdir(parents=True)
            frames = []
            for frame_id in range(6):
                path = root / f"input_bundle/frame_{frame_id:06d}.jpg"
                path.write_bytes(f"synthetic pixels {seed}/{frame_id}".encode())
                frames.append({"frame_id": frame_id, "path": str(path), "timestamp_sec": frame_id / 10})
            D.write(root / "input_bundle/shot_manifest.json", {"reference_frames": frames, "prompt_bound_registry": "DO_NOT_READ_REGISTRY"})
            initial = {"shot_id": shot, "clusters": [
                {"cluster_id": "a", "anonymous_proposal_ids": ["p1", "p2"], "decision": "OLD_VERDICT_FORBIDDEN"},
                {"cluster_id": "b", "anonymous_proposal_ids": ["p3"], "decision": "OLD_VERDICT_FORBIDDEN"}]}
            data = {"adjudicator_initial": initial,
                    "anonymized_candidates": {"proposals": [{"anonymous_proposal_id": p} for p in ("p1", "p2", "p3")]},
                    "verification_targets": {"cluster_ids": ["a"], "identity_challenge_pairs": [],
                                             "intra_cluster_divergent_footprint_challenges": []}}
            artifacts = {}
            for key, payload in data.items():
                path = root / "adjudication" / (key + ".json")
                D.write(path, payload)
                artifacts[key] = {"path": str(path), "sha256": D.digest(path)}
            D.write(root / "run_manifest.json", {"status": "success", "identity_review_policy": "physical_v0.6",
                                                "input_hashes": {f["path"]: D.digest(Path(f["path"])) for f in frames},
                                                "artifacts": artifacts})
            for forbidden in (root / "adjudication/adjudicator_decisions.json", root / "adjudication/verifier_1.json",
                              root / "input_bundle/prompt_bound_registry.json"):
                forbidden.write_text("invalid JSON: this must never be read")

    def modules_at(self, root):
        names = ("ensemble_shot_entity_detection", "physical_identity_review", "blind_pixel_survey", "blind_survey_binding")
        for module, name in zip(self.modules, names):
            module.__file__ = str(root / "frozen_workspace/EECBench/scripts" / (name + ".py"))
        self.survey.SCHEMA_PATH = root / "frozen_workspace/EECBench/schemas/blind-pixel-survey.v0.1.schema.json"
        self.binding.SCHEMA_PATH = root / "frozen_workspace/EECBench/schemas/codex_blind_survey_binding_v0.1.schema.json"
        return self.modules

    @staticmethod
    def view(initial, anonymous, targets, pairs, splits):
        return {"targets": [{"cluster_id": c["cluster_id"], "anonymous_proposal_ids": c["anonymous_proposal_ids"]}
                            for c in initial["clusters"] if c["cluster_id"] in targets],
                "identity_challenge_pairs": pairs, "intra_cluster_divergent_footprint_challenges": splits}

    @staticmethod
    def views(frames, directory):
        directory.mkdir()
        attachments = [f["path"] for f in frames]
        for index in range(8):
            path = directory / f"corner_{index}.png"
            path.write_bytes(b"synthetic crop")
            attachments.append(str(path))
        return {"attachments": attachments, "safe_frame_ids": [f["frame_id"] for f in frames]}

    @staticmethod
    def binding_prompt(**kw):
        if D.content_hash(kw["locked_survey"]) != kw["survey_sha256"]:
            raise ValueError("wrong survey hash")
        return "WRAPPER child instructions\n" + kw["standard_verifier_prompt"] + "\nLOCKED " + json.dumps(kw["locked_survey"])

    def invoke(self, **kwargs):
        directory = Path(kwargs["output_path"]).parent
        role, chain = directory.name, directory.parent.name
        key = chain + "/" + role
        with self.call_lock:
            self.calls.append((key, kwargs))
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
        try:
            time.sleep(0.005)
            failure = self.failures.get(key)
            if failure == "unknown_start":
                raise OSError("events persistence failed after possibly started subprocess")
            context = D.read(directory.parent / "validation_context.json")
            report = {"shot_id": context["shot_id"], "verifier_id": D.VERIFIER_ID, "reviews": [{"cluster_id": "a"}]}
            payload = {"regions": [{"region_id": chain + "_r"}]} if role == "survey" else report
            if role == "binding":
                payload = {"verifier_report": report, "bindings": [{"anonymous_proposal_id": "p1"}, {"anonymous_proposal_id": "p2"}]}
            if failure == "schema":
                payload = {"wrong_output_root": True}
            usage = None if key in self.unknown_usage else copy.deepcopy(USAGE)
            event = {"type": "turn.completed", "usage": usage}
            if failure == "tool":
                event["item"] = {"type": "command_execution", "command": "forbidden read"}
            Path(kwargs["events_path"]).write_text(json.dumps(event) + "\n")
            D.write(Path(kwargs["output_path"]), payload)
            return SimpleNamespace(payload=payload, token_usage=usage, runtime_seconds=0.01, thread_id=key)
        finally:
            with self.call_lock:
                self.active -= 1

    @staticmethod
    def account(*, invocation, error, events_path):
        return {"subprocess_started": invocation is not None, "token_usage": invocation.token_usage if invocation else None,
                "failure_kind": "python_validation" if invocation and error else "orchestration_error" if error else None,
                "runtime_seconds": invocation.runtime_seconds if invocation else None,
                "returncode": 0 if invocation else None, "thread_id": invocation.thread_id if invocation else None}

    def prepare(self):
        D.prepare(self.args)
        self.plan = D.read(self.args.output_root / "execution_plan.json")
        return self.plan

    def execute(self):
        D.execute(self.args)
        return D.read(self.args.output_root / "manifest.json")

    def test_prepare_fixed_subset_targetsets_no_forbidden_inputs_or_survey_leakage(self):
        plan = self.prepare()
        self.assertEqual((len(plan["calls"]), plan["maximum_retries"], plan["max_workers"], plan["timeout_sec"]), (6, 0, 2, 1800))
        self.assertEqual(plan["model_config"]["disabled_features"], ["shell_tool"])
        self.assertFalse(any(c["targetset_is_all_initial_clusters"] for c in plan["contexts"]))
        for spec in plan["calls"]:
            prompt = Path(spec["prompt"]).read_text()
            self.assertNotIn("OLD_VERDICT_FORBIDDEN", prompt)
            self.assertNotIn("FULL_SKILL_NOT_MODEL_INPUT", prompt)
            self.assertNotIn("DO_NOT_READ_REGISTRY", prompt)
            if spec["role"] == "survey":
                self.assertNotIn("p1", prompt)
                self.assertEqual(len(spec["attachments"]), 14)
        self.assertEqual(self.calls, [])

    def test_six_fresh_calls_global_two_workers_same_standard_control_binding_bytes(self):
        self.prepare()
        result = self.execute()
        self.assertEqual(result["status"], "success", result["results"])
        self.assertEqual((len(self.calls), result["model_invocations"]), (6, 6))
        self.assertLessEqual(self.maximum_active, 2)
        self.assertEqual(result["token_usage"]["total_tokens"], 150)
        for key, kwargs in self.calls:
            self.assertIs(kwargs["persistent"], False)
            self.assertEqual(kwargs["model"], D.MODEL)
            self.assertEqual(kwargs["timeout_sec"], 1800)
            self.assertNotIn("thread_id", kwargs)
            if key.endswith("/binding"):
                standard = (Path(kwargs["output_path"]).parents[1] / "standard_verifier_prompt.txt").read_text()
                self.assertEqual(kwargs["prompt"].count(standard), 1)
                self.assertEqual(len(kwargs["attachments"]), 6)
        self.assertEqual(self.runtime.validate_verifier_report.call_count, 4)
        self.assertEqual(self.physical.validate_verifier_identity_fields.call_count, 4)

    def test_survey_failure_skips_only_its_binding_preserves_peer_controls_and_usage(self):
        self.prepare()
        self.failures["context_01/survey"] = "schema"
        result = self.execute()
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["model_invocations"], 5)
        rows = {r["call_id"]: r for r in result["results"]}
        self.assertEqual(rows["context_01/binding"]["reason"], "dependency_failed")
        self.assertEqual(rows["context_01/control"]["status"], "success")
        self.assertEqual(rows["context_02/binding"]["status"], "success")
        self.assertEqual(result["known_token_usage_subtotal"]["total_tokens"], 125)
        self.assertFalse((self.args.output_root / "context_01/binding/attempt1.started.json").exists())

    def test_control_tool_failure_retains_raw_usage_and_does_not_cancel_chain(self):
        self.prepare()
        self.failures["context_01/control"] = "tool"
        result = self.execute()
        row = next(r for r in result["results"] if r["call_id"] == "context_01/control")
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["token_usage"], USAGE)
        self.assertTrue((self.args.output_root / "context_01/control/attempt1.json").is_file())
        self.assertEqual(result["model_invocations"], 6)

    def test_binding_invalid_wrapper_does_not_count_as_valid_report(self):
        self.prepare()
        self.failures["context_01/binding"] = "schema"
        result = self.execute()
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(self.runtime.validate_verifier_report.call_count, 3)
        self.assertEqual(result["known_token_usage_subtotal"]["total_tokens"], 150)

    def test_strict_report_extension_failure_is_paid_failure(self):
        self.prepare()
        self.physical.validate_verifier_identity_fields.side_effect = ValueError("invalid exact union")
        result = self.execute()
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["model_invocations"], 6)
        self.assertEqual(sum(r["status"] == "failed" for r in result["results"]), 4)
        self.assertEqual(result["token_usage"]["total_tokens"], 150)

    def test_unknown_start_is_not_zero_or_complete_even_without_events(self):
        self.prepare()
        self.failures["context_01/control"] = "unknown_start"
        result = self.execute()
        self.assertEqual(result["status"], "incomplete")
        self.assertFalse(result["model_invocation_count_complete"])
        self.assertEqual(result["unknown_subprocess_starts"], ["context_01/control"])
        self.assertTrue(all(v is None for v in result["token_usage"].values()))
        self.assertEqual(result["known_token_usage_subtotal"]["total_tokens"], 125)

    def test_successful_outputs_with_unknown_usage_leave_batch_incomplete(self):
        self.prepare()
        self.unknown_usage.add("context_01/control")
        result = self.execute()
        self.assertTrue(all(r["status"] == "success" for r in result["results"]))
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["unknown_usage_attempts"], ["context_01/control"])
        self.assertIsNone(result["token_usage"]["total_tokens"])

    def test_worker_exception_after_marker_cannot_erase_unknown_request_or_peers(self):
        self.prepare()
        original = D.run_one

        def crash(*args):
            spec = args[-2]
            if spec["call_id"] == "context_01/control":
                D.write(Path(spec["directory"]) / "attempt1.started.json", {"requested": True})
                raise OSError("worker write failure")
            return original(*args)

        with mock.patch.object(D, "run_one", side_effect=crash):
            result = self.execute()
        self.assertEqual(result["unaccounted_attempt_starts"], ["context_01/control"])
        self.assertFalse(result["model_invocation_count_complete"])
        self.assertIsNone(result["token_usage"]["total_tokens"])
        self.assertEqual(len(result["results"]), 6)

    def test_duplicate_execute_and_template_drift_fail_before_calls(self):
        self.prepare()
        path = self.args.output_root / "context_01/binding_template.json"
        path.write_text("tampered template")
        with self.assertRaisesRegex(RuntimeError, "Changed frozen material"):
            self.execute()
        self.assertEqual(self.calls, [])
        self.assertFalse((self.args.output_root / "execute_claim.json").exists())

    def test_atomic_claim_prevents_reexecution(self):
        self.prepare()
        self.execute()
        with self.assertRaisesRegex(RuntimeError, "never-started"):
            self.execute()
        self.assertEqual(len(self.calls), 6)

    def test_mutated_plan_budget_rejected_even_with_matching_manifest(self):
        self.prepare()
        plan = copy.deepcopy(self.plan)
        plan["maximum_retries"] = 1
        with self.assertRaisesRegex(RuntimeError, "six-call"):
            D.validate_plan(plan, self.args.output_root)

    def test_survey_lock_detects_raw_drift_before_binding_request(self):
        self.prepare()
        original = D.lock_binding

        def mutate(spec, *args):
            if spec["chain_id"] == "context_01":
                D.write(Path(spec["directory"]).parent / "survey/attempt1.json", {"regions": []})
            return original(spec, *args)

        with mock.patch.object(D, "lock_binding", side_effect=mutate):
            result = self.execute()
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["model_invocations"], 5)
        row = next(r for r in result["results"] if r["call_id"] == "context_01/binding")
        self.assertFalse(row["subprocess_started"])
        self.assertFalse(row["subprocess_start_unknown"])

    def test_prepare_rejects_changed_initial_artifact_before_model_calls(self):
        seed, shot = D.CONTEXTS[0]
        path = self.batch / f"seed_{seed}" / shot / "adjudication/adjudicator_initial.json"
        path.write_text("{}")
        with self.assertRaisesRegex(RuntimeError, "recorded artifact"):
            self.prepare()
        self.assertEqual(self.calls, [])

    def test_single_result_write_failure_preserves_known_usage_and_harvests_peers(self):
        self.prepare()
        real_write = D.write
        failed = False

        def fail_once(path, value):
            nonlocal failed
            if str(path).endswith("context_01/control/result.json") and not failed:
                failed = True
                raise OSError("synthetic result persistence failure")
            return real_write(path, value)

        with mock.patch.object(D, "write", side_effect=fail_once):
            result = self.execute()
        self.assertTrue(failed)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual((len(result["results"]), result["model_invocations"], len(self.calls)), (6, 6, 6))
        self.assertEqual(result["token_usage"]["total_tokens"], 150)
        self.assertTrue(result["persistence_errors"])
        self.assertEqual(json.loads(self.stdout.getvalue().splitlines()[-1])["known_token_usage_subtotal"]["total_tokens"], 150)

    def test_final_manifest_write_failure_emits_all_results_and_usage(self):
        self.prepare()
        real_write = D.write

        def fail_final(path, value):
            if Path(path).name == "manifest.json" and "end_utc" in value:
                raise OSError("synthetic final manifest failure")
            return real_write(path, value)

        with mock.patch.object(D, "write", side_effect=fail_final):
            code = D.execute(self.args)
        summary = json.loads(self.stdout.getvalue().splitlines()[-1])
        self.assertEqual(code, 1)
        self.assertEqual(summary["status"], "incomplete")
        self.assertEqual((len(summary["results"]), summary["model_invocations"], len(self.calls)), (6, 6, 6))
        self.assertEqual(summary["known_token_usage_subtotal"]["total_tokens"], 150)
        self.assertTrue(summary["model_invocation_count_complete"])
        self.assertEqual(summary["unknown_usage_attempts"], [])
        self.assertTrue(any("final manifest failure" in e["error"] for e in summary["persistence_errors"]))

    def test_accounting_helper_failure_preserves_returned_invocation_usage(self):
        self.prepare()

        def fail_one_account(*, invocation, error, events_path):
            if invocation and invocation.thread_id == "context_01/control":
                raise OSError("synthetic accounting failure")
            return self.account(invocation=invocation, error=error, events_path=events_path)

        self.runtime._codex_attempt_accounting.side_effect = fail_one_account
        result = self.execute()
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual((result["model_invocations"], len(result["results"])), (6, 6))
        self.assertEqual(result["token_usage"]["total_tokens"], 150)
        row = next(r for r in result["results"] if r["call_id"] == "context_01/control")
        self.assertEqual(row["token_usage"], USAGE)
        self.assertFalse(row["subprocess_start_unknown"])
        self.assertIn("accounting_error", row)

    def test_postpaid_output_hash_failure_does_not_erase_usage(self):
        self.prepare()
        real_digest = D.digest

        def fail_hash(path):
            if str(path).endswith("context_01/control/returned_payload.json"):
                raise OSError("synthetic output hash failure")
            return real_digest(path)

        with mock.patch.object(D, "digest", side_effect=fail_hash):
            result = self.execute()
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual((result["model_invocations"], len(self.calls)), (6, 6))
        self.assertEqual(result["token_usage"]["total_tokens"], 150)
        self.assertTrue(any(e.get("operation") == "hash" for e in result["persistence_errors"]))


class BlindProbeRealContractTests(unittest.TestCase):
    """Exercise real survey/binding schemas and unchanged verifier validators."""

    def run_chain(self, *, omit_binding=False):
        fixtures = load("blind_probe_real_contract_fixture", Path(__file__).with_name("test_blind_survey_binding.py"))
        fixture = fixtures.BlindSurveyBindingTests()
        fixture.setUp()
        ensemble = importlib.import_module("ensemble_shot_entity_detection")
        physical = importlib.import_module("physical_identity_review")
        survey, binding = fixtures.survey, fixtures.binding
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        parent = Path(temporary.name) / "test_chain"
        parent.mkdir()
        context = {"shot_id": "synthetic", "target_cluster_ids": list(fixture.targets),
                   "all_cluster_ids": list(fixture.targets), "valid_frame_ids": [0, 2, 4, 6, 8, 10],
                   "target_proposal_ids_by_cluster": fixture.targets, "identity_challenge_pairs": [],
                   "intra_cluster_split_challenges": []}
        D.write(parent / "context.json", context)
        D.write(parent / "views.json", fixture.bundle)
        standard = physical.build_verifier_prompt(
            shot_id="synthetic", verifier_id=D.VERIFIER_ID, verification_view={"targets": []},
            valid_frame_ids=context["valid_frame_ids"], reference_frames=fixture.bundle["views"][:6],
            allowed_input_paths=fixture.bundle["attachments"][:6], policy_text="Synthetic neutral verifier policy.")
        (parent / "standard.txt").write_text(standard)
        (parent / "survey.txt").write_text(survey.build_survey_prompt(fixture.bundle))
        D.write(parent / "template.json", {"chain_id": "test_chain", "standard_verifier_prompt": str(parent / "standard.txt"),
                                          "builder_source_sha256": D.digest(Path(binding.__file__)),
                                          "binding_instructions": binding.BINDING_INSTRUCTIONS})
        payload = copy.deepcopy(fixture.payload)
        if omit_binding:
            payload["bindings"].pop()
        calls = []

        def invoke(**kwargs):
            role = Path(kwargs["output_path"]).parent.name
            returned = fixture.raw if role == "survey" else payload
            calls.append(role)
            D.write(Path(kwargs["output_path"]), returned)
            Path(kwargs["events_path"]).write_text(json.dumps({"type": "turn.completed", "usage": USAGE}) + "\n")
            return SimpleNamespace(payload=returned, token_usage=copy.deepcopy(USAGE), runtime_seconds=0.01, thread_id=role)

        runtime = SimpleNamespace(run_codex_json=invoke, _codex_attempt_accounting=ensemble._codex_attempt_accounting,
                                  validate_verifier_report=ensemble.validate_verifier_report)
        schema = Path(physical.__file__).resolve().parents[1] / "schemas/codex_entity_verification_v0.6.schema.json"
        plan = {"model_config": {"codex_wrapper": "fake_no_cli_invocation"}, "verifier_output_schema": str(schema),
                "frozen_hashes": {str(p): D.digest(p) for p in parent.iterdir() if p.is_file()}}
        rows = {}
        for role in ("survey", "binding"):
            directory = parent / role
            (directory / "workdir").mkdir(parents=True)
            spec = {"call_id": "test_chain/" + role, "chain_id": "test_chain", "role": role,
                    "directory": str(directory), "context": str(parent / "context.json"),
                    "view_bundle": str(parent / "views.json"), "standard_prompt": str(parent / "standard.txt"),
                    "binding_template": str(parent / "template.json"), "prompt": str(parent / "survey.txt"),
                    "attachments": fixture.bundle["attachments"] if role == "survey" else fixture.bundle["attachments"][:6],
                    "output_schema": str(survey.SCHEMA_PATH if role == "survey" else binding.SCHEMA_PATH),
                    "dependency": "test_chain/survey" if role == "binding" else None}
            rows[role] = D.run_one(runtime, physical, survey, binding, spec, plan)
        self.assertEqual(calls, ["survey", "binding"])
        self.assertEqual(rows["survey"]["status"], "success", rows["survey"])
        self.assertEqual(D.content_hash(fixture.raw), binding.survey_content_sha256(fixture.raw))
        return parent, rows

    def test_actual_survey_binding_and_v06_report_contracts_pass_through_driver(self):
        parent, rows = self.run_chain()
        self.assertEqual(rows["binding"]["status"], "success", rows["binding"])
        audit = D.read(parent / "binding/correspondence_audit.json")
        self.assertTrue(audit["all_target_proposals_covered"])
        self.assertTrue((parent / "binding/verifier_report.json").is_file())
        self.assertEqual((parent / "binding/binding_prompt.txt").read_text().count((parent / "standard.txt").read_text()), 1)

    def test_actual_missing_proposal_binding_retains_raw_usage_and_never_fills_gap(self):
        parent, rows = self.run_chain(omit_binding=True)
        self.assertEqual(rows["binding"]["status"], "failed")
        self.assertIn("Missing target proposal bindings", rows["binding"]["error"])
        self.assertEqual(rows["binding"]["token_usage"], USAGE)
        self.assertEqual(len(D.read(parent / "binding/attempt1.json")["bindings"]), 1)
        self.assertFalse((parent / "binding/verifier_report.json").exists())


if __name__ == "__main__":
    unittest.main()
