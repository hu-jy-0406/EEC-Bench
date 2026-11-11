import importlib.util
import sys
import unittest
from pathlib import Path

from PIL import Image


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "render_entity_graph_video.py"
SPEC = importlib.util.spec_from_file_location("render_entity_graph_video", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class RenderEntityGraphVideoTest(unittest.TestCase):
    def graph(self):
        return {
            "entities": [
                {
                    "id": "e1",
                    "name": "cup",
                    "grounding": {
                        "status": "grounded",
                        "query": "blue cup",
                        "boxes": [
                            {
                                "frame_id": 0,
                                "bbox_xyxy_normalized": [0.1, 0.2, 0.3, 0.4],
                                "score": 0.5,
                            },
                            {
                                "frame_id": 10,
                                "bbox_xyxy_normalized": [0.3, 0.4, 0.5, 0.6],
                                "score": 0.9,
                            },
                        ],
                    },
                }
            ]
        }

    def test_exact_detection_is_not_marked_interpolated(self):
        tracks = MODULE.build_tracks(self.graph())
        overlays = MODULE.overlays_for_frame(tracks, 0, "interpolate")
        self.assertEqual(len(overlays), 1)
        self.assertFalse(overlays[0].interpolated)
        self.assertEqual(overlays[0].bbox, (0.1, 0.2, 0.3, 0.4))

    def test_interpolation_is_labelled_and_linear(self):
        tracks = MODULE.build_tracks(self.graph())
        overlays = MODULE.overlays_for_frame(tracks, 5, "interpolate")
        self.assertEqual(len(overlays), 1)
        self.assertTrue(overlays[0].interpolated)
        for actual, expected in zip(overlays[0].bbox, (0.2, 0.3, 0.4, 0.5)):
            self.assertAlmostEqual(actual, expected)
        self.assertAlmostEqual(overlays[0].score, 0.7)

    def test_exact_mode_does_not_invent_boxes(self):
        tracks = MODULE.build_tracks(self.graph())
        self.assertEqual(MODULE.overlays_for_frame(tracks, 5, "exact"), [])
        self.assertEqual(MODULE.overlays_for_frame(tracks, 11, "interpolate"), [])

    def test_interpolation_does_not_cross_explicit_detector_miss(self):
        graph = self.graph()
        graph["entities"][0]["evidence_frame_ids"] = [0, 5, 10]
        tracks = MODULE.build_tracks(graph)
        self.assertEqual(MODULE.overlays_for_frame(tracks, 3, "interpolate"), [])
        self.assertEqual(MODULE.overlays_for_frame(tracks, 7, "interpolate"), [])

    def test_interpolation_rejects_incompatible_endpoint_scales(self):
        graph = self.graph()
        graph["entities"][0]["grounding"]["boxes"][0][
            "bbox_xyxy_normalized"
        ] = [0.1, 0.1, 0.2, 0.2]
        graph["entities"][0]["grounding"]["boxes"][1][
            "bbox_xyxy_normalized"
        ] = [0.1, 0.1, 0.7, 0.7]
        tracks = MODULE.build_tracks(graph)
        self.assertEqual(MODULE.overlays_for_frame(tracks, 5, "interpolate"), [])

    def test_interpolation_rejects_large_center_jump(self):
        graph = self.graph()
        graph["entities"][0]["grounding"]["boxes"][0][
            "bbox_xyxy_normalized"
        ] = [0.0, 0.0, 0.1, 0.1]
        graph["entities"][0]["grounding"]["boxes"][1][
            "bbox_xyxy_normalized"
        ] = [0.9, 0.9, 1.0, 1.0]
        tracks = MODULE.build_tracks(graph)
        self.assertEqual(MODULE.overlays_for_frame(tracks, 5, "interpolate"), [])

    def test_duplicate_entity_frame_is_rejected(self):
        graph = self.graph()
        duplicate = dict(graph["entities"][0]["grounding"]["boxes"][0])
        graph["entities"][0]["grounding"]["boxes"].append(duplicate)
        with self.assertRaisesRegex(MODULE.RenderError, "Duplicate grounding box"):
            MODULE.build_tracks(graph)

    def test_overlay_changes_image_pixels(self):
        image = Image.new("RGB", (100, 80), (255, 255, 255))
        overlay = MODULE.OverlayBox(
            "e1", "cup", (0.1, 0.2, 0.3, 0.4), 0.8, False
        )
        MODULE.draw_overlays(image, [overlay], {"e1": (255, 0, 0)})
        self.assertNotEqual(image.getpixel((10, 16)), (255, 255, 255))


if __name__ == "__main__":
    unittest.main()
