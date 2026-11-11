"""Zero supported anchors is a coverage no-op, never a recovered inventory."""

import copy
import importlib.util
import json
from pathlib import Path
import unittest

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "zero_anchor_fixtures", Path(__file__).with_name("test_granularity_family_ablation.py"))
F = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(F)
import granularity_family_stage as M  # noqa: E402


def fixture(*, withdraw_members=True):
    plan, baseline, anonymous, _, _ = F._fixture()
    plan["families"] = []
    plan["excluded_group_alternatives"] = [{
        "cluster_id": "c_group", "candidate_member_anchor_cluster_ids": [],
        "independent_context_anchor_cluster_ids": [],
        "reason_code": "insufficient_supported_member_anchors",
        "reason": "The visual group can be localized, but no supported eligible member is available.",
    }]
    if withdraw_members:
        for cluster in baseline["clusters"]:
            if cluster["cluster_id"].startswith("c_member_"):
                cluster.update(decision="abstain", identity_status="ambiguous", final_entity=None)
    return plan, baseline, anonymous


def validate(plan, baseline, anonymous):
    M.validate_family_plan(plan, shot_id=F.SHOT_ID, baseline=baseline,
                          anonymous_view=anonymous, valid_frame_ids=F.FRAME_IDS,
                          base_protocol=F.ENSEMBLE.PROTOCOL_VERSION)


def assemble(first, second, baseline, anonymous, resolutions=None):
    resolutions = M.select_consensus_resolutions(first, second) if resolutions is None else resolutions
    return M.assemble_consensus(
        baseline=baseline, anonymous_view=anonymous, first_plan=first, second_plan=second,
        consensus_resolutions=resolutions, shot_id=F.SHOT_ID, valid_frame_ids=F.FRAME_IDS,
        base_protocol=F.ENSEMBLE.PROTOCOL_VERSION)


class ZeroSupportedMemberAnchorTests(unittest.TestCase):
    def test_resolvable_group_zero_eligible_members_is_schema_valid_noop(self):
        plan, baseline, anonymous = fixture()
        before = copy.deepcopy((plan, baseline, anonymous))
        schema = json.loads((ROOT / "schemas/codex_granularity_family_plan_v0.3.schema.json").read_text())
        jsonschema.validate(plan, schema)
        validate(plan, baseline, anonymous)
        final, audit, application, resolutions = assemble(plan, copy.deepcopy(plan), baseline, anonymous)
        self.assertEqual(final, baseline)
        self.assertEqual(application["families"], [])
        self.assertEqual(resolutions, [])
        self.assertEqual(audit["applied_family_ids"], [])
        coverage = audit["empty_supported_anchor_exclusions"]
        self.assertEqual(coverage["policy"], M.EMPTY_SUPPORTED_ANCHOR_POLICY)
        self.assertTrue(coverage["unresolved_coverage_risk"])
        self.assertEqual([x["planner_index"] for x in coverage["records"]], [1, 2])
        self.assertTrue(all(not x["physical_scope_absence_proven"] for x in coverage["records"]))
        self.assertFalse(coverage["nonaccepted_anchors_recovered"])
        self.assertEqual((plan, baseline, anonymous), before)

    def test_zero_mapping_does_not_use_global_accepted_count_name_or_boxes_as_oracle(self):
        plan, baseline, anonymous = fixture(withdraw_members=False)
        # Globally accepted anchors do not prove visual membership in this group.
        for row in baseline["clusters"]:
            row["canonical_name"] = "the same arbitrary label"
        for proposal in anonymous["proposals"]:
            for frame in proposal["frame_presence"]:
                frame["bbox_xyxy_normalized"] = [0.0, 0.0, 1.0, 1.0]
        final, audit, _, _ = assemble(plan, plan, baseline, anonymous)
        self.assertEqual(final, baseline)
        self.assertTrue(audit["empty_supported_anchor_exclusions"]["unresolved_coverage_risk"])

    def test_insufficient_reason_keeps_nonempty_mapping_legal(self):
        for members in (["c_member_1"], ["c_member_1", "c_member_2", "c_member_3"]):
            plan, baseline, anonymous = fixture(withdraw_members=False)
            plan["excluded_group_alternatives"][0]["candidate_member_anchor_cluster_ids"] = members
            validate(plan, baseline, anonymous)
            final, audit, _, _ = assemble(plan, plan, baseline, anonymous)
            self.assertEqual(final, baseline)
            self.assertFalse(audit["empty_supported_anchor_exclusions"]["unresolved_coverage_risk"])

    def test_other_empty_reason_guards_and_unresolvable_exceptions_remain(self):
        for reason in M.GROUP_ALTERNATIVE_EXCLUSION_REASON_CODES:
            plan, baseline, anonymous = fixture()
            plan["excluded_group_alternatives"][0]["reason_code"] = reason
            if reason in M.EMPTY_CANDIDATE_ANCHOR_REASON_CODES:
                validate(plan, baseline, anonymous)
            else:
                with self.assertRaisesRegex(M.FamilyPlanError, "may be empty only"):
                    validate(plan, baseline, anonymous)

    def test_exclusion_cannot_also_claim_same_group_in_family(self):
        plan, baseline, anonymous, _, _ = F._fixture()
        exclusion, _, _ = fixture(withdraw_members=False)
        plan["excluded_group_alternatives"] = exclusion["excluded_group_alternatives"]
        with self.assertRaisesRegex(M.FamilyPlanError, "both a family and an exclusion"):
            validate(plan, baseline, anonymous)

    def test_context_subset_nonaccepted_member_and_mandatory_coverage_guards(self):
        for kind in ("context", "nonaccepted", "missing_exclusion", "duplicate_exclusion"):
            plan, baseline, anonymous = fixture()
            row = plan["excluded_group_alternatives"][0]
            if kind == "context":
                row["independent_context_anchor_cluster_ids"] = ["c_outside"]
            elif kind == "nonaccepted":
                row["candidate_member_anchor_cluster_ids"] = ["c_member_1"]
            elif kind == "missing_exclusion":
                plan["excluded_group_alternatives"] = []
            else:
                plan["excluded_group_alternatives"].append(copy.deepcopy(row))
            with self.assertRaises(M.FamilyPlanError):
                validate(plan, baseline, anonymous)

    def test_one_planner_zero_report_remains_in_consensus_coverage_audit(self):
        first, baseline, anonymous = fixture(withdraw_members=False)
        second = copy.deepcopy(first)
        second["excluded_group_alternatives"][0]["candidate_member_anchor_cluster_ids"] = ["c_member_1"]
        final, audit, _, _ = assemble(second, first, baseline, anonymous)
        self.assertEqual(final, baseline)
        coverage = audit["empty_supported_anchor_exclusions"]
        self.assertTrue(coverage["unresolved_coverage_risk"])
        self.assertEqual([x["planner_index"] for x in coverage["records"]], [2])

    def test_zero_exclusion_cannot_be_upgraded_by_forged_resolution(self):
        plan, baseline, anonymous = fixture()
        with self.assertRaisesRegex(M.FamilyPlanError, "resolution payload was modified"):
            assemble(plan, plan, baseline, anonymous,
                     resolutions=[{"family_id": "invented", "status": "applied", "selected_kind": "group"}])

    def test_unrelated_valid_family_still_applies_with_zero_exclusion(self):
        plan, baseline, anonymous, _, _ = F._fixture()
        baseline["clusters"].append(F._cluster("extra_group", ["extra_proposal"], "unresolved membership", decision="reject"))
        anonymous["proposals"].append({"anonymous_proposal_id": "extra_proposal", **F._proposal_payload("unresolved membership")})
        plan["reviewed_group_alternative_cluster_ids"].append("extra_group")
        plan["excluded_group_alternatives"].append({
            "cluster_id": "extra_group", "candidate_member_anchor_cluster_ids": [],
            "independent_context_anchor_cluster_ids": [], "reason_code": "insufficient_supported_member_anchors",
            "reason": "No supported eligible member for this independent group claim.",
        })
        final, audit, _, _ = assemble(plan, copy.deepcopy(plan), baseline, anonymous)
        self.assertTrue(audit["applied_family_ids"])
        self.assertEqual(next(x for x in final["clusters"] if x["cluster_id"] == "extra_group"), baseline["clusters"][-1])
        self.assertTrue(audit["empty_supported_anchor_exclusions"]["unresolved_coverage_risk"])


if __name__ == "__main__":
    unittest.main()
