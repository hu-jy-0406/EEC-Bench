"""Eight-call survey isolation, immutable inputs and complete failure accounting."""
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


DIRECTORY = Path(__file__).resolve().parents[1] / "experiments/study_inconsistent_2/entity_discovery_iterations"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


D = load("spatial_driver_tested", DIRECTORY / "run_spatial_cell_survey_probe.py")
HELPER = load("spatial_test_configuration", DIRECTORY / "run_frozen_batch.py")
with mock.patch.dict(sys.modules, {"run_frozen_batch": HELPER}):
    BASE = load("spatial_test_accounting", DIRECTORY / "run_blind_pixel_survey_probe.py")
USAGE = dict(zip(BASE.TOKEN_KEYS, (20, 3, 5, 25)))
EMPTY = {"schema_version": "blind_pixel_survey_v0.1", "regions": [], "tracks": [],
         "region_relations": [], "coverage_notes": "No completeness claim."}


class SpatialCellSurveyProbeDriverTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.workspace, self.root, self.source = (self.base / s for s in ("workspace", "output", "source"))
        schemas = self.workspace / "EECBench/schemas"
        scripts = self.workspace / "EECBench/scripts"
        schemas.mkdir(parents=True)
        scripts.mkdir()
        actual_schema = Path(__file__).resolve().parents[1] / "schemas" / D.SCHEMA_NAME
        (schemas / D.SCHEMA_NAME).write_bytes(actual_schema.read_bytes())
        for name in ("ensemble_shot_entity_detection", "blind_pixel_survey", "spatial_cell_survey"):
            (scripts / (name + ".py")).write_text("# frozen fixture; never calls a model\n")
        self.source.mkdir()
        source_schema = self.source / "frozen_workspace/EECBench/schemas" / D.SCHEMA_NAME
        source_schema.parent.mkdir(parents=True)
        source_schema.write_bytes(actual_schema.read_bytes())
        hashes = {str(source_schema): D.digest(source_schema)}
        calls = []
        for index, (seed, shot) in enumerate(D.CONTEXTS, 1):
            directory = self.source / f"context_{index:02d}"
            directory.mkdir()
            originals, views = {}, []
            for i in range(14):
                frame = i if i < 6 else (0 if i < 10 else 5)
                path = directory / (f"frame_{i:02d}.jpg" if i < 6 else f"crop_{i:02d}.png")
                path.write_bytes(f"immutable-image-context-{index}-view-{i}".encode())
                hashes[str(path)] = D.digest(path)
                if i < 6:
                    originals[frame] = str(path)
                views.append({"path": str(path), "source_path": originals[frame], "frame_id": frame,
                              "view_id": f"view_{i}", "sha256": D.digest(path), "output_size": [10, 6]})
            bundle = {"instructions": "unchanged base", "attachments": [v["path"] for v in views], "views": views}
            bundle_path = directory / "view_bundle.json"
            HELPER.write(bundle_path, bundle)
            hashes[str(bundle_path)] = D.digest(bundle_path)
            calls.append({"chain_id": f"context_{index:02d}", "role": "survey", "seed": seed, "shot": shot,
                          "view_bundle": str(bundle_path), "attachments": bundle["attachments"]})
            for forbidden in ("survey.json", "control.json", "binding.json", "candidates.json", "expected.json"):
                (directory / forbidden).write_text("FORBIDDEN_PRIVATE_CONTENT")
        self.original = {"protocol_version": "blind_pixel_survey_binding_diagnostic_v0.1", "status": "incomplete",
                         "end_utc": "completed", "calls": calls, "hashes": hashes,
                         "actual_output_schemas": {"survey": {"path": str(source_schema),
                             "sha256": D.digest(source_schema), "version": "blind_pixel_survey_v0.1"}}}
        HELPER.write(self.source / "manifest.json", self.original)
        self.binary = self.base / "fake-codex"
        self.binary.write_text("#!/bin/sh\nexit 97\n")
        self.binary.chmod(0o755)
        self.args = SimpleNamespace(source_probe=self.source, output_root=self.root, codex_bin=str(self.binary))
        self.observed, self.active, self.peak = [], 0, 0
        self.lock = threading.Lock()
        self.failure = None
        self.runtime = SimpleNamespace(run_codex_json=self.fake_call, _codex_attempt_accounting=self.accounting,
                                       validate_codex_schema_transport=lambda p: None)
        self.survey = SimpleNamespace(SCHEMA_PATH=self.root / "frozen_workspace/EECBench/schemas" / D.SCHEMA_NAME,
                    INSTRUCTIONS="unchanged base", build_survey_prompt=self.base_prompt,
                    validate_survey=lambda payload, bundle: {**copy.deepcopy(payload), "validated_mapping": True})
        self.spatial = SimpleNamespace(POLICY_VERSION="spatial_cell_survey_v0.1",
                    build_spatial_survey_prompt=lambda bundle, cell: self.base_prompt(bundle) + "\nCELL=" + cell)
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.patches.enter_context(mock.patch.object(D, "WORKSPACE", self.workspace))
        self.patches.enter_context(mock.patch.object(D, "load_runtime", return_value=(self.runtime, self.survey, self.spatial)))
        self.patches.enter_context(mock.patch.object(D, "load_shared", return_value=(HELPER, BASE)))

    @staticmethod
    def base_prompt(bundle):
        return "unchanged base\n" + json.dumps([{k: v[k] for k in ("view_id", "frame_id", "output_size")} for v in bundle["views"]])

    @staticmethod
    def accounting(*, invocation, error, events_path):
        source = invocation if invocation is not None else error
        return {"subprocess_started": invocation is not None or hasattr(error, "token_usage"),
                "token_usage": getattr(source, "token_usage", None), "returncode": 0 if invocation else None}

    def prepare(self):
        with redirect_stdout(io.StringIO()):
            D.prepare(self.args)
        return D.read(self.root / "execution_plan.json")

    def fake_call(self, **kwargs):
        cell = kwargs["output_path"].parent.name
        context = kwargs["output_path"].parent.parent.name
        with self.lock:
            self.observed.append((context, cell, kwargs))
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            time.sleep(0.003)
            if self.failure == "unknown_start" and (context, cell) == ("context_01", "TL"):
                raise OSError("events persistence could have failed after child start")
            events = []
            if self.failure == "tool" and (context, cell) == ("context_01", "TL"):
                events = [{"type": "item.completed", "item": {"type": "command_execution"}}]
            kwargs["events_path"].write_text("\n".join(json.dumps(x) for x in events))
            payload = copy.deepcopy(getattr(self, "payload_override", EMPTY))
            if self.failure == "schema" and (context, cell) == ("context_01", "TL"):
                payload.pop("regions")
            HELPER.write(kwargs["output_path"], payload)
            if self.failure == "transport" and (context, cell) == ("context_01", "TL"):
                error = RuntimeError("HTTP 400 transport failure")
                error.token_usage = USAGE.copy()
                raise error
            usage = None if self.failure == "unknown_usage" and (context, cell) == ("context_01", "TL") else USAGE.copy()
            return SimpleNamespace(payload=payload, token_usage=usage, runtime_seconds=0.1, thread_id="fresh")
        finally:
            with self.lock:
                self.active -= 1

    def execute(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = D.execute(self.args)
        return code, json.loads(output.getvalue().splitlines()[-1])

    def test_prepare_exact_matrix_images_and_original_bundle_copy_without_private_inputs(self):
        plan = self.prepare()
        self.assertEqual([(s["seed"], s["assigned_cell"]) for s in plan["calls"]],
                         [(seed, cell) for cell in D.CELLS for seed, _ in D.CONTEXTS])
        self.assertEqual(plan["maximum_model_calls"], 8)
        self.assertEqual(plan["maximum_retries"], 0)
        for index in (1, 2):
            name = f"context_{index:02d}"
            self.assertEqual((self.source / name / "view_bundle.json").read_bytes(),
                             (self.root / name / "source_view_bundle.json").read_bytes())
            old = D.read(self.source / name / "view_bundle.json")
            new = D.read(self.root / name / "view_bundle.json")
            for before, after in zip(old["attachments"], new["attachments"]):
                self.assertEqual(Path(before).read_bytes(), Path(after).read_bytes())
            for cell in D.CELLS:
                prompt = (self.root / name / cell / "prompt.txt").read_text()
                self.assertNotIn("FORBIDDEN_PRIVATE_CONTENT", prompt)
                self.assertNotIn(str(self.source), prompt)
                self.assertTrue(prompt.startswith(self.base_prompt(old)))

    def test_original_schema_policy_or_image_drift_fails_prepare(self):
        for kind in ("schema", "policy", "image"):
            with self.subTest(kind=kind):
                # Each branch uses a separate output root; the original is restored afterward.
                self.args.output_root = self.base / ("output_" + kind)
                self.survey.SCHEMA_PATH = self.args.output_root / "frozen_workspace/EECBench/schemas" / D.SCHEMA_NAME
                path = (self.workspace / "EECBench/schemas" / D.SCHEMA_NAME if kind == "schema"
                        else self.source / "context_01/view_bundle.json" if kind == "policy"
                        else Path(self.original["calls"][0]["attachments"][0]))
                before = path.read_bytes()
                try:
                    path.write_bytes(before + b" ")
                    with self.assertRaises(RuntimeError), redirect_stdout(io.StringIO()):
                        D.prepare(self.args)
                finally:
                    path.write_bytes(before)

    def test_eight_fresh_calls_max_two_high_wrapper_same_schema_and_known_usage(self):
        plan = self.prepare()
        code, report = self.execute()
        self.assertEqual(code, 0)
        self.assertEqual((len(self.observed), len(report["results"]), report["model_invocations"]), (8, 8, 8))
        self.assertLessEqual(self.peak, 2)
        self.assertEqual(report["token_usage"]["total_tokens"], 200)
        self.assertEqual(report["status"], "success")
        wrapper = Path(plan["model_config"]["codex_wrapper"]).read_text()
        self.assertIn("--disable shell_tool", wrapper)
        self.assertIn('model_reasoning_effort="high"', wrapper)
        for _, _, call in self.observed:
            self.assertFalse(call["persistent"])
            self.assertEqual(call["model"], "gpt-5.6-sol")
            self.assertEqual(call["timeout_sec"], 1800)
            self.assertEqual(len(call["attachments"]), 14)
            self.assertEqual(str(call["schema_path"]), plan["actual_output_schema"]["path"])

    def test_schema_guard_failure_retains_raw_usage_and_all_other_cells(self):
        self.prepare()
        self.failure = "schema"
        code, report = self.execute()
        self.assertEqual(code, 1)
        self.assertEqual(len(self.observed), 8)
        self.assertEqual(report["known_token_usage_subtotal"]["total_tokens"], 200)
        self.assertEqual(sum(r["status"] == "success" for r in report["results"]), 7)
        self.assertTrue((self.root / "context_01/TL/returned_payload.json").is_file())

    def test_tool_guard_failure_retains_raw_and_known_usage(self):
        self.prepare()
        self.failure = "tool"
        _, report = self.execute()
        self.assertEqual(report["status"], "incomplete")
        self.assertIn("prohibited tool", report["results"][0]["error"])
        self.assertEqual(report["token_usage"]["total_tokens"], 200)
        self.assertEqual(len(self.observed), 8)

    def test_transport_failure_is_not_retried_and_keeps_known_failed_usage(self):
        self.prepare()
        self.failure = "transport"
        _, report = self.execute()
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(len(self.observed), 8)
        self.assertEqual(report["token_usage"]["total_tokens"], 200)
        self.assertTrue((self.root / "context_01/TL/attempt1.json").is_file())

    def test_unknown_start_marker_never_becomes_zero_or_complete(self):
        self.prepare()
        self.failure = "unknown_start"
        _, report = self.execute()
        self.assertFalse(report["model_invocation_count_complete"])
        self.assertEqual(report["unknown_subprocess_starts"], ["context_01/TL"])
        self.assertIsNone(report["token_usage"]["total_tokens"])
        self.assertEqual(report["known_token_usage_subtotal"]["total_tokens"], 175)
        self.assertEqual(report["status"], "incomplete")

    def test_started_unknown_usage_is_incomplete(self):
        self.prepare()
        self.failure = "unknown_usage"
        _, report = self.execute()
        self.assertEqual(report["model_invocations"], 8)
        self.assertEqual(report["unknown_usage_attempts"], ["context_01/TL"])
        self.assertIsNone(report["token_usage"]["total_tokens"])
        self.assertEqual(report["status"], "incomplete")

    def test_worker_exception_with_unavailable_result_preserves_unknown_and_peers(self):
        self.prepare()
        real = D.run_one
        def crash(base, runtime, survey, spec, plan):
            if spec["call_id"] == "context_01/TL":
                raise RuntimeError("worker disappeared at unknown boundary")
            return real(base, runtime, survey, spec, plan)
        with mock.patch.object(D, "run_one", side_effect=crash):
            _, report = self.execute()
        self.assertEqual(len(report["results"]), 8)
        self.assertEqual(report["unknown_subprocess_starts"], ["context_01/TL"])
        self.assertEqual(report["known_token_usage_subtotal"]["total_tokens"], 175)

    def test_result_write_failure_cannot_discard_paid_peer_usage(self):
        self.prepare()
        write = HELPER.write
        def fail(path, value):
            if path == self.root / "context_01/TL/result.json":
                raise OSError("disk full on result")
            return write(path, value)
        with mock.patch.object(HELPER, "write", side_effect=fail):
            _, report = self.execute()
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual((len(self.observed), len(report["results"])), (8, 8))
        self.assertEqual(report["known_token_usage_subtotal"]["total_tokens"], 200)
        self.assertTrue(report["persistence_errors"])

    def test_final_manifest_write_failure_stdout_retains_all_results_and_usage(self):
        self.prepare()
        write = HELPER.write
        def fail(path, value):
            if path == self.root / "manifest.json" and value.get("status") in {"success", "incomplete"}:
                raise OSError("final manifest unavailable")
            return write(path, value)
        with mock.patch.object(HELPER, "write", side_effect=fail):
            _, report = self.execute()
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(len(report["results"]), 8)
        self.assertEqual(report["token_usage"]["total_tokens"], 200)

    def test_relaunch_rejected_even_if_manifest_reset_to_prepared(self):
        self.prepare()
        self.execute()
        manifest = D.read(self.root / "manifest.json")
        manifest["status"] = "prepared"
        HELPER.write(self.root / "manifest.json", manifest)
        with self.assertRaises(FileExistsError):
            self.execute()
        self.assertEqual(len(self.observed), 8)

    def test_image_or_source_snapshot_drift_blocks_before_calls(self):
        plan = self.prepare()
        Path(plan["calls"][0]["attachments"][0]).write_bytes(b"tampered")
        with self.assertRaises(RuntimeError):
            self.execute()
        self.assertFalse(self.observed)

    def test_plan_reordering_numeric_alias_and_wrong_cell_prompt_rejected(self):
        plan = self.prepare()
        for key, value in (("maximum_retries", False), ("max_workers", 1), ("timeout_sec", 900)):
            changed = copy.deepcopy(plan)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                D.validate_plan(changed, self.root)
        plan["calls"][0], plan["calls"][1] = plan["calls"][1], plan["calls"][0]
        with self.assertRaises(RuntimeError):
            D.validate_plan(plan, self.root)

    def test_real_frozen_prompt_and_geometry_interoperate_without_new_cell_gate(self):
        from PIL import Image
        project = Path(__file__).resolve().parents[1]
        for name in ("blind_pixel_survey.py", "spatial_cell_survey.py"):
            (self.workspace / "EECBench/scripts" / name).write_bytes((project / "scripts" / name).read_bytes())
        source_survey = load("spatial_fixture_view_builder", project / "scripts/blind_pixel_survey.py")
        for index in (1, 2):
            directory = self.source / f"context_{index:02d}"
            frames = []
            for frame in range(6):
                path = directory / f"original_{frame}.png"
                Image.new("RGB", (10, 6), (frame, 20, 30)).save(path)
                frames.append({"frame_id": frame, "path": str(path), "sha256": D.digest(path)})
            bundle = source_survey.build_views(frames, directory / "native_crops")
            bundle["candidate_payload"] = "FORBIDDEN_PRIVATE_CONTENT"
            bundle_path = directory / "view_bundle.json"
            HELPER.write(bundle_path, bundle)
            self.original["hashes"][str(bundle_path)] = D.digest(bundle_path)
            for path in bundle["attachments"]:
                self.original["hashes"][path] = D.digest(path)
            self.original["calls"][index - 1]["attachments"] = bundle["attachments"]
        HELPER.write(self.source / "manifest.json", self.original)
        def frozen_modules(root):
            directory = root / "frozen_workspace/EECBench/scripts"
            survey = load("actual_frozen_survey_for_spatial_test", directory / "blind_pixel_survey.py")
            with mock.patch.dict(sys.modules, {"blind_pixel_survey": survey}):
                spatial = load("actual_frozen_spatial_for_spatial_test", directory / "spatial_cell_survey.py")
            return self.runtime, survey, spatial
        D.load_runtime.side_effect = frozen_modules
        self.payload_override = {**copy.deepcopy(EMPTY), "regions": [{"region_id": "r0001", "frame_id": 0,
            "view_id": "frame_0_original", "visual_description": "Partially visible boundary.",
            "scope_kind": "part", "boundary_status": "partial", "bbox_xyxy": [0, 0, 2, 2]}],
            "tracks": [{"track_id": "t0001", "visual_description": "Provisional only.", "scope_kind": "part",
                        "frame_states": [{"frame_id": frame, "visibility": "visible" if frame == 0 else "uncertain",
                                          "region_ids": ["r0001"] if frame == 0 else [], "note": "Unresolved."}
                                         for frame in range(6)]}]}
        plan = self.prepare()
        code, report = self.execute()
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "success")
        for spec in plan["calls"]:
            self.assertNotIn("FORBIDDEN_PRIVATE_CONTENT", Path(spec["prompt"]).read_text())
            derived = D.read(Path(spec["directory"]) / "survey_derived.json")
            self.assertEqual(derived["regions"][0]["original_bbox_xyxy"], [0, 0, 2, 2])
            self.assertEqual(derived["regions"][0]["scope_kind"], "part")

    def test_frozen_shared_loader_rejects_cached_live_helper(self):
        # Exercise the actual loader, not this fixture's execute-time mock.
        fresh = load("spatial_loader_contract_test", DIRECTORY / "run_spatial_cell_survey_probe.py")
        with mock.patch.dict(sys.modules, {"run_frozen_batch": HELPER}), self.assertRaises(RuntimeError):
            fresh.load_shared(self.root)

    def test_frozen_runtime_loader_rejects_live_module_resolution(self):
        fresh = load("spatial_runtime_loader_contract_test", DIRECTORY / "run_spatial_cell_survey_probe.py")
        outside = SimpleNamespace(__file__=str(self.workspace / "EECBench/scripts/blind_pixel_survey.py"))
        before = list(sys.path)
        try:
            with mock.patch.object(fresh.importlib, "import_module", return_value=outside), self.assertRaises(RuntimeError):
                fresh.load_runtime(self.root)
        finally:
            sys.path[:] = before


if __name__ == "__main__":
    unittest.main()
