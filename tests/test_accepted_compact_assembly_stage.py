import copy
import hashlib
import json
import sys
import unittest
from itertools import combinations
from pathlib import Path

import jsonschema


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import accepted_compact_assembly_stage as STAGE  # noqa: E402


SHOT_ID = "shot_test"
BASE_PROTOCOL = "single_shot_inventory_test_v1"
FRAME_IDS = [10, 20, 30]


def _attribute(name, value, confidence=0.8):
    return {
        "name": name,
        "value": value,
        "confidence": confidence,
        "evidence_frame_ids": [10, 20],
    }


def _cluster(cluster_id, proposal_id, name, *, decision="accept", confidence=0.9):
    accepted = decision == "accept"
    return {
        "cluster_id": cluster_id,
        "anonymous_proposal_ids": [proposal_id],
        "canonical_name": name,
        "aliases": [name, f"alias-{name}"],
        "granularity": "whole",
        "adjudicator_evidence": [
            {
                "frame_id": 10,
                "coarse_locator": f"pixels occupied by {name}",
                "support_quality": "strong" if accepted else "weak",
            }
        ],
        "frame_presence": [
            {
                "frame_id": frame_id,
                "status": "visible" if accepted else "uncertain",
                "description": f"{name} at frame {frame_id}",
                "bbox_xyxy_normalized": [0.1, 0.1, 0.2, 0.2],
            }
            for frame_id in FRAME_IDS
        ],
        "identity_status": "resolved" if accepted else "ambiguous",
        "decision": decision,
        "decision_reason": "private decision narrative",
        "uncertainty_flags": ["private_source_flag"],
        "detector_support_count": 4,
        "final_entity": (
            {
                "name": name,
                "attributes": [_attribute("shared", "value")],
                "entity_confidence": confidence,
                "evidence_frame_ids": [10, 20],
            }
            if accepted
            else None
        ),
    }


def _baseline():
    return {
        "protocol_version": BASE_PROTOCOL,
        "shot_id": SHOT_ID,
        "clusters": [
            _cluster("c1", "p0001", "first component", confidence=0.91),
            _cluster("c2", "p0002", "second component", confidence=0.83),
            _cluster("c3", "p0003", "third component", confidence=0.88),
            _cluster("c4", "p0004", "fourth component", confidence=0.87),
            _cluster("c5", "p0005", "fifth component", confidence=0.86),
            _cluster("c6", "p0006", "sixth component", confidence=0.85),
            _cluster("c_reject", "p0098", "rejected region", decision="reject"),
            _cluster("c_abstain", "p0099", "uncertain region", decision="abstain"),
        ],
        "warnings": ["frozen warning"],
    }


def _visual_evidence(frame_id=10, description="direct original-pixel evidence"):
    return {"frame_id": frame_id, "description": description}


def _independence_checks():
    return [
        {
            "kind": kind,
            "outcome": "not_observed",
            "evidence": [],
            "description": f"Reviewed all frames; {kind} is not observed.",
        }
        for kind in sorted(STAGE.INDEPENDENCE_KINDS)
    ]


def _protected_reviews():
    return [
        {
            "kind": kind,
            "outcome": "absent",
            "evidence": [],
            "description": f"The protected case {kind} is absent.",
        }
        for kind in sorted(STAGE.PROTECTED_RELATION_KINDS)
    ]


def _cohesion_kind(assembly_kind):
    return {
        "integrated_part_whole": "shared_continuous_housing_or_joint",
        "small_container_contents_unit": "same_small_container_functional_unit",
        "fixed_coordinated_array": "common_fixed_mounting_or_array",
        "passive_homogeneous_collection": "same_fixture_bounded_passive_homogeneous_content",
        "directly_coupled_operational_unit": (
            "direct_mechanical_or_operational_coupling"
        ),
    }[assembly_kind]


def _scope_review(frame_ids=FRAME_IDS, box=(0.1, 0.1, 0.2, 0.2)):
    return {"observations": [
        {"frame_id": f, "correspondence": "matched", "coverage": "complete_visible_claim",
         "bbox_xyxy_normalized": list(box), "boundary_evidence": "Full frozen content boundary is visible.", "limitation": "none"}
        for f in frame_ids
    ]}


def _reference_review(anchor_ids, kind, *, reference_id=None, external=False, frame_ids=FRAME_IDS):
    ref_id = reference_id or anchor_ids[0]
    relation = {
        "shared_continuous_housing_or_joint": "part_of_housing_or_joint",
        "same_small_container_functional_unit": "contained_in_or_inserted_into",
        "common_fixed_mounting_or_array": "mounted_on_common_structure",
        "stable_complementary_same_role_array_about_external_reference": "complementary_array_member_about",
        "direct_mechanical_or_operational_coupling": "directly_coupled_to",
        "same_fixture_bounded_passive_homogeneous_content": "fixture_organized_passive_content",
    }[kind]
    return {
        "reference_type": "accepted_anchor", "reference_anchor_cluster_id": ref_id,
        "external_reference_excluded": external,
        "observations": [{"frame_id": f, "bbox_xyxy_normalized": [0.1, 0.1, 0.2, 0.2],
                          "boundary_status": "bounded_visible_structure",
                          "boundary_evidence": "Visible physical reference boundary.", "limitation": "none"}
                         for f in frame_ids],
        "member_relations": [{"frame_id": f, "anchor_cluster_id": a, "relation": relation,
                              "outcome": "supported", "member_locus_bbox_xyxy_normalized": [0.12, 0.12, 0.15, 0.15],
                              "reference_locus_bbox_xyxy_normalized": [0.12, 0.12, 0.15, 0.15],
                              "boundary_evidence": "Direct organization at localized loci.", "limitation": "none"}
                             for f in frame_ids for a in anchor_ids],
    }


def _family(
    family_id,
    anchor_ids,
    *,
    assembly_kind="fixed_coordinated_array",
    context_ids=(),
):
    unit_by_anchor = {
        anchor_id: f"u{index + 1}" for index, anchor_id in enumerate(anchor_ids)
    }
    unit_ids = list(unit_by_anchor.values())
    pairs = list(combinations(unit_ids, 2))
    return {
        "family_id": family_id,
        "candidate_id": _candidate_id(anchor_ids),
        "visual_scope": "one compact original-pixel scope",
        "anchor_cluster_ids": list(anchor_ids),
        "content_units": [
            {
                "unit_id": unit_by_anchor[anchor_id],
                "anchor_cluster_id": anchor_id,
                "description": f"physical content of {anchor_id}",
                "pixel_evidence": [_visual_evidence()],
                "anchor_scope_review": _scope_review(),
            }
            for anchor_id in anchor_ids
        ],
        "assembly_kind": assembly_kind,
        "collection_scope_review": None,
        "common_visible_frame_ids": list(FRAME_IDS),
        "cohesion_witnesses": [
            {
                "witness_id": f"cw{index + 1}",
                "unit_a_id": first,
                "unit_b_id": second,
                "kind": _cohesion_kind(assembly_kind),
                "frame_ids": [10, 20],
                "description": f"{first} and {second} share a fixed assembly.",
                "reference_review": _reference_review(
                    [a for a, u in unit_by_anchor.items() if u in (first, second)],
                    _cohesion_kind(assembly_kind),
                    reference_id="c3" if assembly_kind == "passive_homogeneous_collection" else sorted(anchor_ids)[0],
                    external=assembly_kind == "passive_homogeneous_collection",
                ),
            }
            for index, (first, second) in enumerate(pairs)
        ],
        "pairwise_independence_reviews": [
            {
                "unit_a_id": first,
                "unit_b_id": second,
                "reviewed_frame_ids": list(FRAME_IDS),
                "checks": _independence_checks(),
            }
            for first, second in pairs
        ],
        "protected_relation_reviews": _protected_reviews(),
        "context_exclusion_reviews": [
            {
                "context_anchor_cluster_id": context_id,
                "reviewed_frame_ids": list(FRAME_IDS),
                "outcome": "excluded_from_minimal_closure",
                "evidence": [_visual_evidence()],
                "description": "Direct pixels show a different-role context anchor.",
            }
            for context_id in context_ids
        ],
        "scope_review_complete": True,
        "minimal_cohesive_closure_confirmed": True,
        "reason": "All positive and exclusion evidence has been reviewed.",
    }


def _candidate_id(anchor_ids):
    payload = json.dumps(
        {"anchor_cluster_ids": sorted(anchor_ids)},
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"aca_{hashlib.sha256(payload.encode()).hexdigest()[:12]}"


def _exclusion(anchor_ids, reason_code="insufficient_positive_same_role_cohesion"):
    return {
        "candidate_id": _candidate_id(anchor_ids),
        "anchor_cluster_ids": list(anchor_ids),
        "reason_code": reason_code,
        "evidence": [],
        "reason": "The required positive evidence is not present.",
    }


def _plan(families, excluded=()):
    candidate_ids = [item["candidate_id"] for item in [*families, *excluded]]
    return {
        "protocol_version": STAGE.PLAN_PROTOCOL,
        "shot_id": SHOT_ID,
        "reviewed_accepted_cluster_ids": [
            "c1",
            "c2",
            "c3",
            "c4",
            "c5",
            "c6",
        ],
        "reviewed_candidate_ids": candidate_ids,
        "families": families,
        "excluded_candidates": list(excluded),
        "warnings": [],
    }


def _candidate_bank_from_plan(plan):
    records = [*plan["families"], *plan["excluded_candidates"]]
    return {
        "protocol_version": STAGE.CANDIDATE_BANK_PROTOCOL,
        "shot_id": SHOT_ID,
        "candidates": [
            {
                "candidate_id": item["candidate_id"],
                "anchor_cluster_ids": list(item["anchor_cluster_ids"]),
                "context_anchor_cluster_ids": [
                    review["context_anchor_cluster_id"]
                    for review in item.get("context_exclusion_reviews", [])
                ],
            }
            for item in records
        ],
    }


def _validate(plan, baseline=None, candidate_bank=None):
    baseline = baseline or _baseline()
    candidate_bank = candidate_bank or _candidate_bank_from_plan(plan)
    view = STAGE.planner_baseline_view(
        baseline,
        candidate_bank=candidate_bank,
        shot_id=SHOT_ID,
        base_protocol=BASE_PROTOCOL,
    )
    STAGE.validate_plan(
        plan,
        shot_id=SHOT_ID,
        baseline=baseline,
        accepted_view=view,
        valid_frame_ids=FRAME_IDS,
        base_protocol=BASE_PROTOCOL,
    )
    return view


class AcceptedCompactAssemblyStageTests(unittest.TestCase):
    def test_vetoed_superset_does_not_block_unanimous_subset(self):
        baseline = _baseline()
        vetoes = [{
            "planner_index": 1,
            "family_id": "prior_family",
            "anchor_cluster_ids": ["c1", "c2", "c3"],
            "blocked_anchor_pairs": [["c1", "c3"], ["c2", "c3"]],
            "deterministic_audit": {"blocking_incompatibilities": [
                {"member_anchor_cluster_id": "c3"}
            ]},
        }]
        for second_proposes_superset in (False, True):
            with self.subTest(second_proposes_superset=second_proposes_superset):
                first = _plan([
                    _family("af_subset_1", ["c1", "c2"]),
                    _family("af_superset_1", ["c1", "c2", "c3"]),
                ])
                second = _plan(
                    [_family("af_subset_2", ["c1", "c2"])] + (
                        [_family("af_superset_2", ["c1", "c2", "c3"])]
                        if second_proposes_superset else []
                    ),
                    [] if second_proposes_superset else [
                        _exclusion(["c1", "c2", "c3"])
                    ],
                )
                bank = _candidate_bank_from_plan(first)
                _validate(first, baseline, bank)
                _validate(second, baseline, bank)
                # Without a deterministic veto, existing overlap protection stays.
                ordinary = STAGE.select_consensus_resolutions(first, second)
                self.assertTrue(all(r["status"] == "not_applied" for r in ordinary))
                resolutions = STAGE.select_consensus_resolutions(
                    first, second, spatial_vetoes=vetoes
                )
                by_anchors = {
                    tuple(r["anchor_cluster_ids"]): r for r in resolutions
                }
                self.assertEqual(by_anchors[("c1", "c2")]["status"], "applied")
                blocked = by_anchors[("c1", "c2", "c3")]
                self.assertEqual(blocked["status"], "not_applied")
                self.assertEqual(blocked["basis"], "gross_spatial_incompatibility_veto")
                self.assertEqual(blocked["spatial_vetoes"], vetoes)
                final, audit = STAGE.assemble_consensus(
                    baseline=baseline, first_plan=first, second_plan=second,
                    resolutions=resolutions, candidate_bank=bank,
                    shot_id=SHOT_ID, valid_frame_ids=FRAME_IDS,
                    base_protocol=BASE_PROTOCOL, spatial_vetoes=vetoes,
                )
                self.assertEqual(audit["applied_anchor_sets"], [["c1", "c2"]])
                self.assertEqual(final["clusters"][1:], baseline["clusters"][2:])
                self.assertEqual(audit["spatial_vetoes"], vetoes)

    def test_candidate_bank_uses_partition_neighborhoods_and_strips_derivation(self):
        baseline = _baseline()
        baseline["clusters"][4]["uncertainty_flags"].append(
            "possible_compact_assembly_partition"
        )
        baseline["clusters"][5]["uncertainty_flags"].append(
            "possible_compact_assembly_partition"
        )
        heads = {
            "p0001": ("sheet", "document"),
            "p0002": ("memo", "paper artifact"),
            "p0003": ("picture", "decoration"),
            "p0004": ("sheet", "document"),
            "p0005": ("curtain", "furnishing"),
            "p0006": ("curtain", "furnishing"),
        }
        anonymous_view = {
            "protocol_version": BASE_PROTOCOL,
            "shot_id": SHOT_ID,
            "proposals": [
                {
                    "anonymous_proposal_id": proposal_id,
                    "canonical_head": head,
                    "entity_type": entity_type,
                    "bbox_xyxy_normalized": [0.0, 0.0, 1.0, 1.0],
                    "detector_support_count": 99,
                }
                for proposal_id, (head, entity_type) in heads.items()
            ],
        }
        plans = [
            {
                "shot_id": SHOT_ID,
                "families": [],
                "excluded_group_alternatives": [
                    {
                        "cluster_id": "g1",
                        "candidate_member_anchor_cluster_ids": ["c1", "c2", "c3"],
                        "independent_context_anchor_cluster_ids": ["c3"],
                    }
                ],
            },
            {
                "shot_id": SHOT_ID,
                "families": [],
                "excluded_group_alternatives": [
                    {
                        "cluster_id": "g1",
                        "candidate_member_anchor_cluster_ids": [
                            "c1",
                            "c2",
                            "c3",
                            "c4",
                        ],
                        "independent_context_anchor_cluster_ids": ["c3"],
                    }
                ],
            },
        ]
        bank, audit = STAGE.build_candidate_bank(
            baseline=baseline,
            anonymous_view=anonymous_view,
            explicit_partition_plans=plans,
            shot_id=SHOT_ID,
            base_protocol=BASE_PROTOCOL,
        )
        candidates = {
            tuple(item["anchor_cluster_ids"]): item for item in bank["candidates"]
        }
        self.assertEqual(
            set(candidates),
            {("c1", "c2"), ("c1", "c2", "c4"), ("c5", "c6")},
        )
        self.assertEqual(
            candidates[("c1", "c2")]["context_anchor_cluster_ids"], ["c3"]
        )
        public_text = json.dumps(bank)
        for forbidden in (
            "p0001",
            "canonical_head",
            "entity_type",
            "derivation",
            "detector",
            "bbox",
            "count",
        ):
            self.assertNotIn(forbidden, public_text)
        self.assertTrue(audit["candidates"][0]["derivations"])
        self.assertFalse(audit["derivation_uses_detector_panels_or_counts"])

    def test_every_candidate_requires_exactly_one_structured_disposition(self):
        family = _family("af1", ["c1", "c2"])
        plan = _plan([family])
        plan["families"] = []
        with self.assertRaisesRegex(
            STAGE.AcceptedAssemblyError, "accounted for exactly once"
        ):
            _validate(
                plan,
                candidate_bank={
                    "protocol_version": STAGE.CANDIDATE_BANK_PROTOCOL,
                    "shot_id": SHOT_ID,
                    "candidates": [
                        {
                            "candidate_id": family["candidate_id"],
                            "anchor_cluster_ids": ["c1", "c2"],
                            "context_anchor_cluster_ids": [],
                        }
                    ],
                },
            )

    def test_context_review_is_mandatory_and_uncertainty_blocks_coarsening(self):
        first = _plan([_family("af1", ["c1", "c2"], context_ids=["c3"])])
        second = copy.deepcopy(first)
        second["families"][0]["family_id"] = "af2"
        _validate(first)
        uncertain = second["families"][0]["context_exclusion_reviews"][0]
        uncertain["outcome"] = "uncertain_membership"
        _validate(second)
        resolution = STAGE.select_consensus_resolutions(first, second)[0]
        self.assertEqual(resolution["status"], "not_applied")

    def test_schema_is_valid_and_forbids_free_naming(self):
        schema_path = (
            Path(__file__).resolve().parents[1]
            / "schemas"
            / "codex_accepted_compact_assembly_plan_v0.5.schema.json"
        )
        schema = json.loads(schema_path.read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        plan = _plan([_family("af1", ["c1", "c2"])])
        jsonschema.validate(plan, schema)

        with_name = copy.deepcopy(plan)
        with_name["families"][0]["canonical_name"] = "model-chosen name"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(with_name, schema)
        with self.assertRaisesRegex(STAGE.AcceptedAssemblyError, "extra"):
            _validate(with_name)

    def test_planner_view_strips_nonaccepted_provenance_proposals_and_boxes(self):
        baseline = _baseline()
        view = STAGE.planner_baseline_view(
            baseline,
            candidate_bank={
                "protocol_version": STAGE.CANDIDATE_BANK_PROTOCOL,
                "shot_id": SHOT_ID,
                "candidates": [],
            },
            shot_id=SHOT_ID,
            base_protocol=BASE_PROTOCOL,
        )
        serialized = json.dumps(view)
        self.assertEqual(
            [item["cluster_id"] for item in view["accepted_clusters"]],
            ["c1", "c2", "c3", "c4", "c5", "c6"],
        )
        for forbidden in (
            "anonymous_proposal_ids",
            "bbox_xyxy_normalized",
            "detector_support_count",
            "decision_reason",
            "uncertainty_flags",
            "c_reject",
            "c_abstain",
            "entity_confidence",
            '"confidence"',
        ):
            self.assertNotIn(forbidden, serialized)

    def test_prompt_contains_original_frames_but_not_private_baseline_fields(self):
        view = STAGE.planner_baseline_view(
            _baseline(),
            candidate_bank={
                "protocol_version": STAGE.CANDIDATE_BANK_PROTOCOL,
                "shot_id": SHOT_ID,
                "candidates": [],
            },
            shot_id=SHOT_ID,
            base_protocol=BASE_PROTOCOL,
        )
        manifest = {
            "reference_frames": [
                {"frame_id": frame_id, "path": f"/tmp/frame_{frame_id}.jpg"}
                for frame_id in FRAME_IDS
            ]
        }
        prompt = STAGE.build_prompt(
            shot_id=SHOT_ID,
            shot_manifest=manifest,
            accepted_view=view,
            policy_text="general policy",
        )
        self.assertIn("frame_10.jpg", prompt)
        self.assertIn("original frame", prompt)
        self.assertIn("Do not output a canonical name", prompt)
        self.assertIn(
            "stable_complementary_same_role_array_about_external_reference",
            prompt,
        )
        self.assertIn("at least two common-visible frames", prompt)
        self.assertIn("For that array the fixture stays external.", prompt)
        self.assertEqual(prompt.count(STAGE.HOLDING_CONTAINER_SCOPE_INSTRUCTION), 1)
        self.assertIn("complementary same-role array around one bounded excluded reference", prompt)
        self.assertIn("A continuous connector need not be visible", prompt)
        self.assertIn("Shared wording, semantic type, proximity", prompt)
        self.assertIn(
            "heterogeneous independent contents with only shared storage/support, "
            "and worn/body constituents cannot be absorbed",
            prompt,
        )
        self.assertIn("Selecting an assembly kind cannot bypass any of these protections", prompt)
        self.assertNotIn("p0001", prompt)
        self.assertNotIn("bbox_xyxy_normalized", prompt)

    def test_external_reference_array_cohesion_is_separately_auditable(self):
        plan = _plan([_family("af1", ["c1", "c2"])])
        witness = plan["families"][0]["cohesion_witnesses"][0]
        witness["kind"] = (
            "stable_complementary_same_role_array_about_external_reference"
        )
        witness["reference_review"] = _reference_review(
            ["c1", "c2"], witness["kind"], reference_id="c3", external=True,
        )
        witness["description"] = (
            "The repeated same-role units keep a complementary layout about one "
            "bounded external reference in frames 10 and 20; the reference and gap "
            "are excluded from the candidate content."
        )
        _validate(plan)

        schema_path = (
            Path(__file__).resolve().parents[1]
            / "schemas"
            / "codex_accepted_compact_assembly_plan_v0.5.schema.json"
        )
        jsonschema.validate(plan, json.loads(schema_path.read_text()))

        wrong_assembly = copy.deepcopy(plan)
        wrong_assembly["families"][0]["assembly_kind"] = "integrated_part_whole"
        with self.assertRaisesRegex(
            STAGE.AcceptedAssemblyError,
            "cohesion kind is incompatible with assembly_kind",
        ):
            _validate(wrong_assembly)

    def test_complete_pairwise_cohesion_and_reviews_are_required(self):
        valid = _plan([_family("af1", ["c1", "c2", "c3"])])
        _validate(valid)

        missing_cohesion = copy.deepcopy(valid)
        missing_cohesion["families"][0]["cohesion_witnesses"].pop()
        with self.assertRaisesRegex(
            STAGE.AcceptedAssemblyError, "cohesion must cover every unordered"
        ):
            _validate(missing_cohesion)

        missing_review = copy.deepcopy(valid)
        missing_review["families"][0]["pairwise_independence_reviews"].pop()
        with self.assertRaisesRegex(
            STAGE.AcceptedAssemblyError, "independence review must cover every pair"
        ):
            _validate(missing_review)

    def test_cohesion_requires_two_family_common_visible_frames(self):
        plan = _plan([_family("af1", ["c1", "c2"])])
        plan["families"][0]["cohesion_witnesses"][0]["frame_ids"] = [10]
        with self.assertRaisesRegex(STAGE.AcceptedAssemblyError, "two family-common"):
            _validate(plan)

        baseline = _baseline()
        baseline["clusters"][1]["frame_presence"][2]["status"] = "occluded"
        with self.assertRaisesRegex(
            STAGE.AcceptedAssemblyError, "must exactly equal"
        ):
            _validate(_plan([_family("af1", ["c1", "c2"])]), baseline)

    def test_observed_temporal_independence_requires_two_frames(self):
        plan = _plan([_family("af1", ["c1", "c2"])])
        check = next(
            item
            for item in plan["families"][0]["pairwise_independence_reviews"][0][
                "checks"
            ]
            if item["kind"] == "relative_motion"
        )
        check["outcome"] = "observed"
        check["evidence"] = [_visual_evidence(10, "relative displacement")]
        with self.assertRaisesRegex(STAGE.AcceptedAssemblyError, "needs two frames"):
            _validate(plan)

    def test_any_independence_or_protected_case_blocks_consensus(self):
        clear = _plan([_family("af1", ["c1", "c2"])])
        blocked = copy.deepcopy(clear)
        blocked_check = blocked["families"][0]["pairwise_independence_reviews"][0][
            "checks"
        ][0]
        blocked_check["outcome"] = "uncertain"
        blocked_check["evidence"] = [_visual_evidence()]
        _validate(clear)
        _validate(blocked)
        resolution = STAGE.select_consensus_resolutions(clear, blocked)[0]
        self.assertEqual(resolution["status"], "not_applied")
        self.assertIn("not_unanimously_clear", resolution["basis"])

        protected = copy.deepcopy(clear)
        review = protected["families"][0]["protected_relation_reviews"][0]
        review["outcome"] = "present"
        review["evidence"] = [_visual_evidence()]
        _validate(protected)
        resolution = STAGE.select_consensus_resolutions(clear, protected)[0]
        self.assertEqual(resolution["status"], "not_applied")

    def test_exact_two_planner_consensus_and_kind_agreement_are_required(self):
        first = _plan([_family("af1", ["c1", "c2"])])
        second = _plan([], [_exclusion(["c1", "c2"])])
        _validate(first)
        _validate(second)
        resolution = STAGE.select_consensus_resolutions(first, second)[0]
        self.assertEqual(resolution["status"], "not_applied")
        self.assertEqual(
            resolution["basis"], "one_or_both_planners_excluded_candidate"
        )

        second = _plan(
            [
                _family(
                    "af9",
                    ["c1", "c2"],
                    assembly_kind="integrated_part_whole",
                )
            ]
        )
        _validate(second)
        resolution = STAGE.select_consensus_resolutions(first, second)[0]
        self.assertEqual(resolution["status"], "not_applied")
        self.assertEqual(resolution["basis"], "assembly_kind_disagreement")

    def test_overlap_component_is_noop_while_disjoint_family_applies(self):
        first = _plan(
            [
                _family("af1", ["c1", "c2"]),
                _family("af2", ["c2", "c3"]),
                _family("af3", ["c4", "c5"]),
            ]
        )
        second = copy.deepcopy(first)
        for index, family in enumerate(second["families"], start=7):
            family["family_id"] = f"af{index}"
        _validate(first)
        _validate(second)
        resolutions = STAGE.select_consensus_resolutions(first, second)
        by_anchors = {
            tuple(item["anchor_cluster_ids"]): item for item in resolutions
        }
        self.assertEqual(by_anchors[("c1", "c2")]["status"], "not_applied")
        self.assertEqual(by_anchors[("c2", "c3")]["status"], "not_applied")
        self.assertEqual(by_anchors[("c4", "c5")]["status"], "applied")

    def test_nested_family_disagreement_is_noop(self):
        first = _plan(
            [_family("af1", ["c1", "c2"])],
            [_exclusion(["c1", "c2", "c3"])],
        )
        second = _plan(
            [_family("af2", ["c1", "c2", "c3"])],
            [_exclusion(["c1", "c2"])],
        )
        _validate(first)
        _validate(second)
        resolutions = STAGE.select_consensus_resolutions(first, second)
        self.assertTrue(resolutions)
        self.assertTrue(all(item["status"] == "not_applied" for item in resolutions))
        self.assertTrue(
            all(
                item["basis"] == "overlapping_or_nested_family_component"
                for item in resolutions
            )
        )

    def test_duplicate_candidate_disposition_is_invalid(self):
        first = _plan(
            [
                _family("af1", ["c1", "c2"]),
                _family("af2", ["c2", "c1"]),
            ]
        )
        with self.assertRaisesRegex(
            STAGE.AcceptedAssemblyError, "candidate IDs"
        ):
            _validate(
                first,
                candidate_bank={
                    "protocol_version": STAGE.CANDIDATE_BANK_PROTOCOL,
                    "shot_id": SHOT_ID,
                    "candidates": [
                        {
                            "candidate_id": _candidate_id(["c1", "c2"]),
                            "anchor_cluster_ids": ["c1", "c2"],
                            "context_anchor_cluster_ids": [],
                        }
                    ],
                },
            )

    def test_consensus_assembly_is_deterministic_and_preserves_firewall(self):
        baseline = _baseline()
        first = _plan([_family("af1", ["c2", "c1"])])
        second = _plan([_family("af8", ["c1", "c2"])])
        _validate(first, baseline)
        _validate(second, baseline)
        resolutions = STAGE.select_consensus_resolutions(first, second)
        self.assertEqual(resolutions[0]["status"], "applied")
        final, audit = STAGE.assemble_consensus(
            baseline=baseline,
            first_plan=first,
            second_plan=second,
            resolutions=resolutions,
            candidate_bank=_candidate_bank_from_plan(first),
            shot_id=SHOT_ID,
            valid_frame_ids=FRAME_IDS,
            base_protocol=BASE_PROTOCOL,
        )
        merged = final["clusters"][0]
        self.assertEqual(merged["canonical_name"], "fixed display")
        self.assertEqual(merged["final_entity"]["entity_confidence"], 0.83)
        self.assertEqual(merged["final_entity"]["evidence_frame_ids"], [10, 20])
        attributes = {item["name"]: item["value"] for item in merged["final_entity"]["attributes"]}
        self.assertEqual(attributes["assembly_kind"], "fixed_coordinated_array")
        self.assertEqual(
            attributes["graph_components"], "first component; second component"
        )
        self.assertEqual(merged["anonymous_proposal_ids"], ["p0001", "p0002"])
        self.assertEqual(final["clusters"][1:], baseline["clusters"][2:])
        self.assertEqual(audit["changed_outside_family_cluster_ids"], [])
        self.assertFalse(audit["model_naming_authority"])
        self.assertFalse(audit["detector_boxes_visible_to_planners"])

        reversed_first = copy.deepcopy(first)
        reversed_first["families"][0]["anchor_cluster_ids"].reverse()
        reversed_first["families"][0]["content_units"].reverse()
        _validate(reversed_first, baseline)
        reversed_resolutions = STAGE.select_consensus_resolutions(
            reversed_first, second
        )
        reversed_final, _ = STAGE.assemble_consensus(
            baseline=baseline,
            first_plan=reversed_first,
            second_plan=second,
            resolutions=reversed_resolutions,
            candidate_bank=_candidate_bank_from_plan(first),
            shot_id=SHOT_ID,
            valid_frame_ids=FRAME_IDS,
            base_protocol=BASE_PROTOCOL,
        )
        self.assertEqual(final, reversed_final)

    def test_consensus_assembly_preserves_repeated_component_counts(self):
        baseline = _baseline()
        for cluster in baseline["clusters"]:
            if cluster["cluster_id"] in {"c1", "c2"}:
                cluster["final_entity"]["name"] = "repeated component"
        first = _plan([_family("af1", ["c1", "c2"])])
        second = _plan([_family("af2", ["c2", "c1"])])
        _validate(first, baseline)
        _validate(second, baseline)
        resolutions = STAGE.select_consensus_resolutions(first, second)
        final, _ = STAGE.assemble_consensus(
            baseline=baseline,
            first_plan=first,
            second_plan=second,
            resolutions=resolutions,
            candidate_bank=_candidate_bank_from_plan(first),
            shot_id=SHOT_ID,
            valid_frame_ids=FRAME_IDS,
            base_protocol=BASE_PROTOCOL,
        )
        attributes = {
            item["name"]: item["value"]
            for item in final["clusters"][0]["final_entity"]["attributes"]
        }
        self.assertEqual(
            attributes["graph_components"], "2 × repeated component"
        )

    def test_deterministic_name_uses_safe_shared_core_or_fixed_fallback(self):
        baseline = _baseline()
        baseline["clusters"][0]["final_entity"]["name"] = "upper pinned sheet"
        baseline["clusters"][1]["final_entity"]["name"] = "lower pinned sheet"
        self.assertEqual(
            STAGE.deterministic_merged_name(
                baseline["clusters"][:2], "fixed_coordinated_array"
            ),
            "pinned sheet group",
        )
        baseline["clusters"][0]["final_entity"]["name"] = "first object"
        baseline["clusters"][1]["final_entity"]["name"] = "second object"
        self.assertEqual(
            STAGE.deterministic_merged_name(
                baseline["clusters"][:2], "fixed_coordinated_array"
            ),
            "fixed display",
        )

    def test_modified_resolution_is_rejected(self):
        plan = _plan([_family("af1", ["c1", "c2"])])
        _validate(plan)
        resolutions = STAGE.select_consensus_resolutions(plan, copy.deepcopy(plan))
        resolutions[0]["basis"] = "tampered"
        with self.assertRaisesRegex(STAGE.AcceptedAssemblyError, "modified"):
            STAGE.assemble_consensus(
                baseline=_baseline(),
                first_plan=plan,
                second_plan=copy.deepcopy(plan),
                resolutions=resolutions,
                candidate_bank=_candidate_bank_from_plan(plan),
                shot_id=SHOT_ID,
                valid_frame_ids=FRAME_IDS,
                base_protocol=BASE_PROTOCOL,
            )

    def test_rejected_anchor_and_tampered_view_are_invalid(self):
        rejected = _plan([_family("af1", ["c1", "c_reject"])])
        with self.assertRaisesRegex(STAGE.AcceptedAssemblyError, "non-accepted"):
            _validate(rejected)

        baseline = _baseline()
        view = STAGE.planner_baseline_view(
            baseline,
            candidate_bank={
                "protocol_version": STAGE.CANDIDATE_BANK_PROTOCOL,
                "shot_id": SHOT_ID,
                "candidates": [],
            },
            shot_id=SHOT_ID,
            base_protocol=BASE_PROTOCOL,
        )
        view["accepted_clusters"][0]["canonical_name"] = "tampered"
        with self.assertRaisesRegex(STAGE.AcceptedAssemblyError, "view was modified"):
            STAGE.validate_plan(
                _plan([]),
                shot_id=SHOT_ID,
                baseline=baseline,
                accepted_view=view,
                valid_frame_ids=FRAME_IDS,
                base_protocol=BASE_PROTOCOL,
            )


if __name__ == "__main__":
    unittest.main()
