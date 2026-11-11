"""Verifier projection retains physical claims without initial verdict priming."""
import copy
import json
import unittest
from test_prompt_unbound_pipelines import ENSEMBLE, ensemble_proposal


class CompactVerificationViewTests(unittest.TestCase):
    def fixture(self):
        proposal = ensemble_proposal("e1")
        proposal.update(anonymous_proposal_id="p1", source="PRIVATE_SOURCE",
                        local_id="PRIVATE_ID", attributes=[{"secret": "PRIVATE_ATTRIBUTE"}],
                        self_confidence=0.99, uncertainty_flags=["PRIVATE_FLAG"])
        proposal["coarse_locators"] = [
            {"frame_id": 10, "description": "bounded region", "source": "PRIVATE_LOCATOR"}
        ]
        for item in proposal["frame_presence"]:
            item["description"] = "PRIVATE_REPEAT"
        proposal["frame_presence"].append(
            {"frame_id": 20, "status": "uncertain", "bbox_xyxy_normalized": None,
             "description": "PRIVATE_UNCERTAIN_REASON"}
        )
        decisions = {"clusters": [{
            "cluster_id": "c1", "anonymous_proposal_ids": ["p1"],
            "canonical_name": "fixture", "aliases": ["PRIVATE_ALIAS"],
            "granularity": "whole_instance", "decision": "PRIVATE_DECISION",
            "decision_reason": "PRIVATE_REASON",
        }], "registry": "PRIVATE_REGISTRY"}
        anonymous = {"proposals": [proposal], "detector_panels": "PRIVATE_PANEL"}
        pairs = [{"cluster_id_a": "c1", "cluster_id_b": "c2", "frame_ids": [10]}]
        split = [{"cluster_id": "c1", "anonymous_proposal_ids": ["p1"]}]
        return decisions, anonymous, pairs, split

    def test_no_verdict_provenance_or_repeated_evidence(self):
        d, a, pairs, split = self.fixture()
        view = ENSEMBLE._verification_view(d, a, ["c1"], pairs, split)
        encoded = json.dumps(view)
        for marker in ("PRIVATE_", "initial_decision", "initial_reason", "self_confidence",
                       "uncertainty_flags", "evidence_frame_ids"):
            self.assertNotIn(marker, encoded)

    def test_preserves_proposal_identity_frames_statuses_and_boxes(self):
        d, a, pairs, split = self.fixture()
        p = ENSEMBLE._verification_view(d, a, ["c1"], pairs, split)["targets"][0]["proposals"][0]
        original = a["proposals"][0]
        self.assertEqual(p["anonymous_proposal_id"], "p1")
        self.assertEqual(p["proposed_name"], original["proposed_name"])
        self.assertEqual(p["granularity"], original["granularity"])
        self.assertEqual(p["frame_presence"], [
            {key: item[key] for key in ("frame_id", "status", "bbox_xyxy_normalized")}
            for item in original["frame_presence"]
        ])
        self.assertEqual(p["coarse_locators"], [{"frame_id": 10, "description": "bounded region"}])

    def test_no_aliasing_or_foreign_target_proposals(self):
        d, a, pairs, split = self.fixture()
        foreign = copy.deepcopy(a["proposals"][0])
        foreign.update(anonymous_proposal_id="p2", proposed_name="FOREIGN_PROPOSAL")
        a["proposals"].append(foreign)
        d["clusters"].append({**copy.deepcopy(d["clusters"][0]), "cluster_id": "c2",
                              "anonymous_proposal_ids": ["p2"]})
        frozen = copy.deepcopy((d, a, pairs, split))
        view = ENSEMBLE._verification_view(d, a, ["c1"], pairs, split)
        self.assertNotIn("FOREIGN_PROPOSAL", json.dumps(view))
        self.assertEqual(view["identity_challenge_pairs"], pairs)
        self.assertEqual(view["intra_cluster_divergent_footprint_challenges"], split)
        view["targets"][0]["proposals"][0]["frame_presence"][0]["bbox_xyxy_normalized"][0] = 0.99
        view["identity_challenge_pairs"][0]["frame_ids"].append(99)
        self.assertEqual((d, a, pairs, split), frozen)

    def test_missing_box_is_not_fabricated(self):
        d, a, pairs, split = self.fixture()
        del a["proposals"][0]["frame_presence"][0]["bbox_xyxy_normalized"]
        p = ENSEMBLE._verification_view(d, a, ["c1"], pairs, split)["targets"][0]["proposals"][0]
        self.assertNotIn("bbox_xyxy_normalized", p["frame_presence"][0])

    def test_prompt_requires_boundary_separation_and_limitations(self):
        d, a, pairs, split = self.fixture()
        prompt = ENSEMBLE._verifier_prompt(
            base="", shot_id="synthetic", verifier_id="verifier_1",
            verification_view=ENSEMBLE._verification_view(d, a, ["c1"], pairs, split),
            valid_frame_ids=[10, 20],
        )
        for clause in ("a specific category label alone is never proof",
                       "coarse_locator must state the observed physical boundary",
                       "separation from or continuity with nearby content",
                       "occlusion, contrast, or resolution limitation",
                       "Inspect the full original frames"):
            self.assertIn(clause, prompt)
