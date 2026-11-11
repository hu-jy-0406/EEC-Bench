"""Anonymous single-crop geometry and observation contracts, without image I/O.

The driver selects candidates and verifies/copies actual pixels. This module
neither chooses candidates nor establishes correspondence to their identities.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from fractions import Fraction
import json
import math
import re

import jsonschema

from single_frame_pixel_survey import SCHEMA_PATH, SCHEMA_VERSION

PROTOCOL_VERSION = "candidate_local_crop_survey_views_v0.1"
CONTEXT_PROTOCOL_VERSION = "candidate_local_crop_with_context_views_v0.1"
GEOMETRY_POLICY_VERSION = "candidate_local_crop_geometry_v0.1"
INSTRUCTIONS = """Inspect the one attached unannotated crop from a single frame.
Use only its visible pixels and the safe view table below. Do not use tools,
shell commands, files, network, prior conversations or external information.
Return only the schema-conforming JSON. No target identity, category or count
is prescribed. Report directly visible observations and honest uncertainty.
An empty result is valid but does not establish complete coverage or absence
outside this crop. The crop's selection is not evidence of any particular object.

Describe appearance, visible boundaries and occlusion without guessing a subtype.
Keep whole, physical part, collection or unknown scope. A physical part is a
component scope; a partial boundary means a clipped or occluded observation.
Do not turn a whole's clipped visible portion into a separate physical component,
or assume a crop edge is a complete object boundary. Boundary detail alone does
not decide graph-worthiness. Preserve supported ordinary observations without
deciding which ones should become final graph nodes.

For each visible member with a distinguishable independent physical boundary,
record its supported observation scope separately. A collection description
must not replace separately supportable members. You may also observe the
collection at its different scope. Do not split texture, invent hidden members,
or infer an expected number. Keep collection/unknown and uncertainty when
members cannot be distinguished. There is no required count or category.

Use neutral region IDs r0001, r0002, ... unique within this response. Every region
must reference the supplied frame_id and view_id. bbox_xyxy is half-open
[left,top,right,bottom] in this CROP'S LOCAL pixels, with its top-left at [0,0].
Use the listed output_size=[width,height]; do not output normalized or original
image coordinates. Python performs the separate coordinate mapping. Enclose
only the actually visible extent. Do not complete hidden or clipped extent
beyond the crop edge. Use boundary_status=partial for clipped or occluded
boundaries. If geometry cannot be localized reliably, use bbox_xyxy=null with
boundary_status=uncertain rather than inventing a box.

No matching, alias, identity relation, track, temporal visibility or association
with any prior proposal is requested. Shared labels, repeated observations and
shared pixels are not independent identity evidence. Keep actual observations
and uncertainty; coverage_notes may explain limitations without claiming an
exhaustive inventory or establishing the identity of an unseen source candidate.
"""

CONTEXT_INSTRUCTIONS = """Inspect attachment 1, the unannotated crop, as the ONLY output view.
Attachment 2 is the complete original image of the SAME frame, provided only
as structural context to interpret visible whole/part scope and occlusion in
the crop. Do not add objects visible only outside the crop, complete hidden
or clipped boundaries, or use the original image's coordinates for output.
Every reported observation must have visible pixel support in attachment 1.
The second image is not a second independent observation or identity vote.
Its view_id is context-only and MUST NOT be referenced by any output region.

""" + INSTRUCTIONS.removeprefix(
    "Inspect the one attached unannotated crop from a single frame.\n"
).replace("Use only its visible pixels and the safe view table below.",
          "Use only these two images and the safe view table below.", 1)


def _size(value):
    if (not isinstance(value, list) or len(value) != 2
            or any(type(x) is not int or x <= 0 for x in value)):
        raise ValueError("source_size must contain two positive integer dimensions")
    return value


def _finite_number(value):
    return type(value) in (int, float) and (type(value) is int or math.isfinite(value))


def crop_geometry(bbox_xyxy, source_size) -> dict:
    """Pad a valid original-pixel box, expand about its center, round, then clip.

    Invalid/null source boxes are rejected, never repaired. Each continuous axis
    receives max(16, length/4) padding on both sides and is expanded to at least
    96 pixels about the original center. Only then are its ends rounded outward.
    Fraction arithmetic prevents inward floating-point rounding at an integer
    edge. The actual crop may be smaller than 96 when the source clips it.
    """
    width, height = _size(source_size)
    if (not isinstance(bbox_xyxy, list) or len(bbox_xyxy) != 4
            or not all(_finite_number(x) for x in bbox_xyxy)
            or not (0 <= bbox_xyxy[0] < bbox_xyxy[2] <= width)
            or not (0 <= bbox_xyxy[1] < bbox_xyxy[3] <= height)):
        raise ValueError("A finite positive-area bbox inside the source is required")
    lower, upper = [], []
    for a, b in ((bbox_xyxy[0], bbox_xyxy[2]), (bbox_xyxy[1], bbox_xyxy[3])):
        a, b = Fraction(a), Fraction(b)
        length, center = b - a, (a + b) / 2
        padded_length = max(Fraction(96), length + 2 * max(Fraction(16), length / 4))
        lower.append(math.floor(center - padded_length / 2))
        upper.append(math.ceil(center + padded_length / 2))
    requested = [*lower, *upper]
    actual = [max(0, lower[0]), max(0, lower[1]), min(width, upper[0]), min(height, upper[1])]
    return {"geometry_policy_version": GEOMETRY_POLICY_VERSION,
            "source_size": list(source_size), "requested_crop_xyxy": requested,
            "actual_crop_xyxy": actual,
            "clipped_flags": {"left": lower[0] < 0, "top": lower[1] < 0,
                              "right": upper[0] > width, "bottom": upper[1] > height}}


def _view(bundle):
    """Validate a strict mode and return its sole output crop, without image I/O."""
    if not isinstance(bundle, Mapping) or bundle.get("protocol_version") not in (
        PROTOCOL_VERSION, CONTEXT_PROTOCOL_VERSION
    ):
        raise ValueError("Unknown candidate-local-crop view policy")
    with_context = bundle["protocol_version"] == CONTEXT_PROTOCOL_VERSION
    frame_id = bundle.get("frame_id")
    if type(frame_id) is not int or frame_id < 0:
        raise ValueError("A nonnegative integer frame_id is required")
    views = bundle.get("views")
    if (not isinstance(views, list) or len(views) != (2 if with_context else 1)
            or not all(isinstance(view, Mapping) for view in views)):
        raise ValueError("View count must match the explicit candidate-crop policy")
    view = views[0]
    if (type(view.get("attachment_index")) is not int or view["attachment_index"] != 1
            or view.get("kind") != "candidate_crop"
            or not isinstance(view.get("view_id"), str)
            or re.fullmatch(r"view_[0-9]{4,}", view["view_id"]) is None
            or type(view.get("frame_id")) is not int or view["frame_id"] != frame_id
            or type(view.get("scale")) is not int or view["scale"] != 1):
        raise ValueError("Invalid anonymous crop view or frame reference")
    width, height = _size(view.get("source_size"))
    crop = view.get("crop_xyxy")
    if (not isinstance(crop, list) or len(crop) != 4 or any(type(x) is not int for x in crop)
            or not (0 <= crop[0] < crop[2] <= width) or not (0 <= crop[1] < crop[3] <= height)):
        raise ValueError("Actual crop must be a positive integer-pixel source intersection")
    if _size(view.get("output_size")) != [crop[2] - crop[0], crop[3] - crop[1]]:
        raise ValueError("Crop dimensions disagree with the unscaled source intersection")
    if any(not isinstance(view.get(k), str) or not view[k].strip() for k in ("path", "source_path")):
        raise ValueError("Nonempty crop and source paths are required")
    if any(not isinstance(view.get(k), str) or re.fullmatch(r"[0-9a-f]{64}", view[k]) is None
           for k in ("sha256", "source_sha256")):
        raise ValueError("Crop and source SHA-256 metadata are required")
    if with_context:
        context = views[1]
        if (view["view_id"] != "view_0001"
                or type(context.get("attachment_index")) is not int
                or context["attachment_index"] != 2
                or context.get("view_id") != "view_0002"
                or context.get("kind") != "context_original"
                or type(context.get("frame_id")) is not int
                or context["frame_id"] != frame_id
                or type(context.get("scale")) is not int or context["scale"] != 1):
            raise ValueError("Context must be the fixed second same-frame original view")
        if (context.get("path") != view["source_path"]
                or context.get("source_path") != view["source_path"]
                or context.get("sha256") != view["source_sha256"]
                or context.get("source_sha256") != view["source_sha256"]
                or _size(context.get("source_size")) != [width, height]
                or _size(context.get("output_size")) != [width, height]):
            raise ValueError("Context provenance must match this crop's complete original")
        context_crop = context.get("crop_xyxy")
        if (not isinstance(context_crop, list) or len(context_crop) != 4
                or any(type(x) is not int for x in context_crop)
                or context_crop != [0, 0, width, height]):
            raise ValueError("Context must cover the unscaled complete original image")
        expected_attachments = [view["path"], context["path"]]
    else:
        expected_attachments = [view["path"]]
    if bundle.get("attachments") != expected_attachments:
        raise ValueError("Attachments must exactly match the ordered views for this policy")
    return view


def build_survey_prompt(bundle: Mapping) -> str:
    """Expose no proposal, source-image geometry, origin, path, hash or selector."""
    view = _view(bundle)
    public = {key: view[key] for key in ("frame_id", "view_id", "output_size")}
    if bundle["protocol_version"] == CONTEXT_PROTOCOL_VERSION:
        public = {"output_crop": {"attachment_index": 1, **public},
                  "context_original": {"attachment_index": 2, "role": "context_only",
                                       "view_id": "view_0002", "frame_id": view["frame_id"]}}
        return (CONTEXT_INSTRUCTIONS + "\nRequired schema_version: " + SCHEMA_VERSION
                + "\nSafe view table (crop-local output only):\n"
                + json.dumps(public, sort_keys=True, indent=2))
    return (INSTRUCTIONS + "\nRequired schema_version: " + SCHEMA_VERSION
            + "\nSafe view table (crop-local pixels):\n" + json.dumps(public, sort_keys=True, indent=2))


def validate_survey(payload: Mapping, bundle: Mapping) -> dict:
    """Validate the unchanged full schema and derive only the fixed translation.

    The driver verifies actual files and locks raw bytes. Geometry correctness
    cannot establish that a region depicts the source candidate, even if an
    incorrect original-image coordinate happens to fit within the crop bounds.
    """
    view = _view(bundle)
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        jsonschema.Draft202012Validator(schema).validate(payload)
    except jsonschema.ValidationError as error:
        raise ValueError(f"Invalid candidate-crop survey schema: {error.message}") from error
    seen = set()
    for region in payload["regions"]:
        key = region["region_id"]
        if re.fullmatch(r"r[0-9]{4,}", key) is None or key in seen:
            raise ValueError("Region IDs must be unique neutral rNNNN IDs")
        seen.add(key)
        if (region["view_id"] != view["view_id"] or type(region["frame_id"]) is not int
                or region["frame_id"] != view["frame_id"]):
            raise ValueError("Region must reference this exact crop and frame")
        if not region["visual_description"].strip():
            raise ValueError("Region description must not be empty")
        box = region["bbox_xyxy"]
        if box is None:
            if region["boundary_status"] != "uncertain":
                raise ValueError("Unknown geometry requires uncertain boundary status")
        elif (len(box) != 4 or not all(_finite_number(x) for x in box)
              or not (0 <= box[0] < box[2] <= view["output_size"][0])
              or not (0 <= box[1] < box[3] <= view["output_size"][1])):
            raise ValueError("Invalid finite crop-local pixel box")
    derived = deepcopy(dict(payload))
    x, y = view["crop_xyxy"][:2]
    for region in derived["regions"]:
        box = region["bbox_xyxy"]
        region["original_bbox_xyxy"] = None if box is None else [box[0] + x, box[1] + y, box[2] + x, box[3] + y]
    derived["validation_summary"] = {"view_policy_version": bundle["protocol_version"],
                                     "frame_id": view["frame_id"],
                                     "coordinate_mapping": "crop_local_plus_actual_crop_origin",
                                     "raw_payload_unchanged": True,
                                     "visual_accuracy_established": False,
                                     "identity_established": False,
                                     "candidate_correspondence_established": False}
    return derived
