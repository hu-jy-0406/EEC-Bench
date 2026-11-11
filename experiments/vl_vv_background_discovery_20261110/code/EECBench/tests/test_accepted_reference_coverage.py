"""Deterministic reference review coverage without invented positive evidence."""

import copy
import json
from pathlib import Path
import unittest

import jsonschema

from test_accepted_compact_assembly_stage import (
    STAGE, SHOT_ID, FRAME_IDS, BASE_PROTOCOL, _baseline, _family, _plan,
    _validate, _candidate_bank_from_plan, _reference_review,
)


def uncertain_frame(family, frame):
    for witness in family["cohesion_witnesses"]:
        for obs in witness["reference_review"]["observations"]:
            if obs["frame_id"] == frame:
                obs.update(boundary_status="uncertain", bbox_xyxy_normalized=None,
                           boundary_evidence="No reference boundary can be established in this frame.",
                           limitation="not_visible in this original frame")
        for relation in witness["reference_review"]["member_relations"]:
            if relation["frame_id"] == frame:
                relation.update(outcome="uncertain", member_locus_bbox_xyxy_normalized=None,
                                reference_locus_bbox_xyxy_normalized=None, limitation="reference not_visible")


class ReferenceCoverageTests(unittest.TestCase):
    def setUp(self):
        self.baseline = _baseline()
        self.first = _plan([_family("af1", ["c1", "c2"])])
        self.second = copy.deepcopy(self.first)

    def resolution(self):
        _validate(self.first, self.baseline)
        _validate(self.second, self.baseline, _candidate_bank_from_plan(self.first))
        return STAGE.select_consensus_resolutions(self.first, self.second)[0]

    def external_reference(self):
        for plan in (self.first, self.second):
            witness = plan["families"][0]["cohesion_witnesses"][0]
            witness["kind"] = "stable_complementary_same_role_array_about_external_reference"
            witness["reference_review"] = _reference_review(
                ["c1", "c2"], witness["kind"], reference_id="c3", external=True, frame_ids=FRAME_IDS)

    def test_different_positive_citation_subsets_do_not_remove_reviewed_common_frames(self):
        self.second["families"][0]["cohesion_witnesses"][0]["frame_ids"] = [10, 30]
        result = self.resolution()
        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["anchor_scope_audit"]["jointly_localized_frame_ids"], FRAME_IDS)
        self.assertEqual(result["reference_coverage_policy"], STAGE.REFERENCE_COVERAGE_POLICY)

    def test_extra_not_visible_frame_is_valid_nonpositive_without_forced_box(self):
        for plan in (self.first, self.second):
            uncertain_frame(plan["families"][0], 30)
        before = copy.deepcopy((self.first, self.second))
        schema = json.loads((Path(__file__).resolve().parents[1] / "schemas/codex_accepted_compact_assembly_plan_v0.5.schema.json").read_text())
        jsonschema.validate(self.first, schema)
        result = self.resolution()
        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["anchor_scope_audit"]["jointly_localized_frame_ids"], [10, 20])
        self.assertEqual((self.first, self.second), before)

    def test_full_coverage_with_only_one_joint_localized_reference_is_insufficient(self):
        uncertain_frame(self.first["families"][0], 30)
        uncertain_frame(self.second["families"][0], 20)
        self.second["families"][0]["cohesion_witnesses"][0]["frame_ids"] = [10, 30]
        result = self.resolution()
        self.assertEqual(result["status"], "not_applied")
        self.assertEqual(result["basis"], "insufficient_common_reference_frames")
        self.assertEqual(result["anchor_scope_audit"]["common_reference_frame_ids"], [10])

    def test_legacy_selective_observations_fail_new_coverage_but_are_not_box_conflict(self):
        for plan, frames in ((self.first, {10, 20}), (self.second, {10, 30})):
            witness = plan["families"][0]["cohesion_witnesses"][0]
            witness["frame_ids"] = sorted(frames)
            ref = witness["reference_review"]
            for key in ("observations", "member_relations"):
                ref[key] = [row for row in ref[key] if row["frame_id"] in frames]
            with self.assertRaisesRegex(STAGE.AcceptedAssemblyError, "all candidate common visible frames"):
                _validate(plan, self.baseline)
        diagnostic = STAGE._joint_scope_audit(self.first["families"][0], self.second["families"][0])
        self.assertEqual(diagnostic["basis"], "insufficient_common_reference_frames")

    def test_missing_duplicate_or_wrong_reference_frame_is_fatal(self):
        for mutation in ("missing", "duplicate", "wrong"):
            plan = copy.deepcopy(self.first)
            observations = plan["families"][0]["cohesion_witnesses"][0]["reference_review"]["observations"]
            if mutation == "missing":
                observations.pop()
            elif mutation == "duplicate":
                observations.append(copy.deepcopy(observations[0]))
            else:
                observations[-1]["frame_id"] = 999
            with self.assertRaises(STAGE.AcceptedAssemblyError):
                _validate(plan, self.baseline)

    def test_missing_or_duplicate_relation_on_uncited_frame_is_fatal(self):
        for duplicate in (False, True):
            plan = copy.deepcopy(self.first)
            relations = plan["families"][0]["cohesion_witnesses"][0]["reference_review"]["member_relations"]
            if duplicate:
                relations.append(copy.deepcopy(relations[-1]))
            else:
                relations.pop()
            with self.assertRaises(STAGE.AcceptedAssemblyError):
                _validate(plan, self.baseline)

    def test_unknown_frames_do_not_count_as_persistent_localization_conflicts(self):
        box = [0.1, 0.1, 0.2, 0.2]
        self.assertFalse(STAGE._persistent_localization_conflict({10: box, 20: None}, {10: box, 20: None}))
        self.assertFalse(STAGE._persistent_localization_conflict({10: box, 20: box}, {10: box, 30: box}))

    def test_real_multi_frame_reference_conflict_keeps_distinct_diagnostic(self):
        self.external_reference()
        ref = self.second["families"][0]["cohesion_witnesses"][0]["reference_review"]
        for obs in ref["observations"]:
            obs["bbox_xyxy_normalized"] = [0.7, 0.7, 0.8, 0.8]
        for relation in ref["member_relations"]:
            relation["reference_locus_bbox_xyxy_normalized"] = [0.72, 0.72, 0.75, 0.75]
        result = self.resolution()
        self.assertEqual(result["basis"], "same_reference_localization_conflict")
        self.assertEqual(result["anchor_scope_audit"]["common_reference_frame_ids"], FRAME_IDS)

    def test_uncited_positive_reference_requires_accepted_reference_visible(self):
        self.external_reference()
        fixture = next(c for c in self.baseline["clusters"] if c["cluster_id"] == "c3")
        next(p for p in fixture["frame_presence"] if p["frame_id"] == 30)["status"] = "uncertain"
        with self.assertRaisesRegex(STAGE.AcceptedAssemblyError, "accepted anchor visible"):
            _validate(self.first, self.baseline)
        for plan in (self.first, self.second):
            uncertain_frame(plan["families"][0], 30)
        self.assertEqual(self.resolution()["status"], "applied")

    def test_uncited_explicit_or_geometric_contradiction_still_blocks(self):
        original = copy.deepcopy(self.second)
        for mutation in ("arbitrary", "contradicted", "member_outside", "reference_outside", "no_touch"):
            self.second = copy.deepcopy(original)
            ref = self.second["families"][0]["cohesion_witnesses"][0]["reference_review"]
            observation = next(o for o in ref["observations"] if o["frame_id"] == 30)
            relation = next(r for r in ref["member_relations"] if r["frame_id"] == 30)
            if mutation == "arbitrary":
                observation["boundary_status"] = "arbitrary_enclosing_region"
            elif mutation == "contradicted":
                relation["outcome"] = "contradicted"
            elif mutation == "member_outside":
                relation["member_locus_bbox_xyxy_normalized"] = [0.4, 0.4, 0.5, 0.5]
            elif mutation == "reference_outside":
                relation["reference_locus_bbox_xyxy_normalized"] = [0.4, 0.4, 0.5, 0.5]
            else:
                relation["reference_locus_bbox_xyxy_normalized"] = [0.18, 0.18, 0.19, 0.19]
            self.assertEqual(self.resolution()["status"], "not_applied", mutation)

    def test_uncertain_cited_frame_does_not_supply_the_two_positive_witness_frames(self):
        uncertain_frame(self.second["families"][0], 20)
        self.assertEqual(self.resolution()["status"], "not_applied")

    def test_policy_is_recorded_in_payload_prompt_and_firewall_audit(self):
        bank = _candidate_bank_from_plan(self.first)
        view = STAGE.planner_baseline_view(self.baseline, candidate_bank=bank, shot_id=SHOT_ID, base_protocol=BASE_PROTOCOL)
        self.assertEqual(view["reference_coverage_policy"], STAGE.REFERENCE_COVERAGE_POLICY)
        prompt = STAGE.build_prompt(shot_id=SHOT_ID, shot_manifest={"reference_frames": [
            {"frame_id": f, "path": f"/tmp/synthetic_frame_{f}.jpg"} for f in FRAME_IDS]},
            accepted_view=view, policy_text="General original-pixel scope rules.")
        self.assertIn(STAGE.REFERENCE_COVERAGE_POLICY, prompt)
        self.assertIn("not retry triggers", prompt)
        _, audit = STAGE.assemble_consensus(baseline=self.baseline, first_plan=self.first, second_plan=self.second,
                                           candidate_bank=bank, shot_id=SHOT_ID, valid_frame_ids=FRAME_IDS,
                                           resolutions=STAGE.select_consensus_resolutions(self.first, self.second),
                                           base_protocol=BASE_PROTOCOL)
        self.assertEqual(audit["reference_coverage_policy"], STAGE.REFERENCE_COVERAGE_POLICY)


if __name__ == "__main__":
    unittest.main()
