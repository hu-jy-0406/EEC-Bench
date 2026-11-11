"""Pixel reconstruction and provenance checks for candidate-independent views."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from original_pixel_views import build_views  # noqa: E402


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class OriginalPixelViewsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def source(self, name, size):
        path = self.root / name
        image = Image.new("RGB", size)
        for y in range(size[1]):
            for x in range(size[0]):
                image.putpixel((x, y), ((31*x+7*y) % 256, (13*x+47*y) % 256, (59*x+19*y) % 256))
        image.save(path, format="JPEG", quality=95, subsampling=0)
        return path

    def assert_rejected(self, frames):
        output = self.root / "rejected"
        with self.assertRaises((TypeError, ValueError, OSError)):
            build_views(frames, output)
        self.assertFalse(output.exists())

    def test_every_pixel_reconstructs_odd_nonsquare_sources_and_order(self):
        paths = [self.source("wide.jpg", (9, 7)), self.source("tall.jpg", (5, 11))]
        before = {p: p.read_bytes() for p in paths}
        frames = [{"frame_id": 17, "path": str(paths[0])}, {"frame_id": 3, "path": str(paths[1])}]
        manifest = build_views(frames, self.root / "views")
        self.assertEqual(json.loads(json.dumps(manifest)), manifest)
        self.assertTrue(manifest["protocol_version"])
        self.assertTrue(manifest["instructions"])
        views = manifest["views"]
        self.assertEqual(len(views), 10)
        self.assertEqual([v["frame_id"] for v in views], [17, 3, 17, 17, 17, 17, 3, 3, 3, 3])
        self.assertEqual([v["kind"] for v in views], ["original"]*2 + ["crop"]*8)
        self.assertEqual(manifest["attachments"], [v["path"] for v in views])
        self.assertEqual(len(set(manifest["attachments"])), 10)
        self.assertEqual(len({v["view_id"] for v in views}), 10)
        for i, view in enumerate(views, 1):
            self.assertEqual(view["attachment_index"], i)
            self.assertTrue(Path(view["path"]).is_absolute())
            self.assertEqual(view["sha256"], digest(view["path"]))
        for index, (path, frame) in enumerate(zip(paths, frames)):
            with Image.open(path) as encoded:
                original = encoded.copy()
            width, height = original.size
            source_hash = hashlib.sha256(before[path]).hexdigest()
            full = views[index]
            self.assertEqual(full["path"], str(path.resolve()))
            self.assertEqual(full["crop_xyxy"], [0, 0, width, height])
            self.assertEqual(full["scale"], 1)
            x_ranges = [(0, (9*width+15)//16), (7*width//16, width)]
            y_ranges = [(0, (9*height+15)//16), (7*height//16, height)]
            boxes = [[x0, y0, x1, y1] for y0, y1 in y_ranges for x0, x1 in x_ranges]
            crops = views[2+4*index:6+4*index]
            self.assertEqual([v["crop_xyxy"] for v in crops], boxes)
            self.assertGreater(x_ranges[0][1], x_ranges[1][0])
            self.assertGreater(y_ranges[0][1], y_ranges[1][0])
            covered = set()
            reconstructed = Image.new(original.mode, original.size)
            for record in [full, *crops]:
                self.assertEqual(record["source_sha256"], source_hash)
                self.assertEqual(record["source_path"], str(path.resolve()))
                self.assertEqual(record["source_size"], [width, height])
                self.assertEqual(record["frame_id"], frame["frame_id"])
            for record, (x0, y0, x1, y1) in zip(crops, boxes):
                self.assertEqual(record["scale"], 2)
                self.assertEqual(record["output_size"], [2*(x1-x0), 2*(y1-y0)])
                with Image.open(record["path"]) as crop:
                    self.assertEqual(crop.format, "PNG")
                    self.assertEqual(list(crop.size), record["output_size"])
                    for y in range(crop.height):
                        for x in range(crop.width):
                            position = (x0+x//2, y0+y//2)
                            self.assertEqual(crop.getpixel((x, y)), original.getpixel(position))
                            reconstructed.putpixel(position, crop.getpixel((x, y)))
                            covered.add(position)
            self.assertEqual(covered, {(x, y) for x in range(width) for y in range(height)})
            self.assertEqual(reconstructed.tobytes(), original.tobytes())
            self.assertEqual(path.read_bytes(), before[path])

    def test_existing_output_is_never_overwritten(self):
        path = self.source("source.jpg", (7, 5))
        for name, occupied in [("empty", False), ("occupied", True)]:
            output = self.root / name
            output.mkdir()
            if occupied:
                (output / "keep.txt").write_text("existing artifact")
            before = {p.name: p.read_bytes() for p in output.iterdir()}
            with self.assertRaises(FileExistsError):
                build_views([{"frame_id": 0, "path": str(path)}], output)
            self.assertEqual({p.name: p.read_bytes() for p in output.iterdir()}, before)

    def test_invalid_records_hashes_and_duplicate_ids_leave_no_output(self):
        path = self.source("source.jpg", (7, 5))
        valid = {"frame_id": 0, "path": str(path)}
        for frames in (None, [], (), "invalid", [None], [{}], [{"frame_id": 1}], [valid, valid]):
            with self.subTest(frames=frames):
                self.assert_rejected(frames)
        for value in (True, False, -1, 1.5, "1", None):
            self.assert_rejected([valid, {"frame_id": value, "path": str(path)}])
        self.assert_rejected([{**valid, "sha256": "0"*64}])
        build_views([{**valid, "sha256": digest(path)}], self.root / "verified")

    def test_missing_corrupt_and_truncated_images_leave_no_output(self):
        source = self.source("valid.jpg", (7, 5))
        corrupt = self.root / "corrupt.jpg"
        corrupt.write_bytes(b"not an image")
        truncated = self.root / "truncated.jpg"
        truncated.write_bytes(source.read_bytes()[:30])
        for path in (self.root / "missing.jpg", corrupt, truncated, self.root):
            self.assert_rejected([{"frame_id": 0, "path": str(source)}, {"frame_id": 1, "path": str(path)}])

    def test_transparency_is_preserved_without_rgb_conversion(self):
        path = self.root / "alpha.png"
        source = Image.new("RGBA", (5, 7), (11, 23, 47, 61))
        source.putpixel((2, 3), (131, 113, 79, 0))
        source.save(path)
        manifest = build_views([{"frame_id": 0, "path": str(path)}], self.root / "alpha_views")
        for view in manifest["views"][1:]:
            x0, y0, _, _ = view["crop_xyxy"]
            with Image.open(view["path"]) as crop:
                self.assertEqual(crop.mode, "RGBA")
                for y in range(crop.height):
                    for x in range(crop.width):
                        self.assertEqual(crop.getpixel((x, y)), source.getpixel((x0+x//2, y0+y//2)))


if __name__ == "__main__":
    unittest.main()
