"""Frozen scope planner routing and native failure accounting; no API calls."""

from contextlib import ExitStack, redirect_stdout
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from PIL import Image

DIRECTORY = (
    Path(__file__).resolve().parents[1]
    / "experiments/study_inconsistent_2/entity_discovery_iterations"
)
PROJECT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {name: module}):
        spec.loader.exec_module(module)
    return module


D = load("scope_shadow_driver_tested", DIRECTORY / "run_scope_first_shadow_probe.py")
CONFIG = load("scope_shadow_config_test", DIRECTORY / "run_frozen_batch.py")
CONTROLS = load(
    "scope_shadow_controls_test", DIRECTORY / "observer_context_controls.py"
)
with mock.patch.dict(
    sys.modules, {"run_frozen_batch": CONFIG, "observer_context_controls": CONTROLS}
):
    BASE = load("scope_shadow_accounting_test", DIRECTORY / D.BASE_NAME)
    SMOKE = load(
        "scope_shadow_smoke_test",
        DIRECTORY / "run_single_frame_schema_transport_smoke.py",
    )
USAGE = dict(zip(BASE.TOKEN_KEYS, (20, 3, 5, 25)))
EMPTY = {"plans": []}
SCHEMA = {
    "type": "object",
    "properties": {"plans": {"type": "array"}},
    "required": ["plans"],
    "additionalProperties": False,
}
STUB_HELPER = """from pathlib import Path
import json
SCHEMA_PATH = Path(__file__).resolve().parents[1] / 'schemas/scope-first-shadow.v0.1.schema.json'
SCHEMA_ADMISSION_PAYLOAD = {'plans': []}
def build_shadow_context(initial, anonymous, targets, view_bundle, shot_id):
    public = {'shot_id': shot_id, 'clusters': initial['clusters'],
              'proposals': anonymous['proposals'], 'pairs': targets['pairs'], 'splits': targets['splits']}
    return {'public_context': public, 'private_audit': {'proposal_count': len(anonymous['proposals'])}}
def build_shadow_prompt(public):
    return 'Independent scope planner. No tools.\u005cn' + json.dumps(public, sort_keys=True)
def validate_shadow(payload, public):
    if payload['plans']:
        raise ValueError('Mock exact scope coverage violation')
    return {'coverage_valid': True, 'proposal_count': len(public['proposals']), 'production_consumer': False}
"""


class ScopeFirstShadowDriverTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root, self.source, self.workspace = [
            self.base / p for p in ("out", "source", "workspace")
        ]
        scripts, schemas = (
            self.workspace / "EECBench/scripts",
            self.workspace / "EECBench/schemas",
        )
        scripts.mkdir(parents=True)
        schemas.mkdir(parents=True)
        (scripts / "ensemble_shot_entity_detection.py").write_text("# fake transport\n")
        (scripts / "scope_first_shadow.py").write_text(STUB_HELPER)
        CONFIG.write(schemas / D.SCHEMA_NAME, SCHEMA)
        CONFIG.write(
            schemas / "codex_entity_adjudication_v0.6.schema.json",
            {"type": "object", "required": ["clusters"]},
        )
        source_hashes = {}
        for index, (_, shot) in enumerate(D.CONTEXTS, 1):
            directory = self.source / f"context_{index:02d}"
            views, refs = [], []
            for ordinal in range(6):
                path = directory / "inputs/images" / f"frame_{ordinal:06d}.jpg"
                path.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (32, 24), (index, ordinal, 47)).save(path)
                h = D.digest(path)
                source_hashes[str(path)] = h
                views.append(
                    {
                        "attachment_index": ordinal + 1,
                        "view_id": f"frame_{ordinal}_original",
                        "frame_id": ordinal,
                        "kind": "original",
                        "path": str(path),
                        "source_path": str(path),
                        "sha256": h,
                        "source_sha256": h,
                        "source_size": [32, 24],
                        "output_size": [32, 24],
                        "crop_xyxy": [0, 0, 32, 24],
                        "scale": 1,
                    }
                )
                refs.append(
                    {
                        "attachment_index": ordinal + 1,
                        "frame_id": ordinal,
                        "path": str(path),
                        "sha256": h,
                    }
                )
            material = {
                "inputs/initial.json": {
                    "clusters": [
                        {
                            "cluster_id": "c001",
                            "anonymous_proposal_ids": ["p001", "p002"],
                        }
                    ],
                    "initial_verdict": "FORBIDDEN_VERDICT",
                },
                "inputs/anonymous.json": {
                    "proposals": [
                        {"anonymous_proposal_id": "p001", "name": "fallible first"},
                        {"anonymous_proposal_id": "p002", "name": "fallible second"},
                    ],
                    "panel": "FORBIDDEN_PANEL",
                },
                "inputs/targets.json": {
                    "pairs": ["pair001"],
                    "splits": ["split001"],
                    "prior_review": "FORBIDDEN_REVIEW",
                },
                "inputs/shot_manifest.json": {
                    "shot_id": shot,
                    "reference_frames": refs,
                    "prompt_bound_registry": "FORBIDDEN_REGISTRY",
                },
                "view_bundle.json": {
                    "views": views,
                    "attachments": [v["path"] for v in views],
                    "instructions": "FORBIDDEN_OLD_POLICY",
                },
            }
            for relative, payload in material.items():
                path = directory / relative
                CONFIG.write(path, payload)
                source_hashes[str(path)] = D.digest(path)
            CONFIG.write(
                directory / "survey_answer.json", {"answer": "FORBIDDEN_OLD_OUTPUT"}
            )
        CONFIG.write(
            self.source / "manifest.json",
            {
                "protocol_version": "blind_pixel_survey_binding_diagnostic_v0.1",
                "status": "success",
                "hashes": source_hashes,
                "results": [{"answer": "FORBIDDEN_OLD_OUTPUT"}],
            },
        )
        binary = self.base / "codex"
        binary.write_text("#!/bin/sh\nexit 97\n")
        binary.chmod(0o755)
        evidence = self.base / "offline.json"
        CONFIG.write(evidence, {"offline": True})
        controls = self.base / "controls.json"
        CONFIG.write(
            controls,
            {
                "version": "observer_process_context_controls_v0.1",
                "pinned_cli_sha256": D.digest(binary),
                "disabled_skill_paths": [],
                "project_doc_max_bytes": 0,
                "offline_evidence": {
                    "path": str(evidence),
                    "sha256": D.digest(evidence),
                },
            },
        )
        self.args = SimpleNamespace(
            source_probe=self.source,
            output_root=self.root,
            codex_bin=str(binary),
            schema_admission=self.base / "admission/manifest.json",
            observer_context_controls=controls,
        )
        self.observed, self.failure, self.active, self.peak = [], None, 0, 0
        self.lock = threading.Lock()
        self.runtime = SimpleNamespace(
            run_codex_json=self.fake_call,
            TOKEN_KEYS=BASE.TOKEN_KEYS,
            validate_codex_schema_transport=lambda p: None,
            _codex_attempt_accounting=self.accounting,
            validate_decisions=mock.Mock(),
            _attempt_usage_from_events=lambda p: json.loads(
                p.read_text().splitlines()[0]
            )["usage"],
            CodexCallError=RuntimeError,
        )
        self.make_admission(
            schemas / D.SCHEMA_NAME, CONTROLS.context_overrides(D.read(controls))
        )
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.object(D, "WORKSPACE", self.workspace))
        self.stack.enter_context(
            mock.patch.object(D, "load_runtime", side_effect=self.frozen_runtime)
        )
        self.stack.enter_context(
            mock.patch.object(D, "load_shared", return_value=(CONFIG, BASE))
        )

    def make_admission(self, schema, overrides):
        directory = self.args.schema_admission.parent / "scope_shadow"
        directory.mkdir(parents=True)
        for name, payload in (("attempt1.json", EMPTY), ("result.json", {})):
            CONFIG.write(directory / name, payload)
        (directory / "attempt1.events.jsonl").write_text(
            json.dumps({"type": "turn.completed", "usage": USAGE}) + "\n"
        )
        (directory / "attempt1.stderr.log").write_text("")
        attempt = {
            "role": "scope_shadow",
            "attempt": 1,
            "status": "success",
            "subprocess_started": True,
            "subprocess_start_unknown": False,
            "returncode": 0,
            "token_usage": USAGE.copy(),
        }
        CONFIG.write(directory / "result.json", attempt)
        record = {
            "status": "success",
            "hashes_unchanged": True,
            "end_utc": "2026-09-08T00:00:00Z",
            "images": [],
            "maximum_invocations": 1,
            "model_invocations": 1,
            "model_invocation_count_complete": True,
            "maximum_retries": 0,
            "max_workers": 1,
            "model_config": {
                "model": D.MODEL,
                "reasoning_effort": "high",
                "context_config_overrides": overrides,
            },
            "unknown_subprocess_starts": [],
            "unknown_usage_attempts": [],
            "persistence_errors": [],
            "cases": [
                {
                    "role": "scope_shadow",
                    "schema": str(schema),
                    "directory": str(directory),
                    "expected": EMPTY,
                }
            ],
            "attempts": [attempt],
            "token_usage": USAGE.copy(),
            "known_token_usage_subtotal": USAGE.copy(),
            "hashes": {str(schema): D.digest(schema)},
            "output_hashes": {str(p): D.digest(p) for p in directory.iterdir()},
        }
        CONFIG.write(self.args.schema_admission, record)

    def frozen_runtime(self, root):
        self.shadow = load(
            "scope_shadow_frozen_mock",
            root / "frozen_workspace/EECBench/scripts/scope_first_shadow.py",
        )
        return self.runtime, self.shadow

    @staticmethod
    def accounting(*, invocation, error, events_path):
        source = invocation if invocation is not None else error
        return {
            "subprocess_started": invocation is not None
            or hasattr(error, "token_usage"),
            "token_usage": getattr(source, "token_usage", None),
            "returncode": 0 if invocation else None,
        }

    def fake_call(self, **kwargs):
        first = kwargs["output_path"].parent == self.root / "context_01/planner_1"
        with self.lock:
            self.observed.append(kwargs)
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            time.sleep(0.004)
            if first and self.failure == "unknown_start":
                raise OSError("events write failed after possible transport")
            payload = {} if first and self.failure == "schema" else copy.deepcopy(EMPTY)
            if first and self.failure == "coverage":
                payload["plans"] = [{"wrong_scope": True}]
            event = {"type": "turn.completed", "usage": USAGE.copy()}
            if first and self.failure == "tool":
                event = {"item": {"type": "command_execution"}}
            kwargs["events_path"].write_text(json.dumps(event) + "\n")
            CONFIG.write(kwargs["output_path"], payload)
            if first and self.failure == "transport":
                error = RuntimeError("HTTP 400")
                error.token_usage = USAGE.copy()
                raise error
            return SimpleNamespace(
                payload=payload,
                token_usage=None
                if first and self.failure == "unknown_usage"
                else USAGE.copy(),
                runtime_seconds=0.01,
                thread_id="fresh",
            )
        finally:
            with self.lock:
                self.active -= 1

    def prepare(self):
        with redirect_stdout(io.StringIO()):
            D.prepare(self.args)
        return D.read(self.root / "execution_plan.json")

    def execute(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = D.execute(self.args)
        return code, json.loads(output.getvalue().splitlines()[-1])

    def test_prepare_allowlist_complete_projection_and_identical_fresh_inputs(self):
        plan = self.prepare()
        self.assertEqual(len(plan["calls"]), 4)
        provenance = D.read(self.root / "sources/source_provenance.json")
        self.assertEqual(len(provenance["artifact_hashes"]), 22)
        self.assertFalse((self.root / "sources/source_manifest_snapshot.json").exists())
        self.assertEqual(
            [s["chain_id"] for s in plan["calls"]], ["context_01", "context_02"] * 2
        )
        for context in plan["contexts"]:
            public = D.read(context["public_context"])
            self.assertEqual(len(public["proposals"]), 2)
            self.assertEqual(
                public["clusters"][0]["anonymous_proposal_ids"], ["p001", "p002"]
            )
            self.assertNotIn("FORBIDDEN", Path(context["prompt"]).read_text())
            a, b = [s for s in plan["calls"] if s["chain_id"] == context["chain_id"]]
            self.assertEqual(a["prompt"], b["prompt"])
            self.assertEqual(a["attachments"], b["attachments"])
            self.assertEqual(len(a["attachments"]), 6)
            self.assertNotEqual(a["directory"], b["directory"])
        self.assertFalse(self.observed)

    def test_four_scope_calls_use_fixed_callback_audit_and_no_survey_output(self):
        plan = self.prepare()
        code, report = self.execute()
        self.assertEqual(
            (code, report["status"], len(self.observed)), (0, "success", 4)
        )
        self.assertEqual(report["token_usage"]["total_tokens"], 100)
        self.assertLessEqual(self.peak, 2)
        for call, spec in zip(
            sorted(self.observed, key=lambda c: str(c["output_path"])),
            sorted(plan["calls"], key=lambda s: s["directory"]),
        ):
            self.assertEqual(
                (call["model"], call["timeout_sec"], call["persistent"]),
                (D.MODEL, 1800, False),
            )
            self.assertEqual(len(call["attachments"]), 6)
            directory = Path(spec["directory"])
            self.assertTrue((directory / "scope_plan_audit.json").exists())
            self.assertFalse((directory / "survey_derived.json").exists())
            self.assertFalse((directory / "verifier_report.json").exists())
            result = D.read(directory / "result.json")
            self.assertEqual(
                result["output_hashes"][str(directory / "scope_plan_audit.json")],
                D.digest(directory / "scope_plan_audit.json"),
            )

    def test_schema_coverage_tools_and_transport_failures_keep_four_paid_attempts(self):
        for failure in ("schema", "coverage", "tool", "transport"):
            with self.subTest(failure=failure):
                self.root = self.args.output_root = self.base / failure
                self.failure, self.observed = failure, []
                self.prepare()
                code, report = self.execute()
                self.assertEqual(
                    (
                        code,
                        report["status"],
                        len(self.observed),
                        len(report["results"]),
                    ),
                    (1, "incomplete", 4, 4),
                )
                self.assertEqual(
                    report["known_token_usage_subtotal"]["total_tokens"], 100
                )
                self.assertTrue(
                    (self.root / "context_01/planner_1/attempt1.json").exists()
                )

    def test_unknown_start_and_usage_never_become_zero_or_success(self):
        for failure in ("unknown_start", "unknown_usage"):
            with self.subTest(failure=failure):
                self.root = self.args.output_root = self.base / failure
                self.failure, self.observed = failure, []
                self.prepare()
                code, report = self.execute()
                self.assertEqual(
                    (code, report["status"], len(self.observed)), (1, "incomplete", 4)
                )
                self.assertTrue(all(v is None for v in report["token_usage"].values()))
                self.assertEqual(
                    report["known_token_usage_subtotal"]["total_tokens"], 75
                )

    def test_worker_and_persistence_failures_preserve_peer_usage(self):
        for failure in ("worker", "audit_write", "result_write", "final_manifest"):
            with self.subTest(failure=failure):
                self.root = self.args.output_root = self.base / failure
                self.observed = []
                self.prepare()
                original_worker, original_write = D.run_one, CONFIG.write

                def worker(*args):
                    if (
                        failure == "worker"
                        and args[3]["call_id"] == "context_01/planner_1"
                    ):
                        raise OSError("lost worker result")
                    return original_worker(*args)

                def write(path, value):
                    p = Path(path)
                    if (
                        (
                            failure == "audit_write"
                            and p.name == "scope_plan_audit.json"
                            and p.parent == self.root / "context_01/planner_1"
                        )
                        or (
                            failure == "result_write"
                            and p == self.root / "context_01/planner_1/result.json"
                        )
                        or (
                            failure == "final_manifest"
                            and p == self.root / "manifest.json"
                            and value.get("end_utc")
                        )
                    ):
                        raise OSError("fake persistence failure")
                    original_write(path, value)

                with (
                    mock.patch.object(D, "run_one", side_effect=worker),
                    mock.patch.object(CONFIG, "write", side_effect=write),
                    mock.patch.object(BASE, "write", side_effect=write),
                ):
                    code, report = self.execute()
                self.assertEqual(
                    (code, report["status"], len(report["results"])),
                    (1, "incomplete", 4),
                )
                self.assertEqual(
                    report["known_token_usage_subtotal"]["total_tokens"],
                    75 if failure == "worker" else 100,
                )
                if failure == "worker":
                    self.assertTrue(report["unknown_subprocess_starts"])
                else:
                    self.assertTrue(report["persistence_errors"])

    def test_missing_callback_is_prepaid_failure_and_default_survey_still_works(self):
        plan = self.prepare()
        spec = plan["calls"][0]
        result = BASE.run_one(self.runtime, None, None, None, spec, plan)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["request_marker_written"])
        self.assertFalse(self.observed)
        survey_spec = {**spec, "role": "survey", "view_bundle": spec["context"]}
        survey = SimpleNamespace(
            validate_survey=lambda payload, context: {"legacy": True}
        )
        result = BASE.run_one(self.runtime, None, survey, None, survey_spec, plan)
        self.assertEqual(result["status"], "success")
        self.assertEqual(
            D.read(Path(spec["directory"]) / "survey_derived.json"), {"legacy": True}
        )

    def test_iterator_failure_harvests_every_submitted_paid_future(self):
        self.prepare()

        def broken_iterator(futures):
            yield next(iter(futures))
            raise RuntimeError("injected completion iterator failure")

        with mock.patch.object(
            D.concurrent.futures, "as_completed", side_effect=broken_iterator
        ):
            code, report = self.execute()
        self.assertEqual(
            (code, report["status"], len(self.observed), len(report["results"])),
            (1, "incomplete", 4, 4),
        )
        self.assertEqual(report["known_token_usage_subtotal"]["total_tokens"], 100)
        self.assertEqual(report["token_usage"]["total_tokens"], 100)
        self.assertEqual(report["unknown_subprocess_starts"], [])
        self.assertEqual(report["unknown_usage_attempts"], [])

    def test_original_frame_aliases_projection_mutation_and_limits_are_rejected(self):
        plan = self.prepare()
        for key, value in (
            ("maximum_model_calls", 5),
            ("maximum_retries", False),
            ("max_workers", 3),
            ("timeout_sec", 900),
            ("production_consumer", True),
        ):
            changed = copy.deepcopy(plan)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                D.validate_plan(changed, self.root, self.shadow)
        view_path = self.root / "context_01/view_bundle.json"
        original = D.read(view_path)
        for key, value in (
            ("frame_id", False),
            ("scale", True),
            ("scale", 1.0),
            ("attachment_index", True),
        ):
            changed = copy.deepcopy(original)
            changed["views"][0][key] = value
            CONFIG.write(view_path, changed)
            with (
                self.subTest(view_key=key, value=value),
                self.assertRaises(RuntimeError),
            ):
                D.validate_plan(plan, self.root, self.shadow)
        CONFIG.write(view_path, original)
        p = Path(plan["contexts"][0]["public_context"])
        changed = D.read(p)
        changed["proposals"].pop()
        CONFIG.write(p, changed)
        with self.assertRaises(RuntimeError):
            D.validate_plan(plan, self.root, self.shadow)

    def test_relaunch_image_drift_and_old_survey_admission_block_before_api(self):
        plan = self.prepare()
        image = Path(plan["calls"][0]["attachments"][0])
        old = image.read_bytes()
        image.write_bytes(old + b"drift")
        with self.assertRaises(RuntimeError):
            self.execute()
        self.assertFalse(self.observed)
        image.write_bytes(old)
        self.execute()
        with self.assertRaises(RuntimeError):
            self.execute()
        self.assertEqual(len(self.observed), 4)
        admission = D.read(self.args.schema_admission)
        admission["cases"][0]["role"] = "survey"
        CONFIG.write(self.args.schema_admission, admission)
        with self.assertRaises(RuntimeError):
            D.validate_admission(
                self.args.schema_admission,
                Path(plan["actual_output_schema"]["path"]),
                self.runtime,
            )

    def test_smoke_contract_default_and_scope_are_explicit_and_frozen(self):
        self.prepare()
        role, path, expected = SMOKE.admission_case("survey", self.root)
        self.assertEqual(role, "survey")
        self.assertEqual(path.name, "single-frame-pixel-survey.v0.1.schema.json")
        self.assertEqual(
            expected,
            {
                "schema_version": "single_frame_pixel_survey_v0.1",
                "regions": [],
                "coverage_notes": "Synthetic schema admission only.",
            },
        )
        with mock.patch.dict(sys.modules, {"scope_first_shadow": self.shadow}):
            role, path, expected = SMOKE.admission_case("scope_shadow", self.root)
        self.assertEqual(
            (role, path.name, expected), ("scope_shadow", D.SCHEMA_NAME, EMPTY)
        )
        stale = SimpleNamespace(
            __file__="/tmp/not-frozen.py",
            SCHEMA_PATH=path,
            SCHEMA_ADMISSION_PAYLOAD=EMPTY,
        )
        with (
            mock.patch.dict(sys.modules, {"scope_first_shadow": stale}),
            self.assertRaises(RuntimeError),
        ):
            SMOKE.admission_case("scope_shadow", self.root)

    def test_shared_loader_refuses_cached_live_configuration(self):
        with (
            mock.patch.dict(sys.modules, {"run_frozen_batch": CONFIG}),
            self.assertRaises(RuntimeError),
        ):
            # Bypass this fixture's loader patch for the actual isolated loader.
            load(
                "scope_unpatched_loader", DIRECTORY / "run_scope_first_shadow_probe.py"
            ).load_shared(self.root)

    def test_actual_source_projection_base_validation_and_full_schema_interoperate(
        self,
    ):
        import jsonschema
        import shutil

        isolated = self.base / "actual_inputs"
        frozen = isolated / "frozen_workspace/EECBench"
        captured = {}
        for source_file in [
            *sorted((PROJECT / "scripts").glob("*.py")),
            *sorted((PROJECT / "schemas").glob("*.json")),
        ]:
            D.copy_checked(
                source_file, frozen / source_file.relative_to(PROJECT), captured
            )
        # Exercise the actual frozen import guard, not this fixture's mock loader.
        self.stack.enter_context(mock.patch.dict(sys.modules))
        for source_file in (PROJECT / "scripts").glob("*.py"):
            sys.modules.pop(source_file.stem, None)
        self.stack.enter_context(mock.patch.object(sys, "path", list(sys.path)))
        actual_driver = load(
            "scope_real_frozen_loader", DIRECTORY / "run_scope_first_shadow_probe.py"
        )
        runtime, shadow = actual_driver.load_runtime(isolated)
        self.assertEqual(
            Path(shadow.SCHEMA_PATH).resolve(), frozen / "schemas" / D.SCHEMA_NAME
        )
        self.assertEqual(D.read(shadow.SCHEMA_PATH), shadow.SCHEMA)
        runtime.validate_codex_schema_transport(shadow.SCHEMA_PATH)
        jsonschema.Draft202012Validator(shadow.SCHEMA).validate(
            shadow.SCHEMA_ADMISSION_PAYLOAD
        )
        source = DIRECTORY / "blind_pixel_survey_probe_01"
        for index, (_, shot_id) in enumerate(D.CONTEXTS, 1):
            directory = isolated / f"context_{index:02d}"
            before = {}
            for relative in D.INPUTS:
                p = source / directory.name / relative
                before[str(p)] = D.digest(p)
                target = directory / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(p, target)
            projection = D.project_context(shadow, directory, shot_id, runtime)
            initial = D.read(directory / "inputs/initial.json")
            anonymous = D.read(directory / "inputs/anonymous.json")
            public = projection["public_context"]
            self.assertEqual(
                [c["cluster_id"] for c in public["clusters"]],
                [c["cluster_id"] for c in initial["clusters"]],
            )
            self.assertEqual(
                [p["anonymous_proposal_id"] for p in public["proposals"]],
                [p["anonymous_proposal_id"] for p in anonymous["proposals"]],
            )
            self.assertEqual(len(public["reference_frames"]), 6)
            self.assertTrue(shadow.build_shadow_prompt(public))
            empty = copy.deepcopy(shadow.SCHEMA_ADMISSION_PAYLOAD)
            empty["shot_id"] = shot_id
            with self.assertRaises(ValueError):
                shadow.validate_shadow(empty, public)
            broken = copy.deepcopy(initial)
            broken["clusters"][0].pop("decision")
            CONFIG.write(directory / "inputs/initial.json", broken)
            with mock.patch.object(shadow, "build_shadow_context") as builder:
                with self.assertRaises(jsonschema.ValidationError):
                    D.project_context(shadow, directory, shot_id, runtime)
                builder.assert_not_called()
            D.verify(before)
        D.verify(captured)
        self.assertFalse(self.observed)

    def test_scope_smoke_uses_actual_complete_schema_and_retains_failed_usage(self):
        with mock.patch.object(sys, "path", [str(PROJECT / "scripts"), *sys.path]):
            shadow = load(
                "scope_actual_smoke_contract", PROJECT / "scripts/scope_first_shadow.py"
            )
        expected = copy.deepcopy(shadow.SCHEMA_ADMISSION_PAYLOAD)
        for invalid in (False, True):
            directory = self.base / ("smoke_invalid" if invalid else "smoke_valid")
            (directory / "workdir").mkdir(parents=True)
            prompt = directory / "prompt.txt"
            prompt.write_text(json.dumps(expected))
            spec = {
                "role": "scope_shadow",
                "directory": str(directory),
                "schema": str(shadow.SCHEMA_PATH),
                "prompt": str(prompt),
                "expected": expected,
            }

            def invoke(**kwargs):
                self.assertEqual(kwargs["attachments"], [])
                self.assertFalse(kwargs["persistent"])
                self.assertEqual(
                    D.digest(kwargs["schema_path"]), D.digest(shadow.SCHEMA_PATH)
                )
                payload = copy.deepcopy(expected)
                if invalid:
                    payload.pop("proposal_reviews")
                CONFIG.write(kwargs["output_path"], payload)
                kwargs["events_path"].write_text(
                    json.dumps({"type": "turn.completed", "usage": USAGE}) + "\n"
                )
                return SimpleNamespace(
                    payload=payload,
                    token_usage=USAGE.copy(),
                    runtime_seconds=0.1,
                    thread_id="fresh",
                )

            with mock.patch.object(
                self.runtime, "run_codex_json", side_effect=invoke
            ) as call:
                row = SMOKE.invoke_case(
                    self.runtime,
                    {"codex_wrapper": "/unused/fake", "model": D.MODEL},
                    spec,
                )
            self.assertEqual(call.call_count, 1)
            self.assertEqual(row["role"], "scope_shadow")
            self.assertEqual(row["status"], "failed" if invalid else "success")
            self.assertEqual(row["token_usage"]["total_tokens"], 25)
            self.assertTrue((directory / "attempt1.json").exists())


if __name__ == "__main__":
    unittest.main()
