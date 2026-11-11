"""Experimental candidate-blind pixel views and survey contracts; no model calls.

The geometry validator establishes coordinate/reference consistency, never visual
truth, object completeness, graph-worthiness, or proposal correspondence.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re

import jsonschema
from PIL import Image

PROTOCOL_VERSION = "blind_pixel_survey_views_v0.1"
SCHEMA_VERSION = "blind_pixel_survey_v0.1"
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "blind-pixel-survey.v0.1.schema.json"
INSTRUCTIONS = """This is a candidate-blind visual survey of exactly one shot.
Use only the attached images and the attachment table below. Do not use tools,
shell commands, files, network, prior conversations, or external information.
Return only the schema-conforming JSON. No entity names, counts, boxes, earlier
judgments, proposal ledgers, or expected answers have been supplied as targets.
There is no target entity count. Report visually supported observations and
honest uncertainty; an empty survey is permitted but is not a completeness claim.

The first six attachments are original full frames in temporal order. The next
four are fixed corner crops from the first frame, followed by four from the last
frame, each ordered top-left, top-right, bottom-left, bottom-right. Each crop is
ceil(0.6*width) by ceil(0.6*height), copied from decoded original pixels without
resizing, annotation, sharpening or generated detail. The nominal overlap is
20% of the full image width/height, approximately one third of a crop dimension;
integer rounding is retained. These are overlapping views, not extra frames or
independent observations. A crop edge is not a physical boundary. Use full-frame
context to distinguish a bounded whole, part, collection, and unresolved scope.
Boundaries and local detail alone do not establish graph-worthiness. Preserve
ordinary visible fixtures as observations without forcing a graph-node decision.

Assign neutral IDs r0001, r0002, ... to observed regions and t0001, t0002, ... to
provisional tracks. Describe appearance, visible boundary, occlusion and support
directly, rather than guessing a specific subtype. A region is one observation
in one named view and frame. bbox_xyxy is [left,top,right,bottom] in that VIEW'S
local pixel coordinates, half-open, with origin at its upper-left. Use its listed
width and height; do not mentally convert to full-frame coordinates. Bound the
visible region only, never hallucinate an occluded extent. Use boundary_status
partial for a clipped/occluded boundary. If reliable geometry is unavailable,
use bbox_xyxy=null and boundary_status=uncertain, without inventing a box.

Each track must contain exactly one frame_states row for every original frame.
visible means some region is actually observed (even when its bbox is unknown),
and references one or more regions from that frame. occluded means a supported
occlusion explanation; out_of_view means outside that original full frame, not
merely outside a crop. Use uncertain when absence/identity cannot be resolved.
Non-visible states have empty region_ids. Every observed region belongs to one
provisional track. Track IDs are organizational hypotheses, NOT confirmed
cross-frame identity, entity counts, acceptance, or proposal aliases.

Use sparse region_relations for meaningful continuity, overlap, distinctness or
scope questions; do not enumerate all possible pairs. identity is same, distinct
or uncertain, based on a concrete visual_evidence description for the two exact
regions. Missing separation is not sameness. Normal camera movement, repeated
appearance and similar names do not establish independent object trajectories.
Separate physical boundaries or independent interaction can support distinctness;
actual continuity can support sameness. Use confirmed same/distinct only with
scope_relation=comparable. Directed whole/part or collection/member relations
keep identity=uncertain because they are not equal-scope identity comparisons.
Do not infer identity from shared track IDs. Conflicting or weak observations
remain uncertain. You may observe the same physical region in overlapping views;
record that correspondence explicitly rather than counting the crop twice.
"""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _corners(width: int, height: int) -> list[list[int]]:
    cw, ch = (3 * width + 4) // 5, (3 * height + 4) // 5
    return [[x, y, x + cw, y + ch] for y in (0, height - ch) for x in (0, width - cw)]


def build_views(reference_frames: Sequence[Mapping], output_dir: Path | str) -> dict:
    """Create eight PNG crops in a new exclusive directory; originals stay intact.

    Only frame_id, path and optional sha256 are consumed. Exactly six distinct,
    increasing nonnegative frame IDs are required. Extra input fields never flow
    into the result or prompt. No output is created before all sources validate.
    """
    if (not isinstance(reference_frames, Sequence) or isinstance(reference_frames, (str, bytes))
            or len(reference_frames) != 6):
        raise ValueError("Exactly six ordered reference frames are required")
    destination = Path(output_dir).absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    sources = []
    previous = -1
    for row in reference_frames:
        if not isinstance(row, Mapping):
            raise ValueError("Each reference frame must be a mapping")
        frame_id = row.get("frame_id")
        if type(frame_id) is not int or frame_id <= previous:
            raise ValueError("Frame IDs must be nonnegative, unique and increasing")
        previous = frame_id
        path_value = row.get("path")
        if not isinstance(path_value, (str, Path)) or not str(path_value):
            raise ValueError("A source image path is required")
        path = Path(path_value).resolve(strict=True)
        digest = _sha(path)
        if "sha256" in row and row["sha256"] != digest:
            raise ValueError("Source hash mismatch")
        with Image.open(path) as source:
            if source.mode not in {"RGB", "RGBA", "L", "LA", "P", "1"}:
                raise ValueError("Unsupported lossless PNG channel representation")
            source.load()
            size = list(source.size)
        sources.append({"frame_id": frame_id, "path": path, "sha256": digest, "size": size})
    destination.mkdir(parents=True, exist_ok=False)
    views = []

    def record(source, path, kind, view_id, box):
        views.append({"attachment_index": len(views) + 1, "view_id": view_id,
                      "frame_id": source["frame_id"], "kind": kind, "path": str(path),
                      "source_path": str(source["path"]), "source_sha256": source["sha256"],
                      "source_size": list(source["size"]), "crop_xyxy": box, "scale": 1,
                      "output_size": [box[2] - box[0], box[3] - box[1]], "sha256": _sha(path)})

    for source in sources:
        width, height = source["size"]
        record(source, source["path"], "original", f"frame_{source['frame_id']}_original", [0, 0, width, height])
    for source in (sources[0], sources[-1]):
        with Image.open(source["path"]) as image:
            for index, box in enumerate(_corners(*source["size"]), 1):
                view_id = f"frame_{source['frame_id']}_corner_{index}"
                path = destination / f"{view_id}.png"
                image.crop(box).save(path, format="PNG")
                record(source, path, "crop", view_id, box)
    if any(_sha(source["path"]) != source["sha256"] for source in sources):
        raise RuntimeError("Source changed while building blind survey views")
    return {"protocol_version": PROTOCOL_VERSION, "attachments": [v["path"] for v in views],
            "views": views, "instructions": INSTRUCTIONS}


def _int_list(value, length, *, positive=False):
    return (isinstance(value, list) and len(value) == length
            and all(type(x) is int and x >= (1 if positive else 0) for x in value))


def _view_index(bundle):
    """Validate fixed transform metadata without image I/O or trusted extra text."""
    if not isinstance(bundle, Mapping) or bundle.get("protocol_version") != PROTOCOL_VERSION:
        raise ValueError("Unknown blind survey view policy")
    views = bundle.get("views")
    if not isinstance(views, list) or len(views) != 14:
        raise ValueError("Fixed view policy requires fourteen views")
    originals = views[:6]
    frame_ids = [v.get("frame_id") if isinstance(v, Mapping) else None for v in originals]
    if (any(type(f) is not int or f < 0 for f in frame_ids)
            or frame_ids != sorted(set(frame_ids))):
        raise ValueError("Invalid original frame IDs")
    by_id = {}
    for index, view in enumerate(views):
        if not isinstance(view, Mapping):
            raise ValueError("Each view must be a mapping")
        if index < 6:
            source = originals[index]
            expected_id = f"frame_{frame_ids[index]}_original"
            expected_kind = "original"
        else:
            source = originals[0 if index < 10 else 5]
            expected_id = f"frame_{source['frame_id']}_corner_{(index - 6) % 4 + 1}"
            expected_kind = "crop"
        size = source.get("source_size")
        if not _int_list(size, 2, positive=True):
            raise ValueError("Invalid source dimensions")
        box = [0, 0, *size] if index < 6 else _corners(*size)[(index - 6) % 4]
        if (view.get("view_id") != expected_id or view.get("kind") != expected_kind
                or type(view.get("frame_id")) is not int or view["frame_id"] != source["frame_id"]
                or type(view.get("attachment_index")) is not int or view["attachment_index"] != index + 1
                or not _int_list(view.get("source_size"), 2, positive=True) or view["source_size"] != size
                or not _int_list(view.get("crop_xyxy"), 4) or view["crop_xyxy"] != box
                or not _int_list(view.get("output_size"), 2, positive=True)
                or view["output_size"] != [box[2] - box[0], box[3] - box[1]]
                or type(view.get("scale")) is not int or view["scale"] != 1):
            raise ValueError("View metadata disagrees with fixed original-pixel policy")
        by_id[expected_id] = view
    if bundle.get("attachments") != [v.get("path") for v in views]:
        raise ValueError("Attachment order disagrees with views")
    return frame_ids, by_id


def build_survey_prompt(view_bundle: Mapping) -> str:
    """Only fixed text and whitelisted neutral view metadata reach the model."""
    frame_ids, _ = _view_index(view_bundle)
    public = [{key: view[key] for key in ("attachment_index", "view_id", "frame_id", "kind", "output_size")}
              for view in view_bundle["views"]]
    return (INSTRUCTIONS + "\nRequired schema_version: " + SCHEMA_VERSION
            + "\nOriginal frame IDs: " + json.dumps(frame_ids)
            + "\nAttachment table (output_size=[width,height]):\n"
            + json.dumps(public, sort_keys=True, indent=2))


def _neutral_id(value, prefix):
    return isinstance(value, str) and re.fullmatch(prefix + r"[0-9]{4,}", value) is not None


def validate_survey(payload: Mapping, view_bundle: Mapping) -> dict:
    """Validate raw survey and return a deep copy with computed original boxes.

    The returned record adds original_bbox_xyxy per region and a validation
    summary. It is a derived audit record, not an alternative raw model response
    and is deliberately not accepted by the raw-output schema. Files/hashes are
    checked by the freezing driver; this function checks references/transforms.
    """
    frame_ids, view_index = _view_index(view_bundle)
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        jsonschema.Draft202012Validator(schema).validate(payload)
    except jsonschema.ValidationError as error:
        raise ValueError(f"Invalid blind survey schema: {error.message}") from error
    regions = {}
    for region in payload["regions"]:
        key = region["region_id"]
        if not _neutral_id(key, "r") or key in regions:
            raise ValueError("Region IDs must be unique neutral rNNNN IDs")
        regions[key] = region
        view = view_index.get(region["view_id"])
        if (view is None or type(region["frame_id"]) is not int
                or region["frame_id"] != view["frame_id"]):
            raise ValueError("Region frame/view reference mismatch")
        if not region["visual_description"].strip():
            raise ValueError("Region description must not be empty")
        box = region["bbox_xyxy"]
        if box is None:
            if region["boundary_status"] != "uncertain":
                raise ValueError("Unknown geometry must have uncertain boundary status")
        else:
            if (len(box) != 4 or any(type(x) not in (int, float) or not math.isfinite(x) for x in box)
                    or not (0 <= box[0] < box[2] <= view["output_size"][0])
                    or not (0 <= box[1] < box[3] <= view["output_size"][1])):
                raise ValueError("Invalid finite view-local pixel box")
    used = Counter()
    track_ids = set()
    for track in payload["tracks"]:
        key = track["track_id"]
        if not _neutral_id(key, "t") or key in track_ids:
            raise ValueError("Track IDs must be unique neutral tNNNN IDs")
        track_ids.add(key)
        if not track["visual_description"].strip():
            raise ValueError("Track description must not be empty")
        states = track["frame_states"]
        row_ids = [row["frame_id"] for row in states]
        if (any(type(f) is not int for f in row_ids) or len(row_ids) != 6
                or set(row_ids) != set(frame_ids)):
            raise ValueError("Every track requires one state per original frame")
        visible_count = 0
        for state in states:
            refs = state["region_ids"]
            if len(refs) != len(set(refs)):
                raise ValueError("Duplicate region references in frame state")
            if (state["visibility"] == "visible") != bool(refs):
                raise ValueError("Only visible frame states must reference observed regions")
            visible_count += bool(refs)
            for ref in refs:
                if ref not in regions or regions[ref]["frame_id"] != state["frame_id"]:
                    raise ValueError("Unknown or cross-frame region reference")
                used[ref] += 1
        if not visible_count:
            raise ValueError("A track needs at least one observed region")
    if used != Counter({key: 1 for key in regions}):
        raise ValueError("Every region must occur in exactly one track state")
    pairs = set()
    for relation in payload["region_relations"]:
        a, b = relation["region_id_a"], relation["region_id_b"]
        pair = tuple(sorted((a, b)))
        if a not in regions or b not in regions or a == b or pair in pairs:
            raise ValueError("Unknown, self or duplicate unordered region relation")
        pairs.add(pair)
        if not relation["visual_evidence"].strip():
            raise ValueError("Relations require a visual observation or uncertainty explanation")
        if relation["identity"] != "uncertain" and relation["scope_relation"] != "comparable":
            raise ValueError("Non-comparable scopes cannot assert equal-scope same/distinct identity")
    derived = deepcopy(dict(payload))
    for region in derived["regions"]:
        box = region["bbox_xyxy"]
        crop = view_index[region["view_id"]]["crop_xyxy"]
        region["original_bbox_xyxy"] = None if box is None else [box[0] + crop[0], box[1] + crop[1],
                                                               box[2] + crop[0], box[3] + crop[1]]
    derived["validation_summary"] = {"view_policy_version": PROTOCOL_VERSION,
                                     "coordinate_mapping": "view_local_plus_fixed_crop_origin",
                                     "raw_payload_unchanged": True,
                                     "tracks_are_provisional": True,
                                     "visual_accuracy_established": False}
    return derived
