"""Small CPU-only geometry and information-boundary checks; no model calls."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import blind_pixel_survey as base  # noqa: E402
import spatial_cell_survey as spatial  # noqa: E402


def bundle():
    """Valid view metadata needs no filesystem or real image to build prompts."""
    views = []
    for index, (width, height) in enumerate([(11, 7), (12, 8), (9, 6), (8, 9), (1, 1), (13, 11)]):
        frame_id = index * 9
        views.append({"attachment_index": index + 1, "view_id": f"frame_{frame_id}_original",
                      "frame_id": frame_id, "kind": "original", "source_size": [width, height],
                      "output_size": [width, height], "crop_xyxy": [0, 0, width, height],
                      "scale": 1, "path": f"/private/frame_{frame_id}.png"})
    for original in (views[0], views[5]):
        width, height = original["source_size"]
        cw, ch = (3 * width + 4) // 5, (3 * height + 4) // 5
        for corner, (x, y) in enumerate([(0, 0), (width-cw, 0), (0, height-ch), (width-cw, height-ch)], 1):
            view_id = f"frame_{original['frame_id']}_corner_{corner}"
            views.append({"attachment_index": len(views) + 1, "view_id": view_id,
                          "frame_id": original["frame_id"], "kind": "crop",
                          "source_size": [width, height], "output_size": [cw, ch],
                          "crop_xyxy": [x, y, x+cw, y+ch], "scale": 1,
                          "path": f"/private/{view_id}.png"})
    return {"protocol_version": base.PROTOCOL_VERSION, "views": views,
            "attachments": [v["path"] for v in views]}


def parameters(prompt):
    return json.loads(prompt.split("\nSpatial parameters (original pixels):\n", 1)[1])


class SpatialCellSurveyTests(unittest.TestCase):
    def setUp(self):
        self.bundle = bundle()

    def test_base_prefix_and_only_assigned_cell_changes_between_roles(self):
        prefix = base.build_survey_prompt(self.bundle)
        expected = None
        for cell in spatial.CELL_ORDER:
            prompt = spatial.build_spatial_survey_prompt(self.bundle, cell)
            self.assertTrue(prompt.startswith(prefix))
            suffix = prompt[len(prefix):]
            self.assertTrue(suffix.startswith("\n\n" + spatial.INSTRUCTIONS))
            normalized = suffix.replace('"assigned_cell": "' + cell + '"', '"assigned_cell": "CELL"')
            if expected is None:
                expected = normalized
            self.assertEqual(normalized, expected)

    def test_floor_half_open_cells_tile_every_original_without_overlap(self):
        rows = parameters(spatial.build_spatial_survey_prompt(self.bundle, "TR"))["original_frame_cells"]
        self.assertEqual(len(rows), 6)
        for row, view in zip(rows, self.bundle["views"][:6]):
            width, height = view["source_size"]
            self.assertEqual(row["frame_id"], view["frame_id"])
            self.assertEqual(row["original_view_id"], view["view_id"])
            self.assertEqual(row["original_size"], [width, height])
            cells = row["cells_xyxy"]
            self.assertEqual(cells["TL"], [0, 0, width//2, height//2])
            self.assertEqual(cells["BR"], [width//2, height//2, width, height])
            seen = set()
            for box in cells.values():
                points = {(x, y) for x in range(box[0], box[2]) for y in range(box[1], box[3])}
                self.assertFalse(seen & points)
                seen |= points
            self.assertEqual(seen, {(x, y) for x in range(width) for y in range(height)})
            mx, my = width//2, height//2
            self.assertTrue(cells["BR"][0] <= mx < cells["BR"][2])
            self.assertTrue(cells["BR"][1] <= my < cells["BR"][3])

    def test_untrusted_extra_text_and_paths_do_not_reach_prompt_or_mutate_input(self):
        clean = spatial.build_spatial_survey_prompt(self.bundle, "BL")
        poisoned = deepcopy(self.bundle)
        for key in ("instructions", "registry", "expected_count", "candidate", "assigned_cell"):
            poisoned[key] = "POISON_UNTRUSTED_TEXT"
        for view in poisoned["views"]:
            for key in ("source_path", "candidate_name", "proposal_boxes", "old_survey"):
                view[key] = "POISON_UNTRUSTED_TEXT"
            view["path"] = "POISON_PATH_" + str(view["attachment_index"])
        poisoned["attachments"] = [v["path"] for v in poisoned["views"]]
        before = deepcopy(poisoned)
        self.assertEqual(spatial.build_spatial_survey_prompt(poisoned, "BL"), clean)
        self.assertEqual(poisoned, before)
        self.assertNotIn("POISON", clean)
        self.assertNotIn("/private", clean)

    def test_each_view_intersection_is_exact_cell_pixels_in_local_coordinates(self):
        data = parameters(spatial.build_spatial_survey_prompt(self.bundle, "TR"))
        originals = {r["frame_id"]: r["cells_xyxy"] for r in data["original_frame_cells"]}
        self.assertEqual(len(data["view_cell_intersections"]), 14)
        for row, view in zip(data["view_cell_intersections"], self.bundle["views"]):
            self.assertEqual(row["view_id"], view["view_id"])
            vx0, vy0, vx1, vy1 = view["crop_xyxy"]
            for cell, local in row["cells_xyxy_view_local"].items():
                cx0, cy0, cx1, cy1 = originals[view["frame_id"]][cell]
                expected = {(x-vx0, y-vy0) for x in range(vx0, vx1) for y in range(vy0, vy1)
                            if cx0 <= x < cx1 and cy0 <= y < cy1}
                if not expected:
                    self.assertIsNone(local)
                else:
                    actual = {(x, y) for x in range(local[0], local[2]) for y in range(local[1], local[3])}
                    self.assertEqual(actual, expected)
                    self.assertTrue(0 <= local[0] < local[2] <= view["output_size"][0])
                    self.assertTrue(0 <= local[1] < local[3] <= view["output_size"][1])

    def test_invalid_cell_and_invalid_base_geometry_fail(self):
        for cell in (None, True, 1, [], {}, "tl", "TL\nPOISON", "TL/TR", ""):
            with self.subTest(cell=cell), self.assertRaises(ValueError):
                spatial.build_spatial_survey_prompt(self.bundle, cell)
        for bad in (True, 11.0, 0, -1, "11"):
            changed = deepcopy(self.bundle)
            changed["views"][0]["source_size"][0] = bad
            with self.subTest(dimension=bad), self.assertRaises(ValueError):
                spatial.build_spatial_survey_prompt(changed, "TL")
        changed = deepcopy(self.bundle)
        changed["views"][6]["crop_xyxy"][0] = 1
        with self.assertRaises(ValueError):
            spatial.build_spatial_survey_prompt(changed, "TL")

    def test_empty_unknown_and_cross_cell_outputs_keep_existing_contract(self):
        empty = {"schema_version": base.SCHEMA_VERSION, "regions": [], "tracks": [],
                 "region_relations": [], "coverage_notes": "No reliable observations."}
        raw = deepcopy(empty)
        raw["regions"] = [{"region_id": "r0001", "frame_id": 0, "view_id": "frame_0_original",
                           "visual_description": "An incomplete visible boundary crosses the midpoint.",
                           "scope_kind": "unknown", "boundary_status": "partial", "bbox_xyxy": [4, 2, 9, 6]}]
        raw["tracks"] = [{"track_id": "t0001", "visual_description": "Uncertain correspondence.",
                          "scope_kind": "unknown", "frame_states": [
                              {"frame_id": v["frame_id"], "visibility": "visible" if i == 0 else "uncertain",
                               "region_ids": ["r0001"] if i == 0 else [], "note": "Limited observation."}
                              for i, v in enumerate(self.bundle["views"][:6])]}]
        unknown = deepcopy(raw)
        unknown["regions"][0].update(bbox_xyxy=None, boundary_status="uncertain")
        for cell in spatial.CELL_ORDER:
            spatial.build_spatial_survey_prompt(self.bundle, cell)
            for payload in (empty, raw, unknown):
                before = deepcopy(payload)
                base.validate_survey(payload, self.bundle)
                self.assertEqual(payload, before)

    def test_prompt_retains_home_frame_visibility_and_scope_limits(self):
        prompt = spatial.build_spatial_survey_prompt(self.bundle, "BR")
        self.assertIn("earliest supplied original frame", prompt)
        self.assertIn("It need not be\nthe first frame", prompt)
        self.assertIn("or before its home frame", prompt)
        self.assertIn("never treat original cell bounds as crop-local coordinates", prompt)
        self.assertIn("inside the original full frame is NOT\nout_of_view", prompt)
        self.assertIn("not a required new output field", prompt)
        self.assertIn("Do not split a physical scope mechanically", prompt)
        self.assertIn("that VIEW'S LOCAL pixels", prompt)
        self.assertNotIn("c000", prompt)
        self.assertNotIn("p000", prompt)


if __name__ == "__main__":
    unittest.main()
