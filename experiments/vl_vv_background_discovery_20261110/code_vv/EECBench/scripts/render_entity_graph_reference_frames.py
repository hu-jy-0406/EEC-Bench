#!/usr/bin/env python3
"""Render exact GroundingDINO detections on sampled reference frames."""

from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path
from typing import Optional, Sequence

from PIL import Image, ImageDraw, ImageFont

from render_entity_graph_video import (
    PALETTE,
    RenderError,
    build_tracks,
    draw_overlays,
    load_graph,
    overlays_for_frame,
)


def render_reference_sheet(
    graph_path: Path,
    frame_dir: Path,
    output_path: Path,
    *,
    columns: int = 3,
    annotated_dir: Optional[Path] = None,
) -> tuple[int, int]:
    if columns <= 0:
        raise RenderError("columns must be positive")
    graph = load_graph(graph_path)
    metadata = graph.get("shot_metadata")
    if not isinstance(metadata, dict):
        raise RenderError("Entity graph must contain shot_metadata")
    frame_ids = metadata.get("reference_frame_ids")
    if not isinstance(frame_ids, list) or not frame_ids:
        raise RenderError("shot_metadata.reference_frame_ids must be a nonempty array")
    try:
        ordered_ids = [int(value) for value in frame_ids]
        fps = float(metadata["fps"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RenderError("Invalid reference-frame IDs or FPS in entity graph") from exc
    if len(set(ordered_ids)) != len(ordered_ids) or fps <= 0 or not math.isfinite(fps):
        raise RenderError("Reference-frame IDs must be unique and FPS must be positive")

    tracks = build_tracks(graph)
    color_by_entity = {
        entity_id: PALETTE[index % len(PALETTE)]
        for index, (entity_id, _, _, _) in enumerate(tracks)
    }
    font = ImageFont.load_default()
    header_height = 26
    rendered = []
    detection_count = 0
    expected_size = None
    if annotated_dir is not None:
        annotated_dir.mkdir(parents=True, exist_ok=True)
    for frame_id in ordered_ids:
        frame_path = frame_dir / f"frame_{frame_id:06d}.jpg"
        if not frame_path.is_file():
            raise RenderError(f"Missing sampled reference frame: {frame_path}")
        with Image.open(frame_path) as source:
            image = source.convert("RGB")
        if expected_size is None:
            expected_size = image.size
        elif image.size != expected_size:
            raise RenderError(
                f"Reference-frame dimensions differ: {image.size} != {expected_size}"
            )
        overlays = overlays_for_frame(tracks, frame_id, "exact")
        detection_count += len(overlays)
        draw_overlays(image, overlays, color_by_entity)

        if annotated_dir is not None:
            annotated_path = annotated_dir / f"frame_{frame_id:06d}.grounded.jpg"
            temporary_frame = annotated_path.with_name(
                f".{annotated_path.name}.tmp-{os.getpid()}"
            )
            image.save(temporary_frame, format="JPEG", quality=95)
            os.replace(temporary_frame, annotated_path)

        tile = Image.new("RGB", (image.width, image.height + header_height), "white")
        tile.paste(image, (0, header_height))
        label = f"frame {frame_id}  t={frame_id / fps:.3f}s  detections={len(overlays)}"
        ImageDraw.Draw(tile).text((8, 7), label, fill="black", font=font)
        rendered.append(tile)

    assert expected_size is not None
    used_columns = min(columns, len(rendered))
    rows = math.ceil(len(rendered) / used_columns)
    sheet = Image.new(
        "RGB",
        (used_columns * rendered[0].width, rows * rendered[0].height),
        (225, 225, 225),
    )
    for index, tile in enumerate(rendered):
        sheet.paste(
            tile,
            ((index % used_columns) * tile.width, (index // used_columns) * tile.height),
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.tmp-{os.getpid()}")
    sheet.save(temporary, format="PNG", optimize=True)
    os.replace(temporary, output_path)
    return len(rendered), detection_count


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a contact sheet of exact reference-frame detections."
    )
    parser.add_argument("graph", type=Path, help="Entity graph JSON")
    parser.add_argument("frame_dir", type=Path, help="Saved sampled-frame directory")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Output PNG")
    parser.add_argument(
        "--annotated-dir",
        type=Path,
        help="Also save each exact reference frame with grounding overlays",
    )
    parser.add_argument("--columns", type=int, default=3)
    args = parser.parse_args(argv)
    if args.columns <= 0:
        parser.error("--columns must be positive")
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        frames, detections = render_reference_sheet(
            args.graph.resolve(),
            args.frame_dir.resolve(),
            args.output.resolve(),
            columns=args.columns,
            annotated_dir=(
                args.annotated_dir.resolve() if args.annotated_dir else None
            ),
        )
    except (OSError, RenderError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        f"Wrote {args.output.resolve()} (reference_frames={frames}, detections={detections})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
