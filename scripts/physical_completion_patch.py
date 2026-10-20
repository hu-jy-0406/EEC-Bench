"""Pure, bounded transport of explicit physical-completion edits.

Inputs are an already validated immutable candidate and its authenticated
obligations. This module performs no I/O, model calls, visual inference, or
automatic proof completion. The materialized ledger must still pass the full
adjudication schema/base/identity, deferred-lineage, split and physical gates.
The static Codex schema is a checked copy of PATCH_SCHEMA, not loaded at runtime.
"""

from __future__ import annotations

import copy
import hashlib
import json

import jsonschema

import physical_review_completion as completion


PATCH_VERSION = "physical_completion_patch_v0.1"
# Transport budgets, not desired observation counts or calibrated visual limits.
# Never truncate, silently expand a budget, or retry a budget failure here.
MAX_NEW_EVIDENCE_PER_OWNER = 24
MAX_NEW_EVIDENCE_TOTAL = 256


class PhysicalCompletionPatchError(ValueError):
    """A patch exceeded its frozen permission, reference, or transport contract."""


def _require(condition, message):
    if not condition:
        raise PhysicalCompletionPatchError(message)


def _object(properties):
    return {"type": "object", "additionalProperties": False,
            "required": list(properties), "properties": properties}


def _array(items, **limits):
    return {"type": "array", "items": items, **limits}


def _nullable(value):
    return {"anyOf": [value, {"type": "null"}]}


def _enum(*values):
    return {"type": "string", "enum": list(values)}


_TEXT = {"type": "string", "minLength": 1}
_INDEX = {"type": "integer", "minimum": 0}
_REFS = _array({"$ref": "#/$defs/evidence_ref"})
_CLUSTER_FIELDS = {
    "decision": _nullable(_enum("accept", "abstain", "reject")),
    "decision_reason": _nullable(_TEXT),
    "identity_status": _nullable(_enum("resolved", "ambiguous")),
    "existence_judgment": _nullable(_enum("confirmed", "rejected", "uncertain")),
    "salience_judgment": _nullable(_enum("graph_worthy", "background_integrated", "ambiguous")),
    "proposal_scope_judgment": _nullable(_enum("resolved_single_scope", "mixed_scope", "unresolved")),
    "entity_confidence": _nullable({"type": "number", "minimum": 0, "maximum": 1}),
    "evidence_frame_ids": _nullable(_array(_INDEX, minItems=1)),
}
PATCH_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://eecbench.local/schemas/codex_physical_completion_patch_v0.1.schema.json",
    "title": "Bounded explicit physical completion patch v0.1",
    **_object({
        "schema_version": _enum(PATCH_VERSION), "shot_id": _TEXT,
        "slot_table_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "cluster_updates": _array({"$ref": "#/$defs/cluster_update"}),
        "new_evidence": _array({"$ref": "#/$defs/new_evidence"}, maxItems=MAX_NEW_EVIDENCE_TOTAL),
        "comparison_updates": _array({"$ref": "#/$defs/comparison_update"}),
        "resolution_updates": _array({"$ref": "#/$defs/resolution_update"}),
    }),
    "$defs": {
        "cluster_update": _object({"owner_cluster_id": _TEXT, **_CLUSTER_FIELDS}),
        "evidence": _object({
            "frame_id": _INDEX, "coarse_locator": _TEXT,
            "support_quality": _enum("strong", "moderate", "weak"),
            "anonymous_proposal_ids": _array(_TEXT, minItems=1),
            "cue_type": _enum("physical_boundary", "direct_interaction", "temporal_continuity",
                              "same_instance_continuity", "simultaneous_separation",
                              "independent_interaction_or_trajectory", "integrated_component",
                              "non_entity", "unresolved", "category_only"),
            "observation": _TEXT,
        }),
        "new_evidence": _object({"owner_cluster_id": _TEXT, "new_evidence_id": _TEXT,
                                 "observation": {"$ref": "#/$defs/evidence"}}),
        "evidence_ref": {"anyOf": [
            _object({"kind": _enum("existing"), "index": _INDEX,
                     "new_evidence_id": {"type": "null"}}),
            _object({"kind": _enum("new"), "index": {"type": "null"}, "new_evidence_id": _TEXT}),
        ]},
        "comparison_update": _object({
            "slot_id": _TEXT, "judgment": _enum("confirmed_same_scope", "confirmed_distinct", "unresolved"),
            "scope_relation": _enum("comparable", "whole_part", "group_member", "unresolved"),
            "evidence_refs": _REFS,
        }),
        "resolution_update": _object({"slot_id": _TEXT,
                                      "evidence_refs": _array({"$ref": "#/$defs/evidence_ref"}, minItems=1)}),
    },
}


def _canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise PhysicalCompletionPatchError("Material must contain finite JSON values") from exc


def _digest(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _frame_ids(candidate):
    frames = {row["frame_id"] for cluster in candidate["clusters"] for row in cluster["frame_presence"]}
    _require(all(type(frame) is int and frame >= 0 for frame in frames), "Invalid candidate frame IDs")
    return sorted(frames)


def build_completion_patch_slots(candidate_decisions, obligations):
    """Bind finite editable slots to exact candidate/obligation JSON content.

    Resolution keys are owner/axis/initial-target SET, never owner/partner. The
    table preserves an existing resolution and all its refs even when one slot
    also serves new pairs or a merged-initial-scope continuity obligation.
    """
    completion.validate_completion_scope(candidate_decisions, candidate_decisions, obligations)
    clusters, scopes = completion._ledger(candidate_decisions)
    permission = completion._permissions(candidate_decisions, obligations)
    pairs, comparison_slots, resolution_slots = [], [], []
    for a, b in sorted(tuple(sorted(pair)) for pair in permission["pairs"]):
        pair = {"pair_id": f"pair{len(pairs) + 1:04d}", "cluster_ids": [a, b],
                "union_anonymous_proposal_ids": sorted(scopes[a] | scopes[b])}
        source = next(row for row in obligations["pair_obligations"] if set(row["cluster_ids"]) == {a, b})
        pair["initial_target_cluster_ids"] = sorted(source["initial_target_cluster_ids"])
        pairs.append(pair)
        for owner, partner in ((a, b), (b, a)):
            existing = next((row for row in clusters[owner]["identity_comparisons"]
                             if row["other_cluster_id"] == partner), None)
            comparison_slots.append({"slot_id": f"comparison{len(comparison_slots) + 1:04d}",
                "owner_cluster_id": owner, "other_cluster_id": partner, "pair_id": pair["pair_id"],
                "existing_comparison": copy.deepcopy(existing)})
    for owner in sorted(permission["reviewed"]):
        for axis, targets in sorted(permission["slots"][owner], key=lambda item: (item[0], sorted(item[1]))):
            existing = next((row for row in clusters[owner]["revision_resolutions"]
                             if row["axis"] == axis and frozenset(row["target_cluster_ids"]) == targets), None)
            unary = [copy.deepcopy(row) for item in permission["model_view"]["cluster_obligations"]
                     if item["cluster_id"] == owner for row in item["axis_obligations"]
                     if row["axis"] == axis and frozenset(row["initial_target_cluster_ids"]) == targets
                     and row["revision_cannot_override"] is False]
            resolution_slots.append({"slot_id": f"resolution{len(resolution_slots) + 1:04d}",
                "owner_cluster_id": owner, "axis": axis, "anonymous_proposal_ids": sorted(scopes[owner]),
                "target_cluster_ids": sorted(targets), "existing_resolution": copy.deepcopy(existing),
                "cluster_axis_obligations": unary,
                "associated_pair_ids": [pair["pair_id"] for pair in pairs
                    if axis == "instance_correspondence" and owner in pair["cluster_ids"]
                    and frozenset(pair["initial_target_cluster_ids"]) == targets]})
    table = {
        "schema_version": PATCH_VERSION, "shot_id": candidate_decisions["shot_id"],
        "canonical_json_hash_algorithm": "sha256_sorted_keys_compact_utf8_finite_json",
        "candidate_sha256": _digest(candidate_decisions), "obligations_sha256": _digest(obligations),
        "new_evidence_budget": {"per_owner": MAX_NEW_EVIDENCE_PER_OWNER, "total": MAX_NEW_EVIDENCE_TOTAL,
                                "overflow_policy": "reject_without_truncation_or_retry"},
        "candidate_frame_ids": _frame_ids(candidate_decisions),
        "owners": [{"owner_cluster_id": key, "anonymous_proposal_ids": sorted(scopes[key]),
                    "editable_axes": sorted(permission["axes"][key]),
                    "original_evidence_count": len(clusters[key]["adjudicator_evidence"])}
                   for key in sorted(permission["reviewed"])],
        "pairs": pairs, "comparison_slots": comparison_slots, "resolution_slots": resolution_slots,
    }
    table["slot_table_sha256"] = _digest(table)
    return table


def _unique_rows(rows, key):
    indexed = {}
    for row in rows:
        value = row[key]
        _require(value not in indexed, "Duplicate update: " + value)
        indexed[value] = row
    return indexed


def _integer_list(values, allowed, label):
    _require(all(type(value) is int and value in allowed for value in values)
             and len(values) == len(set(values)), label)


def apply_completion_patch(candidate_decisions, obligations, slots, patch):
    """Apply explicit edits atomically to a deepcopy; do not run visual gates.

    Null cluster fields and omitted rows mean KEEP. Comparison/resolution refs
    are complete replacements explicitly selected by the model. No refs are
    inferred, merged from duplicate rows, inherited from a partner, or upgraded
    from partial evidence. The returned audit records transport validity only.
    """
    expected = build_completion_patch_slots(candidate_decisions, obligations)
    _require(_canonical(slots) == _canonical(expected), "Stale or altered frozen slot table")
    _canonical(patch)
    try:
        jsonschema.Draft202012Validator(PATCH_SCHEMA).validate(patch)
    except jsonschema.ValidationError as exc:
        raise PhysicalCompletionPatchError("Patch schema: " + exc.message) from exc
    _require(patch["slot_table_sha256"] == slots["slot_table_sha256"]
             and patch["shot_id"] == slots["shot_id"], "Patch belongs to another frozen context")
    before, scopes = completion._ledger(candidate_decisions)
    result = copy.deepcopy(candidate_decisions)
    after, _ = completion._ledger(result)
    owners = {row["owner_cluster_id"]: row for row in slots["owners"]}
    frames = set(slots["candidate_frame_ids"])
    updates = _unique_rows(patch["cluster_updates"], "owner_cluster_id")
    _require(set(updates) <= set(owners), "Update to a non-reviewed owner")
    axis_fields = {"physical_entity": {"existence_judgment", "salience_judgment"},
                   "proposal_scope": {"proposal_scope_judgment", "identity_status"},
                   "instance_correspondence": {"identity_status"}}
    for owner, update in updates.items():
        allowed = set().union(*(axis_fields[axis] for axis in owners[owner]["editable_axes"]))
        for field in {"existence_judgment", "salience_judgment", "proposal_scope_judgment", "identity_status"}:
            _require(update[field] is None or field in allowed, "Update outside the listed axis")
        for field in set(_CLUSTER_FIELDS) - {"entity_confidence", "evidence_frame_ids"}:
            if update[field] is not None:
                after[owner][field] = update[field]
        if after[owner]["decision"] != "accept":
            _require(update["entity_confidence"] is None and update["evidence_frame_ids"] is None,
                     "Withdrawal cannot update accepted entity support")
            after[owner]["final_entity"] = None
        else:
            for field in ("entity_confidence", "evidence_frame_ids"):
                if update[field] is not None:
                    if field == "evidence_frame_ids":
                        _integer_list(update[field], frames, "Invalid/duplicate entity evidence frames")
                    after[owner]["final_entity"][field] = copy.deepcopy(update[field])
    new_indices = {owner: {} for owner in owners}
    for row in patch["new_evidence"]:
        owner, evidence_id = row["owner_cluster_id"], row["new_evidence_id"]
        _require(owner in owners, "New evidence belongs to a non-reviewed owner")
        _require(evidence_id not in new_indices[owner], "Duplicate local evidence ID")
        _require(len(new_indices[owner]) < MAX_NEW_EVIDENCE_PER_OWNER, "Per-owner new evidence budget exceeded")
        observation = row["observation"]
        _integer_list([observation["frame_id"]], frames, "New evidence frame is not a candidate frame")
        scope = completion._ids(observation["anonymous_proposal_ids"], "New observation scope")
        allowed = [scopes[owner], *(frozenset(pair["union_anonymous_proposal_ids"]) for pair in slots["pairs"]
                                   if owner in pair["cluster_ids"])]
        _require(bool(scope & scopes[owner]) and any(scope <= limit for limit in allowed),
                 "New evidence addresses an unauthorized scope")
        new_indices[owner][evidence_id] = len(after[owner]["adjudicator_evidence"])
        after[owner]["adjudicator_evidence"].append(copy.deepcopy(observation))

    def references(owner, refs):
        indices = []
        for ref in refs:
            if ref["kind"] == "existing":
                index = ref["index"]
                _require(type(index) is int and 0 <= index < len(before[owner]["adjudicator_evidence"]),
                         "Existing reference is not an original owner-local index")
            else:
                _require(ref["new_evidence_id"] in new_indices[owner], "Unknown owner-local new evidence reference")
                index = new_indices[owner][ref["new_evidence_id"]]
            _require(index not in indices, "Duplicate evidence reference")
            indices.append(index)
        return indices

    replacements = []
    for kind, target_field in (("comparison", "identity_comparisons"), ("resolution", "revision_resolutions")):
        slot_index = {row["slot_id"]: row for row in slots[kind + "_slots"]}
        rows = _unique_rows(patch[kind + "_updates"], "slot_id")
        _require(set(rows) <= set(slot_index), "Unknown or unauthorized " + kind + " slot")
        for slot_id, update in rows.items():
            slot = slot_index[slot_id]
            owner = slot["owner_cluster_id"]
            indices = references(owner, update["evidence_refs"])
            if kind == "comparison":
                replacement = {"other_cluster_id": slot["other_cluster_id"], "judgment": update["judgment"],
                               "scope_relation": update["scope_relation"], "evidence_indices": indices}
                matches = [i for i, row in enumerate(after[owner][target_field])
                           if row["other_cluster_id"] == slot["other_cluster_id"]]
            else:
                replacement = {field: copy.deepcopy(slot[field])
                               for field in ("axis", "anonymous_proposal_ids", "target_cluster_ids")}
                replacement["evidence_indices"] = indices
                matches = [i for i, row in enumerate(after[owner][target_field])
                           if row["axis"] == slot["axis"] and set(row["target_cluster_ids"]) == set(slot["target_cluster_ids"])]
            _require(len(matches) <= 1, "Candidate contains duplicate slot rows")
            old = copy.deepcopy(after[owner][target_field][matches[0]]) if matches else None
            if matches:
                after[owner][target_field][matches[0]] = replacement
            else:
                after[owner][target_field].append(replacement)
            replacements.append({"kind": kind, "slot_id": slot_id, "owner_cluster_id": owner,
                                 "before": old, "after": copy.deepcopy(replacement)})
    firewall = completion.validate_completion_scope(candidate_decisions, result, obligations)
    audit = {"schema_version": PATCH_VERSION, "patch_materialization_valid": True,
             "candidate_sha256": slots["candidate_sha256"], "slot_table_sha256": slots["slot_table_sha256"],
             "patch_sha256": _digest(patch), "materialized_sha256": _digest(result),
             "new_evidence_budget": copy.deepcopy(slots["new_evidence_budget"]),
             "new_evidence_index_map": new_indices, "explicit_slot_replacements": replacements,
             "original_evidence_indices_preserved": True, "proposal_ownership_preserved": True,
             "evidence_scope_expanded": False, "reciprocal_comparisons_inferred": False,
             "independent_observations_created_by_python": False, "visual_truth_verified": False,
             "full_schema_base_identity_lineage_split_and_gate_validation_required": True,
             "completion_firewall": firewall}
    return result, audit
