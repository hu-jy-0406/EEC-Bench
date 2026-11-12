"""Revision-only transport with implicit, containing-cluster resolution ownership.

This is not an initial-output repair or a visual adjudicator. Only the explicit
wire header and the omitted resolution owner array are materialized. Complete
canonical schema and physical-extension validation run before a result returns.
The caller must still run its base, deferred-lineage, exact two-verifier split,
and physical gate checks; a valid resolution row need not supply a useful witness.
Use the JSON-text entry point on model output before ordinary JSON decoding so
duplicate object keys cannot be silently lost. Neither entry point writes files.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

import jsonschema

import physical_identity_review as physical


WIRE_VERSION = "physical_identity_revision_wire_v0.1"
POLICY_VERSION = "implicit_resolution_owner_materialization_v0.1"
CANONICAL_VERSION = "physical_identity_review_v0.6"
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas/codex_entity_revision_wire_v0.1.schema.json"
CANONICAL_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas/codex_entity_adjudication_v0.6.schema.json"


class RevisionWireError(ValueError):
    """Malformed wire input; no partial canonical ledger is returned."""


def _require(condition, message):
    if not condition:
        raise RevisionWireError(message)


def _finite_json(value):
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        _require(math.isfinite(value), "Nonfinite JSON number")
        return
    if type(value) is list:
        for item in value:
            _finite_json(item)
        return
    if type(value) is dict:
        for key, item in value.items():
            _require(type(key) is str, "JSON object keys must be strings")
            _finite_json(item)
        return
    raise RevisionWireError("Only native finite JSON objects, arrays and scalars are supported")


def _content_bytes(value):
    _finite_json(value)
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise RevisionWireError("Input must have a finite UTF-8 JSON representation") from exc


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, f"Duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise RevisionWireError(f"Nonfinite JSON constant: {value}")


def parse_revision_wire_json(text):
    """Decode exact JSON text with recursive duplicate-key/nonfinite rejection.

    This only parses; use materialize_revision_wire_json for the full contract.
    Markdown fences, trailing objects and canonical-version input are not guessed
    or repaired. Overflowed exponent numbers are rejected after JSON decoding.
    """
    _require(type(text) is str, "Raw wire output must be JSON text")
    try:
        text.encode("utf-8")
        payload = json.loads(text, object_pairs_hook=_unique_object,
                             parse_constant=_invalid_constant)
        _content_bytes(payload)
    except (json.JSONDecodeError, UnicodeError, RecursionError) as exc:
        raise RevisionWireError("Malformed UTF-8 JSON wire output") from exc
    return payload


_WIRE_BYTES = SCHEMA_PATH.read_bytes()
_CANONICAL_BYTES = CANONICAL_SCHEMA_PATH.read_bytes()
WIRE_SCHEMA = parse_revision_wire_json(_WIRE_BYTES.decode("utf-8"))
CANONICAL_SCHEMA = parse_revision_wire_json(_CANONICAL_BYTES.decode("utf-8"))
# JSON integer slots must not alias booleans or floating-point indices/frames.
_Validator = jsonschema.validators.extend(
    jsonschema.Draft202012Validator,
    type_checker=jsonschema.Draft202012Validator.TYPE_CHECKER.redefine(
        "integer", lambda checker, value: type(value) is int),
)
_WIRE_VALIDATOR = _Validator(WIRE_SCHEMA)
_CANONICAL_VALIDATOR = _Validator(CANONICAL_SCHEMA)


def _schema_validate(validator, payload, label):
    try:
        validator.validate(payload)
    except jsonschema.ValidationError as exc:
        pointer = "/" + "/".join(str(value).replace("~", "~0").replace("/", "~1")
                                  for value in exc.absolute_path)
        raise RevisionWireError(f"{label} schema failed at {pointer}: {exc.message}") from exc


def _context_ids(values, label, *, frames=False):
    _require(type(values) in (list, tuple), f"{label} must be a list or tuple")
    valid = (lambda x: type(x) is int and x >= 0) if frames else (lambda x: type(x) is str and bool(x))
    _require(all(valid(value) for value in values), f"Invalid {label}")
    _require(len(values) == len(set(values)), f"Duplicate {label}")
    return set(values)


def materialize_revision_wire(payload, *, valid_frame_ids, expected_proposal_ids,
                              expected_shot_id, initial_cluster_ids):
    """Materialize one explicitly selected revision wire object, without mutation.

    initial_cluster_ids refers to the authenticated *initial* ledger, not the
    final container names. It is used only to reject unknown target references.
    This dict entry point cannot certify that its caller preserved duplicate raw
    keys; its audit therefore records duplicate_key_check_performed=False.
    """
    raw_content = _content_bytes(payload)
    _schema_validate(_WIRE_VALIDATOR, payload, "Wire")
    _require(payload["schema_version"] == WIRE_VERSION, "Only explicit revision wire input is supported")
    _require(type(expected_shot_id) is str and bool(expected_shot_id), "Invalid expected shot ID")
    _require(payload["shot_id"] == expected_shot_id, "Wire shot ID differs from authenticated input")
    frames = _context_ids(valid_frame_ids, "valid frame IDs", frames=True)
    _require(bool(frames), "At least one valid original frame is required")
    expected = _context_ids(expected_proposal_ids, "expected proposal IDs")
    initial_ids = _context_ids(initial_cluster_ids, "initial cluster IDs")
    seen_proposals, seen_owners = set(), set()
    for cluster in payload["clusters"]:
        owner, scope = cluster["cluster_id"], cluster["anonymous_proposal_ids"]
        _require(owner not in seen_owners, "Duplicate final cluster owner")
        _require(len(scope) == len(set(scope)), "Duplicate proposal within final cluster")
        _require(not seen_proposals.intersection(scope), "Proposal assigned to multiple final clusters")
        seen_owners.add(owner)
        seen_proposals.update(scope)
        for resolution in cluster["revision_resolutions"]:
            _require(set(resolution["target_cluster_ids"]) <= initial_ids,
                     "Revision resolution references an unknown initial target")
    _require(seen_proposals == expected, "Final ownership must exactly cover the authenticated proposal universe")

    canonical = copy.deepcopy(payload)
    canonical["schema_version"] = CANONICAL_VERSION
    insertions = []
    for cluster_index, cluster in enumerate(canonical["clusters"]):
        owner_pointer = f"/clusters/{cluster_index}/anonymous_proposal_ids"
        for resolution_index, resolution in enumerate(cluster["revision_resolutions"]):
            pointer = f"/clusters/{cluster_index}/revision_resolutions/{resolution_index}"
            resolution["anonymous_proposal_ids"] = list(cluster["anonymous_proposal_ids"])
            insertions.append({
                "operation": "add", "json_pointer": pointer + "/anonymous_proposal_ids",
                "source_json_pointer": owner_pointer, "owner_cluster_id": cluster["cluster_id"],
                "anonymous_proposal_ids": list(cluster["anonymous_proposal_ids"]),
                "wire_resolution_content_sha256": _sha(_content_bytes(
                    payload["clusters"][cluster_index]["revision_resolutions"][resolution_index])),
                "canonical_resolution_content_sha256": _sha(_content_bytes(resolution)),
            })
    _schema_validate(_CANONICAL_VALIDATOR, canonical, "Canonical")
    try:
        physical.validate_adjudication_identity_fields(
            canonical, valid_frame_ids=valid_frame_ids,
            expected_proposal_ids=expected_proposal_ids)
    except physical.PhysicalIdentityContractError as exc:
        raise RevisionWireError(f"Canonical physical contract failed: {exc}") from exc
    audit = {
        "policy_version": POLICY_VERSION, "wire_schema_version": WIRE_VERSION,
        "canonical_schema_version": CANONICAL_VERSION, "shot_id": expected_shot_id,
        "wire_schema_file_sha256": _sha(_WIRE_BYTES),
        "canonical_schema_file_sha256": _sha(_CANONICAL_BYTES),
        "raw_content_sha256": _sha(raw_content),
        "canonical_content_sha256": _sha(_content_bytes(canonical)),
        "raw_json_text_sha256": None, "input_kind": "parsed_object",
        "duplicate_key_check_performed": False,
        "content_hash_encoding": "UTF-8 JSON; sorted keys; compact separators; ensure_ascii=false; finite only",
        "schema_header_change": {"operation": "replace", "json_pointer": "/schema_version",
                                 "old_value": WIRE_VERSION, "new_value": CANONICAL_VERSION},
        "resolution_owner_insertions": insertions,
        "cluster_count": len(canonical["clusters"]), "proposal_count": len(seen_proposals),
        "resolution_count": len(insertions), "complete_proposal_ownership_valid": True,
        "canonical_schema_valid": True, "canonical_physical_extension_valid": True,
        "caller_validation_required": ["base_adjudication", "deferred_lineage",
                                       "exact_two_verifier_split", "physical_identity_gate"],
        "visual_proof_created": False, "visual_accuracy_verified": False,
    }
    return canonical, audit


def materialize_revision_wire_json(text, **context):
    """Strict raw-text entry point; return only a fully validated pair of outputs."""
    payload = parse_revision_wire_json(text)
    canonical, audit = materialize_revision_wire(payload, **context)
    audit.update(raw_json_text_sha256=_sha(text.encode("utf-8")), input_kind="raw_json_text",
                 duplicate_key_check_performed=True)
    return canonical, audit
