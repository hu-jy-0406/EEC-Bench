import copy
import inspect
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import ensemble_shot_entity_detection as ENSEMBLE  # noqa: E402
import run_granularity_family_ablation as FAMILY  # noqa: E402


SHOT_ID = "shot_test"
FRAME_IDS = [10]
DETECTOR_IDS = [
    "detector_2",
    "detector_7",
    "detector_11",
    "detector_20",
    "detector_42",
]


def _attribute(name, value, confidence):
    return {
        "name": name,
        "value": value,
        "confidence": confidence,
        "evidence_frame_ids": [10],
    }


def _proposal_payload(name):
    return {
        "proposed_name": name,
        "canonical_head": name,
        "entity_type": "object",
        "granularity": "whole_or_compact_group",
        "attributes": [],
        "evidence_frame_ids": [10],
        "coarse_locators": [{"frame_id": 10, "description": f"location of {name}"}],
        "frame_presence": [
            {
                "frame_id": 10,
                "status": "visible",
                "description": f"{name} is visible",
                "bbox_xyxy_normalized": [0.1, 0.1, 0.4, 0.4],
            }
        ],
        "uncertainty_flags": [],
    }


def _cluster(
    cluster_id,
    proposal_ids,
    name,
    *,
    decision="accept",
    attributes=None,
    confidence=0.9,
    evidence_label=None,
):
    accepted = decision == "accept"
    flags = [] if accepted else ["group_member_conflict", "private_challenge"]
    return {
        "cluster_id": cluster_id,
        "anonymous_proposal_ids": list(proposal_ids),
        "canonical_name": name,
        "aliases": [name],
        "granularity": "compact_group" if "group" in cluster_id else "member",
        "adjudicator_evidence": [
            {
                "frame_id": 10,
                "coarse_locator": evidence_label or f"location of {name}",
                "support_quality": "strong" if accepted else "moderate",
            }
        ],
        "frame_presence": [
            {
                "frame_id": 10,
                "status": "visible" if accepted else "uncertain",
                "description": (
                    f"{name} is visible"
                    if accepted
                    else f"{name} is superseded partition evidence"
                ),
            }
        ],
        "identity_status": "resolved" if accepted else "ambiguous",
        "decision": decision,
        "decision_reason": (
            "visually supported member unit"
            if accepted
            else "superseded group partition; depicted content remains present"
        ),
        "uncertainty_flags": flags,
        "final_entity": (
            {
                "name": name,
                "attributes": copy.deepcopy(attributes or []),
                "entity_confidence": confidence,
                "evidence_frame_ids": [10],
            }
            if accepted
            else None
        ),
    }


def _witnesses(mode):
    first = {
        "witness_id": "w1",
        "kind": "separate_handling_or_use",
        "separated_unit_id": "u1",
        "contrast_unit_id": "u2",
        "frame_ids": [10],
        "description": "u1 is separately handled from u2",
    }
    if mode == "partial":
        return [first]
    if mode == "full":
        return [
            first,
            {
                "witness_id": "w2",
                "kind": "detachment_or_standalone_state",
                "separated_unit_id": "u1",
                "contrast_unit_id": "u3",
                "frame_ids": [10],
                "description": "u1 appears detached from u3",
            },
            {
                "witness_id": "w3",
                "kind": "separate_handling_or_use",
                "separated_unit_id": "u2",
                "contrast_unit_id": "u3",
                "frame_ids": [10],
                "description": "u2 is separately handled from u3",
            },
        ]
    return []


def _fixture(*, witness_mode="none"):
    group_ids = ["p0001", "p0005"]
    member_ids = {
        "u1": ["p0002", "p0006", "p0010"],
        "u2": ["p0003", "p0007"],
        "u3": ["p0004", "p0008"],
    }
    scope = group_ids + [
        proposal_id
        for unit_id in ("u1", "u2", "u3")
        for proposal_id in member_ids[unit_id]
    ]
    baseline = {
        "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
        "shot_id": SHOT_ID,
        "clusters": [
            _cluster(
                "c_group",
                group_ids,
                "frozen compact display",
                decision="reject",
                evidence_label="rejected-only evidence",
            ),
            _cluster(
                "c_member_1",
                member_ids["u1"],
                "first unit",
                attributes=[_attribute("color", "white", 0.75)],
                confidence=0.82,
                evidence_label="accepted evidence one",
            ),
            _cluster(
                "c_member_2",
                member_ids["u2"],
                "second unit",
                attributes=[
                    _attribute("color", "white", 0.9),
                    _attribute("material", "paper", 0.8),
                ],
                confidence=0.91,
                evidence_label="accepted evidence two",
            ),
            _cluster(
                "c_member_3",
                member_ids["u3"],
                "third unit",
                attributes=[_attribute("color", "white", 0.85)],
                confidence=0.87,
                evidence_label="accepted evidence three",
            ),
            _cluster(
                "c_outside",
                ["p0009"],
                "unrelated object",
                attributes=[_attribute("state", "closed", 0.88)],
                confidence=0.93,
            ),
        ],
        "warnings": ["baseline warning"],
    }
    proposal_names = {
        "p0001": "proposal wording must not name output",
        "p0002": "first unit",
        "p0003": "second unit",
        "p0004": "third unit",
        "p0005": "another group proposal",
        "p0006": "first component",
        "p0007": "second component",
        "p0008": "third component",
        "p0009": "unrelated object",
        "p0010": "upper member",
    }
    anonymous_view = {
        "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
        "shot_id": SHOT_ID,
        "proposals": [
            {
                "anonymous_proposal_id": proposal_id,
                **_proposal_payload(proposal_names[proposal_id]),
            }
            for proposal_id in sorted(proposal_names)
        ],
        "box_redundancy_challenges": [
            {"private_marker": "must-never-reach-family-planner"}
        ],
    }
    role_by_id = {
        "p0001": ("group", ["u1", "u2", "u3"]),
        "p0002": ("member", ["u1"]),
        "p0003": ("member", ["u2"]),
        "p0004": ("member", ["u3"]),
        "p0005": ("group", ["u1", "u2", "u3"]),
        "p0006": ("member", ["u1"]),
        "p0007": ("member", ["u2"]),
        "p0008": ("member", ["u3"]),
        "p0010": ("member", ["u1"]),
    }
    family = {
        "family_id": "gf1",
        "visual_scope": "one compact three-unit display",
        "baseline_cluster_ids": [
            "c_group",
            "c_member_1",
            "c_member_2",
            "c_member_3",
        ],
        "scope_proposal_ids": list(scope),
        "content_units": [
            {
                "unit_id": "u1",
                "description": "first unit",
                "anchor_cluster_id": "c_member_1",
                "evidence": [{"frame_id": 10, "description": "first boundary"}],
            },
            {
                "unit_id": "u2",
                "description": "second unit",
                "anchor_cluster_id": "c_member_2",
                "evidence": [{"frame_id": 10, "description": "second boundary"}],
            },
            {
                "unit_id": "u3",
                "description": "third unit",
                "anchor_cluster_id": "c_member_3",
                "evidence": [{"frame_id": 10, "description": "third boundary"}],
            },
        ],
        "proposal_roles": [
            {
                "proposal_id": proposal_id,
                "role": role_by_id[proposal_id][0],
                "covers_unit_ids": role_by_id[proposal_id][1],
                "same_content_evidence": (
                    [
                        {
                            "unit_id": unit_id,
                            "anchor_cluster_id": f"c_member_{unit_id[1:]}",
                            "frame_id": 10,
                            "description": (
                                "group boundary covers this accepted member "
                                "without adjacent context"
                            ),
                        }
                        for unit_id in ("u1", "u2", "u3")
                    ]
                    if role_by_id[proposal_id][0] == "group"
                    else []
                ),
                "reason": "test partition role",
            }
            for proposal_id in scope
        ],
        "same_content_evidence": [
            {
                "frame_id": 10,
                "description": "both partitions cover the same physical content",
            }
        ],
        "compact_scope_confirmed": True,
        "large_host_or_support_involved": False,
        "independence_witnesses": _witnesses(witness_mode),
        "reason": "strict group-versus-members conflict",
    }
    plan = {
        "protocol_version": FAMILY.FAMILY_PLAN_PROTOCOL,
        "shot_id": SHOT_ID,
        "reviewed_group_alternative_cluster_ids": ["c_group"],
        "excluded_group_alternatives": [],
        "families": [family],
        "warnings": [],
    }
    sources = {
        "p0001": "detector_2",  # complete group
        "p0002": "detector_7",  # complete members, counted once
        "p0003": "detector_7",
        "p0004": "detector_7",
        "p0005": "detector_11",  # group plus complete members: mixed
        "p0006": "detector_11",
        "p0007": "detector_11",
        "p0008": "detector_11",
        "p0009": "detector_42",  # outside family: no_vote within gf1
        "p0010": "detector_20",  # incomplete member partition: partial
    }
    proposal_by_id = {
        item["anonymous_proposal_id"]: item for item in anonymous_view["proposals"]
    }
    source_map = {
        "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
        "shot_id": SHOT_ID,
        "mappings": [
            {
                "anonymous_proposal_id": proposal_id,
                "source_kind": "detector",
                "source": detector_id,
                "local_id": f"{detector_id}_{proposal_id}",
            }
            for proposal_id, detector_id in sources.items()
        ],
    }
    detector_ledgers = []
    for detector_id in DETECTOR_IDS:
        entities = []
        for proposal_id, source in sources.items():
            if source != detector_id:
                continue
            entities.append(
                {
                    "local_id": f"{detector_id}_{proposal_id}",
                    **{
                        field: copy.deepcopy(proposal_by_id[proposal_id][field])
                        for field in FAMILY.PROPOSAL_FIELDS
                    },
                }
            )
        detector_ledgers.append({"detector_id": detector_id, "entities": entities})
    return plan, baseline, anonymous_view, source_map, detector_ledgers


def _planner_variant(plan, *, family_id="gf9", witness_mode=None):
    result = copy.deepcopy(plan)
    family = result["families"][0]
    family["family_id"] = family_id
    family["visual_scope"] = "independently worded compact scope"
    family["reason"] = "independent wording for the same frozen structure"
    family["same_content_evidence"][0]["description"] = (
        "independent original-pixel description of the same content"
    )
    if witness_mode is not None:
        family["independence_witnesses"] = _witnesses(witness_mode)
    return result


def _usage(input_tokens, output_tokens):
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": 0,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }


def _set_proposal_track(anonymous_view, proposal_id, boxes_by_frame):
    proposal = next(
        item
        for item in anonymous_view["proposals"]
        if item["anonymous_proposal_id"] == proposal_id
    )
    proposal["frame_presence"] = [
        {
            "frame_id": frame_id,
            "status": "visible" if bbox is not None else "uncertain",
            "description": (
                "bounded visual track"
                if bbox is not None
                else "no reliable localization"
            ),
            "bbox_xyxy_normalized": bbox,
        }
        for frame_id, bbox in sorted(boxes_by_frame.items())
    ]


def _extend_baseline_presence(baseline, frame_ids):
    for cluster in baseline["clusters"]:
        existing = {item["frame_id"] for item in cluster["frame_presence"]}
        for frame_id in frame_ids:
            if frame_id in existing:
                continue
            status = "visible" if cluster["decision"] == "accept" else "uncertain"
            cluster["frame_presence"].append(
                {
                    "frame_id": frame_id,
                    "status": status,
                    "description": f"generic {status} frame",
                }
            )


def _spatial_fixture(group_boxes_by_frame, third_member_boxes_by_frame):
    plan, baseline, anonymous_view, source_map, detector_ledgers = _fixture()
    frame_ids = sorted(set(group_boxes_by_frame) | set(third_member_boxes_by_frame))
    _extend_baseline_presence(baseline, frame_ids)
    for proposal_id in ("p0001", "p0005"):
        _set_proposal_track(anonymous_view, proposal_id, group_boxes_by_frame)
    for proposal_id in ("p0004", "p0008"):
        _set_proposal_track(anonymous_view, proposal_id, third_member_boxes_by_frame)
    return (
        plan,
        baseline,
        anonymous_view,
        source_map,
        detector_ledgers,
        frame_ids,
    )


class GranularityFamilyAblationTest(unittest.TestCase):
    def _validate_plan(self, plan, baseline, anonymous_view):
        FAMILY.validate_family_plan(
            plan,
            shot_id=SHOT_ID,
            baseline=baseline,
            anonymous_view=FAMILY._planner_view(anonymous_view),
            valid_frame_ids=FRAME_IDS,
        )

    def _validate_source_map(
        self,
        source_map,
        anonymous_view,
        detector_ledgers,
        detector_ids=None,
    ):
        FAMILY.validate_source_map(
            source_map,
            shot_id=SHOT_ID,
            proposal_ids={
                item["anonymous_proposal_id"] for item in anonymous_view["proposals"]
            },
            detector_ids=detector_ids or DETECTOR_IDS,
            anonymous_view=anonymous_view,
            detector_ledgers=detector_ledgers,
        )

    def test_planner_views_and_schema_are_partition_only(self):
        plan, baseline, anonymous_view, _, _ = _fixture()
        planner_view = FAMILY._planner_view(anonymous_view)
        self.assertEqual(
            set(planner_view), {"protocol_version", "shot_id", "proposals"}
        )
        self.assertNotIn("box_redundancy_challenges", planner_view)
        self.assertNotIn("must-never-reach-family-planner", json.dumps(planner_view))
        planner_baseline = FAMILY._planner_baseline_view(baseline)
        self.assertNotIn("decision_reason", json.dumps(planner_baseline))
        self.assertEqual(planner_baseline["warnings"], [])
        self.assertEqual(
            planner_baseline["clusters"][0]["uncertainty_flags"],
            ["group_member_conflict"],
        )
        self._validate_plan(plan, baseline, anonymous_view)

        schema = json.loads(FAMILY.FAMILY_PLAN_SCHEMA.read_text(encoding="utf-8"))
        family_schema = schema["$defs"]["family"]
        self.assertFalse(schema["additionalProperties"])
        self.assertFalse(family_schema["additionalProperties"])
        self.assertIn("reviewed_group_alternative_cluster_ids", schema["required"])
        self.assertIn("excluded_group_alternatives", schema["required"])
        exclusion_schema = schema["$defs"]["excludedGroupAlternative"]
        self.assertFalse(exclusion_schema["additionalProperties"])
        self.assertIn(
            "candidate_member_anchor_cluster_ids",
            exclusion_schema["required"],
        )
        self.assertIn(
            "independent_context_anchor_cluster_ids",
            exclusion_schema["required"],
        )
        member_coverage_schema = schema["$defs"]["memberCoverageEvidence"]
        self.assertIn("unit_id", member_coverage_schema["required"])
        self.assertIn("anchor_cluster_id", member_coverage_schema["required"])
        serialized_schema = json.dumps(schema)
        for forbidden_field in (
            '"decision"',
            '"final_entity"',
            '"attributes"',
            '"partition_options"',
            '"replacement_clusters"',
            '"detector_id"',
            '"group_name_source_proposal_id"',
            '"contrast_unit_ids"',
        ):
            self.assertNotIn(forbidden_field, serialized_schema)
        self.assertIn('"contrast_unit_id"', serialized_schema)

        parameters = inspect.signature(FAMILY._build_prompt).parameters
        self.assertNotIn("source_map", parameters)
        self.assertNotIn("detector_ids", parameters)
        prompt = FAMILY._build_prompt(
            shot_id=SHOT_ID,
            shot_manifest={
                "reference_frames": [{"frame_id": 10, "path": "/tmp/frame.jpg"}]
            },
            anonymous_view=planner_view,
            baseline=planner_baseline,
            skill_text="generic partition policy",
        )
        self.assertIn("cannot output accept/reject decisions", prompt)
        self.assertIn("planner itself selects nothing", prompt)
        self.assertIn("has no naming authority", prompt)
        self.assertIn("separate isolated planner", prompt)
        self.assertIn("exact agreement on frozen family scope", prompt)
        self.assertIn("mandatory group-alternative review target", prompt)
        self.assertIn("reviewed_group_alternative_cluster_ids", prompt)
        self.assertIn("excluded_group_alternatives", prompt)
        self.assertIn("passive homogeneous collection has one canonical scope", prompt)
        self.assertIn("regardless of whether proposals initially used whole collections or subdivisions", prompt)
        self.assertIn("A contents-only collection family must exclude its fixture", prompt)
        self.assertIn("no family may include independent context", prompt)
        self.assertNotIn("No family may include the fixture or independent context", prompt)
        shared_scope_rule = FAMILY.family_stage.HOLDING_CONTAINER_SCOPE_INSTRUCTION
        self.assertEqual(prompt.count(shared_scope_rule), 1)
        protocol = (
            SCRIPTS_DIR.parent.parent
            / ".agents/skills/ensemble-shot-entity-detection/references/protocol.md"
        ).read_text(encoding="utf-8")
        self.assertIn(shared_scope_rule.rstrip(), protocol)
        self.assertIn("mandatory minimal-scope negative/context audit", prompt)
        self.assertIn("every accepted, resolved anchor", prompt)
        self.assertIn("different mounting plane or alignment", prompt)
        self.assertIn("persistent clear gap", prompt)
        self.assertIn("generic statement such as 'spans all members'", prompt)
        self.assertIn("geometry never proves a family or an entity", prompt)
        self.assertNotIn("must-never-reach-family-planner", prompt)
        for detector_id in DETECTOR_IDS:
            self.assertNotIn(detector_id, prompt)

    def test_each_planner_must_account_for_every_collection_alternative(self):
        plan, baseline, anonymous_view, _, _ = _fixture()
        for planner_index in (1, 2):
            with self.subTest(planner_index=planner_index):
                silently_omitted = copy.deepcopy(plan)
                silently_omitted["families"] = []
                silently_omitted["excluded_group_alternatives"] = []
                with self.assertRaisesRegex(
                    FAMILY.FamilyPlanError,
                    "must appear exactly once",
                ):
                    self._validate_plan(silently_omitted, baseline, anonymous_view)

        explicit_exclusion = copy.deepcopy(plan)
        explicit_exclusion["families"] = []
        explicit_exclusion["excluded_group_alternatives"] = [
            {
                "cluster_id": "c_group",
                "candidate_member_anchor_cluster_ids": [
                    "c_member_1",
                    "c_member_2",
                    "c_member_3",
                ],
                "independent_context_anchor_cluster_ids": [],
                "reason_code": "insufficient_joint_visibility",
                "reason": (
                    "Original pixels do not jointly expose the full competing "
                    "member partition."
                ),
            }
        ]
        self._validate_plan(explicit_exclusion, baseline, anonymous_view)

    def test_exclusion_anchor_mapping_is_structurally_constrained(self):
        plan, baseline, anonymous_view, _, _ = _fixture()
        excluded = copy.deepcopy(plan)
        excluded["families"] = []
        excluded["excluded_group_alternatives"] = [
            {
                "cluster_id": "c_group",
                "candidate_member_anchor_cluster_ids": [
                    "c_member_1",
                    "c_member_2",
                    "c_outside",
                ],
                "independent_context_anchor_cluster_ids": ["c_outside"],
                "reason_code": "contains_independently_graph_worthy_context",
                "reason": (
                    "The claimed group scope includes a separately graph-worthy "
                    "accepted context anchor."
                ),
            }
        ]
        self._validate_plan(excluded, baseline, anonymous_view)

        invalid_context = copy.deepcopy(excluded)
        invalid_context["excluded_group_alternatives"][0][
            "independent_context_anchor_cluster_ids"
        ] = ["c_member_3"]
        with self.assertRaisesRegex(FAMILY.FamilyPlanError, "must be a subset"):
            self._validate_plan(invalid_context, baseline, anonymous_view)

        empty_without_unresolvable_scope = copy.deepcopy(excluded)
        record = empty_without_unresolvable_scope["excluded_group_alternatives"][0]
        record["candidate_member_anchor_cluster_ids"] = []
        record["independent_context_anchor_cluster_ids"] = []
        record["reason_code"] = "insufficient_joint_visibility"
        with self.assertRaisesRegex(FAMILY.FamilyPlanError, "may be empty only"):
            self._validate_plan(
                empty_without_unresolvable_scope, baseline, anonymous_view
            )

    def test_family_roles_require_group_evidence_and_member_silence(self):
        plan, baseline, anonymous_view, _, _ = _fixture()
        self._validate_plan(plan, baseline, anonymous_view)

        group_without_evidence = copy.deepcopy(plan)
        group_without_evidence["families"][0]["proposal_roles"][0][
            "same_content_evidence"
        ] = []
        group_missing_anchor_evidence = copy.deepcopy(plan)
        first_group_role = next(
            role
            for role in group_missing_anchor_evidence["families"][0]["proposal_roles"]
            if role["role"] == "group"
        )
        first_group_role["same_content_evidence"] = [
            item
            for item in first_group_role["same_content_evidence"]
            if item["unit_id"] != "u3"
        ]
        group_wrong_anchor_evidence = copy.deepcopy(plan)
        wrong_anchor_evidence = next(
            role
            for role in group_wrong_anchor_evidence["families"][0]["proposal_roles"]
            if role["role"] == "group"
        )["same_content_evidence"][0]
        wrong_anchor_evidence["anchor_cluster_id"] = "c_member_2"
        member_with_group_evidence = copy.deepcopy(plan)
        member_role = next(
            role
            for role in member_with_group_evidence["families"][0]["proposal_roles"]
            if role["role"] == "member"
        )
        member_role["same_content_evidence"] = [
            {
                "unit_id": "u1",
                "anchor_cluster_id": "c_member_1",
                "frame_id": 10,
                "description": "not allowed for a member",
            }
        ]
        missing_conflict_flag = copy.deepcopy(baseline)
        missing_conflict_flag["clusters"][0]["uncertainty_flags"] = []

        for label, invalid_plan, invalid_baseline in (
            ("group evidence empty", group_without_evidence, baseline),
            (
                "group evidence omits one member anchor",
                group_missing_anchor_evidence,
                baseline,
            ),
            (
                "group evidence names the wrong member anchor",
                group_wrong_anchor_evidence,
                baseline,
            ),
            ("member evidence nonempty", member_with_group_evidence, baseline),
            ("rejected group lacks frozen flag", plan, missing_conflict_flag),
        ):
            with self.subTest(label=label):
                with self.assertRaises(FAMILY.FamilyPlanError):
                    self._validate_plan(invalid_plan, invalid_baseline, anonymous_view)

    def test_same_content_evidence_requires_joint_family_visibility(self):
        plan, baseline, anonymous_view, _, _ = _fixture()
        for cluster in baseline["clusters"]:
            if cluster["cluster_id"] == "c_member_3":
                status = "occluded"
            elif cluster["decision"] == "accept":
                status = "visible"
            else:
                status = "uncertain"
            cluster["frame_presence"].append(
                {
                    "frame_id": 20,
                    "status": status,
                    "description": f"frame 20 is {status}",
                }
            )

        invalid_cases = []
        family_only = copy.deepcopy(plan)
        family_only["families"][0]["same_content_evidence"] = [
            {
                "frame_id": 20,
                "description": "not all accepted units are visible",
            }
        ]
        invalid_cases.append(
            (
                "family",
                family_only,
                "every same-content evidence frame must show all accepted "
                "content units visible",
            )
        )
        for group_proposal_id in ("p0001", "p0005"):
            group_only = copy.deepcopy(plan)
            group_role = next(
                role
                for role in group_only["families"][0]["proposal_roles"]
                if role["proposal_id"] == group_proposal_id
            )
            group_role["same_content_evidence"] = [
                {
                    "unit_id": unit_id,
                    "anchor_cluster_id": f"c_member_{unit_id[1:]}",
                    "frame_id": 20,
                    "description": "not all covered units are visible",
                }
                for unit_id in ("u1", "u2", "u3")
            ]
            invalid_cases.append(
                (
                    group_proposal_id,
                    group_only,
                    "every group evidence frame must show all content units visible",
                )
            )

        for label, invalid_plan, expected_error in invalid_cases:
            with self.subTest(scope=label):
                with self.assertRaisesRegex(FAMILY.FamilyPlanError, expected_error):
                    FAMILY.validate_family_plan(
                        invalid_plan,
                        shot_id=SHOT_ID,
                        baseline=baseline,
                        anonymous_view=FAMILY._planner_view(anonymous_view),
                        valid_frame_ids=[10, 20],
                    )

    def test_gross_persistent_spatial_incompatibility_keeps_baseline(self):
        frame_ids = [10, 20, 30, 40, 50]
        separated_group_boxes = {
            frame_id: [0.05, 0.05, 0.30, 0.30] for frame_id in frame_ids
        }
        separated_member_boxes = {
            frame_id: [0.70, 0.65, 0.88, 0.90] for frame_id in frame_ids
        }
        plan, baseline, anonymous_view, _, _, valid_frames = _spatial_fixture(
            separated_group_boxes, separated_member_boxes
        )

        FAMILY.validate_family_plan(
            plan, shot_id=SHOT_ID, baseline=baseline,
            anonymous_view=FAMILY._planner_view(anonymous_view), valid_frame_ids=valid_frames,
        )
        vetoes = FAMILY.family_stage.collect_spatial_vetoes(
            (plan,), baseline=baseline, anonymous_view=anonymous_view,
        )
        resolution = FAMILY._select_resolutions(plan, spatial_vetoes=vetoes)[0]
        self.assertEqual(resolution["status"], "kept_baseline")
        self.assertEqual(resolution["basis"], "gross_spatial_incompatibility_veto")

        proposal_by_id = {
            item["anonymous_proposal_id"]: item for item in anonymous_view["proposals"]
        }
        audit = FAMILY.family_stage.audit_gross_spatial_incompatibility(
            plan["families"][0],
            baseline_by_id={item["cluster_id"]: item for item in baseline["clusters"]},
            proposal_by_id=proposal_by_id,
        )
        self.assertEqual(audit["policy"], "veto_only_never_positive_group_evidence")
        self.assertEqual(audit["thresholds"]["minimum_covisible_frames_per_track"], 3)
        self.assertTrue(audit["blocking_incompatibilities"])
        self.assertTrue(
            all(
                blocker["member_anchor_cluster_id"] == "c_member_3"
                for blocker in audit["blocking_incompatibilities"]
            )
        )

        excluded = copy.deepcopy(plan)
        excluded["families"] = []
        excluded["excluded_group_alternatives"] = [
            {
                "cluster_id": "c_group",
                "candidate_member_anchor_cluster_ids": [
                    "c_member_1",
                    "c_member_2",
                    "c_member_3",
                ],
                "independent_context_anchor_cluster_ids": ["c_member_3"],
                "reason_code": "contains_independently_graph_worthy_context",
                "reason": (
                    "Original-pixel review finds a separately bounded context "
                    "anchor outside the minimal member cohort."
                ),
            }
        ]
        FAMILY.validate_family_plan(
            excluded,
            shot_id=SHOT_ID,
            baseline=baseline,
            anonymous_view=FAMILY._planner_view(anonymous_view),
            valid_frame_ids=valid_frames,
        )

    def test_spatial_veto_does_not_act_on_sparse_missing_or_containing_boxes(self):
        frame_ids = [10, 20, 30, 40, 50]
        third_member_boxes = {
            frame_id: [0.70, 0.65, 0.88, 0.90] for frame_id in frame_ids
        }
        cases = {
            "single-frame disagreement": {
                10: [0.05, 0.05, 0.30, 0.30],
                20: None,
                30: None,
                40: None,
                50: None,
            },
            "missing group geometry": {frame_id: None for frame_id in frame_ids},
            "consistent containment": {
                frame_id: [0.05, 0.05, 0.95, 0.95] for frame_id in frame_ids
            },
            "one occasional offset": {
                frame_id: (
                    [0.05, 0.05, 0.30, 0.30]
                    if frame_id == 10
                    else [0.05, 0.05, 0.95, 0.95]
                )
                for frame_id in frame_ids
            },
        }
        for label, group_boxes in cases.items():
            with self.subTest(case=label):
                (
                    plan,
                    baseline,
                    anonymous_view,
                    _,
                    _,
                    valid_frames,
                ) = _spatial_fixture(group_boxes, third_member_boxes)
                FAMILY.validate_family_plan(
                    plan,
                    shot_id=SHOT_ID,
                    baseline=baseline,
                    anonymous_view=FAMILY._planner_view(anonymous_view),
                    valid_frame_ids=valid_frames,
                )

    def test_spatial_veto_requires_every_comparable_member_track_to_conflict(self):
        frame_ids = [10, 20, 30, 40, 50]
        group_boxes = {frame_id: [0.05, 0.05, 0.30, 0.30] for frame_id in frame_ids}
        separated_member_boxes = {
            frame_id: [0.70, 0.65, 0.88, 0.90] for frame_id in frame_ids
        }
        plan, baseline, anonymous_view, _, _, valid_frames = _spatial_fixture(
            group_boxes, separated_member_boxes
        )
        _set_proposal_track(anonymous_view, "p0008", group_boxes)

        FAMILY.validate_family_plan(
            plan,
            shot_id=SHOT_ID,
            baseline=baseline,
            anonymous_view=FAMILY._planner_view(anonymous_view),
            valid_frame_ids=valid_frames,
        )
        audit = FAMILY.family_stage.audit_gross_spatial_incompatibility(
            plan["families"][0],
            baseline_by_id={item["cluster_id"]: item for item in baseline["clusters"]},
            proposal_by_id={
                item["anonymous_proposal_id"]: item
                for item in anonymous_view["proposals"]
            },
        )
        self.assertEqual(audit["blocking_incompatibilities"], [])

    def test_family_validator_enforces_frozen_member_anchor_shape(self):
        plan, baseline, anonymous_view, _, _ = _fixture()
        self._validate_plan(plan, baseline, anonymous_view)

        partial_scope = copy.deepcopy(plan)
        partial_scope["families"][0]["scope_proposal_ids"].remove("p0010")
        wrong_anchor = copy.deepcopy(plan)
        wrong_anchor["families"][0]["content_units"][0]["anchor_cluster_id"] = "c_group"
        non_rejected_alternative = copy.deepcopy(baseline)
        non_rejected_alternative["clusters"][0]["decision"] = "abstain"
        member_as_group = copy.deepcopy(plan)
        member_role = next(
            role
            for role in member_as_group["families"][0]["proposal_roles"]
            if role["proposal_id"] == "p0002"
        )
        member_role.update(
            role="group",
            covers_unit_ids=["u1", "u2", "u3"],
            same_content_evidence=[
                {
                    "unit_id": unit_id,
                    "anchor_cluster_id": f"c_member_{unit_id[1:]}",
                    "frame_id": 10,
                    "description": "invalid relabel",
                }
                for unit_id in ("u1", "u2", "u3")
            ],
        )
        group_as_member = copy.deepcopy(plan)
        group_role = next(
            role
            for role in group_as_member["families"][0]["proposal_roles"]
            if role["proposal_id"] == "p0001"
        )
        group_role.update(
            role="member",
            covers_unit_ids=["u1"],
            same_content_evidence=[],
        )

        for label, invalid_plan, invalid_baseline in (
            ("partial whole-cluster scope", partial_scope, baseline),
            ("rejected cluster used as anchor", wrong_anchor, baseline),
            ("non-anchor alternative is not rejected", plan, non_rejected_alternative),
            ("accepted anchor relabeled group", member_as_group, baseline),
            ("rejected group relabeled member", group_as_member, baseline),
        ):
            with self.subTest(label=label):
                with self.assertRaises(FAMILY.FamilyPlanError):
                    self._validate_plan(invalid_plan, invalid_baseline, anonymous_view)

    def test_source_map_reconciles_ids_local_ids_and_payloads_exactly(self):
        _, _, anonymous_view, source_map, detector_ledgers = _fixture()
        self._validate_source_map(source_map, anonymous_view, detector_ledgers)

        missing = copy.deepcopy(source_map)
        missing["mappings"].pop()
        duplicate = copy.deepcopy(source_map)
        duplicate["mappings"].append(copy.deepcopy(duplicate["mappings"][0]))
        wrong_local = copy.deepcopy(source_map)
        wrong_local["mappings"][0]["local_id"] = "missing_local_id"
        wrong_kind = copy.deepcopy(source_map)
        wrong_kind["mappings"][0]["source_kind"] = "verifier"
        payload_mismatch = copy.deepcopy(anonymous_view)
        payload_mismatch["proposals"][0]["proposed_name"] = "tampered name"
        missing_ledger_entity = copy.deepcopy(detector_ledgers)
        missing_ledger_entity[0]["entities"].pop()

        cases = (
            (
                "missing proposal mapping",
                missing,
                anonymous_view,
                detector_ledgers,
                DETECTOR_IDS,
            ),
            (
                "duplicate proposal mapping",
                duplicate,
                anonymous_view,
                detector_ledgers,
                DETECTOR_IDS,
            ),
            (
                "wrong local ID",
                wrong_local,
                anonymous_view,
                detector_ledgers,
                DETECTOR_IDS,
            ),
            (
                "non-detector source",
                wrong_kind,
                anonymous_view,
                detector_ledgers,
                DETECTOR_IDS,
            ),
            (
                "anonymous payload mismatch",
                source_map,
                payload_mismatch,
                detector_ledgers,
                DETECTOR_IDS,
            ),
            (
                "missing ledger entity",
                source_map,
                anonymous_view,
                missing_ledger_entity,
                DETECTOR_IDS,
            ),
            (
                "bad detector format",
                source_map,
                anonymous_view,
                detector_ledgers,
                ["detector_2", "panel_7"],
            ),
        )
        for label, invalid_map, view, ledgers, detector_ids in cases:
            with self.subTest(label=label):
                with self.assertRaises(FAMILY.FamilyPlanError):
                    self._validate_source_map(invalid_map, view, ledgers, detector_ids)

    def test_panel_positions_are_dynamic_deterministic_audit_only(self):
        plan, baseline, anonymous_view, source_map, detector_ledgers = _fixture()
        self._validate_plan(plan, baseline, anonymous_view)
        self._validate_source_map(source_map, anonymous_view, detector_ledgers)
        positions = FAMILY.build_panel_positions(plan, source_map, DETECTOR_IDS)
        reversed_map = copy.deepcopy(source_map)
        reversed_map["mappings"].reverse()
        self.assertEqual(
            positions,
            FAMILY.build_panel_positions(plan, reversed_map, DETECTOR_IDS),
        )
        ballots = positions["positions"][0]["ballots"]
        self.assertEqual([item["detector_id"] for item in ballots], DETECTOR_IDS)
        statuses = {item["detector_id"]: item["status"] for item in ballots}
        self.assertEqual(
            statuses,
            {
                "detector_2": "group",
                "detector_7": "members",
                "detector_11": "mixed",
                "detector_20": "partial",
                "detector_42": "no_vote",
            },
        )

        no_votes = copy.deepcopy(positions)
        for ballot in no_votes["positions"][0]["ballots"]:
            ballot["status"] = "no_vote"
        resolution = FAMILY._select_resolutions(plan, no_votes)[0]
        self.assertEqual(resolution["status"], "applied")
        self.assertEqual(resolution["selected_kind"], "group")
        self.assertEqual(resolution["group_panel_ids"], [])
        self.assertEqual(resolution["member_panel_ids"], [])

    def test_pairwise_witness_coverage_controls_members_vs_coarsest(self):
        for mode, expected_status, expected_kind, expected_basis in (
            (
                "none",
                "applied",
                "group",
                "coarsest_stable_partition_default",
            ),
            (
                "partial",
                "kept_baseline",
                "members",
                "partial_independence_evidence_fail_closed_to_baseline",
            ),
            (
                "full",
                "kept_baseline",
                "members",
                "all_member_boundaries_have_typed_shot_observed_witnesses",
            ),
        ):
            with self.subTest(mode=mode):
                plan, baseline, anonymous_view, source_map, _ = _fixture(
                    witness_mode=mode
                )
                self._validate_plan(plan, baseline, anonymous_view)
                positions = FAMILY.build_panel_positions(plan, source_map, DETECTOR_IDS)
                resolution = FAMILY._select_resolutions(plan, positions)[0]
                self.assertEqual(resolution["status"], expected_status)
                self.assertEqual(resolution["selected_kind"], expected_kind)
                self.assertEqual(resolution["basis"], expected_basis)
                expected_observed = [
                    witness["witness_id"]
                    for witness in plan["families"][0]["independence_witnesses"]
                ]
                self.assertEqual(resolution["observed_witness_ids"], expected_observed)
                self.assertEqual(
                    resolution["decisive_witness_ids"],
                    expected_observed if expected_kind == "members" else [],
                )

    def test_witness_frame_requires_both_anchor_units_visible(self):
        plan, baseline, anonymous_view, _, _ = _fixture(witness_mode="partial")
        plan["families"][0]["independence_witnesses"][0]["frame_ids"] = [20]
        for cluster in baseline["clusters"]:
            if cluster["cluster_id"] == "c_member_2":
                status = "occluded"
            elif cluster["decision"] == "accept":
                status = "visible"
            else:
                status = "uncertain"
            cluster["frame_presence"].append(
                {
                    "frame_id": 20,
                    "status": status,
                    "description": f"frame 20 is {status}",
                }
            )
        with self.assertRaisesRegex(
            FAMILY.FamilyPlanError,
            "witness frames must show both contrasted units visible",
        ):
            FAMILY.validate_family_plan(
                plan,
                shot_id=SHOT_ID,
                baseline=baseline,
                anonymous_view=FAMILY._planner_view(anonymous_view),
                valid_frame_ids=[10, 20],
            )

    def test_temporal_witnesses_require_at_least_two_frames(self):
        plan, baseline, anonymous_view, _, _ = _fixture(witness_mode="partial")
        for cluster in baseline["clusters"]:
            status = "visible" if cluster["decision"] == "accept" else "uncertain"
            cluster["frame_presence"].append(
                {
                    "frame_id": 20,
                    "status": status,
                    "description": f"frame 20 is {status}",
                }
            )

        for kind in ("relative_motion", "independent_trajectory"):
            with self.subTest(kind=kind):
                one_frame = copy.deepcopy(plan)
                witness = one_frame["families"][0]["independence_witnesses"][0]
                witness["kind"] = kind
                with self.assertRaisesRegex(
                    FAMILY.FamilyPlanError,
                    "motion/trajectory witness needs at least two frames",
                ):
                    FAMILY.validate_family_plan(
                        one_frame,
                        shot_id=SHOT_ID,
                        baseline=baseline,
                        anonymous_view=FAMILY._planner_view(anonymous_view),
                        valid_frame_ids=[10, 20],
                    )

                two_frames = copy.deepcopy(one_frame)
                two_frames["families"][0]["independence_witnesses"][0]["frame_ids"] = [
                    10,
                    20,
                ]
                FAMILY.validate_family_plan(
                    two_frames,
                    shot_id=SHOT_ID,
                    baseline=baseline,
                    anonymous_view=FAMILY._planner_view(anonymous_view),
                    valid_frame_ids=[10, 20],
                )

    def test_complete_witness_keeps_baseline_members_deep_equal(self):
        plan, baseline, anonymous_view, source_map, _ = _fixture(witness_mode="full")
        baseline_before = copy.deepcopy(baseline)
        resolution = FAMILY._select_resolutions(
            plan,
            FAMILY.build_panel_positions(plan, source_map, DETECTOR_IDS),
        )[0]
        final, audit = FAMILY._assemble_final(
            baseline=baseline,
            anonymous_view=anonymous_view,
            plan=plan,
            resolutions=[resolution],
            shot_id=SHOT_ID,
            valid_frame_ids=FRAME_IDS,
        )
        self.assertEqual(final, baseline_before)
        self.assertEqual(baseline, baseline_before)
        self.assertEqual(audit["applied_family_ids"], [])
        self.assertEqual(
            audit["frozen_nonfamily_cluster_ids"],
            [cluster["cluster_id"] for cluster in baseline["clusters"]],
        )

    def test_presence_merge_uses_conservative_truth_table(self):
        cases = {
            ("visible", "visible"): "visible",
            ("absent", "absent"): "absent",
            ("occluded", "occluded"): "occluded",
            ("visible", "occluded"): "occluded",
            ("visible", "absent"): "uncertain",
            ("occluded", "absent"): "uncertain",
            ("visible", "uncertain"): "uncertain",
        }
        for statuses, expected in cases.items():
            with self.subTest(statuses=statuses):
                anchors = [
                    {
                        "frame_presence": [
                            {
                                "frame_id": 10,
                                "status": status,
                                "description": status,
                            }
                        ]
                    }
                    for status in statuses
                ]
                merged = FAMILY._merge_frame_presence(anchors, FRAME_IDS)
                self.assertEqual(merged[0]["status"], expected)
                for status in statuses:
                    self.assertIn(status, merged[0]["description"])

    def test_coarsening_uses_frozen_name_anchor_evidence_and_attributes(self):
        plan, baseline, anonymous_view, source_map, _ = _fixture()
        baseline_before = copy.deepcopy(baseline)
        resolution = FAMILY._select_resolutions(
            plan,
            FAMILY.build_panel_positions(plan, source_map, DETECTOR_IDS),
        )[0]
        final, audit = FAMILY._assemble_final(
            baseline=baseline,
            anonymous_view=anonymous_view,
            plan=plan,
            resolutions=[resolution],
            shot_id=SHOT_ID,
            valid_frame_ids=FRAME_IDS,
        )
        self.assertEqual(baseline, baseline_before)

        group = next(
            cluster
            for cluster in final["clusters"]
            if cluster["cluster_id"].startswith("gf_")
        )
        self.assertEqual(
            set(group["anonymous_proposal_ids"]),
            set(plan["families"][0]["scope_proposal_ids"]),
        )
        self.assertEqual(group["decision"], "accept")
        self.assertEqual(group["identity_status"], "resolved")
        self.assertEqual(group["canonical_name"], "frozen compact display")
        self.assertEqual(group["final_entity"]["name"], "frozen compact display")
        self.assertNotEqual(
            group["canonical_name"],
            next(
                item["proposed_name"]
                for item in anonymous_view["proposals"]
                if item["anonymous_proposal_id"] == "p0001"
            ),
        )
        self.assertEqual(
            group["final_entity"]["attributes"],
            [
                _attribute("color", "white", 0.75),
                {
                    "name": "graph_components",
                    "value": "first unit; second unit; third unit",
                    "confidence": 0.82,
                    "evidence_frame_ids": [10],
                },
            ],
        )
        self.assertEqual(group["final_entity"]["entity_confidence"], 0.82)
        evidence_locators = {
            item["coarse_locator"] for item in group["adjudicator_evidence"]
        }
        self.assertEqual(
            evidence_locators,
            {
                "accepted evidence one",
                "accepted evidence two",
                "accepted evidence three",
            },
        )
        self.assertNotIn("rejected-only evidence", evidence_locators)

        outside_before = next(
            cluster
            for cluster in baseline_before["clusters"]
            if cluster["cluster_id"] == "c_outside"
        )
        outside_after = next(
            cluster
            for cluster in final["clusters"]
            if cluster["cluster_id"] == "c_outside"
        )
        self.assertEqual(outside_after, outside_before)
        self.assertEqual(audit["frozen_nonfamily_cluster_ids"], ["c_outside"])
        self.assertEqual(audit["changed_outside_family_cluster_ids"], [])
        self.assertEqual(audit["applied_family_ids"], ["gf1"])
        self.assertEqual(audit["frozen_content_unit_count"], 3)
        anchors_by_id = {
            item["anchor_cluster_id"]: item for item in audit["frozen_content_units"]
        }
        for cluster_id in ("c_member_1", "c_member_2", "c_member_3"):
            expected_cluster = next(
                cluster
                for cluster in baseline_before["clusters"]
                if cluster["cluster_id"] == cluster_id
            )
            self.assertEqual(
                anchors_by_id[cluster_id]["immutable_anchor_cluster"],
                expected_cluster,
            )
            self.assertEqual(
                anchors_by_id[cluster_id]["anchor_cluster_sha256"],
                FAMILY._json_hash(expected_cluster),
            )
        self.assertFalse(audit["panel_positions_gate_family_application"])
        self.assertFalse(audit["panel_positions_select_group_vs_members"])
        self.assertEqual(audit["post_provenance_model_calls"], 0)
        self.assertFalse(audit["cross_shot_input"])

    def test_coarsening_preserves_repeated_component_counts(self):
        plan, baseline, anonymous_view, source_map, _ = _fixture()
        for cluster in baseline["clusters"]:
            if cluster["cluster_id"] in {"c_member_1", "c_member_2"}:
                cluster["final_entity"]["name"] = "repeated unit"
        resolution = FAMILY._select_resolutions(
            plan,
            FAMILY.build_panel_positions(plan, source_map, DETECTOR_IDS),
        )[0]
        final, _ = FAMILY._assemble_final(
            baseline=baseline,
            anonymous_view=anonymous_view,
            plan=plan,
            resolutions=[resolution],
            shot_id=SHOT_ID,
            valid_frame_ids=FRAME_IDS,
        )
        group = next(
            cluster
            for cluster in final["clusters"]
            if cluster["cluster_id"].startswith("gf_")
        )
        components = next(
            item["value"]
            for item in group["final_entity"]["attributes"]
            if item["name"] == "graph_components"
        )
        self.assertEqual(components, "2 × repeated unit; third unit")

    def test_exact_two_planner_structure_and_partition_consensus_applies(self):
        plan, baseline, anonymous_view, _, _ = _fixture()
        second_plan = _planner_variant(plan)
        planner_view = ENSEMBLE.family_stage.planner_view(anonymous_view)
        for candidate in (plan, second_plan):
            ENSEMBLE.family_stage.validate_family_plan(
                candidate,
                shot_id=SHOT_ID,
                baseline=baseline,
                anonymous_view=planner_view,
                valid_frame_ids=FRAME_IDS,
                base_protocol=ENSEMBLE.PROTOCOL_VERSION,
            )

        consensus = ENSEMBLE.family_stage.select_consensus_resolutions(
            plan, second_plan
        )
        self.assertEqual(len(consensus), 1)
        self.assertEqual(consensus[0]["status"], "applied")
        self.assertEqual(consensus[0]["selected_kind"], "group")
        self.assertEqual(consensus[0]["first_planner_family_ids"], ["gf1"])
        self.assertEqual(consensus[0]["second_planner_family_ids"], ["gf9"])

        final, audit, application_plan, application_resolutions = (
            ENSEMBLE.family_stage.assemble_consensus(
                baseline=baseline,
                anonymous_view=planner_view,
                first_plan=plan,
                second_plan=second_plan,
                consensus_resolutions=consensus,
                shot_id=SHOT_ID,
                valid_frame_ids=FRAME_IDS,
                base_protocol=ENSEMBLE.PROTOCOL_VERSION,
            )
        )
        self.assertEqual(
            [item["family_id"] for item in application_plan["families"]],
            ["gf1"],
        )
        self.assertEqual(application_resolutions[0]["selected_kind"], "group")
        self.assertEqual(audit["planner_count"], 2)
        self.assertTrue(audit["exact_family_member_partition_consensus_required"])
        self.assertEqual(
            sum(
                cluster["cluster_id"].startswith("gf_") for cluster in final["clusters"]
            ),
            1,
        )

    def test_missing_or_partition_disagreement_preserves_baseline(self):
        group_plan, baseline, anonymous_view, _, _ = _fixture()
        empty_plan = {
            "protocol_version": FAMILY.FAMILY_PLAN_PROTOCOL,
            "shot_id": SHOT_ID,
            "reviewed_group_alternative_cluster_ids": ["c_group"],
            "excluded_group_alternatives": [
                {
                    "cluster_id": "c_group",
                    "candidate_member_anchor_cluster_ids": [
                        "c_member_1",
                        "c_member_2",
                        "c_member_3",
                    ],
                    "independent_context_anchor_cluster_ids": [],
                    "reason_code": "insufficient_joint_visibility",
                    "reason": (
                        "Original-pixel review does not provide joint visibility "
                        "for a strict same-content family."
                    ),
                }
            ],
            "families": [],
            "warnings": [],
        }
        member_plan = _planner_variant(group_plan, witness_mode="partial")
        planner_view = ENSEMBLE.family_stage.planner_view(anonymous_view)
        for label, second_plan, expected_basis in (
            (
                "missing family",
                empty_plan,
                "missing_exact_family_or_member_set_in_one_planner",
            ),
            (
                "partition disagreement",
                member_plan,
                "group_members_partition_disagreement",
            ),
        ):
            with self.subTest(label=label):
                consensus = ENSEMBLE.family_stage.select_consensus_resolutions(
                    group_plan, second_plan
                )
                self.assertEqual(consensus[0]["status"], "kept_baseline")
                self.assertEqual(consensus[0]["basis"], expected_basis)
                final, _, application_plan, application_resolutions = (
                    ENSEMBLE.family_stage.assemble_consensus(
                        baseline=baseline,
                        anonymous_view=planner_view,
                        first_plan=group_plan,
                        second_plan=second_plan,
                        consensus_resolutions=consensus,
                        shot_id=SHOT_ID,
                        valid_frame_ids=FRAME_IDS,
                        base_protocol=ENSEMBLE.PROTOCOL_VERSION,
                    )
                )
                self.assertEqual(final, baseline)
                self.assertEqual(application_plan["families"], [])
                self.assertEqual(application_resolutions, [])

    def test_exact_members_consensus_and_tamper_both_fail_closed(self):
        first_plan, baseline, anonymous_view, _, _ = _fixture(witness_mode="partial")
        second_plan = _planner_variant(first_plan, witness_mode="partial")
        consensus = ENSEMBLE.family_stage.select_consensus_resolutions(
            first_plan, second_plan
        )
        self.assertEqual(consensus[0]["status"], "kept_baseline")
        self.assertEqual(consensus[0]["selected_kind"], "members")
        final, _, application_plan, _ = ENSEMBLE.family_stage.assemble_consensus(
            baseline=baseline,
            anonymous_view=ENSEMBLE.family_stage.planner_view(anonymous_view),
            first_plan=first_plan,
            second_plan=second_plan,
            consensus_resolutions=consensus,
            shot_id=SHOT_ID,
            valid_frame_ids=FRAME_IDS,
            base_protocol=ENSEMBLE.PROTOCOL_VERSION,
        )
        self.assertEqual(final, baseline)
        self.assertEqual(application_plan["families"], [])

        tampered = copy.deepcopy(consensus)
        tampered[0]["status"] = "applied"
        with self.assertRaisesRegex(
            ENSEMBLE.family_stage.FamilyPlanError,
            "Consensus resolution payload was modified",
        ):
            ENSEMBLE.family_stage.assemble_consensus(
                baseline=baseline,
                anonymous_view=ENSEMBLE.family_stage.planner_view(anonymous_view),
                first_plan=first_plan,
                second_plan=second_plan,
                consensus_resolutions=tampered,
                shot_id=SHOT_ID,
                valid_frame_ids=FRAME_IDS,
                base_protocol=ENSEMBLE.PROTOCOL_VERSION,
            )

    def test_valid_cross_planner_overlapping_families_preserve_baseline(self):
        first_plan, baseline, anonymous_view, _, _ = _fixture()
        baseline = copy.deepcopy(baseline)
        anonymous_view = copy.deepcopy(anonymous_view)
        baseline["clusters"].insert(
            1,
            _cluster(
                "c_group_2",
                ["p0011"],
                "second supported group alternative",
                decision="reject",
            ),
        )
        anonymous_view["proposals"].append(
            {
                "anonymous_proposal_id": "p0011",
                **_proposal_payload("second supported group alternative"),
            }
        )
        first_plan["reviewed_group_alternative_cluster_ids"] = [
            "c_group",
            "c_group_2",
        ]
        first_plan["excluded_group_alternatives"] = [
            {
                "cluster_id": "c_group_2",
                "candidate_member_anchor_cluster_ids": [
                    "c_member_1",
                    "c_member_2",
                    "c_member_3",
                ],
                "independent_context_anchor_cluster_ids": [],
                "reason_code": "overlaps_another_family",
                "reason": "The alternative overlaps the first reviewed family.",
            }
        ]
        second_plan = _planner_variant(first_plan)
        second_plan["excluded_group_alternatives"] = [
            {
                "cluster_id": "c_group",
                "candidate_member_anchor_cluster_ids": [
                    "c_member_1",
                    "c_member_2",
                    "c_member_3",
                ],
                "independent_context_anchor_cluster_ids": [],
                "reason_code": "overlaps_another_family",
                "reason": "The alternative overlaps the second reviewed family.",
            }
        ]
        second_family = second_plan["families"][0]
        second_family["baseline_cluster_ids"] = [
            "c_group_2",
            "c_member_1",
            "c_member_2",
            "c_member_3",
        ]
        second_family["scope_proposal_ids"] = [
            proposal_id
            for proposal_id in second_family["scope_proposal_ids"]
            if proposal_id not in {"p0001", "p0005"}
        ] + ["p0011"]
        second_family["proposal_roles"] = [
            role
            for role in second_family["proposal_roles"]
            if role["proposal_id"] not in {"p0001", "p0005"}
        ] + [
            {
                "proposal_id": "p0011",
                "role": "group",
                "covers_unit_ids": ["u1", "u2", "u3"],
                "same_content_evidence": [
                    {
                        "unit_id": unit_id,
                        "anchor_cluster_id": f"c_member_{unit_id[1:]}",
                        "frame_id": 10,
                        "description": "second group covers this exact anchor",
                    }
                    for unit_id in ("u1", "u2", "u3")
                ],
                "reason": "independent group alternative",
            }
        ]
        planner_view = ENSEMBLE.family_stage.planner_view(anonymous_view)
        for candidate in (first_plan, second_plan):
            ENSEMBLE.family_stage.validate_family_plan(
                candidate,
                shot_id=SHOT_ID,
                baseline=baseline,
                anonymous_view=planner_view,
                valid_frame_ids=FRAME_IDS,
                base_protocol=ENSEMBLE.PROTOCOL_VERSION,
            )
        consensus = ENSEMBLE.family_stage.select_consensus_resolutions(
            first_plan, second_plan
        )
        self.assertEqual(len(consensus), 2)
        self.assertTrue(
            all(
                item["basis"] == "overlapping_or_nested_family_component"
                for item in consensus
            )
        )
        final, _, application_plan, _ = ENSEMBLE.family_stage.assemble_consensus(
            baseline=baseline,
            anonymous_view=planner_view,
            first_plan=first_plan,
            second_plan=second_plan,
            consensus_resolutions=consensus,
            shot_id=SHOT_ID,
            valid_frame_ids=FRAME_IDS,
            base_protocol=ENSEMBLE.PROTOCOL_VERSION,
        )
        self.assertEqual(final, baseline)
        self.assertEqual(application_plan["families"], [])


class GranularityFamilyConsensusIntegrationTest(unittest.TestCase):
    def _paths(self, root):
        prompt_dir = root / "prompts"
        attempt_dir = root / "attempts"
        adjudication_dir = root / "adjudication"
        work_dirs = [root / "planner_1", root / "planner_2"]
        for path in [prompt_dir, attempt_dir, adjudication_dir, *work_dirs]:
            path.mkdir(parents=True, exist_ok=False)
        frame_path = root / "frame_10.jpg"
        frame_path.write_bytes(b"frame-10")
        shot_manifest = {
            "shot_id": SHOT_ID,
            "num_frames": 1,
            "fps": 1.0,
            "reference_frames": [
                {
                    "attachment_index": 1,
                    "frame_id": 10,
                    "timestamp_sec": 0.0,
                    "path": str(frame_path),
                    "sha256": "frame-hash",
                }
            ],
            "prompt_bound_registry": "/private/registry-must-not-leak.json",
        }
        return (
            prompt_dir,
            attempt_dir,
            adjudication_dir,
            work_dirs,
            frame_path,
            shot_manifest,
        )

    def test_two_planners_are_identical_input_isolated_and_consensus_gated(self):
        plan, baseline, anonymous_view, _, _ = _fixture()
        second_plan = _planner_variant(plan)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (
                prompt_dir,
                attempt_dir,
                adjudication_dir,
                work_dirs,
                frame_path,
                shot_manifest,
            ) = self._paths(root)
            calls = []
            call_lock = threading.Lock()

            def fake_codex(**kwargs):
                planner_index = int(kwargs["work_dir"].name.rsplit("_", 1)[1])
                with call_lock:
                    calls.append(kwargs)
                payload = plan if planner_index == 1 else second_plan
                return ENSEMBLE.CodexInvocation(
                    copy.deepcopy(payload),
                    _usage(10 * planner_index, planner_index),
                    f"thread-{planner_index}",
                    0.01,
                )

            with mock.patch.object(ENSEMBLE, "run_codex_json", side_effect=fake_codex):
                final, result = ENSEMBLE.run_group_member_family_stage(
                    shot_id=SHOT_ID,
                    shot_manifest=shot_manifest,
                    attachments=[frame_path],
                    skill_text="general single-shot partition policy",
                    baseline=baseline,
                    anonymous_view=anonymous_view,
                    anonymous_ids=sorted(
                        item["anonymous_proposal_id"]
                        for item in anonymous_view["proposals"]
                    ),
                    valid_frame_ids=FRAME_IDS,
                    codex_bin="codex",
                    model=None,
                    timeout_sec=5,
                    work_dirs=work_dirs,
                    prompt_dir=prompt_dir,
                    attempt_dir=attempt_dir,
                    adjudication_dir=adjudication_dir,
                    verbose=False,
                )

            self.assertEqual(result["status"], "applied")
            self.assertEqual(result["invocation_count"], 2)
            self.assertEqual(result["valid_planner_count"], 2)
            self.assertEqual(result["synthetic_empty_plan_count"], 0)
            self.assertEqual(
                [
                    (item["planner_index"], item["attempt"])
                    for item in result["attempts"]
                ],
                [(1, 1), (2, 1)],
            )
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0]["prompt"], calls[1]["prompt"])
            self.assertEqual(calls[0]["attachments"], calls[1]["attachments"])
            self.assertEqual(calls[0]["schema_path"], calls[1]["schema_path"])
            self.assertEqual({call["work_dir"] for call in calls}, set(work_dirs))
            self.assertTrue(all(call["persistent"] is False for call in calls))
            self.assertNotIn(
                "registry-must-not-leak",
                result["prompt_path"].read_text(encoding="utf-8"),
            )
            self.assertTrue(all(path.is_file() for path in result["paths"].values()))
            self.assertEqual(
                sum(
                    cluster["cluster_id"].startswith("gf_")
                    for cluster in final["clusters"]
                ),
                1,
            )

    def test_valid_planner_disagreement_is_successful_baseline_noop(self):
        first_plan, baseline, anonymous_view, _, _ = _fixture()
        second_plan = _planner_variant(first_plan, witness_mode="partial")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (
                prompt_dir,
                attempt_dir,
                adjudication_dir,
                work_dirs,
                frame_path,
                shot_manifest,
            ) = self._paths(root)

            def fake_codex(**kwargs):
                planner_index = int(kwargs["work_dir"].name.rsplit("_", 1)[1])
                payload = first_plan if planner_index == 1 else second_plan
                return ENSEMBLE.CodexInvocation(
                    copy.deepcopy(payload), _usage(10, 1), None, 0.01
                )

            with mock.patch.object(ENSEMBLE, "run_codex_json", side_effect=fake_codex):
                final, result = ENSEMBLE.run_group_member_family_stage(
                    shot_id=SHOT_ID,
                    shot_manifest=shot_manifest,
                    attachments=[frame_path],
                    skill_text="general single-shot partition policy",
                    baseline=baseline,
                    anonymous_view=anonymous_view,
                    anonymous_ids=sorted(
                        item["anonymous_proposal_id"]
                        for item in anonymous_view["proposals"]
                    ),
                    valid_frame_ids=FRAME_IDS,
                    codex_bin="codex",
                    model=None,
                    timeout_sec=5,
                    work_dirs=work_dirs,
                    prompt_dir=prompt_dir,
                    attempt_dir=attempt_dir,
                    adjudication_dir=adjudication_dir,
                    verbose=False,
                )
            self.assertEqual(final, baseline)
            self.assertEqual(result["status"], "no_consensus_family")
            self.assertEqual(
                result["consensus_resolutions"][0]["basis"],
                "group_members_partition_disagreement",
            )

    def test_ineligible_shape_uses_two_empty_plans_without_model_calls(self):
        _, baseline, anonymous_view, _, _ = _fixture()
        baseline = copy.deepcopy(baseline)
        baseline["clusters"][0]["uncertainty_flags"] = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (
                prompt_dir,
                attempt_dir,
                adjudication_dir,
                work_dirs,
                frame_path,
                shot_manifest,
            ) = self._paths(root)
            with mock.patch.object(ENSEMBLE, "run_codex_json") as codex_mock:
                final, result = ENSEMBLE.run_group_member_family_stage(
                    shot_id=SHOT_ID,
                    shot_manifest=shot_manifest,
                    attachments=[frame_path],
                    skill_text="general single-shot partition policy",
                    baseline=baseline,
                    anonymous_view=anonymous_view,
                    anonymous_ids=sorted(
                        item["anonymous_proposal_id"]
                        for item in anonymous_view["proposals"]
                    ),
                    valid_frame_ids=FRAME_IDS,
                    codex_bin="codex",
                    model=None,
                    timeout_sec=5,
                    work_dirs=work_dirs,
                    prompt_dir=prompt_dir,
                    attempt_dir=attempt_dir,
                    adjudication_dir=adjudication_dir,
                    verbose=False,
                )
            codex_mock.assert_not_called()
            self.assertEqual(final, baseline)
            self.assertEqual(result["status"], "deterministically_skipped")
            self.assertEqual(result["invocation_count"], 0)
            self.assertEqual(result["synthetic_empty_plan_count"], 2)
            self.assertEqual(
                [len(plan["families"]) for plan in result["plans"]], [0, 0]
            )

    def test_exhausted_planner_retry_fails_with_complete_attempt_ledger(self):
        plan, baseline, anonymous_view, _, _ = _fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (
                prompt_dir,
                attempt_dir,
                adjudication_dir,
                work_dirs,
                frame_path,
                shot_manifest,
            ) = self._paths(root)

            def fake_codex(**kwargs):
                if kwargs["work_dir"] == work_dirs[0]:
                    kwargs["events_path"].write_text(
                        json.dumps({"usage": _usage(30, 3)}) + "\n",
                        encoding="utf-8",
                    )
                    raise ENSEMBLE.EnsembleError("planner one invalid")
                return ENSEMBLE.CodexInvocation(
                    copy.deepcopy(plan), _usage(40, 4), "thread-2", 0.01
                )

            with mock.patch.object(ENSEMBLE, "run_codex_json", side_effect=fake_codex):
                final, result = ENSEMBLE.run_group_member_family_stage(
                    shot_id=SHOT_ID,
                    shot_manifest=shot_manifest,
                    attachments=[frame_path],
                    skill_text="general single-shot partition policy",
                    baseline=baseline,
                    anonymous_view=anonymous_view,
                    anonymous_ids=sorted(
                        item["anonymous_proposal_id"]
                        for item in anonymous_view["proposals"]
                    ),
                    valid_frame_ids=FRAME_IDS,
                    codex_bin="codex",
                    model=None,
                    timeout_sec=5,
                    work_dirs=work_dirs,
                    prompt_dir=prompt_dir,
                    attempt_dir=attempt_dir,
                    adjudication_dir=adjudication_dir,
                    verbose=False,
                )
            self.assertEqual(final, baseline)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["invocation_count"], 3)
            self.assertEqual(result["valid_planner_count"], 1)
            self.assertEqual(result["failed_planner_indices"], [1])
            self.assertEqual(
                [
                    (item["planner_index"], item["attempt"], item["status"])
                    for item in result["attempts"]
                ],
                [
                    (1, 1, "failed"),
                    (1, 2, "failed"),
                    (2, 1, "success"),
                ],
            )
            self.assertEqual(
                result["token_usages"],
                [_usage(30, 3), _usage(30, 3), _usage(40, 4)],
            )
            failure = json.loads(result["paths"]["failure"].read_text(encoding="utf-8"))
            self.assertEqual(failure["missing_planner_indices"], [1])
            self.assertNotIn("firewall", result["paths"])


if __name__ == "__main__":
    unittest.main()
