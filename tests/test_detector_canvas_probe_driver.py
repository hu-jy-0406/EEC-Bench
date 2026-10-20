"""Synthetic PNGs and native mocks only; no real probe preparation or API."""
from contextlib import ExitStack, redirect_stdout
import copy
import io
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from PIL import Image

from test_detector_coordinate_metadata_probe_driver import C, USAGE, FAKE_RUNTIME, load

IT = Path(__file__).resolve().parents[1] / "experiments/study_inconsistent_2/entity_discovery_iterations"
D = load("canvas_probe_tested", IT / "run_detector_canvas_probe.py")


class CanvasProbeTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.tmp = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(mock.patch.dict(sys.modules))
        old_path = sys.path.copy()
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), old_path))
        for key in ("ensemble_shot_entity_detection", "run_frozen_batch", "image_canvas_coordinates"):
            sys.modules.pop(key, None)
        self.package = self.tmp / D.PACKAGE_NAME
        self.package.mkdir()
        self.root = self.tmp / "new_canvas"
        self.binary = self.tmp / "codex-fake"
        self.binary.write_text("#!/bin/sh\nexit 88\n")
        self.binary.chmod(0o755)
        fake_runtime = FAKE_RUNTIME.replace("if payload['entities']: raise ValueError('mock detector contract invalid')",
                                           "if payload.get('invalid'): raise ValueError('mock detector contract invalid')")
        schema = {"type": "object", "properties": {"entities": {"type": "array"},
                  **{k: {"type": "string"} for k in ("protocol_version", "shot_id", "source_kind", "detector_id")}},
                  "required": ["entities"], "additionalProperties": False}
        for relative, content in {
            D.RUNTIME_RELATIVE: fake_runtime, D.SCHEMA_RELATIVE: D.canonical(schema),
            D.POLICY_RELATIVE: "Neutral complete frozen detector-only policy.",
            D.CONFIG_RELATIVE: (IT / "run_frozen_batch.py").read_text(),
            "EECBench/scripts/independent_dep.py": "# frozen dependency\n",
        }.items():
            path = self.package / "source_workspace" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        lineage = []
        for shot in ("shot_c", "shot_a", "shot_b"):
            bundle = self.package / "frozen_inputs" / shot / "input_bundle"
            bundle.mkdir(parents=True)
            refs = []
            for i in range(6):
                path = bundle / f"frame_{i:06d}.jpg"
                Image.new("RGB", (5 + i, 3), (i, 50, 90)).save(path)
                refs.append({"attachment_index": i + 1, "frame_id": i, "timestamp_sec": i / 3,
                             "path": str(self.tmp / "DO_NOT_READ_STALE" / shot / path.name),
                             "sha256": D.digest(path)})
            C.write(bundle / "shot_manifest.json", {"shot_id": shot, "reference_frames": refs})
            C.write(bundle / "prompt_bound_registry.json", {"secret": "FORBIDDEN_REGISTRY"})
            C.write(bundle / "prompt_bound_registry_semantic.json", {"secret": "FORBIDDEN_ANSWER"})
            for path in bundle.iterdir():
                lineage.append({"relative_path": str(path.relative_to(self.package / "frozen_inputs")),
                                "copy_path": str(path), "copy_sha256": D.digest(path),
                                "original_sha256": D.digest(path),
                                "original_path": str(self.tmp / "DO_NOT_READ_STALE" / shot / path.name)})
        self.manifest = {"source_hashes": D.tree_hashes(self.package / "source_workspace"),
                         "input_hashes": D.tree_hashes(self.package / "frozen_inputs"), "inputs": lineage,
                         "codex": {"path": str(self.binary), "sha256": D.digest(self.binary)}}
        self.save_package()
        evidence = self.tmp / "offline.json"
        C.write(evidence, {"synthetic_context_evidence": True})
        self.controls = self.tmp / "controls.json"
        C.write(self.controls, {"version": "observer_process_context_controls_v0.1",
                               "pinned_cli_sha256": D.digest(self.binary), "disabled_skill_paths": [],
                               "project_doc_max_bytes": 0,
                               "offline_evidence": {"path": str(evidence), "sha256": D.digest(evidence)}})
        self.args = SimpleNamespace(source_package=self.package, output_root=self.root,
                                    codex_bin=str(self.binary), observer_context_controls=self.controls)

    def save_package(self):
        C.write(self.package / "package_manifest.json", self.manifest)
        C.write(self.package / "source_sha256.json", self.manifest["source_hashes"])
        C.write(self.package / "input_sha256.json", self.manifest["input_hashes"])

    def prepared(self):
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(D.prepare(self.args), 0, output.getvalue())
        self.plan = D.read(self.root / "execution_plan.json")
        self.configuration, self.base, self.helper, self.geometry = D.frozen_modules(self.root)
        self.runtime = D.D.load_runtime(self.root)
        return self.plan

    def validate(self, plan):
        D.validate_plan(plan, self.root, self.runtime, self.helper, self.geometry)

    def test_all_three_shots_six_calls_rgb_and_prompt_template(self):
        p = self.prepared()
        self.assertEqual(len(p["calls"]), 6)
        self.assertEqual([c["shot_id"] for c in p["contexts"]],
                         [s for s in ("shot_a", "shot_b", "shot_c") for _ in range(2)])
        for spec, context in zip(p["calls"], p["contexts"]):
            self.assertEqual(list(Path(spec["directory"]).joinpath("workdir").iterdir()), [])
            self.assertEqual(spec["attachments"], [f["view_path"] for f in context["frames"]])
            prompt = Path(spec["prompt"]).read_text()
            self.assertNotIn("FORBIDDEN", prompt)
            self.assertNotIn("DO_NOT_READ_STALE", prompt)
            self.assertNotIn("decoded_rgb_sha256", prompt)
            self.assertEqual(self.helper.build_geometry_metadata(context),
                             self.helper.build_geometry_metadata(D.read(spec["geometry_context"])))
        self.assertFalse((self.root / "execute_claim.json").exists())
        self.assertEqual(len(list(self.root.glob("context_*/*/images/*.png"))), 36)
        with self.assertRaises(FileExistsError):
            D.prepare(self.args)

    def test_bad_source_hash_or_symlink_fails_before_any_invocation(self):
        path = self.package / "frozen_inputs/shot_a/input_bundle/frame_000000.jpg"
        path.unlink()
        path.symlink_to(self.package / "frozen_inputs/shot_b/input_bundle/frame_000000.jpg")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(D.prepare(self.args), 1)
        failed = D.read(self.root / "preparation_failure.json")
        self.assertTrue(failed["no_invocation_attempted"])
        self.assertFalse(failed["subprocess_started"])
        self.assertFalse(list(self.root.glob("context_*/*/attempt1*")))

    def test_stale_path_substitution_rejected_even_with_updated_source_hash(self):
        m = D.read(self.package / "frozen_inputs/shot_a/input_bundle/shot_manifest.json")
        m["reference_frames"][0]["path"] = m["reference_frames"][1]["path"]
        path = self.package / "frozen_inputs/shot_a/input_bundle/shot_manifest.json"
        C.write(path, m)
        relative = str(path.relative_to(self.package / "frozen_inputs"))
        self.manifest["input_hashes"][relative] = D.digest(path)
        row = next(r for r in self.manifest["inputs"] if r["relative_path"] == relative)
        row.update(copy_sha256=D.digest(path), original_sha256=D.digest(path))
        self.save_package()
        with self.assertRaisesRegex(ValueError, "association"):
            D.capture_package(self.package)

    def test_matrix_model_missing_locks_and_rehashed_prompt_rejected(self):
        p = self.prepared()
        for mutation in (
            lambda x: x.update(maximum_calls=4),
            lambda x: x.update(maximum_workers=True),
            lambda x: x["calls"][0].update(resume_thread_id="old"),
            lambda x: x["calls"][0]["attachments"].reverse(),
            lambda x: x["frozen_hashes"].pop(x["calls"][0]["prompt"]),
            lambda x: x["model_config"].update(model="other"),
        ):
            bad = copy.deepcopy(p)
            mutation(bad)
            with self.subTest(mutation=mutation), self.assertRaises((ValueError, RuntimeError)):
                self.validate(bad)
        path = Path(p["calls"][0]["prompt"])
        path.write_text(path.read_text() + "\nextra instruction")
        p["frozen_hashes"][str(path)] = D.digest(path)
        with self.assertRaisesRegex(ValueError, "Prompt"):
            self.validate(p)

    def test_rehashed_padding_and_forged_publication_fail(self):
        p = self.prepared()
        path = Path(p["calls"][1]["attachments"][0])
        publication = path.with_suffix(".publication.json")
        original = publication.read_bytes()
        value = D.read(publication)
        value["source"]["encoded_sha256"] = "0" * 64
        C.write(publication, value)
        p["frozen_hashes"][str(publication)] = D.digest(publication)
        with self.assertRaisesRegex(ValueError, "publication"):
            self.validate(p)
        publication.write_bytes(original)
        p["frozen_hashes"][str(publication)] = D.digest(publication)
        image = D.rgb_snapshot(path)
        image.putpixel((0, 0), (1, 2, 3))
        image.save(path)
        p["frozen_hashes"][str(path)] = D.digest(path)
        with self.assertRaisesRegex(ValueError, "padding"):
            self.validate(p)

    def native_mock(self, *, fail_index=None, unknown_index=None, padding=False):
        guard, active = threading.Lock(), {"now": 0, "peak": 0, "calls": []}

        def invoke(**kwargs):
            with guard:
                index = self.plan["calls"].index(next(s for s in self.plan["calls"]
                                                    if Path(s["directory"]) == kwargs["output_path"].parent))
                active["now"] += 1
                active["peak"] = max(active["peak"], active["now"])
                active["calls"].append(kwargs)
            time.sleep(.004)
            with guard:
                active["now"] -= 1
            if index == unknown_index:
                raise OSError("unknown native start")
            spec = self.plan["calls"][index]
            context = D.read(spec["context"])
            entities = [{"local_id": "p1", "frame_presence": [
                {"frame_id": f, "status": "visible", "description": "bounded synthetic region",
                 "bbox_xyxy_normalized": [0, 0, 1, 1]}
                for f in context["valid_frame_ids"]]}] if padding else []
            payload = {"entities": entities, "protocol_version": "single_shot_inventory_first_boxed_granularity_v0.5",
                       "source_kind": "detector", "detector_id": "detector_1", "shot_id": context["shot_id"]}
            if index == fail_index:
                payload["extra_schema_field"] = True
            C.write(kwargs["output_path"], payload)
            kwargs["events_path"].write_text(D.canonical({"type": "turn.completed", "usage": USAGE}) + "\n")
            kwargs["stderr_path"].write_text("native stderr retained\n")
            return SimpleNamespace(payload=payload, token_usage=USAGE, runtime_seconds=.01,
                                   thread_id=f"fresh-{index}", returncode=0)

        def accounting(invocation, error, events_path):
            return {"subprocess_started": True if invocation else None,
                    "token_usage": USAGE if invocation else None, "runtime_seconds": .01,
                    "thread_id": invocation.thread_id if invocation else None,
                    "returncode": 0 if invocation else None}

        self.runtime.run_codex_json = mock.Mock(side_effect=invoke)
        self.runtime._codex_attempt_accounting = accounting
        return active

    def run_calls(self, **kwargs):
        self.prepared()
        active = self.native_mock(**kwargs)
        manifest = D.read(self.root / "manifest.json")
        with redirect_stdout(io.StringIO()):
            code = D.D.execute_calls(self.root, self.plan, manifest, self.configuration, self.base, self.runtime)
            final = D.finalize(self.root, self.plan, manifest, self.configuration, self.helper)
        return code, final, manifest, active

    def test_six_actual_mock_calls_max_two_no_retry_raw_and_padding_rows(self):
        code, final, manifest, active = self.run_calls(padding=True)
        self.assertEqual((code, final), (0, 0))
        self.assertEqual(len(active["calls"]), 6)
        self.assertLessEqual(active["peak"], 2)
        self.assertEqual(manifest["token_usage"]["total_tokens"], 150)
        for kwargs in active["calls"]:
            self.assertEqual(kwargs["model"], "gpt-5.6-sol")
            self.assertEqual(kwargs["timeout_sec"], 1800)
            self.assertIs(kwargs["persistent"], False)
            self.assertNotIn("resume_thread_id", kwargs)
        for spec in self.plan["calls"]:
            path = Path(spec["directory"]) / "canonical_coordinate_audit.json"
            audit = D.read(path)
            self.assertEqual(audit["entity_count"], 1)
            self.assertEqual(audit["frame_row_count"], 6)
            counts = audit["mapping_status_counts"]
            self.assertGreater(counts["error"] if spec["condition"] == "v02" else counts["mapped"], 0)
            self.assertEqual(D.read(Path(spec["directory"]) / "attempt1.json")["entities"][0]
                             ["frame_presence"][0]["bbox_xyxy_normalized"], [0, 0, 1, 1])
        locked = D.read(self.root / "coordinate_derivation_audit.json")["hashes"]
        self.assertEqual(sum(p.endswith(".stderr.log") for p in locked), 6)
        self.assertEqual(sum(p.endswith(".started.json") for p in locked), 6)

    def test_paid_failure_and_unknown_preserve_all_slots_and_subtotal(self):
        code, final, manifest, active = self.run_calls(fail_index=1, unknown_index=3)
        self.assertEqual((code, final), (1, 1))
        self.assertEqual(len(active["calls"]), 6)
        self.assertEqual(len(manifest["results"]), 6)
        self.assertEqual(manifest["known_token_usage_subtotal"]["total_tokens"], 125)
        self.assertTrue(all(v is None for v in manifest["token_usage"].values()))
        failed = next(r for r in manifest["results"] if r["call_id"] == "context_01_v02")
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["token_usage"], USAGE)

    def test_finalizer_io_failure_retains_paid_totals_and_raw_results(self):
        self.prepared()
        self.native_mock()
        manifest = D.read(self.root / "manifest.json")
        with redirect_stdout(io.StringIO()):
            D.D.execute_calls(self.root, self.plan, manifest, self.configuration, self.base, self.runtime)
            before = copy.deepcopy(manifest["results"])
            with mock.patch.object(self.configuration, "write", side_effect=OSError("disk unavailable")):
                code = D.finalize(self.root, self.plan, manifest, self.configuration, self.helper)
        self.assertEqual(code, 1)
        self.assertEqual(manifest["results"], before)
        self.assertEqual(manifest["token_usage"]["total_tokens"], 150)

    def test_scheduler_iterator_failure_harvests_six_paid_futures(self):
        self.prepared()
        active = self.native_mock()
        manifest = D.read(self.root / "manifest.json")
        with redirect_stdout(io.StringIO()), mock.patch.object(D.D.concurrent.futures, "as_completed",
                                                              side_effect=RuntimeError("iterator failure")):
            code = D.D.execute_calls(self.root, self.plan, manifest, self.configuration, self.base, self.runtime)
        self.assertEqual(code, 1)
        self.assertEqual(len(active["calls"]), 6)
        self.assertEqual(len(manifest["results"]), 6)
        self.assertEqual(manifest["token_usage"]["total_tokens"], 150)

    def test_rehashed_wrapper_cannot_remove_process_controls(self):
        p = self.prepared()
        wrapper = self.root / "execution_config/codex.sh"
        wrapper.write_text('#!/bin/sh\nexec ' + str(self.binary) + ' "$@"\n')
        p["frozen_hashes"][str(wrapper)] = D.digest(wrapper)
        with self.assertRaisesRegex(ValueError, "configuration"):
            self.validate(p)

    def test_actual_execute_claim_identity_and_no_relaunch(self):
        self.prepared()
        active = self.native_mock()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(D.execute(self.args), 0)
        identity = D.read(self.root / "driver_identity.json")
        self.assertGreater(identity["start_ticks"], 0)
        self.assertTrue(identity["argv"])
        self.assertTrue(identity["cgroup"])
        self.assertEqual(len(active["calls"]), 6)
        with self.assertRaisesRegex(ValueError, "never-started"):
            D.execute(self.args)
        self.assertEqual(len(active["calls"]), 6)


if __name__ == "__main__":
    unittest.main()
