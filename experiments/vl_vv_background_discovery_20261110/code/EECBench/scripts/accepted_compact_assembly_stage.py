"""Pure accepted-only compact-assembly planning and consensus resolution.

The model-visible view contains a deterministic mandatory candidate bank, frozen
accepted clusters, and original-frame descriptions. Detector provenance,
proposal IDs, boxes, rejected candidates, and support counts remain private.
Two independently produced exact-candidate judgments are required for any
graph-node coarsening.
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

from granularity_family_stage import (
    matching_spatial_vetoes, _box_intersection_metrics,
    GROSS_SPATIAL_MAX_IOU, GROSS_SPATIAL_MAX_INTERSECTION_OVER_SMALLER,
    GROSS_SPATIAL_MIN_INCOMPATIBLE_RATIO,
    HOLDING_CONTAINER_SCOPE_INSTRUCTION,
)


PLAN_PROTOCOL = "single_shot_accepted_compact_assembly_plan_v0.5"
INPUT_PROTOCOL = "single_shot_accepted_compact_assembly_input_v0.2"
CANDIDATE_BANK_PROTOCOL = (
    "single_shot_accepted_compact_assembly_candidate_bank_v0.3"
)
REFERENCE_COVERAGE_POLICY = "all_candidate_common_visible_reference_frames_v0.1"

ASSEMBLY_KIND_NAMES = {
    "integrated_part_whole": "integrated object",
    "small_container_contents_unit": "container-content unit",
    "fixed_coordinated_array": "fixed display",
    "directly_coupled_operational_unit": "coupled functional unit",
    "passive_homogeneous_collection": "homogeneous collection",
}
COHESION_KINDS_BY_ASSEMBLY = {
    "integrated_part_whole": {
        "shared_continuous_housing_or_joint",
        "direct_mechanical_or_operational_coupling",
    },
    "small_container_contents_unit": {
        "same_small_container_functional_unit"
    },
    "fixed_coordinated_array": {
        "common_fixed_mounting_or_array",
        "stable_complementary_same_role_array_about_external_reference",
    },
    "directly_coupled_operational_unit": {
        "direct_mechanical_or_operational_coupling"
    },
}
COHESION_KINDS_BY_ASSEMBLY["passive_homogeneous_collection"] = {
    "same_fixture_bounded_passive_homogeneous_content"
}
COLLECTION_SCOPE_KEYS = {
    "fixture_anchor_cluster_id", "content_category", "evidence", "description",
    "complete_fixture_content_scope", "passive_unhandled_content",
    "fixture_excluded", "heterogeneous_neighbors_excluded",
    "independently_framed_subjects_excluded",
}
COLLECTION_SCOPE_CHECKS = COLLECTION_SCOPE_KEYS - {
    "fixture_anchor_cluster_id", "content_category", "evidence", "description"
}

INDEPENDENCE_KINDS = {
    "separate_handling_or_use",
    "detachment_or_standalone_state",
    "relative_motion",
    "independent_trajectory",
}
PROTECTED_RELATION_KINDS = {
    "large_host_or_support_member",
    "person_or_animal_member",
    "holder_with_held_or_carried_item",
    "loose_items_sharing_support_or_proximity",
    "temporary_storage_or_transport_payload",
    "worn_or_body_constituent_scope_case",
}

TOP_LEVEL_KEYS = {
    "protocol_version",
    "shot_id",
    "reviewed_accepted_cluster_ids",
    "reviewed_candidate_ids",
    "families",
    "excluded_candidates",
    "warnings",
}
FAMILY_KEYS = {
    "family_id",
    "candidate_id",
    "visual_scope",
    "anchor_cluster_ids",
    "content_units",
    "assembly_kind",
    "collection_scope_review",
    "common_visible_frame_ids",
    "cohesion_witnesses",
    "pairwise_independence_reviews",
    "protected_relation_reviews",
    "context_exclusion_reviews",
    "scope_review_complete",
    "minimal_cohesive_closure_confirmed",
    "reason",
}
CONTENT_UNIT_KEYS = {
    "unit_id",
    "anchor_cluster_id",
    "description",
    "pixel_evidence",
    "anchor_scope_review",
}
VISUAL_EVIDENCE_KEYS = {"frame_id", "description"}
COHESION_WITNESS_KEYS = {
    "witness_id",
    "unit_a_id",
    "unit_b_id",
    "kind",
    "frame_ids",
    "description",
    "reference_review",
}
PAIR_REVIEW_KEYS = {
    "unit_a_id",
    "unit_b_id",
    "reviewed_frame_ids",
    "checks",
}
INDEPENDENCE_CHECK_KEYS = {"kind", "outcome", "evidence", "description"}
PROTECTED_REVIEW_KEYS = {"kind", "outcome", "evidence", "description"}
CONTEXT_REVIEW_KEYS = {
    "context_anchor_cluster_id",
    "reviewed_frame_ids",
    "outcome",
    "evidence",
    "description",
}
EXCLUDED_CANDIDATE_KEYS = {
    "candidate_id",
    "anchor_cluster_ids",
    "reason_code",
    "evidence",
    "reason",
}
CANDIDATE_BANK_KEYS = {"protocol_version", "shot_id", "candidates"}
CANDIDATE_KEYS = {
    "candidate_id",
    "anchor_cluster_ids",
    "context_anchor_cluster_ids",
}
EXCLUDED_CANDIDATE_REASON_CODES = {
    "insufficient_positive_same_role_cohesion",
    "insufficient_common_visibility",
    "observed_independence",
    "uncertain_independence",
    "protected_relation_present_or_uncertain",
    "context_membership_uncertain",
    "not_minimal_cohesive_closure",
    "anchor_scope_uncertain_or_different",
    "reference_scope_uncertain_or_incomplete",
}

_POSITIONAL_NAME_TOKENS = {
    "back",
    "bottom",
    "center",
    "central",
    "front",
    "left",
    "lower",
    "middle",
    "rear",
    "right",
    "side",
    "top",
    "upper",
}
_UNSAFE_SINGLE_CORE_TOKENS = {
    "area",
    "component",
    "content",
    "item",
    "object",
    "part",
    "piece",
    "region",
    "thing",
    "unit",
}
_COLLECTIVE_CORE_TOKENS = {
    "array",
    "assembly",
    "collection",
    "display",
    "group",
    "pair",
    "set",
    "stack",
}


class AcceptedAssemblyError(Exception):
    """Raised when the accepted-only partition contract is violated."""


def json_hash(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str], label: str
) -> None:
    observed = set(value)
    if observed != expected:
        raise AcceptedAssemblyError(
            f"{label} keys differ: missing={sorted(expected - observed)}, "
            f"extra={sorted(observed - expected)}"
        )


def _require_unique(values: Sequence[Any], label: str) -> set[Any]:
    result = set(values)
    if len(result) != len(values):
        raise AcceptedAssemblyError(f"{label} contains duplicate values")
    return result


def _pair(first: str, second: str) -> Tuple[str, str]:
    if first == second:
        raise AcceptedAssemblyError("A pair cannot contain the same unit twice")
    return tuple(sorted((first, second)))


def _eligible_clusters(baseline: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    return [
        cluster
        for cluster in baseline["clusters"]
        if cluster["decision"] == "accept"
        and cluster["identity_status"] == "resolved"
        and cluster["final_entity"] is not None
    ]


def _normalize_semantic_label(value: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value).casefold()))


def _semantic_pairs_for_cluster(
    cluster: Mapping[str, Any],
    proposal_by_id: Mapping[str, Mapping[str, Any]],
) -> set[Tuple[str, str]]:
    """Return source-blind proposal head/type pairs for cohort construction."""
    pairs = set()
    for proposal_id in cluster["anonymous_proposal_ids"]:
        proposal = proposal_by_id.get(proposal_id)
        if proposal is None:
            continue
        head = _normalize_semantic_label(proposal.get("canonical_head", ""))
        entity_type = _normalize_semantic_label(proposal.get("entity_type", ""))
        if head and entity_type:
            pairs.add((head, entity_type))
    return pairs


def _safe_shared_name_core(names: Sequence[str]) -> str | None:
    """Derive a conservative shared lexical core without model naming authority."""
    token_lists = []
    for name in names:
        tokens = [
            token
            for token in re.findall(r"[a-z0-9]+", name.casefold())
            if token not in _POSITIONAL_NAME_TOKENS and not token.isdigit()
        ]
        if not tokens:
            return None
        token_lists.append(tokens)
    suffix_length = 0
    for offset in range(1, min(map(len, token_lists)) + 1):
        tokens = {items[-offset] for items in token_lists}
        if len(tokens) != 1:
            break
        suffix_length = offset
    if suffix_length == 0:
        return None
    shared = token_lists[0][-suffix_length:]
    if len(shared) == 1 and shared[0] in _UNSAFE_SINGLE_CORE_TOKENS:
        return None
    return " ".join(shared)


def deterministic_merged_name(
    clusters: Sequence[Mapping[str, Any]], assembly_kind: str
) -> str:
    """Name a coarsened node from a safely shared constituent core when possible."""
    core = _safe_shared_name_core(
        [str(cluster["final_entity"]["name"]) for cluster in clusters]
    )
    if core is None:
        return ASSEMBLY_KIND_NAMES[assembly_kind]
    if core.split()[-1] in _COLLECTIVE_CORE_TOKENS:
        return core
    return f"{core} group"


def _validate_candidate_bank(
    candidate_bank: Mapping[str, Any],
    *,
    shot_id: str,
    accepted_cluster_ids: set[str],
) -> None:
    _require_exact_keys(candidate_bank, CANDIDATE_BANK_KEYS, "candidate bank")
    if candidate_bank["protocol_version"] != CANDIDATE_BANK_PROTOCOL:
        raise AcceptedAssemblyError("Unexpected candidate-bank protocol_version")
    if candidate_bank["shot_id"] != shot_id:
        raise AcceptedAssemblyError("Candidate bank changed shot_id")
    candidate_ids = []
    for index, candidate in enumerate(candidate_bank["candidates"]):
        _require_exact_keys(candidate, CANDIDATE_KEYS, f"candidate[{index}]")
        candidate_id = candidate["candidate_id"]
        if not isinstance(candidate_id, str) or not candidate_id:
            raise AcceptedAssemblyError("Candidate bank has an invalid candidate ID")
        candidate_ids.append(candidate_id)
        anchors = _require_unique(
            candidate["anchor_cluster_ids"], f"{candidate_id} anchor cluster IDs"
        )
        contexts = _require_unique(
            candidate["context_anchor_cluster_ids"],
            f"{candidate_id} context anchor cluster IDs",
        )
        if len(anchors) < 2:
            raise AcceptedAssemblyError(
                f"{candidate_id}: candidate needs at least two anchors"
            )
        if not anchors <= accepted_cluster_ids or not contexts <= accepted_cluster_ids:
            raise AcceptedAssemblyError(
                f"{candidate_id}: candidate cites a non-accepted anchor"
            )
        if anchors & contexts:
            raise AcceptedAssemblyError(
                f"{candidate_id}: candidate anchors and context must be disjoint"
            )
    _require_unique(candidate_ids, "candidate IDs")


def build_declared_partition_neighborhoods(
    *, baseline: Mapping[str, Any], initial_decisions: Mapping[str, Any],
    verifier_reports: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Nominate advisory partner sets only across unchanged proposal scopes."""
    for key in ("shot_id", "protocol_version"):
        if initial_decisions.get(key) != baseline.get(key):
            raise AcceptedAssemblyError(f"Partner handoff changed {key}")
    initial_by_id = {c["cluster_id"]: c for c in initial_decisions["clusters"]}
    accepted_by_scope: Dict[frozenset[str], List[str]] = {}
    for cluster in _eligible_clusters(baseline):
        scope = frozenset(cluster["anonymous_proposal_ids"])
        if scope:
            accepted_by_scope.setdefault(scope, []).append(cluster["cluster_id"])
    declarations = []
    for report in verifier_reports:
        if report.get("shot_id") != baseline["shot_id"]:
            raise AcceptedAssemblyError("Partner report changed shot_id")
        for review in report["reviews"]:
            if (review["graph_partition_judgment"] != "merge_into_compact_composite"
                    or review["existence_judgment"] != "confirmed"
                    or review["salience_judgment"] != "graph_worthy"
                    or review["observed_independence_evidence"]):
                continue
            partners = sorted(set(review["same_graph_node_with_cluster_ids"]))
            if not partners or review["cluster_id"] in partners:
                continue
            initial_ids = [review["cluster_id"], *partners]
            mapped_ids = []
            for initial_id in initial_ids:
                initial = initial_by_id.get(initial_id)
                scope = frozenset(initial["anonymous_proposal_ids"]) if initial else frozenset()
                matches = accepted_by_scope.get(scope, [])
                if len(matches) != 1:
                    break
                mapped_ids.append(matches[0])
            else:
                if len(set(mapped_ids)) == len(initial_ids):
                    declarations.append({
                        "anchor_cluster_ids": sorted(mapped_ids),
                        "context_anchor_cluster_ids": [],
                        "source_provenance": {
                            "verifier_id": report["verifier_id"],
                            "initial_anchor_cluster_ids": initial_ids,
                            "review": copy.deepcopy(review),
                        },
                    })
    return declarations


def build_candidate_bank(
    *,
    baseline: Mapping[str, Any],
    anonymous_view: Mapping[str, Any],
    explicit_partition_plans: Sequence[Mapping[str, Any]],
    shot_id: str,
    base_protocol: str,
    declared_partition_neighborhoods: Sequence[Mapping[str, Any]] = (),
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Build a mandatory, source-blind candidate bank before model review.

    Candidates come from explicit partition-planner member maps, declared
    verifier member maps handed off across exact unchanged proposal scopes, or
    accepted anchors explicitly marked for compact-assembly review. Explicit
    and declared member maps define their candidate closure directly; declared
    maps remain local nominations, without transitive expansion or extra votes.
    Exact normalized proposal head/type overlap is used only to cohort otherwise
    unscoped accepted-only markers. No panel, count, score, or box participates.
    """
    if baseline.get("protocol_version") != base_protocol:
        raise AcceptedAssemblyError("Baseline changed base protocol_version")
    if baseline.get("shot_id") != shot_id:
        raise AcceptedAssemblyError("Baseline changed shot_id")
    if anonymous_view.get("protocol_version") != base_protocol:
        raise AcceptedAssemblyError("Anonymous view changed base protocol_version")
    if anonymous_view.get("shot_id") != shot_id:
        raise AcceptedAssemblyError("Anonymous view changed shot_id")

    accepted = _eligible_clusters(baseline)
    accepted_by_id = {cluster["cluster_id"]: cluster for cluster in accepted}
    if len(accepted_by_id) != len(accepted):
        raise AcceptedAssemblyError("Baseline has duplicate accepted cluster IDs")
    proposal_by_id = {
        item["anonymous_proposal_id"]: item
        for item in anonymous_view["proposals"]
    }
    if len(proposal_by_id) != len(anonymous_view["proposals"]):
        raise AcceptedAssemblyError("Anonymous view has duplicate proposal IDs")
    semantic_pairs = {
        cluster_id: _semantic_pairs_for_cluster(cluster, proposal_by_id)
        for cluster_id, cluster in accepted_by_id.items()
    }

    raw_neighborhoods: List[Dict[str, Any]] = []
    for planner_index, plan in enumerate(explicit_partition_plans, start=1):
        if plan.get("shot_id") != shot_id:
            raise AcceptedAssemblyError("Explicit partition plan changed shot_id")
        for family in plan.get("families", []):
            raw_neighborhoods.append(
                {
                    "kind": "explicit_family_member_map",
                    "planner_index": planner_index,
                    "source_id": family["family_id"],
                    "anchor_ids": sorted(
                        {
                            unit["anchor_cluster_id"]
                            for unit in family["content_units"]
                            if unit["anchor_cluster_id"] in accepted_by_id
                        }
                    ),
                    "forced_context_ids": [],
                }
            )
        for exclusion in plan.get("excluded_group_alternatives", []):
            raw_neighborhoods.append(
                {
                    "kind": "explicit_exclusion_member_map",
                    "planner_index": planner_index,
                    "source_id": exclusion["cluster_id"],
                    "anchor_ids": sorted(
                        {
                            cluster_id
                            for cluster_id in exclusion[
                                "candidate_member_anchor_cluster_ids"
                            ]
                            if cluster_id in accepted_by_id
                        }
                    ),
                    "forced_context_ids": sorted(
                        {
                            cluster_id
                            for cluster_id in exclusion[
                                "independent_context_anchor_cluster_ids"
                            ]
                            if cluster_id in accepted_by_id
                        }
                    ),
                }
            )

    for index, declaration in enumerate(declared_partition_neighborhoods, start=1):
        anchors = _require_unique(declaration["anchor_cluster_ids"], "declared partner anchors")
        contexts = _require_unique(declaration["context_anchor_cluster_ids"], "declared partner context")
        if (len(anchors) < 2 or not (anchors | contexts) <= set(accepted_by_id)
                or anchors & contexts):
            raise AcceptedAssemblyError("Invalid accepted-only partner neighborhood")
        raw_neighborhoods.append({
            "kind": "declared_verifier_member_map", "planner_index": None,
            "source_id": f"declared_review_{index}", "anchor_ids": sorted(anchors),
            "forced_context_ids": sorted(contexts),
            "source_provenance": copy.deepcopy(declaration["source_provenance"]),
        })

    marked_ids = sorted(
        cluster_id
        for cluster_id, cluster in accepted_by_id.items()
        if "possible_compact_assembly_partition" in cluster["uncertainty_flags"]
    )
    if marked_ids:
        raw_neighborhoods.append(
            {
                "kind": "possible_compact_assembly_partition_semantic_cohort",
                "planner_index": None,
                "source_id": None,
                "anchor_ids": marked_ids,
                "forced_context_ids": [],
            }
        )

    candidates_by_anchors: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    derivations_by_anchors: Dict[Tuple[str, ...], List[Dict[str, Any]]] = {}
    for neighborhood in raw_neighborhoods:
        forced_context = set(neighborhood["forced_context_ids"])
        neighborhood_ids = set(neighborhood["anchor_ids"]) | forced_context
        peer_pool = neighborhood_ids - forced_context
        cohorts: List[Tuple[Tuple[str, str] | None, set[str]]] = []
        if (neighborhood["kind"].startswith("explicit_")
                or neighborhood["kind"] == "declared_verifier_member_map"):
            cohorts = [(None, peer_pool)]
        else:
            pair_to_ids: Dict[Tuple[str, str], set[str]] = {}
            for cluster_id in sorted(peer_pool):
                for semantic_pair in sorted(semantic_pairs[cluster_id]):
                    pair_to_ids.setdefault(semantic_pair, set()).add(cluster_id)
            cohorts = list(sorted(pair_to_ids.items()))
        for semantic_pair, cohort_ids in cohorts:
            if len(cohort_ids) < 2:
                continue
            anchors = tuple(sorted(cohort_ids))
            contexts = sorted(neighborhood_ids - cohort_ids)
            current = candidates_by_anchors.setdefault(
                anchors,
                {
                    "anchor_cluster_ids": list(anchors),
                    "context_anchor_cluster_ids": [],
                },
            )
            current["context_anchor_cluster_ids"] = sorted(
                set(current["context_anchor_cluster_ids"]) | set(contexts)
            )
            derivations_by_anchors.setdefault(anchors, []).append(
                {
                    "neighborhood_kind": neighborhood["kind"],
                    "planner_index": neighborhood["planner_index"],
                    "source_id": neighborhood["source_id"],
                    "semantic_pair": (
                        {
                            "canonical_head": semantic_pair[0],
                            "entity_type": semantic_pair[1],
                        }
                        if semantic_pair is not None
                        else None
                    ),
                    "neighborhood_anchor_cluster_ids": sorted(neighborhood_ids),
                    "forced_context_anchor_cluster_ids": sorted(forced_context),
                }
            )

    public_candidates = []
    private_candidates = []
    for anchors in sorted(candidates_by_anchors):
        item = candidates_by_anchors[anchors]
        candidate_key = json.dumps(
            {"anchor_cluster_ids": list(anchors)},
            sort_keys=True,
            separators=(",", ":"),
        )
        candidate_id = f"aca_{hashlib.sha256(candidate_key.encode()).hexdigest()[:12]}"
        public = {"candidate_id": candidate_id, **copy.deepcopy(item)}
        public_candidates.append(public)
        clusters = [accepted_by_id[cluster_id] for cluster_id in anchors]
        private_candidates.append(
            {
                **copy.deepcopy(public),
                "derivations": copy.deepcopy(derivations_by_anchors[anchors]),
                "proposal_semantic_pairs_by_anchor": {
                    cluster_id: [
                        {"canonical_head": head, "entity_type": entity_type}
                        for head, entity_type in sorted(semantic_pairs[cluster_id])
                    ]
                    for cluster_id in anchors
                },
                "deterministic_names_by_assembly_kind": {
                    kind: deterministic_merged_name(clusters, kind)
                    for kind in sorted(ASSEMBLY_KIND_NAMES)
                },
            }
        )

    public_bank = {
        "protocol_version": CANDIDATE_BANK_PROTOCOL,
        "shot_id": shot_id,
        "candidates": public_candidates,
    }
    _validate_candidate_bank(
        public_bank,
        shot_id=shot_id,
        accepted_cluster_ids=set(accepted_by_id),
    )
    private_audit = {
        "protocol_version": CANDIDATE_BANK_PROTOCOL,
        "shot_id": shot_id,
        "derivation_uses_detector_panels_or_counts": False,
        "derivation_uses_detector_boxes": False,
        "public_bank_contains_proposal_ids_or_derivation": False,
        "raw_partition_neighborhoods": raw_neighborhoods,
        "candidates": private_candidates,
        "public_candidate_bank_sha256": json_hash(public_bank),
    }
    return public_bank, private_audit


def planner_baseline_view(
    baseline: Mapping[str, Any],
    *,
    candidate_bank: Mapping[str, Any],
    shot_id: str,
    base_protocol: str,
) -> Dict[str, Any]:
    """Return the strict model-visible accepted-only view.

    The allowlist construction intentionally drops proposal membership, detector
    boxes, rejected/abstained clusters, confidence values, decisions, uncertainty
    flags, and every provenance-derived diagnostic.
    """
    if baseline.get("protocol_version") != base_protocol:
        raise AcceptedAssemblyError("Baseline changed base protocol_version")
    if baseline.get("shot_id") != shot_id:
        raise AcceptedAssemblyError("Baseline changed shot_id")

    accepted_clusters = []
    for cluster in _eligible_clusters(baseline):
        final_entity = cluster["final_entity"]
        accepted_clusters.append(
            {
                "cluster_id": cluster["cluster_id"],
                "canonical_name": cluster["canonical_name"],
                "granularity": cluster["granularity"],
                "adjudicator_evidence": [
                    {
                        "frame_id": item["frame_id"],
                        "coarse_locator": item["coarse_locator"],
                        "support_quality": item["support_quality"],
                    }
                    for item in cluster["adjudicator_evidence"]
                ],
                "frame_presence": [
                    {
                        "frame_id": item["frame_id"],
                        "status": item["status"],
                        "description": item["description"],
                    }
                    for item in cluster["frame_presence"]
                ],
                "entity": {
                    "name": final_entity["name"],
                    "attributes": [
                        {
                            "name": item["name"],
                            "value": item["value"],
                            "evidence_frame_ids": copy.deepcopy(
                                item["evidence_frame_ids"]
                            ),
                        }
                        for item in final_entity["attributes"]
                    ],
                    "evidence_frame_ids": copy.deepcopy(
                        final_entity["evidence_frame_ids"]
                    ),
                },
            }
        )
    _validate_candidate_bank(
        candidate_bank,
        shot_id=shot_id,
        accepted_cluster_ids={item["cluster_id"] for item in accepted_clusters},
    )
    return {
        "protocol_version": INPUT_PROTOCOL,
        "shot_id": shot_id,
        "reference_coverage_policy": REFERENCE_COVERAGE_POLICY,
        "accepted_clusters": accepted_clusters,
        "candidate_bank": copy.deepcopy(candidate_bank),
    }


def build_prompt(
    *,
    shot_id: str,
    shot_manifest: Mapping[str, Any],
    accepted_view: Mapping[str, Any],
    policy_text: str,
) -> str:
    """Build the identical prompt supplied to both isolated planners."""
    allowed_paths = [
        str(Path(item["path"]).resolve())
        for item in shot_manifest["reference_frames"]
    ]
    name_map = json.dumps(ASSEMBLY_KIND_NAMES, sort_keys=True)
    cohesion_map = json.dumps(
        {
            key: sorted(value)
            for key, value in COHESION_KINDS_BY_ASSEMBLY.items()
        },
        sort_keys=True,
    )
    return (
        "You are a source-blind graph-node partition planner for exactly one video "
        "shot. Inspect every attached original frame together. The supplied clusters "
        "have already passed existence and physical-identity adjudication. You may "
        "only propose that two or more accepted physical constituents form one compact "
        "graph node. You cannot discover, reject, split, rename, or classify an entity; "
        "emit graph relations; use another shot; or output a final decision. Return only "
        "schema-valid JSON. Do not use shell tools, read unlisted paths, search the "
        "workspace, or spawn agents.\n\n"
        f"Set protocol_version to {PLAN_PROTOCOL} and shot_id to {shot_id}. List every "
        "supplied accepted cluster ID exactly once in reviewed_accepted_cluster_ids, "
        "and every supplied candidate ID exactly once in reviewed_candidate_ids. The "
        "candidate bank is mandatory and exhaustive for this role: account for each "
        "candidate exactly once, either as one family or as one structured "
        "excluded_candidates record. Do not invent a candidate, omit one, or propose a "
        "family outside the bank. A family must use exactly its bank candidate's anchor "
        "set, never a subset or superset. Overlapping bank candidates must still each be "
        "reviewed; the deterministic firewall, not this planner, handles overlap. The "
        "downstream resolver requires exact agreement between two independent plans; a "
        "positive judgment from one planner alone has no effect.\n\n"
        "A family requires positive visual organization across at least two common-visible frames. Choose graph scope by the canonical category policy regardless of initial whole-collection versus subdivision representation. A passive homogeneous collection contains all visible passive content of one physical category within one clearly bounded storage or display fixture, across internal shelves, bays, rows or slots. Internal dividers, crop, content colors, or separately localizable subgroups alone do not create independent graph subjects. The fixture is an external accepted anchor, never a collection member. Different fixtures and unbounded shared surfaces cannot be merged. This is positive collection organization, not mechanical coupling.\n\n"
        "For passive_homogeneous_collection use cohesion kind same_fixture_bounded_passive_homogeneous_content. Set collection_scope_review to a structured review naming the accepted external fixture_anchor_cluster_id, common content_category, and direct two-frame evidence for complete_fixture_content_scope, passive_unhandled_content, fixture_excluded, heterogeneous_neighbors_excluded, and independently_framed_subjects_excluded. Set checks true only after original-pixel review. Both the fixture and every collection anchor must be visible in at least two cited frames. If any accepted same-category passive content in that fixture is missing from the candidate, exclude it as not_minimal_cohesive_closure. Different fixtures, individually framed artwork or separately mounted complete display fixtures, heterogeneous neighbors, and separately handled or used objects remain separate. Other assembly kinds use null collection_scope_review.\n\n"
        f"{HOLDING_CONTAINER_SCOPE_INSTRUCTION}"
        "Other permitted cohesion is integrated part-whole structure, a continuous housing/joint, one small container-content functional unit under the shared rule, a shared fixed mount, a complementary same-role array around one bounded excluded reference, or direct mechanical/operational coupling. Same-role covering or control panels serving one bounded fixture form one whole array unless direct independent handling, use or motion occurs. For that array the fixture stays external. Individually framed artworks or separately mounted complete display fixtures stay separate even when categories or walls match. fixed_coordinated_array uses common_fixed_mounting_or_array or stable_complementary_same_role_array_about_external_reference. A continuous connector need not be visible for the latter.\n\n"
        "Shared wording, semantic type, proximity, overlap, contact, appearance or support alone is not cohesion. Absence of independence evidence is not positive cohesion. Demonstrated complete passive homogeneous content within one bounded fixture is a permitted category-level organization; loose_items_sharing_support_or_proximity is absent for that demonstrated contents-only case, not merely because its kind was selected. Scattered items on a surface and heterogeneous independent contents linked only by shared storage or support remain protected. Different constituent categories neither supply positive cohesion nor negate directly demonstrated integrated or functional organization; every other scope, independence and protection requirement still applies. Passive fixture-organized contents are not temporary_storage_or_transport_payload merely because they are stored; actual temporary packing, loading or transport payloads remain protected. Large hosts included as members, people or animals, protected holder/item or load relations as defined above, independently framed subjects, heterogeneous independent contents with only shared storage/support, and worn/body constituents cannot be absorbed. Selecting an assembly kind cannot bypass any of these protections. Apply holder_with_held_or_carried_item by that shared definition, not by a holder name or absence of observed handling. Explain its application in the existing description; absent still requires empty evidence and present/uncertain still requires original-frame evidence.\n\n"
        "Set common_visible_frame_ids to the exact intersection of visible frames for every anchor, with at least two frames. Each content unit needs direct pixel evidence where visible. Give exactly one cohesion witness per unordered pair, citing at least two common-visible frames. For every pair review all supplied frames and all four independence kinds. not_observed requires empty evidence; observed or uncertain requires nonempty evidence. Observed relative motion or independent trajectory needs two frames; observed evidence must show both units. Review exactly all six protected relation kinds: absent requires empty evidence; present/uncertain requires evidence. Any observed/uncertain independence or present/uncertain protected relation blocks merging. Static internal divisions of a canonical fixture collection are not detachment or independent use. No detector boxes may substitute for original pixels.\n\n"
        "For each content unit, anchor_scope_review.observations must cover every "
        "common_visible_frame_id exactly once. Reidentify the FULL visible scope of "
        "that frozen anchor from the original pixels; do not replace it with a nearby "
        "object, reinterpret a collection as one member, or repair identity silently. "
        "Give correspondence matched/uncertain/different_content, coverage "
        "complete_visible_claim/partial/unresolved, a tight normalized xyxy bbox or "
        "null, boundary_evidence, and limitation ('none' only when no limitation is "
        "observed). Matched+complete requires a box. Uncertain, partial, or different "
        "content is valid evidence and prevents this candidate from merging; it is "
        "not an instruction to retry until positive.\n\n"
        "Each cohesion witness requires reference_review. Reference_type is "
        "accepted_anchor or visible_intrinsic_structure; reference_anchor_cluster_id "
        "must be an existing accepted anchor. Intrinsic structures must be visibly "
        "inside that named candidate member. An external fixture must use an existing "
        "accepted anchor, stay outside the member set, and set external_reference_excluded "
        "true. Never invent an enclosing room/surface/union region as a structure. "
        f"Reference coverage policy: {REFERENCE_COVERAGE_POLICY}. "
        "Give exactly one observations record for EVERY candidate common_visible_frame_id, "
        "including frames not selected in witness.frame_ids, with a tight physical "
        "structure bbox or null, boundary_status bounded_visible_structure/uncertain/"
        "arbitrary_enclosing_region, boundary_evidence, and limitation. For both pair "
        "members in EACH candidate common-visible frame give exactly one member_relations record bound "
        "to frame_id and anchor_cluster_id, a permitted relation, supported/uncertain/"
        "contradicted outcome, separately localized member_locus and reference_locus "
        "normalized boxes (or null when unresolved), boundary evidence and limitation. "
        "The loci must lie within their respective independently localized scopes. "
        "Direct physical connection requires touching/overlapping loci; organization "
        "around a bounded external fixture does not require member boxes to overlap. "
        "For passive collections the reference must equal the collection's excluded "
        "fixture. If a reference is not visible or cannot be localized, use the existing "
        "boundary_status=uncertain with bbox=null and explain not_visible or the actual "
        "limitation; use uncertain relations and null loci when unresolved. Do not "
        "copy or interpolate boxes to complete coverage. These are valid nonpositive "
        "observations, not retry triggers. witness.frame_ids still cites at least two "
        "positive frames. Additional uncertain frames contribute no cohesion; the "
        "resolver requires at least two frames with positive reference and both member "
        "relations in BOTH plans across all pairs, regardless of which positive subset "
        "each planner cites. Arbitrary enclosing references and contradicted relations "
        "block the candidate. "
        "These boxes cannot prove pixel truth by themselves; describe actual boundaries "
        "and organizational evidence, never use bbox enclosure as positive cohesion.\n\n"
        f"Allowed cohesion/member-relation mapping: {json.dumps({k: sorted(v) for k, v in RELATIONS_BY_COHESION.items()}, sort_keys=True)}.\n\n"
        f"Allowed assembly/cohesion mapping: {cohesion_map}.\n\n"
        "For every family, review every context anchor supplied for that candidate exactly "
        "once in context_exclusion_reviews over all frames. The family is clear only when "
        "each context anchor is directly excluded from the candidate's minimal cohesive "
        "closure; uncertain membership must be recorded and blocks coarsening. Confirm "
        "minimal_cohesive_closure_confirmed only for the exact candidate anchors. If the "
        "candidate lacks two-frame positive cohesion, has observed or uncertain "
        "independence, triggers a protected relation, or cannot exclude its context, emit "
        "a structured exclusion rather than stretching a family.\n\n"
        "Do not output a canonical name or name suggestion. The resolver derives a "
        "shared semantic core deterministically when one is safe and otherwise uses "
        f"this fixed assembly-kind fallback table: {name_map}.\n\n"
        "Chronological attachment mapping:\n"
        + json.dumps(shot_manifest["reference_frames"], indent=2)
        + "\n\nAllowed input paths:\n"
        + json.dumps(allowed_paths, indent=2)
        + "\n\nThe following general entity-scope policy remains authoritative:\n"
        + policy_text
        + "\n\naccepted_only_source_blind_inventory:\n"
        + json.dumps(accepted_view, indent=2, ensure_ascii=False)
    )


def _validate_visual_evidence(
    evidence: Sequence[Mapping[str, Any]],
    *,
    valid_frames: set[int],
    label: str,
) -> set[int]:
    frame_ids = []
    for index, item in enumerate(evidence):
        _require_exact_keys(
            item, VISUAL_EVIDENCE_KEYS, f"{label} evidence[{index}]"
        )
        frame_id = item["frame_id"]
        if frame_id not in valid_frames:
            raise AcceptedAssemblyError(f"{label} cites unknown frame {frame_id}")
        if not isinstance(item["description"], str) or not item["description"].strip():
            raise AcceptedAssemblyError(f"{label} has an empty evidence description")
        frame_ids.append(frame_id)
    return set(frame_ids)


def _validate_plan_header(
    plan: Mapping[str, Any],
    *,
    shot_id: str,
    accepted_cluster_ids: set[str],
    candidate_ids: set[str],
) -> None:
    _require_exact_keys(plan, TOP_LEVEL_KEYS, "plan")
    if plan["protocol_version"] != PLAN_PROTOCOL:
        raise AcceptedAssemblyError("Unexpected plan protocol_version")
    if plan["shot_id"] != shot_id:
        raise AcceptedAssemblyError("Plan changed shot_id")
    reviewed = _require_unique(
        plan["reviewed_accepted_cluster_ids"], "reviewed accepted cluster IDs"
    )
    if reviewed != accepted_cluster_ids:
        raise AcceptedAssemblyError(
            "reviewed_accepted_cluster_ids must cover accepted input exactly"
        )
    reviewed_candidates = _require_unique(
        plan["reviewed_candidate_ids"], "reviewed candidate IDs"
    )
    if reviewed_candidates != candidate_ids:
        raise AcceptedAssemblyError(
            "reviewed_candidate_ids must cover candidate bank exactly"
        )
    _require_unique(
        [family["family_id"] for family in plan["families"]], "family IDs"
    )


def _validate_collection_scope(family, accepted_by_id, common_visible):
    review = family["collection_scope_review"]
    if family["assembly_kind"] != "passive_homogeneous_collection":
        if review is not None:
            raise AcceptedAssemblyError("Non-collection family requires null collection_scope_review")
        return
    if not isinstance(review, Mapping):
        raise AcceptedAssemblyError("Passive collection requires structured collection_scope_review")
    _require_exact_keys(review, COLLECTION_SCOPE_KEYS, "collection_scope_review")
    fixture_id = review["fixture_anchor_cluster_id"]
    if fixture_id not in accepted_by_id or fixture_id in family["anchor_cluster_ids"]:
        raise AcceptedAssemblyError("Collection fixture must be an accepted external anchor")
    if any(review[key] is not True for key in COLLECTION_SCOPE_CHECKS):
        raise AcceptedAssemblyError("Collection scope and exclusions must be confirmed")
    for key in ("content_category", "description"):
        if not isinstance(review[key], str) or not review[key].strip():
            raise AcceptedAssemblyError("Collection category and scope description must be nonempty")
    fixture_visible = {
        item["frame_id"] for item in accepted_by_id[fixture_id]["frame_presence"]
        if item["status"] == "visible"
    }
    evidence_frames = _validate_visual_evidence(
        review["evidence"], valid_frames=set(common_visible) & fixture_visible,
        label="collection scope",
    )
    if len(evidence_frames) < 2:
        raise AcceptedAssemblyError("Collection scope requires two joint-visible fixture/content frames")


# Structured reviews bind new pixel judgments to frozen accepted identities.
SCOPE_OBSERVATION_KEYS = {
    "frame_id", "correspondence", "coverage", "bbox_xyxy_normalized",
    "boundary_evidence", "limitation",
}
REFERENCE_REVIEW_KEYS = {
    "reference_type", "reference_anchor_cluster_id", "external_reference_excluded",
    "observations", "member_relations",
}
REFERENCE_OBSERVATION_KEYS = {
    "frame_id", "bbox_xyxy_normalized", "boundary_status", "boundary_evidence", "limitation",
}
MEMBER_RELATION_KEYS = {
    "frame_id", "anchor_cluster_id", "relation", "outcome",
    "member_locus_bbox_xyxy_normalized", "reference_locus_bbox_xyxy_normalized",
    "boundary_evidence", "limitation",
}
RELATIONS_BY_COHESION = {
    "shared_continuous_housing_or_joint": {"reference_itself", "part_of_housing_or_joint"},
    "same_small_container_functional_unit": {"reference_itself", "contained_in_or_inserted_into"},
    "common_fixed_mounting_or_array": {"reference_itself", "mounted_on_common_structure"},
    "stable_complementary_same_role_array_about_external_reference": {"complementary_array_member_about"},
    "direct_mechanical_or_operational_coupling": {"reference_itself", "directly_coupled_to"},
    "same_fixture_bounded_passive_homogeneous_content": {"fixture_organized_passive_content"},
}


def _validate_bbox(box, label):
    if box is None:
        return
    if (not isinstance(box, list) or len(box) != 4
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in box)
            or not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1)):
        raise AcceptedAssemblyError(f"{label}: invalid normalized bbox")


def _require_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise AcceptedAssemblyError(f"{label}: nonempty text required")


def _validate_anchor_scope(unit, common_visible):
    review = unit["anchor_scope_review"]
    _require_exact_keys(review, {"observations"}, "anchor_scope_review")
    observations = review["observations"]
    if _require_unique([o["frame_id"] for o in observations], "anchor scope frames") != common_visible:
        raise AcceptedAssemblyError("Anchor scope must cover all common visible frames exactly once")
    for obs in observations:
        _require_exact_keys(obs, SCOPE_OBSERVATION_KEYS, "anchor scope observation")
        if obs["correspondence"] not in {"matched", "uncertain", "different_content"}:
            raise AcceptedAssemblyError("Invalid anchor correspondence")
        if obs["coverage"] not in {"complete_visible_claim", "partial", "unresolved"}:
            raise AcceptedAssemblyError("Invalid anchor coverage")
        _validate_bbox(obs["bbox_xyxy_normalized"], "anchor scope")
        _require_text(obs["boundary_evidence"], "anchor boundary evidence")
        _require_text(obs["limitation"], "anchor scope limitation (use 'none' if none)")
        if (obs["correspondence"] == "matched" and obs["coverage"] == "complete_visible_claim"
                and obs["bbox_xyxy_normalized"] is None):
            raise AcceptedAssemblyError("Matched complete anchor scope requires a bbox")


def _validate_reference_review(witness, family, accepted_by_id):
    review = witness["reference_review"]
    _require_exact_keys(review, REFERENCE_REVIEW_KEYS, "reference_review")
    ref_id = review["reference_anchor_cluster_id"]
    if ref_id not in accepted_by_id:
        raise AcceptedAssemblyError("Reference must bind an existing accepted anchor")
    if review["reference_type"] not in {"accepted_anchor", "visible_intrinsic_structure"}:
        raise AcceptedAssemblyError("Invalid reference_type")
    member_ids = set(family["anchor_cluster_ids"])
    external = ref_id not in member_ids
    if review["reference_type"] == "visible_intrinsic_structure" and external:
        raise AcceptedAssemblyError("Intrinsic structure must belong to a candidate member")
    if review["external_reference_excluded"] is not external:
        raise AcceptedAssemblyError("External reference must remain excluded from members")
    if witness["kind"] == "stable_complementary_same_role_array_about_external_reference" and not external:
        raise AcceptedAssemblyError("External-reference array requires an excluded accepted fixture")
    if family["assembly_kind"] == "passive_homogeneous_collection" and (
        not external or ref_id != family["collection_scope_review"]["fixture_anchor_cluster_id"]
    ):
        raise AcceptedAssemblyError("Collection cohesion must reference its exact excluded fixture")
    frames = set(witness["frame_ids"])
    coverage_frames = set(family["common_visible_frame_ids"])
    ref_visible = {p["frame_id"] for p in accepted_by_id[ref_id]["frame_presence"] if p["status"] == "visible"}
    if not frames <= ref_visible:
        raise AcceptedAssemblyError("Reference must be visible in every witness frame")
    observations = review["observations"]
    if _require_unique([o["frame_id"] for o in observations], "reference frames") != coverage_frames:
        raise AcceptedAssemblyError("Reference observations must cover all candidate common visible frames exactly once")
    for obs in observations:
        _require_exact_keys(obs, REFERENCE_OBSERVATION_KEYS, "reference observation")
        if obs["boundary_status"] not in {"bounded_visible_structure", "uncertain", "arbitrary_enclosing_region"}:
            raise AcceptedAssemblyError("Invalid reference boundary_status")
        _validate_bbox(obs["bbox_xyxy_normalized"], "reference")
        _require_text(obs["boundary_evidence"], "reference boundary evidence")
        _require_text(obs["limitation"], "reference limitation")
        if obs["boundary_status"] == "bounded_visible_structure" and obs["bbox_xyxy_normalized"] is None:
            raise AcceptedAssemblyError("Bounded visible reference requires a bbox")
        if obs["boundary_status"] == "bounded_visible_structure" and obs["frame_id"] not in ref_visible:
            raise AcceptedAssemblyError("Positive reference observation requires its accepted anchor visible in that frame")
    anchor_by_unit = {u["unit_id"]: u["anchor_cluster_id"] for u in family["content_units"]}
    edge_anchors = {anchor_by_unit[witness["unit_a_id"]], anchor_by_unit[witness["unit_b_id"]]}
    relations = review["member_relations"]
    keys = _require_unique([(r["frame_id"], r["anchor_cluster_id"]) for r in relations], "member/frame relations")
    if keys != {(frame, anchor) for frame in coverage_frames for anchor in edge_anchors}:
        raise AcceptedAssemblyError("Reference relations must cover both exact anchors in every candidate common visible frame")
    for relation in relations:
        _require_exact_keys(relation, MEMBER_RELATION_KEYS, "member relation")
        if relation["relation"] not in RELATIONS_BY_COHESION[witness["kind"]]:
            raise AcceptedAssemblyError("Relation incompatible with positive cohesion kind")
        if relation["relation"] == "reference_itself" and (
            relation["anchor_cluster_id"] != ref_id or review["reference_type"] != "accepted_anchor"
        ):
            raise AcceptedAssemblyError("reference_itself requires the exact reference anchor")
        if relation["outcome"] not in {"supported", "uncertain", "contradicted"}:
            raise AcceptedAssemblyError("Invalid member relation outcome")
        for key in ("member_locus_bbox_xyxy_normalized", "reference_locus_bbox_xyxy_normalized"):
            _validate_bbox(relation[key], "relation locus")
            if relation["outcome"] == "supported" and relation[key] is None:
                raise AcceptedAssemblyError("Supported relation needs both localized loci")
        _require_text(relation["boundary_evidence"], "relation boundary evidence")
        _require_text(relation["limitation"], "relation limitation")


def _contains_box(outer, inner):
    return outer is not None and inner is not None and (
        outer[0] <= inner[0] < inner[2] <= outer[2]
        and outer[1] <= inner[1] < inner[3] <= outer[3]
    )


def _loci_touch(first, second):
    return (first is not None and second is not None
            and max(first[0], second[0]) <= min(first[2], second[2]) + 1e-6
            and max(first[1], second[1]) <= min(first[3], second[3]) + 1e-6)


def _scope_boxes(family):
    return {u["anchor_cluster_id"]: {
        o["frame_id"]: o["bbox_xyxy_normalized"] for o in u["anchor_scope_review"]["observations"]
    } for u in family["content_units"]}


def _anchor_scopes_are_clear(family):
    common = set(family["common_visible_frame_ids"])
    if len(common) < 2:
        return False
    for unit in family["content_units"]:
        observations = unit.get("anchor_scope_review", {}).get("observations", [])
        if len(observations) != len(common) or {o["frame_id"] for o in observations} != common:
            return False
        if any(o["correspondence"] != "matched" or o["coverage"] != "complete_visible_claim"
               or o["bbox_xyxy_normalized"] is None for o in observations):
            return False
    return True


def _reference_frame_analysis(family, witness):
    """Separate missing evidence from explicit negative/geometric contradictions."""
    boxes = _scope_boxes(family)
    review = witness["reference_review"]
    ref_id = review["reference_anchor_cluster_id"]
    observations = {o["frame_id"]: o for o in review["observations"]}
    relations_by_frame = {}
    for relation in review["member_relations"]:
        relations_by_frame.setdefault(relation["frame_id"], []).append(relation)
    positive = set()
    for frame, observation in observations.items():
        bbox = observation["bbox_xyxy_normalized"]
        bounded = observation["boundary_status"] == "bounded_visible_structure" and bbox is not None
        if observation["boundary_status"] == "arbitrary_enclosing_region":
            return set(), True
        if bounded and ref_id in boxes:
            # Intrinsic structure must actually fit its named member. A broad
            # union of arbitrary members cannot stand in for a physical joint.
            if review["reference_type"] == "visible_intrinsic_structure":
                if not _contains_box(boxes[ref_id][frame], bbox):
                    return set(), True
            elif not _boxes_correspond(boxes[ref_id][frame], bbox):
                return set(), True
        frame_relations = relations_by_frame.get(frame, [])
        for relation in frame_relations:
            anchor = relation["anchor_cluster_id"]
            if relation["outcome"] == "contradicted":
                return set(), True
            if relation["outcome"] == "uncertain":
                continue
            if not _contains_box(boxes[anchor][frame], relation["member_locus_bbox_xyxy_normalized"]):
                return set(), True
            if bounded and not _contains_box(bbox, relation["reference_locus_bbox_xyxy_normalized"]):
                return set(), True
            if relation["relation"] == "fixture_organized_passive_content":
                if bounded and not _contains_box(bbox, relation["member_locus_bbox_xyxy_normalized"]):
                    return set(), True
            elif relation["relation"] != "complementary_array_member_about":
                if not _loci_touch(relation["member_locus_bbox_xyxy_normalized"],
                                   relation["reference_locus_bbox_xyxy_normalized"]):
                    return set(), True
        if bounded and len(frame_relations) == 2 and all(r["outcome"] == "supported" for r in frame_relations):
            positive.add(frame)
    return positive, False


def _scope_is_clear(family):
    """Uncertain reference frames are nonpositive, never fabricated or retried."""
    if not _anchor_scopes_are_clear(family):
        return False
    common = set(family["common_visible_frame_ids"])
    anchors_by_unit = {u["unit_id"]: u["anchor_cluster_id"] for u in family["content_units"]}
    for witness in family["cohesion_witnesses"]:
        review = witness["reference_review"]
        observations = review["observations"]
        pair = {anchors_by_unit[witness["unit_a_id"]], anchors_by_unit[witness["unit_b_id"]]}
        relation_keys = [(r["frame_id"], r["anchor_cluster_id"]) for r in review["member_relations"]]
        if (len(observations) != len(common) or {o["frame_id"] for o in observations} != common
                or len(relation_keys) != 2 * len(common)
                or set(relation_keys) != {(frame, anchor) for frame in common for anchor in pair}):
            return False
        positive, contradicted = _reference_frame_analysis(family, witness)
        if (contradicted or len(positive) < 2 or len(set(witness["frame_ids"])) < 2
                or not set(witness["frame_ids"]) <= positive):
            return False
    return True


def _boxes_correspond(first, second):
    """Same-ID scope compatibility only, never A/B overlap as cohesion evidence."""
    if first is None or second is None:
        return False
    iou, ios = _box_intersection_metrics(tuple(first), tuple(second))
    return not (iou <= GROSS_SPATIAL_MAX_IOU and ios <= GROSS_SPATIAL_MAX_INTERSECTION_OVER_SMALLER)


def _persistent_localization_conflict(first, second):
    frames = sorted(f for f in set(first) & set(second) if first[f] is not None and second[f] is not None)
    if len(frames) < 2:
        return False
    incompatible = sum(not _boxes_correspond(first[f], second[f]) for f in frames)
    return incompatible >= max(2, math.ceil(len(frames) * GROSS_SPATIAL_MIN_INCOMPATIBLE_RATIO))


def _joint_scope_audit_result(first, second):
    """Audit two independent scopes without interpreting descriptions as truth."""
    if not _anchor_scopes_are_clear(first) or not _anchor_scopes_are_clear(second):
        return {"clear": False, "basis": "anchor_or_reference_scope_not_complete"}
    first_boxes, second_boxes = _scope_boxes(first), _scope_boxes(second)
    if set(first_boxes) != set(second_boxes):
        return {"clear": False, "basis": "anchor_scope_identity_disagreement"}
    jointly_localized_frames = set(first["common_visible_frame_ids"]) & set(second["common_visible_frame_ids"])
    for anchor in first_boxes:
        jointly_localized_frames &= {f for f in set(first_boxes[anchor]) & set(second_boxes[anchor])
                                    if _boxes_correspond(first_boxes[anchor][f], second_boxes[anchor][f])}
    conflicts = [a for a in sorted(first_boxes) if _persistent_localization_conflict(first_boxes[a], second_boxes[a])]
    if conflicts:
        return {"clear": False, "basis": "same_anchor_localization_conflict", "anchor_cluster_ids": conflicts}
    def by_pair(family):
        ids = {u["unit_id"]: u["anchor_cluster_id"] for u in family["content_units"]}
        return {tuple(sorted((ids[w["unit_a_id"]], ids[w["unit_b_id"]]))): w for w in family["cohesion_witnesses"]}
    first_pairs, second_pairs = by_pair(first), by_pair(second)
    if set(first_pairs) != set(second_pairs):
        return {"clear": False, "basis": "cohesion_pair_identity_disagreement"}
    reference_frame_reviews = []
    for pair in sorted(first_pairs):
        a, b = first_pairs[pair], second_pairs[pair]
        ar, br = a["reference_review"], b["reference_review"]
        if (a["kind"], ar["reference_type"], ar["reference_anchor_cluster_id"]) != (b["kind"], br["reference_type"], br["reference_anchor_cluster_id"]):
            return {"clear": False, "basis": "cohesion_reference_identity_disagreement", "anchor_cluster_ids": list(pair)}
        ab = {o["frame_id"]: o["bbox_xyxy_normalized"] for o in ar["observations"]
              if o["boundary_status"] == "bounded_visible_structure" and o["bbox_xyxy_normalized"] is not None}
        bb = {o["frame_id"]: o["bbox_xyxy_normalized"] for o in br["observations"]
              if o["boundary_status"] == "bounded_visible_structure" and o["bbox_xyxy_normalized"] is not None}
        common_reference_frames = set(ab) & set(bb)
        if len(common_reference_frames) < 2:
            return {"clear": False, "basis": "insufficient_common_reference_frames", "anchor_cluster_ids": list(pair),
                    "common_reference_frame_ids": sorted(common_reference_frames),
                    "first_localized_reference_frame_ids": sorted(ab), "second_localized_reference_frame_ids": sorted(bb)}
        if any(len(review["observations"]) != len(family["common_visible_frame_ids"])
               or {o["frame_id"] for o in review["observations"]} != set(family["common_visible_frame_ids"])
               for family, review in ((first, ar), (second, br))):
            return {"clear": False, "basis": "incomplete_reference_frame_coverage", "anchor_cluster_ids": list(pair)}
        if _persistent_localization_conflict(ab, bb):
            return {"clear": False, "basis": "same_reference_localization_conflict", "anchor_cluster_ids": list(pair),
                    "common_reference_frame_ids": sorted(common_reference_frames)}
        ap, ac = _reference_frame_analysis(first, a)
        bp, bc = _reference_frame_analysis(second, b)
        if ac or bc:
            return {"clear": False, "basis": "anchor_or_reference_scope_not_complete"}
        joint_positive = ap & bp & {f for f in common_reference_frames if _boxes_correspond(ab[f], bb[f])}
        jointly_localized_frames &= joint_positive
        reference_frame_reviews.append({"anchor_cluster_ids": list(pair),
                                        "common_reference_frame_ids": sorted(common_reference_frames),
                                        "joint_positive_reference_frame_ids": sorted(joint_positive)})
        ak = {(r["frame_id"], r["anchor_cluster_id"]): r["relation"] for r in ar["member_relations"] if r["outcome"] == "supported"}
        bk = {(r["frame_id"], r["anchor_cluster_id"]): r["relation"] for r in br["member_relations"] if r["outcome"] == "supported"}
        if any(ak[k] != bk[k] for k in set(ak) & set(bk)):
            return {"clear": False, "basis": "reference_relation_disagreement", "anchor_cluster_ids": list(pair)}
    if not _scope_is_clear(first) or not _scope_is_clear(second):
        return {"clear": False, "basis": "anchor_or_reference_scope_not_complete"}
    if len(jointly_localized_frames) < 2:
        return {"clear": False, "basis": "insufficient_jointly_localized_cohesion_frames",
                "jointly_localized_frame_ids": sorted(jointly_localized_frames)}
    return {"clear": True, "basis": "complete_independent_anchor_and_reference_scope",
            "jointly_localized_frame_ids": sorted(jointly_localized_frames),
            "reference_frame_reviews": reference_frame_reviews,
            "limitation": "Structured agreement and geometry do not establish pixel truth; correlated localization or boundary errors remain possible."}


def _joint_scope_audit(first, second):
    return {"reference_coverage_policy": REFERENCE_COVERAGE_POLICY,
            **_joint_scope_audit_result(first, second)}


def validate_plan(
    plan: Mapping[str, Any],
    *,
    shot_id: str,
    baseline: Mapping[str, Any],
    accepted_view: Mapping[str, Any],
    valid_frame_ids: Sequence[int],
    base_protocol: str,
) -> None:
    """Validate one planner's evidence without selecting a partition."""
    valid_frames = _require_unique(valid_frame_ids, "reference frame IDs")
    accepted = _eligible_clusters(baseline)
    accepted_by_id = {item["cluster_id"]: item for item in accepted}
    if len(accepted_by_id) != len(accepted):
        raise AcceptedAssemblyError("Baseline has duplicate accepted cluster IDs")
    candidate_bank = accepted_view.get("candidate_bank")
    if not isinstance(candidate_bank, Mapping):
        raise AcceptedAssemblyError("Accepted-only view has no candidate bank")
    _validate_candidate_bank(
        candidate_bank,
        shot_id=shot_id,
        accepted_cluster_ids=set(accepted_by_id),
    )
    expected_view = planner_baseline_view(
        baseline,
        candidate_bank=candidate_bank,
        shot_id=shot_id,
        base_protocol=base_protocol,
    )
    if accepted_view != expected_view:
        raise AcceptedAssemblyError("Accepted-only model view was modified")
    candidate_by_id = {
        item["candidate_id"]: item for item in candidate_bank["candidates"]
    }
    _validate_plan_header(
        plan,
        shot_id=shot_id,
        accepted_cluster_ids=set(accepted_by_id),
        candidate_ids=set(candidate_by_id),
    )

    family_candidate_ids = _require_unique(
        [item["candidate_id"] for item in plan["families"]],
        "family candidate IDs",
    )
    excluded_candidate_ids = _require_unique(
        [item["candidate_id"] for item in plan["excluded_candidates"]],
        "excluded candidate IDs",
    )
    if family_candidate_ids & excluded_candidate_ids:
        raise AcceptedAssemblyError(
            "A candidate cannot appear as both a family and an exclusion"
        )
    accounted_candidates = family_candidate_ids | excluded_candidate_ids
    if accounted_candidates != set(candidate_by_id):
        raise AcceptedAssemblyError(
            "Every candidate must be accounted for exactly once"
        )

    for index, exclusion in enumerate(plan["excluded_candidates"]):
        _require_exact_keys(
            exclusion,
            EXCLUDED_CANDIDATE_KEYS,
            f"excluded_candidates[{index}]",
        )
        candidate_id = exclusion["candidate_id"]
        if candidate_id not in candidate_by_id:
            raise AcceptedAssemblyError(
                f"excluded candidate cites unknown ID {candidate_id}"
            )
        anchors = _require_unique(
            exclusion["anchor_cluster_ids"],
            f"{candidate_id} excluded anchor cluster IDs",
        )
        if anchors != set(candidate_by_id[candidate_id]["anchor_cluster_ids"]):
            raise AcceptedAssemblyError(
                f"{candidate_id}: excluded record must preserve exact candidate anchors"
            )
        if exclusion["reason_code"] not in EXCLUDED_CANDIDATE_REASON_CODES:
            raise AcceptedAssemblyError(
                f"{candidate_id}: unknown exclusion reason_code"
            )
        _validate_visual_evidence(
            exclusion["evidence"],
            valid_frames=valid_frames,
            label=f"{candidate_id} exclusion",
        )
        if not isinstance(exclusion["reason"], str) or not exclusion[
            "reason"
        ].strip():
            raise AcceptedAssemblyError(
                f"{candidate_id}: exclusion reason must be nonempty"
            )

    for family in plan["families"]:
        family_id = family["family_id"]
        _require_exact_keys(family, FAMILY_KEYS, family_id)
        candidate_id = family["candidate_id"]
        if candidate_id not in candidate_by_id:
            raise AcceptedAssemblyError(
                f"{family_id}: family cites an unknown candidate"
            )
        if family["assembly_kind"] not in ASSEMBLY_KIND_NAMES:
            raise AcceptedAssemblyError(f"{family_id}: unknown assembly_kind")
        if family["scope_review_complete"] is not True:
            raise AcceptedAssemblyError(f"{family_id}: scope review is incomplete")
        if family["minimal_cohesive_closure_confirmed"] is not True:
            raise AcceptedAssemblyError(
                f"{family_id}: minimal cohesive closure is not confirmed"
            )

        anchor_ids = _require_unique(
            family["anchor_cluster_ids"], f"{family_id} anchor cluster IDs"
        )
        if len(anchor_ids) < 2:
            raise AcceptedAssemblyError(f"{family_id}: needs at least two anchors")
        if not anchor_ids <= set(accepted_by_id):
            raise AcceptedAssemblyError(f"{family_id}: cites a non-accepted anchor")
        if anchor_ids != set(candidate_by_id[candidate_id]["anchor_cluster_ids"]):
            raise AcceptedAssemblyError(
                f"{family_id}: family anchors must exactly equal candidate anchors"
            )

        units = family["content_units"]
        unit_ids = _require_unique(
            [item["unit_id"] for item in units], f"{family_id} content unit IDs"
        )
        anchor_by_unit: Dict[str, Mapping[str, Any]] = {}
        unit_anchor_ids = []
        for index, unit in enumerate(units):
            _require_exact_keys(
                unit, CONTENT_UNIT_KEYS, f"{family_id} content_units[{index}]"
            )
            if not isinstance(unit["description"], str) or not unit[
                "description"
            ].strip():
                raise AcceptedAssemblyError(
                    f"{family_id}/{unit['unit_id']}: empty unit description"
                )
            anchor_id = unit["anchor_cluster_id"]
            if anchor_id not in accepted_by_id:
                raise AcceptedAssemblyError(
                    f"{family_id}/{unit['unit_id']}: unknown anchor"
                )
            anchor_by_unit[unit["unit_id"]] = accepted_by_id[anchor_id]
            unit_anchor_ids.append(anchor_id)
        if _require_unique(
            unit_anchor_ids, f"{family_id} unit anchor cluster IDs"
        ) != anchor_ids:
            raise AcceptedAssemblyError(
                f"{family_id}: content units must map every anchor exactly once"
            )

        visible_by_unit = {
            unit_id: {
                item["frame_id"]
                for item in cluster["frame_presence"]
                if item["status"] == "visible"
            }
            for unit_id, cluster in anchor_by_unit.items()
        }
        common_visible = set.intersection(
            *(set(items) for items in visible_by_unit.values())
        )
        supplied_common = _require_unique(
            family["common_visible_frame_ids"],
            f"{family_id} common visible frame IDs",
        )
        if len(supplied_common) < 2 or supplied_common != common_visible:
            raise AcceptedAssemblyError(
                f"{family_id}: common_visible_frame_ids must exactly equal the "
                "at-least-two-frame accepted-anchor intersection"
            )
        if not common_visible <= valid_frames:
            raise AcceptedAssemblyError(
                f"{family_id}: anchor presence cites unknown frames"
            )

        _validate_collection_scope(family, accepted_by_id, common_visible)

        for unit in units:
            _validate_anchor_scope(unit, common_visible)
            evidence_frames = _validate_visual_evidence(
                unit["pixel_evidence"],
                valid_frames=valid_frames,
                label=f"{family_id}/{unit['unit_id']}",
            )
            if not evidence_frames or not evidence_frames <= visible_by_unit[
                unit["unit_id"]
            ]:
                raise AcceptedAssemblyError(
                    f"{family_id}/{unit['unit_id']}: pixel evidence must cite "
                    "frames where that accepted anchor is visible"
                )

        required_pairs = {
            tuple(sorted(pair)) for pair in combinations(sorted(unit_ids), 2)
        }
        witness_ids = _require_unique(
            [item["witness_id"] for item in family["cohesion_witnesses"]],
            f"{family_id} cohesion witness IDs",
        )
        if not witness_ids:
            raise AcceptedAssemblyError(f"{family_id}: missing cohesion witnesses")
        cohesion_pairs = []
        allowed_cohesion = COHESION_KINDS_BY_ASSEMBLY[family["assembly_kind"]]
        for index, witness in enumerate(family["cohesion_witnesses"]):
            _require_exact_keys(
                witness,
                COHESION_WITNESS_KEYS,
                f"{family_id} cohesion_witnesses[{index}]",
            )
            edge = _pair(witness["unit_a_id"], witness["unit_b_id"])
            if not set(edge) <= unit_ids:
                raise AcceptedAssemblyError(
                    f"{family_id}: cohesion witness cites an unknown unit"
                )
            if witness["kind"] not in allowed_cohesion:
                raise AcceptedAssemblyError(
                    f"{family_id}: cohesion kind is incompatible with assembly_kind"
                )
            frames = _require_unique(
                witness["frame_ids"],
                f"{family_id}/{witness['witness_id']} frame IDs",
            )
            if len(frames) < 2 or not frames <= common_visible:
                raise AcceptedAssemblyError(
                    f"{family_id}/{witness['witness_id']}: cohesion needs two "
                    "family-common visible frames"
                )
            if not isinstance(witness["description"], str) or not witness[
                "description"
            ].strip():
                raise AcceptedAssemblyError(
                    f"{family_id}/{witness['witness_id']}: empty description"
                )
            _validate_reference_review(witness, family, accepted_by_id)
            cohesion_pairs.append(edge)
        if _require_unique(
            cohesion_pairs, f"{family_id} cohesion witness pairs"
        ) != required_pairs:
            raise AcceptedAssemblyError(
                f"{family_id}: cohesion must cover every unordered unit pair exactly once"
            )

        pair_reviews = family["pairwise_independence_reviews"]
        review_pairs = []
        for index, review in enumerate(pair_reviews):
            _require_exact_keys(
                review,
                PAIR_REVIEW_KEYS,
                f"{family_id} pairwise_independence_reviews[{index}]",
            )
            edge = _pair(review["unit_a_id"], review["unit_b_id"])
            if not set(edge) <= unit_ids:
                raise AcceptedAssemblyError(
                    f"{family_id}: independence review cites an unknown unit"
                )
            reviewed_frames = _require_unique(
                review["reviewed_frame_ids"],
                f"{family_id}/{edge} reviewed frame IDs",
            )
            if reviewed_frames != valid_frames:
                raise AcceptedAssemblyError(
                    f"{family_id}/{edge}: independence review must cover every frame"
                )
            checks = review["checks"]
            check_kinds = _require_unique(
                [item["kind"] for item in checks],
                f"{family_id}/{edge} independence check kinds",
            )
            if check_kinds != INDEPENDENCE_KINDS:
                raise AcceptedAssemblyError(
                    f"{family_id}/{edge}: independence check set is incomplete"
                )
            for check_index, check in enumerate(checks):
                _require_exact_keys(
                    check,
                    INDEPENDENCE_CHECK_KEYS,
                    f"{family_id}/{edge} checks[{check_index}]",
                )
                evidence_frames = _validate_visual_evidence(
                    check["evidence"],
                    valid_frames=valid_frames,
                    label=f"{family_id}/{edge}/{check['kind']}",
                )
                outcome = check["outcome"]
                if outcome not in {"not_observed", "observed", "uncertain"}:
                    raise AcceptedAssemblyError(
                        f"{family_id}/{edge}: invalid independence outcome"
                    )
                if outcome == "not_observed" and evidence_frames:
                    raise AcceptedAssemblyError(
                        f"{family_id}/{edge}: not_observed must not invent evidence"
                    )
                if outcome != "not_observed" and not evidence_frames:
                    raise AcceptedAssemblyError(
                        f"{family_id}/{edge}: observed/uncertain needs evidence"
                    )
                if outcome == "observed" and not evidence_frames <= (
                    visible_by_unit[edge[0]] & visible_by_unit[edge[1]]
                ):
                    raise AcceptedAssemblyError(
                        f"{family_id}/{edge}: observed independence requires both "
                        "units visible"
                    )
                if (
                    outcome == "observed"
                    and check["kind"]
                    in {"relative_motion", "independent_trajectory"}
                    and len(evidence_frames) < 2
                ):
                    raise AcceptedAssemblyError(
                        f"{family_id}/{edge}: temporal independence needs two frames"
                    )
                if not isinstance(check["description"], str) or not check[
                    "description"
                ].strip():
                    raise AcceptedAssemblyError(
                        f"{family_id}/{edge}: empty independence description"
                    )
            review_pairs.append(edge)
        if _require_unique(
            review_pairs, f"{family_id} independence review pairs"
        ) != required_pairs:
            raise AcceptedAssemblyError(
                f"{family_id}: independence review must cover every pair exactly once"
            )

        protected = family["protected_relation_reviews"]
        protected_kinds = _require_unique(
            [item["kind"] for item in protected],
            f"{family_id} protected relation kinds",
        )
        if protected_kinds != PROTECTED_RELATION_KINDS:
            raise AcceptedAssemblyError(
                f"{family_id}: protected-relation review set is incomplete"
            )
        for index, review in enumerate(protected):
            _require_exact_keys(
                review,
                PROTECTED_REVIEW_KEYS,
                f"{family_id} protected_relation_reviews[{index}]",
            )
            evidence_frames = _validate_visual_evidence(
                review["evidence"],
                valid_frames=valid_frames,
                label=f"{family_id}/{review['kind']}",
            )
            outcome = review["outcome"]
            if outcome not in {"absent", "present", "uncertain"}:
                raise AcceptedAssemblyError(
                    f"{family_id}: invalid protected-relation outcome"
                )
            if outcome == "absent" and evidence_frames:
                raise AcceptedAssemblyError(
                    f"{family_id}: absent protected relation must have no evidence"
                )
            if outcome != "absent" and not evidence_frames:
                raise AcceptedAssemblyError(
                    f"{family_id}: present/uncertain protected relation needs evidence"
                )
            if not isinstance(review["description"], str) or not review[
                "description"
            ].strip():
                raise AcceptedAssemblyError(
                    f"{family_id}: empty protected-relation description"
                )

        expected_context_ids = set(
            candidate_by_id[candidate_id]["context_anchor_cluster_ids"]
        )
        context_reviews = family["context_exclusion_reviews"]
        supplied_context_ids = _require_unique(
            [item["context_anchor_cluster_id"] for item in context_reviews],
            f"{family_id} context-exclusion anchor IDs",
        )
        if supplied_context_ids != expected_context_ids:
            raise AcceptedAssemblyError(
                f"{family_id}: context reviews must cover candidate context exactly"
            )
        family_visible_union = set().union(*visible_by_unit.values())
        for index, review in enumerate(context_reviews):
            _require_exact_keys(
                review,
                CONTEXT_REVIEW_KEYS,
                f"{family_id} context_exclusion_reviews[{index}]",
            )
            context_id = review["context_anchor_cluster_id"]
            reviewed_frames = _require_unique(
                review["reviewed_frame_ids"],
                f"{family_id}/{context_id} reviewed frame IDs",
            )
            if reviewed_frames != valid_frames:
                raise AcceptedAssemblyError(
                    f"{family_id}/{context_id}: context review must cover every frame"
                )
            if review["outcome"] not in {
                "excluded_from_minimal_closure",
                "uncertain_membership",
            }:
                raise AcceptedAssemblyError(
                    f"{family_id}/{context_id}: invalid context-review outcome"
                )
            evidence_frames = _validate_visual_evidence(
                review["evidence"],
                valid_frames=valid_frames,
                label=f"{family_id}/{context_id} context review",
            )
            context_visible = {
                item["frame_id"]
                for item in accepted_by_id[context_id]["frame_presence"]
                if item["status"] == "visible"
            }
            if not evidence_frames or not evidence_frames <= (
                context_visible & family_visible_union
            ):
                raise AcceptedAssemblyError(
                    f"{family_id}/{context_id}: context review needs direct evidence "
                    "where context and at least one family anchor are visible"
                )
            if not isinstance(review["description"], str) or not review[
                "description"
            ].strip():
                raise AcceptedAssemblyError(
                    f"{family_id}/{context_id}: empty context-review description"
                )


def _family_is_clear(family: Mapping[str, Any]) -> bool:
    return _scope_is_clear(family) and all(
        check["outcome"] == "not_observed"
        for review in family["pairwise_independence_reviews"]
        for check in review["checks"]
    ) and all(
        review["outcome"] == "absent"
        for review in family["protected_relation_reviews"]
    ) and all(
        review["outcome"] == "excluded_from_minimal_closure"
        for review in family["context_exclusion_reviews"]
    )


def _anchors(family: Mapping[str, Any]) -> Tuple[str, ...]:
    return tuple(sorted(family["anchor_cluster_ids"]))


def select_consensus_resolutions(
    first_plan: Mapping[str, Any], second_plan: Mapping[str, Any],
    *, spatial_vetoes: Sequence[Mapping[str, Any]] = (),
) -> List[Dict[str, Any]]:
    """Resolve every mandatory candidate with an exact two-planner gate."""
    for label, plan in (("first", first_plan), ("second", second_plan)):
        if plan.get("protocol_version") != PLAN_PROTOCOL:
            raise AcceptedAssemblyError(f"{label} plan has the wrong protocol")
    if first_plan.get("shot_id") != second_plan.get("shot_id"):
        raise AcceptedAssemblyError("Planner shot IDs differ")
    if set(first_plan.get("reviewed_accepted_cluster_ids", [])) != set(
        second_plan.get("reviewed_accepted_cluster_ids", [])
    ):
        raise AcceptedAssemblyError("Planner reviewed-cluster sets differ")
    first_candidate_ids = set(first_plan.get("reviewed_candidate_ids", []))
    second_candidate_ids = set(second_plan.get("reviewed_candidate_ids", []))
    if first_candidate_ids != second_candidate_ids:
        raise AcceptedAssemblyError("Planner reviewed-candidate sets differ")

    family_by_plan = [
        {item["candidate_id"]: item for item in plan["families"]}
        for plan in (first_plan, second_plan)
    ]
    exclusion_by_plan = [
        {item["candidate_id"]: item for item in plan["excluded_candidates"]}
        for plan in (first_plan, second_plan)
    ]
    anchors_by_candidate: Dict[str, Tuple[str, ...]] = {}
    for candidate_id in sorted(first_candidate_ids):
        records = [
            mapping[candidate_id]
            for mapping in (*family_by_plan, *exclusion_by_plan)
            if candidate_id in mapping
        ]
        anchor_variants = {_anchors(item) for item in records}
        if len(anchor_variants) != 1:
            raise AcceptedAssemblyError(
                f"Planner candidate anchor sets differ for {candidate_id}"
            )
        anchors_by_candidate[candidate_id] = next(iter(anchor_variants))

    positive_candidate_ids = {
        candidate_id
        for candidate_id in first_candidate_ids
        if any(candidate_id in families and _family_is_clear(families[candidate_id])
               for families in family_by_plan)
        and not (candidate_id in family_by_plan[0] and candidate_id in family_by_plan[1]
                 and not _joint_scope_audit(family_by_plan[0][candidate_id], family_by_plan[1][candidate_id])["clear"])
        and not matching_spatial_vetoes(
            anchors_by_candidate[candidate_id], spatial_vetoes
        )
    }
    conflicted: set[str] = set()
    ordered_candidates = sorted(first_candidate_ids)
    for index, first_id in enumerate(ordered_candidates):
        if first_id not in positive_candidate_ids:
            continue
        for second_id in ordered_candidates[index + 1 :]:
            if second_id not in positive_candidate_ids:
                continue
            if set(anchors_by_candidate[first_id]) & set(
                anchors_by_candidate[second_id]
            ):
                conflicted.update((first_id, second_id))

    resolutions = []
    for candidate_id in ordered_candidates:
        anchor_set = anchors_by_candidate[candidate_id]
        first_family = family_by_plan[0].get(candidate_id)
        second_family = family_by_plan[1].get(candidate_id)
        first_ids = [first_family["family_id"]] if first_family else []
        second_ids = [second_family["family_id"]] if second_family else []
        assembly_kinds = sorted(
            {
                item["assembly_kind"]
                for item in (first_family, second_family)
                if item is not None
            }
        )
        status = "not_applied"
        assembly_kind = assembly_kinds[0] if len(assembly_kinds) == 1 else None
        vetoes = matching_spatial_vetoes(anchor_set, spatial_vetoes)
        scope_audit = _joint_scope_audit(first_family, second_family) if first_family and second_family else None
        if vetoes:
            basis = "gross_spatial_incompatibility_veto"
        elif candidate_id in conflicted:
            basis = "overlapping_or_nested_family_component"
        elif first_family is None or second_family is None:
            basis = "one_or_both_planners_excluded_candidate"
        elif first_family["assembly_kind"] != second_family["assembly_kind"]:
            basis = "assembly_kind_disagreement"
        elif (
            first_family["assembly_kind"] == "passive_homogeneous_collection"
            and first_family["collection_scope_review"]["fixture_anchor_cluster_id"]
            != second_family["collection_scope_review"]["fixture_anchor_cluster_id"]
        ):
            basis = "collection_fixture_disagreement"
        elif not scope_audit["clear"]:
            basis = scope_audit["basis"]
        elif not _family_is_clear(first_family) or not _family_is_clear(second_family):
            basis = "independence_or_protected_relation_not_unanimously_clear"
        else:
            status = "applied"
            basis = "exact_two_planner_consensus_with_complete_clear_reviews"
        resolutions.append(
            {
                "candidate_id": candidate_id,
                "reference_coverage_policy": REFERENCE_COVERAGE_POLICY,
                "anchor_scope_audit": scope_audit,
                **({"spatial_vetoes": vetoes} if vetoes else {}),
                "anchor_cluster_ids": list(anchor_set),
                "status": status,
                "assembly_kind": assembly_kind,
                "basis": basis,
                "first_planner_family_ids": first_ids,
                "second_planner_family_ids": second_ids,
                "first_planner_disposition": (
                    "family" if first_family is not None else "excluded"
                ),
                "second_planner_disposition": (
                    "family" if second_family is not None else "excluded"
                ),
            }
        )
    return resolutions


def _merge_frame_presence(
    clusters: Sequence[Mapping[str, Any]], valid_frame_ids: Sequence[int]
) -> List[Dict[str, Any]]:
    by_cluster = [
        {item["frame_id"]: item for item in cluster["frame_presence"]}
        for cluster in clusters
    ]
    result = []
    for frame_id in valid_frame_ids:
        statuses = [items[frame_id]["status"] for items in by_cluster]
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
                    "Conservative deterministic aggregation of frozen component "
                    f"presence states: {','.join(statuses)}."
                ),
            }
        )
    return result


def _merge_attributes(
    clusters: Sequence[Mapping[str, Any]],
    *,
    assembly_kind: str,
    evidence_frame_ids: Sequence[int],
) -> List[Dict[str, Any]]:
    per_cluster = [
        {
            (item["name"], item["value"]): item
            for item in cluster["final_entity"]["attributes"]
            if item["name"] not in {"graph_components", "assembly_kind"}
        }
        for cluster in clusters
    ]
    common_keys = (
        set.intersection(*(set(items) for items in per_cluster))
        if per_cluster
        else set()
    )
    merged = []
    for key in sorted(common_keys):
        values = [items[key] for items in per_cluster]
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
    confidence = min(
        cluster["final_entity"]["entity_confidence"] for cluster in clusters
    )
    components = _format_component_multiset(
        cluster["final_entity"]["name"].strip() for cluster in clusters
    )
    merged.extend(
        [
            {
                "name": "assembly_kind",
                "value": assembly_kind,
                "confidence": confidence,
                "evidence_frame_ids": list(evidence_frame_ids),
            },
            {
                "name": "graph_components",
                "value": components,
                "confidence": confidence,
                "evidence_frame_ids": list(evidence_frame_ids),
            },
        ]
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
        labels.append(
            representative if count == 1 else f"{count} × {representative}"
        )
    return "; ".join(labels)


def _consensus_evidence_frames(
    first_family: Mapping[str, Any], second_family: Mapping[str, Any]
) -> List[int]:
    return sorted(
        {
            frame_id
            for family in (first_family, second_family)
            for witness in family["cohesion_witnesses"]
            for frame_id in witness["frame_ids"]
        }
    )


def _consensus_evidence(
    first_family: Mapping[str, Any], second_family: Mapping[str, Any]
) -> List[Dict[str, Any]]:
    descriptions_by_frame: Dict[int, List[str]] = {}
    for family in (first_family, second_family):
        for witness in family["cohesion_witnesses"]:
            for frame_id in witness["frame_ids"]:
                descriptions_by_frame.setdefault(frame_id, []).append(
                    witness["description"].strip()
                )
    return [
        {
            "frame_id": frame_id,
            "coarse_locator": min(
                set(descriptions_by_frame[frame_id]),
                key=lambda value: (len(value), value.casefold(), value),
            ),
            "support_quality": "strong",
        }
        for frame_id in sorted(descriptions_by_frame)
    ]


def _build_merged_cluster(
    *,
    anchor_ids: Tuple[str, ...],
    assembly_kind: str,
    first_family: Mapping[str, Any],
    second_family: Mapping[str, Any],
    baseline_by_id: Mapping[str, Mapping[str, Any]],
    baseline_order: Mapping[str, int],
    valid_frame_ids: Sequence[int],
) -> Dict[str, Any]:
    clusters = sorted(
        (baseline_by_id[item] for item in anchor_ids),
        key=lambda item: baseline_order[item["cluster_id"]],
    )
    evidence_frames = _consensus_evidence_frames(first_family, second_family)
    canonical_name = deterministic_merged_name(clusters, assembly_kind)
    confidence = min(
        cluster["final_entity"]["entity_confidence"] for cluster in clusters
    )
    cluster_key = json.dumps(
        {"anchors": list(anchor_ids), "assembly_kind": assembly_kind},
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "cluster_id": f"ac_{hashlib.sha256(cluster_key.encode()).hexdigest()[:12]}",
        "anonymous_proposal_ids": sorted(
            {
                proposal_id
                for cluster in clusters
                for proposal_id in cluster["anonymous_proposal_ids"]
            }
        ),
        "canonical_name": canonical_name,
        "aliases": [canonical_name],
        "granularity": "compact_composite_group",
        "adjudicator_evidence": _consensus_evidence(
            first_family, second_family
        ),
        "frame_presence": _merge_frame_presence(clusters, valid_frame_ids),
        "identity_status": "resolved",
        "decision": "accept",
        "decision_reason": (
            "Deterministic mandatory-candidate graph-node coarsening backed by "
            "exact two-planner consensus, complete pairwise original-frame "
            "cohesion, and clear independence, protected-relation, and context "
            "exclusion reviews."
        ),
        "uncertainty_flags": sorted(
            {
                flag
                for cluster in clusters
                for flag in cluster["uncertainty_flags"]
            }
            | {"accepted_only_graph_partition_coarsened"}
        ),
        "final_entity": {
            "name": canonical_name,
            "attributes": _merge_attributes(
                clusters,
                assembly_kind=assembly_kind,
                evidence_frame_ids=evidence_frames,
            ),
            "entity_confidence": confidence,
            "evidence_frame_ids": evidence_frames,
        },
    }


def assemble_consensus(
    *,
    baseline: Mapping[str, Any],
    first_plan: Mapping[str, Any],
    second_plan: Mapping[str, Any],
    resolutions: Sequence[Mapping[str, Any]],
    candidate_bank: Mapping[str, Any],
    shot_id: str,
    valid_frame_ids: Sequence[int],
    base_protocol: str,
    spatial_vetoes: Sequence[Mapping[str, Any]] = (),
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Apply only exact, clear, nonoverlapping two-planner resolutions."""
    if baseline.get("protocol_version") != base_protocol:
        raise AcceptedAssemblyError("Baseline changed base protocol_version")
    if baseline.get("shot_id") != shot_id:
        raise AcceptedAssemblyError("Baseline changed shot_id")
    accepted_view = planner_baseline_view(
        baseline,
        candidate_bank=candidate_bank,
        shot_id=shot_id,
        base_protocol=base_protocol,
    )
    for plan in (first_plan, second_plan):
        validate_plan(
            plan,
            shot_id=shot_id,
            baseline=baseline,
            accepted_view=accepted_view,
            valid_frame_ids=valid_frame_ids,
            base_protocol=base_protocol,
        )
    expected_resolutions = select_consensus_resolutions(
        first_plan, second_plan, spatial_vetoes=spatial_vetoes,
    )
    if list(resolutions) != expected_resolutions:
        raise AcceptedAssemblyError("Consensus resolutions were modified")

    baseline_by_id = {
        cluster["cluster_id"]: cluster for cluster in baseline["clusters"]
    }
    if len(baseline_by_id) != len(baseline["clusters"]):
        raise AcceptedAssemblyError("Baseline contains duplicate cluster IDs")
    baseline_order = {
        cluster["cluster_id"]: index
        for index, cluster in enumerate(baseline["clusters"])
    }
    first_by_candidate = {
        item["candidate_id"]: item for item in first_plan["families"]
    }
    second_by_candidate = {
        item["candidate_id"]: item for item in second_plan["families"]
    }
    applied = {
        tuple(item["anchor_cluster_ids"]): item
        for item in resolutions
        if item["status"] == "applied"
    }
    baseline_to_anchors: Dict[str, Tuple[str, ...]] = {}
    for anchor_ids in applied:
        for cluster_id in anchor_ids:
            if cluster_id not in baseline_by_id:
                raise AcceptedAssemblyError(
                    "Applied resolution cites an unknown baseline cluster"
                )
            baseline_to_anchors[cluster_id] = anchor_ids

    inserted: set[Tuple[str, ...]] = set()
    final_clusters = []
    for cluster in baseline["clusters"]:
        anchor_ids = baseline_to_anchors.get(cluster["cluster_id"])
        if anchor_ids is None:
            final_clusters.append(copy.deepcopy(cluster))
            continue
        if anchor_ids in inserted:
            continue
        inserted.add(anchor_ids)
        assembly_kind = applied[anchor_ids]["assembly_kind"]
        if assembly_kind is None:
            raise AcceptedAssemblyError("Applied resolution has no assembly_kind")
        candidate_id = applied[anchor_ids]["candidate_id"]
        final_clusters.append(
            _build_merged_cluster(
                anchor_ids=anchor_ids,
                assembly_kind=assembly_kind,
                first_family=first_by_candidate[candidate_id],
                second_family=second_by_candidate[candidate_id],
                baseline_by_id=baseline_by_id,
                baseline_order=baseline_order,
                valid_frame_ids=valid_frame_ids,
            )
        )

    original_proposals = [
        proposal_id
        for cluster in baseline["clusters"]
        for proposal_id in cluster["anonymous_proposal_ids"]
    ]
    final_proposals = [
        proposal_id
        for cluster in final_clusters
        for proposal_id in cluster["anonymous_proposal_ids"]
    ]
    if Counter(original_proposals) != Counter(final_proposals):
        raise AcceptedAssemblyError("Proposal accounting changed during assembly")

    final = {
        "protocol_version": base_protocol,
        "shot_id": shot_id,
        "clusters": final_clusters,
        "warnings": copy.deepcopy(baseline.get("warnings", [])),
    }
    final_by_id = {cluster["cluster_id"]: cluster for cluster in final_clusters}
    frozen_ids = [
        cluster["cluster_id"]
        for cluster in baseline["clusters"]
        if cluster["cluster_id"] not in baseline_to_anchors
    ]
    changed_outside = [
        cluster_id
        for cluster_id in frozen_ids
        if final_by_id.get(cluster_id) != baseline_by_id[cluster_id]
    ]
    if changed_outside:
        raise AcceptedAssemblyError(
            "Accepted-only firewall changed clusters outside applied families"
        )

    frozen_components = []
    for anchor_ids in sorted(applied):
        for cluster_id in anchor_ids:
            cluster = baseline_by_id[cluster_id]
            frozen_components.append(
                {
                    "anchor_cluster_id": cluster_id,
                    "anchor_cluster_sha256": json_hash(cluster),
                    "immutable_anchor_cluster": copy.deepcopy(cluster),
                }
            )
    audit = {
        "shot_id": shot_id,
        "reference_coverage_policy": REFERENCE_COVERAGE_POLICY,
        "resolutions": copy.deepcopy(list(resolutions)),
        "spatial_vetoes": copy.deepcopy(list(spatial_vetoes)),
        "applied_anchor_sets": [list(item) for item in sorted(applied)],
        "frozen_nonfamily_cluster_ids": frozen_ids,
        "changed_outside_family_cluster_ids": changed_outside,
        "frozen_components": frozen_components,
        "frozen_components_sha256": json_hash(frozen_components),
        "baseline_cluster_count": len(baseline["clusters"]),
        "final_cluster_count": len(final_clusters),
        "exact_two_planner_consensus_required": True,
        "mandatory_candidate_bank": True,
        "candidate_count": len(candidate_bank["candidates"]),
        "candidate_bank_sha256": json_hash(candidate_bank),
        "overlap_components_are_noop": True,
        "model_naming_authority": False,
        "detector_provenance_visible_to_planners": False,
        "detector_boxes_visible_to_planners": False,
        "cross_shot_input": False,
    }
    return final, audit


def build_physical_anchor_lineage(
    baseline: Mapping[str, Any], final_decisions: Mapping[str, Any],
) -> Dict[str, Any]:
    """Reconstruct graph-to-physical lineage without changing either ledger.

    Frozen physical anchors are immutable units. A graph node may combine whole
    anchors, but that partition operation supplies no same-instance evidence.
    Proposal ownership is checked independently rather than trusting supplied
    component metadata or previously computed resolutions.
    """
    if baseline.get("shot_id") != final_decisions.get("shot_id"):
        raise AcceptedAssemblyError("Physical lineage changed shot_id")
    if baseline.get("protocol_version") != final_decisions.get("protocol_version"):
        raise AcceptedAssemblyError("Physical lineage changed base protocol_version")

    def index_ledger(ledger, label):
        rows = ledger.get("clusters")
        if not isinstance(rows, list):
            raise AcceptedAssemblyError(f"{label}: clusters must be an array")
        by_id, scopes, owners = {}, {}, {}
        for row in rows:
            if not isinstance(row, Mapping):
                raise AcceptedAssemblyError(f"{label}: cluster must be an object")
            cluster_id = row.get("cluster_id")
            if not isinstance(cluster_id, str) or not cluster_id or cluster_id in by_id:
                raise AcceptedAssemblyError(f"{label}: duplicate or invalid cluster ID")
            proposal_ids = row.get("anonymous_proposal_ids")
            if (not isinstance(proposal_ids, list) or not proposal_ids
                    or any(not isinstance(p, str) or not p for p in proposal_ids)
                    or len(set(proposal_ids)) != len(proposal_ids)):
                raise AcceptedAssemblyError(f"{label}/{cluster_id}: invalid proposal IDs")
            if any(p in owners for p in proposal_ids):
                raise AcceptedAssemblyError(f"{label}: a proposal has multiple owners")
            if row.get("decision") not in {"accept", "reject", "abstain"}:
                raise AcceptedAssemblyError(f"{label}/{cluster_id}: invalid decision")
            by_id[cluster_id] = row
            scopes[cluster_id] = frozenset(proposal_ids)
            owners.update({p: cluster_id for p in proposal_ids})
        return by_id, scopes, owners

    frozen, frozen_scopes, frozen_owners = index_ledger(baseline, "physical baseline")
    graph, graph_scopes, graph_owners = index_ledger(final_decisions, "derived graph")
    if set(frozen_owners) != set(graph_owners):
        raise AcceptedAssemblyError("Physical lineage changed the complete proposal universe")
    accepted = {key for key, row in frozen.items() if row["decision"] == "accept"}
    accepted_graph = {key for key, row in graph.items() if row["decision"] == "accept"}
    accepted_proposals = {p for key in accepted for p in frozen_scopes[key]}
    visits: Counter[str] = Counter()
    nodes = []
    for graph_id in sorted(accepted_graph):
        scope = graph_scopes[graph_id]
        if not scope <= accepted_proposals:
            raise AcceptedAssemblyError(
                f"{graph_id}: graph scope contains a rejected or abstained physical proposal"
            )
        anchor_ids = sorted({frozen_owners[p] for p in scope})
        for anchor_id in anchor_ids:
            if not frozen_scopes[anchor_id] <= scope:
                raise AcceptedAssemblyError(
                    f"{graph_id}: partial physical anchor {anchor_id} cannot enter graph lineage"
                )
        anchor_union = frozenset().union(*(frozen_scopes[key] for key in anchor_ids))
        if scope != anchor_union:
            raise AcceptedAssemblyError(f"{graph_id}: graph scope is not its exact anchor union")
        visits.update(anchor_ids)
        nodes.append({
            "graph_cluster_id": graph_id,
            "graph_cluster_sha256": json_hash(graph[graph_id]),
            "anonymous_proposal_ids": sorted(scope),
            "physical_anchor_cluster_ids": anchor_ids,
            "physical_anchors": [
                {"anchor_cluster_id": key, "anchor_cluster_sha256": json_hash(frozen[key]),
                 "anonymous_proposal_ids": sorted(frozen_scopes[key])}
                for key in anchor_ids
            ],
            "is_synthetic_graph_group": len(anchor_ids) > 1,
            "same_instance_evidence_from_grouping": False,
        })
    if set(visits) != accepted or any(visits[key] != 1 for key in accepted):
        raise AcceptedAssemblyError(
            "Every accepted frozen physical anchor must map to exactly one accepted graph node"
        )
    return {
        "protocol_version": "single_shot_graph_physical_anchor_lineage_v0.1",
        "shot_id": baseline["shot_id"],
        "physical_baseline_content_sha256": json_hash(baseline),
        "derived_graph_content_sha256": json_hash(final_decisions),
        "physical_baseline_schema_version": baseline.get("schema_version"),
        "accepted_physical_anchor_count": len(accepted),
        "accepted_graph_node_count": len(nodes),
        "accepted_physical_anchor_ids": sorted(accepted),
        "accepted_physical_proposal_ids": sorted(accepted_proposals),
        "nodes": nodes,
        "every_physical_anchor_mapped_exactly_once": True,
        "complete_proposal_universe_preserved": True,
        "graph_scopes_equal_exact_frozen_anchor_unions": True,
        "synthetic_groups_are_same_instance_evidence": False,
        "physical_inventory_mutated": False,
        "interpretation": (
            "Derived graph partition over the immutable physical inventory. A synthetic "
            "graph node preserves its constituent physical anchors; grouping does not "
            "assert confirmed_same_scope or replace their physical identity judgments."
        ),
    }


__all__ = [
    "PLAN_PROTOCOL",
    "INPUT_PROTOCOL",
    "CANDIDATE_BANK_PROTOCOL",
    "REFERENCE_COVERAGE_POLICY",
    "ASSEMBLY_KIND_NAMES",
    "INDEPENDENCE_KINDS",
    "PROTECTED_RELATION_KINDS",
    "AcceptedAssemblyError",
    "json_hash",
    "build_declared_partition_neighborhoods",
    "build_candidate_bank",
    "deterministic_merged_name",
    "planner_baseline_view",
    "build_prompt",
    "validate_plan",
    "select_consensus_resolutions",
    "assemble_consensus",
    "build_physical_anchor_lineage",
]
