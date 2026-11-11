"""Pure initial-only projection of non-proof observations spanning >=3 scopes.

The caller must first validate the complete raw adjudication schema/base contract
and retain the raw response. This module preserves eligible observations in an
audit sidecar and returns a PRE-PENDING ledger. The versioned initial pending
preparer is used only for shadow validation; the caller must invoke it formally
after this projection and persist both transformations. Nothing here declares
the raw response invalid, judges pixels, creates comparisons or routes models.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping

import physical_identity_review as identity


POLICY_VERSION = "initial_context_quarantine_v0.2"
MIN_CONTEXT_SCOPE_OWNERS = 3
CONTEXT_REFERENCE_RELATIONS = frozenset(("whole_part", "group_member"))


class InitialContextQuarantineError(ValueError):
    """A context observation or surrounding ledger cannot be projected safely."""


def _require(condition, message):
    if not condition:
        raise InitialContextQuarantineError(message)


def _hash(value):
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError) as exc:
        raise InitialContextQuarantineError("Only finite JSON material may be projected") from exc
    return hashlib.sha256(encoded).hexdigest()


def _rows(value, label):
    _require(isinstance(value, list) and all(isinstance(row, Mapping) for row in value), label)
    return value


def _ids(value, label):
    _require(isinstance(value, list) and bool(value)
             and all(isinstance(item, str) and bool(item) for item in value), label)
    _require(len(value) == len(set(value)), label + ": duplicate IDs")
    return frozenset(value)


def _reference_indices(value, count):
    # Initial-only preflight leaves valid [] for the pending preparer's explicit
    # withdrawal and sidecar; it does not supply evidence or change a judgment.
    _require(isinstance(value, list) and all(type(index) is int and 0 <= index < count for index in value)
             and len(value) == len(set(value)),
             "Invalid identity comparison evidence indices")
    return value


def project_initial_context(decisions, valid_frame_ids, expected_proposal_ids):
    """Return an immutable-source context projection and complete index sidecar.

    Classification always uses the complete RAW ownership map. Exact-own and
    binary observations keep existing semantics; undeclared binary partners
    receive no new exception. A >=3-owner observation must cover every touched
    scope completely and include its complete owner. It must be unreferenced or
    referenced only by unresolved whole-part/group-member comparisons. Every
    such item is quarantined, even if its raw declared-neighbor set allowed it.

    Positive references, partial multi-scope context, unknown IDs, bad structure
    and any initial revision resolutions are fatal. No judgment is downgraded
    here. Repeating on raw input is deterministic; projecting a derived input
    cannot discharge or replace the original audit and review obligations.
    """
    _require(isinstance(decisions, Mapping), "Initial ledger must be an object")
    raw_hash = _hash(decisions)
    _require(isinstance(valid_frame_ids, (list, tuple))
             and all(type(frame) is int and frame >= 0 for frame in valid_frame_ids)
             and len(valid_frame_ids) == len(set(valid_frame_ids)), "Invalid original frame IDs")
    _require(isinstance(expected_proposal_ids, (list, tuple))
             and all(isinstance(item, str) and bool(item) for item in expected_proposal_ids)
             and len(expected_proposal_ids) == len(set(expected_proposal_ids)), "Invalid expected proposal universe")
    _require(decisions.get("schema_version") == identity.SCHEMA_VERSION, "Incorrect physical identity schema version")
    clusters = _rows(decisions.get("clusters"), "Clusters must be objects in an array")
    scopes, proposal_owners = {}, {}
    for cluster in clusters:
        owner = cluster.get("cluster_id")
        _require(isinstance(owner, str) and bool(owner) and owner not in scopes, "Invalid or duplicate cluster ID")
        scope = _ids(cluster.get("anonymous_proposal_ids"), "Cluster must have a complete unique proposal scope")
        _require(not scope.intersection(proposal_owners), "Duplicate proposal ownership")
        scopes[owner] = scope
        proposal_owners.update({proposal: owner for proposal in scope})
    universe = frozenset(proposal_owners)
    _require(universe == frozenset(expected_proposal_ids), "Initial ledger does not cover the expected proposal universe")

    # Validate every record/reference before classifying or removing any item.
    for cluster in clusters:
        identity._axes(cluster)
        _require(cluster.get("decision") in {"accept", "abstain", "reject"}, "Invalid initial decision")
        _require(cluster.get("identity_status") in {"resolved", "ambiguous"}, "Invalid initial identity status")
        resolutions = _rows(cluster.get("revision_resolutions"), "Initial resolutions must be an array")
        _require(not resolutions, "Initial context projection cannot process revision resolutions")
        evidence = _rows(cluster.get("adjudicator_evidence"), "Evidence must be objects in an array")
        for observation in evidence:
            _ids(observation.get("anonymous_proposal_ids"), "Observation must have unique proposal IDs")
            _require(observation.get("support_quality") in {"strong", "moderate", "weak"}, "Invalid evidence support quality")
        # Universe-level validation is ONLY structural preflight. It never grants
        # a wider proof scope; the unchanged strict shadow below enforces that.
        identity._evidence(evidence, allowed_ids=universe, valid_frames=set(valid_frame_ids))
        partners = set()
        for comparison in _rows(cluster.get("identity_comparisons"), "Comparisons must be objects in an array"):
            partner = comparison.get("other_cluster_id")
            _require(isinstance(partner, str) and partner in scopes and partner != cluster["cluster_id"]
                     and partner not in partners, "Unknown, self or duplicate comparison partner")
            partners.add(partner)
            _require(comparison.get("judgment") in identity.IDENTITY_JUDGMENTS, "Invalid comparison judgment")
            _require(comparison.get("scope_relation") in identity.SCOPE_RELATIONS, "Invalid comparison scope relation")
            confirmed = comparison["judgment"] != "unresolved"
            _reference_indices(comparison.get("evidence_indices"), len(evidence))
            _require(not confirmed or comparison["scope_relation"] == "comparable",
                     "Noncomparable scopes cannot assert confirmed identity")

    quarantined, index_maps, review_scope_ids = [], {}, set()
    for cluster_index, cluster in enumerate(clusters):
        owner = cluster["cluster_id"]
        index_map, kept_count = [], 0
        for evidence_index, observation in enumerate(cluster["adjudicator_evidence"]):
            scope = frozenset(observation["anonymous_proposal_ids"])
            scope_owners = {proposal_owners[proposal] for proposal in scope}
            if len(scope_owners) < MIN_CONTEXT_SCOPE_OWNERS:
                index_map.append(kept_count)
                kept_count += 1
                continue
            complete_union = frozenset().union(*(scopes[key] for key in scope_owners))
            _require(scope == complete_union and scopes[owner] <= scope,
                     "Wide context must contain its full owner and every complete touched scope")
            references = []
            for comparison_index, comparison in enumerate(cluster["identity_comparisons"]):
                if evidence_index not in comparison["evidence_indices"]:
                    continue
                _require(comparison["judgment"] == "unresolved"
                         and comparison["scope_relation"] in CONTEXT_REFERENCE_RELATIONS,
                         "Wide context has a positive or unauthorized comparison reference")
                references.append({
                    "comparison_index": comparison_index,
                    "json_pointer": f"/clusters/{cluster_index}/identity_comparisons/{comparison_index}/evidence_indices",
                    "other_cluster_id": comparison["other_cluster_id"], "judgment": comparison["judgment"],
                    "scope_relation": comparison["scope_relation"],
                    "original_evidence_indices": list(comparison["evidence_indices"]),
                })
            quarantined.append({"owner_cluster_id": owner, "original_evidence_index": evidence_index,
                "original_json_pointer": f"/clusters/{cluster_index}/adjudicator_evidence/{evidence_index}",
                "observation": copy.deepcopy(observation), "observation_sha256": _hash(observation),
                "scope_owner_ids": sorted(scope_owners), "references": references})
            index_map.append(None)
            review_scope_ids.update(scope_owners)
        index_maps[owner] = index_map

    projected = copy.deepcopy(dict(decisions))
    for cluster in projected["clusters"]:
        index_map = index_maps[cluster["cluster_id"]]
        cluster["adjudicator_evidence"] = [item for i, item in enumerate(cluster["adjudicator_evidence"])
                                          if index_map[i] is not None]
        for comparison in cluster["identity_comparisons"]:
            comparison["evidence_indices"] = [index_map[i] for i in comparison["evidence_indices"]
                                              if index_map[i] is not None]
    for item in quarantined:
        index_map = index_maps[item["owner_cluster_id"]]
        for reference in item["references"]:
            reference["projected_evidence_indices"] = [index_map[i] for i in reference["original_evidence_indices"]
                                                        if index_map[i] is not None]

    # The existing preparer must still reject every remaining structural/scope
    # error. Its pending conversions are NOT returned or folded into this audit.
    _, shadow_audit = identity.prepare_initial_adjudication_for_review(
        projected, valid_frame_ids, expected_proposal_ids)
    audit = {
        "policy_version": POLICY_VERSION, "stage": "initial_adjudication", "visual_correction": False,
        "raw_sha256": raw_hash, "projected_sha256": _hash(projected),
        "quarantined_evidence": quarantined, "evidence_index_maps": index_maps,
        "review_scope_ids": sorted(review_scope_ids),
        "shadow_validation_policy": identity.INITIAL_PREPARATION_VERSION,
        "shadow_pending_comparison_count": len(shadow_audit["pending_comparisons"]),
        "strict_shadow_validation_passed": True, "requires_pending_preparation_before_use": True,
    }
    return projected, audit
