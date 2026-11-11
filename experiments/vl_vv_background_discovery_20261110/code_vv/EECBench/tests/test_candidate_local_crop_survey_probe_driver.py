"""Bounded crop sampling, source provenance and paid failure accounting; zero API calls."""

from contextlib import ExitStack, redirect_stdout
import copy
import hashlib
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
    spec.loader.exec_module(module)
    return module


D = load(
    "candidate_local_crop_driver_tested",
    DIRECTORY / "run_candidate_local_crop_survey_probe.py",
)
HELPER = load("candidate_crop_config_test", DIRECTORY / "run_frozen_batch.py")
with mock.patch.dict(sys.modules, {"run_frozen_batch": HELPER}):
    BASE = load(
        "candidate_crop_accounting_test", DIRECTORY / "run_blind_pixel_survey_probe.py"
    )
USAGE = dict(zip(BASE.TOKEN_KEYS, (20, 3, 5, 25)))
EMPTY = {
    "schema_version": "single_frame_pixel_survey_v0.1",
    "regions": [],
    "coverage_notes": "No completeness claim.",
}


class CandidateLocalCropSurveyDriverTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.workspace, self.root, self.source = (
            self.base / s for s in ("workspace", "output", "source")
        )
        schemas, scripts = (
            self.workspace / "EECBench/schemas",
            self.workspace / "EECBench/scripts",
        )
        schemas.mkdir(parents=True)
        scripts.mkdir()
        (schemas / D.SCHEMA_NAME).write_bytes(
            (PROJECT / "schemas" / D.SCHEMA_NAME).read_bytes()
        )
        for name in (
            "blind_pixel_survey.py",
            "single_frame_pixel_survey.py",
            "candidate_local_crop_survey.py",
        ):
            (scripts / name).write_bytes((PROJECT / "scripts" / name).read_bytes())
        (scripts / "ensemble_shot_entity_detection.py").write_text(
            "# mock transport only\n"
        )
        hashes = {}
        for relative in (
            "scripts/blind_pixel_survey.py",
            "scripts/single_frame_pixel_survey.py",
            "schemas/" + D.SCHEMA_NAME,
        ):
            path = self.source / "frozen_workspace/EECBench" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((self.workspace / "EECBench" / relative).read_bytes())
            hashes[str(path)] = D.digest(path)
        full = load("crop_fixture_full_source", scripts / "blind_pixel_survey.py")
        with mock.patch.dict(sys.modules, {"blind_pixel_survey": full}):
            self.source_survey = load(
                "crop_fixture_single_source", scripts / "single_frame_pixel_survey.py"
            )
        calls, results, contexts = {}, {}, []
        for index, (seed, shot) in enumerate(D.CONTEXTS, 1):
            chain = f"context_{index:02d}"
            directory = self.source / chain
            directory.mkdir(parents=True)
            frames = []
            for frame in D.ORDINALS:
                path = directory / f"original_{frame}.png"
                Image.new("RGB", (180, 120), (frame, index, 37)).save(path)
                frames.append(
                    {"frame_id": frame, "path": str(path), "sha256": D.digest(path)}
                )
            bundle = full.build_views(frames, directory / "crops")
            for path in bundle["attachments"]:
                hashes[path] = D.digest(path)
            contexts.append(
                {
                    "chain_id": chain,
                    "seed": seed,
                    "shot": shot,
                    "frame_ids": list(D.ORDINALS),
                }
            )
            for ordinal in D.ORDINALS:
                call_id = chain + f"/frame_{ordinal:02d}"
                cd = self.source / call_id
                cd.mkdir()
                fb = self.source_survey.build_frame_view_bundle(bundle, ordinal)
                raw = {
                    **EMPTY,
                    "regions": [
                        {
                            "region_id": "r0001",
                            "frame_id": ordinal,
                            "view_id": fb["views"][0]["view_id"],
                            "visual_description": "PRIVATE_CANDIDATE_NAME_DO_NOT_REVEAL",
                            "scope_kind": "whole",
                            "boundary_status": "clear",
                            "bbox_xyxy": [10, 12, 30, 42],
                        },
                        {
                            "region_id": "r0002",
                            "frame_id": ordinal,
                            "view_id": fb["views"][-1]["view_id"],
                            "visual_description": "PRIVATE_EXPECTED_CATEGORY_DO_NOT_REVEAL",
                            "scope_kind": "collection",
                            "boundary_status": "partial",
                            "bbox_xyxy": [2, 2, 22, 32],
                        },
                        {
                            "region_id": "r0003",
                            "frame_id": ordinal,
                            "view_id": fb["views"][0]["view_id"],
                            "visual_description": "Uncertain visible extent.",
                            "scope_kind": "unknown",
                            "boundary_status": "uncertain",
                            "bbox_xyxy": None,
                        },
                    ],
                }
                derived = self.source_survey.validate_survey(raw, fb)
                for filename, payload in (
                    ("view_bundle.json", fb),
                    ("attempt1.json", raw),
                    ("survey_derived.json", derived),
                ):
                    HELPER.write(cd / filename, payload)
                hashes[str(cd / "view_bundle.json")] = D.digest(cd / "view_bundle.json")
                result = {
                    "call_id": call_id,
                    "status": "success",
                    "subprocess_started": True,
                    "token_usage": USAGE,
                    "output_hashes": {
                        str(cd / n): D.digest(cd / n)
                        for n in ("attempt1.json", "survey_derived.json")
                    },
                }
                HELPER.write(cd / "result.json", result)
                (cd / "analyst_pixel_audit.json").write_text("FORBIDDEN_AUDIT_ANSWER")
                calls[call_id] = {
                    "call_id": call_id,
                    "chain_id": chain,
                    "seed": seed,
                    "shot": shot,
                    "frame_ordinal": ordinal,
                    "frame_id": ordinal,
                    "role": "survey",
                }
                results[call_id] = result
        order = [
            f"context_{index:02d}/frame_{ordinal:02d}"
            for ordinal in D.ORDINALS
            for index in (1, 2)
        ]
        self.original = {
            "protocol_version": "single_frame_survey_diagnostic_v0.1",
            "status": "success",
            "end_utc": "completed",
            "hashes": hashes,
            "contexts": contexts,
            "calls": [calls[k] for k in order],
            "results": [results[k] for k in order],
        }
        HELPER.write(self.source / "manifest.json", self.original)
        binary = self.base / "fake-codex"
        binary.write_text("#!/bin/sh\nexit 97\n")
        binary.chmod(0o755)
        evidence, controls = self.base / "offline.json", self.base / "controls.json"
        HELPER.write(evidence, {"mock_only": True})
        HELPER.write(
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
        admission_dir = self.base / "admission"
        admission_dir.mkdir()
        schema = admission_dir / D.SCHEMA_NAME
        schema.write_bytes((PROJECT / "schemas" / D.SCHEMA_NAME).read_bytes())
        attempt = {
            "role": "survey",
            "attempt": 1,
            "status": "success",
            "subprocess_started": True,
            "subprocess_start_unknown": False,
            "returncode": 0,
            "token_usage": USAGE.copy(),
        }
        HELPER.write(admission_dir / "result.json", attempt)
        HELPER.write(admission_dir / "attempt1.json", EMPTY)
        (admission_dir / "attempt1.events.jsonl").write_text(
            json.dumps({"type": "turn.completed", "usage": USAGE}) + "\n"
        )
        (admission_dir / "attempt1.stderr.log").write_text("")
        self.admission = {
            "status": "success",
            "hashes_unchanged": True,
            "maximum_invocations": 1,
            "model_invocations": 1,
            "maximum_retries": 0,
            "max_workers": 1,
            "images": [],
            "unknown_subprocess_starts": [],
            "unknown_usage_attempts": [],
            "persistence_errors": [],
            "end_utc": "completed",
            "model_config": {
                "model": D.MODEL,
                "reasoning_effort": "high",
                "context_config_overrides": [
                    "project_doc_max_bytes=0",
                    "skills.config=[]",
                ],
            },
            "cases": [
                {
                    "role": "survey",
                    "schema": str(schema),
                    "directory": str(admission_dir),
                    "expected": EMPTY,
                }
            ],
            "attempts": [attempt],
            "token_usage": USAGE.copy(),
            "known_token_usage_subtotal": USAGE.copy(),
            "hashes": {str(schema): D.digest(schema)},
            "output_hashes": {
                str(admission_dir / n): D.digest(admission_dir / n)
                for n in (
                    "attempt1.json",
                    "attempt1.events.jsonl",
                    "result.json",
                    "attempt1.stderr.log",
                )
            },
        }
        self.admission_path = admission_dir / "manifest.json"
        HELPER.write(self.admission_path, self.admission)
        self.args = SimpleNamespace(
            source_probe=self.source,
            output_root=self.root,
            codex_bin=str(binary),
            schema_admission=self.admission_path,
            observer_context_controls=controls,
            context_mode="none",
        )
        self.observed, self.peak, self.active, self.failure = [], 0, 0, None
        self.lock = threading.Lock()
        self.runtime = SimpleNamespace(
            run_codex_json=self.fake_call,
            _codex_attempt_accounting=self.accounting,
            validate_codex_schema_transport=lambda p: None,
            TOKEN_KEYS=BASE.TOKEN_KEYS,
            _attempt_usage_from_events=lambda p: json.loads(
                p.read_text().splitlines()[0]
            )["usage"],
        )
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.patches.enter_context(mock.patch.object(D, "WORKSPACE", self.workspace))
        self.patches.enter_context(
            mock.patch.object(D, "load_runtime", side_effect=self.frozen_runtime)
        )
        self.patches.enter_context(
            mock.patch.object(D, "load_shared", return_value=(HELPER, BASE))
        )

    def frozen_runtime(self, root):
        scripts = root / "frozen_workspace/EECBench/scripts"
        full = load(
            "candidate_crop_frozen_full_test", scripts / "blind_pixel_survey.py"
        )
        with mock.patch.dict(sys.modules, {"blind_pixel_survey": full}):
            single = load(
                "candidate_crop_frozen_single_test",
                scripts / "single_frame_pixel_survey.py",
            )
        with mock.patch.dict(sys.modules, {"single_frame_pixel_survey": single}):
            self.survey = load(
                "candidate_crop_frozen_local_test",
                scripts / "candidate_local_crop_survey.py",
            )
        return self.runtime, full, single, self.survey

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
        first = kwargs["output_path"].parent == self.root / "context_01/frame_00"
        with self.lock:
            self.observed.append(kwargs)
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            time.sleep(0.003)
            if self.failure == "unknown_start" and first:
                raise OSError("events write may fail after transport")
            events = (
                [{"type": "item.completed", "item": {"type": "command_execution"}}]
                if self.failure == "tool" and first
                else []
            )
            kwargs["events_path"].write_text("\n".join(json.dumps(x) for x in events))
            payload = copy.deepcopy(EMPTY)
            if self.failure == "schema" and first:
                payload.pop("regions")
            if (
                self.failure in ("local_geometry", "context_output", "valid_region")
                and first
            ):
                spec_bundle = D.read(kwargs["output_path"].parent / "view_bundle.json")
                view = spec_bundle["views"][0]
                payload["regions"] = [
                    {
                        "region_id": "r0001",
                        "frame_id": view["frame_id"],
                        "view_id": "view_0002"
                        if self.failure == "context_output"
                        else view["view_id"],
                        "visual_description": "Uncertain visible patch.",
                        "scope_kind": "unknown",
                        "boundary_status": "uncertain",
                        "bbox_xyxy": [
                            0,
                            0,
                            view["output_size"][0] + 1
                            if self.failure == "local_geometry"
                            else 4,
                            4,
                        ],
                    }
                ]
            HELPER.write(kwargs["output_path"], payload)
            if self.failure == "transport" and first:
                error = RuntimeError("HTTP 400")
                error.token_usage = USAGE.copy()
                raise error
            usage = None if self.failure == "unknown_usage" and first else USAGE.copy()
            return SimpleNamespace(
                payload=payload,
                token_usage=usage,
                runtime_seconds=0.1,
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

    def change_source(self, call_id, transform, *, refresh_derived=True):
        directory = self.source / call_id
        raw, bundle = (
            D.read(directory / "attempt1.json"),
            D.read(directory / "view_bundle.json"),
        )
        transform(raw)
        HELPER.write(directory / "attempt1.json", raw)
        if refresh_derived:
            HELPER.write(
                directory / "survey_derived.json",
                self.source_survey.validate_survey(raw, bundle),
            )
        result = next(r for r in self.original["results"] if r["call_id"] == call_id)
        result["output_hashes"] = {
            str(directory / n): D.digest(directory / n)
            for n in ("attempt1.json", "survey_derived.json")
        }
        HELPER.write(directory / "result.json", result)
        HELPER.write(self.source / "manifest.json", self.original)

    def test_prepare_preserves_full_catalog_exact_rank_source_mapping_and_blind_local_assets(
        self,
    ):
        plan = self.prepare()
        catalog = D.read(plan["candidate_catalog"])
        self.assertEqual(catalog["region_count"], 36)
        self.assertEqual(len(catalog["frames"]), 12)
        for frame, spec in zip(catalog["frames"], plan["calls"]):
            rows = frame["rows"]
            selected = next(r for r in rows if r["disposition"] == "selected")
            ranks = [
                (
                    hashlib.sha256(
                        json.dumps(
                            [104729, r["original_source_sha256"], r["region_id"]],
                            separators=(",", ":"),
                        ).encode()
                    ).hexdigest(),
                    r["catalog_index"],
                )
                for r in rows[:2]
            ]
            self.assertEqual(selected["catalog_index"], min(ranks)[1])
            self.assertEqual(rows[2]["disposition"], "null_geometry")
            self.assertEqual(spec["selected_catalog_index"], selected["catalog_index"])
            prompt = Path(spec["prompt"]).read_text()
            for hidden in (
                "PRIVATE_CANDIDATE",
                "PRIVATE_EXPECTED",
                "FORBIDDEN_AUDIT",
                str(self.source),
                "crop_origin",
                "source_size",
            ):
                self.assertNotIn(hidden, prompt)
            bundle = D.read(spec["view_bundle"])
            self.assertEqual(len(bundle["attachments"]), 1)
            with (
                Image.open(frame["copied_original"]) as original,
                Image.open(spec["attachments"][0]) as crop,
            ):
                expected = original.crop(frame["crop_geometry"]["actual_crop_xyxy"])
                self.assertEqual(crop.size, expected.size)
                self.assertEqual(crop.tobytes(), expected.tobytes())
            raw = D.read(frame["source_raw"])
            self.assertEqual(raw["regions"], [r["raw_observation"] for r in rows])
        self.assertEqual(
            catalog["frames"][0]["rows"][1]["original_bbox_xyxy"], [74, 50, 94, 80]
        )
        self.assertEqual(plan["selection_seed"], 104729)
        self.assertEqual(
            plan["actual_output_schema"]["sha256"], D.ADMITTED_SCHEMA_SHA256
        )
        self.assertEqual(plan["maximum_retries"], 0)
        self.assertFalse(self.observed)

    def test_context_prepare_preserves_selection_crop_bytes_and_appends_only_own_original(
        self,
    ):
        baseline = self.prepare()
        old_catalog = D.read(baseline["candidate_catalog"])
        self.assertEqual(baseline["context_mode"], "none")
        self.assertEqual(baseline["protocol_version"], D.PROTOCOL)
        self.args.context_mode = "same-frame-original"
        self.root = self.args.output_root = self.base / "with_context"
        plan = self.prepare()
        self.assertEqual(plan["protocol_version"], D.CONTEXT_PROTOCOL)
        self.assertEqual(Path(plan["protocol_source"]).name, D.CONTEXT_PROTOCOL_NAME)
        self.assertEqual(
            plan["view_protocol_version"], self.survey.CONTEXT_PROTOCOL_VERSION
        )
        catalog = D.read(plan["candidate_catalog"])
        self.assertEqual(catalog["region_count"], old_catalog["region_count"])
        for old, new, old_frame, new_frame in zip(
            baseline["calls"], plan["calls"], old_catalog["frames"], catalog["frames"]
        ):
            self.assertEqual(old_frame["rows"], new_frame["rows"])
            self.assertEqual(old_frame["crop_geometry"], new_frame["crop_geometry"])
            self.assertEqual(
                old["selected_catalog_index"], new["selected_catalog_index"]
            )
            self.assertEqual(
                Path(old["attachments"][0]).read_bytes(),
                Path(new["attachments"][0]).read_bytes(),
            )
            bundle = D.read(new["view_bundle"])
            self.assertEqual(
                new["attachments"],
                [new["directory"] + "/crop.png", new_frame["copied_original"]],
            )
            self.assertEqual(bundle["attachments"], new["attachments"])
            crop, context = bundle["views"]
            self.assertEqual(context, D.original_context_view(crop))
            self.assertEqual(
                Path(context["path"]).read_bytes(),
                Path(new_frame["original_view"]["path"]).read_bytes(),
            )
            self.assertEqual(D.digest(context["path"]), context["sha256"])
            prompt = Path(new["prompt"]).read_text()
            for hidden in (
                "PRIVATE_CANDIDATE",
                "PRIVATE_EXPECTED",
                "FORBIDDEN_AUDIT",
                str(self.source),
                "crop_origin",
                "source_size",
                "source_sha256",
                "original_bbox_xyxy",
            ):
                self.assertNotIn(hidden, prompt)
            public = json.loads(
                prompt.split("Safe view table (crop-local output only):\n", 1)[1]
            )
            self.assertEqual(
                set(public["context_original"]),
                {"attachment_index", "frame_id", "role", "view_id"},
            )
        self.assertFalse(self.observed)

    def test_context_plan_rejects_wrong_original_metadata_image_and_mode(self):
        self.args.context_mode = "same-frame-original"
        plan = self.prepare()
        spec = plan["calls"][0]
        path = Path(spec["view_bundle"])
        original_bundle = D.read(path)
        other = D.read(plan["calls"][1]["view_bundle"])["views"][1]
        changes = [
            ("path", other["path"]),
            ("source_path", other["source_path"]),
            ("sha256", "0" * 64),
            ("source_sha256", "0" * 64),
            ("source_size", [180, 121]),
            ("output_size", [180, 121]),
            ("crop_xyxy", [0, 0, 179, 120]),
            ("frame_id", 1),
            ("frame_id", False),
            ("kind", "original"),
            ("view_id", "view_0001"),
            ("attachment_index", 1),
            ("scale", 1.0),
        ]
        for key, value in changes:
            bundle = copy.deepcopy(original_bundle)
            bundle["views"][1][key] = value
            HELPER.write(path, bundle)
            with self.subTest(field=key, value=value), self.assertRaises(RuntimeError):
                D.validate_plan(plan, self.root, self.survey)
        for change in ("drop", "swap", "old_protocol"):
            bundle = copy.deepcopy(original_bundle)
            if change == "drop":
                bundle["views"].pop()
                bundle["attachments"].pop()
            elif change == "swap":
                bundle["views"].reverse()
                bundle["attachments"].reverse()
            else:
                bundle["protocol_version"] = self.survey.PROTOCOL_VERSION
            HELPER.write(path, bundle)
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                D.validate_plan(plan, self.root, self.survey)
        HELPER.write(path, original_bundle)
        for key, value in (
            ("context_mode", "none"),
            ("context_mode", "unknown"),
            ("protocol_version", D.PROTOCOL),
            ("protocol_source", str(self.root / "sources" / D.PROTOCOL_NAME)),
            ("view_protocol_version", self.survey.PROTOCOL_VERSION),
        ):
            changed = copy.deepcopy(plan)
            changed[key] = value
            with self.subTest(plan_field=key), self.assertRaises(RuntimeError):
                D.validate_plan(changed, self.root, self.survey)
        # Even equal frame IDs from another shot cannot establish source ownership.
        context_path = Path(original_bundle["views"][1]["path"])
        context_path.write_bytes(Path(other["path"]).read_bytes())
        with self.assertRaises(RuntimeError):
            D.validate_plan(plan, self.root, self.survey)
        self.assertFalse(self.observed)

    def test_context_execute_twelve_fresh_two_images_and_only_crop_coordinates(self):
        self.args.context_mode = "same-frame-original"
        self.failure = "valid_region"
        plan = self.prepare()
        code, report = self.execute()
        self.assertEqual(
            (code, report["status"], len(self.observed)), (0, "success", 12)
        )
        self.assertLessEqual(self.peak, 2)
        self.assertEqual(report["token_usage"]["total_tokens"], 300)
        for call in self.observed:
            self.assertEqual(len(call["attachments"]), 2)
            self.assertFalse(call["persistent"])
            self.assertEqual((call["model"], call["timeout_sec"]), (D.MODEL, 1800))
            self.assertEqual(D.digest(call["schema_path"]), D.ADMITTED_SCHEMA_SHA256)
        first = plan["calls"][0]
        raw = D.read(Path(first["directory"]) / "attempt1.json")
        derived = D.read(Path(first["directory"]) / "survey_derived.json")
        crop = D.read(first["view_bundle"])["views"][0]
        x, y = crop["crop_xyxy"][:2]
        self.assertEqual(raw["regions"][0]["view_id"], "view_0001")
        self.assertEqual(raw["regions"][0]["bbox_xyxy"], [0, 0, 4, 4])
        self.assertEqual(
            derived["regions"][0]["original_bbox_xyxy"], [x, y, x + 4, y + 4]
        )
        self.assertFalse(plan["binding_or_final_gates_applied"])

    def test_context_output_and_unknown_failures_keep_paid_peers_without_fallback(self):
        self.args.context_mode = "same-frame-original"
        for failure in (
            "context_output",
            "local_geometry",
            "unknown_start",
            "unknown_usage",
        ):
            with self.subTest(failure=failure):
                self.root = self.args.output_root = self.base / ("context_" + failure)
                self.observed, self.failure = [], failure
                self.prepare()
                code, report = self.execute()
                self.assertEqual((code, report["status"]), (1, "incomplete"))
                self.assertEqual((len(self.observed), len(report["results"])), (12, 12))
                self.assertTrue(
                    all(len(call["attachments"]) == 2 for call in self.observed)
                )
                if failure.startswith("unknown"):
                    self.assertTrue(
                        all(value is None for value in report["token_usage"].values())
                    )
                    self.assertEqual(
                        report["known_token_usage_subtotal"]["total_tokens"], 275
                    )
                else:
                    self.assertEqual(
                        report["known_token_usage_subtotal"]["total_tokens"], 300
                    )
                    self.assertTrue(
                        (self.root / "context_01/frame_00/attempt1.json").exists()
                    )
                    self.assertFalse(
                        (self.root / "context_01/frame_00/survey_derived.json").exists()
                    )

    def test_context_empty_slot_never_falls_back_to_original(self):
        def make_null(raw):
            for region in raw["regions"]:
                region["bbox_xyxy"] = None
                region["boundary_status"] = "uncertain"

        self.change_source("context_01/frame_00", make_null)
        self.args.context_mode = "same-frame-original"
        plan = self.prepare()
        first = plan["calls"][0]
        self.assertEqual(first["attachments"], [])
        self.assertIsNone(first["prompt"])
        self.assertIsNone(first["view_bundle"])
        code, report = self.execute()
        self.assertEqual(
            (code, report["status"], len(self.observed)), (0, "success", 11)
        )
        self.assertEqual(len(report["results"]), 12)
        self.assertEqual(report["token_usage"]["total_tokens"], 275)
        self.assertFalse(
            (self.root / "context_01/frame_00/attempt1.started.json").exists()
        )

    def test_context_execute_requires_explicit_frozen_mode_and_default_is_none(self):
        self.args.context_mode = "same-frame-original"
        self.prepare()
        self.args.context_mode = "none"
        with self.assertRaises(RuntimeError):
            self.execute()
        self.assertFalse((self.root / "execute_claim.json").exists())
        self.assertFalse(self.observed)
        with (
            mock.patch.object(
                sys,
                "argv",
                [
                    "driver",
                    "--source-probe",
                    "source",
                    "--output-root",
                    "out",
                    "--schema-admission",
                    "admission",
                    "--observer-context-controls",
                    "controls",
                ],
            ),
            mock.patch.object(D, "prepare") as prepare,
        ):
            self.assertEqual(D.main(), 0)
            self.assertEqual(prepare.call_args.args[0].context_mode, "none")

    def test_names_scope_kinds_and_input_row_order_do_not_change_rank_identity(self):
        p = self.source / "context_01/frame_00"
        raw, derived, bundle = (
            D.read(p / "attempt1.json"),
            D.read(p / "survey_derived.json"),
            D.read(p / "view_bundle.json"),
        )
        rows = D.catalog_rows(raw, derived, bundle["views"][0], "context_01/frame_00")
        raw["regions"].reverse()
        for r in raw["regions"]:
            r["visual_description"] = "ANOTHER CLASS"
            r["scope_kind"] = "unknown"
        mapped = self.source_survey.validate_survey(raw, bundle)
        other = D.catalog_rows(raw, mapped, bundle["views"][0], "context_01/frame_00")
        self.assertEqual(
            next(r["region_id"] for r in rows if r["disposition"] == "selected"),
            next(r["region_id"] for r in other if r["disposition"] == "selected"),
        )

    def test_null_only_frame_keeps_all_candidates_and_does_not_replace_or_call(self):
        def make_null(raw):
            for row in raw["regions"]:
                row.update(bbox_xyxy=None, boundary_status="uncertain")

        self.change_source("context_01/frame_00", make_null)
        plan = self.prepare()
        self.assertIsNone(plan["calls"][0]["selected_catalog_index"])
        _, report = self.execute()
        self.assertEqual(report["status"], "success")
        self.assertEqual(len(self.observed), 11)
        self.assertEqual(len(report["results"]), 12)
        self.assertEqual(report["results"][0]["reason"], "not_selected_no_geometry")
        self.assertEqual(report["known_token_usage_subtotal"]["total_tokens"], 275)
        self.assertFalse(
            (self.root / "context_01/frame_00/attempt1.started.json").exists()
        )

    def test_invalid_geometry_classification_is_not_source_provenance_amnesty(self):
        p = self.source / "context_01/frame_00"
        raw, derived, bundle = (
            D.read(p / "attempt1.json"),
            D.read(p / "survey_derived.json"),
            D.read(p / "view_bundle.json"),
        )
        derived["regions"][0]["original_bbox_xyxy"] = [0, 0, -1, 2]
        rows = D.catalog_rows(raw, derived, bundle["views"][0], "context_01/frame_00")
        self.assertEqual(rows[0]["disposition"], "invalid_geometry")
        HELPER.write(p / "survey_derived.json", derived)
        result = self.original["results"][0]
        result["output_hashes"][str(p / "survey_derived.json")] = D.digest(
            p / "survey_derived.json"
        )
        HELPER.write(p / "result.json", result)
        HELPER.write(self.source / "manifest.json", self.original)
        with self.assertRaisesRegex(RuntimeError, "source mapping"):
            self.prepare()
        self.assertFalse(self.observed)

    def test_large_integer_geometry_and_hash_tie_have_fixed_dispositions(self):
        p = self.source / "context_01/frame_00"
        raw, derived, bundle = (
            D.read(p / "attempt1.json"),
            D.read(p / "survey_derived.json"),
            D.read(p / "view_bundle.json"),
        )
        derived["regions"][0]["original_bbox_xyxy"] = [0, 0, 10**400, 4]
        rows = D.catalog_rows(raw, derived, bundle["views"][0], "context_01/frame_00")
        self.assertEqual(rows[0]["disposition"], "invalid_geometry")
        raw["regions"].reverse()
        derived = self.source_survey.validate_survey(raw, bundle)
        original_hash = hashlib.sha256

        def force_rank_tie(value):
            if value.startswith(b"[104729,"):
                return SimpleNamespace(hexdigest=lambda: "0" * 64)
            return original_hash(value)

        with mock.patch.object(D.hashlib, "sha256", side_effect=force_rank_tie):
            rows = D.catalog_rows(
                raw, derived, bundle["views"][0], "context_01/frame_00"
            )
        self.assertEqual(
            next(r["region_id"] for r in rows if r["disposition"] == "selected"),
            "r0001",
        )

    def test_full_frame_crop_records_no_localization_gain(self):
        def full_frame(raw):
            raw["regions"] = [raw["regions"][0]]
            raw["regions"][0]["bbox_xyxy"] = [0, 0, 180, 120]

        self.change_source("context_01/frame_00", full_frame)
        plan = self.prepare()
        catalog = D.read(plan["candidate_catalog"])
        self.assertIs(catalog["frames"][0]["no_localization_gain_full_frame"], True)
        catalog["frames"][0]["no_localization_gain_full_frame"] = False
        HELPER.write(Path(plan["candidate_catalog"]), catalog)
        with self.assertRaisesRegex(RuntimeError, "no localization gain"):
            D.validate_plan(plan, self.root, self.survey)

    def test_source_unknown_view_is_fatal_even_with_refreshed_hashes(self):
        self.change_source(
            "context_01/frame_00",
            lambda raw: raw["regions"][0].update(view_id="unknown"),
            refresh_derived=False,
        )
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertFalse(self.observed)

    def test_catalog_partial_duplicate_selection_seed_and_source_drift_rejected(self):
        plan = self.prepare()
        catalog_path = Path(plan["candidate_catalog"])
        original = D.read(catalog_path)
        for kind in ("partial", "duplicate", "selection", "source"):
            catalog = copy.deepcopy(original)
            if kind == "partial":
                catalog["frames"][0]["rows"].pop()
            elif kind == "duplicate":
                catalog["frames"][0]["rows"][1] = copy.deepcopy(
                    catalog["frames"][0]["rows"][0]
                )
            elif kind == "selection":
                next(
                    r
                    for r in catalog["frames"][0]["rows"]
                    if r["disposition"] == "not_selected"
                )["disposition"] = "selected"
            else:
                catalog["frames"][0]["original_view"]["source_sha256"] = "0" * 64
            HELPER.write(catalog_path, catalog)
            with self.subTest(kind=kind), self.assertRaises(RuntimeError):
                D.validate_plan(plan, self.root, self.survey)
        HELPER.write(catalog_path, original)
        for key, value in (
            ("selection_seed", 104730),
            ("maximum_retries", False),
            ("max_workers", 3),
            ("timeout_sec", 900),
        ):
            altered = copy.deepcopy(plan)
            altered[key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                D.validate_plan(altered, self.root, self.survey)

    def test_cross_frame_crop_and_full_image_fallback_rejected(self):
        plan = self.prepare()
        for field, value in (
            ("attachments", [plan["calls"][1]["attachments"][0]]),
            (
                "attachments",
                [D.read(plan["candidate_catalog"])["frames"][0]["copied_original"]],
            ),
            ("frame_id", True),
        ):
            altered = copy.deepcopy(plan)
            altered["calls"][0][field] = value
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                D.validate_plan(altered, self.root, self.survey)

    def test_twelve_fresh_calls_one_crop_max_two_high_no_tools_same_admitted_schema(
        self,
    ):
        plan = self.prepare()
        code, report = self.execute()
        self.assertEqual(
            (code, report["status"], len(self.observed)), (0, "success", 12)
        )
        self.assertLessEqual(self.peak, 2)
        self.assertEqual(report["token_usage"]["total_tokens"], 300)
        wrapper = Path(plan["model_config"]["codex_wrapper"]).read_text()
        self.assertIn("--disable shell_tool", wrapper)
        self.assertIn('model_reasoning_effort="high"', wrapper)
        for call in self.observed:
            self.assertEqual(len(call["attachments"]), 1)
            self.assertFalse(call["persistent"])
            self.assertEqual((call["model"], call["timeout_sec"]), (D.MODEL, 1800))
            self.assertEqual(D.digest(call["schema_path"]), D.ADMITTED_SCHEMA_SHA256)

    def test_schema_local_bounds_tool_and_transport_failures_retain_paid_peers(self):
        # Each subcase has an independently prepared fake directory, never a retried call.
        for failure in ("schema", "local_geometry", "tool", "transport"):
            with self.subTest(failure=failure):
                self.args.output_root = self.base / ("out_" + failure)
                self.root = self.args.output_root
                self.observed = []
                self.failure = failure
                self.prepare()
                _, report = self.execute()
                self.assertEqual(report["status"], "incomplete")
                self.assertEqual((len(self.observed), len(report["results"])), (12, 12))
                self.assertEqual(
                    report["known_token_usage_subtotal"]["total_tokens"], 300
                )
                self.assertTrue(
                    (self.root / "context_01/frame_00/attempt1.json").is_file()
                )

    def test_unknown_start_and_unknown_usage_never_report_zero_or_success(self):
        for failure in ("unknown_start", "unknown_usage"):
            with self.subTest(failure=failure):
                self.args.output_root = self.base / ("out_" + failure)
                self.root = self.args.output_root
                self.observed = []
                self.failure = failure
                self.prepare()
                _, report = self.execute()
                self.assertEqual(report["status"], "incomplete")
                self.assertIsNone(report["token_usage"]["total_tokens"])
                self.assertEqual(
                    report["known_token_usage_subtotal"]["total_tokens"], 275
                )
                key = (
                    "unknown_subprocess_starts"
                    if failure == "unknown_start"
                    else "unknown_usage_attempts"
                )
                self.assertEqual(report[key], ["context_01/frame_00"])

    def test_worker_exception_and_write_failures_preserve_all_slots_and_stdout(self):
        for failure in ("worker", "result", "manifest"):
            with self.subTest(failure=failure):
                self.args.output_root = self.base / ("out_" + failure)
                self.root = self.args.output_root
                self.observed = []
                self.prepare()
                real_run, real_write = D.run_one, HELPER.write

                def run(*args):
                    if (
                        failure == "worker"
                        and args[3]["call_id"] == "context_01/frame_00"
                    ):
                        raise RuntimeError("lost worker")
                    return real_run(*args)

                def write(path, value):
                    if (
                        failure == "result"
                        and path == self.root / "context_01/frame_00/result.json"
                    ):
                        raise OSError("disk full")
                    if (
                        failure == "manifest"
                        and path == self.root / "manifest.json"
                        and value.get("status") in {"success", "incomplete"}
                    ):
                        raise OSError("disk full on final manifest")
                    return real_write(path, value)

                with (
                    mock.patch.object(D, "run_one", side_effect=run),
                    mock.patch.object(HELPER, "write", side_effect=write),
                ):
                    _, report = self.execute()
                self.assertEqual(report["status"], "incomplete")
                self.assertEqual(len(report["results"]), 12)
                self.assertEqual(
                    report["known_token_usage_subtotal"]["total_tokens"],
                    275 if failure == "worker" else 300,
                )

    def test_relaunch_and_frozen_image_drift_stop_before_extra_calls(self):
        plan = self.prepare()
        image = Path(plan["calls"][0]["attachments"][0])
        before = image.read_bytes()
        image.write_bytes(b"changed")
        with self.assertRaises(RuntimeError):
            self.execute()
        self.assertFalse(self.observed)
        image.write_bytes(before)
        self.execute()
        manifest = D.read(self.root / "manifest.json")
        manifest["status"] = "prepared"
        HELPER.write(self.root / "manifest.json", manifest)
        with self.assertRaises(FileExistsError):
            self.execute()
        self.assertEqual(len(self.observed), 12)

    def test_admission_failure_or_context_mismatch_stops_before_crop_calls(self):
        for kind in ("failed", "context", "schema"):
            record = copy.deepcopy(self.admission)
            if kind == "failed":
                record["attempts"][0]["status"] = "failed"
            elif kind == "context":
                record["model_config"]["context_config_overrides"] = []
            else:
                record["hashes"][record["cases"][0]["schema"]] = "0" * 64
            HELPER.write(self.admission_path, record)
            self.args.output_root = self.base / ("out_" + kind)
            with self.subTest(kind=kind), self.assertRaises(RuntimeError):
                self.prepare()
        self.assertFalse(self.observed)

    def test_shared_loader_rejects_cached_live_configuration(self):
        fresh = load(
            "candidate_crop_frozen_loader_check",
            DIRECTORY / "run_candidate_local_crop_survey_probe.py",
        )
        with (
            mock.patch.dict(sys.modules, {"run_frozen_batch": HELPER}),
            self.assertRaises(RuntimeError),
        ):
            fresh.load_shared(self.root)


if __name__ == "__main__":
    unittest.main()
