#!/usr/bin/env python3
"""Extract an open-vocabulary semantic entity graph from one video shot.

The default pipeline is:

    video -> uniformly sampled reference frames -> ``codex exec`` semantics
          -> GroundingDINO boxes -> validated shot graph JSON

Codex is run non-interactively in an ephemeral, read-only session.  It never
produces boxes: GroundingDINO supplies those after semantic extraction.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEMANTIC_SCHEMA_PATH = PROJECT_ROOT / "schemas" / "codex_shot_semantics_v0.1.schema.json"
PROMPT_PATH = PROJECT_ROOT / "prompts" / "shot_entity_graph_v0.2.md"
PROMPT_VERSION = "shot_entity_graph_v0.2"
FINAL_SCHEMA_VERSION = "0.1"

ENTITY_ID_RE = re.compile(r"^e[1-9][0-9]*$")
RELATION_ID_RE = re.compile(r"^r[1-9][0-9]*$")
PRECISIONS = {"frame", "segment", "shot", "unknown"}
GROUNDING_STATUSES = {
    "grounded", "partially_grounded", "not_found", "ambiguous", "not_run"
}


class GraphExtractionError(RuntimeError):
    """Raised when extraction cannot produce an auditable graph."""


@dataclass
class VideoSample:
    frames: Dict[int, Any]
    frame_paths: Dict[int, Path]
    num_frames: int
    fps: float

    @property
    def duration_sec(self) -> float:
        return self.num_frames / self.fps

    @property
    def reference_frame_ids(self) -> List[int]:
        return sorted(self.frames)


@dataclass(frozen=True)
class CodexRunResult:
    semantics: Dict[str, Any]
    token_usage: Optional[Dict[str, Optional[int]]]


def _compact_text(value: str, *, lowercase: bool = False) -> str:
    text = " ".join(value.strip().split())
    return text.lower() if lowercase else text


def uniform_indices(num_frames: int, n_samples: int) -> List[int]:
    """Return unique, uniformly spaced indices including both endpoints."""
    if num_frames <= 0:
        raise ValueError("num_frames must be positive")
    if n_samples <= 0:
        raise ValueError("n_samples must be positive")
    count = min(num_frames, n_samples)
    if count == 1:
        return [num_frames // 2]
    result = []
    for i in range(count):
        index = round(i * (num_frames - 1) / (count - 1))
        if not result or index != result[-1]:
            result.append(index)
    return result


def _parse_fraction(value: str) -> float:
    try:
        numerator, denominator = value.split("/", 1)
        result = float(numerator) / float(denominator)
    except (AttributeError, ValueError, ZeroDivisionError) as exc:
        raise GraphExtractionError(f"Invalid video frame rate: {value!r}") from exc
    if not math.isfinite(result) or result <= 0:
        raise GraphExtractionError(f"Invalid video frame rate: {value!r}")
    return result


def _extract_reference_frames_ffmpeg(
    video_path: Path, n_frames: int, frame_dir: Path
) -> VideoSample:
    probe_command = [
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
        "-show_entries", "stream=avg_frame_rate,nb_frames,nb_read_frames",
        "-of", "json", str(video_path),
    ]
    probe = subprocess.run(probe_command, text=True, capture_output=True, check=False)
    if probe.returncode != 0:
        raise GraphExtractionError(f"ffprobe failed: {_tail(probe.stderr)}")
    try:
        streams = json.loads(probe.stdout)["streams"]
        stream = streams[0]
        fps = _parse_fraction(stream["avg_frame_rate"])
        frame_count_value = stream.get("nb_read_frames") or stream.get("nb_frames")
        num_frames = int(frame_count_value)
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise GraphExtractionError(
            f"ffprobe did not return usable frame metadata: {_tail(probe.stdout)}"
        ) from exc
    if num_frames <= 0:
        raise GraphExtractionError(f"Video contains no readable frames: {video_path}")

    frame_dir.mkdir(parents=True, exist_ok=True)
    selected_ids = uniform_indices(num_frames, n_frames)
    selection = "+".join(f"eq(n\\,{frame_id})" for frame_id in selected_ids)
    output_pattern = frame_dir / "ffmpeg_selected_%06d.jpg"
    extract_command = [
        "ffmpeg", "-y", "-v", "error", "-i", str(video_path),
        "-vf", f"select={selection}", "-vsync", "0", "-q:v", "2",
        str(output_pattern),
    ]
    extract = subprocess.run(extract_command, text=True, capture_output=True, check=False)
    if extract.returncode != 0:
        raise GraphExtractionError(f"ffmpeg frame extraction failed: {_tail(extract.stderr)}")

    decoded_paths = sorted(frame_dir.glob("ffmpeg_selected_*.jpg"))
    if len(decoded_paths) != len(selected_ids):
        raise GraphExtractionError(
            f"ffmpeg produced {len(decoded_paths)} frames; expected {len(selected_ids)}"
        )
    try:
        import numpy as np
    except ImportError as exc:
        raise GraphExtractionError("numpy is required for GroundingDINO frame arrays") from exc

    frames: Dict[int, Any] = {}
    frame_paths: Dict[int, Path] = {}
    for frame_id, decoded_path in zip(selected_ids, decoded_paths):
        final_path = frame_dir / f"frame_{frame_id:06d}.jpg"
        os.replace(decoded_path, final_path)
        with Image.open(final_path) as image:
            frames[frame_id] = np.asarray(image.convert("RGB")).copy()
        frame_paths[frame_id] = final_path.resolve()
    return VideoSample(
        frames=frames,
        frame_paths=frame_paths,
        num_frames=num_frames,
        fps=fps,
    )



def _extract_reference_frames_imageio_ffmpeg(
    video_path: Path, n_frames: int, frame_dir: Path
) -> VideoSample:
    """Decode native frames instead of expanding VFR video to nominal CFR."""
    try:
        import imageio_ffmpeg
        import numpy as np
    except ImportError as exc:
        raise GraphExtractionError(
            "Video decoding requires system ffmpeg/ffprobe or imageio-ffmpeg."
        ) from exc

    try:
        num_frames_value, _ = imageio_ffmpeg.count_frames_and_secs(str(video_path))
        num_frames = int(num_frames_value)
        reader = imageio_ffmpeg.read_frames(str(video_path), pix_fmt="rgb24")
        try:
            metadata = next(reader)
        finally:
            reader.close()
        fps = float(metadata["fps"])
        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise GraphExtractionError(
            f"imageio-ffmpeg could not probe {video_path}: {exc}"
        ) from exc
    if num_frames <= 0:
        raise GraphExtractionError(f"Video contains no readable frames: {video_path}")
    if not math.isfinite(fps) or fps <= 0:
        raise GraphExtractionError(f"Invalid imageio-ffmpeg frame rate: {fps!r}")
    if not ffmpeg_bin or not Path(ffmpeg_bin).is_file():
        raise GraphExtractionError(
            f"imageio-ffmpeg returned an invalid executable: {ffmpeg_bin!r}"
        )

    frame_dir.mkdir(parents=True, exist_ok=True)
    selected_ids = uniform_indices(num_frames, n_frames)
    selection = "+".join(f"eq(n\\,{frame_id})" for frame_id in selected_ids)
    output_pattern = frame_dir / "ffmpeg_selected_%06d.jpg"
    extract_command = [
        ffmpeg_bin, "-y", "-v", "error", "-i", str(video_path),
        "-vf", f"select={selection}", "-vsync", "0", "-q:v", "2",
        str(output_pattern),
    ]
    extract = subprocess.run(extract_command, text=True, capture_output=True, check=False)
    if extract.returncode != 0:
        raise GraphExtractionError(f"ffmpeg frame extraction failed: {_tail(extract.stderr)}")

    decoded_paths = sorted(frame_dir.glob("ffmpeg_selected_*.jpg"))
    if len(decoded_paths) != len(selected_ids):
        raise GraphExtractionError(
            f"ffmpeg produced {len(decoded_paths)} frames; expected {len(selected_ids)}"
        )
    frames: Dict[int, Any] = {}
    frame_paths: Dict[int, Path] = {}
    for frame_id, decoded_path in zip(selected_ids, decoded_paths):
        final_path = frame_dir / f"frame_{frame_id:06d}.jpg"
        os.replace(decoded_path, final_path)
        with Image.open(final_path) as image:
            frames[frame_id] = np.asarray(image.convert("RGB")).copy()
        frame_paths[frame_id] = final_path.resolve()
    return VideoSample(
        frames=frames,
        frame_paths=frame_paths,
        num_frames=num_frames,
        fps=fps,
    )


def extract_reference_frames(video_path: Path, n_frames: int, frame_dir: Path) -> VideoSample:
    if not video_path.is_file():
        raise GraphExtractionError(f"Video does not exist: {video_path}")

    if shutil.which("ffprobe") and shutil.which("ffmpeg"):
        return _extract_reference_frames_ffmpeg(video_path, n_frames, frame_dir)

    try:
        import imageio_ffmpeg  # noqa: F401
    except ImportError:
        pass
    else:
        return _extract_reference_frames_imageio_ffmpeg(
            video_path, n_frames, frame_dir
        )

    try:
        import imageio.v2 as imageio
    except ImportError as exc:
        raise GraphExtractionError(
            "Video decoding requires system ffmpeg/ffprobe or imageio with a video backend."
        ) from exc

    try:
        reader = imageio.get_reader(str(video_path))
    except Exception as exc:
        raise GraphExtractionError(f"Cannot open video {video_path}: {exc}") from exc

    frames: List[Any] = []
    metadata: Dict[str, Any] = {}
    try:
        try:
            metadata = dict(reader.get_meta_data())
        except Exception:
            metadata = {}
        for frame in reader:
            frames.append(frame)
    except Exception as exc:
        raise GraphExtractionError(f"Failed while reading {video_path}: {exc}") from exc
    finally:
        try:
            reader.close()
        except Exception:
            pass

    if not frames:
        raise GraphExtractionError(f"Video contains no readable frames: {video_path}")

    fps_value = metadata.get("fps", 0.0)
    try:
        fps = float(fps_value)
    except (TypeError, ValueError):
        fps = 0.0
    if not math.isfinite(fps) or fps <= 0:
        raise GraphExtractionError(
            f"Video FPS is unavailable or invalid ({fps_value!r}); cannot define time ranges."
        )

    frame_dir.mkdir(parents=True, exist_ok=True)
    selected_frames: Dict[int, Any] = {}
    frame_paths: Dict[int, Path] = {}
    for frame_id in uniform_indices(len(frames), n_frames):
        frame = frames[frame_id]
        path = frame_dir / f"frame_{frame_id:06d}.jpg"
        Image.fromarray(frame).convert("RGB").save(path, format="JPEG", quality=95)
        selected_frames[frame_id] = frame
        frame_paths[frame_id] = path.resolve()

    return VideoSample(
        frames=selected_frames,
        frame_paths=frame_paths,
        num_frames=len(frames),
        fps=fps,
    )


def build_codex_prompt(sample: VideoSample) -> str:
    if not PROMPT_PATH.is_file():
        raise GraphExtractionError(f"Prompt template is missing: {PROMPT_PATH}")
    template = PROMPT_PATH.read_text(encoding="utf-8").rstrip()
    mapping = "\n".join(
        f"- attached image {index + 1}: frame_id={frame_id}, "
        f"timestamp_sec={frame_id / sample.fps:.6f}"
        for index, frame_id in enumerate(sample.reference_frame_ids)
    )
    return (
        f"{template}\n\n"
        "Shot metadata:\n"
        f"- num_frames: {sample.num_frames}\n"
        f"- fps: {sample.fps:.9g}\n"
        f"- valid frame interval: [0, {sample.num_frames})\n\n"
        "Attachment-to-frame mapping (chronological):\n"
        f"{mapping}\n"
    )


def _tail(text: str, limit: int = 4000) -> str:
    return text if len(text) <= limit else text[-limit:]


def codex_version(codex_bin: str) -> str:
    try:
        result = subprocess.run(
            [codex_bin, "--version"],
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except Exception:
        return "unknown"
    output = (result.stdout or result.stderr).strip()
    return output or "unknown"


def _token_count(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(float(value)) or value < 0 or int(value) != value:
        return None
    return int(value)


def _normalize_token_usage(value: Mapping[str, Any]) -> Optional[Dict[str, Optional[int]]]:
    """Normalize Codex/Responses-style usage dictionaries."""
    input_tokens = _token_count(
        value.get("input_tokens", value.get("prompt_tokens", value.get("prompt_token_count")))
    )
    output_tokens = _token_count(
        value.get(
            "output_tokens",
            value.get("completion_tokens", value.get("completion_token_count")),
        )
    )
    total_tokens = _token_count(value.get("total_tokens", value.get("total_token_count")))
    cached_input_tokens = _token_count(
        value.get("cached_input_tokens", value.get("cached_tokens"))
    )
    if cached_input_tokens is None:
        for details_key in ("input_tokens_details", "prompt_tokens_details"):
            details = value.get(details_key)
            if isinstance(details, Mapping):
                cached_input_tokens = _token_count(details.get("cached_tokens"))
                if cached_input_tokens is not None:
                    break

    if input_tokens is None and output_tokens is None and total_tokens is None:
        return None
    if total_tokens is None and (input_tokens is not None or output_tokens is not None):
        total_tokens = (input_tokens or 0) + (output_tokens or 0)
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def parse_codex_token_usage(jsonl: str) -> Optional[Dict[str, Optional[int]]]:
    """Return the best cumulative token-usage record in Codex JSONL output."""
    candidates: List[Dict[str, Optional[int]]] = []

    def visit(value: Any, parent_key: Optional[str] = None) -> None:
        if isinstance(value, Mapping):
            if parent_key in {"usage", "token_usage"} or any(
                key in value
                for key in (
                    "input_tokens", "prompt_tokens", "output_tokens",
                    "completion_tokens", "total_tokens",
                )
            ):
                candidate = _normalize_token_usage(value)
                if candidate is not None:
                    candidates.append(candidate)
            for key, child in value.items():
                visit(child, str(key))
        elif isinstance(value, list):
            for child in value:
                visit(child, parent_key)

    for line in jsonl.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        visit(event)

    if not candidates:
        return None
    # Completed-turn usage is normally the most populated record. If tied,
    # retain the latest record because Codex reports cumulative usage.
    return max(
        enumerate(candidates),
        key=lambda item: (sum(v is not None for v in item[1].values()), item[0]),
    )[1]


def format_token_usage(usage: Optional[Mapping[str, Optional[int]]]) -> str:
    if usage is None:
        return "unavailable"

    def display(key: str) -> str:
        value = usage.get(key)
        return str(value) if value is not None else "unknown"

    return (
        f"input={display('input_tokens')}, "
        f"cached_input={display('cached_input_tokens')}, "
        f"output={display('output_tokens')}, "
        f"total={display('total_tokens')}"
    )


def run_codex(
    sample: VideoSample,
    *,
    codex_bin: str,
    model: Optional[str],
    timeout_sec: int,
    work_dir: Path,
    verbose: bool,
) -> CodexRunResult:
    if shutil.which(codex_bin) is None and not Path(codex_bin).is_file():
        raise GraphExtractionError(f"Codex CLI was not found: {codex_bin}")
    if not SEMANTIC_SCHEMA_PATH.is_file():
        raise GraphExtractionError(f"Codex output schema is missing: {SEMANTIC_SCHEMA_PATH}")

    raw_output = work_dir / "codex_semantics.json"
    command = [
        codex_bin,
        "--ask-for-approval",
        "never",
        "exec",
        "--ephemeral",
        "--color",
        "never",
        "--json",
        "--sandbox",
        "read-only",
        "--output-schema",
        str(SEMANTIC_SCHEMA_PATH),
        "--output-last-message",
        str(raw_output),
        "--cd",
        str(PROJECT_ROOT),
    ]
    if model:
        command.extend(["--model", model])
    for frame_id in sample.reference_frame_ids:
        command.extend(["--image", str(sample.frame_paths[frame_id])])
    command.append("-")

    prompt = build_codex_prompt(sample)
    try:
        result = subprocess.run(
            command,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GraphExtractionError(
            f"Codex extraction timed out after {timeout_sec} seconds."
        ) from exc

    if verbose:
        if result.stdout:
            print(result.stdout, file=sys.stderr, end="")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")

    if result.returncode != 0:
        diagnostic = _tail((result.stderr or "") + "\n" + (result.stdout or ""))
        raise GraphExtractionError(
            f"codex exec failed with exit code {result.returncode}:\n{diagnostic}"
        )
    if not raw_output.is_file():
        raise GraphExtractionError("codex exec succeeded but did not write its final message.")

    try:
        semantics = json.loads(raw_output.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GraphExtractionError(
            f"Codex final message is not valid JSON: {exc}\n{_tail(raw_output.read_text(encoding='utf-8'))}"
        ) from exc
    return CodexRunResult(
        semantics=semantics,
        token_usage=parse_codex_token_usage(result.stdout or ""),
    )


def _require_exact_keys(
    value: Mapping[str, Any], required: Iterable[str], context: str
) -> None:
    required_set = set(required)
    actual = set(value)
    missing = sorted(required_set - actual)
    extra = sorted(actual - required_set)
    if missing or extra:
        raise GraphExtractionError(
            f"{context} keys are invalid; missing={missing}, extra={extra}"
        )


def _require_confidence(value: Any, context: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GraphExtractionError(f"{context} must be a number in [0, 1]")
    if not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
        raise GraphExtractionError(f"{context} must be a finite number in [0, 1]")


def _validate_evidence(
    value: Any, reference_ids: set[int], context: str, *, allow_empty: bool = False
) -> None:
    if not isinstance(value, list) or (not allow_empty and not value):
        qualifier = "a list" if allow_empty else "a non-empty list"
        raise GraphExtractionError(f"{context} must be {qualifier}")
    if any(isinstance(item, bool) or not isinstance(item, int) for item in value):
        raise GraphExtractionError(f"{context} must contain integer frame IDs")
    if len(value) != len(set(value)):
        raise GraphExtractionError(f"{context} contains duplicate frame IDs")
    unknown = sorted(set(value) - reference_ids)
    if unknown:
        raise GraphExtractionError(
            f"{context} contains frames not supplied to Codex: {unknown}"
        )


def normalize_and_validate_semantics(
    graph: Dict[str, Any], sample: VideoSample
) -> Dict[str, Any]:
    if not isinstance(graph, dict):
        raise GraphExtractionError("Codex output must be a JSON object")
    _require_exact_keys(graph, {"entities", "relations", "warnings"}, "root")
    if not isinstance(graph["entities"], list) or not isinstance(graph["relations"], list):
        raise GraphExtractionError("entities and relations must be arrays")
    if not isinstance(graph["warnings"], list) or not all(
        isinstance(item, str) for item in graph["warnings"]
    ):
        raise GraphExtractionError("warnings must be an array of strings")

    result = copy.deepcopy(graph)
    reference_ids = set(sample.reference_frame_ids)
    entity_ids: set[str] = set()

    entity_keys = {
        "id", "name", "attributes", "entity_confidence", "evidence_frame_ids"
    }
    attribute_keys = {"name", "value", "confidence", "evidence_frame_ids"}
    for index, entity in enumerate(result["entities"]):
        context = f"entities[{index}]"
        if not isinstance(entity, dict):
            raise GraphExtractionError(f"{context} must be an object")
        _require_exact_keys(entity, entity_keys, context)
        entity_id = entity["id"]
        if not isinstance(entity_id, str) or not ENTITY_ID_RE.fullmatch(entity_id):
            raise GraphExtractionError(f"{context}.id must match e1, e2, ...")
        if entity_id in entity_ids:
            raise GraphExtractionError(f"Duplicate entity ID: {entity_id}")
        entity_ids.add(entity_id)

        if not isinstance(entity["name"], str) or not entity["name"].strip():
            raise GraphExtractionError(f"{context}.name must be non-empty")
        entity["name"] = _compact_text(entity["name"], lowercase=True)
        _require_confidence(entity["entity_confidence"], f"{context}.entity_confidence")
        _validate_evidence(
            entity["evidence_frame_ids"], reference_ids, f"{context}.evidence_frame_ids"
        )
        entity["evidence_frame_ids"] = sorted(entity["evidence_frame_ids"])

        if not isinstance(entity["attributes"], list):
            raise GraphExtractionError(f"{context}.attributes must be an array")
        for attr_index, attribute in enumerate(entity["attributes"]):
            attr_context = f"{context}.attributes[{attr_index}]"
            if not isinstance(attribute, dict):
                raise GraphExtractionError(f"{attr_context} must be an object")
            _require_exact_keys(attribute, attribute_keys, attr_context)
            for field in ("name", "value"):
                if not isinstance(attribute[field], str) or not attribute[field].strip():
                    raise GraphExtractionError(f"{attr_context}.{field} must be non-empty")
                attribute[field] = _compact_text(attribute[field], lowercase=True)
            _require_confidence(attribute["confidence"], f"{attr_context}.confidence")
            _validate_evidence(
                attribute["evidence_frame_ids"],
                reference_ids,
                f"{attr_context}.evidence_frame_ids",
            )
            attribute["evidence_frame_ids"] = sorted(attribute["evidence_frame_ids"])

    relation_ids: set[str] = set()
    relation_keys = {
        "id", "subject_id", "object_id", "predicate", "temporal_extent",
        "confidence", "evidence_frame_ids",
    }
    extent_keys = {"start_frame", "end_frame_exclusive", "precision"}
    for index, relation in enumerate(result["relations"]):
        context = f"relations[{index}]"
        if not isinstance(relation, dict):
            raise GraphExtractionError(f"{context} must be an object")
        _require_exact_keys(relation, relation_keys, context)
        relation_id = relation["id"]
        if not isinstance(relation_id, str) or not RELATION_ID_RE.fullmatch(relation_id):
            raise GraphExtractionError(f"{context}.id must match r1, r2, ...")
        if relation_id in relation_ids:
            raise GraphExtractionError(f"Duplicate relation ID: {relation_id}")
        relation_ids.add(relation_id)
        for endpoint in ("subject_id", "object_id"):
            if relation[endpoint] not in entity_ids:
                raise GraphExtractionError(
                    f"{context}.{endpoint} references missing entity {relation[endpoint]!r}"
                )
        if relation["subject_id"] == relation["object_id"]:
            raise GraphExtractionError(f"{context} cannot be a self-relation")
        if not isinstance(relation["predicate"], str) or not relation["predicate"].strip():
            raise GraphExtractionError(f"{context}.predicate must be non-empty")
        relation["predicate"] = _compact_text(relation["predicate"], lowercase=True)
        _require_confidence(relation["confidence"], f"{context}.confidence")
        _validate_evidence(
            relation["evidence_frame_ids"], reference_ids, f"{context}.evidence_frame_ids"
        )
        relation["evidence_frame_ids"] = sorted(relation["evidence_frame_ids"])

        extent = relation["temporal_extent"]
        if not isinstance(extent, dict):
            raise GraphExtractionError(f"{context}.temporal_extent must be an object")
        _require_exact_keys(extent, extent_keys, f"{context}.temporal_extent")
        precision = extent["precision"]
        if precision not in PRECISIONS:
            raise GraphExtractionError(
                f"{context}.temporal_extent.precision must be one of {sorted(PRECISIONS)}"
            )
        start = extent["start_frame"]
        end = extent["end_frame_exclusive"]
        if precision == "unknown":
            if start is not None or end is not None:
                raise GraphExtractionError(
                    f"{context} unknown temporal extent must have null boundaries"
                )
        else:
            if any(isinstance(v, bool) or not isinstance(v, int) for v in (start, end)):
                raise GraphExtractionError(f"{context} temporal boundaries must be integers")
            if not 0 <= start < end <= sample.num_frames:
                raise GraphExtractionError(
                    f"{context} temporal extent [{start}, {end}) is outside the shot"
                )
            outside = [
                frame_id for frame_id in relation["evidence_frame_ids"]
                if not start <= frame_id < end
            ]
            if outside:
                raise GraphExtractionError(
                    f"{context} evidence frames fall outside its temporal extent: {outside}"
                )

    result["warnings"] = [_compact_text(item) for item in result["warnings"] if item.strip()]
    return result


def build_grounding_query(entity: Mapping[str, Any], max_attributes: int) -> str:
    base_name = _compact_text(str(entity["name"]), lowercase=True)
    parts = [base_name]
    seen = {base_name}
    ranked_attributes = sorted(
        entity.get("attributes", []),
        key=lambda item: float(item.get("confidence", 0.0)),
        reverse=True,
    )
    for attribute in ranked_attributes[:max_attributes]:
        value = _compact_text(str(attribute["value"]), lowercase=True)
        if value and value not in seen and value not in base_name:
            parts.append(value)
            seen.add(value)
    return " ".join(parts)


# Historical temporal-selector helpers are retained for replaying and testing
# pre-EntityBench graph artifacts.  The active extraction path below does not
# call them; current candidates are selected by EntityBench CLIP/quality score.
def bbox_iou(box_a: Sequence[float], box_b: Sequence[float]) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    intersection = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def _bbox_area(box: Sequence[float]) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _bbox_aspect_ratio(box: Sequence[float]) -> float:
    height = max(0.0, box[3] - box[1])
    return (max(0.0, box[2] - box[0]) / height) if height > 0 else float("inf")


def temporal_candidate_support(
    candidates_by_frame: Mapping[int, Sequence[Mapping[str, Any]]],
    *,
    frame_width: int,
    frame_height: int,
    max_area_ratio: float,
    max_center_distance: float,
    max_aspect_ratio: float,
) -> Dict[int, int]:
    """Count distinct reference frames geometrically supporting each candidate."""
    indexed = [
        (frame_id, candidate)
        for frame_id, frame_candidates in candidates_by_frame.items()
        for candidate in frame_candidates
    ]
    support: Dict[int, int] = {id(candidate): 0 for _, candidate in indexed}
    for left_frame, left_candidate in indexed:
        left_area = _bbox_area(left_candidate["bbox"])
        left_aspect = _bbox_aspect_ratio(left_candidate["bbox"])
        left_box = left_candidate["bbox"]
        left_center = (
            (left_box[0] + left_box[2]) / (2 * frame_width),
            (left_box[1] + left_box[3]) / (2 * frame_height),
        )
        supported_frames = set()
        for right_frame, right_candidate in indexed:
            if left_frame == right_frame:
                continue
            right_area = _bbox_area(right_candidate["bbox"])
            right_aspect = _bbox_aspect_ratio(right_candidate["bbox"])
            area_low = min(left_area, right_area)
            area_ratio = (
                max(left_area, right_area) / area_low
                if area_low > 0 else float("inf")
            )
            aspect_low = min(left_aspect, right_aspect)
            aspect_ratio = (
                max(left_aspect, right_aspect) / aspect_low
                if aspect_low > 0 else float("inf")
            )
            right_box = right_candidate["bbox"]
            right_center = (
                (right_box[0] + right_box[2]) / (2 * frame_width),
                (right_box[1] + right_box[3]) / (2 * frame_height),
            )
            center_distance = math.hypot(
                left_center[0] - right_center[0],
                left_center[1] - right_center[1],
            )
            if (
                area_ratio <= max_area_ratio
                and aspect_ratio <= max_aspect_ratio
                and center_distance <= max_center_distance
            ):
                supported_frames.add(right_frame)
        support[id(left_candidate)] = len(supported_frames)
    return support


OUTLIER_RESCUE_MIN_STABLE_FRAMES = 3
OUTLIER_RESCUE_MAX_AREA_RATIO = 3.0
OUTLIER_RESCUE_MAX_CENTER_DISTANCE = 0.20
OUTLIER_RESCUE_MAX_ASPECT_RATIO = 2.5


def _temporal_boxes_compatible(
    box_a: Sequence[float],
    box_b: Sequence[float],
    *,
    frame_width: int,
    frame_height: int,
    max_area_ratio: float,
    max_center_distance: float,
    max_aspect_ratio: float,
) -> bool:
    area_a, area_b = _bbox_area(box_a), _bbox_area(box_b)
    area_low = min(area_a, area_b)
    area_ratio = max(area_a, area_b) / area_low if area_low > 0 else float("inf")
    aspect_a, aspect_b = _bbox_aspect_ratio(box_a), _bbox_aspect_ratio(box_b)
    aspect_low = min(aspect_a, aspect_b)
    aspect_ratio = (
        max(aspect_a, aspect_b) / aspect_low
        if aspect_low > 0 else float("inf")
    )
    center_a = (
        (box_a[0] + box_a[2]) / (2 * frame_width),
        (box_a[1] + box_a[3]) / (2 * frame_height),
    )
    center_b = (
        (box_b[0] + box_b[2]) / (2 * frame_width),
        (box_b[1] + box_b[3]) / (2 * frame_height),
    )
    return (
        area_ratio <= max_area_ratio
        and aspect_ratio <= max_aspect_ratio
        and math.dist(center_a, center_b) <= max_center_distance
    )


def repair_single_frame_temporal_outliers(
    selected_by_frame: Dict[int, Dict[str, Mapping[str, Any]]],
    raw_candidates: Mapping[int, Mapping[str, Sequence[Mapping[str, Any]]]],
    sample: VideoSample,
    entity_names: Mapping[str, str],
    *,
    max_entity_box_iou: float,
) -> List[str]:
    """Replace a unique jump only when at least three selected frames agree."""
    warnings: List[str] = []
    entity_ids = sorted({
        entity_id
        for selected in selected_by_frame.values()
        for entity_id in selected
    })
    for entity_id in entity_ids:
        chosen = {
            frame_id: selected[entity_id]
            for frame_id, selected in selected_by_frame.items()
            if entity_id in selected
        }
        if len(chosen) < OUTLIER_RESCUE_MIN_STABLE_FRAMES + 1:
            continue
        first_frame = sample.frames[next(iter(chosen))]
        frame_height, frame_width = first_frame.shape[:2]

        support: Dict[int, int] = {}
        for frame_id, candidate in chosen.items():
            support[frame_id] = sum(
                _temporal_boxes_compatible(
                    candidate["bbox"], other["bbox"],
                    frame_width=frame_width,
                    frame_height=frame_height,
                    max_area_ratio=OUTLIER_RESCUE_MAX_AREA_RATIO,
                    max_center_distance=OUTLIER_RESCUE_MAX_CENTER_DISTANCE,
                    max_aspect_ratio=OUTLIER_RESCUE_MAX_ASPECT_RATIO,
                )
                for other_frame, other in chosen.items()
                if other_frame != frame_id
            )
        stable_frames = [
            frame_id for frame_id, count in support.items()
            if count >= OUTLIER_RESCUE_MIN_STABLE_FRAMES - 1
        ]
        outlier_frames = [frame_id for frame_id, count in support.items() if count == 0]
        if len(stable_frames) < OUTLIER_RESCUE_MIN_STABLE_FRAMES or len(outlier_frames) != 1:
            continue

        frame_id = outlier_frames[0]
        original = selected_by_frame[frame_id][entity_id]
        alternatives = []
        for candidate in raw_candidates.get(frame_id, {}).get(entity_id, []):
            if candidate is original:
                continue
            if not all(
                _temporal_boxes_compatible(
                    candidate["bbox"], chosen[stable_frame]["bbox"],
                    frame_width=frame_width,
                    frame_height=frame_height,
                    max_area_ratio=OUTLIER_RESCUE_MAX_AREA_RATIO,
                    max_center_distance=OUTLIER_RESCUE_MAX_CENTER_DISTANCE,
                    max_aspect_ratio=OUTLIER_RESCUE_MAX_ASPECT_RATIO,
                )
                for stable_frame in stable_frames
            ):
                continue
            conflicts = any(
                other_id != entity_id
                and bbox_iou(candidate["bbox"], other["bbox"]) > max_entity_box_iou
                for other_id, other in selected_by_frame[frame_id].items()
            )
            if conflicts:
                continue
            mean_iou = sum(
                bbox_iou(candidate["bbox"], chosen[stable_frame]["bbox"])
                for stable_frame in stable_frames
            ) / len(stable_frames)
            alternatives.append((mean_iou, float(candidate["confidence"]), candidate))

        name = entity_names.get(entity_id, entity_id)
        if alternatives:
            _, _, replacement = max(alternatives, key=lambda item: (item[0], item[1]))
            selected_by_frame[frame_id][entity_id] = replacement
            warnings.append(
                f"Temporal outlier rescue replaced {entity_id} ({name}) on reference "
                f"frame {frame_id}: detector score {float(original['confidence']):.4f} "
                f"was overridden by a {float(replacement['confidence']):.4f} candidate "
                f"consistent with {len(stable_frames)} stable selected frames."
            )
        else:
            del selected_by_frame[frame_id][entity_id]
            warnings.append(
                f"Temporal outlier rescue abstained for {entity_id} ({name}) on "
                f"reference frame {frame_id}: its selected box was the unique jump "
                f"against {len(stable_frames)} stable frames and no nonconflicting "
                "candidate matched that track."
            )
    return warnings


def sanitize_grounding_candidates(
    candidates: Sequence[Mapping[str, Any]],
    *,
    frame_width: int,
    frame_height: int,
    max_candidates: int,
) -> Tuple[List[Dict[str, Any]], int, int]:
    """Validate, sort, and cap detector candidates before joint selection."""
    valid: List[Dict[str, Any]] = []
    rejected = 0
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            rejected += 1
            continue
        bbox = candidate.get("bbox")
        confidence_value = candidate.get("confidence")
        if (
            not isinstance(bbox, Sequence)
            or isinstance(bbox, (str, bytes))
            or len(bbox) != 4
            or isinstance(confidence_value, (bool, str, bytes))
        ):
            rejected += 1
            continue
        try:
            coordinates = tuple(float(value) for value in bbox)
            confidence = float(confidence_value)
        except (TypeError, ValueError):
            rejected += 1
            continue
        if (
            any(not math.isfinite(value) for value in coordinates)
            or not math.isfinite(confidence)
            or not 0.0 <= confidence <= 1.0
        ):
            rejected += 1
            continue
        x1, y1, x2, y2 = coordinates
        if not (
            0.0 <= x1 < x2 <= frame_width
            and 0.0 <= y1 < y2 <= frame_height
        ):
            rejected += 1
            continue
        cleaned = dict(candidate)
        # EntityBench's grounder returns integer pixel coordinates and
        # ``crop_entity`` uses them directly as NumPy slice indices. Keep
        # that contract after validating through a temporary float tuple.
        cleaned["bbox"] = tuple(int(value) for value in coordinates)
        cleaned["confidence"] = confidence
        valid.append(cleaned)

    valid.sort(key=lambda candidate: float(candidate["confidence"]), reverse=True)
    truncated = max(0, len(valid) - max_candidates)
    return valid[:max_candidates], rejected, truncated


def assign_joint_entity_candidates(
    candidates: Mapping[str, Sequence[Mapping[str, Any]]],
    utilities: Mapping[int, float],
    null_utilities: Mapping[str, float],
    max_iou: float,
    support_scores: Optional[Mapping[int, float]] = None,
    support_ambiguity_margin: float = 0.10,
    max_search_nodes: int = 200_000,
) -> Tuple[Dict[str, Mapping[str, Any]], set[str], set[str]]:
    """Jointly maximize candidate utility with one box per entity and abstention."""
    if max_search_nodes <= 0:
        raise ValueError("max_search_nodes must be positive")
    support_scores = support_scores or {}
    entity_ids = sorted(candidates)
    upper_bounds = [0.0] * (len(entity_ids) + 1)
    for index in range(len(entity_ids) - 1, -1, -1):
        entity_id = entity_ids[index]
        best_candidate = max(
            (utilities[id(candidate)] for candidate in candidates[entity_id]),
            default=float("-inf"),
        )
        upper_bounds[index] = upper_bounds[index + 1] + max(
            null_utilities[entity_id], best_candidate
        )

    best_score = float("-inf")
    best_assignment: Dict[str, Optional[Mapping[str, Any]]] = {}
    best_found = False
    search_nodes = 0

    def search(
        index: int,
        used_boxes: List[Sequence[float]],
        score: float,
        assignment: Dict[str, Optional[Mapping[str, Any]]],
    ) -> None:
        nonlocal best_score, best_assignment, best_found, search_nodes
        search_nodes += 1
        if search_nodes > max_search_nodes:
            counts = ", ".join(
                f"{entity_id}={len(candidates[entity_id])}"
                for entity_id in entity_ids
            )
            raise GraphExtractionError(
                "Joint grounding assignment exceeded the deterministic search "
                f"budget of {max_search_nodes} nodes (candidate counts: {counts}). "
                "Reduce --max-grounding-candidates-per-entity or increase "
                "--max-joint-search-nodes."
            )
        if best_found and score + upper_bounds[index] <= best_score + 1e-12:
            return
        if index == len(entity_ids):
            if score > best_score + 1e-12:
                best_score = score
                best_assignment = dict(assignment)
                best_found = True
            return
        entity_id = entity_ids[index]
        ranked = sorted(
            enumerate(candidates[entity_id]),
            key=lambda item: (-utilities[id(item[1])], item[0]),
        )
        for _, candidate in ranked:
            if any(bbox_iou(candidate["bbox"], used) > max_iou for used in used_boxes):
                continue
            assignment[entity_id] = candidate
            search(
                index + 1,
                used_boxes + [candidate["bbox"]],
                score + utilities[id(candidate)],
                assignment,
            )
        assignment[entity_id] = None
        search(
            index + 1,
            used_boxes,
            score + null_utilities[entity_id],
            assignment,
        )
        assignment.pop(entity_id, None)

    search(0, [], 0.0, {})
    selected = {
        entity_id: candidate
        for entity_id, candidate in best_assignment.items()
        if candidate is not None
    }
    unassigned = {
        entity_id for entity_id in entity_ids
        if candidates[entity_id] and entity_id not in selected
    }
    ambiguous: set[str] = set()
    if support_ambiguity_margin >= 0:
        for missing_id in sorted(unassigned):
            for missing_candidate in candidates[missing_id]:
                missing_support = support_scores.get(id(missing_candidate), 0.0)
                for selected_id, selected_candidate in list(selected.items()):
                    selected_support = support_scores.get(id(selected_candidate), 0.0)
                    if (
                        bbox_iou(missing_candidate["bbox"], selected_candidate["bbox"])
                        > max_iou
                        and abs(missing_support - selected_support)
                        <= support_ambiguity_margin
                    ):
                        ambiguous.update({missing_id, selected_id})
    for entity_id in ambiguous:
        selected.pop(entity_id, None)
    unassigned.update(ambiguous)
    return selected, unassigned, ambiguous


def assign_distinct_entity_candidates(
    candidates: Mapping[str, Sequence[Mapping[str, Any]]], max_iou: float
) -> Tuple[Dict[str, Mapping[str, Any]], set[str]]:
    """Compatibility wrapper using exact joint matching without temporal support."""
    utilities = {
        id(candidate): float(candidate["confidence"])
        for entity_candidates in candidates.values()
        for candidate in entity_candidates
    }
    selected, unassigned, _ = assign_joint_entity_candidates(
        candidates,
        utilities,
        {entity_id: 0.0 for entity_id in candidates},
        max_iou,
        support_scores={id(candidate): 0.0 for entity_candidates in candidates.values()
                        for candidate in entity_candidates},
        support_ambiguity_margin=-1.0,
    )
    return selected, unassigned


def assign_same_name_candidates(
    candidates: Mapping[str, Sequence[Mapping[str, Any]]], max_iou: float
) -> Tuple[Dict[str, Mapping[str, Any]], set[str]]:
    """Backward-compatible same-name entry point using joint matching."""
    return assign_distinct_entity_candidates(candidates, max_iou)


def _load_grounding_functions() -> Tuple[Callable[..., Any], ...]:
    sys.path.insert(0, str(PROJECT_ROOT))
    try:
        from eval.evaluate_benchmark import (  # type: ignore
            compute_clip_text_sim,
            compute_selection_score,
            crop_entity,
            get_clip_model,
            get_grounding_dino,
            ground_one_entity_in_frame,
        )
    except Exception as exc:
        raise GraphExtractionError(
            "Could not import EECBench's GroundingDINO adapter. "
            "Install the evaluator dependencies first."
        ) from exc
    return (
        get_grounding_dino,
        get_clip_model,
        ground_one_entity_in_frame,
        crop_entity,
        compute_clip_text_sim,
        compute_selection_score,
    )


def ground_entities(
    entities: Sequence[Mapping[str, Any]],
    sample: VideoSample,
    *,
    device: str,
    box_threshold: float,
    text_threshold: float,
    max_query_attributes: int,
) -> Tuple[List[Dict[str, Any]], int, List[str]]:
    (
        get_grounding_dino,
        get_clip_model,
        ground_one_entity,
        crop_entity,
        compute_clip_text_sim,
        compute_selection_score,
    ) = _load_grounding_functions()
    try:
        get_grounding_dino(device=device, strict=True)
        get_clip_model(device=device)
    except Exception as exc:
        raise GraphExtractionError(
            f"EntityBench-style GroundingDINO/CLIP stack failed to load: {exc}"
        ) from exc

    grounded = [copy.deepcopy(dict(entity)) for entity in entities]
    by_id = {entity["id"]: entity for entity in grounded}
    queries = {
        entity["id"]: build_grounding_query(entity, max_query_attributes)
        for entity in grounded
    }
    attempted_frames: Dict[str, List[int]] = {}
    output_boxes: Dict[str, List[Dict[str, Any]]] = {
        entity["id"]: [] for entity in grounded
    }
    selection_warnings: List[str] = []
    n_calls = 0

    for entity in grounded:
        evidence = set(entity["evidence_frame_ids"])
        attempted_frames[entity["id"]] = sorted(evidence & set(sample.reference_frame_ids))

    for frame_id in sample.reference_frame_ids:
        active = [
            entity for entity in grounded if frame_id in attempted_frames[entity["id"]]
        ]
        frame_height, frame_width = sample.frames[frame_id].shape[:2]
        for entity in active:
            entity_id = entity["id"]
            n_calls += 1
            try:
                raw = list(ground_one_entity(
                    sample.frames[frame_id],
                    entity_name=entity["name"],
                    description=queries[entity_id],
                    entity_type="open_vocabulary",
                    device=device,
                    box_threshold=box_threshold,
                    text_threshold=text_threshold,
                    return_all=True,
                    strict=True,
                ))
            except Exception as exc:
                raise GraphExtractionError(
                    f"GroundingDINO failed for {entity['id']} on frame {frame_id}: {exc}"
                ) from exc

            # Match EntityBench: score every threshold-passing detector
            # candidate with CLIP text similarity, crop sharpness, and crop
            # area.  Do not cap candidates before this scoring step.
            cleaned, rejected, truncated = sanitize_grounding_candidates(
                raw,
                frame_width=frame_width,
                frame_height=frame_height,
                max_candidates=max(1, len(raw)),
            )
            if rejected:
                selection_warnings.append(
                    f"Discarded {rejected} malformed/out-of-frame GroundingDINO "
                    f"candidate(s) for {entity['id']} ({entity['name']}) on "
                    f"reference frame {frame_id}."
                )
            if truncated:
                raise GraphExtractionError(
                    "Internal error: EntityBench-style candidate scoring must not "
                    "truncate threshold-passing GroundingDINO candidates."
                )

            best_detection: Optional[Mapping[str, Any]] = None
            best_components: Optional[Mapping[str, float]] = None
            for detection in cleaned:
                crop = crop_entity(sample.frames[frame_id], detection["bbox"])
                try:
                    clip_score = compute_clip_text_sim(
                        crop, queries[entity_id], device
                    )
                    components = compute_selection_score(
                        clip_score, crop, sample.frames[frame_id].shape
                    )
                except Exception as exc:
                    raise GraphExtractionError(
                        "EntityBench-style CLIP candidate scoring failed for "
                        f"{entity_id} ({entity['name']}) on frame {frame_id}: {exc}"
                    ) from exc
                # EntityBench updates only on a strict improvement, so a tie
                # deterministically retains the first detector candidate.
                if (
                    best_components is None
                    or components["selection"] > best_components["selection"]
                ):
                    best_detection = detection
                    best_components = components

            if best_detection is None or best_components is None:
                continue

            x1, y1, x2, y2 = best_detection["bbox"]
            normalized = [
                max(0.0, min(1.0, x1 / frame_width)),
                max(0.0, min(1.0, y1 / frame_height)),
                max(0.0, min(1.0, x2 / frame_width)),
                max(0.0, min(1.0, y2 / frame_height)),
            ]
            output_boxes[entity_id].append({
                "frame_id": frame_id,
                "bbox_xyxy_normalized": [round(value, 6) for value in normalized],
                "score": round(float(best_detection["confidence"]), 6),
            })

    for entity_id, entity in by_id.items():
        boxes = sorted(output_boxes[entity_id], key=lambda item: item["frame_id"])
        attempts = attempted_frames[entity_id]
        if boxes and len(boxes) == len(attempts):
            status = "grounded"
        elif boxes:
            status = "partially_grounded"
        else:
            status = "not_found"
        entity["grounding"] = {
            "query": queries[entity_id],
            "status": status,
            "boxes": boxes,
        }
        entity["reference_grounding"] = [
            {
                "frame_id": box["frame_id"],
                "reference_frame_path": str(
                    sample.frame_paths[box["frame_id"]].resolve()
                ),
                "bbox_xyxy_normalized": list(box["bbox_xyxy_normalized"]),
                "score": box["score"],
            }
            for box in boxes
        ]
    return grounded, n_calls, selection_warnings


def add_not_run_grounding(
    entities: Sequence[Mapping[str, Any]], max_query_attributes: int
) -> List[Dict[str, Any]]:
    result = []
    for source in entities:
        entity = copy.deepcopy(dict(source))
        entity["grounding"] = {
            "query": build_grounding_query(entity, max_query_attributes),
            "status": "not_run",
            "boxes": [],
        }
        entity["reference_grounding"] = []
        result.append(entity)
    return result


def build_final_graph(
    *,
    video_path: Path,
    video_id: str,
    shot_id: str,
    sample: VideoSample,
    semantics: Mapping[str, Any],
    grounded_entities: Sequence[Mapping[str, Any]],
    args: argparse.Namespace,
    n_grounding_calls: int,
    grounding_warnings: Sequence[str],
    codex_token_usage: Optional[Mapping[str, Optional[int]]],
) -> Dict[str, Any]:
    warnings = list(semantics["warnings"])
    warnings.extend(grounding_warnings)
    if args.skip_grounding:
        warnings.append("GroundingDINO was skipped; bounding boxes were not produced.")
    return {
        "schema_version": FINAL_SCHEMA_VERSION,
        "video_id": video_id,
        "shot_id": shot_id,
        "shot_metadata": {
            "source_video": str(video_path.resolve()),
            "num_frames": sample.num_frames,
            "fps": sample.fps,
            "duration_sec": sample.duration_sec,
            "reference_frame_ids": sample.reference_frame_ids,
        },
        "extraction_metadata": {
            "vlm_provider": "codex_cli" if args.semantic_json is None else "precomputed_json",
            "codex_cli_version": codex_version(args.codex_bin),
            "codex_model": args.codex_model or "configured_default",
            "codex_token_usage": (
                dict(codex_token_usage) if codex_token_usage is not None else None
            ),
            "vlm_prompt_version": PROMPT_VERSION,
            "semantic_confidence_note": "uncalibrated model self-report",
            "grounding_model": "GroundingDINO SwinT OGC",
            "grounding_device": args.device,
            "box_threshold": args.box_threshold,
            "text_threshold": args.text_threshold,
            "grounding_selector": "entitybench_clip_quality_v1_per_frame",
            "n_grounding_calls": n_grounding_calls,
        },
        "entities": list(grounded_entities),
        "relations": list(semantics["relations"]),
        "warnings": warnings,
    }


def validate_final_graph(graph: Mapping[str, Any]) -> None:
    top_keys = {
        "schema_version", "video_id", "shot_id", "shot_metadata",
        "extraction_metadata", "entities", "relations", "warnings",
    }
    _require_exact_keys(graph, top_keys, "final graph")
    frame_ids = set(graph["shot_metadata"]["reference_frame_ids"])
    for index, entity in enumerate(graph["entities"]):
        grounding = entity.get("grounding")
        if not isinstance(grounding, dict):
            raise GraphExtractionError(f"entities[{index}].grounding must be an object")
        _require_exact_keys(grounding, {"query", "status", "boxes"}, f"entities[{index}].grounding")
        if grounding["status"] not in GROUNDING_STATUSES:
            raise GraphExtractionError(f"Invalid grounding status: {grounding['status']!r}")
        if not isinstance(grounding["query"], str) or not grounding["query"].strip():
            raise GraphExtractionError(f"entities[{index}].grounding.query is empty")
        if not isinstance(grounding["boxes"], list):
            raise GraphExtractionError(f"entities[{index}].grounding.boxes must be an array")
        if grounding["status"] == "grounded" and not grounding["boxes"]:
            raise GraphExtractionError("grounded entity has no boxes")
        if grounding["status"] in {"not_found", "ambiguous", "not_run"} and grounding["boxes"]:
            raise GraphExtractionError(f"{grounding['status']} entity unexpectedly has boxes")
        for box in grounding["boxes"]:
            _require_exact_keys(box, {"frame_id", "bbox_xyxy_normalized", "score"}, "box")
            if box["frame_id"] not in frame_ids:
                raise GraphExtractionError(f"Box uses unsampled frame {box['frame_id']}")
            coords = box["bbox_xyxy_normalized"]
            if not isinstance(coords, list) or len(coords) != 4:
                raise GraphExtractionError("bbox_xyxy_normalized must contain four numbers")
            if any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1
                for v in coords
            ):
                raise GraphExtractionError("bbox coordinates must be numbers in [0, 1]")
            if not coords[0] < coords[2] or not coords[1] < coords[3]:
                raise GraphExtractionError(f"Invalid xyxy box: {coords}")
            _require_confidence(box["score"], "box.score")

        reference_grounding = entity.get("reference_grounding")
        if not isinstance(reference_grounding, list):
            raise GraphExtractionError(
                f"entities[{index}].reference_grounding must be an array"
            )
        if len(reference_grounding) != len(grounding["boxes"]):
            raise GraphExtractionError(
                f"entities[{index}].reference_grounding must correspond one-to-one "
                "with grounding.boxes"
            )
        for item, box in zip(reference_grounding, grounding["boxes"]):
            _require_exact_keys(
                item,
                {
                    "frame_id", "reference_frame_path",
                    "bbox_xyxy_normalized", "score",
                },
                "reference_grounding item",
            )
            if item["frame_id"] != box["frame_id"]:
                raise GraphExtractionError(
                    "reference_grounding frame_id does not match grounding box"
                )
            if (
                not isinstance(item["reference_frame_path"], str)
                or not item["reference_frame_path"].strip()
            ):
                raise GraphExtractionError("reference_frame_path must be nonempty")
            if item["bbox_xyxy_normalized"] != box["bbox_xyxy_normalized"]:
                raise GraphExtractionError(
                    "reference_grounding bbox does not match grounding box"
                )
            if item["score"] != box["score"]:
                raise GraphExtractionError(
                    "reference_grounding score does not match grounding box"
                )


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def render_annotated_video(
    video_path: Path,
    graph_path: Path,
    output_path: Path,
    *,
    box_mode: str,
) -> None:
    renderer = PROJECT_ROOT / "scripts" / "render_entity_graph_video.py"
    command = [
        sys.executable,
        str(renderer),
        str(video_path),
        str(graph_path),
        "--output",
        str(output_path),
        "--box-mode",
        box_mode,
    ]
    result = subprocess.run(
        command, text=True, capture_output=True, check=False
    )
    if result.returncode != 0:
        raise GraphExtractionError(
            "Annotated video rendering failed after the graph was written: "
            f"{_tail(result.stderr or result.stdout)}"
        )
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract a Codex+GroundingDINO semantic entity graph from one video shot."
    )
    parser.add_argument("video", type=Path, help="Path to one video shot")
    parser.add_argument("-o", "--output", type=Path, help="Output graph JSON path")
    parser.add_argument("--video-id", help="Graph video ID (default: video's parent directory)")
    parser.add_argument("--shot-id", help="Graph shot ID (default: video filename stem)")
    parser.add_argument("--n-reference-frames", type=int, default=6)
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--codex-model", default=None, help="Override Codex's configured model")
    parser.add_argument("--codex-timeout-sec", type=int, default=900)
    parser.add_argument(
        "--semantic-json",
        type=Path,
        help="Use a saved Codex semantic JSON instead of invoking Codex",
    )
    parser.add_argument("--device", default="cuda", help="GroundingDINO torch device")
    parser.add_argument("--box-threshold", type=float, default=0.25)
    parser.add_argument("--text-threshold", type=float, default=0.20)
    parser.add_argument("--max-query-attributes", type=int, default=3)
    parser.add_argument(
        "--skip-grounding",
        action="store_true",
        help="Produce semantics with grounding.status=not_run; intended for CPU tests",
    )
    parser.add_argument(
        "--keep-reference-frames",
        type=Path,
        help="Persist sampled JPEGs in this directory instead of a temporary directory",
    )
    parser.add_argument(
        "--annotated-video",
        type=Path,
        help="Annotated MP4 path (default: OUTPUT_STEM.annotated.mp4)",
    )
    parser.add_argument(
        "--annotation-box-mode",
        choices=("exact", "interpolate"),
        default="interpolate",
        help="Draw exact reference-frame detections only, or clearly labelled "
             "interpolation between detections (default: interpolate)",
    )
    parser.add_argument(
        "--skip-annotated-video",
        action="store_true",
        help="Do not create the automatic annotated MP4",
    )
    parser.add_argument("--verbose", action="store_true", help="Show Codex CLI output")
    args = parser.parse_args(argv)

    if args.n_reference_frames <= 0:
        parser.error("--n-reference-frames must be positive")
    if args.codex_timeout_sec <= 0:
        parser.error("--codex-timeout-sec must be positive")
    if args.max_query_attributes < 0:
        parser.error("--max-query-attributes cannot be negative")
    for flag in ("box_threshold", "text_threshold"):
        value = getattr(args, flag)
        if not 0 <= value <= 1:
            parser.error(f"--{flag.replace('_', '-')} must be in [0, 1]")
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    video_path = args.video.resolve()
    output = (args.output or video_path.with_suffix(".entity_graph.json")).resolve()
    annotated_output = (
        args.annotated_video.resolve()
        if args.annotated_video
        else output.with_name(f"{output.stem}.annotated.mp4")
    )
    if not args.skip_annotated_video and annotated_output == video_path:
        print("error: --annotated-video must not overwrite the source video", file=sys.stderr)
        return 2
    video_id = args.video_id or video_path.parent.name
    shot_id = args.shot_id or video_path.stem
    total_steps = 4 if args.skip_annotated_video else 5

    temporary_context: Optional[tempfile.TemporaryDirectory[str]] = None
    if args.keep_reference_frames:
        frame_dir = args.keep_reference_frames.resolve()
        frame_dir.mkdir(parents=True, exist_ok=True)
    else:
        temporary_context = tempfile.TemporaryDirectory(prefix="eecbench_entity_graph_")
        frame_dir = Path(temporary_context.name)

    try:
        print(
            f"[1/{total_steps}] Sampling {args.n_reference_frames} reference frames",
            file=sys.stderr,
        )
        sample = extract_reference_frames(video_path, args.n_reference_frames, frame_dir)

        if args.semantic_json:
            print(
                f"[2/{total_steps}] Loading semantic graph {args.semantic_json}",
                file=sys.stderr,
            )
            try:
                raw_semantics = json.loads(args.semantic_json.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise GraphExtractionError(f"Cannot load --semantic-json: {exc}") from exc
            codex_token_usage = None
        else:
            print(
                f"[2/{total_steps}] Calling Codex CLI for entities and semantic relations",
                file=sys.stderr,
            )
            codex_result = run_codex(
                sample,
                codex_bin=args.codex_bin,
                model=args.codex_model,
                timeout_sec=args.codex_timeout_sec,
                work_dir=frame_dir,
                verbose=args.verbose,
            )
            raw_semantics = codex_result.semantics
            codex_token_usage = codex_result.token_usage
        semantics = normalize_and_validate_semantics(raw_semantics, sample)

        if args.skip_grounding:
            print(
                f"[3/{total_steps}] Grounding skipped by request",
                file=sys.stderr,
            )
            grounded_entities = add_not_run_grounding(
                semantics["entities"], args.max_query_attributes
            )
            n_grounding_calls = 0
            grounding_warnings: List[str] = []
        else:
            print(
                f"[3/{total_steps}] Grounding entities with GroundingDINO",
                file=sys.stderr,
            )
            grounded_entities, n_grounding_calls, grounding_warnings = ground_entities(
                semantics["entities"],
                sample,
                device=args.device,
                box_threshold=args.box_threshold,
                text_threshold=args.text_threshold,
                max_query_attributes=args.max_query_attributes,
            )

        print(
            f"[4/{total_steps}] Validating and writing the final graph",
            file=sys.stderr,
        )
        graph = build_final_graph(
            video_path=video_path,
            video_id=video_id,
            shot_id=shot_id,
            sample=sample,
            semantics=semantics,
            grounded_entities=grounded_entities,
            args=args,
            n_grounding_calls=n_grounding_calls,
            grounding_warnings=grounding_warnings,
            codex_token_usage=codex_token_usage,
        )
        validate_final_graph(graph)
        atomic_write_json(output, graph)
        print(f"Wrote {output}", file=sys.stderr)
        if not args.skip_annotated_video:
            print(
                f"[5/{total_steps}] Rendering annotated video",
                file=sys.stderr,
            )
            render_annotated_video(
                video_path,
                output,
                annotated_output,
                box_mode=args.annotation_box_mode,
            )
        if args.semantic_json is None:
            print(
                f"Codex token usage: {format_token_usage(codex_token_usage)}",
                file=sys.stderr,
            )
        return 0
    except GraphExtractionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        if temporary_context is not None:
            temporary_context.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
