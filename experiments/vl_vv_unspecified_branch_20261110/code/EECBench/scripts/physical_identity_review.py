"""Source-blind physical identity contract, independent of the ensemble runner.

These checks validate typed, exact-scope claims, not their visual truth. Pixel
accuracy still needs independent review. No name, source count, confidence grade,
or free-text uncertainty flag is a gate input. Extension validators follow the
base v0.5 validators; honest unresolved judgments are valid output.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "physical_identity_review_v0.6"
INITIAL_PREPARATION_VERSION = "initial_identity_pending_v0.2"
DISTINCT_REVISION_PROOF_POLICY = "undirected_exact_union_revision_distinct_v0.1"
BASE_PROTOCOL_VERSION = "single_shot_inventory_first_boxed_granularity_v0.5"
VERIFIER_POLICY_RELATIVE_PATH = "references/verifier-protocol.md"
PROPOSAL_SCOPE_JUDGMENTS = ("resolved_single_scope", "mixed_scope", "unresolved")
CATEGORY_RESOLUTIONS = ("resolved", "subtype_unresolved", "category_unresolved")
IDENTITY_JUDGMENTS = ("confirmed_same_scope", "confirmed_distinct", "unresolved")
SCOPE_RELATIONS = ("comparable", "whole_part", "group_member", "unresolved")
CUE_TYPES = (
    "physical_boundary", "direct_interaction", "temporal_continuity",
    "same_instance_continuity", "simultaneous_separation", "independent_interaction_or_trajectory", "integrated_component",
    "non_entity", "unresolved", "category_only",
)
PHYSICAL_CUES = frozenset(("physical_boundary", "direct_interaction", "temporal_continuity"))
SAME_CUES = frozenset(("same_instance_continuity",))
DISTINCT_CUES = frozenset(("simultaneous_separation", "independent_interaction_or_trajectory"))
RESOLUTION_AXES = ("physical_entity", "proposal_scope", "instance_correspondence")

PHYSICAL_IDENTITY_RULE = """Judge three independent axes at the claimed physical scope:
1. Physical entity: existence and a graph-worthy independently bounded unit or
   directly observed independent use, handling, or motion.
2. Proposal scope and instance correspondence: which proposals describe the same
   complete physical content, and whether another claim is the same or distinct.
3. Category resolution: known category, unknown subtype, or unknown category.
A visible independently bounded or independently used object can be confirmed
while its subtype or category remains unknown. Use a truthful broad name then.
A more specific name, repeated proposals, detector support, confidence language,
or support_quality never supplies missing physical or correspondence evidence.
Identity between comparable scopes is confirmed_same_scope, confirmed_distinct,
or unresolved. Failure to observe two separate objects does not prove one object;
failure to prove an alias does not prove distinctness. Whole-part and group-member
relations are not same-scope aliases. Keep physical existence separate from later
graph grouping. Unresolved judgments are normal valid answers, not format errors.
Determine scope_relation from the complete physical content asserted by each
scope. Image-plane enclosure, support, or proximity alone establishes neither
whole_part nor group_member. A fixture-only claim excludes stored or supported
contents; a contents-only claim excludes the fixture. Here 'only' describes the
asserted content, not a category-name shortcut: it neither removes integral
components nor rewrites an explicit assembly claim. whole_part requires a claimed
whole and its actual constituent; group_member requires a claimed group containing
that member. Independently bounded objects can have comparable scopes while one
encloses or supports the other. Comparable scope does not prove distinctness;
retain the exact-union boundary, interaction, or continuity evidence requirements.
If the scope relation itself is uncertain, use scope_relation=unresolved. A known
non-comparable relation still uses judgment=unresolved. Do not choose a relation
enum to evade unresolved identity. Later graph composition is a separate decision.
Every evidence item binds explicit anonymous_proposal_ids, a valid original frame,
a concrete locator, cue_type, and observation of the actual boundary, interaction,
continuity, or separation. A confidence adjective is not an observation. An item
about a parent, a different track, or a union cannot confirm an exact child scope.
Typed evidence is an auditable assertion; it is not automatic proof of pixel truth.
"""

ADJUDICATION_FIELDS_INSTRUCTION = """
Use schema_version=physical_identity_review_v0.6 and retain the supplied base
protocol_version. On every cluster add existence_judgment (confirmed/rejected/
uncertain), salience_judgment (graph_worthy/background_integrated/ambiguous),
proposal_scope_judgment (resolved_single_scope/mixed_scope/unresolved), and
category_resolution (resolved/subtype_unresolved/category_unresolved).
identity_status=resolved means the physical content and proposal correspondence
are resolved; it does not assert a known subtype. Evidence in adjudicator_evidence
adds anonymous_proposal_ids, cue_type, and observation. cue_type is one of:
physical_boundary, direct_interaction, temporal_continuity,
same_instance_continuity, simultaneous_separation, independent_interaction_or_trajectory, integrated_component,
non_entity, unresolved, category_only. Physical confirmation needs a direct
physical_boundary, direct_interaction, or temporal_continuity observation at
the exact accepted proposal set, independently of the support_quality label.
Every adjudicator_evidence item, including unresolved evidence in rejected or
abstained clusters, may name only its own cluster's proposal IDs and IDs owned by
partners declared in this cluster's own identity_comparisons. A reverse declaration
elsewhere creates no local link. This is a maximum allowance, not a requirement
that every weak observation cover the complete owner. Keep meaningful local
comparisons unresolved when appropriate; never invent a partner, copy evidence,
or relabel an observation's scope to satisfy validation. An eligible original
reverse-owner union proof can still serve the undirected gate without a new link.
identity_comparisons contains other_cluster_id (in this output ledger), judgment
(confirmed_same_scope/confirmed_distinct/unresolved), scope_relation (comparable/
whole_part/group_member/unresolved), and zero-based evidence_indices into this
cluster's adjudicator_evidence. Confirmed same/distinct requires comparable scope
and respectively same_instance_continuity or a distinctness cue
(simultaneous_separation/independent_interaction_or_trajectory) whose
proposal IDs equal the union of both complete compared scopes. Other relations
use judgment=unresolved and never imply an alias. Explicitly compare any retained
challenged partners whose identity the revision claims to resolve.
revision_resolutions is [] initially. A revision may independently resolve missing
or conflicting verifier evidence, but must record each resolved axis as a separate
entry: axis (physical_entity/proposal_scope/instance_correspondence),
target_cluster_ids (all initial targets involved in that assertion),
anonymous_proposal_ids (exact final cluster scope), and evidence_indices (zero
based indices into this cluster's adjudicator_evidence). For every axis, the
resolution owner is its containing final cluster's complete scope. The referenced
observation for retained-distinct identity covers both complete final scopes;
that pair union does not change the resolution's owner. A merged final cluster's
own scope can itself be a union. A physical_entity entry
requires exact-scope physical evidence. This axis also covers graph-worthiness in
the existing gate: if a verifier confirms existence but its salience judgment is
not graph_worthy, retaining accept requires an explicit exact-scope physical_entity
resolution explaining the independently node-worthy boundary or functional scope;
do not misrepresent that salience disagreement as a denial of existence.
proposal_scope requires exact-scope
physical_boundary/direct_interaction/temporal_continuity/same_instance_continuity evidence.
For merging initial targets, instance_correspondence requires exact final-union
same_instance_continuity evidence. For retaining challenged targets separately,
it requires an explicit confirmed_distinct comparison and simultaneous_separation
or independent_interaction_or_trajectory
evidence at both complete final scopes, and target_cluster_ids must include all
initial targets contributing to either side. Distinctness is an unordered pair
claim: one currently eligible endpoint's complete exact-union revision proof may
support that same pair from either direction, without copying evidence or inventing
a reciprocal comparison. Any existing contrary or unresolved comparable claim, or
conflicting scope relation, still blocks acceptance; one reused adjudicator proof
is not two independent observations. Missing required review or a promoted
unreviewed acceptance needs both physical_entity and proposal_scope resolutions.
Do not use renamed categories, voting, strong ratings, or generic confidence
claims to resolve disagreement. Never transfer parent confirmation to a subset:
an intra-cluster split still requires the exact authorized two-verifier partition
and each verifier's exact child evidence; a revision cannot override that boundary.
Independent interaction/trajectory must positively establish different identities
for both exact compared scopes, such as one unit being lifted while the other
remains separately localized. Incomplete edges do not preclude this cue. Ordinary
camera motion or two descriptions of the same trajectory do not establish
distinctness; category uncertainty remains separate.
"""


class PhysicalIdentityContractError(ValueError):
    """Malformed physical identity extension (not an uncertain visual answer)."""


def _fail(message: str) -> None:
    raise PhysicalIdentityContractError(message)


def _ids(value: Any, label: str, *, allow_empty: bool = False) -> frozenset[str]:
    if (not isinstance(value, (list, tuple)) or
            any(not isinstance(x, str) or not x for x in value) or
            len(value) != len(set(value)) or (not value and not allow_empty)):
        _fail(f"{label} must contain unique nonempty IDs")
    return frozenset(value)


def _enum(record: Mapping[str, Any], key: str, values: Sequence[str]) -> None:
    if record.get(key) not in values:
        _fail(f"Invalid or missing {key}: {record.get(key)!r}")


def _axes(record: Mapping[str, Any]) -> None:
    _enum(record, "existence_judgment", ("confirmed", "rejected", "uncertain"))
    _enum(record, "salience_judgment", ("graph_worthy", "background_integrated", "ambiguous"))
    _enum(record, "proposal_scope_judgment", PROPOSAL_SCOPE_JUDGMENTS)
    _enum(record, "category_resolution", CATEGORY_RESOLUTIONS)


def _evidence(items: Any, *, allowed_ids: frozenset[str], valid_frames: set[int]) -> None:
    if not isinstance(items, list):
        _fail("Evidence must be an array")
    for item in items:
        if not isinstance(item, Mapping):
            _fail("Evidence item must be an object")
        scope = _ids(item.get("anonymous_proposal_ids"), "Evidence scope")
        if not scope <= allowed_ids:
            _fail("Evidence references a proposal outside its allowed scope")
        if type(item.get("frame_id")) is not int or item["frame_id"] not in valid_frames:
            _fail("Evidence references an invalid original frame")
        _enum(item, "cue_type", CUE_TYPES)
        for key in ("coarse_locator", "observation"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                _fail(f"Evidence requires a concrete {key}")


def _indices(value: Any, evidence: Sequence[Mapping[str, Any]], *, nonempty: bool) -> list[int]:
    if (not isinstance(value, list) or any(type(x) is not int for x in value) or
            len(value) != len(set(value)) or
            any(x < 0 or x >= len(evidence) for x in value) or (nonempty and not value)):
        _fail("Invalid evidence_indices: use unique in-range zero-based indices")
    return value


def _witness(items: Sequence[Mapping[str, Any]], scope: frozenset[str], cues: frozenset[str]) -> bool:
    return any(
        set(item.get("anonymous_proposal_ids", [])) == scope
        and item.get("cue_type") in cues
        and isinstance(item.get("observation"), str) and bool(item["observation"].strip())
        and isinstance(item.get("coarse_locator"), str) and bool(item["coarse_locator"].strip())
        and type(item.get("frame_id")) is int
        for item in items
    )


def confirmed_same_scope_ids(comparisons: Sequence[Mapping[str, Any]]) -> list[str]:
    """Legacy alias list is a projection, never an independent model judgment."""
    return sorted(item["other_cluster_id"] for item in comparisons
                  if item.get("judgment") == "confirmed_same_scope"
                  and item.get("scope_relation") == "comparable")


def _comparisons(
    record: Mapping[str, Any], *, own_scope: frozenset[str],
    scope_by_cluster: Mapping[str, frozenset[str]], evidence_key: str,
    required_partners: set[str] | None = None, all_cluster_ids: set[str] | None = None,
) -> None:
    comparisons = record.get("identity_comparisons")
    if not isinstance(comparisons, list):
        _fail("identity_comparisons must be an array")
    seen: set[str] = set()
    evidence = record[evidence_key]
    for item in comparisons:
        partner = item.get("other_cluster_id")
        if (not isinstance(partner, str) or not partner or partner == record["cluster_id"]
                or partner in seen or (all_cluster_ids is not None and partner not in all_cluster_ids)):
            _fail("Invalid, self, or duplicate identity comparison partner")
        seen.add(partner)
        _enum(item, "judgment", IDENTITY_JUDGMENTS)
        _enum(item, "scope_relation", SCOPE_RELATIONS)
        confirmed = item["judgment"] != "unresolved"
        indices = _indices(item.get("evidence_indices"), evidence, nonempty=confirmed)
        if confirmed:
            if item["scope_relation"] != "comparable":
                _fail("Whole-part/group-member/unresolved scopes cannot assert same-scope identity")
            if partner not in scope_by_cluster:
                _fail("Confirmed comparison requires the partner's complete proposal scope")
            cues = SAME_CUES if item["judgment"] == "confirmed_same_scope" else DISTINCT_CUES
            if not _witness([evidence[i] for i in indices], own_scope | scope_by_cluster[partner], cues):
                _fail("Confirmed comparison lacks exact union-scope direct identity evidence")
    if required_partners is not None and not required_partners <= seen:
        _fail(f"Missing challenge partner comparisons: {sorted(required_partners - seen)}")


def validate_verifier_identity_fields(
    report: Mapping[str, Any], *, target_proposal_ids_by_cluster: Mapping[str, Sequence[str]],
    identity_challenge_pairs: Sequence[Mapping[str, Any]], valid_frame_ids: Sequence[int],
    all_cluster_ids: Sequence[str] | None = None,
) -> None:
    """Validate the v0.6 extension after base verifier validation."""
    if report.get("schema_version") != SCHEMA_VERSION:
        _fail("Incorrect physical identity schema_version")
    scopes = {key: _ids(value, "Target scope") for key, value in target_proposal_ids_by_cluster.items()}
    known = set(all_cluster_ids) if all_cluster_ids is not None else set(scopes)
    required = {key: set() for key in scopes}
    for pair in identity_challenge_pairs:
        a, b = pair.get("cluster_id_a"), pair.get("cluster_id_b")
        if a not in known or b not in known or a == b:
            _fail("Invalid identity challenge pair")
        if a in required:
            required[a].add(b)
        if b in required:
            required[b].add(a)
    reviews = report.get("reviews", [])
    review_ids = [item.get("cluster_id") for item in reviews]
    if len(review_ids) != len(set(review_ids)) or set(review_ids) != set(scopes):
        _fail("Physical reviews must cover every supplied target exactly once")
    for review in reviews:
        cluster_id = review["cluster_id"]
        _axes(review)
        partners = required[cluster_id] | {x.get("other_cluster_id") for x in review.get("identity_comparisons", [])}
        allowed = scopes[cluster_id] | frozenset().union(*(scopes.get(x, frozenset()) for x in partners))
        _evidence(review.get("evidence"), allowed_ids=allowed, valid_frames=set(valid_frame_ids))
        _evidence(review.get("observed_independence_evidence"), allowed_ids=allowed, valid_frames=set(valid_frame_ids))
        _comparisons(review, own_scope=scopes[cluster_id], scope_by_cluster=scopes,
                     evidence_key="evidence", required_partners=required[cluster_id], all_cluster_ids=known)
        actual = _ids(review.get("same_instance_with_cluster_ids"), "Legacy aliases", allow_empty=True)
        if actual != set(confirmed_same_scope_ids(review["identity_comparisons"])):
            _fail("same_instance_with_cluster_ids must exactly project confirmed_same_scope")
        for unit in review.get("proposed_physical_units", []):
            unit_scope = _ids(unit.get("anonymous_proposal_ids"), "Physical unit scope")
            if not unit_scope <= scopes[cluster_id]:
                _fail("Physical unit is outside the initial target")
            _axes(unit)
            _evidence(unit.get("evidence"), allowed_ids=unit_scope, valid_frames=set(valid_frame_ids))


def validate_adjudication_identity_fields(
    decisions: Mapping[str, Any], *, valid_frame_ids: Sequence[int],
    expected_proposal_ids: Sequence[str] | None = None,
) -> None:
    """Validate typed axes and references, allowing honest unresolved decisions."""
    if decisions.get("schema_version") != SCHEMA_VERSION:
        _fail("Incorrect physical identity schema_version")
    clusters = decisions.get("clusters", [])
    scopes: dict[str, frozenset[str]] = {}
    seen: set[str] = set()
    for cluster in clusters:
        key = cluster.get("cluster_id")
        if not isinstance(key, str) or not key or key in scopes:
            _fail("Invalid or duplicate adjudication cluster ID")
        scope = _ids(cluster.get("anonymous_proposal_ids"), "Adjudication scope")
        if seen & scope:
            _fail("Proposal assigned to multiple adjudication clusters")
        seen.update(scope)
        scopes[key] = scope
    if expected_proposal_ids is not None and seen != set(expected_proposal_ids):
        _fail("Adjudication does not cover the expected proposal universe")
    for cluster in clusters:
        _axes(cluster)
        own = scopes[cluster["cluster_id"]]
        partners = {item.get("other_cluster_id") for item in cluster.get("identity_comparisons", [])}
        allowed = own | frozenset().union(*(scopes.get(x, frozenset()) for x in partners))
        evidence = cluster.get("adjudicator_evidence")
        _evidence(evidence, allowed_ids=allowed, valid_frames=set(valid_frame_ids))
        _comparisons(cluster, own_scope=own, scope_by_cluster=scopes,
                     evidence_key="adjudicator_evidence", all_cluster_ids=set(scopes))
        resolutions = cluster.get("revision_resolutions")
        if not isinstance(resolutions, list):
            _fail("revision_resolutions must be an array")
        seen_resolutions = set()
        for resolution in resolutions:
            _enum(resolution, "axis", RESOLUTION_AXES)
            target_ids = _ids(resolution.get("target_cluster_ids"), "Revision initial target IDs")
            if _ids(resolution.get("anonymous_proposal_ids"), "Revision exact scope") != own:
                _fail("Revision resolution must name exactly its final cluster scope")
            _indices(resolution.get("evidence_indices"), evidence, nonempty=True)
            key = (resolution["axis"], target_ids)
            if key in seen_resolutions:
                _fail("Duplicate revision resolution for the same axis and targets")
            seen_resolutions.add(key)


def prepare_initial_adjudication_for_review(
    decisions: Mapping[str, Any], valid_frame_ids: Sequence[int],
    expected_proposal_ids: Sequence[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Withdraw only unsupported initial pair certainty, without visual correction.

    The caller must first validate the base/schema contract and use this only for
    the initial adjudicator, never a verifier or revision. All structural and
    malformed reference errors remain fatal. The strict extension validator is unchanged
    and validates the complete derived ledger before anything is returned.

    Only a comparable confirmed comparison with a valid reference array (which
    may be empty) but no referenced exact-union identity witness becomes
    unresolved. Empty references remain empty: no local or reciprocal witness
    is selected for the model. Nothing else,
    including the referenced evidence and indices, changes. A witness elsewhere
    in the same ledger is not copied or rebound. The caller must durably preserve
    the raw output and this audit, enforce both independent verifier reviews of
    every pending pair, and carry the obligation through final scope disposition.

    Repeating the call on the raw input is deterministic. Repeating it on the
    derived ledger changes nothing and reports no *new* pending conversions;
    it must not replace the original audit or discharge its pending obligations.
    """
    derived = copy.deepcopy(dict(decisions))
    clusters = derived.get("clusters", [])
    scopes = {cluster["cluster_id"]: _ids(cluster.get("anonymous_proposal_ids"), "Adjudication scope")
              for cluster in clusters}
    pending = []
    for cluster_index, cluster in enumerate(clusters):
        if cluster.get("revision_resolutions"):
            _fail("Initial preparation cannot process revision resolutions")
        own_id = cluster["cluster_id"]
        own_scope = scopes[own_id]
        comparisons = cluster.get("identity_comparisons")
        if not isinstance(comparisons, list):
            _fail("identity_comparisons must be an array")
        evidence = cluster.get("adjudicator_evidence")
        partners = {item.get("other_cluster_id") for item in comparisons}
        allowed = own_scope | frozenset().union(*(scopes.get(x, frozenset()) for x in partners))
        _evidence(evidence, allowed_ids=allowed, valid_frames=set(valid_frame_ids))
        seen = set()
        for comparison_index, item in enumerate(comparisons):
            other_id = item.get("other_cluster_id")
            if (not isinstance(other_id, str) or not other_id or other_id == own_id
                    or other_id in seen or other_id not in scopes):
                _fail("Invalid, self, or duplicate identity comparison partner")
            seen.add(other_id)
            _enum(item, "judgment", IDENTITY_JUDGMENTS)
            _enum(item, "scope_relation", SCOPE_RELATIONS)
            confirmed = item["judgment"] != "unresolved"
            # Initial-only withdrawal permits a well-typed empty list. The
            # public strict comparison validator still requires positive proof.
            indices = _indices(item.get("evidence_indices"), evidence, nonempty=False)
            if not confirmed:
                continue
            if item["scope_relation"] != "comparable":
                _fail("Whole-part/group-member/unresolved scopes cannot assert same-scope identity")
            union_scope = own_scope | scopes[other_id]
            cues = SAME_CUES if item["judgment"] == "confirmed_same_scope" else DISTINCT_CUES
            if _witness([evidence[i] for i in indices], union_scope, cues):
                continue
            first, second = sorted((own_id, other_id))
            pending.append({
                "json_pointer": f"/clusters/{cluster_index}/identity_comparisons/{comparison_index}/judgment",
                "cluster_id_a": first, "cluster_id_b": second,
                "own_cluster_id": own_id, "other_cluster_id": other_id,
                "own_anonymous_proposal_ids": sorted(own_scope),
                "other_anonymous_proposal_ids": sorted(scopes[other_id]),
                "union_anonymous_proposal_ids": sorted(union_scope),
                "source_judgment": item["judgment"], "derived_judgment": "unresolved",
                "scope_relation": item["scope_relation"], "evidence_indices": list(indices),
                "reason": "confirmed_comparison_missing_exact_union_scope_identity_witness",
            })
            item["judgment"] = "unresolved"
    # A repairable early assertion must never hide another structural, reference,
    # ownership, axis, or schema-version failure later in the initial ledger.
    validate_adjudication_identity_fields(
        derived, valid_frame_ids=valid_frame_ids, expected_proposal_ids=expected_proposal_ids)
    return derived, {
        "policy_version": INITIAL_PREPARATION_VERSION,
        "stage": "initial_adjudication",
        "visual_correction": False,
        "pending_comparisons": sorted(pending, key=lambda item: (item["own_cluster_id"], item["other_cluster_id"])),
    }


def _physical_confirmed(record: Mapping[str, Any], scope: frozenset[str], evidence_key: str) -> bool:
    return (record.get("existence_judgment") == "confirmed"
            and record.get("salience_judgment") == "graph_worthy"
            and _witness(record.get(evidence_key, []), scope, PHYSICAL_CUES))


def _scope_confirmed(record: Mapping[str, Any], scope: frozenset[str], evidence_key: str) -> bool:
    return (record.get("proposal_scope_judgment") == "resolved_single_scope"
            and _witness(record.get(evidence_key, []), scope,
                         PHYSICAL_CUES | SAME_CUES))


def _resolution(
    cluster: Mapping[str, Any], axis: str, targets: frozenset[str], scope: frozenset[str],
    cues: frozenset[str], *, witness_scope: frozenset[str] | None = None,
) -> bool:
    evidence = cluster.get("adjudicator_evidence", [])
    for item in cluster.get("revision_resolutions", []):
        if (item.get("axis") != axis or set(item.get("target_cluster_ids", [])) != targets
                or set(item.get("anonymous_proposal_ids", [])) != scope):
            continue
        indices = item.get("evidence_indices", [])
        if (not indices or any(type(i) is not int or i < 0 or i >= len(evidence) for i in indices)):
            continue
        if _witness([evidence[i] for i in indices], witness_scope if witness_scope is not None else scope, cues):
            return True
    return False


def _comparison_confirmed(
    record: Mapping[str, Any], partner: str, judgment: str, scope: frozenset[str], evidence_key: str,
) -> bool:
    evidence = record.get(evidence_key, [])
    matches = [x for x in record.get("identity_comparisons", []) if x.get("other_cluster_id") == partner]
    if len(matches) != 1:
        return False
    item = matches[0]
    if item.get("judgment") != judgment or item.get("scope_relation") != "comparable":
        return False
    indices = item.get("evidence_indices", [])
    if not indices or any(type(i) is not int or i < 0 or i >= len(evidence) for i in indices):
        return False
    return _witness([evidence[i] for i in indices], scope,
                    SAME_CUES if judgment == "confirmed_same_scope" else DISTINCT_CUES)


def _distinct_revision_proof(
    cluster: Mapping[str, Any], *, other_cluster_id: str,
    targets: frozenset[str], own_scope: frozenset[str], other_scope: frozenset[str],
) -> dict[str, Any] | None:
    """Locate an existing complete proof; return provenance without rebinding it."""
    pair_scope = own_scope | other_scope
    comparisons = [(index, item) for index, item in enumerate(cluster.get("identity_comparisons", []))
                   if item.get("other_cluster_id") == other_cluster_id]
    if len(comparisons) != 1:
        return None
    comparison_index, comparison = comparisons[0]
    if comparison.get("judgment") != "confirmed_distinct" or comparison.get("scope_relation") != "comparable":
        return None
    evidence = cluster.get("adjudicator_evidence", [])

    def witness_indices(item):
        indices = item.get("evidence_indices")
        if (not isinstance(indices, list) or not indices
                or any(type(i) is not int or i < 0 or i >= len(evidence) for i in indices)
                or len(indices) != len(set(indices))):
            return []
        return [i for i in indices if _witness([evidence[i]], pair_scope, DISTINCT_CUES)]

    comparison_witnesses = witness_indices(comparison)
    if not comparison_witnesses:
        return None
    resolutions = [(index, item) for index, item in enumerate(cluster.get("revision_resolutions", []))
                   if item.get("axis") == "instance_correspondence"
                   and frozenset(item.get("target_cluster_ids", [])) == targets
                   and frozenset(item.get("anonymous_proposal_ids", [])) == own_scope]
    if len(resolutions) != 1:
        return None
    resolution_index, resolution = resolutions[0]
    resolution_witnesses = witness_indices(resolution)
    if not resolution_witnesses:
        return None
    return {
        "policy": DISTINCT_REVISION_PROOF_POLICY,
        "source_cluster_id": cluster["cluster_id"], "other_cluster_id": other_cluster_id,
        "source_anonymous_proposal_ids": sorted(own_scope),
        "other_anonymous_proposal_ids": sorted(other_scope),
        "union_anonymous_proposal_ids": sorted(pair_scope),
        "initial_target_cluster_ids": sorted(targets),
        "comparison_index": comparison_index,
        "comparison_evidence_indices": list(comparison["evidence_indices"]),
        "comparison_exact_union_witness_indices": comparison_witnesses,
        "resolution_index": resolution_index,
        "resolution_evidence_indices": list(resolution["evidence_indices"]),
        "resolution_exact_union_witness_indices": resolution_witnesses,
        "independent_observation": False, "evidence_copied_or_rebound": False,
        "reciprocal_comparison_created": False,
    }


def _retention_json_hash(value: Any) -> str:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PhysicalIdentityContractError("Retention binding requires finite JSON") from exc
    return hashlib.sha256(encoded).hexdigest()


def _retention_gate_binding(
    decisions: Mapping[str, Any], initial_decisions: Mapping[str, Any],
    verifier_reports: Sequence[Mapping[str, Any]], roster: Sequence[str],
    consensus: Mapping[str, Any], split_parent_ids: Sequence[str],
) -> tuple[dict[str, Any], dict[str, Mapping[str, Any]], dict[str, dict[str, Mapping[str, Any]]]]:
    # Load beside this gate, including when it is in a frozen workspace. The
    # default gate never imports the opt-in helper or changes its dependency path.
    spec = importlib.util.spec_from_file_location(
        "physical_gate_retention_helper", Path(__file__).with_name("proposal_scope_retention.py"))
    if spec is None or spec.loader is None:
        _fail("Retention helper is unavailable beside the physical gate")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    if not isinstance(consensus, Mapping) or consensus.get("policy_version") != helper.POLICY_VERSION:
        _fail("Unknown retention gate policy")
    binding = consensus.get("input_binding")
    if not isinstance(binding, Mapping) or binding.get("verifier_ids") != sorted(roster):
        _fail("Retention consensus verifier roster differs from the current gate")
    current = {report["verifier_id"]: report for report in verifier_reports}
    bound = binding.get("verifier_reports")
    if (len(current) != len(roster) or not isinstance(bound, list) or len(bound) != len(roster)
            or any(not isinstance(row, Mapping) or not isinstance(row.get("verifier_id"), str)
                   for row in bound)
            or {row.get("verifier_id") for row in bound} != set(roster)):
        _fail("Retention requires both current complete verifier reports")
    requests = {}
    for row in bound:
        verifier = row["verifier_id"]
        report = current[verifier]
        if (report.get("scope_retention_policy") != helper.POLICY_VERSION
                or _retention_json_hash(row) != _retention_json_hash(report)):
            _fail("Retention consensus does not bind the current extended verifier report")
    try:
        transition = helper.validate_retention_transition(
            initial_decisions, decisions, consensus,
            independently_authorized_split_parent_ids=list(split_parent_ids))
    except helper.RetentionContractError as exc:
        raise PhysicalIdentityContractError(str(exc)) from exc
    # The helper authenticated every request and its indices while rebuilding
    # consensus. Keep the complete original review obligation as well.
    for verifier, report in current.items():
        reviewed = {row["cluster_id"] for row in report["reviews"]}
        requests[verifier] = {row["parent_cluster_id"]: row for row in report["retention_requests"]}
        if not set(requests[verifier]) <= reviewed:
            _fail("Retention request lacks its complete original-target review")
    applied = {row["parent_cluster_id"]: row for row in transition["audited_transitions"]}
    audit = {
        "policy_version": helper.POLICY_VERSION,
        "consensus_sha256": _retention_json_hash(consensus),
        "initial_decisions_sha256": binding["initial_decisions_sha256"],
        "verifier_report_sha256s": {key: _retention_json_hash(current[key]) for key in sorted(current)},
        "report_sources": copy.deepcopy(binding["report_sources"]),
        "valid_frame_ids": list(binding["valid_frame_ids"]),
        "transition_audit_stage": "pre_gate_revision", "transition_audit": transition,
        "exact_subset_proofs": copy.deepcopy([row for row in consensus["records"]
                                                if row["parent_cluster_id"] in applied]),
        "final_relation_proofs": [], "gated_survivor_results": [],
        "independent_source_authentication": "caller_supplied_not_self_proven",
        "native_success_and_frame_universe_authentication": "outer_caller_required",
        "residual_existence_asserted": False, "pixel_truth_verified": False,
    }
    return audit, applied, requests


def _retention_final_relation_proof(
    left: Mapping[str, Any], right: Mapping[str, Any],
    left_scope: frozenset[str], right_scope: frozenset[str],
) -> dict[str, Any] | None:
    """A current, reciprocal non-alias relation; never inherit parent evidence."""
    endpoints = []
    relation = None
    union = left_scope | right_scope
    for own, other in ((left, right), (right, left)):
        matches = [(i, row) for i, row in enumerate(own.get("identity_comparisons", []))
                   if row.get("other_cluster_id") == other["cluster_id"]]
        if len(matches) != 1:
            return None
        index, row = matches[0]
        current_relation = row.get("scope_relation")
        if (current_relation not in {"whole_part", "group_member"}
                or row.get("judgment") != "unresolved"
                or (relation is not None and relation != current_relation)):
            return None
        relation = current_relation
        evidence = own.get("adjudicator_evidence", [])
        indices = row.get("evidence_indices")
        if (not isinstance(indices, list) or not indices
                or any(type(i) is not int or i < 0 or i >= len(evidence) for i in indices)
                or len(indices) != len(set(indices))):
            return None
        witnesses = [i for i in indices if _witness(
            [evidence[i]], union, PHYSICAL_CUES | frozenset(("integrated_component",)))]
        if not witnesses:
            return None
        endpoints.append({"cluster_id": own["cluster_id"], "comparison_index": index,
                          "evidence_indices": list(indices), "exact_union_witness_indices": witnesses})
    return {"scope_relation": relation, "union_anonymous_proposal_ids": sorted(union),
            "endpoints": endpoints, "evidence_copied_or_rebound": False,
            "independent_observation": False}


def apply_physical_identity_gate(
    decisions: Mapping[str, Any], *, initial_decisions: Mapping[str, Any],
    verifier_reports: Sequence[Mapping[str, Any]],
    verification_target_reasons: Mapping[str, Sequence[str]],
    verifier_ids: Sequence[str] = ("verifier_1", "verifier_2"),
    intra_cluster_split_consensus: Mapping[str, Any] | None = None,
    retention_consensus: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Conservative, source-independent exact-scope gate for physical_v0.6.

    Inputs must first pass base/schema/extension validation. This function never
    creates or merges scopes. It changes unsupported accepts to auditably retained
    abstentions. Structured revision can resolve evidence disagreements, but cannot
    bypass the exact split firewall. Nonaccept decisions remain unchanged. The
    opt-in retention ledger requires authenticated caller provenance and two
    dedicated subset proofs; it neither authenticates native calls itself nor
    grants physical status to residual claims.
    """
    if decisions.get("schema_version") != SCHEMA_VERSION or initial_decisions.get("schema_version") != SCHEMA_VERSION:
        _fail("The physical gate requires v0.6 initial and revised ledgers")
    roster = tuple(verifier_ids)
    if len(roster) != 2 or len(set(roster)) != 2 or any(not x for x in roster):
        _fail("The physical gate requires two distinct isolated verifier IDs")
    reports: dict[str, dict[str, Mapping[str, Any]]] = {}
    for report in verifier_reports:
        verifier = report.get("verifier_id")
        if verifier not in roster or verifier in reports or report.get("schema_version") != SCHEMA_VERSION:
            _fail("Unexpected, duplicate, or legacy verifier report")
        rows = report.get("reviews", [])
        if len({x["cluster_id"] for x in rows}) != len(rows):
            _fail("Duplicate verifier target")
        reports[verifier] = {x["cluster_id"]: x for x in rows}
    initial = {c["cluster_id"]: c for c in initial_decisions["clusters"]}
    initial_scopes = {key: frozenset(c["anonymous_proposal_ids"]) for key, c in initial.items()}
    required = set(verification_target_reasons) | {key for report in reports.values() for key in report}
    if not required <= set(initial):
        _fail("A verification target is absent from the initial ledger")
    partitions: dict[str, set[frozenset[str]]] = {}
    for item in (intra_cluster_split_consensus or {}).get("exact_consensus_partitions", []):
        key = item["cluster_id"]
        groups = [frozenset(x) for x in item["proposal_partition"]]
        if (key not in initial or len(groups) < 2 or any(not x for x in groups)
                or len(set(groups)) != len(groups)
                or sum(map(len, groups)) != len(frozenset().union(*groups))
                or frozenset().union(*groups) != initial_scopes[key]):
            _fail("Invalid exact split consensus partition")
        partitions[key] = set(groups)
    retention_audit = None
    retained = {}
    retention_requests = {}
    if retention_consensus is not None:
        retention_audit, retained, retention_requests = _retention_gate_binding(
            decisions, initial_decisions, verifier_reports, roster, retention_consensus,
            sorted(partitions))
    retained_survivor_ids = {row["survivor_cluster_id"] for row in retained.values()}
    gated = copy.deepcopy(decisions)
    final = {c["cluster_id"]: c for c in decisions["clusters"]}
    final_scopes = {key: frozenset(c["anonymous_proposal_ids"]) for key, c in final.items()}
    universe = frozenset().union(*initial_scopes.values())
    if frozenset().union(*final_scopes.values()) != universe:
        _fail("Revision changed the proposal universe")
    target_sets = {key: frozenset(t for t, old in initial_scopes.items() if scope & old)
                   for key, scope in final_scopes.items()}
    records = []
    for cluster in gated["clusters"]:
        if cluster["decision"] != "accept":
            continue
        key = cluster["cluster_id"]
        scope = final_scopes[key]
        targets = target_sets[key]
        failures: list[str] = []
        resolutions_used: list[str] = []
        if not _physical_confirmed(cluster, scope, "adjudicator_evidence"):
            failures.append("final_physical_entity_not_confirmed_at_exact_scope")
        if not _scope_confirmed(cluster, scope, "adjudicator_evidence") or cluster.get("identity_status") != "resolved":
            failures.append("final_proposal_or_physical_identity_scope_unresolved")
        judgments = []
        missing_or_disputed_physical = False
        missing_or_disputed_scope = False
        hard_split_failure = False
        for target in sorted(targets):
            overlap = scope & initial_scopes[target]
            partial = overlap != initial_scopes[target]
            retention = retained.get(target)
            retained_subset = (retention is not None and retention["survivor_cluster_id"] == key
                               and frozenset(retention["retained_anonymous_proposal_ids"]) == scope)
            if partial and not retained_subset and overlap not in partitions.get(target, set()):
                hard_split_failure = True
                failures.append(f"{target}:partial_target_without_exact_split_authorization")
            for verifier in roster:
                review = reports.get(verifier, {}).get(target)
                if target not in required and not partial:
                    continue
                unit: Mapping[str, Any] = review or {}
                scope_kind = "complete_initial_target"
                if partial and retained_subset:
                    unit = retention_requests[verifier][target]
                    scope_kind = "exact_retention_survivor_subset"
                elif partial:
                    reported_partition = {frozenset(u.get("anonymous_proposal_ids", []))
                                          for u in unit.get("proposed_physical_units", [])}
                    matches = [u for u in unit.get("proposed_physical_units", [])
                               if frozenset(u.get("anonymous_proposal_ids", [])) == overlap]
                    if (unit.get("intra_cluster_split_judgment") != "split_into_multiple_physical_instances"
                            or len(matches) != 1 or reported_partition != partitions.get(target, set())):
                        unit = {}
                    else:
                        unit = matches[0]
                    scope_kind = "exact_consensus_split_unit"
                if partial and retained_subset:
                    # Only the request's indexed subset witnesses count. Whole
                    # target review, split units, and revision repair are not votes.
                    evidence = unit["retained_evidence"]
                    physical = _physical_confirmed(
                        {**unit, "evidence": [evidence[i] for i in unit["physical_evidence_indices"]]},
                        overlap, "evidence")
                    scoped = _scope_confirmed(
                        {**unit, "evidence": [evidence[i] for i in unit["scope_evidence_indices"]]},
                        overlap, "evidence")
                    if not (physical and scoped):
                        _fail("Validated retention request lost its exact subset witnesses")
                else:
                    physical = _physical_confirmed(unit, overlap, "evidence")
                    scoped = _scope_confirmed(unit, overlap, "evidence")
                judgments.append({"verifier_id": verifier, "target_cluster_id": target,
                                  "anonymous_proposal_ids": sorted(overlap), "scope_kind": scope_kind,
                                  "record_present": bool(unit), "physical_confirmed": physical,
                                  "proposal_scope_confirmed": scoped})
                missing_or_disputed_physical |= not physical
                missing_or_disputed_scope |= not scoped
                if partial and not (physical and scoped):
                    hard_split_failure = True
                    failures.append(f"{target}:{verifier}:exact_split_unit_not_confirmed")
        unchanged_anchor = (len(targets) == 1 and
                            initial_scopes[next(iter(targets))] == scope and
                            initial[next(iter(targets))].get("decision") == "accept"
                            and initial[next(iter(targets))].get("identity_status") == "resolved"
                            and _physical_confirmed(initial[next(iter(targets))], scope, "adjudicator_evidence")
                            and _scope_confirmed(initial[next(iter(targets))], scope, "adjudicator_evidence"))
        # An unreviewed initial abstention/rejection or a newly combined scope is
        # never promoted solely by a renamed final entity or fresh confidence.
        requires_new_scope_resolution = not unchanged_anchor and any(t not in required for t in targets)
        for axis, needed, cues in (
            ("physical_entity", missing_or_disputed_physical or requires_new_scope_resolution, PHYSICAL_CUES),
            ("proposal_scope", missing_or_disputed_scope or requires_new_scope_resolution, PHYSICAL_CUES | SAME_CUES),
        ):
            if needed:
                if _resolution(cluster, axis, targets, scope, cues):
                    resolutions_used.append(axis)
                else:
                    failures.append(f"{axis}:missing_exact_scope_revision_resolution")
        # Combining complete initial targets needs positive same-content evidence
        # connecting every contributing target, independently from their existence.
        if len(targets) > 1:
            connected_by_both = True
            for verifier in roster:
                explicit_conflict = any(
                    comparison.get("other_cluster_id") in targets
                    and (comparison.get("judgment") != "confirmed_same_scope"
                         or comparison.get("scope_relation") != "comparable")
                    for target in targets
                    for comparison in reports.get(verifier, {}).get(target, {}).get("identity_comparisons", []))
                reached = {min(targets)}
                while True:
                    added = {b for a in reached for b in targets - reached
                             if initial_scopes[a] <= scope and initial_scopes[b] <= scope
                             and _comparison_confirmed(reports.get(verifier, {}).get(a, {}), b,
                                                       "confirmed_same_scope", initial_scopes[a] | initial_scopes[b], "evidence")
                             and _comparison_confirmed(reports.get(verifier, {}).get(b, {}), a,
                                                       "confirmed_same_scope", initial_scopes[a] | initial_scopes[b], "evidence")}
                    if not added:
                        break
                    reached |= added
                connected_by_both &= reached == targets and not explicit_conflict
            if not connected_by_both:
                if _resolution(cluster, "instance_correspondence", targets, scope, SAME_CUES):
                    resolutions_used.append("instance_correspondence:merged_initial_targets")
                else:
                    failures.append("merged_initial_targets_lack_confirmed_same_scope_correspondence")
        if failures:
            cluster["decision"] = "abstain"
            cluster["identity_status"] = "ambiguous"
            cluster["final_entity"] = None
            cluster["decision_reason"] = (cluster.get("decision_reason", "") +
                                           " Physical identity gate: " + "; ".join(sorted(set(failures))))
        records.append({"cluster_id": key, "anonymous_proposal_ids": sorted(scope),
                        "initial_target_cluster_ids": sorted(targets), "verifier_judgments": judgments,
                        "identity_pair_judgments": [],
                        "revision_resolutions_used": sorted(set(resolutions_used)),
                        "exact_split_firewall_failed": hard_split_failure,
                        "failure_reasons": sorted(set(failures)), "result": cluster["decision"]})
    # Freeze unary/scope eligibility before pair review. Pair-only uncertainty
    # cannot make iteration order choose an arbitrary surviving alias.
    eligible = frozenset(c["cluster_id"] for c in gated["clusters"] if c["decision"] == "accept")
    records_by_id = {record["cluster_id"]: record for record in records}
    revision_proofs: dict[tuple[str, str], dict[str, Any] | None] = {}
    for cluster in gated["clusters"]:
        key = cluster["cluster_id"]
        if key not in eligible:
            continue
        scope = final_scopes[key]
        targets = target_sets[key]
        record = records_by_id[key]
        failures = []
        resolutions_used = list(record["revision_resolutions_used"])
        # Compare only retained accepted counterparts. An unresolved rejected
        # alternative is not a reason to delete a separately witnessed anchor.
        pair_records = []
        for other, other_cluster in final.items():
            if other == key or other not in eligible:
                continue
            other_targets = target_sets[other]
            final_pair_rows = [c for x, y in ((key, other), (other, key))
                               for c in final[x].get("identity_comparisons", [])
                               if c.get("other_cluster_id") == y]
            final_comparable_declared = any(
                c.get("scope_relation") not in {"whole_part", "group_member"} for c in final_pair_rows)
            final_pair_unresolved = any(
                c.get("scope_relation") not in {"whole_part", "group_member"}
                and c.get("judgment") != "confirmed_distinct" for c in final_pair_rows)
            final_scope_relation_conflict = final_comparable_declared and any(
                c.get("scope_relation") != "comparable" for c in final_pair_rows)
            final_pair_unresolved |= final_scope_relation_conflict
            challenged = {(a, b) for a in targets for b in other_targets if a != b
                          and any(any(c.get("other_cluster_id") == b
                                      for c in reports.get(v, {}).get(a, {}).get("identity_comparisons", []))
                                  or any(c.get("other_cluster_id") == a
                                         for c in reports.get(v, {}).get(b, {}).get("identity_comparisons", []))
                                  for v in roster)}
            # A ledger's own structured identity question remains a review risk
            # even when target selection supplied no verifier record for it.
            final_pair_declared = (
                any(c.get("other_cluster_id") == other for c in cluster.get("identity_comparisons", []))
                or any(c.get("other_cluster_id") == key for c in other_cluster.get("identity_comparisons", [])))
            challenged |= {(a, b) for a in targets for b in other_targets if a != b
                           and (final_pair_declared
                                or any(c.get("other_cluster_id") == b for c in initial[a].get("identity_comparisons", []))
                                or any(c.get("other_cluster_id") == a for c in initial[b].get("identity_comparisons", [])))}
            if not challenged:
                continue
            # Whole-part/group-member relations do not assert an alias. Their
            # eligibility is governed by physical axes and downstream partition.
            relevant = []
            for a, b in sorted(challenged):
                changed_endpoint = key in retained_survivor_ids or other in retained_survivor_ids
                if changed_endpoint:
                    relation_proof = _retention_final_relation_proof(
                        final[min(key, other)], final[max(key, other)],
                        final_scopes[min(key, other)], final_scopes[max(key, other)])
                    if relation_proof is not None:
                        if relation_proof not in retention_audit["final_relation_proofs"]:
                            retention_audit["final_relation_proofs"].append(relation_proof)
                        continue
                pair_rows = [c for v in roster for x, y in ((a, b), (b, a))
                             for c in reports.get(v, {}).get(x, {}).get("identity_comparisons", [])
                             if c.get("other_cluster_id") == y]
                if (len(pair_rows) == 2 * len(roster)
                        and not changed_endpoint
                        and not final_comparable_declared
                        and len({c.get("scope_relation") for c in pair_rows}) == 1
                        and pair_rows[0].get("scope_relation") in {"whole_part", "group_member"}):
                    continue
                ledger_rows = [c for x, y in ((key, other), (other, key))
                               for c in final[x].get("identity_comparisons", []) if c.get("other_cluster_id") == y]
                if (not changed_endpoint and not pair_rows and len(ledger_rows) == 2
                        and len({c.get("scope_relation") for c in ledger_rows}) == 1
                        and ledger_rows[0].get("scope_relation") in {"whole_part", "group_member"}):
                    continue
                relevant.append((a, b))
            if not relevant:
                continue
            distinct = all(initial_scopes[a] == scope and initial_scopes[b] == final_scopes[other]
                           and all(_comparison_confirmed(reports.get(v, {}).get(a, {}), b,
                                                         "confirmed_distinct", scope | final_scopes[other], "evidence")
                                   and _comparison_confirmed(reports.get(v, {}).get(b, {}), a,
                                                             "confirmed_distinct", scope | final_scopes[other], "evidence")
                                   for v in roster)
                           for a, b in relevant)
            pair_scope = scope | final_scopes[other]
            initial_distinct = all(
                a not in required and b not in required
                and initial_scopes[a] == scope and initial_scopes[b] == final_scopes[other]
                and initial[a].get("decision") == "accept" and initial[b].get("decision") == "accept"
                and _comparison_confirmed(initial[a], b, "confirmed_distinct", pair_scope, "adjudicator_evidence")
                and _comparison_confirmed(initial[b], a, "confirmed_distinct", pair_scope, "adjudicator_evidence")
                and _comparison_confirmed(cluster, other, "confirmed_distinct", pair_scope, "adjudicator_evidence")
                and _comparison_confirmed(other_cluster, key, "confirmed_distinct", pair_scope, "adjudicator_evidence")
                for a, b in relevant)
            pair_key = tuple(sorted((key, other)))
            if pair_key not in revision_proofs:
                # Both endpoints already survived unary and exact-split checks.
                # Read the immutable revision, not a pair-loop mutation; pair-only
                # abstention must not make proof lookup depend on iteration order.
                revision_proofs[pair_key] = next((proof for source, partner in
                    (pair_key, tuple(reversed(pair_key)))
                    if (proof := _distinct_revision_proof(
                        final[source], other_cluster_id=partner,
                        targets=target_sets[source] | target_sets[partner],
                        own_scope=final_scopes[source], other_scope=final_scopes[partner])) is not None), None)
            revision_proof = revision_proofs[pair_key]
            revised_distinct = revision_proof is not None
            # Earlier evidence cannot silently upgrade the revision's own
            # unresolved or same-scope claim into two distinct final nodes.
            if final_pair_unresolved or (not distinct and not initial_distinct and not revised_distinct):
                failures.append(f"{other}:retained_instance_correspondence_unresolved")
            if not final_pair_unresolved and not distinct and not initial_distinct and revised_distinct:
                resolutions_used.append(f"instance_correspondence:distinct_from:{other}")
            pair_records.append({"other_cluster_id": other, "verifiers_confirm_distinct": distinct,
                                 "unchanged_initial_pair_confirms_distinct": initial_distinct,
                                 "final_pair_unresolved_or_same_scope": final_pair_unresolved,
                                 "final_pair_scope_relation_conflict": final_scope_relation_conflict,
                                 "revision_confirms_distinct": revised_distinct,
                                 "revision_distinct_proof_used": (not final_pair_unresolved and not distinct
                                                                  and not initial_distinct and revised_distinct),
                                 "revision_distinct_proof": copy.deepcopy(revision_proof)})
        if failures:
            cluster["decision"] = "abstain"
            cluster["identity_status"] = "ambiguous"
            cluster["final_entity"] = None
            cluster["decision_reason"] = (cluster.get("decision_reason", "") +
                                           " Physical identity gate: " + "; ".join(sorted(set(failures))))
        record["identity_pair_judgments"] = pair_records
        record["revision_resolutions_used"] = sorted(set(resolutions_used))
        record["failure_reasons"] = sorted(set(record["failure_reasons"]) | set(failures))
        record["result"] = cluster["decision"]
    audit = {"schema_version": SCHEMA_VERSION, "policy": "source_independent_exact_scope_physical_identity",
             "distinct_revision_proof_policy": DISTINCT_REVISION_PROOF_POLICY,
             "required_verifier_ids": list(roster), "name_or_category_used": False,
             "source_or_detector_count_used": False, "support_quality_used": False,
             "records": records}
    if retention_audit is not None:
        gated_by_id = {row["cluster_id"]: row for row in gated["clusters"]}
        retention_audit["gated_survivor_results"] = [
            {"parent_cluster_id": parent, "survivor_cluster_id": row["survivor_cluster_id"],
             "decision": gated_by_id[row["survivor_cluster_id"]]["decision"]}
            for parent, row in sorted(retained.items())]
        audit["scope_retention"] = retention_audit
    return gated, audit


def build_verifier_prompt(
    *, shot_id: str, verifier_id: str, verification_view: Mapping[str, Any],
    valid_frame_ids: Sequence[int], reference_frames: Sequence[Mapping[str, Any]],
    allowed_input_paths: Sequence[str], policy_text: str | None = None,
) -> str:
    """Build the isolated verifier role, without downstream inventory policy.

    Caller supplies the existing source-blind compact verification view and records
    the policy hash in its manifest. Unexpected top-level inputs fail closed.
    """
    allowed_keys = {"targets", "cluster_index", "identity_challenge_pairs",
                    "intra_cluster_divergent_footprint_challenges"}
    if set(verification_view) - allowed_keys:
        _fail("Verifier view contains unsupported top-level material")
    if policy_text is None:
        path = Path(__file__).resolve().parents[2] / ".agents/skills/ensemble-shot-entity-detection" / VERIFIER_POLICY_RELATIVE_PATH
        policy_text = path.read_text(encoding="utf-8")
    return ("You are one isolated physical-identity verifier for exactly one shot. "
            "Review only supplied targets from original pixels. Do not discover new entities, "
            "search files, use tools, infer source votes, inspect another shot, or predict a final inventory. "
            "Return only JSON conforming to the supplied verification schema.\n\n"
            + PHYSICAL_IDENTITY_RULE + "\n" + policy_text
            + f"\nshot_id: {shot_id}\nverifier_id: {verifier_id}\nschema_version: {SCHEMA_VERSION}\n"
            + "valid_frame_ids:\n" + json.dumps(list(valid_frame_ids))
            + "\nChronological attachment mapping:\n" + json.dumps(list(reference_frames), ensure_ascii=False, indent=2)
            + "\nAllowed input paths:\n" + json.dumps(list(allowed_input_paths), ensure_ascii=False, indent=2)
            + "\nSource-blind verification targets and challenges:\n" + json.dumps(verification_view, ensure_ascii=False, indent=2))
