"""Synthetic images only; no real dataset, model or pipeline changes."""
from copy import deepcopy
import hashlib
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import image_canvas_coordinates as M  # noqa: E402


class ImageCanvasCoordinatesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def image(self, size=(5, 3), mode="RGB", name="source.png"):
        path = self.root / name
        image = Image.new(mode, size)
        if mode == "RGB":
            image.putdata([(x * 29 % 256, y * 71 % 256, (x + y) * 17 % 256)
                           for y in range(size[1]) for x in range(size[0])])
        image.save(path)
        return path

    def test_default_power_two_odd_padding_and_exact_pixels(self):
        source = self.image()
        before = source.read_bytes()
        output = self.root / "canvas.png"
        manifest = M.write_square_canvas(source, output, padding_rgb=[19, 23, 29])
        self.assertEqual(manifest["source_size"], [5, 3])
        self.assertEqual(manifest["canvas_size"], [8, 8])
        self.assertEqual(manifest["offset_xy"], [1, 2])
        self.assertEqual(manifest["content_rect_xyxy"], [1, 2, 6, 5])
        self.assertEqual(source.read_bytes(), before)
        with Image.open(source) as src, Image.open(output) as dst:
            self.assertEqual(dst.crop((1, 2, 6, 5)).tobytes(), src.tobytes())
            for y in range(8):
                for x in range(8):
                    if not (1 <= x < 6 and 2 <= y < 5):
                        self.assertEqual(dst.getpixel((x, y)), (19, 23, 29))
            self.assertEqual(manifest["source"]["decoded_rgb_sha256"],
                             hashlib.sha256(src.tobytes()).hexdigest())
            self.assertEqual(manifest["canvas"]["decoded_rgb_sha256"],
                             hashlib.sha256(dst.tobytes()).hexdigest())
        self.assertEqual(manifest["source"]["encoded_sha256"], hashlib.sha256(before).hexdigest())
        self.assertEqual(manifest["canvas"]["encoded_sha256"],
                         hashlib.sha256(output.read_bytes()).hexdigest())
        self.assertEqual(manifest["source"]["conversion"], "none")
        self.assertEqual(manifest["source"]["mode"], "RGB")
        self.assertEqual(manifest["padding_rgb"], [19, 23, 29])
        self.assertEqual(list(self.root.glob(".image_canvas_*")), [])

    def test_square_and_minimum_and_non_power_explicit_side(self):
        for size, side, expected in [([1, 1], None, 1), ([4, 4], None, 4),
                                     ([3, 3], None, 4), ([5, 3], 7, 7),
                                     ([5, 3], 5, 5), ([255, 127], None, 256),
                                     ([256, 127], None, 256), ([257, 127], None, 512),
                                     ([1048577, 511], None, 2097152)]:
            with self.subTest(size=size, side=side):
                g = M.canvas_geometry(size, side=side)
                self.assertEqual(g["canvas_size"], [expected, expected])
                full = M.source_to_canvas_bbox([0, 0, 1, 1], g)
                self.assertEqual(M.canvas_to_source_bbox(full, g), [0, 0, 1, 1])
        source = self.image((4, 4))
        m = M.write_square_canvas(source, self.root / "square.png")
        self.assertEqual(m["offset_xy"], [0, 0])
        self.assertEqual(m["source"]["decoded_rgb_sha256"], m["canvas"]["decoded_rgb_sha256"])

    def test_encoded_input_is_not_claimed_equal_to_png(self):
        source = self.image(name="source.bmp")
        m = M.write_square_canvas(source, self.root / "converted.png", side=7)
        self.assertEqual(m["source"]["format"], "BMP")
        self.assertEqual(m["canvas"]["format"], "PNG")
        self.assertNotEqual(m["source"]["encoded_sha256"], m["canvas"]["encoded_sha256"])
        with Image.open(source) as src, Image.open(m["canvas"]["path"]) as canvas:
            self.assertEqual(canvas.crop(tuple(m["content_rect_xyxy"])).tobytes(), src.tobytes())

    def test_invalid_size_side_or_padding_creates_no_output(self):
        for size in [None, [], [1], [0, 3], [-1, 3], [True, 3], [3.0, 3]]:
            with self.subTest(size=size), self.assertRaises(ValueError):
                M.canvas_geometry(size)
        source = self.image()
        for side in [0, -1, 4, True, 8.0, "8"]:
            with self.subTest(side=side), self.assertRaises(ValueError):
                M.write_square_canvas(source, self.root / "bad.png", side=side)
        for padding in [None, [0, 0], [0, 0, 256], [False, 0, 0], [0, 0.0, 0]]:
            with self.subTest(padding=padding), self.assertRaises(ValueError):
                M.write_square_canvas(source, self.root / "bad.png", padding_rgb=padding)
        self.assertFalse((self.root / "bad.png").exists())

    def test_alpha_non_rgb_and_oriented_inputs_are_not_silently_changed(self):
        for mode in ["RGBA", "LA", "L", "P"]:
            source = self.image(mode=mode, name=mode + ".png")
            before = source.read_bytes()
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "RGB"):
                M.write_square_canvas(source, self.root / "bad.png")
            self.assertEqual(source.read_bytes(), before)
        exif = Image.Exif()
        exif[274] = 6
        source = self.root / "rotated.jpg"
        Image.new("RGB", (5, 3)).save(source, exif=exif)
        with self.assertRaisesRegex(ValueError, "orientation"):
            M.write_square_canvas(source, self.root / "bad.png")
        self.assertFalse((self.root / "bad.png").exists())

    def test_multiframe_and_truncated_inputs_fail_without_output(self):
        source = self.root / "animation.tiff"
        Image.new("RGB", (3, 2)).save(source, save_all=True,
                                     append_images=[Image.new("RGB", (3, 2), "red")])
        with self.assertRaisesRegex(ValueError, "frame"):
            M.write_square_canvas(source, self.root / "bad.png")
        source = self.root / "truncated.png"
        source.write_bytes(b"\x89PNG\r\n\x1a\n")
        with self.assertRaises(OSError):
            M.write_square_canvas(source, self.root / "bad.png")
        self.assertFalse((self.root / "bad.png").exists())

    def test_existing_same_path_symlink_and_output_format_are_safe(self):
        source = self.image()
        before = source.read_bytes()
        output = self.root / "existing.png"
        output.write_bytes(b"keep existing bytes")
        with self.assertRaises(FileExistsError):
            M.write_square_canvas(source, output)
        with self.assertRaises(ValueError):
            M.write_square_canvas(source, source)
        alias = self.root / "alias.png"
        alias.symlink_to(source)
        with self.assertRaises(ValueError):
            M.write_square_canvas(source, alias)
        with self.assertRaises(ValueError):
            M.write_square_canvas(source, self.root / "bad.jpg")
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(output.read_bytes(), b"keep existing bytes")
        self.assertTrue(alias.is_symlink())

    def test_failed_encoding_cleans_only_own_temporary(self):
        source = self.image()
        keep = self.root / ".image_canvas_existing.png"
        keep.write_bytes(b"untouched")
        def fail(_image, stream, **_kwargs):
            stream.write(b"partial")
            raise OSError("injected save failure")
        with mock.patch.object(Image.Image, "save", fail), self.assertRaises(OSError):
            M.write_square_canvas(source, self.root / "failed.png")
        self.assertFalse((self.root / "failed.png").exists())
        self.assertEqual(list(self.root.glob(".image_canvas_*")), [keep])
        self.assertEqual(keep.read_bytes(), b"untouched")

    def test_publication_race_keeps_existing_file_and_cleans_temporary(self):
        source = self.image()
        before = source.read_bytes()
        output = self.root / "race.png"
        def occupied(_temporary, destination):
            Path(destination).write_bytes(b"other owner")
            raise FileExistsError(destination)
        with mock.patch.object(M.os, "link", side_effect=occupied), self.assertRaises(FileExistsError):
            M.write_square_canvas(source, output)
        self.assertEqual(output.read_bytes(), b"other owner")
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(list(self.root.glob(".image_canvas_*")), [])

    def test_published_cleanup_failure_retains_complete_manifest_and_output(self):
        source = self.image()
        before = source.read_bytes()
        output = self.root / "published.png"
        keep = self.root / ".image_canvas_existing.png"
        keep.write_bytes(b"unrelated")
        cleanup_error = OSError("injected unlink failure")
        attempted = []

        def fail_cleanup(path, **_kwargs):
            attempted.append(path)
            raise cleanup_error

        with mock.patch.object(Path, "unlink", autospec=True, side_effect=fail_cleanup):
            with self.assertRaises(M.CanvasPublishedCleanupError) as raised:
                M.write_square_canvas(source, output)
        error = raised.exception
        self.assertTrue(error.published)
        self.assertIs(error.__cause__, cleanup_error)
        self.assertEqual(attempted, [error.temporary_path])
        self.assertNotIn(error.temporary_path, [source, output, keep])
        self.assertTrue(error.temporary_path.exists())
        self.assertTrue(output.samefile(error.temporary_path))
        self.assertEqual(error.manifest["canvas"]["path"], str(output))
        self.assertEqual(error.manifest["canvas"]["encoded_sha256"],
                         hashlib.sha256(output.read_bytes()).hexdigest())
        with Image.open(source) as src, Image.open(output) as canvas:
            self.assertEqual(canvas.crop(tuple(error.manifest["content_rect_xyxy"])).tobytes(),
                             src.tobytes())
            self.assertEqual(error.manifest["canvas"]["decoded_rgb_sha256"],
                             hashlib.sha256(canvas.tobytes()).hexdigest())
        self.assertEqual(M.canvas_to_source_bbox(
            M.source_to_canvas_bbox([0, 0, 1, 1], error.manifest), error.manifest), [0, 0, 1, 1])
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(keep.read_bytes(), b"unrelated")

    def test_prepublication_cleanup_error_never_masks_original_failure_or_cause(self):
        source = self.image()
        before = source.read_bytes()
        for stage in ["encoding", "publication"]:
            output = self.root / (stage + ".png")
            original_error = OSError("original " + stage + " failure")
            original_cause = ValueError("original cause")
            attempted = []

            def fail_operation(*_args, **_kwargs):
                if stage == "publication":
                    output.write_bytes(b"other publisher")
                raise original_error from original_cause

            def fail_cleanup(path, **_kwargs):
                attempted.append(path)
                raise OSError("secondary cleanup failure")

            target, attribute = ((Image.Image, "save") if stage == "encoding"
                                 else (M.os, "link"))
            with self.subTest(stage=stage):
                with mock.patch.object(target, attribute, side_effect=fail_operation):
                    with mock.patch.object(Path, "unlink", autospec=True, side_effect=fail_cleanup):
                        with self.assertRaises(OSError) as raised:
                            M.write_square_canvas(source, output)
                self.assertIs(raised.exception, original_error)
                self.assertIs(original_error.__cause__, original_cause)
                self.assertEqual(len(attempted), 1)
                self.assertTrue(attempted[0].exists())
                self.assertNotIn(attempted[0], [source, output])
                self.assertIn(str(attempted[0]), original_error.__notes__[0])
                self.assertIn("secondary cleanup failure", original_error.__notes__[0])
                if stage == "publication":
                    self.assertEqual(output.read_bytes(), b"other publisher")
                else:
                    self.assertFalse(output.exists())
                self.assertEqual(source.read_bytes(), before)

    def test_bidirectional_roundtrip_and_manifest_immutability(self):
        source = self.image()
        m = M.write_square_canvas(source, self.root / "canvas.png", side=11)
        for box in [[0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9], [0, 0.999, 0.001, 1],
                    [1e-8, 1e-8, 1 - 1e-8, 1 - 1e-8]]:
            before = deepcopy((box, m))
            mapped = M.source_to_canvas_bbox(box, m)
            returned = M.canvas_to_source_bbox(mapped, m)
            for actual, expected in zip(returned, box):
                self.assertAlmostEqual(actual, expected, places=14)
            self.assertEqual((box, m), before)
            again = M.source_to_canvas_bbox(returned, m)
            for actual, expected in zip(again, mapped):
                self.assertAlmostEqual(actual, expected, places=14)

    def test_coordinate_units_and_full_content_edges(self):
        g = M.canvas_geometry([5, 3], side=8)
        self.assertEqual(M.source_to_canvas_bbox([0, 0, 1, 1], g),
                         [1 / 8, 2 / 8, 6 / 8, 5 / 8])
        self.assertEqual(M.source_to_canvas_bbox([0.2, 1 / 3, 0.8, 2 / 3], g),
                         [2 / 8, 3 / 8, 5 / 8, 4 / 8])
        g = M.canvas_geometry([5, 3], side=7)
        full = M.source_to_canvas_bbox([0, 0, 1, 1], g)
        self.assertEqual(M.canvas_to_source_bbox(full, g), [0, 0, 1, 1])

    def test_padding_intersection_even_one_float_step_is_not_clipped(self):
        g = M.canvas_geometry([5, 3], side=7)
        full = M.source_to_canvas_bbox([0, 0, 1, 1], g)
        for index, direction in [(0, -math.inf), (1, -math.inf),
                                 (2, math.inf), (3, math.inf)]:
            box = full.copy()
            box[index] = math.nextafter(box[index], direction)
            before = deepcopy((box, g))
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, "content"):
                M.canvas_to_source_bbox(box, g)
            self.assertEqual((box, g), before)
        with self.assertRaises(ValueError):
            M.canvas_to_source_bbox([0, 0, 1, 1], g)
        with self.assertRaises(ValueError):
            M.canvas_to_source_bbox([0, 0, 0.1, 0.1], g)
        # Equivalent real-number expressions are not necessarily the same float.
        # Keep the existing strict bound rather than silently swallowing padding.
        equivalent = full.copy()
        equivalent[2] = 1 / 7 + 5 / 7
        self.assertEqual(equivalent[2], math.nextafter(full[2], math.inf))
        with self.assertRaisesRegex(ValueError, "content"):
            M.canvas_to_source_bbox(equivalent, g)

    def test_bad_or_null_boxes_are_never_repaired(self):
        g = M.canvas_geometry([4, 4])
        bad = [None, [], [0, 0, 1], [0, 0, 0, 1], [1, 0, 0, 1],
               [-1e-12, 0, 1, 1], [0, 0, 1 + 1e-12, 1], [False, 0, 1, 1],
               [0, 0, math.inf, 1], [0, math.nan, 1, 1], ["0", 0, 1, 1]]
        for box in bad:
            for convert in (M.source_to_canvas_bbox, M.canvas_to_source_bbox):
                with self.subTest(box=box, convert=convert.__name__), self.assertRaises(ValueError):
                    convert(box, g)

    def test_tampered_geometry_cannot_change_the_mapping(self):
        original = M.canvas_geometry([5, 3], side=8)
        changes = [("geometry_policy_version", "unknown"), ("source_size", [6, 3]),
                   ("source_size", [5.0, 3]), ("canvas_size", [8, 7]),
                   ("canvas_size", [8.0, 8]), ("offset_xy", [2, 2]),
                   ("offset_xy", [True, 2]), ("content_rect_xyxy", [1, 2, 7, 5]),
                   ("content_rect_xyxy", [1.0, 2, 6, 5]), ("resampling", "resize")]
        for key, value in changes:
            g = deepcopy(original)
            g[key] = value
            for convert in (M.source_to_canvas_bbox, M.canvas_to_source_bbox):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    convert([0, 0, 1, 1], g)
        for key in original:
            g = deepcopy(original)
            del g[key]
            with self.subTest(missing=key), self.assertRaises(ValueError):
                M.source_to_canvas_bbox([0, 0, 1, 1], g)


if __name__ == "__main__":
    unittest.main()
