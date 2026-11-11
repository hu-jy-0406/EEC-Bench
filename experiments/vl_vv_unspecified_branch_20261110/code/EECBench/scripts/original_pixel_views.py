"""Deterministic context-preserving views of existing pixels, independent of proposals."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
from pathlib import Path

from PIL import Image

PROTOCOL_VERSION = "original_pixel_fixed_grid_views_v0.1"
INSTRUCTIONS = (
    "Every derived view shows existing pixels from its named original frame. "
    "All original full frames remain attached first; use them to check full-object "
    "scope and continuity across the fixed overlapping quadrants. Crops were "
    "chosen only from image dimensions, without candidate locations or names. "
    "Nearest-neighbor 2x scaling repeats decoded pixels and adds no information "
    "or detail. No sharpening, generated pixels, or drawn boundaries were used. "
    "A crop edge is not a physical object boundary. Overlapping views are not "
    "independent evidence or additional frames. Cite original frame IDs, retain "
    "uncertainty when original pixels do not resolve identity, and never infer "
    "a second object from a crop edge or intrinsic depicted content. "
    "crop_xyxy uses half-open original-pixel coordinates; all sizes are [width,height]."
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _quadrants(width: int, height: int):
    left_end = (9 * width + 15) // 16
    right_start = 7 * width // 16
    top_end = (9 * height + 15) // 16
    bottom_start = 7 * height // 16
    return (
        (0, 0, left_end, top_end),
        (right_start, 0, width, top_end),
        (0, bottom_start, left_end, height),
        (right_start, bottom_start, width, height),
    )


def build_views(reference_frames: Sequence[Mapping], output_dir: Path | str) -> dict:
    """Return ordered attachment records without changing or copying source images.

    Input order is preserved. Every original comes first, followed by each
    frame's four row-major crops. Validate inputs before creating a new output
    directory; never overwrite an existing directory or file.
    """
    if isinstance(reference_frames, (str, bytes)) or not isinstance(reference_frames, Sequence):
        raise ValueError("reference_frames must be a nonempty ordered sequence")
    if not reference_frames:
        raise ValueError("reference_frames must not be empty")
    destination = Path(output_dir).absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    seen = set()
    sources = []
    for frame in reference_frames:
        if not isinstance(frame, Mapping):
            raise ValueError("Each frame must be a mapping")
        frame_id = frame.get("frame_id")
        if type(frame_id) is not int or frame_id < 0 or frame_id in seen:
            raise ValueError("frame_id must be a unique nonnegative integer")
        seen.add(frame_id)
        raw_path = frame.get("path")
        if not isinstance(raw_path, (str, Path)) or not str(raw_path):
            raise ValueError("Each frame needs a nonempty image path")
        path = Path(raw_path).resolve(strict=True)
        if not path.is_file():
            raise ValueError(f"Source is not a file: {path}")
        digest = _sha(path)
        if "sha256" in frame and frame["sha256"] != digest:
            raise ValueError(f"Source hash mismatch: {path}")
        with Image.open(path) as source:
            if source.mode not in {"RGB", "RGBA", "L", "LA", "P", "1"}:
                raise ValueError(f"Unsupported lossless PNG channel representation: {source.mode}")
            source.load()
            size = list(source.size)
        sources.append({"frame_id": frame_id, "path": path, "sha256": digest, "size": size})
    destination.mkdir(parents=True, exist_ok=False)
    views = []
    for source in sources:
        width, height = source["size"]
        views.append({
            "attachment_index": len(views) + 1,
            "view_id": f"frame_{source['frame_id']}_original", "frame_id": source["frame_id"],
            "kind": "original", "path": str(source["path"]),
            "source_path": str(source["path"]), "source_sha256": source["sha256"],
            "source_size": source["size"], "crop_xyxy": [0, 0, width, height],
            "scale": 1, "output_size": source["size"], "sha256": source["sha256"],
        })
    for source in sources:
        width, height = source["size"]
        with Image.open(source["path"]) as encoded:
            decoded = encoded.copy()
            for index, crop_box in enumerate(_quadrants(width, height), start=1):
                view_id = f"frame_{source['frame_id']}_grid_{index}"
                path = destination / f"{view_id}.png"
                cropped = decoded.crop(crop_box)
                output_size = [cropped.width * 2, cropped.height * 2]
                enlarged = cropped.resize(output_size, resample=Image.Resampling.NEAREST)
                enlarged.save(path, format="PNG")
                views.append({
                    "attachment_index": len(views) + 1,
                    "view_id": view_id, "frame_id": source["frame_id"], "kind": "crop",
                    "path": str(path), "source_path": str(source["path"]),
                    "source_sha256": source["sha256"], "source_size": source["size"],
                    "crop_xyxy": list(crop_box), "scale": 2,
                    "output_size": output_size, "sha256": _sha(path),
                })
    for source in sources:
        if _sha(source["path"]) != source["sha256"]:
            raise RuntimeError(f"Source changed while deriving views: {source['path']}")
    return {
        "protocol_version": PROTOCOL_VERSION,
        "attachments": [view["path"] for view in views],
        "views": views, "instructions": INSTRUCTIONS,
    }
