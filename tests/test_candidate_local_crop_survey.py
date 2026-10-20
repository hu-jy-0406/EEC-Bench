"""Pure crop geometry, anonymity and unchanged-schema tests; no image/model I/O."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import candidate_local_crop_survey as M  # noqa: E402
import single_frame_pixel_survey as OLD  # noqa: E402
from ensemble_shot_entity_detection import validate_codex_schema_transport  # noqa: E402


class CandidateLocalCropSurveyTests(unittest.TestCase):
    def bundle(self):
        return {"protocol_version": M.PROTOCOL_VERSION, "frame_id": 17,
                "attachments": ["/missing/private_crop.png"], "views": [
                    {"attachment_index": 1, "view_id": "view_0001", "frame_id": 17,
                     "kind": "candidate_crop", "path": "/missing/private_crop.png", "sha256": "b" * 64,
                     "source_path": "/missing/private_source.jpg", "source_sha256": "a" * 64,
                     "source_size": [200, 160], "crop_xyxy": [12, 2, 108, 98],
                     "output_size": [96, 96], "scale": 1}]}

    def raw(self):
        return {"schema_version": M.SCHEMA_VERSION, "regions": [
            {"region_id": "r0001", "frame_id": 17, "view_id": "view_0001",
             "visual_description": "A bounded translucent patch partially obscured along an edge.",
             "scope_kind": "unknown", "boundary_status": "partial", "bbox_xyxy": [0.5, 1, 3, 4]}],
             "coverage_notes": "Limited visible extent."}

    def context_bundle(self):
        bundle = self.bundle()
        bundle["protocol_version"] = M.CONTEXT_PROTOCOL_VERSION
        crop = bundle["views"][0]
        context = {"attachment_index": 2, "view_id": "view_0002", "frame_id": 17,
                   "kind": "context_original", "path": crop["source_path"],
                   "source_path": crop["source_path"], "sha256": crop["source_sha256"],
                   "source_sha256": crop["source_sha256"], "source_size": [200, 160],
                   "crop_xyxy": [0, 0, 200, 160], "output_size": [200, 160], "scale": 1}
        bundle["views"].append(context)
        bundle["attachments"].append(context["path"])
        return bundle

    def test_legacy_instructions_and_prompt_bytes_are_preserved(self):
        # Captured from the unchanged crop-only helper before this mode was added.
        self.assertEqual(M.PROTOCOL_VERSION, "candidate_local_crop_survey_views_v0.1")
        self.assertEqual(hashlib.sha256(M.INSTRUCTIONS.encode()).hexdigest(),
                         "f4da00cab18f65199bb5928819261b8f15214a64d58789d72d711286957d1b2a")
        self.assertEqual(hashlib.sha256(M.build_survey_prompt(self.bundle()).encode()).hexdigest(),
                         "aa6d794f37c31266d8f793e111b7a072225719911cb69196ce8bed7c7d5d63b2")

    def test_context_mode_maps_only_crop_and_preserves_every_raw_field(self):
        raw, bundle = self.raw(), self.context_bundle()
        before = deepcopy((raw, bundle))
        derived = M.validate_survey(raw, bundle)
        old = M.validate_survey(raw, self.bundle())
        self.assertEqual(derived["regions"], old["regions"])
        self.assertEqual(derived["regions"][0]["original_bbox_xyxy"], [12.5, 3, 15, 6])
        self.assertEqual(derived["validation_summary"]["view_policy_version"], M.CONTEXT_PROTOCOL_VERSION)
        self.assertEqual({k: v for k, v in derived["regions"][0].items()
                          if k != "original_bbox_xyxy"}, raw["regions"][0])
        self.assertEqual((raw, bundle), before)
        derived["regions"][0]["bbox_xyxy"][0] = 99
        self.assertEqual((raw, bundle), before)
        self.assertFalse(derived["validation_summary"]["candidate_correspondence_established"])
        self.assertFalse(derived["validation_summary"]["identity_established"])

    def test_context_prompt_whitelist_has_no_original_geometry_or_prior(self):
        bundle = self.context_bundle()
        baseline = M.build_survey_prompt(bundle)
        bundle.update(candidate_id="FORBIDDEN_PRIOR", old_judgment="FORBIDDEN_PRIOR")
        for view in bundle["views"]:
            view.update(description="FORBIDDEN_PRIOR", origin="FORBIDDEN_PRIOR")
        prompt = M.build_survey_prompt(bundle)
        self.assertEqual(prompt, baseline)
        self.assertNotIn("FORBIDDEN_PRIOR", prompt)
        for forbidden in ["/missing/", '"source_size"', '"crop_xyxy"', '"crop_origin"', "a" * 64]:
            self.assertNotIn(forbidden, prompt)
        table = json.loads(prompt.split("Safe view table (crop-local output only):\n")[1])
        self.assertEqual(table, {
            "output_crop": {"attachment_index": 1, "frame_id": 17,
                            "view_id": "view_0001", "output_size": [96, 96]},
            "context_original": {"attachment_index": 2, "role": "context_only",
                                 "view_id": "view_0002", "frame_id": 17}})
        self.assertIn("ONLY output view", prompt)
        self.assertIn("Do not add objects visible only outside the crop", prompt)
        self.assertIn("not a second independent observation", prompt)

    def test_context_protocol_does_not_relax_either_attachment_contract(self):
        mutations = [lambda b: b.update(protocol_version=M.PROTOCOL_VERSION),
                     lambda b: b.update(protocol_version="unknown"),
                     lambda b: b["views"].pop(), lambda b: b["attachments"].pop(),
                     lambda b: b["views"].reverse(), lambda b: b["attachments"].reverse(),
                     lambda b: b["views"].append(deepcopy(b["views"][1])),
                     lambda b: b["attachments"].append("/third.png"),
                     lambda b: b["views"][0].update(view_id="view_0003"),
                     lambda b: b["views"][0].update(attachment_index=2)]
        for mutation in mutations:
            bundle = self.context_bundle()
            mutation(bundle)
            with self.subTest(bundle=bundle), self.assertRaises(ValueError):
                M.build_survey_prompt(bundle)
        bundle = self.bundle()
        bundle["protocol_version"] = M.CONTEXT_PROTOCOL_VERSION
        with self.assertRaises(ValueError):
            M.build_survey_prompt(bundle)

    def test_context_original_must_match_frame_path_hash_size_and_full_extent(self):
        # A colliding frame ID in another shot cannot authorize another source.
        cases = [("frame_id", 18), ("frame_id", 17.0), ("frame_id", True),
                 ("view_id", "view_0001"), ("attachment_index", True),
                 ("attachment_index", 1), ("kind", "original"), ("scale", 1.0),
                 ("scale", True), ("scale", 2), ("path", "/another-shot.jpg"),
                 ("source_path", "/another-shot.jpg"), ("sha256", "c" * 64),
                 ("source_sha256", "c" * 64), ("source_size", [201, 160]),
                 ("source_size", [200.0, 160]), ("output_size", [199, 160]),
                 ("output_size", [200, 160.0]), ("crop_xyxy", [1, 0, 200, 160]),
                 ("crop_xyxy", [0.0, 0, 200, 160]), ("crop_xyxy", [False, 0, 200, 160]),
                 ("crop_xyxy", [0, 0, 199, 160]), ("crop_xyxy", None)]
        for key, value in cases:
            bundle = self.context_bundle()
            bundle["views"][1][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                M.build_survey_prompt(bundle)
        for key in self.context_bundle()["views"][1]:
            bundle = self.context_bundle()
            del bundle["views"][1][key]
            with self.subTest(missing=key), self.assertRaises(ValueError):
                M.build_survey_prompt(bundle)

    def test_context_output_cannot_use_original_view_frame_or_size(self):
        mutations = [("view_id", "view_0002"), ("frame_id", 18), ("frame_id", 17.0),
                     ("frame_id", True), ("bbox_xyxy", [100, 20, 110, 30]),
                     ("bbox_xyxy", [0, 0, float("nan"), 10]),
                     ("bbox_xyxy", [False, 0, 10, 10]), ("bbox_xyxy", None)]
        for key, value in mutations:
            raw = self.raw()
            raw["regions"][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                M.validate_survey(raw, self.context_bundle())
        raw = self.raw()
        raw["regions"].append(deepcopy(raw["regions"][0]))
        with self.assertRaises(ValueError):
            M.validate_survey(raw, self.context_bundle())

    def test_context_keeps_honest_null_empty_and_in_bounds_semantic_uncertainty(self):
        bundle, raw = self.context_bundle(), self.raw()
        raw["regions"][0].update(bbox_xyxy=None, boundary_status="uncertain", scope_kind="unknown")
        derived = M.validate_survey(raw, bundle)
        self.assertIsNone(derived["regions"][0]["original_bbox_xyxy"])
        # The numerical contract cannot know that a valid local box was actually
        # guessed in original coordinates. It must not auto-correct or certify it.
        raw["regions"][0]["bbox_xyxy"] = [20, 20, 21, 21]
        derived = M.validate_survey(raw, bundle)
        self.assertEqual(derived["regions"][0]["original_bbox_xyxy"], [32, 22, 33, 23])
        self.assertFalse(derived["validation_summary"]["visual_accuracy_established"])
        raw["regions"] = []
        self.assertEqual(M.validate_survey(raw, bundle)["regions"], [])

    def test_context_reuses_full_admitted_schema_without_old_survey_relaxation(self):
        self.assertEqual(hashlib.sha256(M.SCHEMA_PATH.read_bytes()).hexdigest(),
                         "8b11d107425171ba0a316e3da5732c9ba502d6cd6123949175c33471103ccd61")
        schema = validate_codex_schema_transport(M.SCHEMA_PATH)
        jsonschema.validate(self.raw(), schema)
        with self.assertRaises(ValueError):
            OLD.validate_survey(self.raw(), self.context_bundle())
        raw = self.raw()
        raw["tracks"] = []
        with self.assertRaises(ValueError):
            M.validate_survey(raw, self.context_bundle())

    def test_small_box_expands_about_center_before_rounding(self):
        bbox, size = [50, 40, 70, 60], [200, 160]
        before = deepcopy((bbox, size))
        g = M.crop_geometry(bbox, size)
        self.assertEqual(g["requested_crop_xyxy"], [12, 2, 108, 98])
        self.assertEqual(g["actual_crop_xyxy"], [12, 2, 108, 98])
        self.assertEqual(g["clipped_flags"], dict.fromkeys(["left", "top", "right", "bottom"], False))
        self.assertEqual((bbox, size), before)
        g["source_size"][0] = 1
        self.assertEqual(size, [200, 160])

    def test_padding_is_axis_specific_and_not_always_minimum(self):
        g = M.crop_geometry([60, 60, 260, 140], [400, 300])
        self.assertEqual(g["requested_crop_xyxy"], [10, 40, 310, 160])
        self.assertEqual(g["actual_crop_xyxy"], g["requested_crop_xyxy"])

    def test_fractional_center_rounds_outward_and_clips_only_request(self):
        g = M.crop_geometry([1.2, 2.6, 2.2, 4.6], [200, 160])
        self.assertEqual(g["requested_crop_xyxy"], [-47, -45, 50, 52])
        self.assertEqual(g["actual_crop_xyxy"], [0, 0, 50, 52])
        self.assertEqual(g["clipped_flags"], {"left": True, "top": True, "right": False, "bottom": False})

    def test_tiny_source_and_whole_image_crop_remain_valid(self):
        tiny = M.crop_geometry([5, 2, 8, 4], [20, 10])
        self.assertEqual(tiny["requested_crop_xyxy"], [-42, -45, 55, 51])
        self.assertEqual(tiny["actual_crop_xyxy"], [0, 0, 20, 10])
        self.assertTrue(all(tiny["clipped_flags"].values()))
        whole = M.crop_geometry([0, 0, 200, 160], [200, 160])
        self.assertEqual(whole["requested_crop_xyxy"], [-50, -40, 250, 200])
        self.assertEqual(whole["actual_crop_xyxy"], [0, 0, 200, 160])

    def test_null_bad_and_out_of_source_boxes_are_never_repaired(self):
        for box in [None, [], [1, 2, 3], [True, 1, 3, 4], [0, 0, float("nan"), 4],
                    [0, 0, float("inf"), 4], [-1, 2, 3, 4], [0, 0, 201, 10],
                    [3, 1, 3, 4], [4, 1, 3, 4], [0, 0, 10**400, 4]]:
            with self.subTest(box=box), self.assertRaises(ValueError):
                M.crop_geometry(box, [200, 160])
        for size in [None, [0, 10], [10, -1], [10.0, 10], [True, 10], [10, 10, 10]]:
            with self.subTest(size=size), self.assertRaises(ValueError):
                M.crop_geometry([1, 1, 2, 2], size)

    def test_prompt_whitelist_excludes_all_candidate_and_source_geometry(self):
        bundle = self.bundle()
        baseline = M.build_survey_prompt(bundle)
        bundle.update(candidate_name="FORBIDDEN_PRIOR", original_bbox=[11, 22, 33, 44], instructions="FORBIDDEN_PRIOR")
        bundle["views"][0].update(candidate_id="FORBIDDEN_PRIOR", prior_description="FORBIDDEN_PRIOR")
        prompt = M.build_survey_prompt(bundle)
        self.assertEqual(prompt, baseline)
        self.assertNotIn("FORBIDDEN_PRIOR", prompt)
        table = json.loads(prompt.split("Safe view table (crop-local pixels):\n")[1])
        self.assertEqual(table, {"frame_id": 17, "view_id": "view_0001", "output_size": [96, 96]})
        self.assertNotIn("/missing/", prompt)
        self.assertNotIn('"source_size"', prompt)
        self.assertNotIn('"crop_xyxy"', prompt)
        self.assertNotIn('"crop_origin"', prompt)
        self.assertNotIn("a" * 64, prompt)

    def test_translation_only_preserves_raw_and_needs_no_image_file(self):
        raw, bundle = self.raw(), self.bundle()
        before = deepcopy((raw, bundle))
        result = M.validate_survey(raw, bundle)
        self.assertEqual(result["regions"][0]["original_bbox_xyxy"], [12.5, 3, 15, 6])
        self.assertEqual((raw, bundle), before)
        self.assertFalse(result["validation_summary"]["candidate_correspondence_established"])
        result["regions"][0]["bbox_xyxy"][0] = 10
        self.assertEqual((raw, bundle), before)
        with self.assertRaises(ValueError):
            M.validate_survey(result, bundle)

    def test_empty_null_and_repeat_observations_are_not_filtered(self):
        raw = {"schema_version": M.SCHEMA_VERSION, "regions": [], "coverage_notes": ""}
        self.assertEqual(M.validate_survey(raw, self.bundle())["regions"], [])
        raw = self.raw()
        raw["regions"][0].update(bbox_xyxy=None, boundary_status="uncertain")
        second = deepcopy(raw["regions"][0])
        second["region_id"] = "r0002"
        raw["regions"].append(second)
        result = M.validate_survey(raw, self.bundle())
        self.assertEqual(len(result["regions"]), 2)
        self.assertTrue(all(r["original_bbox_xyxy"] is None for r in result["regions"]))

    def test_scope_and_boundary_axes_do_not_create_visual_acceptance(self):
        for scope in ["whole", "part", "collection", "unknown"]:
            for boundary in ["clear", "partial", "uncertain"]:
                raw = self.raw()
                raw["regions"][0].update(scope_kind=scope, boundary_status=boundary)
                result = M.validate_survey(raw, self.bundle())
                self.assertEqual(result["regions"][0]["scope_kind"], scope)
                self.assertFalse(result["validation_summary"]["visual_accuracy_established"])

    def test_only_current_crop_frame_and_neutral_unique_ids_are_allowed(self):
        for key, value in [("frame_id", True), ("frame_id", 17.0), ("frame_id", None),
                           ("frame_id", 18), ("view_id", "view_0002"), ("region_id", "candidate1"),
                           ("region_id", "r1"), ("region_id", 1), ("visual_description", " ")]:
            raw = self.raw()
            raw["regions"][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                M.validate_survey(raw, self.bundle())
        raw = self.raw()
        raw["regions"].append(deepcopy(raw["regions"][0]))
        with self.assertRaises(ValueError):
            M.validate_survey(raw, self.bundle())

    def test_crop_local_boxes_cannot_fall_back_to_source_coordinates(self):
        for box in [[100, 20, 110, 30], [True, 0, 3, 4], [0, 0, float("nan"), 4],
                    [0, 0, float("inf"), 4], [-1, 0, 3, 4], [3, 1, 3, 4], [0, 0, 1], None]:
            raw = self.raw()
            raw["regions"][0]["bbox_xyxy"] = box
            with self.subTest(box=box), self.assertRaises(ValueError):
                M.validate_survey(raw, self.bundle())
        # An incorrect semantic coordinate which happens to fit cannot be detected
        # without pixels; acceptance here is deliberately only a geometry check.
        raw = self.raw()
        raw["regions"][0]["bbox_xyxy"] = [20, 20, 21, 21]
        result = M.validate_survey(raw, self.bundle())
        self.assertEqual(result["regions"][0]["original_bbox_xyxy"], [32, 22, 33, 23])
        self.assertFalse(result["validation_summary"]["visual_accuracy_established"])

    def test_invalid_single_crop_metadata_is_rejected(self):
        for key, value in [("frame_id", 17.0), ("frame_id", 18), ("view_id", "target_lamp"),
                           ("attachment_index", True), ("kind", "original"), ("scale", 2),
                           ("source_size", [200.0, 160]), ("crop_xyxy", [-1, 2, 108, 98]),
                           ("crop_xyxy", [12.0, 2, 108, 98]), ("output_size", [95, 96]),
                           ("path", ""), ("source_path", None), ("sha256", "bad")]:
            bundle = self.bundle()
            bundle["views"][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                M.build_survey_prompt(bundle)
        for key, value in [("frame_id", True), ("views", []), ("attachments", ["/another.png"]),
                           ("protocol_version", OLD.PROTOCOL_VERSION)]:
            bundle = self.bundle()
            bundle[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                M.build_survey_prompt(bundle)
        bundle = self.bundle()
        bundle["views"].append(deepcopy(bundle["views"][0]))
        with self.assertRaises(ValueError):
            M.build_survey_prompt(bundle)

    def test_full_admitted_schema_reused_without_relaxing_legacy_views(self):
        before = hashlib.sha256(OLD.SCHEMA_PATH.read_bytes()).hexdigest()
        self.assertEqual(M.SCHEMA_PATH, OLD.SCHEMA_PATH)
        schema = validate_codex_schema_transport(M.SCHEMA_PATH)
        jsonschema.validate(self.raw(), schema)
        self.assertEqual(set(schema["$defs"]), {"scope", "region"})
        self.assertEqual(set(schema["properties"]), {"schema_version", "regions", "coverage_notes"})
        with self.assertRaises(ValueError):
            OLD.validate_survey(self.raw(), self.bundle())
        raw = self.raw()
        raw["tracks"] = []
        with self.assertRaises(ValueError):
            M.validate_survey(raw, self.bundle())
        self.assertEqual(hashlib.sha256(OLD.SCHEMA_PATH.read_bytes()).hexdigest(), before)


if __name__ == "__main__":
    unittest.main()
