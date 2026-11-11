"""Pure single-shot graph-granularity family planning and assembly logic.

This module is intentionally independent of the ensemble pipeline. Callers
supply the frozen base protocol explicitly and validate assembled adjudications
against their own schema.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple


FAMILY_PLAN_PROTOCOL = "single_shot_granularity_family_plan_v0.3"
EMPTY_SUPPORTED_ANCHOR_POLICY = "zero_supported_member_anchor_exclusion_v0.1"
HOLDING_CONTAINER_SCOPE_INSTRUCTION = """Apply the shared holding/container scope rule to the exact candidate members, not their names. Protected holding/carrying includes an actor with an external held item and an inanimate mechanism or support retaining an independent load. Physical distinctness or containment alone does not establish that holder/payload relation. A visible holding or load state suffices; a pickup or movement need not be observed. Being stationary, small, portable or inanimate does not select a branch. Actual temporary packing, loading or transport payloads remain protected; ordinary storage is not temporary transport merely because later transport is possible.

A compact container-content functional unit requires positive original-pixel evidence that the bounded container structure organizes, constrains or presents the complete included content as one local functional scope. Identify that structure and organization beyond merely being inside, touching or resting on a support. Stable placement, tight enclosure, presumed conventional purpose or lack of observed separate handling alone is insufficient. Observed operation is unnecessary when visible structural organization directly supports the unit. An assembly-kind label never supplies this evidence or overrides protection.

When the only positive organization is one bounded fixture's passive same-category storage/display arrangement, the canonical collection contains its complete eligible contents and excludes the fixture. Adding the fixture requires independent positive evidence for the complete container-plus-content functional scope, not relabeling that collection. External references and independent context remain excluded. An external actor carrying a supported functional whole stays outside it; that external relation alone does not establish an internal member-payload relation.

Check actual protection and member independence before choosing cohesion. Present or uncertain protection, or observed or uncertain member independence, blocks coarsening. Absence of observed separate handling neither supplies cohesion nor by itself establishes absent protection. Unresolved classification or evidence preserves the frozen anchors; do not invent a positive explanation. All stage-specific full-scope, common-frame, context, agreement and geometry checks still apply. Graph grouping never makes physical constituents same-instance aliases.

"""
DETECTOR_ID_PATTERN = re.compile(r"^detector_[1-9][0-9]*$")
SUPPORT_QUALITY_RANK = {"weak": 0, "moderate": 1, "strong": 2}
GROSS_SPATIAL_MIN_COVISIBLE_FRAMES = 3
GROSS_SPATIAL_MIN_INCOMPATIBLE_RATIO = 0.8
GROSS_SPATIAL_MAX_IOU = 0.02
GROSS_SPATIAL_MAX_INTERSECTION_OVER_SMALLER = 0.10
GROUP_ALTERNATIVE_EXCLUSION_REASON_CODES = frozenset(
    {
        "insufficient_supported_member_anchors",
        "group_scope_not_supported_in_original_pixels",
        "not_same_member_content",
        "ordinary_duplicate_or_identity_dispute",
        "uncertain_visual_scope",
        "large_host_or_support_involved",
        "protected_relation_or_noncompact_scope",
        "contains_independently_graph_worthy_context",
        "overlaps_another_family",
        "insufficient_joint_visibility",
        "not_selected_by_exact_consensus",
    }
)
UNRESOLVABLE_GROUP_SCOPE_REASON_CODES = frozenset(
    {
        "group_scope_not_supported_in_original_pixels",
        "ordinary_duplicate_or_identity_dispute",
        "uncertain_visual_scope",
    }
)
EMPTY_CANDIDATE_ANCHOR_REASON_CODES = UNRESOLVABLE_GROUP_SCOPE_REASON_CODES | {
    "insufficient_supported_member_anchors"
}
PROPOSAL_FIELDS = (
    "proposed_name",
    "canonical_head",
    "entity_type",
    "granularity",
    "attributes",
    "evidence_frame_ids",
    "coarse_locators",
    "frame_presence",
    "uncertainty_flags",
)


class FamilyPlanError(Exception):
    """Raised when a family plan violates the partition-only contract."""


def _json_hash(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_unique(values: Sequence[str], label: str) -> set[str]:
    result = set(values)
    if len(result) != len(values):
        raise FamilyPlanError(f"{label} contains duplicate values")
    return result


def _ordered_unique(values: Sequence[str]) -> List[str]:
    seen: set[str] = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _cluster_proposal_ids(cluster: Mapping[str, Any]) -> set[str]:
    return set(cluster["anonymous_proposal_ids"])


def _eligible_group_alternative_ids(
    baseline: Mapping[str, Any],
) -> set[str]:
    return {
        cluster["cluster_id"]
        for cluster in baseline["clusters"]
        if cluster["decision"] == "reject"
        and "group_member_conflict" in cluster["uncertainty_flags"]
    }


def _detector_sort_key(detector_id: str) -> int:
    match = DETECTOR_ID_PATTERN.fullmatch(detector_id)
    if match is None:
        raise FamilyPlanError(f"Unexpected detector ID: {detector_id}")
    return int(detector_id.rsplit("_", 1)[1])


def _planner_view(anonymous_view: Mapping[str, Any]) -> Dict[str, Any]:
    """Strip all provenance-derived diagnostics before the model call."""
    return {
        "protocol_version": anonymous_view["protocol_version"],
        "shot_id": anonymous_view["shot_id"],
        "proposals": copy.deepcopy(anonymous_view["proposals"]),
    }


def _planner_baseline_view(baseline: Mapping[str, Any]) -> Dict[str, Any]:
    """Expose frozen outcomes without source-derived challenge narratives."""
    clusters = []
    for cluster in baseline["clusters"]:
        clusters.append(
            {
                "cluster_id": cluster["cluster_id"],
                "anonymous_proposal_ids": copy.deepcopy(
                    cluster["anonymous_proposal_ids"]
                ),
                "canonical_name": cluster["canonical_name"],
                "aliases": copy.deepcopy(cluster["aliases"]),
                "granularity": cluster["granularity"],
                "adjudicator_evidence": copy.deepcopy(cluster["adjudicator_evidence"]),
                "frame_presence": copy.deepcopy(cluster["frame_presence"]),
                "identity_status": cluster["identity_status"],
                "decision": cluster["decision"],
                "uncertainty_flags": [
                    flag
                    for flag in cluster["uncertainty_flags"]
                    if flag == "group_member_conflict"
                ],
                "final_entity": copy.deepcopy(cluster["final_entity"]),
            }
        )
    return {
        "protocol_version": baseline["protocol_version"],
        "shot_id": baseline["shot_id"],
        "clusters": clusters,
        "warnings": [],
    }


def _build_prompt(
    *,
    shot_id: str,
    shot_manifest: Mapping[str, Any],
    anonymous_view: Mapping[str, Any],
    baseline: Mapping[str, Any],
    skill_text: str,
) -> str:
    allowed_paths = [
        str(Path(item["path"]).resolve()) for item in shot_manifest["reference_frames"]
    ]
    return (
        "You are a source-blind graph-partition analyst for exactly one video shot. "
        "Inspect all attached original frames together. You are not an entity detector, "
        "existence verifier, prompt-bound matcher, or cross-shot reconciler. The supplied "
        "baseline adjudication has already frozen entity existence and physical identity. "
        "Your only authority is to identify strict group-versus-members graph-partition "
        "conflicts. You cannot output accept/reject decisions, final entities, replacement "
        "clusters, detector provenance, vote counts, or relations. Do not use shell tools, "
        "search the workspace, read unlisted paths, spawn agents, or inspect another shot. "
        "Return only schema-valid JSON.\n\n"
        f"Set protocol_version exactly to {FAMILY_PLAN_PROTOCOL} and shot_id exactly "
        f"to {shot_id}.\n\n"
        "Every rejected baseline cluster carrying group_member_conflict is a mandatory "
        "group-alternative review target. Inspect the claimed content directly in the "
        "original pixels across all attached frames, even when its supplied wording, "
        "box, or baseline evidence seems sufficient. List every such cluster ID exactly "
        "once in reviewed_group_alternative_cluster_ids. Account for each reviewed "
        "alternative exactly once: either include its whole cluster as a non-anchor "
        "group alternative in exactly one valid family, or add exactly one structured "
        "excluded_group_alternatives record with the most specific allowed reason_code "
        "and a concrete original-pixel reason. Never omit a target because the case is "
        "uncertain; uncertainty is an explicit exclusion. The reserved reason code "
        "not_selected_by_exact_consensus is for deterministic downstream application "
        "artifacts and must not be used in your planner output.\n\n"
        "For each structured exclusion, candidate_member_anchor_cluster_ids must list "
        "every accepted, resolved baseline anchor whose visual content the rejected group "
        "claim actually covers. Leave this list empty when original-pixel review "
        "cannot resolve the claimed group scope at all, or use "
        "insufficient_supported_member_anchors when no accepted resolved baseline "
        "anchor can be supported as covered by the claim. The latter is a conservative "
        "no-op exclusion even if the group's visible scope is resolvable: retain honest "
        "uncertainty about coverage, do not invent member anchors, relabel the scope "
        "as unresolvable, or recover rejected/abstained members. When any eligible "
        "covered anchors are supported, list all of them; "
        "insufficient_supported_member_anchors can also retain a nonempty mapping "
        "when the available anchors do not support a valid family. An excluded group "
        "cannot also appear in a family, and exclusion never authorizes a merge. "
        f"This follows coverage policy {EMPTY_SUPPORTED_ANCHOR_POLICY}. "
        "independent_context_anchor_cluster_ids "
        "must be a subset of those candidate anchors and must contain only independently "
        "graph-worthy context that prevents the alternative from being the same compact "
        "member content. Use contains_independently_graph_worthy_context when that subset "
        "is nonempty. These anchor mappings document the reviewed visual scope; they do "
        "not change any frozen decision or authorize a family.\n\n"
        "Before placing any reviewed alternative in a family, perform a mandatory "
        "minimal-scope negative/context audit. Compare the alternative separately "
        "against every accepted, resolved anchor in the supplied baseline, using the "
        "original pixels rather than its wording or boxes. First identify the exact "
        "accepted anchors whose physical content the group claim covers; then actively "
        "look for an accepted anchor that the claim also contains, conflates, or cannot "
        "cleanly exclude. Shared category wording, a plausible count, a broad group noun, "
        "box overlap, and box enclosure do not prove identical scope. An anchor with its "
        "own boundary and localization may be independently graph-worthy context when it "
        "has a different mounting plane or alignment, a different functional role, or a "
        "persistent clear gap from the intended member cohort. Internal compartment gaps, "
        "shelf planes or alignments within one canonical same-category passive fixture "
        "collection do not make its content anchors independent context. If any such context is "
        "inside or conflated with the proposed group scope, the entire rejected group "
        "alternative must be a structured exclusion using "
        "contains_independently_graph_worthy_context; list every covered candidate anchor "
        "and the context subset. Do not trim the supplied group alternative, silently "
        "drop the context anchor, or form a family from only its convenient sub-scope.\n\n"
        "A family is permitted only in the following conservative baseline shape. At "
        "least two source-blind accepted, resolved baseline clusters are visually distinct "
        "member units of one compact local assembly. At least one separate rejected "
        "baseline cluster contains only proposal(s) that explicitly represent one group "
        "covering all those same member units. Every accepted baseline cluster in the "
        "family anchors exactly one content unit; every remaining family cluster must be "
        "a rejected group-level alternative. Use whole baseline clusters and include every "
        "proposal ID from them. Do not include abstained clusters.\n\n"
        f"{HOLDING_CONTAINER_SCOPE_INSTRUCTION}"
        "This is a graph partition conflict, not an existence dispute or ordinary duplicate. "
        "Do not form a family from a singleton, aliases for one physical instance, a broad "
        "host/support plus spatially separable content, a protected holder/item or load relation as defined above, "
        "mere proximity/containment/contact/overlap, or uncertain visual content. A group "
        "proposal must visibly span all member units. A member proposal must map exactly "
        "to its accepted anchor unit. Families must be disjoint. Exclude a doubtful case "
        "rather than stretching the definition.\n\n"
        "A passive homogeneous collection has one canonical scope: all visible passive contents of one physical category within one clearly bounded storage or display fixture, across its internal shelves, bays, rows or slots. The fixture is excluded from the content node. Internal dividers, crop, color differences, or separately localizable subgroups alone do not split this collection. Different fixtures, individually framed artwork or separately mounted complete display fixtures, heterogeneous neighbors, and objects separately handled or used during the shot remain separate. Same-role covering or control panels serving one bounded fixture use one whole-array scope, excluding that fixture, unless directly observed independent handling, use or motion warrants a split. Apply these scopes at discovery and final partition regardless of whether proposals initially used whole collections or subdivisions. A shared unbounded surface alone never establishes this organization. An excluded fixture does not trigger large_host_or_support_involved merely because internal shelves or bays separate content. A contents-only collection family must exclude its fixture; no family may include independent context. This does not prohibit a separately supported compact container-content functional scope under the shared rule. Map the complete canonical content scope before final candidate judging; never select a convenient subgroup.\n\n"
        "For every family, classify every scope proposal exactly once as group or member. "
        "Every group role covers all unit IDs; every member role covers exactly the unit "
        "anchored by its accepted baseline cluster. Every rejected alternative must already "
        "carry the structured group_member_conflict uncertainty flag. For each group role, "
        "provide same_content_evidence separately for every accepted member anchor. Each "
        "record must name that member's unit_id and anchor_cluster_id and cite an original "
        "frame where the group proposal and all accepted units are visible. The description "
        "must explain how this particular anchor's bounded content is covered without "
        "absorbing adjacent context; a generic statement such as 'spans all members' is "
        "insufficient. The evidence records must collectively cover every member anchor. "
        "Member roles must use an empty evidence list. Detector boxes are only low-trust "
        "location hints. A deterministic fail-closed firewall may use boxes only to reject "
        "irreversible coarsening when a claimed group track remains non-containing and "
        "nearly disjoint from every sufficiently co-visible proposal track of a member "
        "anchor over multiple frames. Missing boxes, one-frame disagreement, or occasional "
        "localization drift do not trigger it; geometry never proves a family or an entity.\n\n"
        "Record independence_witnesses only for direct shot-observed separate handling/use, "
        "detachment or a visibly standalone state, relative motion, or an independent "
        "trajectory. Each witness names exactly one separated_unit_id and one "
        "contrast_unit_id whose pairwise graph-node separation that observation directly "
        "proves; both units must be visible in every cited frame. A standalone-state "
        "witness must show observable detachment or state change, not merely a static "
        "constituent boundary. Use separate witness records for separate member boundaries. Static "
        "boundaries, separate names/materials/colors, theoretical "
        "removability, abstract function, proposal repetition, and visible separability "
        "alone are not witnesses. A downstream deterministic resolver uses the coarsest "
        "group partition only when no independence witness exists, retains all members "
        "when every pairwise boundary is justified, and fails closed to the frozen "
        "baseline when independence evidence is only partial. Detector provenance and "
        "counts are audit metadata only and never select either partition. A separate "
        "isolated planner receives the same role inputs; downstream coarsening requires "
        "exact agreement on frozen family scope, member anchors, and the group partition. "
        "You cannot see or predict the other plan. The planner itself selects nothing "
        "and has no naming authority.\n\n"
        "Chronological attachment mapping:\n"
        + json.dumps(shot_manifest["reference_frames"], indent=2)
        + "\n\nAllowed input paths:\n"
        + json.dumps(allowed_paths, indent=2)
        + "\n\nThe embedded Skill and references define entity scope and the physical-"
        "identity versus graph-partition distinction. Their source-blinding, single-shot, "
        "low-trust-box, compact-assembly, large-host, and observed-independence rules remain "
        "authoritative. This narrow planner overrides only their normal instruction to emit "
        "a complete adjudication ledger:\n"
        + skill_text
        + "\n\nsource_blind_anonymous_candidates:\n"
        + json.dumps(anonymous_view, indent=2, ensure_ascii=False)
        + "\n\nfrozen_source_blind_baseline_adjudication:\n"
        + json.dumps(baseline, indent=2, ensure_ascii=False)
    )


def _validate_evidence_frames(
    evidence: Sequence[Mapping[str, Any]], valid_frame_ids: set[int], label: str
) -> None:
    for item in evidence:
        if item["frame_id"] not in valid_frame_ids:
            raise FamilyPlanError(f"{label} cites unknown frame {item['frame_id']}")


def _proposal_visible_boxes(
    proposal: Mapping[str, Any],
) -> Dict[int, Tuple[float, float, float, float]]:
    """Return only valid visible boxes; absent or malformed geometry is non-evidence."""
    result: Dict[int, Tuple[float, float, float, float]] = {}
    for item in proposal.get("frame_presence", []):
        if item.get("status") != "visible":
            continue
        bbox = item.get("bbox_xyxy_normalized")
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue
        if any(not isinstance(value, (int, float)) for value in bbox):
            continue
        x1, y1, x2, y2 = (float(value) for value in bbox)
        if not (0.0 <= x1 < x2 <= 1.0 and 0.0 <= y1 < y2 <= 1.0):
            continue
        result[int(item["frame_id"])] = (x1, y1, x2, y2)
    return result


def _box_intersection_metrics(
    first: Tuple[float, float, float, float],
    second: Tuple[float, float, float, float],
) -> Tuple[float, float]:
    x1 = max(first[0], second[0])
    y1 = max(first[1], second[1])
    x2 = min(first[2], second[2])
    y2 = min(first[3], second[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    first_area = (first[2] - first[0]) * (first[3] - first[1])
    second_area = (second[2] - second[0]) * (second[3] - second[1])
    union = first_area + second_area - intersection
    iou = intersection / union if union > 0.0 else 0.0
    smaller_area = min(first_area, second_area)
    intersection_over_smaller = (
        intersection / smaller_area if smaller_area > 0.0 else 0.0
    )
    return iou, intersection_over_smaller


def _proposal_track_spatial_audit(
    group_proposal: Mapping[str, Any],
    member_proposal: Mapping[str, Any],
) -> Dict[str, Any]:
    """Audit one group/member track pair without treating boxes as positive proof."""
    group_boxes = _proposal_visible_boxes(group_proposal)
    member_boxes = _proposal_visible_boxes(member_proposal)
    common_frame_ids = sorted(set(group_boxes) & set(member_boxes))
    frame_audit = []
    incompatible_count = 0
    for frame_id in common_frame_ids:
        iou, intersection_over_smaller = _box_intersection_metrics(
            group_boxes[frame_id], member_boxes[frame_id]
        )
        incompatible = (
            iou <= GROSS_SPATIAL_MAX_IOU
            and intersection_over_smaller <= GROSS_SPATIAL_MAX_INTERSECTION_OVER_SMALLER
        )
        incompatible_count += int(incompatible)
        frame_audit.append(
            {
                "frame_id": frame_id,
                "iou": round(iou, 6),
                "intersection_over_smaller": round(intersection_over_smaller, 6),
                "grossly_incompatible": incompatible,
            }
        )
    required_count = max(
        GROSS_SPATIAL_MIN_COVISIBLE_FRAMES,
        math.ceil(len(common_frame_ids) * GROSS_SPATIAL_MIN_INCOMPATIBLE_RATIO),
    )
    sufficiently_comparable = (
        len(common_frame_ids) >= GROSS_SPATIAL_MIN_COVISIBLE_FRAMES
    )
    return {
        "group_proposal_id": group_proposal["anonymous_proposal_id"],
        "member_proposal_id": member_proposal["anonymous_proposal_id"],
        "common_frame_ids": common_frame_ids,
        "frame_audit": frame_audit,
        "incompatible_frame_count": incompatible_count,
        "required_incompatible_frame_count": required_count,
        "sufficiently_comparable": sufficiently_comparable,
        "persistently_incompatible": (
            sufficiently_comparable and incompatible_count >= required_count
        ),
    }


def audit_gross_spatial_incompatibility(
    family: Mapping[str, Any],
    *,
    baseline_by_id: Mapping[str, Mapping[str, Any]],
    proposal_by_id: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    """Find repeated contradictions that invalidate an exact group witness.

    A clean audit cannot establish same content or authorize a merge. An invalid
    group track says nothing about mutual compatibility of the member anchors.
    """
    role_by_id = {item["proposal_id"]: item for item in family["proposal_roles"]}
    group_proposal_ids = sorted(
        proposal_id
        for proposal_id, role in role_by_id.items()
        if role["role"] == "group"
    )
    blockers = []
    for group_proposal_id in group_proposal_ids:
        group_proposal = proposal_by_id[group_proposal_id]
        for unit in family["content_units"]:
            anchor_id = unit["anchor_cluster_id"]
            track_audits = [
                _proposal_track_spatial_audit(
                    group_proposal, proposal_by_id[member_proposal_id]
                )
                for member_proposal_id in baseline_by_id[anchor_id][
                    "anonymous_proposal_ids"
                ]
            ]
            comparable = [
                item for item in track_audits if item["sufficiently_comparable"]
            ]
            if comparable and all(
                item["persistently_incompatible"] for item in comparable
            ):
                blockers.append(
                    {
                        "family_id": family["family_id"],
                        "group_proposal_id": group_proposal_id,
                        "unit_id": unit["unit_id"],
                        "member_anchor_cluster_id": anchor_id,
                        "comparable_track_audits": comparable,
                        "insufficiently_comparable_member_proposal_ids": sorted(
                            item["member_proposal_id"]
                            for item in track_audits
                            if not item["sufficiently_comparable"]
                        ),
                    }
                )
    return {
        "policy": "veto_only_never_positive_group_evidence",
        "thresholds": {
            "minimum_covisible_frames_per_track": (GROSS_SPATIAL_MIN_COVISIBLE_FRAMES),
            "minimum_incompatible_frame_ratio": (GROSS_SPATIAL_MIN_INCOMPATIBLE_RATIO),
            "maximum_iou": GROSS_SPATIAL_MAX_IOU,
            "maximum_intersection_over_smaller": (
                GROSS_SPATIAL_MAX_INTERSECTION_OVER_SMALLER
            ),
        },
        "blocking_incompatibilities": blockers,
    }


def collect_spatial_vetoes(
    plans: Sequence[Mapping[str, Any] | None], *,
    baseline: Mapping[str, Any], anonymous_view: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    """Invalidate only the exact group witness contradicted by member tracks.

    G versus A does not establish a spatial relation between A and B. Retain
    the complete diagnostic without manufacturing an anchor-pair prohibition.
    """
    baseline_by_id = {c["cluster_id"]: c for c in baseline["clusters"]}
    proposal_by_id = {p["anonymous_proposal_id"]: p for p in anonymous_view["proposals"]}
    vetoes = []
    for planner_index, plan in enumerate(plans, start=1):
        if plan is None:
            continue
        for family in plan["families"]:
            audit = audit_gross_spatial_incompatibility(
                family, baseline_by_id=baseline_by_id, proposal_by_id=proposal_by_id,
            )
            for blocker in audit["blocking_incompatibilities"]:
                vetoes.append({
                    "kind": "group_witness_invalid",
                    "planner_index": planner_index,
                    "family_id": family["family_id"],
                    "group_proposal_id": blocker["group_proposal_id"],
                    "member_anchor_cluster_id": blocker["member_anchor_cluster_id"],
                    "anchor_cluster_ids": sorted(
                        u["anchor_cluster_id"] for u in family["content_units"]
                    ),
                    "blocked_anchor_pairs": [],
                    "conflicting_frame_ids": sorted({
                        item["frame_id"] for track in blocker["comparable_track_audits"]
                        for item in track["frame_audit"] if item["grossly_incompatible"]
                    }),
                    "deterministic_audit": {
                        **audit, "blocking_incompatibilities": [blocker],
                    },
                })
    return vetoes


def matching_spatial_vetoes(
    anchor_cluster_ids: Iterable[str], spatial_vetoes: Sequence[Mapping[str, Any]],
    *, group_proposal_ids: Iterable[str] = (),
) -> List[Dict[str, Any]]:
    """Match witness invalidity only when that exact witness is being used.

    Explicit legacy anchor-pair constraints remain fail-closed for callers
    supplying them, but collect_spatial_vetoes never derives such constraints.
    Accepted-only judgments do not use rejected group proposals.
    """
    anchors, groups = set(anchor_cluster_ids), set(group_proposal_ids)
    return [copy.deepcopy(dict(veto)) for veto in spatial_vetoes if (
        veto.get("kind") == "group_witness_invalid"
        and veto["group_proposal_id"] in groups
        and veto["member_anchor_cluster_id"] in anchors
    ) or (
        veto.get("kind") != "group_witness_invalid"
        and any(set(pair) <= anchors for pair in veto.get("blocked_anchor_pairs", []))
    )]


def validate_family_plan(
    plan: Mapping[str, Any],
    *,
    shot_id: str,
    baseline: Mapping[str, Any],
    anonymous_view: Mapping[str, Any],
    valid_frame_ids: Sequence[int],
    base_protocol: str,
) -> None:
    """Validate a source-blind coarsening plan with frozen accepted anchors."""
    if not isinstance(base_protocol, str) or not base_protocol:
        raise FamilyPlanError("base_protocol must be a nonempty string")
    if baseline.get("protocol_version") != base_protocol:
        raise FamilyPlanError("Baseline changed base protocol_version")
    if baseline.get("shot_id") != shot_id:
        raise FamilyPlanError("Baseline changed shot_id")
    if anonymous_view.get("protocol_version") != base_protocol:
        raise FamilyPlanError("Anonymous proposal view changed base protocol_version")
    if plan.get("protocol_version") != FAMILY_PLAN_PROTOCOL:
        raise FamilyPlanError("Unexpected family-plan protocol_version")
    if plan.get("shot_id") != shot_id:
        raise FamilyPlanError("Family plan changed shot_id")
    if anonymous_view.get("shot_id") != shot_id:
        raise FamilyPlanError("Anonymous proposal view changed shot_id")

    valid_frames = set(valid_frame_ids)
    if len(valid_frames) != len(valid_frame_ids):
        raise FamilyPlanError("Reference frame IDs are not unique")
    proposal_id_values = [
        item["anonymous_proposal_id"] for item in anonymous_view["proposals"]
    ]
    proposal_ids = _require_unique(
        proposal_id_values,
        "anonymous proposal IDs",
    )
    baseline_by_id = {
        cluster["cluster_id"]: cluster for cluster in baseline["clusters"]
    }
    if len(baseline_by_id) != len(baseline["clusters"]):
        raise FamilyPlanError("Baseline contains duplicate cluster IDs")
    eligible_group_alternatives = _eligible_group_alternative_ids(baseline)
    reviewed_group_alternatives = _require_unique(
        plan["reviewed_group_alternative_cluster_ids"],
        "reviewed group-alternative cluster IDs",
    )
    if reviewed_group_alternatives != eligible_group_alternatives:
        missing = sorted(eligible_group_alternatives - reviewed_group_alternatives)
        extra = sorted(reviewed_group_alternatives - eligible_group_alternatives)
        raise FamilyPlanError(
            "reviewed_group_alternative_cluster_ids must cover every and only "
            "rejected group_member_conflict cluster exactly once; "
            f"missing={missing}, extra={extra}"
        )
    excluded_records = plan["excluded_group_alternatives"]
    excluded_group_alternatives = _require_unique(
        [item["cluster_id"] for item in excluded_records],
        "excluded group-alternative cluster IDs",
    )
    unknown_exclusions = excluded_group_alternatives - eligible_group_alternatives
    if unknown_exclusions:
        raise FamilyPlanError(
            "excluded_group_alternatives contains ineligible clusters: "
            f"{sorted(unknown_exclusions)}"
        )
    accepted_resolved_ids = {
        cluster_id
        for cluster_id, cluster in baseline_by_id.items()
        if cluster["decision"] == "accept"
        and cluster["identity_status"] == "resolved"
        and cluster["final_entity"] is not None
    }
    for item in excluded_records:
        reason_code = item["reason_code"]
        if reason_code not in GROUP_ALTERNATIVE_EXCLUSION_REASON_CODES:
            raise FamilyPlanError(
                "excluded_group_alternatives contains an unknown reason_code: "
                f"{reason_code}"
            )
        if not isinstance(item["reason"], str) or not item["reason"].strip():
            raise FamilyPlanError(
                "excluded_group_alternatives reasons must be nonempty"
            )
        candidate_ids = _require_unique(
            item["candidate_member_anchor_cluster_ids"],
            f"{item['cluster_id']} candidate member-anchor cluster IDs",
        )
        context_ids = _require_unique(
            item["independent_context_anchor_cluster_ids"],
            f"{item['cluster_id']} independent-context anchor cluster IDs",
        )
        if not candidate_ids <= accepted_resolved_ids:
            raise FamilyPlanError(
                f"{item['cluster_id']}: candidate member anchors must be "
                "accepted and resolved"
            )
        if not context_ids <= candidate_ids:
            raise FamilyPlanError(
                f"{item['cluster_id']}: independent context anchors must be a "
                "subset of candidate member anchors"
            )
        if (
            not candidate_ids
            and reason_code not in EMPTY_CANDIDATE_ANCHOR_REASON_CODES
        ):
            raise FamilyPlanError(
                f"{item['cluster_id']}: candidate member anchors may be empty "
                "only for an unresolvable group scope or an explicit "
                "insufficient_supported_member_anchors no-op exclusion"
            )
        if context_ids and reason_code != "contains_independently_graph_worthy_context":
            raise FamilyPlanError(
                f"{item['cluster_id']}: nonempty independent context requires "
                "contains_independently_graph_worthy_context"
            )
        if (
            reason_code == "contains_independently_graph_worthy_context"
            and not context_ids
        ):
            raise FamilyPlanError(
                f"{item['cluster_id']}: independently graph-worthy context "
                "reason requires at least one context anchor"
            )
    _require_unique([family["family_id"] for family in plan["families"]], "family IDs")

    used_baseline_clusters: set[str] = set()
    used_proposals: set[str] = set()
    family_group_alternatives: set[str] = set()
    for family in plan["families"]:
        family_id = family["family_id"]
        baseline_ids = _require_unique(
            family["baseline_cluster_ids"], f"{family_id} baseline cluster IDs"
        )
        unknown_clusters = baseline_ids - set(baseline_by_id)
        if unknown_clusters:
            raise FamilyPlanError(
                f"{family_id}: unknown baseline clusters {sorted(unknown_clusters)}"
            )
        overlap = used_baseline_clusters & baseline_ids
        if overlap:
            raise FamilyPlanError(
                f"{family_id}: overlaps another family at {sorted(overlap)}"
            )
        used_baseline_clusters.update(baseline_ids)

        expected_scope = set().union(
            *(
                _cluster_proposal_ids(baseline_by_id[cluster_id])
                for cluster_id in baseline_ids
            )
        )
        scope = _require_unique(
            family["scope_proposal_ids"], f"{family_id} scope proposal IDs"
        )
        if scope != expected_scope:
            raise FamilyPlanError(
                f"{family_id}: scope must equal whole baseline-cluster union"
            )
        if not scope <= proposal_ids:
            raise FamilyPlanError(f"{family_id}: scope contains unknown proposals")
        proposal_overlap = used_proposals & scope
        if proposal_overlap:
            raise FamilyPlanError(
                f"{family_id}: proposals overlap another family {sorted(proposal_overlap)}"
            )
        used_proposals.update(scope)

        units = family["content_units"]
        unit_ids = _require_unique(
            [unit["unit_id"] for unit in units],
            f"{family_id} content unit IDs",
        )
        anchor_ids = _require_unique(
            [unit["anchor_cluster_id"] for unit in units],
            f"{family_id} anchor cluster IDs",
        )
        anchor_by_unit = {
            unit["unit_id"]: baseline_by_id[unit["anchor_cluster_id"]] for unit in units
        }
        visible_frames_by_unit = {
            unit_id: {
                item["frame_id"]
                for item in cluster["frame_presence"]
                if item["status"] == "visible"
            }
            for unit_id, cluster in anchor_by_unit.items()
        }
        jointly_visible_family_frames = set.intersection(
            *(set(value) for value in visible_frames_by_unit.values())
        )
        accepted_ids = {
            cluster_id
            for cluster_id in baseline_ids
            if baseline_by_id[cluster_id]["decision"] == "accept"
        }
        if anchor_ids != accepted_ids:
            raise FamilyPlanError(
                f"{family_id}: content units must anchor every and only accepted "
                "baseline cluster in the family"
            )
        for unit in units:
            cluster = baseline_by_id[unit["anchor_cluster_id"]]
            if (
                cluster["identity_status"] != "resolved"
                or cluster["final_entity"] is None
            ):
                raise FamilyPlanError(
                    f"{family_id}/{unit['unit_id']}: anchor is not accepted and resolved"
                )
            _validate_evidence_frames(
                unit["evidence"], valid_frames, f"{family_id}/{unit['unit_id']}"
            )
            if (
                not {item["frame_id"] for item in unit["evidence"]}
                <= visible_frames_by_unit[unit["unit_id"]]
            ):
                raise FamilyPlanError(
                    f"{family_id}/{unit['unit_id']}: content-unit evidence must "
                    "come from frames where its frozen anchor is visible"
                )
        nonanchor_ids = baseline_ids - anchor_ids
        if not nonanchor_ids or any(
            baseline_by_id[cluster_id]["decision"] != "reject"
            for cluster_id in nonanchor_ids
        ):
            raise FamilyPlanError(
                f"{family_id}: non-anchor alternatives must be rejected group clusters"
            )
        for cluster_id in nonanchor_ids:
            cluster = baseline_by_id[cluster_id]
            if "group_member_conflict" not in cluster["uncertainty_flags"]:
                raise FamilyPlanError(
                    f"{family_id}/{cluster_id}: rejected alternative was not "
                    "frozen as a group/member partition conflict"
                )
        family_group_alternatives.update(nonanchor_ids)
        _validate_evidence_frames(
            family["same_content_evidence"], valid_frames, family_id
        )
        if (
            not {item["frame_id"] for item in family["same_content_evidence"]}
            <= jointly_visible_family_frames
        ):
            raise FamilyPlanError(
                f"{family_id}: every same-content evidence frame must show all "
                "accepted content units visible"
            )

        roles = family["proposal_roles"]
        role_ids = _require_unique(
            [item["proposal_id"] for item in roles],
            f"{family_id} proposal roles",
        )
        if role_ids != scope:
            raise FamilyPlanError(
                f"{family_id}: proposal_roles must cover scope exactly once"
            )
        role_by_id = {item["proposal_id"]: item for item in roles}
        anchor_id_by_unit = {
            unit["unit_id"]: unit["anchor_cluster_id"] for unit in units
        }
        group_proposal_ids: set[str] = set()
        member_proposal_ids: set[str] = set()
        for role in roles:
            covers = _require_unique(
                role["covers_unit_ids"],
                f"{family_id}/{role['proposal_id']} covered units",
            )
            if not covers <= unit_ids:
                raise FamilyPlanError(
                    f"{family_id}/{role['proposal_id']}: unknown covered unit"
                )
            if role["role"] == "group":
                if covers != unit_ids:
                    raise FamilyPlanError(
                        f"{family_id}/{role['proposal_id']}: group must cover all units"
                    )
                if not role["same_content_evidence"]:
                    raise FamilyPlanError(
                        f"{family_id}/{role['proposal_id']}: group role needs "
                        "direct same-content evidence"
                    )
                evidence_by_unit: Dict[str, List[Mapping[str, Any]]] = {}
                for evidence in role["same_content_evidence"]:
                    evidence_unit_id = evidence["unit_id"]
                    if evidence_unit_id not in unit_ids:
                        raise FamilyPlanError(
                            f"{family_id}/{role['proposal_id']}: group evidence "
                            "cites an unknown content unit"
                        )
                    if (
                        evidence["anchor_cluster_id"]
                        != anchor_id_by_unit[evidence_unit_id]
                    ):
                        raise FamilyPlanError(
                            f"{family_id}/{role['proposal_id']}: group evidence "
                            "must name the exact accepted anchor for its unit"
                        )
                    evidence_by_unit.setdefault(evidence_unit_id, []).append(evidence)
                if set(evidence_by_unit) != unit_ids:
                    raise FamilyPlanError(
                        f"{family_id}/{role['proposal_id']}: group same-content "
                        "evidence must cover every member anchor separately"
                    )
                _validate_evidence_frames(
                    role["same_content_evidence"],
                    valid_frames,
                    f"{family_id}/{role['proposal_id']}",
                )
                if (
                    not {item["frame_id"] for item in role["same_content_evidence"]}
                    <= jointly_visible_family_frames
                ):
                    raise FamilyPlanError(
                        f"{family_id}/{role['proposal_id']}: every group evidence "
                        "frame must show all content units visible"
                    )
                group_proposal_ids.add(role["proposal_id"])
            else:
                if len(covers) != 1:
                    raise FamilyPlanError(
                        f"{family_id}/{role['proposal_id']}: member must cover one unit"
                    )
                if role["same_content_evidence"]:
                    raise FamilyPlanError(
                        f"{family_id}/{role['proposal_id']}: member role must not "
                        "claim group same-content evidence"
                    )
                member_proposal_ids.add(role["proposal_id"])
        if not group_proposal_ids or len(member_proposal_ids) < 2:
            raise FamilyPlanError(
                f"{family_id}: needs group evidence and at least two member proposals"
            )

        for unit in units:
            anchor = baseline_by_id[unit["anchor_cluster_id"]]
            for proposal_id in anchor["anonymous_proposal_ids"]:
                role = role_by_id[proposal_id]
                if role["role"] != "member" or set(role["covers_unit_ids"]) != {
                    unit["unit_id"]
                }:
                    raise FamilyPlanError(
                        f"{family_id}: accepted anchor proposals must map exactly "
                        f"to {unit['unit_id']}"
                    )
        for cluster_id in nonanchor_ids:
            for proposal_id in baseline_by_id[cluster_id]["anonymous_proposal_ids"]:
                if role_by_id[proposal_id]["role"] != "group":
                    raise FamilyPlanError(
                        f"{family_id}: rejected alternative contains a member proposal"
                    )
        # Geometry vetoes coarsening later; validate all remaining structure now.
        _require_unique(
            [item["witness_id"] for item in family["independence_witnesses"]],
            f"{family_id} witness IDs",
        )
        for witness in family["independence_witnesses"]:
            separated_unit = witness["separated_unit_id"]
            contrast_unit = witness["contrast_unit_id"]
            witness_frames = _require_unique(
                [str(value) for value in witness["frame_ids"]],
                f"{family_id}/{witness['witness_id']} frames",
            )
            if separated_unit not in unit_ids or contrast_unit not in unit_ids:
                raise FamilyPlanError(f"{family_id}: witness cites unknown unit")
            if separated_unit == contrast_unit:
                raise FamilyPlanError(
                    f"{family_id}: witness cannot contrast a unit with itself"
                )
            if not {int(value) for value in witness_frames} <= valid_frames:
                raise FamilyPlanError(f"{family_id}: witness cites unknown frame")
            if (
                witness["kind"] in {"relative_motion", "independent_trajectory"}
                and len(witness_frames) < 2
            ):
                raise FamilyPlanError(
                    f"{family_id}: motion/trajectory witness needs at least two frames"
                )
            jointly_visible = (
                visible_frames_by_unit[separated_unit]
                & visible_frames_by_unit[contrast_unit]
            )
            if not {int(value) for value in witness_frames} <= jointly_visible:
                raise FamilyPlanError(
                    f"{family_id}: witness frames must show both contrasted units visible"
                )

    multiply_accounted = family_group_alternatives & excluded_group_alternatives
    if multiply_accounted:
        raise FamilyPlanError(
            "A group alternative cannot appear in both a family and an exclusion: "
            f"{sorted(multiply_accounted)}"
        )
    accounted_group_alternatives = (
        family_group_alternatives | excluded_group_alternatives
    )
    if accounted_group_alternatives != eligible_group_alternatives:
        missing = sorted(eligible_group_alternatives - accounted_group_alternatives)
        extra = sorted(accounted_group_alternatives - eligible_group_alternatives)
        raise FamilyPlanError(
            "Every reviewed group alternative must appear exactly once as a "
            "family non-anchor or structured exclusion; "
            f"missing={missing}, extra={extra}"
        )


def validate_source_map(
    source_map: Mapping[str, Any],
    *,
    shot_id: str,
    proposal_ids: set[str],
    detector_ids: Sequence[str],
    anonymous_view: Mapping[str, Any],
    detector_ledgers: Sequence[Mapping[str, Any]],
    base_protocol: str,
) -> None:
    if not isinstance(base_protocol, str) or not base_protocol:
        raise FamilyPlanError("base_protocol must be a nonempty string")
    if source_map.get("protocol_version") != base_protocol:
        raise FamilyPlanError("Private source map changed protocol_version")
    if source_map.get("shot_id") != shot_id:
        raise FamilyPlanError("Private source map changed shot_id")
    if anonymous_view.get("protocol_version") != base_protocol:
        raise FamilyPlanError("Anonymous proposal view changed base protocol_version")
    if anonymous_view.get("shot_id") != shot_id:
        raise FamilyPlanError("Anonymous proposal view changed shot_id")
    mappings = source_map.get("mappings")
    if not isinstance(mappings, list):
        raise FamilyPlanError("Private source map has no mappings list")
    mapped_ids = _require_unique(
        [item["anonymous_proposal_id"] for item in mappings],
        "private source-map proposal IDs",
    )
    if mapped_ids != proposal_ids:
        raise FamilyPlanError("Private source map does not exactly cover proposals")
    allowed_sources = set(detector_ids)
    if len(allowed_sources) != len(detector_ids) or len(allowed_sources) < 2:
        raise FamilyPlanError(
            "Detector IDs must be unique and contain at least two panels"
        )
    if any(not DETECTOR_ID_PATTERN.fullmatch(value) for value in allowed_sources):
        raise FamilyPlanError("Unexpected detector ID format")
    for item in mappings:
        if item.get("source_kind") != "detector":
            raise FamilyPlanError("Source map contains a non-detector proposal")
        if item.get("source") not in allowed_sources:
            raise FamilyPlanError("Source map contains an unknown detector")
        if not isinstance(item.get("local_id"), str) or not item["local_id"]:
            raise FamilyPlanError("Source map contains an invalid local_id")

    ledger_entities: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for ledger in detector_ledgers:
        detector_id = str(ledger["detector_id"])
        for entity in ledger["entities"]:
            key = (detector_id, str(entity["local_id"]))
            if key in ledger_entities:
                raise FamilyPlanError(f"Duplicate detector/local proposal key: {key}")
            ledger_entities[key] = {field: entity[field] for field in PROPOSAL_FIELDS}
    mapped_keys = {(str(item["source"]), str(item["local_id"])) for item in mappings}
    if len(mapped_keys) != len(mappings) or mapped_keys != set(ledger_entities):
        raise FamilyPlanError(
            "Private source map does not exactly cover detector/local proposal keys"
        )
    proposal_by_id = {
        item["anonymous_proposal_id"]: item for item in anonymous_view["proposals"]
    }
    for item in mappings:
        proposal_id = item["anonymous_proposal_id"]
        expected = ledger_entities[(item["source"], item["local_id"])]
        observed = {
            field: proposal_by_id[proposal_id][field] for field in PROPOSAL_FIELDS
        }
        if observed != expected:
            raise FamilyPlanError(
                f"Anonymous proposal payload does not match source ledger: {proposal_id}"
            )


def build_panel_positions(
    plan: Mapping[str, Any],
    source_map: Mapping[str, Any],
    detector_ids: Sequence[str] | None = None,
) -> Dict[str, Any]:
    """Derive one eligibility position per detector and family."""
    source_by_proposal = {
        item["anonymous_proposal_id"]: item["source"] for item in source_map["mappings"]
    }
    if detector_ids is None:
        detector_ids = sorted(set(source_by_proposal.values()))
    positions = []
    for family in plan["families"]:
        family_id = family["family_id"]
        unit_ids = {item["unit_id"] for item in family["content_units"]}
        role_by_proposal = {
            item["proposal_id"]: item for item in family["proposal_roles"]
        }
        ballots = []
        for detector_id in detector_ids:
            detector_proposals = sorted(
                proposal_id
                for proposal_id in family["scope_proposal_ids"]
                if source_by_proposal.get(proposal_id) == detector_id
            )
            group_ids = [
                proposal_id
                for proposal_id in detector_proposals
                if role_by_proposal[proposal_id]["role"] == "group"
            ]
            member_ids = [
                proposal_id
                for proposal_id in detector_proposals
                if role_by_proposal[proposal_id]["role"] == "member"
            ]
            member_union = {
                role_by_proposal[proposal_id]["covers_unit_ids"][0]
                for proposal_id in member_ids
            }
            complete_members = len(member_ids) >= 2 and member_union == unit_ids
            if group_ids and member_ids:
                status = "mixed"
            elif group_ids:
                status = "group"
            elif complete_members:
                status = "members"
            elif not detector_proposals:
                status = "no_vote"
            else:
                status = "partial"
            ballots.append(
                {
                    "detector_id": detector_id,
                    "status": status,
                    "proposal_ids": detector_proposals,
                    "group_proposal_ids": group_ids,
                    "member_proposal_ids": member_ids,
                }
            )
        positions.append({"family_id": family_id, "ballots": ballots})
    return {
        "protocol_version": FAMILY_PLAN_PROTOCOL,
        "shot_id": plan["shot_id"],
        "positions": positions,
    }


def _select_resolutions(
    plan: Mapping[str, Any],
    panel_positions: Mapping[str, Any] | None = None,
    *, spatial_vetoes: Sequence[Mapping[str, Any]] = (),
) -> List[Dict[str, Any]]:
    """Select partitions from shot evidence; panel provenance is audit-only."""
    positions_by_family = (
        {item["family_id"]: item for item in panel_positions.get("positions", [])}
        if panel_positions is not None
        else {}
    )
    resolutions = []
    for family in plan["families"]:
        family_id = family["family_id"]
        ballots = positions_by_family.get(family_id, {}).get("ballots", [])
        group_panels = [
            item["detector_id"] for item in ballots if item["status"] == "group"
        ]
        member_panels = [
            item["detector_id"] for item in ballots if item["status"] == "members"
        ]
        witnesses = family["independence_witnesses"]
        unit_ids = sorted(item["unit_id"] for item in family["content_units"])
        required_edges = {tuple(sorted(pair)) for pair in combinations(unit_ids, 2)}
        witnessed_edges = {
            tuple(
                sorted(
                    (
                        witness["separated_unit_id"],
                        witness["contrast_unit_id"],
                    )
                )
            )
            for witness in witnesses
        }
        if required_edges and required_edges <= witnessed_edges:
            status = "kept_baseline"
            selected_kind = "members"
            basis = "all_member_boundaries_have_typed_shot_observed_witnesses"
        elif witnessed_edges:
            status = "kept_baseline"
            selected_kind = "members"
            basis = "partial_independence_evidence_fail_closed_to_baseline"
        else:
            status = "applied"
            selected_kind = "group"
            basis = "coarsest_stable_partition_default"
        vetoes = matching_spatial_vetoes(
            (unit["anchor_cluster_id"] for unit in family["content_units"]), spatial_vetoes,
            group_proposal_ids=(r["proposal_id"] for r in family["proposal_roles"] if r["role"] == "group"),
        )
        if vetoes:
            status, selected_kind = "kept_baseline", "members"
            basis = "gross_spatial_incompatibility_veto"
        resolutions.append(
            {
                **({"spatial_vetoes": vetoes} if vetoes else {}),
                "family_id": family_id,
                "status": status,
                "selected_kind": selected_kind,
                "basis": basis,
                "observed_witness_ids": [item["witness_id"] for item in witnesses],
                "decisive_witness_ids": (
                    [item["witness_id"] for item in witnesses]
                    if selected_kind == "members"
                    else []
                ),
                "group_panel_ids": group_panels,
                "member_panel_ids": member_panels,
            }
        )
    return resolutions


def _family_signature_payload(family: Mapping[str, Any]) -> Dict[str, List[str]]:
    """Return one planner-local-ID-independent family structure."""
    return {
        "baseline_cluster_ids": sorted(family["baseline_cluster_ids"]),
        "scope_proposal_ids": sorted(family["scope_proposal_ids"]),
        "member_anchor_cluster_ids": sorted(
            unit["anchor_cluster_id"] for unit in family["content_units"]
        ),
    }


def _family_signature(
    family: Mapping[str, Any],
) -> Tuple[Tuple[str, ...], Tuple[str, ...], Tuple[str, ...]]:
    payload = _family_signature_payload(family)
    return (
        tuple(payload["baseline_cluster_ids"]),
        tuple(payload["scope_proposal_ids"]),
        tuple(payload["member_anchor_cluster_ids"]),
    )


def _signature_payload_from_key(
    signature: Tuple[Tuple[str, ...], Tuple[str, ...], Tuple[str, ...]],
) -> Dict[str, List[str]]:
    return {
        "baseline_cluster_ids": list(signature[0]),
        "scope_proposal_ids": list(signature[1]),
        "member_anchor_cluster_ids": list(signature[2]),
    }


def _signature_from_resolution(
    resolution: Mapping[str, Any],
) -> Tuple[Tuple[str, ...], Tuple[str, ...], Tuple[str, ...]]:
    return (
        tuple(resolution["baseline_cluster_ids"]),
        tuple(resolution["scope_proposal_ids"]),
        tuple(resolution["member_anchor_cluster_ids"]),
    )


def _signatures_overlap(
    first: Tuple[Tuple[str, ...], Tuple[str, ...], Tuple[str, ...]],
    second: Tuple[Tuple[str, ...], Tuple[str, ...], Tuple[str, ...]],
) -> bool:
    return any(set(first[index]) & set(second[index]) for index in range(3))


def _select_consensus_resolutions(
    first_plan: Mapping[str, Any], second_plan: Mapping[str, Any],
    *, spatial_vetoes: Sequence[Mapping[str, Any]] = (),
) -> List[Dict[str, Any]]:
    """Require exact two-planner agreement before coarsening a family.

    Planner-local family/unit/witness IDs and free-text evidence are ignored.
    Frozen family scope, accepted member anchors, and the deterministic
    group/members partition must all match. A valid disagreement is a
    conservative successful no-op on the frozen baseline.
    """
    for label, plan in (("first", first_plan), ("second", second_plan)):
        if plan.get("protocol_version") != FAMILY_PLAN_PROTOCOL:
            raise FamilyPlanError(f"{label} plan has the wrong protocol")
    if first_plan.get("shot_id") != second_plan.get("shot_id"):
        raise FamilyPlanError("Planner shot IDs differ")

    grouped_by_plan: List[
        Dict[
            Tuple[Tuple[str, ...], Tuple[str, ...], Tuple[str, ...]],
            List[Tuple[Mapping[str, Any], Mapping[str, Any]]],
        ]
    ] = []
    all_signatures: set[Tuple[Tuple[str, ...], Tuple[str, ...], Tuple[str, ...]]] = (
        set()
    )
    for plan in (first_plan, second_plan):
        resolutions = _select_resolutions(plan, spatial_vetoes=spatial_vetoes)
        resolution_by_family_id = {item["family_id"]: item for item in resolutions}
        if len(resolution_by_family_id) != len(resolutions):
            raise FamilyPlanError("A planner produced duplicate family IDs")
        grouped: Dict[
            Tuple[Tuple[str, ...], Tuple[str, ...], Tuple[str, ...]],
            List[Tuple[Mapping[str, Any], Mapping[str, Any]]],
        ] = {}
        for family in plan["families"]:
            signature = _family_signature(family)
            grouped.setdefault(signature, []).append(
                (family, resolution_by_family_id[family["family_id"]])
            )
            all_signatures.add(signature)
        grouped_by_plan.append(grouped)

    conflicted: set[Tuple[Tuple[str, ...], Tuple[str, ...], Tuple[str, ...]]] = set()
    ordered_signatures = sorted(all_signatures)
    for index, first_signature in enumerate(ordered_signatures):
        for second_signature in ordered_signatures[index + 1 :]:
            if _signatures_overlap(first_signature, second_signature):
                conflicted.update((first_signature, second_signature))
    for grouped in grouped_by_plan:
        for signature, entries in grouped.items():
            if len(entries) != 1:
                conflicted.add(signature)

    consensus = []
    for signature in ordered_signatures:
        first_entries = grouped_by_plan[0].get(signature, [])
        second_entries = grouped_by_plan[1].get(signature, [])
        first_family_ids = sorted(entry[0]["family_id"] for entry in first_entries)
        second_family_ids = sorted(entry[0]["family_id"] for entry in second_entries)
        first_partitions = sorted(
            {entry[1]["selected_kind"] for entry in first_entries}
        )
        second_partitions = sorted(
            {entry[1]["selected_kind"] for entry in second_entries}
        )
        status = "kept_baseline"
        selected_kind: str | None = None
        vetoes = matching_spatial_vetoes(
            signature[2], spatial_vetoes,
            group_proposal_ids=(
                role["proposal_id"] for family, _ in (*first_entries, *second_entries)
                for role in family["proposal_roles"] if role["role"] == "group"
            ),
        )
        if vetoes:
            selected_kind = "members"
            basis = "gross_spatial_incompatibility_veto"
        elif signature in conflicted:
            basis = "overlapping_or_nested_family_component"
        elif len(first_entries) != 1 or len(second_entries) != 1:
            basis = "missing_exact_family_or_member_set_in_one_planner"
        elif first_partitions != second_partitions:
            basis = "group_members_partition_disagreement"
        else:
            selected_kind = first_partitions[0]
            if selected_kind == "group":
                status = "applied"
                basis = "exact_two_planner_family_member_partition_consensus"
            else:
                basis = "exact_two_planner_consensus_keeps_frozen_members"
        payload = _signature_payload_from_key(signature)
        consensus.append(
            {
                **payload,
                **({"spatial_vetoes": vetoes} if vetoes else {}),
                "family_signature_sha256": _json_hash(payload),
                "status": status,
                "selected_kind": selected_kind,
                "basis": basis,
                "first_planner_family_ids": first_family_ids,
                "second_planner_family_ids": second_family_ids,
                "first_planner_partitions": first_partitions,
                "second_planner_partitions": second_partitions,
            }
        )
    return consensus


def _build_consensus_application_plan(
    first_plan: Mapping[str, Any],
    consensus_resolutions: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Project only exactly agreed group partitions into an application plan."""
    applied_signatures = {
        _signature_from_resolution(item)
        for item in consensus_resolutions
        if item["status"] == "applied" and item["selected_kind"] == "group"
    }
    families_by_signature: Dict[
        Tuple[Tuple[str, ...], Tuple[str, ...], Tuple[str, ...]],
        List[Mapping[str, Any]],
    ] = {}
    for family in first_plan["families"]:
        families_by_signature.setdefault(_family_signature(family), []).append(family)
    selected_families = []
    for signature in sorted(applied_signatures):
        matches = families_by_signature.get(signature, [])
        if len(matches) != 1:
            raise FamilyPlanError(
                "Consensus application does not map to exactly one first-planner family"
            )
        selected_families.append(copy.deepcopy(matches[0]))
    selected_group_alternative_ids = {
        cluster_id
        for family in selected_families
        for cluster_id in set(family["baseline_cluster_ids"])
        - {unit["anchor_cluster_id"] for unit in family["content_units"]}
    }
    first_exclusions = {
        item["cluster_id"]: item for item in first_plan["excluded_group_alternatives"]
    }
    first_family_by_group_alternative: Dict[str, Mapping[str, Any]] = {}
    for family in first_plan["families"]:
        anchor_ids = {unit["anchor_cluster_id"] for unit in family["content_units"]}
        for cluster_id in set(family["baseline_cluster_ids"]) - anchor_ids:
            first_family_by_group_alternative[cluster_id] = family
    application_exclusions = []
    for cluster_id in sorted(first_plan["reviewed_group_alternative_cluster_ids"]):
        if cluster_id in selected_group_alternative_ids:
            continue
        if cluster_id in first_exclusions:
            application_exclusions.append(copy.deepcopy(first_exclusions[cluster_id]))
            continue
        family = first_family_by_group_alternative.get(cluster_id)
        if family is None:
            raise FamilyPlanError(
                "First plan did not account for reviewed group alternative: "
                f"{cluster_id}"
            )
        application_exclusions.append(
            {
                "cluster_id": cluster_id,
                "candidate_member_anchor_cluster_ids": sorted(
                    unit["anchor_cluster_id"] for unit in family["content_units"]
                ),
                "independent_context_anchor_cluster_ids": [],
                "reason_code": "not_selected_by_exact_consensus",
                "reason": (
                    "The reviewed alternative was not selected because its full "
                    "frozen family structure and group partition did not receive "
                    "exact agreement from both isolated planners."
                ),
            }
        )
    return {
        "protocol_version": FAMILY_PLAN_PROTOCOL,
        "shot_id": first_plan["shot_id"],
        "reviewed_group_alternative_cluster_ids": sorted(
            first_plan["reviewed_group_alternative_cluster_ids"]
        ),
        "excluded_group_alternatives": application_exclusions,
        "families": selected_families,
        "warnings": [],
    }


def _empty_supported_anchor_audit(
    plans: Sequence[Mapping[str, Any]], baseline: Mapping[str, Any],
) -> Dict[str, Any]:
    """Record a planner's zero-anchor claim without declaring absent content.

    This is coverage bookkeeping, not a new visual membership oracle. Callers
    validate each plan first; no family or anchor can be created by this record.
    """
    baseline_by_id = {cluster["cluster_id"]: cluster for cluster in baseline["clusters"]}
    records = []
    for planner_index, plan in enumerate(plans, 1):
        for item in sorted(plan["excluded_group_alternatives"], key=lambda row: row["cluster_id"]):
            if (item["reason_code"] == "insufficient_supported_member_anchors"
                    and not item["candidate_member_anchor_cluster_ids"]):
                group = baseline_by_id[item["cluster_id"]]
                records.append({
                    "planner_index": planner_index,
                    "group_alternative_cluster_id": item["cluster_id"],
                    "group_anonymous_proposal_ids": sorted(group["anonymous_proposal_ids"]),
                    "reason_code": item["reason_code"],
                    "candidate_member_anchor_cluster_ids": [],
                    "coverage_disposition": "no_supported_eligible_anchor_reported_coverage_unresolved",
                    "partition_effect": "no_op_exclusion",
                    "physical_scope_absence_proven": False,
                    "eligible_member_absence_independently_verified": False,
                })
    return {"policy": EMPTY_SUPPORTED_ANCHOR_POLICY,
            "unresolved_coverage_risk": bool(records), "records": records,
            "nonaccepted_anchors_recovered": False, "pixel_truth_verified": False}


def _assemble_consensus(
    *,
    baseline: Mapping[str, Any],
    anonymous_view: Mapping[str, Any],
    first_plan: Mapping[str, Any],
    second_plan: Mapping[str, Any],
    consensus_resolutions: Sequence[Mapping[str, Any]],
    shot_id: str,
    valid_frame_ids: Sequence[int],
    base_protocol: str,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
    """Recompute consensus and apply it through the existing write firewall."""
    for plan in (first_plan, second_plan):
        validate_family_plan(
            plan, shot_id=shot_id, baseline=baseline, anonymous_view=anonymous_view,
            valid_frame_ids=valid_frame_ids, base_protocol=base_protocol,
        )
    spatial_vetoes = collect_spatial_vetoes(
        (first_plan, second_plan), baseline=baseline, anonymous_view=anonymous_view,
    )
    expected_resolutions = _select_consensus_resolutions(
        first_plan, second_plan, spatial_vetoes=spatial_vetoes,
    )
    if list(consensus_resolutions) != expected_resolutions:
        raise FamilyPlanError("Consensus resolution payload was modified")
    application_plan = _build_consensus_application_plan(
        first_plan, expected_resolutions
    )
    application_resolutions = _select_resolutions(application_plan)
    if any(
        item["status"] != "applied" or item["selected_kind"] != "group"
        for item in application_resolutions
    ):
        raise FamilyPlanError(
            "Consensus application plan contains a non-group resolution"
        )
    final, audit = _assemble_final(
        baseline=baseline,
        anonymous_view=anonymous_view,
        plan=application_plan,
        resolutions=application_resolutions,
        shot_id=shot_id,
        valid_frame_ids=valid_frame_ids,
        base_protocol=base_protocol,
    )
    audit.update(
        {
            "planner_count": 2,
            "valid_planner_count": 2,
            "spatial_vetoes": spatial_vetoes,
            "exact_family_member_partition_consensus_required": True,
            "first_plan_sha256": _json_hash(first_plan),
            "second_plan_sha256": _json_hash(second_plan),
            "consensus_resolutions_sha256": _json_hash(expected_resolutions),
            "application_plan_sha256": _json_hash(application_plan),
            "empty_supported_anchor_exclusions": _empty_supported_anchor_audit(
                (first_plan, second_plan), baseline,
            ),
        }
    )
    return final, audit, application_plan, application_resolutions


def _merge_attributes(
    anchor_clusters: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    per_anchor: List[Dict[Tuple[str, str], Mapping[str, Any]]] = []
    for cluster in anchor_clusters:
        per_anchor.append(
            {
                (attribute["name"], attribute["value"]): attribute
                for attribute in cluster["final_entity"]["attributes"]
            }
        )
    common_keys = (
        set.intersection(*(set(items) for items in per_anchor)) if per_anchor else set()
    )
    merged: List[Dict[str, Any]] = []
    for key in sorted(value for value in common_keys if value[0] != "graph_components"):
        values = [items[key] for items in per_anchor]
        merged.append(
            {
                "name": key[0],
                "value": key[1],
                "confidence": min(item["confidence"] for item in values),
                "evidence_frame_ids": sorted(
                    {
                        frame_id
                        for item in values
                        for frame_id in item["evidence_frame_ids"]
                    }
                ),
            }
        )
    component_names = _format_component_multiset(
        str(cluster["final_entity"]["name"]).strip() for cluster in anchor_clusters
    )
    merged.append(
        {
            "name": "graph_components",
            "value": component_names,
            "confidence": min(
                cluster["final_entity"]["entity_confidence"]
                for cluster in anchor_clusters
            ),
            "evidence_frame_ids": sorted(
                {
                    frame_id
                    for cluster in anchor_clusters
                    for frame_id in cluster["final_entity"]["evidence_frame_ids"]
                }
            ),
        }
    )
    return merged


def _format_component_multiset(names: Iterable[str]) -> str:
    """Format constituent names without discarding repeated physical units."""
    variants: Dict[str, List[str]] = {}
    counts: Counter[str] = Counter()
    for raw_name in names:
        name = str(raw_name).strip()
        normalized = name.casefold()
        counts[normalized] += 1
        variants.setdefault(normalized, []).append(name)

    labels = []
    for normalized in sorted(counts):
        representative = min(
            variants[normalized],
            key=lambda value: (len(value), value.casefold(), value),
        )
        count = counts[normalized]
        labels.append(representative if count == 1 else f"{count} × {representative}")
    return "; ".join(labels)


def _merge_evidence(
    clusters: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    merged: Dict[Tuple[int, str], Dict[str, Any]] = {}
    for cluster in clusters:
        for evidence in cluster["adjudicator_evidence"]:
            key = (evidence["frame_id"], evidence["coarse_locator"])
            current = merged.get(key)
            if (
                current is None
                or SUPPORT_QUALITY_RANK[evidence["support_quality"]]
                > SUPPORT_QUALITY_RANK[current["support_quality"]]
            ):
                merged[key] = copy.deepcopy(evidence)
    return [merged[key] for key in sorted(merged)]


def _merge_frame_presence(
    anchor_clusters: Sequence[Mapping[str, Any]],
    valid_frame_ids: Sequence[int],
) -> List[Dict[str, Any]]:
    by_cluster = [
        {item["frame_id"]: item for item in cluster["frame_presence"]}
        for cluster in anchor_clusters
    ]
    result = []
    for frame_id in valid_frame_ids:
        entries = [items[frame_id] for items in by_cluster]
        statuses = [item["status"] for item in entries]
        status_set = set(statuses)
        if status_set == {"visible"}:
            status = "visible"
        elif status_set == {"absent"}:
            status = "absent"
        elif status_set == {"occluded"}:
            status = "occluded"
        elif "uncertain" in status_set or "absent" in status_set:
            status = "uncertain"
        else:
            status = "occluded"
        result.append(
            {
                "frame_id": frame_id,
                "status": status,
                "description": (
                    "Conservative deterministic aggregation of frozen member "
                    f"presence states: {','.join(statuses)}."
                ),
            }
        )
    return result


def _choose_group_name(
    family: Mapping[str, Any],
    baseline_by_id: Mapping[str, Mapping[str, Any]],
) -> str:
    anchor_ids = {unit["anchor_cluster_id"] for unit in family["content_units"]}
    candidates = [
        str(baseline_by_id[cluster_id]["canonical_name"]).strip()
        for cluster_id in family["baseline_cluster_ids"]
        if cluster_id not in anchor_ids
    ]
    normalized_counts = Counter(value.casefold() for value in candidates)
    winner = min(
        normalized_counts,
        key=lambda value: (-normalized_counts[value], len(value), value),
    )
    return min(
        (value for value in candidates if value.casefold() == winner),
        key=lambda value: (len(value), value.casefold(), value),
    )


def _build_group_cluster(
    *,
    family: Mapping[str, Any],
    baseline_by_id: Mapping[str, Mapping[str, Any]],
    proposal_by_id: Mapping[str, Mapping[str, Any]],
    baseline_order: Mapping[str, int],
    valid_frame_ids: Sequence[int],
) -> Dict[str, Any]:
    anchor_ids = {unit["anchor_cluster_id"] for unit in family["content_units"]}
    anchor_clusters = sorted(
        (baseline_by_id[cluster_id] for cluster_id in anchor_ids),
        key=lambda cluster: baseline_order[cluster["cluster_id"]],
    )
    family_clusters = sorted(
        (baseline_by_id[cluster_id] for cluster_id in family["baseline_cluster_ids"]),
        key=lambda cluster: baseline_order[cluster["cluster_id"]],
    )
    rejected_group_clusters = [
        cluster
        for cluster in family_clusters
        if cluster["cluster_id"] not in anchor_ids
    ]
    group_proposal_ids = sorted(
        role["proposal_id"]
        for role in family["proposal_roles"]
        if role["role"] == "group"
    )
    canonical_name = _choose_group_name(family, baseline_by_id)
    alias_candidates = {
        canonical_name,
        *(cluster["canonical_name"] for cluster in rejected_group_clusters),
        *(alias for cluster in rejected_group_clusters for alias in cluster["aliases"]),
        *(
            str(proposal_by_id[proposal_id].get("proposed_name", "")).strip()
            for proposal_id in group_proposal_ids
        ),
    }
    aliases = _ordered_unique(
        [
            canonical_name,
            *sorted(alias_candidates - {canonical_name}, key=str.casefold),
        ]
    )
    entity_evidence = sorted(
        {
            frame_id
            for cluster in anchor_clusters
            for frame_id in cluster["final_entity"]["evidence_frame_ids"]
        }
    )
    confidence = min(
        cluster["final_entity"]["entity_confidence"] for cluster in anchor_clusters
    )
    uncertainty_flags = sorted(
        {flag for cluster in family_clusters for flag in cluster["uncertainty_flags"]}
        | {"graph_partition_coarsened_from_frozen_members"}
    )
    cluster_key = ",".join(sorted(family["baseline_cluster_ids"]))
    return {
        "cluster_id": f"gf_{hashlib.sha256(cluster_key.encode()).hexdigest()[:12]}",
        "anonymous_proposal_ids": sorted(family["scope_proposal_ids"]),
        "canonical_name": canonical_name,
        "aliases": aliases,
        "granularity": "compact_composite_group",
        "adjudicator_evidence": _merge_evidence(anchor_clusters),
        "frame_presence": _merge_frame_presence(anchor_clusters, valid_frame_ids),
        "identity_status": "resolved",
        "decision": "accept",
        "decision_reason": (
            "Deterministic graph-partition coarsening over frozen source-blind "
            "accepted content units; no entity-existence or physical-identity "
            "judgment was changed."
        ),
        "uncertainty_flags": uncertainty_flags,
        "final_entity": {
            "name": canonical_name,
            "attributes": _merge_attributes(anchor_clusters),
            "entity_confidence": confidence,
            "evidence_frame_ids": entity_evidence,
        },
    }


def _assemble_final(
    *,
    baseline: Mapping[str, Any],
    anonymous_view: Mapping[str, Any],
    plan: Mapping[str, Any],
    resolutions: Sequence[Mapping[str, Any]],
    shot_id: str,
    valid_frame_ids: Sequence[int],
    base_protocol: str,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Deterministically assemble a partition-only result and firewall audit.

    The caller remains responsible for validating the returned adjudication
    against its base-protocol schema.
    """
    if not isinstance(base_protocol, str) or not base_protocol:
        raise FamilyPlanError("base_protocol must be a nonempty string")
    validate_family_plan(
        plan, shot_id=shot_id, baseline=baseline, anonymous_view=anonymous_view,
        valid_frame_ids=valid_frame_ids, base_protocol=base_protocol,
    )
    spatial_vetoes = collect_spatial_vetoes(
        (plan,), baseline=baseline, anonymous_view=anonymous_view,
    )
    family_by_id = {family["family_id"]: family for family in plan["families"]}
    resolution_by_id = {item["family_id"]: item for item in resolutions}
    applied = {
        family_id
        for family_id, item in resolution_by_id.items()
        if item["status"] == "applied" and item["selected_kind"] == "group"
    }
    baseline_by_id = {
        cluster["cluster_id"]: cluster for cluster in baseline["clusters"]
    }
    baseline_order = {
        cluster["cluster_id"]: index
        for index, cluster in enumerate(baseline["clusters"])
    }
    proposal_by_id = {
        item["anonymous_proposal_id"]: item for item in anonymous_view["proposals"]
    }
    baseline_to_family: Dict[str, str] = {}
    for family_id in applied:
        if matching_spatial_vetoes(
            (unit["anchor_cluster_id"] for unit in family_by_id[family_id]["content_units"]),
            spatial_vetoes,
            group_proposal_ids=(r["proposal_id"] for r in family_by_id[family_id]["proposal_roles"] if r["role"] == "group"),
        ):
            raise FamilyPlanError("Spatial veto cannot be overridden during assembly")
        for cluster_id in family_by_id[family_id]["baseline_cluster_ids"]:
            baseline_to_family[cluster_id] = family_id

    inserted: set[str] = set()
    final_clusters: List[Dict[str, Any]] = []
    for baseline_cluster in baseline["clusters"]:
        family_id = baseline_to_family.get(baseline_cluster["cluster_id"])
        if family_id is None:
            final_clusters.append(copy.deepcopy(baseline_cluster))
            continue
        if family_id in inserted:
            continue
        inserted.add(family_id)
        final_clusters.append(
            _build_group_cluster(
                family=family_by_id[family_id],
                baseline_by_id=baseline_by_id,
                proposal_by_id=proposal_by_id,
                baseline_order=baseline_order,
                valid_frame_ids=valid_frame_ids,
            )
        )

    final = {
        "protocol_version": base_protocol,
        "shot_id": shot_id,
        "clusters": final_clusters,
        "warnings": list(baseline.get("warnings", [])),
    }
    # Schema validation deliberately belongs to the caller.
    final_by_id = {cluster["cluster_id"]: cluster for cluster in final_clusters}
    frozen_ids = [
        cluster["cluster_id"]
        for cluster in baseline["clusters"]
        if cluster["cluster_id"] not in baseline_to_family
    ]
    changed_outside = [
        cluster_id
        for cluster_id in frozen_ids
        if final_by_id.get(cluster_id) != baseline_by_id[cluster_id]
    ]
    if changed_outside:
        raise FamilyPlanError(
            "Partition firewall detected changes outside applied families: "
            f"{changed_outside}"
        )

    frozen_content_units = []
    for family_id in sorted(applied):
        family = family_by_id[family_id]
        for unit in family["content_units"]:
            cluster = baseline_by_id[unit["anchor_cluster_id"]]
            frozen_content_units.append(
                {
                    "family_id": family_id,
                    "unit_id": unit["unit_id"],
                    "anchor_cluster_id": unit["anchor_cluster_id"],
                    "anchor_cluster_sha256": _json_hash(cluster),
                    "anchor_decision": cluster["decision"],
                    "anchor_identity_status": cluster["identity_status"],
                    "anchor_final_entity_sha256": _json_hash(cluster["final_entity"]),
                    "anchor_frame_presence_sha256": _json_hash(
                        cluster["frame_presence"]
                    ),
                    "immutable_anchor_cluster": copy.deepcopy(cluster),
                }
            )
    frozen_content_units.sort(
        key=lambda item: (
            baseline_order[item["anchor_cluster_id"]],
            item["family_id"],
            item["unit_id"],
        )
    )
    frozen_registry_hash = _json_hash(frozen_content_units)
    audit = {
        "shot_id": shot_id,
        "applied_family_ids": sorted(applied),
        "spatial_vetoes": spatial_vetoes,
        "frozen_nonfamily_cluster_ids": frozen_ids,
        "frozen_nonfamily_cluster_count": len(frozen_ids),
        "changed_outside_family_cluster_ids": changed_outside,
        "frozen_content_units": frozen_content_units,
        "frozen_content_unit_count": len(frozen_content_units),
        "frozen_content_registry_sha256": frozen_registry_hash,
        "baseline_cluster_count": len(baseline["clusters"]),
        "final_cluster_count": len(final_clusters),
        "post_provenance_model_calls": 0,
        "panel_positions_gate_family_application": False,
        "panel_positions_select_group_vs_members": False,
        "physical_content_anchors_preserved_in_audit": True,
        "cross_shot_input": False,
        "empty_supported_anchor_exclusions": _empty_supported_anchor_audit((plan,), baseline),
    }
    return final, audit


# Public stage interface. Underscored implementations remain stable for the
# standalone runner's historical test aliases.
json_hash = _json_hash
detector_sort_key = _detector_sort_key
planner_view = _planner_view
planner_baseline_view = _planner_baseline_view
eligible_group_alternative_ids = _eligible_group_alternative_ids
build_prompt = _build_prompt
select_resolutions = _select_resolutions
family_signature = _family_signature
select_consensus_resolutions = _select_consensus_resolutions
build_consensus_application_plan = _build_consensus_application_plan
assemble_consensus = _assemble_consensus
merge_frame_presence = _merge_frame_presence
assemble_final = _assemble_final

__all__ = [
    "FAMILY_PLAN_PROTOCOL",
    "EMPTY_SUPPORTED_ANCHOR_POLICY",
    "PROPOSAL_FIELDS",
    "FamilyPlanError",
    "json_hash",
    "detector_sort_key",
    "planner_view",
    "planner_baseline_view",
    "eligible_group_alternative_ids",
    "build_prompt",
    "audit_gross_spatial_incompatibility",
    "collect_spatial_vetoes",
    "matching_spatial_vetoes",
    "validate_family_plan",
    "validate_source_map",
    "build_panel_positions",
    "select_resolutions",
    "family_signature",
    "select_consensus_resolutions",
    "build_consensus_application_plan",
    "assemble_consensus",
    "merge_frame_presence",
    "assemble_final",
]
