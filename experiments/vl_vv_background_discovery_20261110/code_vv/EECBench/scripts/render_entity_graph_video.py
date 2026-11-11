#!/usr/bin/env python3
"""Render GroundingDINO entity boxes onto the source video.

The entity graph contains detections only for sampled reference frames.
Default visualization linearly interpolates boxes between two real detections
and labels those synthetic overlays with "interp". The graph JSON itself is
never changed.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont


class RenderError(RuntimeError):
    """Raised when an annotated video cannot be produced."""


@dataclass(frozen=True)
class OverlayBox:
    entity_id: str
    entity_name: str
    bbox: Tuple[float, float, float, float]
    score: float
    interpolated: bool


PALETTE = (
    (255, 82, 82),
    (67, 160, 255),
    (76, 217, 100),
    (255, 193, 7),
    (186, 104, 200),
    (0, 188, 212),
    (255, 138, 101),
    (174, 213, 129),
)
INTERPOLATION_MAX_AREA_RATIO = 8.0
INTERPOLATION_MAX_CENTER_DISTANCE = 0.75
INTERPOLATION_MAX_ASPECT_RATIO = 4.0


def _tail(text: str, limit: int = 1200) -> str:
    compact = text.strip()
    return compact[-limit:] if compact else "<no diagnostic output>"


def load_graph(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RenderError(f"Cannot read entity graph {path}: {exc}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("entities"), list):
        raise RenderError("Entity graph must contain an entities array")
    return value


def build_tracks(
    graph: Mapping[str, Any],
) -> List[
    Tuple[
        str,
        str,
        Dict[int, Tuple[Tuple[float, ...], float]],
        set[int],
    ]
]:
    tracks = []
    for entity in graph.get("entities", []):
        if not isinstance(entity, dict):
            continue
        grounding = entity.get("grounding")
        if not isinstance(grounding, dict):
            continue
        detections: Dict[int, Tuple[Tuple[float, ...], float]] = {}
        for box in grounding.get("boxes", []):
            if not isinstance(box, dict):
                continue
            try:
                frame_id = int(box["frame_id"])
                coords = tuple(float(v) for v in box["bbox_xyxy_normalized"])
                score = float(box["score"])
            except (KeyError, TypeError, ValueError) as exc:
                raise RenderError(
                    f"Invalid grounding box for entity {entity.get('id')!r}"
                ) from exc
            if (
                frame_id < 0
                or len(coords) != 4
                or not all(0.0 <= value <= 1.0 for value in coords)
                or coords[0] >= coords[2]
                or coords[1] >= coords[3]
                or not math.isfinite(score)
                or not 0.0 <= score <= 1.0
            ):
                raise RenderError(
                    f"Invalid normalized box for entity {entity.get('id')!r}: "
                    f"frame={frame_id}, bbox={coords}"
                )
            if frame_id in detections:
                raise RenderError(
                    f"Duplicate grounding box for entity {entity.get('id')!r} "
                    f"on frame {frame_id}"
                )
            detections[frame_id] = (coords, score)
        if detections:
            attempted_frames = set(detections)
            for value in entity.get("evidence_frame_ids", []):
                try:
                    attempted_frames.add(int(value))
                except (TypeError, ValueError):
                    continue
            tracks.append((
                str(entity.get("id", "?")),
                str(entity.get("name", "entity")),
                detections,
                attempted_frames,
            ))
    return tracks


def overlays_for_frame(
    tracks: Sequence[
        Tuple[
            str,
            str,
            Dict[int, Tuple[Tuple[float, ...], float]],
            set[int],
        ]
    ],
    frame_id: int,
    box_mode: str,
) -> List[OverlayBox]:
    overlays: List[OverlayBox] = []
    for entity_id, entity_name, detections, attempted_frames in tracks:
        if frame_id in detections:
            bbox, score = detections[frame_id]
            overlays.append(OverlayBox(
                entity_id, entity_name, tuple(bbox), score, False
            ))
            continue
        if box_mode == "exact":
            continue

        ordered = sorted(detections)
        left = max((value for value in ordered if value < frame_id), default=None)
        right = min((value for value in ordered if value > frame_id), default=None)
        if left is None or right is None:
            continue
        left_box, left_score = detections[left]
        right_box, right_score = detections[right]
        if any(
            left < attempted < right and attempted not in detections
            for attempted in attempted_frames
        ):
            continue
        left_area = (left_box[2] - left_box[0]) * (left_box[3] - left_box[1])
        right_area = (right_box[2] - right_box[0]) * (right_box[3] - right_box[1])
        area_ratio = max(left_area, right_area) / min(left_area, right_area)
        if area_ratio > INTERPOLATION_MAX_AREA_RATIO:
            continue
        left_aspect = (left_box[2] - left_box[0]) / (left_box[3] - left_box[1])
        right_aspect = (right_box[2] - right_box[0]) / (right_box[3] - right_box[1])
        aspect_ratio = max(left_aspect, right_aspect) / min(left_aspect, right_aspect)
        if aspect_ratio > INTERPOLATION_MAX_ASPECT_RATIO:
            continue
        left_center = (
            (left_box[0] + left_box[2]) / 2,
            (left_box[1] + left_box[3]) / 2,
        )
        right_center = (
            (right_box[0] + right_box[2]) / 2,
            (right_box[1] + right_box[3]) / 2,
        )
        if math.dist(left_center, right_center) > INTERPOLATION_MAX_CENTER_DISTANCE:
            continue
        alpha = (frame_id - left) / (right - left)
        bbox = tuple(
            start + alpha * (end - start)
            for start, end in zip(left_box, right_box)
        )
        score = left_score + alpha * (right_score - left_score)
        overlays.append(OverlayBox(
            entity_id, entity_name, bbox, score, True
        ))
    return overlays


def draw_overlays(
    image: Image.Image,
    overlays: Sequence[OverlayBox],
    color_by_entity: Mapping[str, Tuple[int, int, int]],
) -> None:
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    width, height = image.size
    line_width = max(2, round(min(width, height) / 240))

    for overlay in overlays:
        color = color_by_entity[overlay.entity_id]
        x1 = round(overlay.bbox[0] * (width - 1))
        y1 = round(overlay.bbox[1] * (height - 1))
        x2 = round(overlay.bbox[2] * (width - 1))
        y2 = round(overlay.bbox[3] * (height - 1))
        draw.rectangle((x1, y1, x2, y2), outline=color, width=line_width)

        suffix = " interp" if overlay.interpolated else f" {overlay.score:.2f}"
        label = f"{overlay.entity_id} {overlay.entity_name}{suffix}"
        text_box = draw.textbbox((0, 0), label, font=font, stroke_width=0)
        text_width = text_box[2] - text_box[0]
        text_height = text_box[3] - text_box[1]
        label_y = max(0, y1 - text_height - 4)
        label_x = min(max(0, x1), max(0, width - text_width - 4))
        draw.rectangle(
            (label_x, label_y, label_x + text_width + 4, label_y + text_height + 4),
            fill=(0, 0, 0),
        )
        draw.text(
            (label_x + 2, label_y + 2),
            label,
            fill=color,
            font=font,
        )


def resolve_ffmpeg_executable() -> str:
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RenderError(
            "Neither system ffmpeg nor imageio-ffmpeg is available"
        ) from exc
    executable = imageio_ffmpeg.get_ffmpeg_exe()
    if not executable or not Path(executable).is_file():
        raise RenderError(
            f"imageio-ffmpeg returned an invalid executable: {executable!r}"
        )
    return executable


def probe_video(video_path: Path) -> Tuple[int, int, str]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        try:
            import imageio_ffmpeg
        except ImportError as exc:
            raise RenderError(
                "Video probing requires system ffprobe or imageio-ffmpeg"
            ) from exc
        reader = imageio_ffmpeg.read_frames(str(video_path), pix_fmt="rgb24")
        try:
            metadata = next(reader)
        except Exception as exc:
            raise RenderError(
                f"imageio-ffmpeg could not probe {video_path}: {exc}"
            ) from exc
        finally:
            reader.close()
        try:
            width, height = (int(value) for value in metadata["size"])
            fps = float(metadata["fps"])
            rate = str(Fraction(str(fps)).limit_denominator(100000))
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
            raise RenderError(
                f"Invalid imageio-ffmpeg metadata: {metadata!r}"
            ) from exc
        if width <= 0 or height <= 0 or fps <= 0:
            raise RenderError(
                f"Invalid video geometry/rate: {width}x{height} at {rate}"
            )
        return width, height, rate

    command = [
        ffprobe, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,avg_frame_rate",
        "-of", "json", str(video_path),
    ]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RenderError(f"ffprobe failed: {_tail(result.stderr)}")
    try:
        stream = json.loads(result.stdout)["streams"][0]
        width = int(stream["width"])
        height = int(stream["height"])
        rate = str(stream["avg_frame_rate"])
        fps = Fraction(rate)
    except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise RenderError(f"Invalid ffprobe metadata: {_tail(result.stdout)}") from exc
    if width <= 0 or height <= 0 or fps <= 0:
        raise RenderError(
            f"Invalid video geometry/rate: {width}x{height} at {rate}"
        )
    return width, height, rate


def render_video(
    video_path: Path,
    graph_path: Path,
    output_path: Path,
    *,
    box_mode: str = "interpolate",
) -> Tuple[int, int, int]:
    if box_mode not in {"exact", "interpolate"}:
        raise RenderError(f"Unsupported box mode: {box_mode}")
    if not video_path.is_file():
        raise RenderError(f"Video does not exist: {video_path}")
    if not graph_path.is_file():
        raise RenderError(f"Entity graph does not exist: {graph_path}")
    if video_path.resolve() == output_path.resolve():
        raise RenderError("Annotated output must not overwrite the source video")

    graph = load_graph(graph_path)
    tracks = build_tracks(graph)
    color_by_entity = {
        entity_id: PALETTE[index % len(PALETTE)]
        for index, (entity_id, _, _, _) in enumerate(tracks)
    }
    ffmpeg = resolve_ffmpeg_executable()
    width, height, frame_rate = probe_video(video_path)
    frame_bytes = width * height * 3
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(
        f".{output_path.stem}.tmp-{os.getpid()}.mp4"
    )

    decoder_command = [
        ffmpeg, "-v", "error", "-threads", "1", "-i", str(video_path),
        "-map", "0:v:0", "-vsync", "0",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
    ]
    encoder_command = [
        ffmpeg, "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s:v", f"{width}x{height}", "-r", frame_rate, "-i", "pipe:0",
        "-i", str(video_path),
        "-map", "0:v:0", "-map", "1:a?",
        "-map_metadata", "1",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-threads", "1", "-pix_fmt", "yuv420p",
        "-c:a", "copy", "-shortest", "-movflags", "+faststart",
        str(temporary),
    ]

    decoder = subprocess.Popen(
        decoder_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    encoder = subprocess.Popen(
        encoder_command, stdin=subprocess.PIPE, stderr=subprocess.PIPE
    )
    frame_id = 0
    exact_count = 0
    interpolated_count = 0
    try:
        assert decoder.stdout is not None
        assert encoder.stdin is not None
        while True:
            data = decoder.stdout.read(frame_bytes)
            if not data:
                break
            if len(data) != frame_bytes:
                raise RenderError(
                    f"Decoder returned a partial frame: {len(data)}/{frame_bytes} bytes"
                )
            image = Image.frombytes("RGB", (width, height), data)
            overlays = overlays_for_frame(tracks, frame_id, box_mode)
            exact_count += sum(not item.interpolated for item in overlays)
            interpolated_count += sum(item.interpolated for item in overlays)
            draw_overlays(image, overlays, color_by_entity)
            encoder.stdin.write(image.tobytes())
            frame_id += 1
        encoder.stdin.close()
        decoder_stderr = (
            decoder.stderr.read().decode("utf-8", errors="replace")
            if decoder.stderr else ""
        )
        decoder_code = decoder.wait()
        encoder_stderr = (
            encoder.stderr.read().decode("utf-8", errors="replace")
            if encoder.stderr else ""
        )
        encoder_code = encoder.wait()
        if decoder_code != 0:
            raise RenderError(f"ffmpeg decode failed: {_tail(decoder_stderr)}")
        if encoder_code != 0:
            raise RenderError(f"ffmpeg encode failed: {_tail(encoder_stderr)}")
        if frame_id == 0:
            raise RenderError("No video frames were decoded")
        os.replace(temporary, output_path)
    except Exception:
        if encoder.poll() is None:
            encoder.terminate()
        if decoder.poll() is None:
            decoder.terminate()
        temporary.unlink(missing_ok=True)
        raise
    return frame_id, exact_count, interpolated_count


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Overlay entity-graph grounding boxes on a video."
    )
    parser.add_argument("video", type=Path, help="Source video")
    parser.add_argument("graph", type=Path, help="Entity graph JSON")
    parser.add_argument("-o", "--output", type=Path, help="Annotated MP4 path")
    parser.add_argument(
        "--box-mode", choices=("exact", "interpolate"), default="interpolate",
        help="Draw only detected reference frames, or label interpolated boxes "
             "between adjacent detections (default: interpolate)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    video_path = args.video.resolve()
    graph_path = args.graph.resolve()
    output_path = (
        args.output.resolve()
        if args.output
        else graph_path.with_name(f"{graph_path.stem}.annotated.mp4")
    )
    try:
        frames, exact, interpolated = render_video(
            video_path, graph_path, output_path, box_mode=args.box_mode
        )
    except (RenderError, OSError, BrokenPipeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        f"Wrote {output_path} "
        f"(frames={frames}, detections={exact}, interpolated={interpolated})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
