import copy
import json
import unittest
from pathlib import Path
import jsonschema
from test_accepted_compact_assembly_stage import (
    STAGE, SHOT_ID, BASE_PROTOCOL, FRAME_IDS,
    _baseline, _family, _plan, _candidate_bank_from_plan,
)


class PassiveCollectionScopeTests(unittest.TestCase):
    def setUp(self):
        self.baseline = _baseline()
        family = _family("af1", ["c1", "c2"], assembly_kind="passive_homogeneous_collection")
        family["collection_scope_review"] = {
            "fixture_anchor_cluster_id": "c3", "content_category": "repeated stored objects",
            "complete_fixture_content_scope": True, "passive_unhandled_content": True,
            "fixture_excluded": True, "heterogeneous_neighbors_excluded": True,
            "independently_framed_subjects_excluded": True,
            "evidence": [{"frame_id": frame, "description": "The excluded fixture bounds the complete passive content category."} for frame in [10, 20]],
            "description": "Complete category contents across internal fixture compartments.",
        }
        self.plan = _plan([family])

    def validate(self):
        bank = _candidate_bank_from_plan(self.plan)
        view = STAGE.planner_baseline_view(
            self.baseline, candidate_bank=bank, shot_id=SHOT_ID, base_protocol=BASE_PROTOCOL,
        )
        STAGE.validate_plan(
            self.plan, shot_id=SHOT_ID, baseline=self.baseline,
            accepted_view=view, valid_frame_ids=FRAME_IDS, base_protocol=BASE_PROTOCOL,
        )

    def test_complete_collection_validates_current_schema(self):
        self.validate()
        schema = Path(__file__).resolve().parents[1] / "schemas/codex_accepted_compact_assembly_plan_v0.5.schema.json"
        jsonschema.validate(self.plan, json.loads(schema.read_text()))
        self.assertTrue(STAGE._family_is_clear(self.plan["families"][0]))

    def test_fixture_cannot_be_member_or_unknown(self):
        for fixture in ["c1", "missing"]:
            self.plan["families"][0]["collection_scope_review"]["fixture_anchor_cluster_id"] = fixture
            with self.assertRaises(STAGE.AcceptedAssemblyError):
                self.validate()

    def test_scope_requires_two_joint_visible_fixture_frames(self):
        self.baseline["clusters"][2]["frame_presence"][1]["status"] = "occluded"
        with self.assertRaises(STAGE.AcceptedAssemblyError):
            self.validate()

    def test_all_scope_checks_required(self):
        original = copy.deepcopy(self.plan)
        for key in sorted(STAGE.COLLECTION_SCOPE_CHECKS):
            self.plan = copy.deepcopy(original)
            self.plan["families"][0]["collection_scope_review"][key] = False
            with self.assertRaises(STAGE.AcceptedAssemblyError):
                self.validate()

    def test_collection_requires_structured_review(self):
        self.plan["families"][0]["collection_scope_review"] = None
        with self.assertRaises(STAGE.AcceptedAssemblyError):
            self.validate()

    def test_handled_content_remains_independent(self):
        family = self.plan["families"][0]
        check = next(item for item in family["pairwise_independence_reviews"][0]["checks"]
                     if item["kind"] == "separate_handling_or_use")
        check.update(outcome="observed", evidence=[{"frame_id": 10, "description": "One unit is separately handled."}])
        self.validate()
        self.assertFalse(STAGE._family_is_clear(family))

    def test_existing_kinds_require_null_collection_review(self):
        family = self.plan["families"][0]
        family["assembly_kind"] = "fixed_coordinated_array"
        family["cohesion_witnesses"][0]["kind"] = "common_fixed_mounting_or_array"
        with self.assertRaises(STAGE.AcceptedAssemblyError):
            self.validate()

    def test_two_judges_must_agree_on_fixture_identity(self):
        self.validate()
        second = copy.deepcopy(self.plan)
        second["families"][0]["collection_scope_review"]["fixture_anchor_cluster_id"] = "different_fixture"
        resolutions = STAGE.select_consensus_resolutions(self.plan, second)
        self.assertEqual(resolutions[0]["status"], "not_applied")
        self.assertEqual(resolutions[0]["basis"], "collection_fixture_disagreement")
