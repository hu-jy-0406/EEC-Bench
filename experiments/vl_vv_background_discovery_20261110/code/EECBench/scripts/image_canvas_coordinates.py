"""Isolated, unresampled RGB square canvases and normalized coordinate maps.

No model, prompt, selection or acceptance policy is implemented here. The image
writer returns a private manifest; its caller decides whether/how to persist it.
Only single-frame RGB images with no nontrivial EXIF orientation are accepted.
Decoded RGB pixels are preserved, not the source's encoded bytes or metadata.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from fractions import Fraction
import hashlib
from io import BytesIO
import math
import os
from pathlib import Path
import tempfile

from PIL import Image


POLICY_VERSION = "image_canvas_coordinates_v0.1"
DEFAULT_PADDING_RGB = (127, 127, 127)


class CanvasPublishedCleanupError(RuntimeError):
    """The complete output exists, but its temporary hard link was not removed.

    ``manifest`` describes the published file. ``temporary_path`` names only the
    temporary file created by this invocation; neither path is removed here.
    The original cleanup OSError is retained as the exception's explicit cause.
    """

    def __init__(self, manifest, temporary_path):
        self.published = True
        self.manifest = deepcopy(manifest)
        self.temporary_path = Path(temporary_path)
        super().__init__(f"Canvas published; temporary cleanup failed: {temporary_path}")


def _sha256(value):
    return hashlib.sha256(value).hexdigest()


def _size(value):
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or any(type(x) is not int or x <= 0 for x in value)):
        raise ValueError("Size must contain two positive integer dimensions")
    return tuple(value)


def canvas_geometry(source_size, *, side=None) -> dict:
    """Center the source, assigning an odd extra padding pixel to right/bottom.

    The default side is the smallest power of two covering both dimensions.
    An explicit side can be any positive integer covering the complete source.
    There is no resizing, cropping, rotation or per-axis scaling.
    """
    width, height = _size(source_size)
    if side is None:
        side = 1 << (max(width, height) - 1).bit_length()
    if type(side) is not int or side < max(width, height):
        raise ValueError("Canvas side must be an integer covering the source")
    left, top = (side - width) // 2, (side - height) // 2
    return {
        "geometry_policy_version": POLICY_VERSION,
        "source_size": [width, height],
        "canvas_size": [side, side],
        "offset_xy": [left, top],
        "content_rect_xyxy": [left, top, left + width, top + height],
        "resampling": "none",
    }


def _geometry(value):
    """Recompute every geometric field; manifests can include asset metadata."""
    if not isinstance(value, Mapping):
        raise ValueError("Geometry or canvas manifest must be a mapping")
    side, other = _size(value.get("canvas_size"))
    if side != other:
        raise ValueError("Canvas must be square")
    expected = canvas_geometry(value.get("source_size"), side=side)
    for key in ("offset_xy", "content_rect_xyxy"):
        actual = value.get(key)
        if (not isinstance(actual, (list, tuple)) or len(actual) != len(expected[key])
                or any(type(x) is not int for x in actual)
                or list(actual) != expected[key]):
            raise ValueError(f"Invalid or inconsistent {key}")
    if (value.get("geometry_policy_version") != POLICY_VERSION
            or value.get("resampling") != "none"):
        raise ValueError("Unknown geometry policy or resampling")
    return expected


def _box(value):
    # Null means unknown geometry, which the caller must preserve separately.
    if (not isinstance(value, (list, tuple)) or len(value) != 4
            or any(type(x) not in (int, float)
                   or (type(x) is float and not math.isfinite(x)) for x in value)
            or not (0 <= value[0] < value[2] <= 1)
            or not (0 <= value[1] < value[3] <= 1)):
        raise ValueError("A finite non-bool positive-area normalized bbox is required")
    return [Fraction(x) for x in value]


def source_to_canvas_bbox(bbox, geometry) -> list[float]:
    """Translate source-normalized xyxy to canvas-normalized xyxy.

    Rational arithmetic is used before the final float representation. This is
    an affine geometry map, not a claim of bit-exact floating-point roundtrips.
    Boxes too small to retain positive area in output floats are rejected.
    """
    g, values = _geometry(geometry), _box(bbox)
    width, height = g["source_size"]
    side = g["canvas_size"][0]
    left, top = g["offset_xy"]
    mapped = [float((v * length + offset) / side)
              for v, length, offset in zip(values, (width, height, width, height),
                                           (left, top, left, top))]
    _box(mapped)
    return mapped


def canvas_to_source_bbox(bbox, geometry) -> list[float]:
    """Map a wholly in-content canvas-normalized box back to the source.

    Padding intersections are errors, never clipped. Bounds use the same float
    representations produced by the forward map. Exact equality to a represented
    content edge maps to exactly 0/1; there is no epsilon or tolerance allowance.
    An external equivalent expression can round one ULP outside this bound (for
    example 1/7 + 5/7 versus float(6/7)) and is deliberately rejected as well.
    """
    g, values = _geometry(geometry), _box(bbox)
    width, height = g["source_size"]
    side = g["canvas_size"][0]
    left, top = g["offset_xy"]
    bounds = source_to_canvas_bbox([0, 0, 1, 1], g)
    if not (bounds[0] <= bbox[0] < bbox[2] <= bounds[2]
            and bounds[1] <= bbox[1] < bbox[3] <= bounds[3]):
        raise ValueError("Canvas bbox extends outside the original content rectangle")
    mapped = []
    for i, (v, length, offset) in enumerate(zip(
            values, (width, height, width, height), (left, top, left, top))):
        lower, upper = bounds[i % 2], bounds[i % 2 + 2]
        if bbox[i] == lower:
            mapped.append(0.0)
        elif bbox[i] == upper:
            mapped.append(1.0)
        else:
            mapped.append(float((v * side - offset) / length))
    _box(mapped)
    return mapped


def write_square_canvas(source_path, output_path, *, side=None,
                        padding_rgb=DEFAULT_PADDING_RGB) -> dict:
    """Write one new PNG atomically and return its geometry/asset manifest.

    RGB-only input avoids silently dropping transparency or changing color mode.
    The encoded source snapshot and decoded source/canvas RGB bytes are hashed
    separately. A same-directory temporary PNG is exclusively created, then a
    hard link publishes the complete file without replacing any existing path.
    Failed encoding/publication attempts to clean only this invocation's
    temporary file. If that cleanup also fails, the original exception is
    re-raised with an explanatory note. After successful publication, cleanup
    failure raises CanvasPublishedCleanupError with the complete manifest and
    published=True; the published output is retained. An exception must therefore
    not be interpreted as proof that the output path is absent.
    The caller must create the output parent directory. No source is written.
    """
    source_path = Path(source_path).absolute()
    output_path = Path(output_path).absolute()
    if source_path.resolve() == output_path.resolve():
        raise ValueError("Output must not be the source path")
    if output_path.suffix.lower() != ".png":
        raise ValueError("Only PNG output is supported")
    if os.path.lexists(output_path):
        raise FileExistsError(output_path)
    if (not isinstance(padding_rgb, (list, tuple)) or len(padding_rgb) != 3
            or any(type(x) is not int or not 0 <= x <= 255 for x in padding_rgb)):
        raise ValueError("Padding must contain three integer RGB channels")

    encoded_source = source_path.read_bytes()
    with Image.open(BytesIO(encoded_source)) as original:
        if getattr(original, "n_frames", 1) != 1:
            raise ValueError("Exactly one source image frame is required")
        orientation = original.getexif().get(274)
        if orientation is not None and (type(orientation) is not int or orientation != 1):
            raise ValueError("Nontrivial or invalid EXIF orientation is unsupported")
        if original.mode != "RGB":
            raise ValueError("Source must be RGB; alpha/color conversion is not implicit")
        original.load()
        source_format = original.format
        source_rgb = original.copy()
    geometry = canvas_geometry(list(source_rgb.size), side=side)
    canvas = Image.new("RGB", tuple(geometry["canvas_size"]), tuple(padding_rgb))
    canvas.paste(source_rgb, tuple(geometry["offset_xy"]))
    source_pixels = source_rgb.tobytes()
    if canvas.crop(tuple(geometry["content_rect_xyxy"])).tobytes() != source_pixels:
        raise RuntimeError("Canvas content does not preserve decoded RGB pixels")

    manifest = {
        **geometry,
        "padding_rgb": list(padding_rgb),
        "source": {"path": str(source_path), "format": source_format, "mode": "RGB",
                   "encoded_sha256": _sha256(encoded_source),
                   "decoded_rgb_sha256": _sha256(source_pixels),
                   "exif_orientation": orientation, "conversion": "none"},
        "canvas": {"path": str(output_path), "format": "PNG", "mode": "RGB",
                   "encoded_sha256": None, "decoded_rgb_sha256": _sha256(canvas.tobytes())},
        "decoded_rgb_content_equal": True,
        "rgb_hash_definition": "sha256 of row-major interleaved uint8 RGB pixel bytes",
    }
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w+b", dir=output_path.parent,
                                         prefix=".image_canvas_", suffix=".png",
                                         delete=False) as temporary:
            temporary_path = Path(temporary.name)
            canvas.save(temporary, format="PNG")
            temporary.flush()
            temporary.seek(0)
            encoded_canvas = temporary.read()
        # Verify the encoded PNG, not merely the pre-encoding in-memory canvas.
        with Image.open(BytesIO(encoded_canvas)) as decoded:
            decoded.load()
            if (decoded.format != "PNG" or decoded.mode != "RGB"
                    or decoded.size != canvas.size or decoded.tobytes() != canvas.tobytes()):
                raise RuntimeError("Encoded PNG did not preserve the RGB canvas")
        manifest["canvas"]["encoded_sha256"] = _sha256(encoded_canvas)
        os.link(temporary_path, output_path)  # EEXIST is fatal, never overwrite.
    except BaseException as original_error:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except OSError as cleanup_error:
                original_error.add_note(
                    f"Temporary cleanup also failed for {temporary_path}: {cleanup_error!r}"
                )
        raise
    try:
        temporary_path.unlink()
    except OSError as cleanup_error:
        raise CanvasPublishedCleanupError(manifest, temporary_path) from cleanup_error
    return manifest
