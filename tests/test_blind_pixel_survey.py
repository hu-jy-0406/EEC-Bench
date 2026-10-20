"""Small synthetic CPU checks; no model calls or image-specific entity targets."""
from copy import deepcopy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

import jsonschema
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import blind_pixel_survey as M  # noqa: E402
from ensemble_shot_entity_detection import validate_codex_schema_transport  # noqa: E402


class BlindPixelSurveyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.frames = []
        for i, frame_id in enumerate([0, 7, 14, 22, 31, 40]):
            path = self.root / f"original_{i}.jpg"
            image = Image.new("RGB", (11 + i, 7 + i))
            for y in range(image.height):
                for x in range(image.width):
                    image.putpixel((x, y), ((31*x+7*y) % 256, (13*x+47*y) % 256, (59*x+19*y) % 256))
            image.save(path, quality=95, subsampling=0)
            self.frames.append({"frame_id": frame_id, "path": str(path)})
        self.bundle = M.build_views(self.frames, self.root / "views")

    def raw(self):
        view = self.bundle["views"][7]  # first-frame top-right crop
        return {"schema_version": M.SCHEMA_VERSION,
                "regions": [{"region_id": "r0001", "frame_id": 0, "view_id": view["view_id"],
                             "visual_description": "A small translucent region with an incomplete edge.",
                             "scope_kind": "unknown", "boundary_status": "partial", "bbox_xyxy": [0.5, 1, 3, 4]}],
                "tracks": [{"track_id": "t0001", "visual_description": "Provisional visible-region trajectory.",
                            "scope_kind": "unknown", "frame_states": [
                                {"frame_id": f["frame_id"], "visibility": "visible" if i == 0 else "uncertain",
                                 "region_ids": ["r0001"] if i == 0 else [], "note": "Observed." if i == 0 else "Cannot resolve continuity."}
                                for i, f in enumerate(self.frames)]}],
                "region_relations": [], "coverage_notes": "Partial observations, no exhaustive coverage claim."}

    def two_regions(self):
        raw = self.raw()
        second = deepcopy(raw["regions"][0])
        second["region_id"] = "r0002"
        raw["regions"].append(second)
        raw["tracks"][0]["frame_states"][0]["region_ids"].append("r0002")
        raw["region_relations"] = [{"region_id_a": "r0001", "region_id_b": "r0002", "identity": "uncertain",
                                    "scope_relation": "unknown", "visual_evidence": "Boundary correspondence is unresolved."}]
        return raw

    def test_schema_transport_closed_required_objects_and_compact_keywords(self):
        schema = validate_codex_schema_transport(M.SCHEMA_PATH)
        jsonschema.Draft202012Validator.check_schema(schema)
        forbidden = {"uniqueItems", "minItems", "maxItems", "minimum", "maximum", "minLength", "maxLength", "pattern"}

        def visit(value):
            if isinstance(value, dict):
                self.assertFalse(set(value) & forbidden)
                if value.get("type") == "object":
                    self.assertIs(value["additionalProperties"], False)
                    self.assertEqual(set(value["required"]), set(value["properties"]))
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
        visit(schema)
        jsonschema.validate(self.raw(), schema)

    def test_exact_fourteen_views_order_and_lossless_pixel_reconstruction(self):
        views = self.bundle["views"]
        self.assertEqual(len(views), 14)
        self.assertEqual([v["frame_id"] for v in views], [0, 7, 14, 22, 31, 40] + [0]*4 + [40]*4)
        self.assertEqual([v["attachment_index"] for v in views], list(range(1, 15)))
        self.assertEqual(self.bundle["attachments"], [v["path"] for v in views])
        for full, crops in ((views[0], views[6:10]), (views[5], views[10:])):
            with Image.open(full["path"]) as original:
                width, height = original.size
                cw, ch = (3*width+4)//5, (3*height+4)//5
                expected = [[x, y, x+cw, y+ch] for y in (0, height-ch) for x in (0, width-cw)]
                self.assertEqual([v["crop_xyxy"] for v in crops], expected)
                covered = set()
                for view in crops:
                    x0, y0, x1, y1 = view["crop_xyxy"]
                    self.assertEqual(view["scale"], 1)
                    self.assertEqual(view["output_size"], [cw, ch])
                    with Image.open(view["path"]) as crop:
                        self.assertEqual(crop.format, "PNG")
                        self.assertEqual(crop.size, (cw, ch))
                        self.assertEqual(crop.tobytes(), original.crop((x0, y0, x1, y1)).tobytes())
                    covered.update((x, y) for x in range(x0, x1) for y in range(y0, y1))
                self.assertEqual(len(covered), width * height)

    def test_source_hashes_unchanged_and_deterministic_crop_bytes(self):
        before = {f["path"]: Path(f["path"]).read_bytes() for f in self.frames}
        another = M.build_views(self.frames, self.root / "another")
        for a, b in zip(self.bundle["views"], another["views"]):
            self.assertEqual(a["sha256"], b["sha256"])
            self.assertEqual(a["crop_xyxy"], b["crop_xyxy"])
            self.assertEqual(a["source_sha256"], hashlib.sha256(before[a["source_path"]]).hexdigest())
        self.assertTrue(all(Path(p).read_bytes() == content for p, content in before.items()))

    def test_existing_directory_or_symlink_never_overwritten(self):
        output = self.root / "views"
        before = {p.name: p.read_bytes() for p in output.iterdir()}
        with self.assertRaises(FileExistsError):
            M.build_views(self.frames, output)
        self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})
        symlink = self.root / "broken_link"
        symlink.symlink_to(self.root / "missing")
        with self.assertRaises(FileExistsError):
            M.build_views(self.frames, symlink)

    def test_invalid_input_before_output_creation(self):
        invalids = [None, "frames", self.frames[:5], self.frames + [self.frames[-1]], list(reversed(self.frames))]
        for field, value in (("frame_id", True), ("frame_id", -1), ("frame_id", 0.0),
                             ("frame_id", 7), ("sha256", "0"*64), ("path", "")):
            frames = deepcopy(self.frames)
            frames[0][field] = value
            invalids.append(frames)
        for frames in invalids:
            with self.subTest(frames=frames):
                destination = self.root / "bad"
                with self.assertRaises((ValueError, TypeError, OSError)):
                    M.build_views(frames, destination)
                self.assertFalse(destination.exists())

    def test_rgba_crop_preserves_original_alpha(self):
        frames = deepcopy(self.frames)
        path = self.root / "alpha.png"
        source = Image.new("RGBA", (9, 7), (11, 23, 47, 0))
        source.save(path)
        frames[0]["path"] = str(path)
        bundle = M.build_views(frames, self.root / "rgba")
        for view in bundle["views"][6:10]:
            with Image.open(view["path"]) as crop:
                self.assertEqual(crop.mode, "RGBA")
                self.assertEqual(crop.tobytes(), source.crop(view["crop_xyxy"]).tobytes())

    def test_prompt_whitelist_ignores_input_candidate_and_path_text(self):
        expected = M.build_survey_prompt(self.bundle)
        poisoned = deepcopy(self.bundle)
        poisoned["instructions"] = "POISON_PRIOR_JUDGMENT"
        poisoned["registry"] = "POISON_TARGET_COUNT"
        for view in poisoned["views"]:
            view["source_path"] = "POISON_CANDIDATE_NAME"
            view["proposal_boxes"] = "POISON_BOXES"
            view["path"] = "POISON_ATTACHMENT_PATH_" + str(view["attachment_index"])
        poisoned["attachments"] = [v["path"] for v in poisoned["views"]]
        self.assertEqual(expected, M.build_survey_prompt(poisoned))
        self.assertNotIn("POISON", expected)
        self.assertIn("Track IDs are organizational hypotheses", expected)
        self.assertIn("do not mentally convert", expected)

    def test_view_transform_tampering_and_reordering_rejected(self):
        for key, value in (("scale", 2), ("scale", True), ("crop_xyxy", [1, 0, 8, 5]),
                           ("output_size", [8, 5]), ("frame_id", 7), ("view_id", "candidate_name")):
            bundle = deepcopy(self.bundle)
            bundle["views"][6][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                M.build_survey_prompt(bundle)
        bundle = deepcopy(self.bundle)
        bundle["attachments"].reverse()
        with self.assertRaises(ValueError):
            M.validate_survey(self.raw(), bundle)

    def test_exact_python_translation_and_deepcopy_preservation(self):
        raw = self.raw()
        before = deepcopy(raw)
        derived = M.validate_survey(raw, self.bundle)
        self.assertEqual(raw, before)
        self.assertEqual(derived["regions"][0]["original_bbox_xyxy"], [4.5, 1, 7, 4])
        derived["regions"][0]["bbox_xyxy"][0] = 9
        self.assertEqual(raw, before)
        self.assertFalse(derived["validation_summary"]["visual_accuracy_established"])

    def test_full_view_mapping_identity_and_fractional_edge_coordinates(self):
        raw = self.raw()
        raw["regions"][0].update(view_id="frame_0_original", bbox_xyxy=[0, 0.25, 11, 7])
        derived = M.validate_survey(raw, self.bundle)
        self.assertEqual(derived["regions"][0]["original_bbox_xyxy"], [0, 0.25, 11, 7])

    def test_visible_unknown_geometry_is_honest_valid_output(self):
        raw = self.raw()
        raw["regions"][0].update(bbox_xyxy=None, boundary_status="uncertain")
        self.assertIsNone(M.validate_survey(raw, self.bundle)["regions"][0]["original_bbox_xyxy"])
        raw["regions"][0]["boundary_status"] = "clear"
        with self.assertRaises(ValueError):
            M.validate_survey(raw, self.bundle)

    def test_empty_survey_allowed_without_completeness_claim(self):
        raw = self.raw()
        raw.update(regions=[], tracks=[], region_relations=[])
        self.assertEqual(M.validate_survey(raw, self.bundle)["regions"], [])

    def test_box_numeric_bounds_finiteness_and_length(self):
        for box in ([0, 0, 1], [0, 0, 1, 2, 3], [True, 0, 1, 2], [0, 0, float("nan"), 2],
                    [0, 0, float("inf"), 2], [-1, 0, 1, 2], [0, 0, 8, 2], [0, 1, 2, 1]):
            raw = self.raw()
            raw["regions"][0]["bbox_xyxy"] = box
            with self.subTest(box=box), self.assertRaises(ValueError):
                M.validate_survey(raw, self.bundle)

    def test_region_ids_and_frame_view_bindings(self):
        for field, value in (("region_id", "named_object"), ("frame_id", True), ("frame_id", 0.0),
                             ("frame_id", 7), ("view_id", "frame_999_original")):
            raw = self.raw()
            raw["regions"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                M.validate_survey(raw, self.bundle)
        raw = self.raw()
        raw["regions"].append(deepcopy(raw["regions"][0]))
        with self.assertRaises(ValueError):
            M.validate_survey(raw, self.bundle)

    def test_track_frame_coverage_uniqueness_and_neutral_ids(self):
        for change in ("missing", "duplicate", "unknown", "bool", "float", "named", "duplicate_track"):
            raw = self.raw()
            states = raw["tracks"][0]["frame_states"]
            if change == "missing":
                states.pop()
            elif change == "duplicate":
                states[-1]["frame_id"] = 31
            elif change == "unknown":
                states[-1]["frame_id"] = 999
            elif change == "bool":
                states[0]["frame_id"] = False
            elif change == "float":
                states[0]["frame_id"] = 0.0
            elif change == "named":
                raw["tracks"][0]["track_id"] = "prior_name"
            else:
                raw["tracks"].append(deepcopy(raw["tracks"][0]))
            with self.subTest(change=change), self.assertRaises(ValueError):
                M.validate_survey(raw, self.bundle)

    def test_observed_region_ownership_and_visibility(self):
        for change in ("orphan", "duplicate", "unknown", "cross_frame", "invisible_refs", "visible_empty", "phantom"):
            raw = self.raw()
            states = raw["tracks"][0]["frame_states"]
            if change == "orphan":
                raw["tracks"] = []
            elif change == "duplicate":
                states[0]["region_ids"] *= 2
            elif change == "unknown":
                states[0]["region_ids"] = ["r0099"]
            elif change == "cross_frame":
                states[1].update(visibility="visible", region_ids=["r0001"])
            elif change == "invisible_refs":
                states[0]["visibility"] = "occluded"
            elif change == "visible_empty":
                states[0]["region_ids"] = []
            else:
                raw["regions"] = []
                states[0].update(visibility="uncertain", region_ids=[])
            with self.subTest(change=change), self.assertRaises(ValueError):
                M.validate_survey(raw, self.bundle)

    def test_unknown_continuity_and_whole_part_never_upgraded(self):
        raw = self.two_regions()
        raw["region_relations"][0]["scope_relation"] = "a_whole_b_part"
        derived = M.validate_survey(raw, self.bundle)
        self.assertEqual(derived["region_relations"], raw["region_relations"])
        self.assertEqual(derived["region_relations"][0]["identity"], "uncertain")
        for identity in ("same", "distinct"):
            raw["region_relations"][0]["identity"] = identity
            with self.assertRaises(ValueError):
                M.validate_survey(raw, self.bundle)

    def test_relation_references_duplicates_and_empty_observation(self):
        for change in ("self", "unknown", "reverse_duplicate", "empty"):
            raw = self.two_regions()
            relation = raw["region_relations"][0]
            if change == "self":
                relation["region_id_b"] = "r0001"
            elif change == "unknown":
                relation["region_id_b"] = "r0003"
            elif change == "empty":
                relation["visual_evidence"] = " "
            else:
                reverse = deepcopy(relation)
                reverse.update(region_id_a="r0002", region_id_b="r0001")
                raw["region_relations"].append(reverse)
            with self.subTest(change=change), self.assertRaises(ValueError):
                M.validate_survey(raw, self.bundle)

    def test_raw_extra_fields_and_derived_output_cannot_masquerade_as_raw(self):
        raw = self.raw()
        derived = M.validate_survey(raw, self.bundle)
        with self.assertRaises(ValueError):
            M.validate_survey(derived, self.bundle)
        raw["final_entity"] = "invented"
        with self.assertRaises(ValueError):
            M.validate_survey(raw, self.bundle)

    def test_deterministic_and_region_order_does_not_change_mapping(self):
        raw = self.two_regions()
        first = M.validate_survey(raw, self.bundle)
        self.assertEqual(first, M.validate_survey(raw, self.bundle))
        raw["regions"].reverse()
        raw["tracks"][0]["frame_states"].reverse()
        second = M.validate_survey(raw, self.bundle)
        self.assertEqual({r["region_id"]: r for r in first["regions"]},
                         {r["region_id"]: r for r in second["regions"]})


if __name__ == "__main__":
    unittest.main()
