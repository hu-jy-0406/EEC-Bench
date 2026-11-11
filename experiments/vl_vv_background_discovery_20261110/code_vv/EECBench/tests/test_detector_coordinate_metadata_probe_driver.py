"""Small fake-CLI tests; no model endpoint, production mutation, or real probe preparation."""

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


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


D = load(
    "coordinate_probe_tested", DIRECTORY / "run_detector_coordinate_metadata_probe.py"
)
C = load("coordinate_config_tested", DIRECTORY / "run_frozen_batch.py")
with mock.patch.dict(sys.modules, {"run_frozen_batch": C}):
    BASE = load("coordinate_base_tested", DIRECTORY / D.BASE_NAME)
M = load("coordinate_material_tested", DIRECTORY / D.MATERIAL_NAME)
USAGE = {
    "input_tokens": 20,
    "cached_input_tokens": 3,
    "output_tokens": 5,
    "total_tokens": 25,
}
SCHEMA = {
    "type": "object",
    "properties": {"entities": {"type": "array"}},
    "required": ["entities"],
    "additionalProperties": False,
}
FAKE_RUNTIME = """from pathlib import Path
import json
DETECTOR_SCHEMA = Path(__file__).resolve().parents[1] / 'schemas/codex_entity_detector_ledger_v0.8.schema.json'
DETECTOR_ROLES = [('detector_1', 'full_scan', 'Complete three passes.')]
def _detector_base_prompt(*, shot_id, shot_manifest, allowed_input_paths, detector_policy_text):
    return json.dumps(shot_manifest,sort_keys=True)+json.dumps(allowed_input_paths)+detector_policy_text
def _detector_prompt(base, role, instruction): return base+role+instruction
def validate_codex_schema_transport(path):
    assert Path(path)==DETECTOR_SCHEMA
def validate_ledger(payload, **context):
    if payload['entities']: raise ValueError('mock detector contract invalid')
    assert context['detector_id']=='detector_1' and context['source_kind']=='detector'
    assert len(context['valid_frame_ids'])==len(context['allowed_input_paths'])==6
    return {'covered':True}
"""


class CoordinateProbeTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.temp = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.stack.enter_context(mock.patch.dict(sys.modules))
        old_path = sys.path.copy()
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), old_path))
        for key in ("ensemble_shot_entity_detection", "run_frozen_batch"):
            sys.modules.pop(key, None)
        self.source = Path(self.temp) / D.SOURCE_NAME
        self.source.mkdir()
        self.root = Path(self.temp) / "new_probe"
        self.binary = Path(self.temp) / "codex-fake"
        self.binary.write_text("#!/bin/sh\nexit 88\n")
        self.binary.chmod(0o755)
        config, execution = C.freeze_codex_config(
            self.source, str(self.binary), D.MODEL, "high"
        )
        source_hashes = {}
        for relative, content in {
            M.ENSEMBLE_RELATIVE: FAKE_RUNTIME,
            "EECBench/scripts/extra_dependency.py": "# independent source dependency\n",
            M.POLICY_RELATIVE: "Complete neutral detector policy; no downstream material.",
            M.SCHEMA_RELATIVE: json.dumps(SCHEMA),
        }.items():
            path = self.source / "frozen_workspace" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            source_hashes[relative] = D.digest(path)
        input_hashes = {}
        shots = ["shot_c", "shot_a", "shot_b"]
        for shot in shots:
            bundle = self.source / "frozen_inputs" / shot / "input_bundle"
            bundle.mkdir(parents=True)
            refs = []
            for index in range(6):
                image = bundle / f"frame_{index:06d}.jpg"
                Image.new("RGB", (32 + index, 24), (index, 5, 9)).save(image)
                refs.append(
                    {
                        "attachment_index": index + 1,
                        "frame_id": index,
                        "timestamp_sec": float(index),
                        "path": str(image),
                        "sha256": D.digest(image),
                    }
                )
                input_hashes[f"{shot}/{image.name}"] = D.digest(image)
            for name, payload in [
                ("shot_manifest.json", {"shot_id": shot, "reference_frames": refs}),
                (
                    "prompt_bound_registry_semantic.json",
                    {"entities": ["FORBIDDEN_REGISTRY"]},
                ),
                ("prompt_bound_registry.json", {"unused_old_record": True}),
            ]:
                C.write(bundle / name, payload)
                if name != "prompt_bound_registry.json":
                    input_hashes[f"{shot}/{name}"] = D.digest(bundle / name)
        C.write(
            self.source / "robustness_manifest.json",
            {
                "model": D.MODEL,
                "reasoning_effort": "high",
                "model_config": config,
                "source_hashes": source_hashes,
                "execution_hashes": execution,
                "input_hashes": input_hashes,
                "shots": shots,
                "status": "running",
            },
        )
        evidence = Path(self.temp) / "offline.json"
        C.write(evidence, {"fake_offline_fixture": True})
        self.controls = Path(self.temp) / "controls.json"
        C.write(
            self.controls,
            {
                "version": "observer_process_context_controls_v0.1",
                "pinned_cli_sha256": D.digest(self.binary),
                "disabled_skill_paths": [],
                "project_doc_max_bytes": 0,
                "offline_evidence": {
                    "path": str(evidence),
                    "sha256": D.digest(evidence),
                },
            },
        )
        self.args = SimpleNamespace(
            source_batch=self.source,
            output_root=self.root,
            codex_bin=str(self.binary),
            observer_context_controls=self.controls,
            execute=False,
        )

    def prepared(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(D.prepare(self.args), 0)
        return D.read(self.root / "execution_plan.json")

    def runtime(self, *, error=None, entities=None, unknown=False):
        runtime = D.load_runtime(self.root)

        def invoke(**kwargs):
            runtime.last_kwargs = kwargs
            if error:
                raise error
            payload = {"entities": entities or []}
            C.write(kwargs["output_path"], payload)
            kwargs["events_path"].write_text(
                json.dumps({"type": "turn.completed", "usage": USAGE}) + "\n"
            )
            kwargs["stderr_path"].write_text("")
            return SimpleNamespace(
                payload=payload,
                token_usage=USAGE,
                runtime_seconds=0.01,
                thread_id="fake-fresh",
                returncode=0,
            )

        def accounting(invocation, error, events_path):
            return {
                "subprocess_started": True
                if invocation is not None
                else None
                if unknown
                else False,
                "token_usage": USAGE if invocation is not None else None,
                "runtime_seconds": 0.01,
                "thread_id": "fake-fresh" if invocation else None,
                "returncode": 0 if invocation else None,
            }

        runtime.run_codex_json = mock.Mock(side_effect=invoke)
        runtime._codex_attempt_accounting = accounting
        return runtime

    def test_prepare_freezes_original_template_pixels_and_only_metadata_difference(
        self,
    ):
        plan = self.prepared()
        self.assertEqual([c["shot_id"] for c in plan["contexts"]], ["shot_a", "shot_b"])
        self.assertEqual(
            [c["call_id"] for c in plan["calls"]],
            [
                "context_01_baseline",
                "context_01_metadata",
                "context_02_baseline",
                "context_02_metadata",
            ],
        )
        for context in plan["contexts"]:
            baseline, enriched = [
                Path(context["prompts"][arm]).read_text() for arm in D.ARMS
            ]
            self.assertEqual(
                enriched, M.build_prompt_pair(baseline, context["metadata"])["metadata"]
            )
            self.assertNotIn("FORBIDDEN_REGISTRY", enriched)
            self.assertNotIn("unused_old_record", enriched)
            for a, b in zip(context["attachments"], context["original_attachments"]):
                self.assertEqual(Path(a).read_bytes(), Path(b).read_bytes())
        self.assertFalse((self.root / "execute_claim.json").exists())
        self.assertFalse(list(self.root.glob("context_*/*/attempt1.started.json")))
        with self.assertRaises(FileExistsError):
            D.prepare(self.args)

    def test_input_failure_is_recorded_without_model_or_claim(self):
        path = self.source / "frozen_inputs/shot_a/input_bundle/frame_000000.jpg"
        path.write_bytes(b"bad")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(D.prepare(self.args), 1)
        failed = D.read(self.root / "preparation_failure.json")
        self.assertEqual(failed["status"], "input_failed")
        self.assertTrue(failed["no_invocation_attempted"])
        self.assertIsNone(failed["token_usage"])
        self.assertFalse((self.root / "execute_claim.json").exists())

    def test_running_source_status_is_not_a_lock(self):
        plan = self.prepared()
        path = self.source / "robustness_manifest.json"
        source = D.read(path)
        source.update(status="success", results=["unrelated downstream"])
        C.write(path, source)
        D.validate_plan(plan, self.root, M, D.load_runtime(self.root))

    def test_call_matrix_model_and_lock_drift_fail_before_launch(self):
        plan = self.prepared()
        for change in [
            lambda p: p.update(maximum_workers=True),
            lambda p: p["calls"][0].update(condition="metadata"),
            lambda p: p["calls"][0]["attachments"].reverse(),
            lambda p: p["model_config"].update(model="other"),
            lambda p: p["frozen_hashes"].pop(p["contexts"][0]["prompts"]["baseline"]),
        ]:
            bad = copy.deepcopy(plan)
            change(bad)
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                D.validate_plan(bad, self.root, M, D.load_runtime(self.root))

    def test_modified_baseline_and_added_arm_fields_rejected_even_with_new_hash(self):
        plan = self.prepared()
        path = Path(plan["contexts"][0]["prompts"]["baseline"])
        path.write_text(path.read_text() + "\nextra rule")
        plan["frozen_hashes"][str(path)] = D.digest(path)
        with self.assertRaisesRegex(RuntimeError, "prompt bytes"):
            D.validate_plan(plan, self.root, M, D.load_runtime(self.root))

    def test_dependency_clone_rehashed_in_plan_still_rejected(self):
        plan = self.prepared()
        path = self.root / "frozen_workspace/EECBench/scripts/extra_dependency.py"
        path.write_text("# changed dependency\n")
        plan["frozen_hashes"][str(path)] = D.digest(path)
        with self.assertRaisesRegex(RuntimeError, "dependency clone"):
            D.validate_plan(plan, self.root, M, D.load_runtime(self.root))

    def test_detector_success_runs_exact_schema_six_images_and_fresh_role(self):
        plan = self.prepared()
        runtime = self.runtime()
        spec = plan["calls"][0]
        result = D.run_one(BASE, runtime, spec, plan)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["token_usage"], USAGE)
        self.assertEqual(runtime.last_kwargs["model"], D.MODEL)
        self.assertEqual(runtime.last_kwargs["timeout_sec"], 1800)
        self.assertIs(runtime.last_kwargs["persistent"], False)
        self.assertNotIn("resume_thread_id", runtime.last_kwargs)
        self.assertEqual(
            list(map(str, runtime.last_kwargs["attachments"])), spec["attachments"]
        )
        self.assertEqual(str(runtime.last_kwargs["schema_path"]), spec["output_schema"])
        path = Path(spec["directory"]) / "detector_output_audit.json"
        self.assertTrue(D.read(path)["detector_contract_valid"])
        self.assertIn(str(path), result["output_hashes"])
        self.assertFalse((Path(spec["directory"]) / "survey_derived.json").exists())

    def test_paid_callback_failure_keeps_raw_native_and_usage(self):
        plan = self.prepared()
        runtime = self.runtime(entities=["invalid"])
        spec = plan["calls"][0]
        result = D.run_one(BASE, runtime, spec, plan)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["token_usage"], USAGE)
        self.assertTrue(result["subprocess_started"])
        self.assertTrue((Path(spec["directory"]) / "attempt1.json").exists())
        self.assertFalse(
            (Path(spec["directory"]) / "detector_output_audit.json").exists()
        )

    def test_actual_detector_schema_and_validator_require_complete_temporal_coverage(
        self,
    ):
        import jsonschema

        scripts = DIRECTORY.parents[2] / "scripts"
        sys.path.insert(0, str(scripts))
        real = load(
            "coordinate_actual_detector_runtime",
            scripts / "ensemble_shot_entity_detection.py",
        )
        frames = list(range(6))
        payload = {
            "protocol_version": real.PROTOCOL_VERSION,
            "shot_id": "synthetic_no_model",
            "detector_id": "detector_1",
            "source_kind": "detector",
            "accessed_input_paths": [],
            "entities": [],
            "warnings": [],
            "coverage_audit": {
                "reviewed_frame_ids": frames,
                "spatial_cells": [
                    {"cell": cell, "best_frame_id": 0, "represented_local_ids": []}
                    for cell in real.DETECTOR_SPATIAL_CELLS
                ],
                "content_strata": [
                    {"stratum": stratum, "represented_local_ids": []}
                    for stratum in real.DETECTOR_CONTENT_STRATA
                ],
                "temporal_reveal_checks": [
                    {
                        "earlier_frame_id": a,
                        "later_frame_id": b,
                        "newly_revealed_cells": [],
                        "added_local_ids": [],
                    }
                    for a, b in zip(frames, frames[1:])
                ],
                "residual_added_local_ids": [],
            },
        }
        context = {
            "shot_id": "synthetic_no_model",
            "valid_frame_ids": frames,
            "allowed_input_paths": [],
        }
        jsonschema.Draft202012Validator(D.read(real.DETECTOR_SCHEMA)).validate(payload)
        self.assertTrue(
            D.validate_detector(real, payload, context)["detector_contract_valid"]
        )
        payload["coverage_audit"]["temporal_reveal_checks"].pop()
        with self.assertRaisesRegex(real.EnsembleError, "adjacent"):
            D.validate_detector(real, payload, context)

    def test_paid_schema_failure_cannot_be_declared_detector_success(self):
        plan = self.prepared()
        runtime = self.runtime()
        spec = plan["calls"][0]

        def invalid(**kwargs):
            payload = {"entities": [], "extra": True}
            C.write(kwargs["output_path"], payload)
            kwargs["events_path"].write_text("{}\n")
            return SimpleNamespace(
                payload=payload,
                token_usage=USAGE,
                runtime_seconds=0.01,
                thread_id="fake",
            )

        runtime.run_codex_json.side_effect = invalid
        result = D.run_one(BASE, runtime, spec, plan)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["token_usage"], USAGE)

    def test_prestart_drift_is_known_no_invocation(self):
        plan = self.prepared()
        runtime = self.runtime()
        spec = plan["calls"][0]
        Path(spec["prompt"]).write_text("changed")
        result = D.run_one(BASE, runtime, spec, plan)
        runtime.run_codex_json.assert_not_called()
        self.assertFalse(result["subprocess_started"])
        self.assertFalse(result["subprocess_start_unknown"])
        self.assertIsNone(result["token_usage"])

    def test_unknown_start_cannot_be_counted_as_zero_complete(self):
        plan = self.prepared()
        runtime = self.runtime(error=OSError("post-start stream error"), unknown=True)
        row = D.run_one(BASE, runtime, plan["calls"][0], plan)
        summary = D.summarize(BASE, {"calls": plan["calls"][:1]}, [row], self.root)
        self.assertTrue(row["subprocess_start_unknown"])
        self.assertFalse(summary["model_invocation_count_complete"])
        self.assertTrue(all(v is None for v in summary["token_usage"].values()))

    def test_explicit_detector_spawn_failure_remains_known_not_started(self):
        class FakeCodexCallError(RuntimeError):
            subprocess_started = False

        plan = self.prepared()
        runtime = self.runtime(error=FakeCodexCallError("spawn failed"))
        runtime.CodexCallError = FakeCodexCallError
        row = D.run_one(BASE, runtime, plan["calls"][0], plan)
        summary = D.summarize(BASE, {"calls": plan["calls"][:1]}, [row], self.root)
        self.assertEqual(row["status"], "failed")
        self.assertTrue(row["request_marker_written"])
        self.assertFalse(row["subprocess_started"])
        self.assertFalse(row["subprocess_start_unknown"])
        self.assertEqual(summary["model_invocations"], 0)
        self.assertTrue(summary["model_invocation_count_complete"])
        self.assertIsNone(row["token_usage"])

    def test_known_usage_under_unknown_start_is_still_in_subtotal(self):
        plan = self.prepared()
        spec = plan["calls"][0]
        row = {
            "call_id": spec["call_id"],
            "attempt": 1,
            "subprocess_started": None,
            "subprocess_start_unknown": True,
            "token_usage": USAGE,
            "request_marker_written": True,
        }
        summary = D.summarize(BASE, {"calls": [spec]}, [row], self.root)
        self.assertEqual(summary["known_token_usage_subtotal"], USAGE)
        self.assertEqual(summary["model_invocations"], 0)
        self.assertFalse(summary["model_invocation_count_complete"])
        self.assertTrue(all(v is None for v in summary["token_usage"].values()))

    def execute_mock(self, *, worker=None, writer=None, iterator=None):
        plan = self.prepared()
        manifest = D.read(self.root / "manifest.json")
        count = {"active": 0, "peak": 0}
        guard = threading.Lock()

        def standard(base, runtime, spec, plan):
            with guard:
                count["active"] += 1
                count["peak"] = max(count["peak"], count["active"])
            time.sleep(0.003)
            with guard:
                count["active"] -= 1
            return {
                "call_id": spec["call_id"],
                "chain_id": spec["chain_id"],
                "role": "detector",
                "status": "success",
                "attempt": 1,
                "subprocess_started": True,
                "subprocess_start_unknown": False,
                "token_usage": USAGE,
                "request_marker_written": True,
            }

        config = SimpleNamespace(write=writer or C.write, utc=C.utc)
        with ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(D, "run_one", side_effect=worker or standard)
            )
            if iterator:
                stack.enter_context(
                    mock.patch.object(
                        D.concurrent.futures, "as_completed", side_effect=iterator
                    )
                )
            output = stack.enter_context(redirect_stdout(io.StringIO()))
            code = D.execute_calls(self.root, plan, manifest, config, BASE, object())
        return code, manifest, output.getvalue(), count

    def test_four_independent_slots_and_global_max_two(self):
        code, manifest, _, count = self.execute_mock()
        self.assertEqual(code, 0)
        self.assertEqual(len(manifest["results"]), 4)
        self.assertLessEqual(count["peak"], 2)
        self.assertEqual(manifest["token_usage"]["total_tokens"], 100)

    def test_paid_failed_peer_is_kept_with_all_other_slots(self):
        def worker(base, runtime, spec, plan):
            return {
                "call_id": spec["call_id"],
                "chain_id": spec["chain_id"],
                "role": "detector",
                "status": "failed" if spec["condition"] == "metadata" else "success",
                "attempt": 1,
                "subprocess_started": True,
                "subprocess_start_unknown": False,
                "token_usage": USAGE,
                "request_marker_written": True,
            }

        code, manifest, _, _ = self.execute_mock(worker=worker)
        self.assertEqual(code, 1)
        self.assertEqual(len(manifest["results"]), 4)
        self.assertEqual(manifest["token_usage"]["total_tokens"], 100)

    def test_iterator_failure_harvests_every_paid_future(self):
        def bad_iterator(pending):
            raise RuntimeError("iterator failure")

        code, manifest, _, _ = self.execute_mock(iterator=bad_iterator)
        self.assertEqual(code, 1)
        self.assertEqual(manifest["token_usage"]["total_tokens"], 100)
        self.assertEqual(len(manifest["results"]), 4)

    def test_result_write_failure_keeps_all_peers_and_stdout_accounting(self):
        def bad_write(path, payload):
            if Path(path).name == "result.json":
                raise OSError("disk error")
            C.write(path, payload)

        code, manifest, output, _ = self.execute_mock(writer=bad_write)
        self.assertEqual(code, 1)
        self.assertEqual(manifest["known_token_usage_subtotal"]["total_tokens"], 100)
        self.assertEqual(len(json.loads(output.splitlines()[-1])["results"]), 4)

    def test_final_manifest_failure_is_incomplete_and_stdout_keeps_totals(self):
        def bad_write(path, payload):
            if Path(path).name == "manifest.json" and payload.get("end_utc"):
                raise OSError("final disk error")
            C.write(path, payload)

        code, _, output, _ = self.execute_mock(writer=bad_write)
        final = json.loads(output.splitlines()[-1])
        self.assertEqual(code, 1)
        self.assertEqual(final["status"], "incomplete")
        self.assertEqual(final["token_usage"]["total_tokens"], 100)

    def test_final_stdout_failure_changes_exit_and_saved_status(self):
        plan = self.prepared()
        manifest = D.read(self.root / "manifest.json")

        def worker(base, runtime, spec, plan):
            return {
                "call_id": spec["call_id"],
                "role": "detector",
                "status": "success",
                "attempt": 1,
                "subprocess_started": True,
                "token_usage": USAGE,
            }

        calls = []

        def fail_final(*args, **kwargs):
            calls.append(args)
            if len(calls) == 5:
                raise OSError("stdout closed on final summary")

        with (
            mock.patch.object(D, "run_one", side_effect=worker),
            mock.patch("builtins.print", side_effect=fail_final),
        ):
            code = D.execute_calls(self.root, plan, manifest, C, BASE, object())
        saved = D.read(self.root / "manifest.json")
        self.assertEqual(code, 1)
        self.assertEqual(saved["status"], "incomplete")
        self.assertEqual(saved["known_token_usage_subtotal"]["total_tokens"], 100)
        self.assertEqual(saved["persistence_errors"][-1]["path"], "stdout")

    def test_lost_worker_is_unknown_and_cannot_erase_paid_peers(self):
        def worker(base, runtime, spec, plan):
            if spec["call_id"] == "context_01_baseline":
                raise SystemExit("lost worker")
            return {
                "call_id": spec["call_id"],
                "role": "detector",
                "status": "success",
                "attempt": 1,
                "subprocess_started": True,
                "token_usage": USAGE,
            }

        code, manifest, _, _ = self.execute_mock(worker=worker)
        self.assertEqual(code, 1)
        self.assertEqual(manifest["known_token_usage_subtotal"]["total_tokens"], 75)
        self.assertTrue(all(v is None for v in manifest["token_usage"].values()))
        self.assertEqual(len(manifest["results"]), 4)

    def test_missing_manifest_lock_rejected_before_claim(self):
        self.prepared()
        manifest = D.read(self.root / "manifest.json")
        manifest["hashes"].pop(str(self.root / "execution_plan.json"))
        C.write(self.root / "manifest.json", manifest)
        with self.assertRaises(RuntimeError):
            D.execute(self.args)
        self.assertFalse((self.root / "execute_claim.json").exists())

    def test_duplicate_execute_claim_never_submits_calls(self):
        self.prepared()
        (self.root / "execute_claim.json").write_text("{}")
        with (
            mock.patch.object(D, "execute_calls") as execute,
            self.assertRaises(FileExistsError),
        ):
            D.execute(self.args)
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
