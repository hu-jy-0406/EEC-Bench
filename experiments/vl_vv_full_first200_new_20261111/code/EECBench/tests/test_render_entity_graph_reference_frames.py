import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "render_entity_graph_reference_frames.py"
)
SCRIPTS_DIR = str(SCRIPT.parent)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
SPEC = importlib.util.spec_from_file_location(
    "render_entity_graph_reference_frames", SCRIPT
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class RenderEntityGraphReferenceFramesTest(unittest.TestCase):
    def test_writes_exact_detection_contact_sheet(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frames = root / "frames"
            frames.mkdir()
            Image.new("RGB", (80, 60), "white").save(frames / "frame_000000.jpg")
            Image.new("RGB", (80, 60), "white").save(frames / "frame_000010.jpg")
            graph = {
                "shot_metadata": {
                    "fps": 10.0,
                    "reference_frame_ids": [0, 10],
                },
                "entities": [
                    {
                        "id": "e1",
                        "name": "cup",
                        "grounding": {
                            "status": "grounded",
                            "query": "cup",
                            "boxes": [
                                {
                                    "frame_id": 0,
                                    "bbox_xyxy_normalized": [0.1, 0.1, 0.5, 0.5],
                                    "score": 0.8,
                                },
                                {
                                    "frame_id": 10,
                                    "bbox_xyxy_normalized": [0.2, 0.2, 0.6, 0.6],
                                    "score": 0.9,
                                },
                            ],
                        },
                    }
                ],
            }
            graph_path = root / "graph.json"
            graph_path.write_text(json.dumps(graph), encoding="utf-8")
            output = root / "sheet.png"
            annotated = root / "grounded"

            frame_count, detection_count = MODULE.render_reference_sheet(
                graph_path, frames, output, columns=2, annotated_dir=annotated
            )

            self.assertEqual(frame_count, 2)
            self.assertEqual(detection_count, 2)
            self.assertTrue(output.is_file())
            self.assertTrue((annotated / "frame_000000.grounded.jpg").is_file())
            self.assertTrue((annotated / "frame_000010.grounded.jpg").is_file())
            with Image.open(output) as image:
                self.assertEqual(image.size, (160, 86))


if __name__ == "__main__":
    unittest.main()
