"""Adversarial frozen-anchor/reference checks for final coarsening authority."""

import copy
import json
import unittest
from pathlib import Path

import jsonschema

from test_accepted_compact_assembly_stage import (
    STAGE,
    SHOT_ID,
    FRAME_IDS,
    BASE_PROTOCOL,
    _baseline,
    _family,
    _plan,
    _validate,
    _candidate_bank_from_plan,
    _reference_review,
)
from test_granularity_family_ablation import _spatial_fixture, FAMILY


class AnchorScopeTests(unittest.TestCase):
    def setUp(self):
        self.baseline = _baseline()
        self.first = _plan([_family("af1", ["c1", "c2"])])
        self.second = copy.deepcopy(self.first)

    def status(self, first=None, second=None):
        first, second = first or self.first, second or self.second
        _validate(first, self.baseline)
        _validate(second, self.baseline, _candidate_bank_from_plan(first))
        return STAGE.select_consensus_resolutions(first, second)[0]

    def assemble(self, first, second, **kwargs):
        return STAGE.assemble_consensus(
            baseline=self.baseline,
            first_plan=first,
            second_plan=second,
            candidate_bank=_candidate_bank_from_plan(first),
            shot_id=SHOT_ID,
            valid_frame_ids=FRAME_IDS,
            base_protocol=BASE_PROTOCOL,
            **kwargs,
        )

    def test_exact_wrong_group_does_not_poison_independently_reviewed_anchors(self):
        frames = [10, 20, 30]
        plan, baseline, view, _, _, _ = _spatial_fixture(
            {f: [0.05, 0.05, 0.30, 0.30] for f in frames},
            {f: [0.70, 0.65, 0.88, 0.90] for f in frames},
        )
        vetoes = FAMILY.family_stage.collect_spatial_vetoes(
            (plan,), baseline=baseline, anonymous_view=view
        )
        self.assertTrue(vetoes)
        self.assertTrue(
            all(
                v["kind"] == "group_witness_invalid" and not v["blocked_anchor_pairs"]
                for v in vetoes
            )
        )
        # Use matching IDs: otherwise this would merely test unrelated candidates.
        for veto in vetoes:
            veto["member_anchor_cluster_id"] = "c1"
            veto["anchor_cluster_ids"] = ["c1", "c2"]
        resolutions = STAGE.select_consensus_resolutions(
            self.first, self.second, spatial_vetoes=vetoes
        )
        self.assertEqual(resolutions[0]["status"], "applied")
        final, audit = self.assemble(
            self.first, self.second, resolutions=resolutions, spatial_vetoes=vetoes
        )
        self.assertEqual(audit["applied_anchor_sets"], [["c1", "c2"]])
        self.assertEqual(final["clusters"][1:], self.baseline["clusters"][2:])
        self.assertEqual(
            final["clusters"][0]["anonymous_proposal_ids"], ["p0001", "p0002"]
        )

    def test_uncertain_partial_and_retarget_are_valid_nonmerges(self):
        for key, value in (
            ("correspondence", "uncertain"),
            ("correspondence", "different_content"),
            ("coverage", "partial"),
            ("coverage", "unresolved"),
        ):
            second = copy.deepcopy(self.second)
            second["families"][0]["content_units"][0]["anchor_scope_review"][
                "observations"
            ][0][key] = value
            result = self.status(second=second)
            self.assertEqual(result["status"], "not_applied")
            self.assertEqual(result["basis"], "anchor_or_reference_scope_not_complete")
            self.assemble(self.first, second, resolutions=[result])

    def test_missing_duplicate_and_wrong_frame_fail_contract(self):
        for change in ("missing", "duplicate", "wrong"):
            plan = copy.deepcopy(self.first)
            observations = plan["families"][0]["content_units"][0][
                "anchor_scope_review"
            ]["observations"]
            if change == "missing":
                observations.pop()
            elif change == "duplicate":
                observations.append(copy.deepcopy(observations[0]))
            else:
                observations[-1]["frame_id"] = 99
            with self.assertRaises(STAGE.AcceptedAssemblyError):
                _validate(plan)

    def test_invalid_or_missing_complete_bbox_fails_contract(self):
        for box in (
            None,
            [0.3, 0.1, 0.2, 0.2],
            [False, 0.1, 0.2, 0.2],
            [0, 0, float("nan"), 1],
        ):
            plan = copy.deepcopy(self.first)
            plan["families"][0]["content_units"][0]["anchor_scope_review"][
                "observations"
            ][0]["bbox_xyxy_normalized"] = box
            with self.assertRaises(STAGE.AcceptedAssemblyError):
                _validate(plan)

    def test_two_judges_retargeting_same_id_to_different_locations_blocks(self):
        family = self.second["families"][0]
        for unit in family["content_units"]:
            for obs in unit["anchor_scope_review"]["observations"]:
                obs["bbox_xyxy_normalized"] = [0.7, 0.7, 0.8, 0.8]
        for witness in family["cohesion_witnesses"]:
            for obs in witness["reference_review"]["observations"]:
                obs["bbox_xyxy_normalized"] = [0.7, 0.7, 0.8, 0.8]
            for rel in witness["reference_review"]["member_relations"]:
                rel["member_locus_bbox_xyxy_normalized"] = [0.72, 0.72, 0.75, 0.75]
                rel["reference_locus_bbox_xyxy_normalized"] = [0.72, 0.72, 0.75, 0.75]
        self.assertEqual(self.status()["basis"], "same_anchor_localization_conflict")

    def test_far_member_cannot_be_attached_by_free_text_or_large_intrinsic_box(self):
        for large_reference in (False, True):
            family = self.second["families"][0]
            for obs in family["content_units"][1]["anchor_scope_review"][
                "observations"
            ]:
                obs["bbox_xyxy_normalized"] = [0.7, 0.7, 0.8, 0.8]
            ref = family["cohesion_witnesses"][0]["reference_review"]
            ref["reference_type"] = "visible_intrinsic_structure"
            for obs in ref["observations"]:
                obs["bbox_xyxy_normalized"] = (
                    [0.1, 0.1, 0.8, 0.8] if large_reference else [0.1, 0.1, 0.2, 0.2]
                )
            for rel in ref["member_relations"]:
                if rel["anchor_cluster_id"] == "c2":
                    rel["member_locus_bbox_xyxy_normalized"] = [0.72, 0.72, 0.75, 0.75]
            self.assertEqual(self.status()["status"], "not_applied")

    def test_invalid_superset_does_not_block_valid_subset(self):
        for failure in ("partial", "far_member", "contradicted_relation"):
            first = _plan(
                [_family("af1", ["c1", "c2"]), _family("af2", ["c1", "c2", "c3"])]
            )
            bad = first["families"][1]
            if failure == "partial":
                bad["content_units"][2]["anchor_scope_review"]["observations"][0][
                    "coverage"
                ] = "partial"
            elif failure == "far_member":
                for o in bad["content_units"][2]["anchor_scope_review"]["observations"]:
                    o["bbox_xyxy_normalized"] = [0.7, 0.7, 0.8, 0.8]
            else:
                bad["cohesion_witnesses"][1]["reference_review"]["member_relations"][1][
                    "outcome"
                ] = "contradicted"
            second = copy.deepcopy(first)
            _validate(first)
            _validate(second)
            resolutions = STAGE.select_consensus_resolutions(first, second)
            by_anchors = {tuple(r["anchor_cluster_ids"]): r for r in resolutions}
            self.assertEqual(by_anchors[("c1", "c2")]["status"], "applied")
            self.assertEqual(by_anchors[("c1", "c2", "c3")]["status"], "not_applied")
            _, audit = self.assemble(first, second, resolutions=resolutions)
            self.assertEqual(audit["applied_anchor_sets"], [["c1", "c2"]])

    def test_neighboring_nonoverlapping_parts_can_have_direct_joint_cohesion(self):
        first = _plan(
            [_family("af1", ["c1", "c2"], assembly_kind="integrated_part_whole")]
        )
        family = first["families"][0]
        for obs in family["content_units"][1]["anchor_scope_review"]["observations"]:
            obs["bbox_xyxy_normalized"] = [0.2, 0.1, 0.3, 0.2]
        for rel in family["cohesion_witnesses"][0]["reference_review"][
            "member_relations"
        ]:
            rel["reference_locus_bbox_xyxy_normalized"] = [0.18, 0.12, 0.2, 0.15]
            rel["member_locus_bbox_xyxy_normalized"] = (
                [0.18, 0.12, 0.2, 0.15]
                if rel["anchor_cluster_id"] == "c1"
                else [0.2, 0.12, 0.22, 0.15]
            )
        self.assertEqual(
            self.status(first=first, second=copy.deepcopy(first))["status"], "applied"
        )

    def test_disjoint_coordinated_array_uses_excluded_external_reference(self):
        family = self.first["families"][0]
        kind = "stable_complementary_same_role_array_about_external_reference"
        witness = family["cohesion_witnesses"][0]
        witness["kind"] = kind
        witness["reference_review"] = _reference_review(
            ["c1", "c2"], kind, reference_id="c3", external=True
        )
        for obs in family["content_units"][1]["anchor_scope_review"]["observations"]:
            obs["bbox_xyxy_normalized"] = [0.7, 0.1, 0.8, 0.2]
        for rel in witness["reference_review"]["member_relations"]:
            if rel["anchor_cluster_id"] == "c2":
                rel["member_locus_bbox_xyxy_normalized"] = [0.72, 0.12, 0.75, 0.15]
        second = copy.deepcopy(self.first)
        resolutions = [self.status(second=second)]
        final, _ = self.assemble(self.first, second, resolutions=resolutions)
        self.assertEqual(resolutions[0]["status"], "applied")
        self.assertEqual(final["clusters"][1], self.baseline["clusters"][2])

    def test_reference_loci_and_identity_are_exact(self):
        for change in (
            "unknown",
            "missing_relation",
            "wrong_anchor",
            "wrong_frame",
            "external_included",
        ):
            plan = copy.deepcopy(self.first)
            ref = plan["families"][0]["cohesion_witnesses"][0]["reference_review"]
            if change == "unknown":
                ref["reference_anchor_cluster_id"] = "new"
            elif change == "missing_relation":
                ref["member_relations"].pop()
            elif change == "wrong_anchor":
                ref["member_relations"][0]["anchor_cluster_id"] = "c6"
            elif change == "wrong_frame":
                ref["member_relations"][0]["frame_id"] = 30
            else:
                ref.update(
                    reference_anchor_cluster_id="c3", external_reference_excluded=False
                )
            with self.assertRaises(STAGE.AcceptedAssemblyError):
                _validate(plan)

    def test_uncertain_reference_or_relation_is_valid_nonmerge(self):
        for field, value in (
            ("boundary_status", "arbitrary_enclosing_region"),
            ("boundary_status", "uncertain"),
            ("outcome", "uncertain"),
        ):
            second = copy.deepcopy(self.second)
            ref = second["families"][0]["cohesion_witnesses"][0]["reference_review"]
            (ref["member_relations"] if field == "outcome" else ref["observations"])[0][
                field
            ] = value
            self.assertEqual(self.status(second=second)["status"], "not_applied")

    def test_forged_resolution_cannot_bypass_structured_scope(self):
        forged = STAGE.select_consensus_resolutions(self.first, self.second)
        self.second["families"][0]["content_units"][0]["anchor_scope_review"][
            "observations"
        ][0]["correspondence"] = "different_content"
        with self.assertRaises(STAGE.AcceptedAssemblyError):
            self.assemble(self.first, self.second, resolutions=forged)

    def test_all_anchors_and_cohesion_need_two_same_agreeing_frames(self):
        family = self.first["families"][0]
        witness = family["cohesion_witnesses"][0]
        kind = "stable_complementary_same_role_array_about_external_reference"
        witness.update(kind=kind, frame_ids=list(FRAME_IDS))
        witness["reference_review"] = _reference_review(
            ["c1", "c2"],
            kind,
            reference_id="c3",
            external=True,
            frame_ids=FRAME_IDS,
        )
        self.second = copy.deepcopy(self.first)
        for index, frame in ((0, 10), (1, 20)):
            second_family = self.second["families"][0]
            observations = second_family["content_units"][index]["anchor_scope_review"][
                "observations"
            ]
            next(o for o in observations if o["frame_id"] == frame)[
                "bbox_xyxy_normalized"
            ] = [0.7, 0.7, 0.8, 0.8]
            for relation in second_family["cohesion_witnesses"][0]["reference_review"][
                "member_relations"
            ]:
                if (
                    relation["frame_id"] == frame
                    and relation["anchor_cluster_id"] == f"c{index + 1}"
                ):
                    relation["member_locus_bbox_xyxy_normalized"] = [
                        0.72,
                        0.72,
                        0.75,
                        0.75,
                    ]
        self.assertEqual(
            self.status()["basis"], "insufficient_jointly_localized_cohesion_frames"
        )

    def test_both_judges_must_name_same_physical_reference(self):
        reference = self.second["families"][0]["cohesion_witnesses"][0][
            "reference_review"
        ]
        reference["reference_anchor_cluster_id"] = "c2"
        self.assertEqual(
            self.status()["basis"], "cohesion_reference_identity_disagreement"
        )

    def test_schema_accepts_honest_uncertainty(self):
        self.first["families"][0]["content_units"][0]["anchor_scope_review"][
            "observations"
        ][0].update(
            correspondence="uncertain",
            coverage="unresolved",
            bbox_xyxy_normalized=None,
        )
        schema = (
            Path(__file__).resolve().parents[1]
            / "schemas/codex_accepted_compact_assembly_plan_v0.5.schema.json"
        )
        jsonschema.validate(self.first, json.loads(schema.read_text()))
        _validate(self.first)
