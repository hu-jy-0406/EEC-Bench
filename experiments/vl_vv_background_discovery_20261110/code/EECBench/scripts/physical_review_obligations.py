"""Read-only, source-blind checklist for an already computed physical gate.

This is not another gate and supplies no visual answers. Inputs must already
have passed the runner's schema/identity validators. Local consistency checks
prevent a stale or misbound audit from becoming a prompt for another scope.
Only typed fields and references to existing records enter the returned view;
names, model prose, source metadata and evidence text are deliberately omitted.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence


PHYSICAL_REVIEW_OBLIGATION_POLICY = "exact_scope_physical_review_obligations_v0.1"
FIRST_REVISION_PREVIEW_POLICY = "first_revision_partial_obligation_preview_v0.1"
PHYSICAL_VERSION = "physical_identity_review_v0.6"
GATE_POLICY = "source_independent_exact_scope_physical_identity"
PAIR_POLICY = "undirected_exact_union_revision_distinct_v0.1"
PHYSICAL_CUES = frozenset({"physical_boundary", "direct_interaction", "temporal_continuity"})
SCOPE_CUES = PHYSICAL_CUES | {"same_instance_continuity"}
DISTINCT_CUES = frozenset({"simultaneous_separation", "independent_interaction_or_trajectory"})
ALL_CUES = PHYSICAL_CUES | SCOPE_CUES | DISTINCT_CUES | {"integrated_component", "non_entity", "unresolved", "category_only"}
AXES = {
    "existence_judgment": {"confirmed", "rejected", "uncertain"},
    "salience_judgment": {"graph_worthy", "background_integrated", "ambiguous"},
    "proposal_scope_judgment": {"resolved_single_scope", "mixed_scope", "unresolved"},
}
UNARY_REASONS = {
    "final_physical_entity_not_confirmed_at_exact_scope": "physical_entity",
    "physical_entity:missing_exact_scope_revision_resolution": "physical_entity",
    "final_proposal_or_physical_identity_scope_unresolved": "proposal_scope",
    "proposal_scope:missing_exact_scope_revision_resolution": "proposal_scope",
    "merged_initial_targets_lack_confirmed_same_scope_correspondence": "instance_correspondence",
}
PAIR_REASON = ":retained_instance_correspondence_unresolved"
REVIEW_INSTRUCTION = """These are unfinished proof obligations from a strict
physical-gate preview, not visual findings, recommendations to accept, or a
target inventory. Reinspect the supplied pixels and original records at the
listed complete proposal scopes. Preserve the verifier judgments as recorded:
confirmed existence with non-graph-worthy salience is not an existence denial.
An existing typed witness is only a record to recheck, not verified pixel truth.
Never invent evidence, automatically add a resolution, copy/rebind a witness,
or manufacture a reciprocal comparison to pass a gate. An unordered distinct
pair may use one eligible endpoint's original complete exact-union proof; this
is not two independent observations. To retain both challenged scopes as accept,
satisfy the existing exact-scope contract and address any explicit contrary or
unresolved claim. Otherwise explicitly do not retain both accepts. Honest
uncertainty and abstention are valid. A resolution cannot override the exact
two-verifier split firewall. This checklist neither authorizes a split/merge nor
changes any decision. These references locate records in the supplied original
candidate or verifier report, not evidence slots in your returned ledger. Rebind
returned evidence indices to the actual final endpoint arrays, even if proposal
scope is unchanged. If scopes change, this preview no longer describes all their
obligations; establish evidence for the complete final scopes under the existing
lineage and split rules. Final validation and the physical gate still apply.
This checklist does not promise another preview or an additional model call.
"""

FIRST_REVISION_PREVIEW_INSTRUCTION = """PARTIAL physical-contract preview for the first revision.
This is a single preview of the supplied initial candidate at its current scopes,
not an exhaustive list of obligations for your future ledger. A unary failure can
prevent the preview gate from examining related pairs; rejected or abstained
candidates are not listed. Absence from this checklist does not mean reviewed,
resolved, or authorized. The complete original ledger, both verifier reports,
all supplied pair questions, and exact split consensus remain in force.
The checklist supplies no visual answer or instruction to accept. Retaining an
accept requires the existing exact-scope contract; honest uncertainty and
abstention remain valid. Newly retained, merged, split, or otherwise changed
scopes require their own complete evidence under the original rules and will
still face full final validation and the unchanged physical gate. Original
record references must not be copied as returned evidence indices. No additional
review call or fresh checklist is promised.
"""


def first_revision_preview_prompt(checklist: Mapping[str, Any]) -> str:
    """Serialize a validated checklist as a partial, non-authoritative supplement."""
    _require(checklist.get("policy_version") == PHYSICAL_REVIEW_OBLIGATION_POLICY
             and checklist.get("schema_version") == PHYSICAL_VERSION,
             "Wrong first-revision checklist policy")
    return (FIRST_REVISION_PREVIEW_INSTRUCTION + "\npartial_obligation_preview:\n"
            + json.dumps(checklist, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False))


class PhysicalReviewObligationError(ValueError):
    """The preview and its original scope-bound inputs do not agree."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PhysicalReviewObligationError(message)


def _rows(value: Any, label: str) -> list:
    _require(isinstance(value, list) and all(isinstance(x, Mapping) for x in value), label)
    return value


def _ids(value: Any, label: str) -> frozenset[str]:
    _require(isinstance(value, list) and bool(value)
             and all(isinstance(x, str) and bool(x) for x in value), label)
    _require(len(value) == len(set(value)), label + ": duplicate IDs")
    return frozenset(value)


def _index(rows: Any, key: str, label: str) -> dict:
    result = {}
    for row in _rows(rows, label):
        value = row.get(key)
        _require(isinstance(value, str) and bool(value) and value not in result,
                 label + ": invalid or duplicate ID")
        result[value] = row
    return result


def _axes(record: Mapping) -> dict:
    result = {key: record.get(key) for key in AXES}
    _require(all(isinstance(value, str) and value in AXES[key] for key, value in result.items()), "Invalid physical axis")
    return result


def _indices(item: Mapping, evidence: list) -> list[int]:
    value = item.get("evidence_indices")
    _require(isinstance(value, list)
             and all(type(i) is int and 0 <= i < len(evidence) for i in value)
             and len(value) == len(set(value)), "Invalid evidence indices")
    return list(value)


def _check_record(record: Mapping, evidence_key: str, universe: frozenset,
                  partners: Mapping, initial_ids: frozenset, own: frozenset | None = None) -> None:
    _axes(record)
    evidence = _rows(record.get(evidence_key), "Invalid evidence array")
    for item in evidence:
        _require(_ids(item.get("anonymous_proposal_ids"), "Evidence scope") <= universe,
                 "Evidence refers to unknown proposal")
        _require(type(item.get("frame_id")) is int and item["frame_id"] >= 0
                 and isinstance(item.get("cue_type"), str) and item["cue_type"] in ALL_CUES
                 and all(isinstance(item.get(k), str) and item[k].strip()
                         for k in ("coarse_locator", "observation")), "Invalid typed evidence")
    comparisons = _index(record.get("identity_comparisons", []), "other_cluster_id", "Comparisons")
    for other, item in comparisons.items():
        _require(other in partners and other != record.get("cluster_id"), "Unknown/self comparison")
        _require(item.get("judgment") in {"confirmed_same_scope", "confirmed_distinct", "unresolved"}
                 and item.get("scope_relation") in {"comparable", "whole_part", "group_member", "unresolved"},
                 "Invalid comparison enum")
        _indices(item, evidence)
    seen = set()
    for item in _rows(record.get("revision_resolutions", []), "Revision resolutions"):
        targets = _ids(item.get("target_cluster_ids"), "Resolution targets")
        scope = _ids(item.get("anonymous_proposal_ids"), "Resolution scope")
        axis = item.get("axis")
        _require(axis in {"physical_entity", "proposal_scope", "instance_correspondence"}
                 and targets <= initial_ids and scope == own, "Resolution scope/target mismatch")
        _require((axis, targets) not in seen, "Duplicate axis/target resolution")
        seen.add((axis, targets))
        _indices(item, evidence)


def _evidence_refs(record: Mapping, key: str, scope: frozenset, cues: frozenset,
                   indices: Sequence[int] | None = None) -> list[dict]:
    evidence = record.get(key, [])
    return [{"evidence_index": i, "frame_id": evidence[i]["frame_id"],
             "anonymous_proposal_ids": sorted(scope), "cue_type": evidence[i]["cue_type"]}
            for i in (range(len(evidence)) if indices is None else indices)
            if frozenset(evidence[i]["anonymous_proposal_ids"]) == scope and evidence[i]["cue_type"] in cues]


def _assessment(record: Mapping | None, key: str, scope: frozenset) -> dict:
    return {"record_present": record is not None,
            **(_axes(record) if record is not None else {k: None for k in AXES}),
            "exact_scope_physical_cue_records": _evidence_refs(record or {}, key, scope, PHYSICAL_CUES),
            "exact_scope_positive_scope_cue_records": _evidence_refs(record or {}, key, scope, SCOPE_CUES)}


def _has_resolution(record: Mapping, axis: str, targets: frozenset, scope: frozenset,
                    cues: frozenset) -> bool:
    return any(item["axis"] == axis and frozenset(item["target_cluster_ids"]) == targets
               and frozenset(item["anonymous_proposal_ids"]) == scope
               and _evidence_refs(record, "adjudicator_evidence", scope, cues, item["evidence_indices"])
               for item in record["revision_resolutions"])


def _endpoint(record: Mapping, partner: str, own: frozenset, other: frozenset,
              targets: frozenset) -> dict:
    union = own | other
    matches = [(i, x) for i, x in enumerate(record["identity_comparisons"])
               if x["other_cluster_id"] == partner]
    comparison = None
    status = "missing_comparison"
    if matches:
        i, item = matches[0]
        refs = _evidence_refs(record, "adjudicator_evidence", union, DISTINCT_CUES, item["evidence_indices"])
        comparison = {"comparison_index": i, "judgment": item["judgment"],
                      "scope_relation": item["scope_relation"], "evidence_indices": list(item["evidence_indices"]),
                      "exact_union_distinct_cue_records": refs}
        if item["scope_relation"] != "comparable":
            status = "noncomparable_or_unresolved_scope_relation"
        elif item["judgment"] != "confirmed_distinct":
            status = "explicit_" + item["judgment"]
        else:
            status = "exact_union_distinct_comparison" if refs else "missing_exact_union_comparison_witness"
    resolutions = []
    exact = []
    for i, item in enumerate(record["revision_resolutions"]):
        if item["axis"] != "instance_correspondence":
            continue
        refs = _evidence_refs(record, "adjudicator_evidence", union, DISTINCT_CUES, item["evidence_indices"])
        matches_scope = frozenset(item["anonymous_proposal_ids"]) == own and frozenset(item["target_cluster_ids"]) == targets
        resolutions.append({"resolution_index": i, "target_cluster_ids": sorted(item["target_cluster_ids"]),
                            "anonymous_proposal_ids": sorted(item["anonymous_proposal_ids"]),
                            "evidence_indices": list(item["evidence_indices"]),
                            "matches_own_scope_and_all_initial_targets": matches_scope,
                            "exact_union_distinct_cue_records": refs})
        if matches_scope:
            exact.append(resolutions[-1])
    resolution_ok = bool(exact and exact[0]["exact_union_distinct_cue_records"])
    resolution_status = ("exact_scope_distinct_resolution" if resolution_ok else
                         "missing_exact_union_resolution_witness" if exact else
                         "missing_exact_scope_and_target_resolution" if resolutions else "missing_resolution")
    return {"cluster_id": record["cluster_id"], "anonymous_proposal_ids": sorted(own),
            "comparison_status": status, "comparison_record": comparison,
            "resolution_status": resolution_status, "instance_resolution_records": resolutions,
            "complete_exact_union_revision_proof": status == "exact_union_distinct_comparison" and resolution_ok,
            "existing_exact_union_distinct_records_to_recheck": _evidence_refs(record, "adjudicator_evidence", union, DISTINCT_CUES)}


def build_physical_review_obligations(
    *, initial_decisions: Mapping[str, Any], candidate_decisions: Mapping[str, Any],
    verifier_reports: Sequence[Mapping[str, Any]], gate_audit: Mapping[str, Any],
    verifier_ids: Sequence[str] = ("verifier_1", "verifier_2"),
) -> dict[str, Any]:
    """Bind unfinished accept obligations to an existing strict gate preview.

    All inputs are read-only. A malformed/stale reference is an exception, not an
    empty checklist. Missing verifier coverage is a fact when the gate records it.
    The caller supplies validated inputs and owns any subsequent bounded review;
    this helper launches nothing and never synthesizes a ledger or resolution.
    """
    roster = tuple(verifier_ids)
    _require(len(roster) == 2 and len(set(roster)) == 2
             and all(isinstance(v, str) and v for v in roster), "Invalid verifier roster")
    _require(initial_decisions.get("schema_version") == candidate_decisions.get("schema_version") == PHYSICAL_VERSION,
             "Wrong physical ledger version")
    _require(initial_decisions.get("shot_id") == candidate_decisions.get("shot_id"), "Shot mismatch")
    initial = _index(initial_decisions.get("clusters"), "cluster_id", "Initial ledger")
    candidate = _index(candidate_decisions.get("clusters"), "cluster_id", "Candidate ledger")
    scopes = {}
    for label, ledger in (("initial", initial), ("candidate", candidate)):
        seen = set()
        scopes[label] = {}
        for k, row in ledger.items():
            scope = _ids(row.get("anonymous_proposal_ids"), label + " scope")
            _require(not scope & seen, "Duplicate proposal ownership")
            _require(row.get("decision") in {"accept", "abstain", "reject"}, "Invalid decision")
            seen.update(scope)
            scopes[label][k] = scope
    universe = frozenset().union(*scopes["initial"].values())
    _require(universe == frozenset().union(*scopes["candidate"].values()), "Proposal universe mismatch")
    targets = {k: frozenset(t for t, old in scopes["initial"].items() if old & own)
               for k, own in scopes["candidate"].items()}
    for label, ledger in (("initial", initial), ("candidate", candidate)):
        for k, row in ledger.items():
            _check_record(row, "adjudicator_evidence", universe, ledger, frozenset(initial), scopes[label][k])
    reports = _index(list(verifier_reports), "verifier_id", "Verifier reports")
    _require(set(reports) == set(roster), "Missing or unexpected verifier report")
    reviews = {}
    for v, report in reports.items():
        _require(report.get("schema_version") == PHYSICAL_VERSION
                 and report.get("shot_id") == initial_decisions.get("shot_id"), "Verifier version/shot mismatch")
        reviews[v] = _index(report.get("reviews"), "cluster_id", "Verifier reviews")
        _require(set(reviews[v]) <= set(initial), "Unknown verifier target")
        for row in reviews[v].values():
            _check_record(row, "evidence", universe, initial, frozenset(initial))
            for unit in _rows(row.get("proposed_physical_units", []), "Split units"):
                _require(_ids(unit.get("anonymous_proposal_ids"), "Split unit scope")
                         <= scopes["initial"][row["cluster_id"]], "Split unit outside its initial scope")
                _check_record(unit, "evidence", universe, initial, frozenset(initial))
    _require(gate_audit.get("schema_version") == PHYSICAL_VERSION and gate_audit.get("policy") == GATE_POLICY
             and gate_audit.get("distinct_revision_proof_policy") == PAIR_POLICY
             and gate_audit.get("required_verifier_ids") == list(roster), "Wrong gate policy/roster")
    gate = _index(gate_audit.get("records"), "cluster_id", "Gate records")
    _require(set(gate) == {k for k, c in candidate.items() if c["decision"] == "accept"},
             "Gate must cover exactly candidate accepts")
    assessments = {}
    pair_maps = {}
    reason_axes = {}
    for k, row in gate.items():
        own = scopes["candidate"][k]
        _require(_ids(row.get("anonymous_proposal_ids"), "Gate scope") == own
                 and _ids(row.get("initial_target_cluster_ids"), "Gate targets") == targets[k], "Gate scope/target mismatch")
        failures = row.get("failure_reasons")
        _require(isinstance(failures, list) and all(isinstance(x, str) for x in failures)
                 and len(failures) == len(set(failures))
                 and row.get("result") == ("abstain" if failures else "accept"), "Gate result/reasons mismatch")
        reason_axes[k] = {}
        for reason in failures:
            axis = UNARY_REASONS.get(reason)
            parts = reason.split(":")
            if axis is None and reason.endswith(PAIR_REASON):
                _require(len(parts) == 2 and parts[0] in gate and parts[0] != k, "Unknown pair failure scope")
                axis = "pair"
            if axis is None and parts[0] in targets[k]:
                valid = (len(parts) == 2 and parts[1] == "partial_target_without_exact_split_authorization"
                         or len(parts) == 3 and parts[1] in roster and parts[2] == "exact_split_unit_not_confirmed")
                if valid:
                    axis = "split_authorization"
            _require(axis is not None, "Unknown gate failure reason")
            reason_axes[k].setdefault(axis, []).append(reason)
        current = _assessment(candidate[k], "adjudicator_evidence", own)
        physical = (current["existence_judgment"] == "confirmed"
                    and current["salience_judgment"] == "graph_worthy"
                    and bool(current["exact_scope_physical_cue_records"]))
        scoped = (current["proposal_scope_judgment"] == "resolved_single_scope"
                  and bool(current["exact_scope_positive_scope_cue_records"])
                  and candidate[k].get("identity_status") == "resolved")
        _require(("final_physical_entity_not_confirmed_at_exact_scope" in failures) == (not physical)
                 and ("final_proposal_or_physical_identity_scope_unresolved" in failures) == (not scoped),
                 "Stale gate candidate-axis assessment")
        for axis, cues in (("physical_entity", PHYSICAL_CUES), ("proposal_scope", SCOPE_CUES),
                           ("instance_correspondence", frozenset({"same_instance_continuity"}))):
            reason = ("merged_initial_targets_lack_confirmed_same_scope_correspondence" if axis == "instance_correspondence"
                      else axis + ":missing_exact_scope_revision_resolution")
            _require(reason not in failures or not _has_resolution(candidate[k], axis, targets[k], own, cues),
                     "Stale gate missing-resolution claim")
        _require(type(row.get("exact_split_firewall_failed")) is bool
                 and row["exact_split_firewall_failed"] == ("split_authorization" in reason_axes[k]), "Split firewall mismatch")
        assessments[k] = []
        seen = set()
        for judgment in _rows(row.get("verifier_judgments"), "Gate verifier judgments"):
            v, target = judgment.get("verifier_id"), judgment.get("target_cluster_id")
            _require(v in roster and target in targets[k] and (v, target) not in seen, "Unknown/duplicate gate review")
            seen.add((v, target))
            overlap = own & scopes["initial"][target]
            partial = overlap != scopes["initial"][target]
            kind = "exact_consensus_split_unit" if partial else "complete_initial_target"
            _require(_ids(judgment.get("anonymous_proposal_ids"), "Gate review scope") == overlap
                     and judgment.get("scope_kind") == kind, "Gate review scope/kind mismatch")
            parent = reviews[v].get(target)
            unit = parent
            if partial:
                matches = [x for x in (parent or {}).get("proposed_physical_units", [])
                           if frozenset(x["anonymous_proposal_ids"]) == overlap]
                unit = matches[0] if len(matches) == 1 and (parent or {}).get("intra_cluster_split_judgment") == "split_into_multiple_physical_instances" else None
            present = judgment.get("record_present")
            _require(type(present) is bool and (not present or unit is not None)
                     and (partial or present == (unit is not None)), "Gate review presence mismatch")
            # An unauthorized/inexact partition can make an otherwise reported
            # child unusable. Preserve parent enums without inheriting them.
            assessed = _assessment(unit if present else None, "evidence", overlap)
            physical = (assessed["existence_judgment"] == "confirmed"
                        and assessed["salience_judgment"] == "graph_worthy"
                        and bool(assessed["exact_scope_physical_cue_records"]))
            scoped = (assessed["proposal_scope_judgment"] == "resolved_single_scope"
                      and bool(assessed["exact_scope_positive_scope_cue_records"]))
            _require(judgment.get("physical_confirmed") is physical
                     and judgment.get("proposal_scope_confirmed") is scoped, "Gate verifier assessment mismatch")
            assessments[k].append({"verifier_id": v, "initial_target_cluster_id": target,
                                   "anonymous_proposal_ids": sorted(overlap), "scope_kind": kind,
                                   "parent_review_axes": _axes(parent) if parent is not None else None,
                                   **assessed})
        _require(all({v for v, t in seen if t == target} in (set(), set(roster)) for target in targets[k]),
                 "Incomplete gate verifier judgment roster")
        pair_maps[k] = _index(row.get("identity_pair_judgments"), "other_cluster_id", "Gate pairs")
        _require(set(pair_maps[k]) <= set(gate) - {k}, "Unknown gate pair endpoint")
        _require(all(reason.split(":")[0] in pair_maps[k] for reason in reason_axes[k].get("pair", [])),
                 "Pair failure missing its gate judgment")
    pair_obligations = []
    failed_pairs = sorted({tuple(sorted((k, reason.split(":")[0]))) for k in gate
                           for reason in reason_axes[k].get("pair", [])})
    for a, b in failed_pairs:
        endpoints = [_endpoint(candidate[x], y, scopes["candidate"][x], scopes["candidate"][y], targets[a] | targets[b])
                     for x, y in ((a, b), (b, a))]
        raw = [candidate[x]["identity_comparisons"][e["comparison_record"]["comparison_index"]]
               for x, e in zip((a, b), endpoints) if e["comparison_record"] is not None]
        comparable = any(x["scope_relation"] not in {"whole_part", "group_member"} for x in raw)
        relation_conflict = comparable and any(x["scope_relation"] != "comparable" for x in raw)
        unresolved = relation_conflict or any(x["scope_relation"] not in {"whole_part", "group_member"}
                                             and x["judgment"] != "confirmed_distinct" for x in raw)
        proof = any(x["complete_exact_union_revision_proof"] for x in endpoints)
        for x, y in ((a, b), (b, a)):
            _require(y + PAIR_REASON in gate[x]["failure_reasons"] and x in pair_maps[y], "Asymmetric failed pair audit")
            pair = pair_maps[x][y]
            _require(pair.get("final_pair_unresolved_or_same_scope") is unresolved
                     and pair.get("final_pair_scope_relation_conflict") is relation_conflict
                     and pair.get("revision_confirms_distinct") is proof, "Stale pair proof/judgment audit")
            _require(unresolved or not (proof or pair.get("verifiers_confirm_distinct")
                                        or pair.get("unchanged_initial_pair_confirms_distinct")), "Failed pair has a gate basis for acceptance")
        pair_obligations.append({"cluster_ids": [a, b], "initial_target_cluster_ids": sorted(targets[a] | targets[b]),
                                 "union_anonymous_proposal_ids": sorted(scopes["candidate"][a] | scopes["candidate"][b]),
                                 "endpoint_records": endpoints, "final_explicit_unresolved_or_same_scope": unresolved,
                                 "final_scope_relation_conflict": relation_conflict,
                                 "either_endpoint_has_complete_revision_proof": proof,
                                 "obligation": "exact_union_distinct_proof_and_no_conflicting_final_claim_or_do_not_retain_both_accepts",
                                 "required_resolution_axis": "instance_correspondence",
                                 "resolution_scope_rule": "one_eligible_endpoint_exact_own_scope_with_all_listed_initial_targets_and_union_witness",
                                 "independent_observations_created": False})
    cluster_obligations = []
    for k in sorted(gate):
        if gate[k]["result"] != "abstain":
            continue
        own = scopes["candidate"][k]
        current = _assessment(candidate[k], "adjudicator_evidence", own)
        current["identity_status"] = candidate[k].get("identity_status")
        dimensions = []
        for label, assessed in [("candidate", current)] + [("verifier", x) for x in assessments[k]]:
            dimensions.append({"record_kind": label,
                               **{key: assessed[key] for key in ("verifier_id", "initial_target_cluster_id", "anonymous_proposal_ids") if key in assessed},
                               "existence": assessed["existence_judgment"],
                               "graph_worthiness": assessed["salience_judgment"],
                               "proposal_scope": assessed["proposal_scope_judgment"],
                               "positive_exact_scope_physical_cue_present": bool(assessed["exact_scope_physical_cue_records"]),
                               "positive_exact_scope_scope_cue_present": bool(assessed["exact_scope_positive_scope_cue_records"])})
        cluster_obligations.append({"cluster_id": k, "anonymous_proposal_ids": sorted(own),
                                    "initial_targets": [{"cluster_id": t, "anonymous_proposal_ids": sorted(scopes["initial"][t]),
                                                         "contributing_anonymous_proposal_ids": sorted(own & scopes["initial"][t])}
                                                        for t in sorted(targets[k])],
                                    "candidate_decision": "accept", "gate_result": "abstain",
                                    "candidate_assessment": current, "verifier_assessments": assessments[k],
                                    "separate_axis_facts": dimensions,
                                    "axis_obligations": [{"axis": axis, "gate_failure_reasons": sorted(reasons),
                                                          "anonymous_proposal_ids": sorted(own),
                                                          "initial_target_cluster_ids": sorted(targets[k]),
                                                          "requires_exact_scope_revision_resolution": any(
                                                              x.endswith(":missing_exact_scope_revision_resolution")
                                                              or x == "merged_initial_targets_lack_confirmed_same_scope_correspondence"
                                                              for x in reasons),
                                                          "revision_cannot_override": axis == "split_authorization"}
                                                         for axis, reasons in sorted(reason_axes[k].items()) if axis != "pair"],
                                    "pair_obligation_cluster_ids": [p["cluster_ids"] for p in pair_obligations if k in p["cluster_ids"]]})
    return {"policy_version": PHYSICAL_REVIEW_OBLIGATION_POLICY, "schema_version": PHYSICAL_VERSION,
            "gate_policy": GATE_POLICY, "distinct_revision_proof_policy": PAIR_POLICY,
            "review_instruction": REVIEW_INSTRUCTION, "has_obligations": bool(cluster_obligations),
            "cluster_obligations": cluster_obligations, "pair_obligations": pair_obligations,
            "pixel_truth_verified": False, "decisions_changed": False, "evidence_added_or_rebound": False}
