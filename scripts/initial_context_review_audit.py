"""Independent audits of initial context quarantine and subsequent scope review.

The projection audit reconstructs the transformation from raw records. It never
calls the projector or the pending preparer. The unchanged physical validator is
used only after an independently computed, temporary pending shadow. The second
audit records coverage and proposal destinations; neither audit supplies a visual
judgment, changes a ledger, or treats coverage as pixel truth.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import jsonschema

import physical_identity_review as physical
import scope_retention_transport as retention_transport


PROJECTION_AUDIT_VERSION = "independent_initial_context_projection_audit_v0.2"
DISPOSITION_AUDIT_VERSION = "initial_context_review_dispositions_v0.1"
QUARANTINE_POLICY = "initial_context_quarantine_v0.2"
PENDING_POLICY = "initial_identity_pending_v0.2"
PROJECTION_CONTRACTS = {
    ("initial_context_quarantine_v0.1", "initial_identity_pending_v0.1"):
        ("independent_initial_context_projection_audit_v0.1", False),
    (QUARANTINE_POLICY, PENDING_POLICY): (PROJECTION_AUDIT_VERSION, True),
}
CONTEXT_RELATIONS = frozenset({"whole_part", "group_member"})
IDENTITY_CUES = {
    "confirmed_same_scope": frozenset({"same_instance_continuity"}),
    "confirmed_distinct": frozenset({"simultaneous_separation", "independent_interaction_or_trajectory"}),
}


class InitialContextAuditError(ValueError):
    """The supplied projection, provenance, or raw structure is inconsistent."""


def _require(condition, message):
    if not condition:
        raise InitialContextAuditError(message)


def _projection_contract(audit):
    """Select exact historical rules, never infer them from current runtime."""
    _require(type(audit) is dict, "Invalid quarantine audit")
    versions = (audit.get("policy_version"), audit.get("shadow_validation_policy"))
    _require(all(type(v) is str for v in versions) and versions in PROJECTION_CONTRACTS,
             "Unsupported or mixed initial context/pending policy versions")
    audit_version, allow_empty_confirmed = PROJECTION_CONTRACTS[versions]
    return versions, audit_version, allow_empty_confirmed


def _canonical(value):
    def check(item):
        if type(item) is dict:
            _require(all(type(k) is str for k in item), "JSON object keys must be strings")
            for child in item.values():
                check(child)
        elif type(item) is list:
            for child in item:
                check(child)
        else:
            _require(item is None or type(item) in (str, int, float, bool), "Non-JSON input value")
    check(value)
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise InitialContextAuditError("Nonfinite or invalid JSON value") from exc


def _hash(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _ids(value, label, *, allow_empty=False):
    _require(type(value) is list and (bool(value) or allow_empty)
             and all(type(x) is str and bool(x) for x in value)
             and len(value) == len(set(value)), label + ": invalid/duplicate IDs")
    return frozenset(value)


def _rows(value, label):
    _require(type(value) is list and all(type(x) is dict for x in value), label + ": invalid records")
    return value


def _index(ledger, label):
    _require(type(ledger) is dict and ledger.get("schema_version") == physical.SCHEMA_VERSION,
             label + ": physical schema mismatch")
    _require(type(ledger.get("shot_id")) is str and bool(ledger["shot_id"]), label + ": invalid shot")
    clusters, scopes, owners = {}, {}, {}
    for row in _rows(ledger.get("clusters"), label):
        key = row.get("cluster_id")
        _require(type(key) is str and bool(key) and key not in clusters, label + ": duplicate/invalid cluster")
        scope = _ids(row.get("anonymous_proposal_ids"), label + " scope")
        _require(not (scope & owners.keys()), label + ": duplicate proposal ownership")
        _require(row.get("decision") in {"accept", "reject", "abstain"}, label + ": invalid decision")
        clusters[key], scopes[key] = row, scope
        owners.update({p: key for p in scope})
    return clusters, scopes, owners


def _schema_validate(value, role="adjudication"):
    # This is the immutable model schema, not a projector-provided validator.
    path = Path(__file__).resolve().parents[1] / f"schemas/codex_entity_{role}_v0.6.schema.json"
    schema = json.loads(path.read_text())
    try:
        jsonschema.Draft202012Validator(schema).validate(value)
    except jsonschema.ValidationError as exc:
        raise InitialContextAuditError(role + " schema: " + exc.message) from exc


def _indices(value, length, label, *, nonempty=False):
    _require(type(value) is list and (bool(value) or not nonempty)
             and all(type(i) is int and 0 <= i < length for i in value)
             and len(value) == len(set(value)), label + ": invalid evidence indices")
    return value


def _observation(row, universe, frames):
    _require(type(row) is dict, "Invalid observation")
    scope = _ids(row.get("anonymous_proposal_ids"), "Observation scope")
    _require(scope <= universe, "Observation names unknown proposals")
    _require(type(row.get("frame_id")) is int and row["frame_id"] in frames, "Invalid observation frame")
    _require(row.get("cue_type") in physical.CUE_TYPES, "Invalid observation cue")
    _require(row.get("support_quality") in {"strong", "moderate", "weak"}, "Invalid observation support")
    for key in ("coarse_locator", "observation"):
        _require(type(row.get(key)) is str and bool(row[key].strip()), "Empty observation " + key)
    return scope


def _context_owners(observation_scope, owner, scopes, proposal_owners):
    touched = sorted({proposal_owners[p] for p in observation_scope})
    if len(touched) < 3:
        return None
    _require(scopes[owner] <= observation_scope, "Wide context omits complete owner scope")
    _require(all(scopes[k] <= observation_scope for k in touched), "Wide context contains a partial original scope")
    return touched


def audit_initial_context_projection(raw_decisions, projected_decisions, quarantine_audit,
                                     *, valid_frame_ids, expected_proposal_ids):
    """Raise on missing/extra quarantine, unsafe deletion, stale hash or mutation.

    The projected input is specifically pre-pending. The selected v0.1/v0.2
    policy's pending comparisons must still have their original judgments here.
    """
    _canonical(raw_decisions)
    _canonical(projected_decisions)
    _canonical(quarantine_audit)
    versions, audit_version, allow_empty_confirmed = _projection_contract(quarantine_audit)
    _schema_validate(raw_decisions)
    _schema_validate(projected_decisions)
    _require(type(valid_frame_ids) in (list, tuple) and bool(valid_frame_ids)
             and all(type(x) is int and x >= 0 for x in valid_frame_ids)
             and len(valid_frame_ids) == len(set(valid_frame_ids)), "Invalid supplied frame IDs")
    expected_ids = _ids(list(expected_proposal_ids), "Expected proposal universe", allow_empty=True)
    clusters, scopes, owners = _index(raw_decisions, "raw")
    _require(set(owners) == expected_ids, "Raw proposal universe mismatch")
    from ensemble_shot_entity_detection import validate_decisions
    for ledger in (raw_decisions, projected_decisions):
        try:
            validate_decisions(ledger, shot_id=raw_decisions["shot_id"],
                               anonymous_ids=list(expected_ids), valid_frame_ids=valid_frame_ids)
        except Exception as exc:
            raise InitialContextAuditError("Base adjudication: " + str(exc)) from exc
    frames = set(valid_frame_ids)
    all_contexts, maps = [], {}
    # Validate and classify every raw record before constructing any projection.
    for position, row in enumerate(raw_decisions["clusters"]):
        owner = row["cluster_id"]
        evidence = _rows(row.get("adjudicator_evidence"), "Raw evidence")
        comparisons = _rows(row.get("identity_comparisons"), "Raw comparisons")
        _require(row.get("revision_resolutions") == [], "Initial revision resolutions are forbidden")
        presence = _rows(row.get("frame_presence"), "Raw presence")
        presence_ids = [x.get("frame_id") for x in presence]
        _require(all(type(x) is int for x in presence_ids) and len(presence_ids) == len(set(presence_ids))
                 and set(presence_ids) == frames, "Initial presence must cover every supplied frame once")
        partners = set()
        for ci, comparison in enumerate(comparisons):
            other = comparison.get("other_cluster_id")
            _require(type(other) is str and other in clusters and other != owner and other not in partners,
                     "Invalid/self/duplicate comparison partner")
            partners.add(other)
            judgment, relation = comparison.get("judgment"), comparison.get("scope_relation")
            _require(judgment in physical.IDENTITY_JUDGMENTS and relation in physical.SCOPE_RELATIONS,
                     "Invalid comparison enums")
            _indices(comparison.get("evidence_indices"), len(evidence), "Raw comparison",
                     nonempty=judgment != "unresolved" and not allow_empty_confirmed)
            _require(judgment == "unresolved" or relation == "comparable", "Confirmed non-comparable relation")
        removed = set()
        for ei, item in enumerate(evidence):
            scope = _observation(item, expected_ids, frames)
            touched = _context_owners(scope, owner, scopes, owners)
            if touched is None:
                continue
            refs = []
            for ci, comparison in enumerate(comparisons):
                if ei not in comparison["evidence_indices"]:
                    continue
                _require(comparison["judgment"] == "unresolved" and comparison["scope_relation"] in CONTEXT_RELATIONS,
                         "Wide context has a prohibited positive/comparable/unresolved reference")
                refs.append({"comparison_index": ci,
                             "json_pointer": f"/clusters/{position}/identity_comparisons/{ci}/evidence_indices",
                             **{k: copy.deepcopy(comparison[k]) for k in ("other_cluster_id", "judgment", "scope_relation")},
                             "original_evidence_indices": list(comparison["evidence_indices"])})
            removed.add(ei)
            all_contexts.append({"owner_cluster_id": owner, "original_evidence_index": ei,
                                 "original_json_pointer": f"/clusters/{position}/adjudicator_evidence/{ei}",
                                 "observation": copy.deepcopy(item), "observation_sha256": _hash(item),
                                 "scope_owner_ids": touched, "references": refs})
        next_index, mapping = 0, []
        for ei in range(len(evidence)):
            mapping.append(None if ei in removed else next_index)
            if ei not in removed:
                next_index += 1
        maps[owner] = mapping
    expected = copy.deepcopy(raw_decisions)
    for row in expected["clusters"]:
        mapping = maps[row["cluster_id"]]
        row["adjudicator_evidence"] = [item for i, item in enumerate(row["adjudicator_evidence"]) if mapping[i] is not None]
        for comparison in row["identity_comparisons"]:
            comparison["evidence_indices"] = [mapping[i] for i in comparison["evidence_indices"] if mapping[i] is not None]
    for item in all_contexts:
        mapping = maps[item["owner_cluster_id"]]
        for ref in item["references"]:
            ref["projected_evidence_indices"] = [mapping[i] for i in ref["original_evidence_indices"] if mapping[i] is not None]
    _require(_canonical(projected_decisions) == _canonical(expected),
             "Projected ledger differs from the complete independently reconstructed projection")
    # Independently derive the selected policy's unsupported-confirmation shadow.
    # An empty v0.2 reference is missing proof, never a reference to a partner's
    # witness; v0.1 rejected it above. The pre-pending projection stays unchanged.
    shadow, pending_count = copy.deepcopy(expected), 0
    for row in shadow["clusters"]:
        for comparison in row["identity_comparisons"]:
            if comparison["judgment"] == "unresolved":
                continue
            union = scopes[row["cluster_id"]] | scopes[comparison["other_cluster_id"]]
            cues = IDENTITY_CUES[comparison["judgment"]]
            supported = any(set(row["adjudicator_evidence"][i]["anonymous_proposal_ids"]) == union
                            and row["adjudicator_evidence"][i]["cue_type"] in cues
                            for i in comparison["evidence_indices"])
            if not supported:
                comparison["judgment"] = "unresolved"
                pending_count += 1
    try:
        physical.validate_adjudication_identity_fields(shadow, valid_frame_ids=valid_frame_ids,
                                                       expected_proposal_ids=list(expected_ids))
    except ValueError as exc:
        raise InitialContextAuditError("Strict independent shadow validation: " + str(exc)) from exc
    review_ids = sorted({k for item in all_contexts for k in item["scope_owner_ids"]})
    expected_audit = {
        "policy_version": versions[0], "stage": "initial_adjudication",
        "raw_sha256": _hash(raw_decisions), "projected_sha256": _hash(expected), "visual_correction": False,
        "quarantined_evidence": all_contexts, "evidence_index_maps": maps, "review_scope_ids": review_ids,
        "shadow_pending_comparison_count": pending_count, "shadow_validation_policy": versions[1],
        "strict_shadow_validation_passed": True, "requires_pending_preparation_before_use": True,
    }
    _require(_canonical(quarantine_audit) == _canonical(expected_audit),
             "Quarantine audit differs from independently recomputed records, maps, references or hashes")
    return {"audit_version": audit_version, "projection_contract_valid": True,
            "raw_sha256": _hash(raw_decisions), "projected_sha256": _hash(expected),
            "quarantine_audit_sha256": _hash(quarantine_audit), "quarantined_evidence_count": len(all_contexts),
            "review_scope_ids": review_ids, "shadow_pending_comparison_count": pending_count,
            "projector_or_pending_preparer_called": False, "decisions_modified": False, "pixel_truth_verified": False}


def _original_scope_review_coverage(report, verifier_id, key, scope, universe, frames):
    """One original-scope observation is coverage, including honest uncertainty."""
    rows = report.get("reviews", [])
    candidates = [row for row in rows if type(row) is dict and row.get("cluster_id") == key] if type(rows) is list else []
    review = candidates[0] if len(candidates) == 1 else None
    exact_indices, invalid = [], False
    if review is not None:
        for i, evidence in enumerate(review.get("evidence", []) if type(review.get("evidence")) is list else []):
            try:
                if _observation(evidence, universe, frames) == scope:
                    exact_indices.append(i)
            except InitialContextAuditError:
                invalid = True
    return {"verifier_id": verifier_id, "review_count": len(candidates),
            "complete_original_scope_review": review is not None and bool(exact_indices) and not invalid,
            "exact_scope_evidence_indices": exact_indices,
            "judgments": {field: review.get(field) for field in (
                "existence_judgment", "salience_judgment", "proposal_scope_judgment", "category_resolution"
            )} if review is not None else None}


def _context_verifier_projection(report, initial_decisions, policy, eligible_parent_ids):
    """Select raw schema explicitly; retain a separate core projection binding."""
    frames = sorted({row["frame_id"] for cluster in initial_decisions["clusters"]
                     for row in cluster.get("frame_presence", [])
                     if type(row) is dict and type(row.get("frame_id")) is int})
    try:
        core = retention_transport.validate_and_project_verifier(
            report, policy=policy, initial_decisions=initial_decisions,
            valid_frame_ids=frames, eligible_parent_ids=eligible_parent_ids)
        audit = None if policy == retention_transport.DISABLED else retention_transport.build_projection_audit(
            report, core, policy=policy)
    except ValueError as exc:
        raise InitialContextAuditError(str(exc)) from exc
    return core, audit


def validate_context_verifier_coverage(report, *, initial_decisions, required_scope_ids, verifier_id,
                                       scope_retention_policy="disabled", eligible_parent_ids=None):
    """Apply the existing final coverage requirement before revision is called.

    The caller has authenticated the quarantine sidecar and validated the full
    report's schema, targets and physical fields. Only its forced original scopes
    need an exact-own observation; unrelated targets gain no new obligation.
    This does not require a positive cue, certainty, agreement or an accepted
    decision. It neither changes nor manufactures observations. Enabled retention
    raw reports must pass their full extended schema before core projection;
    subset evidence never replaces an original-scope coverage observation.
    """
    _canonical(report)
    initial, scopes, owners = _index(initial_decisions, "initial")
    report, _ = _context_verifier_projection(
        report, initial_decisions, scope_retention_policy, eligible_parent_ids)
    required = _ids(required_scope_ids, "Required context review scopes", allow_empty=True)
    _require(required <= initial.keys(), "Unknown required context review scope")
    _require(type(report) is dict and report.get("verifier_id") == verifier_id
             and report.get("schema_version") == physical.SCHEMA_VERSION
             and report.get("shot_id") == initial_decisions["shot_id"], "Verifier identity/schema/shot mismatch")
    rows = _rows(report.get("reviews"), "Verifier reviews")
    keys = [row.get("cluster_id") for row in rows]
    _require(all(type(key) is str and key in initial for key in keys)
             and len(keys) == len(set(keys)), "Unknown or duplicate original-scope review")
    coverage, missing = [], []
    for key in sorted(required):
        frames = {row["frame_id"] for row in initial[key].get("frame_presence", [])
                  if type(row) is dict and type(row.get("frame_id")) is int}
        row = _original_scope_review_coverage(report, verifier_id, key, scopes[key], frozenset(owners), frames)
        coverage.append(row)
        if not row["complete_original_scope_review"]:
            missing.append({"cluster_id": key, "anonymous_proposal_ids": sorted(scopes[key])})
    _require(not missing, "Missing complete original-scope observations: " + _canonical(missing)
             + ". Include at least one valid evidence observation for each listed exact original scope. "
             "An unresolved cue and uncertain judgments are allowed. Pair-union observations do not "
             "replace this scope review; do not relabel their proposal IDs or invent certainty.")
    return coverage


def audit_context_review_dispositions(initial_decisions, final_decisions, quarantine_audit, verifier_reports,
                                      verifier_ids=("verifier_1", "verifier_2"), *,
                                      scope_retention_policy="disabled", eligible_parent_ids=None):
    """Report two-role exact original-scope coverage and every final destination.

    Caller first authenticates the sidecar with audit_initial_context_projection.
    Here initial_decisions may be pre- or post-pending, whose ownership is equal.
    Coverage accepts a concrete unresolved observation. Neither positive verdicts
    nor agreement are required. Missing/partial/duplicate reviews invalidate the
    review contract; rejection, abstention and changed scope retain coverage risk.
    """
    _require(type(verifier_ids) in (list, tuple) and len(verifier_ids) == 2
             and all(type(v) is str and bool(v) for v in verifier_ids)
             and len(set(verifier_ids)) == 2, "Exactly two distinct verifier IDs are required")
    result = {"audit_version": DISPOSITION_AUDIT_VERSION, "stage": "post_physical_gate_pre_graph_partition",
              "required_verifier_ids": list(verifier_ids), "no_context_review_required": False,
              "all_required_scopes_reviewed": False, "unresolved_coverage_risk": True,
              "records": [], "errors": [], "decisions_modified": False, "pixel_truth_verified": False}
    try:
        _require(type(scope_retention_policy) is str
                 and scope_retention_policy in (retention_transport.DISABLED, retention_transport.POLICY_VERSION),
                 "Unknown scope retention policy")
        if scope_retention_policy != retention_transport.DISABLED:
            result.update(scope_retention_policy=scope_retention_policy, verifier_projections=[])
        for value in (initial_decisions, final_decisions, quarantine_audit, list(verifier_reports)):
            _canonical(value)
        initial, scopes, owners = _index(initial_decisions, "initial")
        final, final_scopes, final_owners = _index(final_decisions, "final")
        _require(initial_decisions["shot_id"] == final_decisions["shot_id"], "Final ledger shot mismatch")
        _require(set(owners) == set(final_owners), "Final proposal universe changed")
        _projection_contract(quarantine_audit)
        _require(quarantine_audit.get("stage") == "initial_adjudication"
                 and quarantine_audit.get("visual_correction") is False, "Invalid quarantine provenance policy")
        contexts = _rows(quarantine_audit.get("quarantined_evidence"), "Quarantined evidence")
        forced, context_keys = set(), set()
        for item in contexts:
            owner, ei = item.get("owner_cluster_id"), item.get("original_evidence_index")
            _require(type(owner) is str and owner in initial and type(ei) is int and ei >= 0
                     and (owner, ei) not in context_keys, "Invalid/duplicate quarantined observation source")
            context_keys.add((owner, ei))
            observation = item.get("observation")
            _require(type(observation) is dict and _hash(observation) == item.get("observation_sha256"), "Context observation hash mismatch")
            scope = _ids(observation.get("anonymous_proposal_ids"), "Context observation scope")
            _require(scope <= owners.keys(), "Context contains unknown proposals")
            touched = _context_owners(scope, owner, scopes, owners)
            _require(touched is not None and item.get("scope_owner_ids") == touched, "Context owners do not match full initial scopes")
            forced.update(touched)
        _require(quarantine_audit.get("review_scope_ids") == sorted(forced), "Forced review scope set is incomplete or stale")
    except (InitialContextAuditError, TypeError, KeyError, AttributeError) as exc:
        result["errors"].append(str(exc))
        return result
    result["no_context_review_required"] = not forced
    result["initial_scope_map"] = {k: sorted(scopes[k]) for k in sorted(forced)}
    result["complete_proposal_universe_preserved"] = True
    # Even when no context scopes are forced, a supplied extended report cannot
    # bypass explicit policy/schema selection via the historical early return.
    projected_reports = []
    try:
        for report in _rows(list(verifier_reports), "Verifier reports"):
            core, projection = _context_verifier_projection(
                report, initial_decisions, scope_retention_policy, eligible_parent_ids)
            projected_reports.append(core)
            if projection is not None:
                result["verifier_projections"].append({"verifier_id": report["verifier_id"], **projection})
    except (ValueError, TypeError) as exc:
        result["errors"].append(str(exc))
        return result
    if not forced:
        result.update(all_required_scopes_reviewed=True, unresolved_coverage_risk=False)
        return result
    reports = {}
    report_errors = []
    try:
        rows = projected_reports
        for report in rows:
            _schema_validate(report, "verification")
            vid = report.get("verifier_id")
            _require(type(vid) is str and vid in verifier_ids and vid not in reports, "Duplicate or unexpected verifier ID")
            _require(report.get("schema_version") == physical.SCHEMA_VERSION
                     and report.get("shot_id") == initial_decisions["shot_id"], "Verifier schema/shot mismatch")
            seen_reviews = set()
            for review in report["reviews"]:
                key = review["cluster_id"]
                _require(key in initial and key not in seen_reviews, "Unknown or duplicate original-scope review")
                seen_reviews.add(key)
            physical.validate_verifier_identity_fields(
                report, target_proposal_ids_by_cluster={k: sorted(scopes[k]) for k in seen_reviews},
                identity_challenge_pairs=[],
                valid_frame_ids=sorted({row["frame_id"] for c in initial.values()
                                        for row in c.get("frame_presence", [])
                                        if type(row) is dict and type(row.get("frame_id")) is int}),
                all_cluster_ids=list(initial))
            reports[vid] = report
        _require(set(reports) == set(verifier_ids), "Missing required verifier report")
    except (ValueError, TypeError) as exc:
        report_errors.append(str(exc))
    for key in sorted(forced):
        scope = scopes[key]
        reviews, reasons = [], list(report_errors)
        frame_rows = initial[key].get("frame_presence", [])
        frames = {row["frame_id"] for row in frame_rows if type(row) is dict and type(row.get("frame_id")) is int}
        for vid in verifier_ids:
            report = reports.get(vid, {})
            coverage = _original_scope_review_coverage(report, vid, key, scope, frozenset(owners), frames)
            if not coverage["complete_original_scope_review"]:
                reasons.append(f"{vid}:{key}:missing_duplicate_invalid_or_partial_original_scope_review")
            reviews.append(coverage)
        destinations = []
        disposition_risks = []
        for target, target_scope in final_scopes.items():
            overlap = scope & target_scope
            if not overlap:
                continue
            decision = final[target]["decision"]
            destinations.append({"cluster_id": target, "anonymous_proposal_ids": sorted(target_scope),
                                 "original_scope_overlap": sorted(overlap), "decision": decision,
                                 "contains_complete_original_scope": scope <= target_scope,
                                 "is_exact_original_scope": scope == target_scope})
            if decision != "accept":
                disposition_risks.append(f"{target}:final_{decision}")
            if scope != target_scope:
                disposition_risks.append(f"{target}:final_scope_changed")
        covered = not reasons and all(row["complete_original_scope_review"] for row in reviews)
        result["records"].append({"initial_cluster_id": key, "anonymous_proposal_ids": sorted(scope),
                                  "initial_decision": initial[key]["decision"], "verifier_coverage": reviews,
                                  "complete_two_verifier_coverage": covered, "final_dispositions": destinations,
                                  "all_proposals_accounted_for": set().union(*(set(d["original_scope_overlap"]) for d in destinations)) == scope,
                                  "unresolved_coverage_risk": bool(reasons or disposition_risks),
                                  "reasons": reasons + disposition_risks, "pixel_truth_verified": False})
        result["errors"].extend(reasons)
    result["errors"] = sorted(set(result["errors"]))
    result["all_required_scopes_reviewed"] = not result["errors"] and all(x["complete_two_verifier_coverage"] for x in result["records"])
    result["unresolved_coverage_risk"] = bool(result["errors"] or any(x["unresolved_coverage_risk"] for x in result["records"]))
    return result
