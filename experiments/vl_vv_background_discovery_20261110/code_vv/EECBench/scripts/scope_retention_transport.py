"""Explicit verifier transport for optional single-survivor retention.

This module validates the full selected schema before projecting only its two
extension fields away. It does not authenticate model calls, authorize a final
transition, or replace the existing target/pair/split/physical validators. The
caller retains raw bytes and their file hash, and passes original extended
reports (not these projections) to the two-source consensus builder.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import jsonschema

import proposal_scope_retention as retention


POLICY_VERSION = "single_survivor_scope_retention_v0.1"
DISABLED = "disabled"
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas/codex_entity_verification_retention_v0.1.schema.json"
CORE_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas/codex_entity_verification_v0.6.schema.json"
EXTENSION_FIELDS = frozenset({"scope_retention_policy", "retention_requests"})
PROTECTED_FLAGS = frozenset({"group_member_conflict", "possible_compact_assembly_partition"})


class RetentionTransportError(ValueError):
    """The selected verifier transport or its parent references are invalid."""


def _require(condition, message):
    if not condition:
        raise RetentionTransportError(message)


def _canonical(value):
    def check(item):
        if type(item) is dict:
            _require(all(type(key) is str for key in item), "JSON keys must be strings")
            for child in item.values():
                check(child)
        elif type(item) is list:
            for child in item:
                check(child)
        else:
            _require(item is None or type(item) in (str, int, float, bool), "Non-JSON value")
    check(value)
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RetentionTransportError("Nonfinite or invalid JSON value") from exc


def _hash(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _selected_schema(policy):
    _require(type(policy) is str and policy in (DISABLED, POLICY_VERSION),
             "Unknown scope retention policy")
    return CORE_SCHEMA_PATH if policy == DISABLED else SCHEMA_PATH


def _validate_schema(report, path):
    _canonical(report)
    try:
        jsonschema.Draft202012Validator(json.loads(path.read_text())).validate(report)
    except jsonschema.ValidationError as exc:
        raise RetentionTransportError("Verifier transport schema: " + exc.message) from exc


def _ids(value, label, *, empty=False):
    _require(type(value) in (list, tuple) and (bool(value) or empty)
             and all(type(item) is str and bool(item.strip()) for item in value)
             and len(value) == len(set(value)), "Invalid " + label)
    return frozenset(value)


def _initial_scopes(initial_decisions):
    _require(type(initial_decisions) is dict and type(initial_decisions.get("shot_id")) is str
             and bool(initial_decisions["shot_id"].strip()), "Invalid initial shot")
    _require(type(initial_decisions.get("clusters")) is list, "Invalid initial clusters")
    scopes, eligible, owned = {}, set(), set()
    for row in initial_decisions["clusters"]:
        _require(type(row) is dict, "Invalid initial cluster")
        key = row.get("cluster_id")
        _require(type(key) is str and bool(key.strip()) and key not in scopes,
                 "Invalid or duplicate initial cluster ID")
        scope = _ids(row.get("anonymous_proposal_ids"), "initial proposal scope")
        _require(not scope & owned, "Duplicate initial proposal ownership")
        decision = row.get("decision")
        _require(decision in ("accept", "reject", "abstain"), "Invalid initial decision")
        _require("final_entity" in row and (type(row["final_entity"]) is dict
                 if decision == "accept" else row["final_entity"] is None),
                 "Initial decision/final_entity mismatch")
        flags = _ids(row.get("uncertainty_flags", []), "initial uncertainty flags", empty=True)
        scopes[key] = scope
        owned.update(scope)
        if decision == "accept" and len(scope) >= 2 and not flags & PROTECTED_FLAGS:
            eligible.add(key)
    return scopes, eligible


def validate_and_project_verifier(report, *, policy, initial_decisions,
                                  valid_frame_ids, eligible_parent_ids=None):
    """Return a separate, unchanged-core v0.6 report under explicit transport.

    Enabled reports must carry a fresh explicit policy declaration and dedicated
    requests; an old body is never implicitly upgraded. This syntactic check does
    not prove freshness: the caller authenticates successful calls and raw hashes.
    An explicit eligible list may only narrow initial accept/nonprotected parents.
    Exact subset evidence is additive and never substitutes for the original
    parent review, original identity pairs, or an ordinary physical split.
    """
    path = _selected_schema(policy)
    _validate_schema(report, path)
    if policy == DISABLED:
        return deepcopy(report)
    _canonical(initial_decisions)
    scopes, eligible = _initial_scopes(initial_decisions)
    _require(report["shot_id"] == initial_decisions["shot_id"], "Verifier/initial shot mismatch")
    _require(type(valid_frame_ids) in (list, tuple) and bool(valid_frame_ids)
             and all(type(frame) is int and frame >= 0 for frame in valid_frame_ids)
             and len(valid_frame_ids) == len(set(valid_frame_ids)), "Invalid original frame IDs")
    if eligible_parent_ids is not None:
        selected = _ids(eligible_parent_ids, "eligible parent IDs", empty=True)
        _require(selected <= eligible, "Eligible list includes nonaccept, singleton, protected or unknown parent")
        eligible = selected
    review_ids = [row["cluster_id"] for row in report["reviews"]]
    _require(len(review_ids) == len(set(review_ids)) and set(review_ids) <= scopes.keys(),
             "Unknown or duplicate original parent review")
    seen = set()
    for request in report["retention_requests"]:
        parent = request["parent_cluster_id"]
        _require(parent in eligible, "Retention request names an ineligible parent")
        _require(parent not in seen, "Duplicate retention request parent")
        _require(parent in review_ids, "Retention request cannot replace its original parent review")
        try:
            retention.validate_retention_request(
                request, parent_cluster_id=parent, parent_proposal_ids=sorted(scopes[parent]),
                valid_frame_ids=valid_frame_ids)
        except retention.RetentionContractError as exc:
            raise RetentionTransportError(str(exc)) from exc
        seen.add(parent)
    core = {key: deepcopy(value) for key, value in report.items() if key not in EXTENSION_FIELDS}
    _validate_schema(core, CORE_SCHEMA_PATH)
    return core


def build_projection_audit(raw_report, core_report, *, policy):
    """Bind the sole allowed projection, separately from model-file provenance.

    Both report hashes use finite canonical JSON, not source-file bytes. This
    independently checks schema and exact core preservation, but callers must
    first validate requests with authenticated initial/eligibility/frame inputs.
    It is not a substitute for native call accounting or two-source consensus.
    """
    selected = _selected_schema(policy)
    _validate_schema(raw_report, selected)
    _validate_schema(core_report, CORE_SCHEMA_PATH)
    expected = {key: value for key, value in raw_report.items()
                if policy == DISABLED or key not in EXTENSION_FIELDS}
    _require(_canonical(core_report) == _canonical(expected),
             "Projection changed fields beyond the two transport extensions")
    return {
        "audit_version": "scope_retention_verifier_projection_v0.1",
        "scope_retention_policy": policy,
        "raw_report_sha256": _hash(raw_report), "core_report_sha256": _hash(core_report),
        "report_hash_encoding": "finite_canonical_json_utf8_sorted_compact_ensure_ascii_false",
        "raw_file_sha256": None,
        "raw_file_hash_requires_caller": True,
        "selected_schema": {"path": str(selected), "sha256": hashlib.sha256(selected.read_bytes()).hexdigest()},
        "core_schema": {"path": str(CORE_SCHEMA_PATH), "sha256": hashlib.sha256(CORE_SCHEMA_PATH.read_bytes()).hexdigest()},
        "removed_top_level_fields": [] if policy == DISABLED else sorted(EXTENSION_FIELDS),
        "core_fields_unchanged": True,
        "original_core_validators_required": True,
        "request_parent_eligibility_validation_requires_caller": True,
        "fresh_independent_call_authentication_requires_caller": True,
        "pixel_truth_verified": False,
    }
