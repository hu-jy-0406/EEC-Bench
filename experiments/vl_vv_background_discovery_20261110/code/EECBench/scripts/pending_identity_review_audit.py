"""Read-only disposition audit for initial physical-identity review obligations.

This follows proposal scopes through the existing v0.6 gate. It neither gates
decisions nor validates pixel truth. In particular, a withdrawn raw same-scope
assertion is provenance, never evidence for rejecting either physical anchor.
"""

from __future__ import annotations

import copy
from collections import defaultdict
from typing import Any, Mapping, Sequence


AUDIT_VERSION = "pending_identity_dispositions_v0.2"
PHYSICAL_VERSION = "physical_identity_review_v0.6"
GATE_POLICY = "source_independent_exact_scope_physical_identity"
SAME_CUES = frozenset({"same_instance_continuity"})
DISTINCT_CUES = frozenset({"simultaneous_separation", "independent_interaction_or_trajectory"})
DISTINCT_REVISION_PROOF_POLICY = "undirected_exact_union_revision_distinct_v0.1"
PHYSICAL_CUES = frozenset({"physical_boundary", "direct_interaction", "temporal_continuity"})


def _scope(value: Any) -> frozenset[str] | None:
    if (not isinstance(value, (list, tuple)) or not value
            or any(not isinstance(x, str) or not x for x in value)
            or len(value) != len(set(value))):
        return None
    return frozenset(value)


def _rows(value: Any) -> list[Mapping[str, Any]]:
    return [x for x in value if isinstance(x, Mapping)] if isinstance(value, list) else []


def _unique(rows: Sequence[Mapping[str, Any]], key: str, value: str) -> Mapping[str, Any] | None:
    found = [row for row in rows if row.get(key) == value]
    return found[0] if len(found) == 1 else None


def _witness(evidence: Any, scope: frozenset[str], cues: frozenset[str] | None = None) -> bool:
    return any(_scope(row.get("anonymous_proposal_ids")) == scope
               and (cues is None or row.get("cue_type") in cues)
               and type(row.get("frame_id")) is int
               and all(isinstance(row.get(k), str) and row[k].strip()
                       for k in ("coarse_locator", "observation"))
               for row in _rows(evidence))


def _referenced(record: Mapping[str, Any], item: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    evidence, indices = record.get(key), item.get("evidence_indices")
    if (not isinstance(evidence, list) or not isinstance(indices, list) or not indices
            or any(type(i) is not int or i < 0 or i >= len(evidence) for i in indices)
            or len(indices) != len(set(indices))):
        return []
    return [evidence[i] for i in indices if isinstance(evidence[i], Mapping)]


def _comparison(record: Mapping[str, Any], partner: str, judgment: str,
                scope: frozenset[str], evidence_key: str) -> bool:
    item = _unique(_rows(record.get("identity_comparisons")), "other_cluster_id", partner)
    return bool(item and item.get("judgment") == judgment
                and item.get("scope_relation") == "comparable"
                and _witness(_referenced(record, item, evidence_key), scope,
                             SAME_CUES if judgment == "confirmed_same_scope" else DISTINCT_CUES))


def _pair_reviewed(record: Mapping[str, Any], partner: str, union: frozenset[str]) -> bool:
    """Coverage permits honest unresolved, but not absent/malformed pair reviews."""
    item = _unique(_rows(record.get("identity_comparisons")), "other_cluster_id", partner)
    if not item or item.get("scope_relation") not in {"comparable", "whole_part", "group_member", "unresolved"}:
        return False
    judgment = item.get("judgment")
    if judgment in {"confirmed_same_scope", "confirmed_distinct"}:
        return _comparison(record, partner, judgment, union, "evidence")
    indices, evidence = item.get("evidence_indices"), record.get("evidence")
    return (judgment == "unresolved" and isinstance(indices, list) and isinstance(evidence, list)
            and all(type(i) is int and 0 <= i < len(evidence) for i in indices)
            and len(indices) == len(set(indices)))


def _revision(record: Mapping[str, Any], targets: frozenset[str], own_scope: frozenset[str],
              pair_scope: frozenset[str], cues: frozenset[str], axis: str = "instance_correspondence") -> bool:
    matches = [row for row in _rows(record.get("revision_resolutions"))
               if row.get("axis") == axis
               and _scope(row.get("target_cluster_ids")) == targets
               and _scope(row.get("anonymous_proposal_ids")) == own_scope]
    return len(matches) == 1 and _witness(
        _referenced(record, matches[0], "adjudicator_evidence"), pair_scope, cues)


def _ledger_index(ledger: Mapping[str, Any], label: str) -> tuple[dict[str, Mapping[str, Any]], list[str]]:
    result: dict[str, Mapping[str, Any]] = {}
    seen: set[str] = set()
    errors = []
    rows = ledger.get("clusters")
    if not isinstance(rows, list) or len(_rows(rows)) != len(rows):
        return result, [f"{label}:invalid_cluster_array"]
    for row in rows:
        key, scope = row.get("cluster_id"), _scope(row.get("anonymous_proposal_ids"))
        if not isinstance(key, str) or not key or key in result or scope is None:
            errors.append(f"{label}:invalid_or_duplicate_cluster_scope")
            continue
        if seen & scope:
            errors.append(f"{label}:duplicate_proposal_ownership")
        seen.update(scope)
        result[key] = row
    return result, errors


def _undirected_revision_proof(
    proof: Any, final: Mapping[str, Mapping[str, Any]],
    final_scopes: Mapping[str, frozenset[str]], final_pair: frozenset[str],
    initial_pair: frozenset[str], union: frozenset[str],
) -> bool:
    """Recheck the original recorded witness without copying or rebinding it."""
    if not isinstance(proof, Mapping) or proof.get("policy") != DISTINCT_REVISION_PROOF_POLICY:
        return False
    source, other = proof.get("source_cluster_id"), proof.get("other_cluster_id")
    if (not isinstance(source, str) or not isinstance(other, str)
            or source == other or {source, other} != final_pair
            or source not in final or other not in final
            or _scope(proof.get("source_anonymous_proposal_ids")) != final_scopes[source]
            or _scope(proof.get("other_anonymous_proposal_ids")) != final_scopes[other]
            or _scope(proof.get("union_anonymous_proposal_ids")) != union
            or _scope(proof.get("initial_target_cluster_ids")) != initial_pair
            or any(proof.get(flag) is not False for flag in (
                "independent_observation", "evidence_copied_or_rebound", "reciprocal_comparison_created"))):
        return False
    record = final[source]
    if (not _comparison(record, other, "confirmed_distinct", union, "adjudicator_evidence")
            or not _revision(record, initial_pair, final_scopes[source], union, DISTINCT_CUES)):
        return False
    for key, index_key, indices_key, witness_key in (
        ("identity_comparisons", "comparison_index", "comparison_evidence_indices", "comparison_exact_union_witness_indices"),
        ("revision_resolutions", "resolution_index", "resolution_evidence_indices", "resolution_exact_union_witness_indices"),
    ):
        rows, index = record.get(key), proof.get(index_key)
        if (not isinstance(rows, list) or type(index) is not int or index < 0
                or index >= len(rows) or not isinstance(rows[index], Mapping)):
            return False
        item = rows[index]
        if key == "identity_comparisons":
            if item.get("other_cluster_id") != other:
                return False
        elif (item.get("axis") != "instance_correspondence"
              or _scope(item.get("target_cluster_ids")) != initial_pair
              or _scope(item.get("anonymous_proposal_ids")) != final_scopes[source]):
            return False
        indices = item.get("evidence_indices")
        for field in (indices_key, witness_key):
            recorded_indices = proof.get(field)
            if (not isinstance(recorded_indices, list) or not recorded_indices
                    or any(type(i) is not int or i < 0 for i in recorded_indices)
                    or len(recorded_indices) != len(set(recorded_indices))):
                return False
        if not _referenced(record, item, "adjudicator_evidence") or proof.get(indices_key) != indices:
            return False
        evidence = record["adjudicator_evidence"]
        exact = [i for i in indices if _witness([evidence[i]], union, DISTINCT_CUES)]
        if not exact or proof.get(witness_key) != exact:
            return False
    return True


def audit_pending_identity_dispositions(
    initial_decisions: Mapping[str, Any], final_decisions: Mapping[str, Any],
    pending_comparisons: Sequence[Mapping[str, Any]], physical_gate_audit: Mapping[str, Any],
    verifier_reports: Sequence[Mapping[str, Any]],
    verifier_ids: Sequence[str] = ("verifier_1", "verifier_2"),
) -> dict[str, Any]:
    """Audit pending initial pairs at the post-gate, pre-graph physical ledger.

    Inputs normally already passed the runner's schema/base/physical validators.
    Inconsistencies relevant to this audit produce an explicit unresolved risk,
    never repaired decisions. Revision-based contract resolution is distinguished
    from independent verifier agreement; neither certifies pixels. Rejected or
    abstained endpoints are deliberately not counted as successfully discovered.
    """
    roster = tuple(verifier_ids)
    if len(roster) != 2 or len(set(roster)) != 2 or any(not isinstance(v, str) or not v for v in roster):
        raise ValueError("Pending identity audit requires two distinct verifier IDs")
    result: dict[str, Any] = {
        "audit_version": AUDIT_VERSION, "stage": "post_physical_gate_pre_graph_partition",
        "no_pending": not pending_comparisons, "all_pending_pairs_contract_resolved": True,
        "unresolved_coverage_risk": False, "pixel_truth_verified": False,
        "decisions_modified": False, "required_verifier_ids": list(roster), "records": [],
    }
    if not pending_comparisons:
        return result
    initial, errors = _ledger_index(initial_decisions, "initial")
    final, final_errors = _ledger_index(final_decisions, "final")
    errors += final_errors
    if any(x.get("schema_version") != PHYSICAL_VERSION for x in (initial_decisions, final_decisions, physical_gate_audit)):
        errors.append("physical_schema_version_mismatch")
    if final_decisions.get("shot_id") != initial_decisions.get("shot_id"):
        errors.append("physical_ledger_shot_mismatch")
    if (physical_gate_audit.get("policy") != GATE_POLICY
            or physical_gate_audit.get("required_verifier_ids") != list(roster)):
        errors.append("physical_gate_policy_or_verifier_roster_mismatch")
    if physical_gate_audit.get("distinct_revision_proof_policy") not in (None, DISTINCT_REVISION_PROOF_POLICY):
        errors.append("unsupported_distinct_revision_proof_policy")
    initial_scopes = {key: _scope(row["anonymous_proposal_ids"]) for key, row in initial.items()}
    final_scopes = {key: _scope(row["anonymous_proposal_ids"]) for key, row in final.items()}
    if frozenset().union(*initial_scopes.values()) != frozenset().union(*final_scopes.values()):
        errors.append("physical_proposal_universe_changed")
    reports = {}
    for verifier in roster:
        report = _unique(_rows(list(verifier_reports)), "verifier_id", verifier)
        if report and report.get("schema_version") == PHYSICAL_VERSION:
            reports[verifier] = report
            if report.get("shot_id") != initial_decisions.get("shot_id"):
                errors.append("verifier_report_shot_mismatch")
    if any(row.get("verifier_id") not in roster for row in _rows(list(verifier_reports))):
        errors.append("unexpected_verifier_report")
    gate_rows = _rows(physical_gate_audit.get("records"))
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for index, row in enumerate(pending_comparisons):
        if (not isinstance(row, Mapping)
                or not all(isinstance(row.get(k), str) and row[k] for k in ("cluster_id_a", "cluster_id_b"))):
            grouped[(f"invalid_pending_row_{index}", "")].append(row if isinstance(row, Mapping) else {})
        else:
            grouped[tuple(sorted((row["cluster_id_a"], row["cluster_id_b"])))].append(row)

    for pair, sources in sorted(grouped.items()):
        a, b = pair
        reasons = list(errors)
        own_scopes = [initial_scopes.get(a), initial_scopes.get(b)]
        valid_pair = a != b and all(own_scopes)
        union = frozenset().union(*(scope or frozenset() for scope in own_scopes))
        if not valid_pair:
            reasons.append("pending_pair_missing_or_invalid_initial_scope")
        directions = []
        for row in sources:
            own, other = row.get("own_cluster_id"), row.get("other_cluster_id")
            valid_direction = all(isinstance(x, str) and x for x in (own, other))
            if valid_direction:
                directions.append((own, other))
            if (not valid_pair or not valid_direction or {own, other} != set(pair)
                    or _scope(row.get("own_anonymous_proposal_ids")) != initial_scopes.get(own)
                    or _scope(row.get("other_anonymous_proposal_ids")) != initial_scopes.get(other)
                    or _scope(row.get("union_anonymous_proposal_ids")) != union):
                reasons.append("pending_metadata_does_not_match_initial_exact_scopes")
        if len(set(directions)) != len(directions):
            reasons.append("duplicate_pending_direction")
        sides = []
        endpoint_reviews: dict[tuple[str, str], Mapping[str, Any]] = {}
        for target, scope in zip(pair, own_scopes):
            scope = scope or frozenset()
            destinations = []
            for key, final_scope in final_scopes.items():
                overlap = scope & final_scope
                if overlap:
                    destinations.append({"cluster_id": key, "anonymous_proposal_ids": sorted(final_scope),
                                         "initial_scope_overlap": sorted(overlap), "decision": final[key].get("decision"),
                                         "contains_complete_initial_scope": scope <= final_scope,
                                         "is_exact_initial_scope": scope == final_scope})
            coverage = []
            for verifier in roster:
                review = _unique(_rows(reports.get(verifier, {}).get("reviews")), "cluster_id", target)
                exact = bool(review and scope and _witness(review.get("evidence"), scope))
                other = b if target == a else a
                pair_reviewed = bool(review and _pair_reviewed(review, other, union))
                if review:
                    endpoint_reviews[verifier, target] = review
                coverage.append({"verifier_id": verifier, "initial_cluster_id": target,
                                 "anonymous_proposal_ids": sorted(scope), "record_present": review is not None,
                                 "exact_initial_scope_evidence_present": exact,
                                 "pending_pair_comparison_reviewed": pair_reviewed})
                if not review or not exact:
                    reasons.append(f"{target}:{verifier}:missing_or_partial_initial_scope_review")
                if not pair_reviewed:
                    reasons.append(f"{target}:{verifier}:missing_or_invalid_pending_pair_review")
            complete = (len(destinations) == 1 and destinations[0]["contains_complete_initial_scope"])
            if not complete:
                reasons.append(f"{target}:missing_split_or_partial_final_scope")
            if any(row["decision"] != "accept" for row in destinations):
                reasons.append(f"{target}:final_endpoint_rejected_or_abstained")
            sides.append({"initial_cluster_id": target, "anonymous_proposal_ids": sorted(scope),
                          "final_dispositions": destinations, "complete_single_destination": complete,
                          "verifier_coverage": coverage})
        record: dict[str, Any] = {
            "cluster_id_a": a, "cluster_id_b": b, "union_anonymous_proposal_ids": sorted(union),
            "pending_sources": copy.deepcopy(sources), "sides": sides,
            "gate_disposition": "not_demonstrated", "gate_records": [],
            "proof_basis": None, "independent_verifier_agreement": False, "pixel_truth_verified": False,
        }
        candidate_keys = [side["final_dispositions"][0]["cluster_id"] if side["complete_single_destination"] else None
                          for side in sides]
        gates = {}
        unary_revision_used = False
        if valid_pair and all(candidate_keys):
            for key in sorted(set(candidate_keys)):
                gate = _unique(gate_rows, "cluster_id", key)
                targets = frozenset(t for t, scope in initial_scopes.items() if scope & final_scopes[key])
                if (gate is None or _scope(gate.get("anonymous_proposal_ids")) != final_scopes[key]
                        or _scope(gate.get("initial_target_cluster_ids")) != targets
                        or gate.get("result") != "accept" or gate.get("failure_reasons") != []
                        or gate.get("exact_split_firewall_failed") is not False
                        or final[key].get("decision") != "accept"):
                    reasons.append(f"{key}:missing_or_inconsistent_accepted_gate_record")
                    continue
                gates[key] = gate
                record["gate_records"].append(copy.deepcopy(gate))
                used = gate.get("revision_resolutions_used", [])
                for axis, cues in (("physical_entity", PHYSICAL_CUES), ("proposal_scope", PHYSICAL_CUES | SAME_CUES)):
                    if axis in used:
                        unary_revision_used = True
                        if not _revision(final[key], targets, final_scopes[key], final_scopes[key], cues, axis):
                            reasons.append(f"{key}:{axis}:gate_revision_basis_not_demonstrated")
                for target in pair:
                    if target not in targets:
                        continue
                    for verifier in roster:
                        rows = [row for row in _rows(gate.get("verifier_judgments"))
                                if row.get("verifier_id") == verifier and row.get("target_cluster_id") == target]
                        if (len(rows) != 1 or rows[0].get("scope_kind") != "complete_initial_target"
                                or rows[0].get("record_present") is not True
                                or _scope(rows[0].get("anonymous_proposal_ids")) != initial_scopes[target]):
                            reasons.append(f"{target}:{verifier}:gate_complete_scope_coverage_not_demonstrated")
                            continue
                        review = endpoint_reviews.get((verifier, target), {})
                        physical = (review.get("existence_judgment") == "confirmed"
                                    and review.get("salience_judgment") == "graph_worthy"
                                    and _witness(review.get("evidence"), initial_scopes[target], PHYSICAL_CUES))
                        scoped = (review.get("proposal_scope_judgment") == "resolved_single_scope"
                                  and _witness(review.get("evidence"), initial_scopes[target], PHYSICAL_CUES | SAME_CUES))
                        for flag, confirmed, axis in (("physical_confirmed", physical, "physical_entity"),
                                                     ("proposal_scope_confirmed", scoped, "proposal_scope")):
                            if rows[0].get(flag) is not confirmed:
                                reasons.append(f"{target}:{verifier}:{flag}:gate_and_review_disagree")
                            if not confirmed and axis not in used:
                                reasons.append(f"{key}:{axis}:missing_gate_revision_for_disputed_axis")
            left, right = candidate_keys
            same = left == right
            exact_mapping = (final_scopes[left] == union if same else
                             final_scopes[left] == own_scopes[0] and final_scopes[right] == own_scopes[1])
            if not exact_mapping:
                reasons.append("final_mapping_expands_beyond_the_exact_pending_pair_scopes")
            elif all(key in gates for key in candidate_keys):
                judgment = "confirmed_same_scope" if same else "confirmed_distinct"
                agreement = all(_comparison(endpoint_reviews.get((v, x), {}), y, judgment, union, "evidence")
                                for v in roster for x, y in ((a, b), (b, a)))
                record["independent_verifier_agreement"] = agreement
                if same:
                    record["gate_disposition"] = "exact_merged_alias"
                    used = gates[left].get("revision_resolutions_used", [])
                    revised = ("instance_correspondence:merged_initial_targets" in used
                               and _revision(final[left], frozenset(pair), union, union, SAME_CUES))
                    if revised:
                        record["proof_basis"] = "adjudicator_revision"
                        record["independent_verifier_agreement"] = False
                    elif agreement and "instance_correspondence:merged_initial_targets" not in used:
                        record["proof_basis"] = "independent_verifier_agreement"
                    else:
                        reasons.append("merged_alias_gate_basis_not_demonstrated")
                else:
                    record["gate_disposition"] = "exact_separate_pair"
                    bases = []
                    for key, other in ((left, right), (right, left)):
                        item = _unique(_rows(gates[key].get("identity_pair_judgments")), "other_cluster_id", other)
                        if (not item or item.get("final_pair_unresolved_or_same_scope") is not False
                                or item.get("final_pair_scope_relation_conflict", False) is not False):
                            reasons.append(f"{key}:{other}:missing_or_unresolved_gate_pair_disposition")
                            continue
                        record.setdefault("gate_pair_dispositions", []).append(copy.deepcopy(dict(item, cluster_id=key)))
                        final_rows = [row for x, y in ((key, other), (other, key))
                                      for row in _rows(final[x].get("identity_comparisons"))
                                      if row.get("other_cluster_id") == y]
                        if any(row.get("scope_relation") not in {"whole_part", "group_member"}
                               and row.get("judgment") != "confirmed_distinct" for row in final_rows):
                            reasons.append("gate_pair_disposition_conflicts_with_final_comparison")
                        final_comparable_declared = any(
                            row.get("scope_relation") not in {"whole_part", "group_member"}
                            for row in final_rows)
                        if final_comparable_declared and any(
                                row.get("scope_relation") != "comparable" for row in final_rows):
                            reasons.append("gate_pair_disposition_conflicts_with_final_scope_relation")
                        if physical_gate_audit.get("distinct_revision_proof_policy") == DISTINCT_REVISION_PROOF_POLICY:
                            original_revision_proven = (
                                item.get("revision_distinct_proof_used") is True
                                and all(row.get("scope_relation") == "comparable" for row in final_rows)
                                and _undirected_revision_proof(
                                    item.get("revision_distinct_proof"), final, final_scopes,
                                    frozenset((key, other)), frozenset(pair), union))
                        else:
                            original_revision_proven = (
                                _comparison(final[key], other, "confirmed_distinct", union, "adjudicator_evidence")
                                and _revision(final[key], frozenset(pair), final_scopes[key], union, DISTINCT_CUES))
                        revised = (item.get("revision_confirms_distinct") is True
                                   and f"instance_correspondence:distinct_from:{other}" in gates[key].get("revision_resolutions_used", [])
                                   and original_revision_proven)
                        if item.get("verifiers_confirm_distinct") is True and agreement:
                            bases.append("independent_verifier_agreement")
                        elif revised:
                            bases.append("adjudicator_revision")
                        else:
                            reasons.append(f"{key}:{other}:distinct_pair_gate_basis_not_demonstrated")
                    if len(bases) == 2:
                        record["proof_basis"] = ("adjudicator_revision" if "adjudicator_revision" in bases
                                                 else "independent_verifier_agreement")
                        if record["proof_basis"] == "adjudicator_revision":
                            record["independent_verifier_agreement"] = False
        if record["proof_basis"] and unary_revision_used:
            record["proof_basis"] = "adjudicator_revision"
            record["independent_verifier_agreement"] = False
        if not record["proof_basis"]:
            reasons.append("exact_final_pair_disposition_not_proven_by_existing_gate")
        record["reasons"] = sorted(set(reasons))
        record["reason"] = "; ".join(record["reasons"]) or "existing_exact_scope_contract_satisfied"
        record["contract_resolved"] = not reasons
        record["unresolved_coverage_risk"] = bool(reasons)
        record["disposition"] = "unresolved_coverage_risk" if reasons else "contract_resolved"
        result["records"].append(record)
    result["all_pending_pairs_contract_resolved"] = all(row["contract_resolved"] for row in result["records"])
    result["unresolved_coverage_risk"] = not result["all_pending_pairs_contract_resolved"]
    return result
