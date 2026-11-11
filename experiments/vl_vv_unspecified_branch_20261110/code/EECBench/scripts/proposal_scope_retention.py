"""Opt-in preparation for one retained proposal subset, never a physical split.

Pure validation only: no caller or existing pipeline enables this module by
importing it. Callers authenticate two completed, independently obtained reports
and their private source descriptors. Distinct source/thread strings and matching
hashes check that assertion's consistency; they cannot prove model independence
or pixel truth. Existing schema, physical, pair, and deferred-lineage checks remain
the outer caller's responsibility. These functions never edit input or cost logs.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
import hashlib
import json
import re
from typing import Any


POLICY_VERSION = "single_survivor_scope_retention_v0.1"
VERIFIER_IDS = ("verifier_1", "verifier_2")
PHYSICAL_CUES = {"physical_boundary", "direct_interaction", "temporal_continuity"}
SCOPE_CUES = PHYSICAL_CUES | {"same_instance_continuity"}
ALL_CUES = SCOPE_CUES | {
    "simultaneous_separation", "independent_interaction_or_trajectory",
    "integrated_component", "non_entity", "unresolved", "category_only",
}
REQUEST_FIELDS = {
    "parent_cluster_id", "parent_anonymous_proposal_ids",
    "retained_anonymous_proposal_ids", "residual_anonymous_proposal_ids",
    "existence_judgment", "salience_judgment", "proposal_scope_judgment",
    "retained_evidence", "physical_evidence_indices", "scope_evidence_indices",
    "residual_status", "reason",
}
EVIDENCE_FIELDS = {
    "frame_id", "coarse_locator", "support_quality", "anonymous_proposal_ids",
    "cue_type", "observation",
}


class RetentionContractError(ValueError):
    """A retention request, provenance binding, or transition is invalid."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RetentionContractError(message)


def _text(value: Any, label: str) -> str:
    _require(type(value) is str and bool(value.strip()), f"Invalid {label}")
    return value


def _ids(value: Any, label: str, *, empty: bool = False) -> frozenset[str]:
    _require(isinstance(value, (list, tuple)), f"{label} must be an ID array")
    for item in value:
        _text(item, label)
    _require(len(value) == len(set(value)) and (empty or bool(value)),
             f"{label} must contain unique nonempty IDs")
    return frozenset(value)


def _frames(value: Any) -> list[int]:
    _require(isinstance(value, (list, tuple)) and bool(value)
             and all(type(x) is int and x >= 0 for x in value)
             and len(value) == len(set(value)), "Invalid original frame IDs")
    return list(value)


def _sha(value: Any) -> str:
    try:
        data = json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RetentionContractError("Inputs must be finite JSON data") from exc
    return hashlib.sha256(data).hexdigest()


def _fields(value: Any, names: set[str], label: str) -> None:
    _require(isinstance(value, Mapping) and set(value) == names,
             f"{label} has missing or unknown fields")


def _ledger(value: Mapping[str, Any]):
    _require(isinstance(value, Mapping), "Ledger must be an object")
    _text(value.get("shot_id"), "ledger shot ID")
    rows = value.get("clusters")
    _require(isinstance(rows, list), "Ledger clusters must be an array")
    clusters, scopes, owners = {}, {}, {}
    for row in rows:
        _require(isinstance(row, Mapping), "Cluster must be an object")
        key = _text(row.get("cluster_id"), "cluster ID")
        _require(key not in clusters, "Duplicate cluster ID")
        scope = _ids(row.get("anonymous_proposal_ids"), "Cluster scope")
        _require(not set(owners).intersection(scope), "Duplicate proposal ownership")
        decision = row.get("decision")
        _require(decision in ("accept", "reject", "abstain"), "Invalid cluster decision")
        _require("final_entity" in row, "Missing final_entity")
        _require(isinstance(row["final_entity"], Mapping) if decision == "accept"
                 else row["final_entity"] is None, "Decision/final_entity mismatch")
        clusters[key], scopes[key] = row, scope
        owners.update({proposal: key for proposal in scope})
    return clusters, scopes, owners


def validate_retention_request(
    request: Mapping[str, Any], *, parent_cluster_id: str,
    parent_proposal_ids: Sequence[str], valid_frame_ids: Sequence[int],
) -> dict[str, Any]:
    """Validate dedicated subset evidence, never relabel an old parent witness.

    Initial decision eligibility is checked by the consensus builder, which owns
    the initial ledger. Both axes may cite the same direct subset observation;
    this does not turn one observation into two independent confirmations.
    """
    _fields(request, REQUEST_FIELDS, "Retention request")
    _text(parent_cluster_id, "parent ID")
    parent = _ids(parent_proposal_ids, "Authenticated parent scope")
    frames = set(_frames(valid_frame_ids))
    _require(request["parent_cluster_id"] == parent_cluster_id, "Wrong parent ID")
    _require(_ids(request["parent_anonymous_proposal_ids"], "Request parent scope") == parent,
             "Request parent universe differs from complete initial scope")
    retained = _ids(request["retained_anonymous_proposal_ids"], "Retained scope")
    residual = _ids(request["residual_anonymous_proposal_ids"], "Residual scope")
    _require(retained < parent, "Retained scope must be a nonempty proper subset")
    _require(residual == parent - retained, "Residual must be the exact parent complement")
    _require(request["residual_status"] == "unresolved", "Residual is not an existence verdict")
    _text(request["reason"], "retention reason")
    _require(request["existence_judgment"] == "confirmed"
             and request["salience_judgment"] == "graph_worthy"
             and request["proposal_scope_judgment"] == "resolved_single_scope",
             "Retained subset needs positive physical and scope judgments")
    evidence = request["retained_evidence"]
    _require(isinstance(evidence, list) and bool(evidence), "Retained evidence is required")
    for item in evidence:
        _fields(item, EVIDENCE_FIELDS, "Retained evidence item")
        _require(type(item["frame_id"]) is int and item["frame_id"] in frames,
                 "Evidence references an invalid original frame")
        _require(_ids(item["anonymous_proposal_ids"], "Evidence scope") <= retained,
                 "Retained evidence contains a parent, residual, or external proposal")
        _require(type(item["cue_type"]) is str and item["cue_type"] in ALL_CUES,
                 "Invalid evidence cue")
        _require(item["support_quality"] in ("strong", "moderate", "weak"),
                 "Invalid support_quality")
        _text(item["coarse_locator"], "observed coarse locator")
        _text(item["observation"], "pixel observation")
    for key, cues in (("physical_evidence_indices", PHYSICAL_CUES),
                      ("scope_evidence_indices", SCOPE_CUES)):
        indices = request[key]
        _require(isinstance(indices, list) and bool(indices)
                 and all(type(i) is int and 0 <= i < len(evidence) for i in indices)
                 and len(indices) == len(set(indices)), "Invalid " + key)
        _require(all(set(evidence[i]["anonymous_proposal_ids"]) == retained
                     and evidence[i]["cue_type"] in cues for i in indices),
                 key + " requires direct positive exact-retained-scope witnesses")
    return {
        "parent_cluster_id": parent_cluster_id,
        "parent_anonymous_proposal_ids": sorted(parent),
        "retained_anonymous_proposal_ids": sorted(retained),
        "residual_anonymous_proposal_ids": sorted(residual),
        "residual_status": "unresolved", "request_sha256": _sha(request),
        "physical_evidence_indices": list(request["physical_evidence_indices"]),
        "scope_evidence_indices": list(request["scope_evidence_indices"]),
    }


def build_retention_consensus(
    verifier_reports: Sequence[Mapping[str, Any]], *,
    initial_decisions: Mapping[str, Any], valid_frame_ids: Sequence[int],
    report_sources: Mapping[str, Mapping[str, Any]],
    verifier_ids: Sequence[str] = VERIFIER_IDS,
) -> dict[str, Any]:
    """Require two authenticated report sources and the exact same retained set.

    Reports have shot_id, verifier_id, retention_requests; other original report
    fields are preserved in the private input binding. Source descriptors contain
    source_id, thread_id, report_sha256. That hash is finite canonical JSON with
    sorted keys, compact separators and ensure_ascii=False, not a raw-file hash.
    Callers must supply completed valid reports and authenticate those descriptors.
    """
    roster = _ids(verifier_ids, "Verifier roster")
    _require(len(roster) == 2, "Exactly two independent verifier sources are required")
    frames = _frames(valid_frame_ids)
    clusters, scopes, _ = _ledger(initial_decisions)
    _require(isinstance(verifier_reports, (list, tuple)) and len(verifier_reports) == 2,
             "Both complete verifier reports are required")
    _require(isinstance(report_sources, Mapping) and set(report_sources) == roster,
             "Report sources must cover the exact verifier roster")
    reports, requests, source_ids, threads = {}, {}, set(), set()
    for report in verifier_reports:
        _require(isinstance(report, Mapping), "Verifier report must be an object")
        key = report.get("verifier_id")
        _require(type(key) is str and key in roster and key not in reports,
                 "Unknown or duplicate verifier report")
        _require(report.get("shot_id") == initial_decisions["shot_id"], "Wrong verifier shot")
        source = report_sources[key]
        _fields(source, {"source_id", "thread_id", "report_sha256"}, "Private report source")
        source_id = _text(source["source_id"], "report source ID")
        thread = _text(source["thread_id"], "independent verifier thread")
        _require(source_id not in source_ids and thread not in threads,
                 "Verifier source IDs and threads must be distinct")
        _require(type(source["report_sha256"]) is str
                 and re.fullmatch(r"[0-9a-f]{64}", source["report_sha256"]) is not None
                 and source["report_sha256"] == _sha(report), "Report source hash mismatch")
        source_ids.add(source_id)
        threads.add(thread)
        rows = report.get("retention_requests")
        _require(isinstance(rows, list), "retention_requests must be an array")
        requests[key] = {}
        for index, request in enumerate(rows):
            _require(isinstance(request, Mapping), "Retention request must be an object")
            parent = request.get("parent_cluster_id")
            _require(type(parent) is str and parent in clusters, "Unknown retention parent")
            _require(parent not in requests[key], "Duplicate retention parent in one report")
            _require(clusters[parent]["decision"] == "accept" and len(scopes[parent]) >= 2,
                     "Retention parent must initially accept at least two proposals")
            proof = validate_retention_request(
                request, parent_cluster_id=parent, parent_proposal_ids=sorted(scopes[parent]),
                valid_frame_ids=frames)
            requests[key][parent] = {"verifier_id": key, "request_index": index, **proof}
        reports[key] = report
    parents = sorted(set().union(*(set(rows) for rows in requests.values())))
    records = []
    for parent in parents:
        proofs = [requests[key][parent] for key in sorted(roster) if parent in requests[key]]
        exact = len(proofs) == 2 and proofs[0]["retained_anonymous_proposal_ids"] == proofs[1]["retained_anonymous_proposal_ids"]
        records.append({
            "parent_cluster_id": parent,
            "status": "authorized_single_survivor" if exact else "no_consensus",
            "reason": "exact_two_source_retained_subset" if exact else
                      "missing_request" if len(proofs) != 2 else "retained_subset_disagreement",
            "retained_anonymous_proposal_ids": proofs[0]["retained_anonymous_proposal_ids"] if exact else [],
            "residual_anonymous_proposal_ids": proofs[0]["residual_anonymous_proposal_ids"] if exact else [],
            "proofs": proofs,
        })
    return {
        "policy_version": POLICY_VERSION,
        "records": deepcopy(records),
        "input_binding": {
            "initial_decisions_sha256": _sha(initial_decisions), "valid_frame_ids": frames,
            "verifier_ids": sorted(roster),
            "verifier_reports": deepcopy([reports[key] for key in sorted(roster)]),
            "report_sources": deepcopy(dict(report_sources)),
        },
        "automatic_acceptance": False, "physical_split_authorization": False,
        "residual_existence_asserted": False, "pixel_truth_verified": False,
        "independent_source_authentication": "caller_supplied_not_self_proven",
    }


def validate_retention_transition(
    initial_decisions: Mapping[str, Any], revised_decisions: Mapping[str, Any],
    consensus: Mapping[str, Any], *,
    independently_authorized_split_parent_ids: Sequence[str] = (),
) -> dict[str, Any]:
    """Check only retention ownership, leaving unrelated legal transitions outside.

    Complete-parent merges not touching retention parents remain the outer gate's
    responsibility. Other ordinary split parents must be explicitly authenticated
    by that caller and listed here; this function does not authorize them. They
    cannot overlap any parent on which either verifier requested retention.
    """
    _require(isinstance(consensus, Mapping) and consensus.get("policy_version") == POLICY_VERSION,
             "Unknown retention policy")
    binding = consensus.get("input_binding")
    _require(isinstance(binding, Mapping), "Missing retention input binding")
    _require(binding.get("initial_decisions_sha256") == _sha(initial_decisions),
             "Retention consensus belongs to another initial ledger")
    _require(set(binding) == {"initial_decisions_sha256", "valid_frame_ids", "verifier_ids",
                              "verifier_reports", "report_sources"}, "Invalid retention input binding")
    rebuilt = build_retention_consensus(
        binding["verifier_reports"], initial_decisions=initial_decisions,
        valid_frame_ids=binding["valid_frame_ids"], report_sources=binding["report_sources"],
        verifier_ids=binding["verifier_ids"])
    _require(_sha(rebuilt) == _sha(consensus), "Retention consensus/proofs were altered")
    initial, scopes, owners = _ledger(initial_decisions)
    final, final_scopes, final_owners = _ledger(revised_decisions)
    _require(initial_decisions["shot_id"] == revised_decisions["shot_id"], "Revision changed shot ID")
    _require(set(owners) == set(final_owners), "Revision lost or added original proposals")
    records = {row["parent_cluster_id"]: row for row in rebuilt["records"]}
    external = _ids(independently_authorized_split_parent_ids, "External split parent IDs", empty=True)
    _require(external <= set(initial) and not external.intersection(records),
             "External split authorization is unknown or overlaps retention")
    audited, not_applied, outer_only = [], [], []
    for parent, scope in scopes.items():
        destination_ids = {final_owners[p] for p in scope}
        row = records.get(parent)
        if row is None:
            _require(len(destination_ids) <= 1 or parent in external,
                     "Unauthorized scope contraction for parent " + parent)
            outer_only.append(parent)
            continue
        _require(all(final_scopes[key] <= scope for key in destination_ids),
                 "Retention parent absorbed or was absorbed by another parent")
        if len(destination_ids) == 1:
            owner = next(iter(destination_ids))
            not_applied.append({"parent_cluster_id": parent, "disposition": "not_applied",
                                "final_cluster_id": owner, "final_decision": final[owner]["decision"],
                                "reason": "complete_parent_scope_preserved"})
            continue
        _require(row["status"] == "authorized_single_survivor",
                 "Scope contraction lacks exact retention consensus")
        retained = frozenset(row["retained_anonymous_proposal_ids"])
        survivors = {final_owners[p] for p in retained}
        _require(len(survivors) == 1, "Authorized retained subset was repartitioned")
        survivor = next(iter(survivors))
        _require(final_scopes[survivor] == retained, "Final survivor is not the exact authorized subset")
        remainder = destination_ids - {survivor}
        _require(all(final[key]["decision"] in ("reject", "abstain")
                     and final[key]["final_entity"] is None for key in remainder),
                 "Residual proposals cannot own an accepted entity")
        count = sum(final[key]["decision"] == "accept" for key in destination_ids)
        _require(count <= int(initial[parent]["decision"] == "accept") and count <= 1,
                 "Retention increased accepted entity count")
        audited.append({"parent_cluster_id": parent, "disposition": "applied",
                        "survivor_cluster_id": survivor,
                        "survivor_decision": final[survivor]["decision"],
                        "retained_anonymous_proposal_ids": sorted(retained),
                        "residual_cluster_ids": sorted(remainder),
                        "residual_anonymous_proposal_ids": sorted(scope - retained),
                        "initial_accepted_count": 1, "final_accepted_count": count})
    return {
        "policy_version": POLICY_VERSION, "audited_transitions": audited,
        "audited_parent_ids": sorted(row["parent_cluster_id"] for row in audited),
        "retention_requested_parent_ids": sorted(records),
        "not_applied_transitions": not_applied,
        "outer_validation_only_parent_ids": sorted(outer_only),
        "externally_authorized_split_parent_ids": sorted(external),
        "all_original_proposals_accounted_once": True,
        "residual_existence_asserted": False, "pixel_truth_verified": False,
        "outer_schema_physical_pair_and_lineage_validation_required": True,
    }
