"""Single-frame, candidate-blind observation contracts; no image writes or calls.

Validation establishes reference and coordinate consistency, not pixel truth,
complete discovery, graph-worthiness, or identity between observations.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import json
import math
from pathlib import Path
import re

import jsonschema

from blind_pixel_survey import build_survey_prompt as _validate_full_bundle

PROTOCOL_VERSION = "single_frame_pixel_survey_views_v0.1"
SCHEMA_VERSION = "single_frame_pixel_survey_v0.1"
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "single-frame-pixel-survey.v0.1.schema.json"
INSTRUCTIONS = """This is a candidate-blind visual survey of exactly one frame.
Use only the attached images and the attachment table below. Do not use tools,
shell commands, files, network, prior conversations, or external information.
Return only the schema-conforming JSON. No candidate names, boxes, judgments,
expected answers or target entity count are supplied. An empty survey is valid
but does not establish complete coverage. Preserve honest uncertainty.

The first attachment is the original full frame. When present, the following
four attachments are existing crops of that SAME frame, ordered top-left,
top-right, bottom-left, bottom-right. These are overlapping views, not additional
time points or independent evidence. Their pixels have not been resized,
sharpened or annotated. Crop edges are not physical boundaries. Use the original
view to understand a visible whole, physical part, collection or unknown scope.
A physical part is a component scope; a partial boundary means a clipped or
occluded observation. Do not label a whole's visible fragment as a physical part
merely because its boundary is partial. Specific subtype uncertainty does not
erase a visible observation. Boundaries alone do not decide graph-worthiness;
preserve ordinary visible fixtures without deciding final graph nodes.

For each visible member with a distinguishable independent physical boundary
in this frame, record its own supported observation scope. A collection
description must not replace separately supportable member observations. You
may also record the collection at its different scope. Do not split texture,
invent hidden members or infer an expected number. If members cannot be
distinguished, keep collection/unknown scope and uncertainty without forcing
enumeration. This is a visual instruction, not a required count or output gate.

Assign neutral region IDs r0001, r0002, ... unique within this response. Describe
appearance, visible boundary and occlusion directly. Each region belongs to its
named view_id and the single frame_id supplied below. bbox_xyxy is half-open
[left,top,right,bottom] in that VIEW'S LOCAL pixels, with origin at its top-left.
Use the listed output_size=[width,height], not normalized or full-frame box
coordinates. The listed crop_origin is for audit; Python maps boxes back to the
original image. Do not perform that conversion in your output. Enclose only the
actually visible extent in the selected view. Do not complete hidden or clipped
extent beyond a crop edge. Use boundary_status=partial for clipped or occluded
boundaries. If geometry is unreliable, use bbox_xyxy=null with
boundary_status=uncertain; never invent a box to satisfy the schema.

The same physical scope may be observed in multiple views. Keep each region's
actual source; no matching, alias, identity relation, track, temporal visibility
or cross-frame association is requested. Shared names or region IDs across
calls have no identity meaning. Do not manufacture such evidence. Describe
limitations in coverage_notes without claiming an exhaustive inventory.
"""

_VIEW_FIELDS = (
    "attachment_index", "view_id", "frame_id", "kind", "path", "source_path",
    "source_sha256", "source_size", "crop_xyxy", "scale", "output_size", "sha256",
)


def _integers(value, length, *, positive=False):
    return (isinstance(value, list) and len(value) == length
            and all(type(x) is int and x >= (1 if positive else 0) for x in value))


def _corners(width, height):
    cw, ch = (3 * width + 4) // 5, (3 * height + 4) // 5
    return [[x, y, x + cw, y + ch] for y in (0, height - ch) for x in (0, width - cw)]


def _view_index(bundle):
    """Check a standalone one-frame transform contract without filesystem I/O."""
    if not isinstance(bundle, Mapping) or bundle.get("protocol_version") != PROTOCOL_VERSION:
        raise ValueError("Unknown single-frame view policy")
    frame_id = bundle.get("frame_id")
    if type(frame_id) is not int or frame_id < 0:
        raise ValueError("A nonnegative integer frame_id is required")
    views = bundle.get("views")
    if not isinstance(views, list) or len(views) not in (1, 5) or not all(isinstance(v, Mapping) for v in views):
        raise ValueError("One original or one original and four crops are required")
    original = views[0]
    size = original.get("source_size")
    if not _integers(size, 2, positive=True):
        raise ValueError("Invalid original dimensions")
    by_id, paths = {}, []
    for index, view in enumerate(views):
        if any(key not in view for key in _VIEW_FIELDS):
            raise ValueError("Incomplete source view metadata")
        box = [0, 0, *size] if index == 0 else _corners(*size)[index - 1]
        expected_id = f"frame_{frame_id}_original" if index == 0 else f"frame_{frame_id}_corner_{index}"
        if (view["view_id"] != expected_id or view["kind"] != ("original" if index == 0 else "crop")
                or type(view["frame_id"]) is not int or view["frame_id"] != frame_id
                or type(view["attachment_index"]) is not int or view["attachment_index"] != index + 1
                or not _integers(view["source_size"], 2, positive=True) or view["source_size"] != size
                or not _integers(view["crop_xyxy"], 4) or view["crop_xyxy"] != box
                or not _integers(view["output_size"], 2, positive=True)
                or view["output_size"] != [box[2] - box[0], box[3] - box[1]]
                or type(view["scale"]) is not int or view["scale"] != 1):
            raise ValueError("Single-frame view geometry or reference mismatch")
        if any(not isinstance(view[k], str) or not view[k].strip() for k in ("path", "source_path")):
            raise ValueError("Nonempty original and view paths are required")
        if any(not isinstance(view[k], str) or re.fullmatch(r"[0-9a-f]{64}", view[k]) is None
               for k in ("sha256", "source_sha256")):
            raise ValueError("Source and view SHA-256 metadata are required")
        if view["source_path"] != original["path"] or view["source_sha256"] != original["sha256"]:
            raise ValueError("All views must reference the same original source")
        by_id[expected_id] = view
        paths.append(view["path"])
    if len(set(paths)) != len(paths) or bundle.get("attachments") != paths:
        raise ValueError("Attachment paths must be unique and in exact view order")
    return frame_id, by_id


def build_frame_view_bundle(full14bundle: Mapping, frame_id: int) -> dict:
    """Select existing images without reading, writing or transforming their bytes.

    Frame IDs are original IDs, not ordinal positions. Source hashes/pixels are
    verified by the driver. Only selected-frame metadata is copied, and only the
    attachment indices change; arbitrary source text never reaches the prompt.
    """
    if type(frame_id) is not int or frame_id < 0:
        raise ValueError("Select a nonnegative integer original frame_id")
    _validate_full_bundle(full14bundle)
    selected = [view for view in full14bundle["views"] if view["frame_id"] == frame_id]
    if not selected:
        raise ValueError("Selected frame is absent from the original bundle")
    if any(key not in view for view in selected for key in _VIEW_FIELDS):
        raise ValueError("Incomplete selected source metadata")
    views = [{key: deepcopy(view[key]) for key in _VIEW_FIELDS} for view in selected]
    for index, view in enumerate(views, 1):
        view["attachment_index"] = index
    result = {"protocol_version": PROTOCOL_VERSION, "frame_id": frame_id,
              "attachments": [v["path"] for v in views], "views": views, "instructions": INSTRUCTIONS}
    _view_index(result)
    return result


def build_survey_prompt(view_bundle: Mapping) -> str:
    """Render only fixed policy and a whitelist of this frame's safe geometry."""
    frame_id, _ = _view_index(view_bundle)
    public = []
    for view in view_bundle["views"]:
        row = {key: view[key] for key in ("attachment_index", "view_id", "frame_id", "kind", "output_size")}
        row["crop_origin"] = view["crop_xyxy"][:2]
        public.append(row)
    return (INSTRUCTIONS + "\nRequired schema_version: " + SCHEMA_VERSION
            + "\nOriginal frame ID: " + str(frame_id)
            + "\nAttachment table (view-local pixels):\n" + json.dumps(public, sort_keys=True, indent=2))


def validate_survey(payload: Mapping, view_bundle: Mapping) -> dict:
    """Validate raw observations and return a separate pure geometry audit record.

    No tracks are fabricated, repeated observations are not merged, and no
    member count or category is enforced. The derived record is not raw output.
    """
    frame_id, view_index = _view_index(view_bundle)
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        jsonschema.Draft202012Validator(schema).validate(payload)
    except jsonschema.ValidationError as error:
        raise ValueError(f"Invalid single-frame survey schema: {error.message}") from error
    seen = set()
    for region in payload["regions"]:
        key = region["region_id"]
        if re.fullmatch(r"r[0-9]{4,}", key) is None or key in seen:
            raise ValueError("Region IDs must be unique neutral rNNNN IDs")
        seen.add(key)
        view = view_index.get(region["view_id"])
        if view is None or type(region["frame_id"]) is not int or region["frame_id"] != frame_id:
            raise ValueError("Region must reference a view of this exact frame")
        if not region["visual_description"].strip():
            raise ValueError("Region description must not be empty")
        box = region["bbox_xyxy"]
        if box is None:
            if region["boundary_status"] != "uncertain":
                raise ValueError("Unknown geometry requires uncertain boundary status")
        elif (len(box) != 4 or any(type(x) not in (int, float)
                                 or (type(x) is float and not math.isfinite(x)) for x in box)
              or not (0 <= box[0] < box[2] <= view["output_size"][0])
              or not (0 <= box[1] < box[3] <= view["output_size"][1])):
            raise ValueError("Invalid finite view-local pixel box")
    derived = deepcopy(dict(payload))
    for region in derived["regions"]:
        box = region["bbox_xyxy"]
        x, y = view_index[region["view_id"]]["crop_xyxy"][:2]
        region["original_bbox_xyxy"] = None if box is None else [box[0] + x, box[1] + y, box[2] + x, box[3] + y]
    derived["validation_summary"] = {"view_policy_version": PROTOCOL_VERSION,
                                     "frame_id": frame_id,
                                     "coordinate_mapping": "view_local_plus_fixed_crop_origin",
                                     "raw_payload_unchanged": True,
                                     "visual_accuracy_established": False,
                                     "identity_established": False}
    return derived
