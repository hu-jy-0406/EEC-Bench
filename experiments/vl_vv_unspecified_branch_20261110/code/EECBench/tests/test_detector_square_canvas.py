"""Synthetic detector-v0.8 payloads and geometry only; no images or models."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ensemble_shot_entity_detection as runtime  # noqa: E402
import image_canvas_coordinates as coordinates  # noqa: E402

PATH = ROOT / "experiments/study_inconsistent_2/entity_discovery_iterations/detector_square_canvas.py"
SPEC = importlib.util.spec_from_file_location("detector_square_canvas_test_helper", PATH)
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M
SPEC.loader.exec_module(M)


def context(kind="reference_png"):
    frames = []
    for index, size in enumerate([[5, 3], [3, 5], [4, 4], [7, 3], [3, 7], [1, 1]], 1):
        g = coordinates.canvas_geometry(size)
        frames.append({"attachment_index": index, "frame_id": (index - 1) * 3,
                       "view_path": f"/neutral/view_000{index}.png", "source_size": size,
                       "view_size": size.copy() if kind == "reference_png" else g["canvas_size"],
                       "content_rect_xyxy": [0, 0, *size] if kind == "reference_png"
                       else g["content_rect_xyxy"],
                       "geometry": None if kind == "reference_png" else g})
    return {"shot_id": "synthetic_shot", "view_kind": kind, "frames": frames}


def ledger(ctx):
    ids = [f["frame_id"] for f in ctx["frames"]]
    boxes = [[0.2, 0.2, 0.8, 0.8]] * len(ids)
    if ctx["view_kind"] == "square_canvas":
        boxes = [coordinates.source_to_canvas_bbox(b, f["geometry"])
                 for b, f in zip(boxes, ctx["frames"])]
    entity = {"local_id": "e001", "proposed_name": "bounded shape", "canonical_head": "shape",
              "entity_type": "object", "granularity": "whole_object", "attributes": [],
              "evidence_frame_ids": ids[:-1],
              "coarse_locators": [{"frame_id": ids[0], "description": "Visible bounded shape."}],
              "frame_presence": [{"frame_id": fid, "status": "visible" if i < 5 else "uncertain",
                                  "description": "Visible boundary." if i < 5 else "Uncertain geometry.",
                                  "bbox_xyxy_normalized": deepcopy(boxes[i]) if i < 5 else None}
                                 for i, fid in enumerate(ids)],
              "self_confidence": 0.5, "uncertainty_flags": ["limited_detail"]}
    return {"protocol_version": M.RAW_PROTOCOL_VERSION, "shot_id": ctx["shot_id"],
            "detector_id": "detector_1", "source_kind": "detector",
            "accessed_input_paths": [f["view_path"] for f in ctx["frames"]], "entities": [entity],
            "coverage_audit": {"reviewed_frame_ids": ids,
                               "spatial_cells": [{"cell": c, "best_frame_id": ids[0],
                                                  "represented_local_ids": ["e001"]}
                                                 for c in runtime.DETECTOR_SPATIAL_CELLS],
                               "content_strata": [{"stratum": c, "represented_local_ids": ["e001"]}
                                                   for c in runtime.DETECTOR_CONTENT_STRATA],
                               "temporal_reveal_checks": [{"earlier_frame_id": a, "later_frame_id": b,
                                                           "newly_revealed_cells": [], "added_local_ids": []}
                                                          for a, b in zip(ids, ids[1:])],
                               "residual_added_local_ids": []}, "warnings": ["Not identity proof."]}


class DetectorSquareCanvasTests(unittest.TestCase):
    def test_actual_v08_schema_and_validator_before_both_arm_maps(self):
        schema = json.loads(runtime.DETECTOR_SCHEMA.read_text())
        self.assertEqual(runtime.DETECTOR_SCHEMA.name, M.SCHEMA_NAME)
        for kind in M.VIEW_KINDS:
            ctx = context(kind)
            raw = ledger(ctx)
            with self.subTest(kind=kind):
                jsonschema.validate(raw, schema)
                runtime.validate_ledger(raw, shot_id=ctx["shot_id"], detector_id="detector_1",
                                        source_kind="detector",
                                        valid_frame_ids=[f["frame_id"] for f in ctx["frames"]],
                                        allowed_input_paths=[f["view_path"] for f in ctx["frames"]])
                before = deepcopy((raw, ctx))
                result = M.map_detector_output(raw, ctx)
                self.assertEqual(result["mapping_status_counts"], {"mapped": 5, "null": 1, "error": 0})
                self.assertEqual(result["entity_count"], 1)
                self.assertEqual(result["frame_row_count"], 6)
                self.assertEqual((raw, ctx), before)
                self.assertFalse(result["full_detector_validation_performed"])
                self.assertFalse(result["asset_authentication_performed"])
                for row in result["entities"][0]["frame_mappings"][:5]:
                    for actual, expected in zip(row["source_bbox_xyxy_normalized"], [0.2, 0.2, 0.8, 0.8]):
                        self.assertAlmostEqual(actual, expected, places=14)

    def test_shared_prompt_whitelist_and_exact_base_prefix(self):
        base = "Complete frozen D1 policy\r\nUTF8 α 中文\n"
        prompts = []
        for kind in M.VIEW_KINDS:
            ctx = context(kind)
            ctx.update(old_claims="DO_NOT_EXPOSE", another_shot="DO_NOT_EXPOSE")
            ctx["frames"][0].update(expected_object="DO_NOT_EXPOSE", source_path="/PRIVATE")
            prompt = M.build_detector_prompt(base, ctx)
            self.assertTrue(prompt.encode().startswith(base.encode()))
            suffix = prompt[len(base):]
            public = json.loads(suffix[len(M.GEOMETRY_INSTRUCTIONS):])
            self.assertEqual(public, M.build_geometry_metadata(ctx))
            self.assertEqual(set(public[0]), {"attachment_index", "frame_id", "path", "width", "height",
                                             "content_rect_xyxy"})
            for private in ["view_kind", "source_size", "offset_xy", "geometry_policy_version",
                            "DO_NOT_EXPOSE", "/PRIVATE", "reference_png", "square_canvas"]:
                self.assertNotIn(private, suffix)
            self.assertIn("entire supplied attachment", suffix)
            self.assertIn("padding, not scene content", suffix)
            prompts.append(suffix[:len(M.GEOMETRY_INSTRUCTIONS)])
        self.assertEqual(prompts[0], prompts[1])

    def test_reference_identity_null_and_raw_order_are_preserved(self):
        ctx = context()
        raw = ledger(ctx)
        raw["entities"][0]["frame_presence"][0]["bbox_xyxy_normalized"] = [0, 0, 1e-300, 1e-300]
        raw["entities"][0]["frame_presence"].reverse()
        before = deepcopy(raw)
        result = M.map_detector_output(raw, ctx)
        entity = result["entities"][0]
        self.assertEqual(entity["local_id"], raw["entities"][0]["local_id"])
        for i, row in enumerate(entity["frame_mappings"]):
            original = raw["entities"][0]["frame_presence"][i]
            self.assertEqual(row["raw_frame_presence"], original)
            self.assertEqual(row["original_bbox_xyxy_normalized"], original["bbox_xyxy_normalized"])
            self.assertEqual(row["source_bbox_xyxy_normalized"], original["bbox_xyxy_normalized"])
            self.assertEqual(row["raw_json_pointer"], f"/entities/0/frame_presence/{i}")
        self.assertEqual(entity["frame_mappings"][0]["mapping_status"], "null")
        entity["frame_mappings"][1]["raw_frame_presence"]["description"] = "changed only sidecar"
        self.assertEqual(raw, before)

    def test_padding_invalid_is_a_retained_error_not_whole_payload_failure(self):
        ctx = context("square_canvas")
        raw = ledger(ctx)
        second = deepcopy(raw["entities"][0])
        second["local_id"] = "e002"
        raw["entities"].append(second)
        raw["entities"][0]["frame_presence"][0]["bbox_xyxy_normalized"] = [0, 0, 1, 1]
        before = deepcopy((raw, ctx))
        result = M.map_detector_output(raw, ctx)
        self.assertEqual(result["mapping_status_counts"], {"mapped": 9, "null": 2, "error": 1})
        row = result["entities"][0]["frame_mappings"][0]
        self.assertEqual(row["original_bbox_xyxy_normalized"], [0, 0, 1, 1])
        self.assertIsNone(row["source_bbox_xyxy_normalized"])
        self.assertIsNone(row["source_bbox_xyxy_pixels"])
        self.assertIn("content", row["error"]["message"])
        self.assertEqual(result["entity_count"], 2)
        self.assertEqual(result["frame_row_count"], 12)
        self.assertEqual((raw, ctx), before)

    def test_other_coordinate_errors_are_recorded_per_row(self):
        for kind in M.VIEW_KINDS:
            for box in [[0, 0, 0, 1], [-0.1, 0, 1, 1], [False, 0, 1, 1],
                        [0, 0, float("inf"), 1], ["0", 0, 1, 1], [0, 0, 1]]:
                ctx = context(kind)
                raw = ledger(ctx)
                raw["entities"][0]["frame_presence"][0]["bbox_xyxy_normalized"] = box
                with self.subTest(kind=kind, box=box):
                    result = M.map_detector_output(raw, ctx)
                    self.assertEqual(result["mapping_status_counts"], {"mapped": 4, "null": 1, "error": 1})
                    row = result["entities"][0]["frame_mappings"][0]
                    self.assertEqual(row["original_bbox_xyxy_normalized"], box)
                    self.assertIsNone(row["source_bbox_xyxy_normalized"])

    def test_missing_duplicate_or_foreign_frame_reference_is_fatal(self):
        changes = [lambda r: r["entities"][0]["frame_presence"].pop(),
                   lambda r: r["entities"][0]["frame_presence"][0].update(frame_id=999),
                   lambda r: r["entities"][0]["frame_presence"][0].update(frame_id=3),
                   lambda r: r["entities"][0]["frame_presence"][0].update(frame_id=True),
                   lambda r: r["entities"][0]["frame_presence"][0].update(frame_id=0.0),
                   lambda r: r["entities"][0]["frame_presence"][0].pop("bbox_xyxy_normalized"),
                   lambda r: r.update(shot_id="another_shot"),
                   lambda r: r.update(protocol_version="survey"),
                   lambda r: r["entities"].append(deepcopy(r["entities"][0]))]
        for change in changes:
            ctx = context()
            raw = ledger(ctx)
            change(raw)
            before = deepcopy(raw)
            with self.subTest(change=change), self.assertRaises(ValueError):
                M.map_detector_output(raw, ctx)
            self.assertEqual(raw, before)

    def test_context_missing_or_tampered_geometry_rejected_before_mapping(self):
        changes = [lambda c: c["frames"].pop(), lambda c: c["frames"].reverse(),
                   lambda c: c["frames"][0].update(frame_id=True),
                   lambda c: c["frames"][1].update(view_path=c["frames"][0]["view_path"]),
                   lambda c: c["frames"][0].update(view_size=[9, 8]),
                   lambda c: c["frames"][0].update(content_rect_xyxy=[0, 0, 5, 3]),
                   lambda c: c["frames"][0]["geometry"].update(offset_xy=[0, 0]),
                   lambda c: c["frames"][0]["geometry"].update(source_size=[6, 3]),
                   lambda c: c["frames"][0].pop("geometry")]
        for change in changes:
            ctx = context("square_canvas")
            raw = ledger(ctx)
            change(ctx)
            with self.subTest(change=change), self.assertRaises(ValueError):
                M.map_detector_output(raw, ctx)
            with self.assertRaises(ValueError):
                M.build_geometry_metadata(ctx)
        ctx = context()
        ctx["frames"][0]["geometry"] = coordinates.canvas_geometry([5, 3])
        with self.assertRaises(ValueError):
            M.build_geometry_metadata(ctx)

    def test_empty_inventory_stays_empty_without_geometry_or_truth_claims(self):
        ctx = context()
        raw = ledger(ctx)
        raw["entities"] = []
        result = M.map_detector_output(raw, ctx)
        self.assertEqual(result["entities"], [])
        self.assertEqual(result["frame_row_count"], 0)
        self.assertFalse(result["identity_or_visual_correctness_established"])
        self.assertFalse(result["full_detector_validation_performed"])


if __name__ == "__main__":
    unittest.main()
