"""Synthetic single-frame geometry and input isolation checks, without models."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

import jsonschema
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import blind_pixel_survey as original  # noqa: E402
import single_frame_pixel_survey as M  # noqa: E402
from ensemble_shot_entity_detection import validate_codex_schema_transport  # noqa: E402


class SingleFramePixelSurveyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        refs = []
        for i, frame_id in enumerate([3, 11, 26, 37, 52, 80]):
            path = self.root / f"source_{i}.png"
            image = Image.new("RGB", (11 + i, 7 + i))
            image.putdata([((x * 31) % 256, (y * 47) % 256, (x + y) * 5)
                           for y in range(image.height) for x in range(image.width)])
            image.save(path)
            refs.append({"frame_id": frame_id, "path": str(path)})
        self.full = original.build_views(refs, self.root / "crops")
        self.bundle = M.build_frame_view_bundle(self.full, 3)

    def raw(self, *, view=2):
        v = self.bundle["views"][view]
        return {"schema_version": M.SCHEMA_VERSION, "regions": [
            {"region_id": "r0001", "frame_id": 3, "view_id": v["view_id"],
             "visual_description": "A translucent bounded patch partly hidden at an edge.",
             "scope_kind": "unknown", "boundary_status": "partial", "bbox_xyxy": [0.5, 1, 3, 4]}],
             "coverage_notes": "Uncertain extent, not exhaustive."}

    def test_full_schema_closed_required_and_transport_preflight(self):
        schema = validate_codex_schema_transport(M.SCHEMA_PATH)
        jsonschema.Draft202012Validator.check_schema(schema)
        self.assertEqual(set(schema["$defs"]), {"region", "scope"})
        jsonschema.validate(self.raw(), schema)
        def visit(node):
            if isinstance(node, dict):
                self.assertFalse(set(node) & {"uniqueItems", "minItems", "maxItems", "minimum", "maximum", "pattern"})
                if node.get("type") == "object":
                    self.assertIs(node["additionalProperties"], False)
                    self.assertEqual(set(node["required"]), set(node["properties"]))
                for value in node.values():
                    visit(value)
            elif isinstance(node, list):
                for value in node:
                    visit(value)
        visit(schema)

    def test_all_six_selections_partition_original_images_without_writes(self):
        before = {v["path"]: Path(v["path"]).read_bytes() for v in self.full["views"]}
        source_copy = deepcopy(self.full)
        selected = [M.build_frame_view_bundle(self.full, f) for f in [3, 11, 26, 37, 52, 80]]
        self.assertEqual([len(b["views"]) for b in selected], [5, 1, 1, 1, 1, 5])
        self.assertCountEqual([p for b in selected for p in b["attachments"]], list(before))
        for bundle in selected:
            self.assertEqual([v["attachment_index"] for v in bundle["views"]], list(range(1, len(bundle["views"]) + 1)))
            expected = [v for v in self.full["views"] if v["frame_id"] == bundle["frame_id"]]
            for actual, old in zip(bundle["views"], expected):
                self.assertEqual({k: v for k, v in actual.items() if k != "attachment_index"},
                                 {k: v for k, v in old.items() if k != "attachment_index"})
                self.assertEqual(hashlib.sha256(before[actual["path"]]).hexdigest(), actual["sha256"])
        self.assertEqual(source_copy, self.full)
        self.assertEqual(before, {p: Path(p).read_bytes() for p in before})

    def test_crop_mapping_uses_pixels_and_preserves_raw(self):
        raw = self.raw()
        old = deepcopy(raw)
        derived = M.validate_survey(raw, self.bundle)
        # Width 11: right crop starts at x=4; coordinates remain fractional.
        self.assertEqual(derived["regions"][0]["original_bbox_xyxy"], [4.5, 1, 7, 4])
        self.assertEqual(raw, old)
        self.assertFalse(derived["validation_summary"]["visual_accuracy_established"])
        derived["regions"][0]["bbox_xyxy"][0] = 99
        self.assertEqual(raw, old)
        with self.assertRaises(ValueError):
            M.validate_survey(derived, self.bundle)
        for v in self.bundle["views"]:
            with Image.open(v["path"]) as image, Image.open(v["source_path"]) as source:
                self.assertEqual(image.tobytes(), source.crop(v["crop_xyxy"]).tobytes())

    def test_last_frame_bottom_right_mapping_and_original_identity_transform(self):
        self.bundle = M.build_frame_view_bundle(self.full, 80)
        raw = self.raw(view=4)
        raw["regions"][0]["frame_id"] = 80
        self.assertEqual(M.validate_survey(raw, self.bundle)["regions"][0]["original_bbox_xyxy"], [6.5, 5, 9, 8])
        raw["regions"][0]["view_id"] = self.bundle["views"][0]["view_id"]
        self.assertEqual(M.validate_survey(raw, self.bundle)["regions"][0]["original_bbox_xyxy"], [0.5, 1, 3, 4])

    def test_prompt_excludes_other_frames_and_poisoned_metadata(self):
        contaminated = deepcopy(self.full)
        contaminated["instructions"] = "FORBIDDEN_PRIOR"
        contaminated["old_results"] = "FORBIDDEN_PRIOR"
        for v in contaminated["views"]:
            v["candidate"] = "FORBIDDEN_PRIOR"
        bundle = M.build_frame_view_bundle(contaminated, 26)
        bundle["instructions"] = "FORBIDDEN_PRIOR"
        bundle["views"][0]["old_judgment"] = "FORBIDDEN_PRIOR"
        prompt = M.build_survey_prompt(bundle)
        self.assertNotIn("FORBIDDEN_PRIOR", prompt)
        self.assertNotIn(str(self.root), prompt)
        for f in [3, 11, 37, 52, 80]:
            self.assertNotIn(f'"frame_id": {f}', prompt)
        public = json.loads(prompt.split("Attachment table (view-local pixels):\n")[1])
        self.assertEqual(len(public), 1)
        self.assertEqual(public[0]["frame_id"], 26)
        self.assertEqual(set(public[0]), {"attachment_index", "view_id", "frame_id", "kind", "output_size", "crop_origin"})

    def test_empty_uncertain_and_repeated_observations_do_not_require_tracks(self):
        raw = {"schema_version": M.SCHEMA_VERSION, "regions": [], "coverage_notes": ""}
        self.assertEqual(M.validate_survey(raw, self.bundle)["regions"], [])
        raw = self.raw()
        raw["regions"][0].update(bbox_xyxy=None, boundary_status="uncertain")
        second = deepcopy(raw["regions"][0])
        second["region_id"] = "r0002"
        raw["regions"].append(second)
        result = M.validate_survey(raw, self.bundle)
        self.assertEqual(len(result["regions"]), 2)
        self.assertIsNone(result["regions"][0]["original_bbox_xyxy"])
        self.assertNotIn("tracks", result)

    def test_physical_part_and_partial_boundary_are_independent(self):
        for scope in ["whole", "part", "collection", "unknown"]:
            for boundary in ["clear", "partial", "uncertain"]:
                with self.subTest(scope=scope, boundary=boundary):
                    raw = self.raw()
                    raw["regions"][0].update(scope_kind=scope, boundary_status=boundary)
                    self.assertEqual(M.validate_survey(raw, self.bundle)["regions"][0]["scope_kind"], scope)

    def test_invalid_frame_ids_never_become_ordinals(self):
        for value in [True, 3.0, "3", None, -1, 0, 2]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                M.build_frame_view_bundle(self.full, value)

    def test_invalid_region_ids_frames_and_empty_description(self):
        for field, value in [("region_id", "object1"), ("region_id", "r1"), ("region_id", 1),
                             ("frame_id", True), ("frame_id", 3.0), ("frame_id", None),
                             ("frame_id", 11), ("view_id", "frame_11_original"), ("visual_description", " ")]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                raw = self.raw()
                raw["regions"][0][field] = value
                M.validate_survey(raw, self.bundle)
        raw = self.raw()
        raw["regions"].append(deepcopy(raw["regions"][0]))
        with self.assertRaises(ValueError):
            M.validate_survey(raw, self.bundle)

    def test_invalid_boxes_do_not_pass_as_unknown_geometry(self):
        for box in [[True, 0, 3, 4], [0, 0, float("nan"), 4], [0, 0, float("inf"), 4],
                    [-1, 0, 3, 4], [0, 0, 8, 4], [3, 1, 3, 4], [3, 1, 2, 4], [0, 0, 1],
                    [0, 0, 10**400, 4]]:
            with self.subTest(box=box), self.assertRaises(ValueError):
                raw = self.raw()
                raw["regions"][0]["bbox_xyxy"] = box
                M.validate_survey(raw, self.bundle)
        raw = self.raw()
        raw["regions"][0]["bbox_xyxy"] = None
        with self.assertRaises(ValueError):
            M.validate_survey(raw, self.bundle)

    def test_malformed_single_frame_metadata_rejected_without_full_bundle(self):
        edits = [("frame_id", 3.0), ("attachment_index", True), ("source_size", [11.0, 7]),
                 ("crop_xyxy", [0, 0, 11, 7]), ("scale", True), ("output_size", [8, 5]),
                 ("source_path", "/another.png"), ("source_sha256", "a" * 64),
                 ("view_id", "frame_11_corner_1"), ("path", None), ("sha256", "broken")]
        for field, value in edits:
            with self.subTest(field=field), self.assertRaises(ValueError):
                bundle = deepcopy(self.bundle)
                bundle["views"][2][field] = value
                M.build_survey_prompt(bundle)
        for field, value in [("frame_id", True), ("views", self.bundle["views"][:2]),
                             ("attachments", list(reversed(self.bundle["attachments"]))), ("protocol_version", "old")]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                bundle = deepcopy(self.bundle)
                bundle[field] = value
                M.build_survey_prompt(bundle)

    def test_wrong_full_bundle_and_source_origin_rejected_before_selection(self):
        broken = deepcopy(self.full)
        broken["views"][3]["frame_id"] = 3
        with self.assertRaises(ValueError):
            M.build_frame_view_bundle(broken, 3)
        broken = deepcopy(self.full)
        broken["views"][7]["source_path"] = self.full["views"][1]["path"]
        with self.assertRaises(ValueError):
            M.build_frame_view_bundle(broken, 3)
        broken = deepcopy(self.full)
        broken["views"][0]["source_sha256"] = "f" * 64
        with self.assertRaises(ValueError):
            M.build_frame_view_bundle(broken, 3)

    def test_old_temporal_fields_and_missing_required_fields_are_rejected(self):
        for field in ["tracks", "region_relations", "frame_states"]:
            raw = self.raw()
            raw[field] = []
            with self.subTest(field=field), self.assertRaises(ValueError):
                M.validate_survey(raw, self.bundle)
        for field in self.raw()["regions"][0]:
            raw = self.raw()
            del raw["regions"][0][field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                M.validate_survey(raw, self.bundle)

    def test_standalone_middle_frame_and_tiny_valid_region(self):
        bundle = M.build_frame_view_bundle(self.full, 26)
        raw = self.raw()
        raw["regions"][0].update(frame_id=26, view_id="frame_26_original", bbox_xyxy=[0, 0, 0.001, 0.002])
        derived = M.validate_survey(raw, bundle)
        self.assertEqual(derived["regions"][0]["original_bbox_xyxy"], [0, 0, 0.001, 0.002])
        bundle["views"][0]["source_size"][0] = 100
        self.assertEqual(self.full["views"][2]["source_size"], [13, 9])

    def test_duplicate_path_missing_source_field_and_original_self_reference(self):
        for action in ["duplicate_path", "missing_source", "original_self_reference"]:
            bundle = deepcopy(self.bundle)
            if action == "duplicate_path":
                bundle["views"][1]["path"] = bundle["views"][0]["path"]
                bundle["attachments"][1] = bundle["attachments"][0]
            elif action == "missing_source":
                del bundle["views"][1]["source_path"]
            else:
                bundle["views"][0]["source_path"] = bundle["views"][1]["path"]
            with self.subTest(action=action), self.assertRaises(ValueError):
                M.build_survey_prompt(bundle)


if __name__ == "__main__":
    unittest.main()
