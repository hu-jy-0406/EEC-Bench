import copy
import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import ensemble_shot_entity_detection as ENSEMBLE  # noqa: E402


FRAME_IDS = [0, 10, 20]


def _proposal(proposal_id, name, box):
    return {
        "anonymous_proposal_id": proposal_id,
        "proposed_name": name,
        "canonical_head": name,
        "entity_type": "object",
        "granularity": "whole_instance",
        "attributes": [],
        "evidence_frame_ids": [0],
        "coarse_locators": [
            {"frame_id": 0, "description": f"region for {proposal_id}"}
        ],
        "frame_presence": [
            {
                "frame_id": frame_id,
                "status": "visible",
                "description": f"region for {proposal_id}",
                "bbox_xyxy_normalized": list(box),
            }
            for frame_id in FRAME_IDS
        ],
        "uncertainty_flags": [],
    }


def _cluster(cluster_id, proposal_ids, *, decision="accept"):
    return {
        "cluster_id": cluster_id,
        "anonymous_proposal_ids": list(proposal_ids),
        "canonical_name": "mounted display",
        "aliases": ["mounted display"],
        "granularity": "whole_instance",
        "adjudicator_evidence": [],
        "frame_presence": [],
        "identity_status": "resolved",
        "decision": decision,
        "decision_reason": "initial visual review",
        "uncertainty_flags": [],
        "final_entity": (
            {
                "name": "mounted display",
                "attributes": [],
                "entity_confidence": 0.9,
                "evidence_frame_ids": [0],
            }
            if decision == "accept"
            else None
        ),
    }


def _decisions(clusters):
    return {
        "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
        "shot_id": "shot_test",
        "clusters": clusters,
        "warnings": [],
    }


def _base_review(cluster_id, *, split_judgment, units=None, pairwise=None):
    return {
        "cluster_id": cluster_id,
        "existence_judgment": "confirmed",
        "salience_judgment": "graph_worthy",
        "same_instance_with_cluster_ids": [],
        "graph_partition_judgment": "keep_as_separate_node",
        "same_graph_node_with_cluster_ids": [],
        "observed_independence_evidence": [],
        "intra_cluster_split_judgment": split_judgment,
        "proposed_physical_units": units or [],
        "pairwise_physical_separation_evidence": pairwise or [],
        "evidence": [
            {
                "frame_id": 0,
                "coarse_locator": "bounded mounted content",
                "support_quality": "strong",
            }
        ],
        "reason": "direct review of original pixels",
    }


def _unit(unit_id, proposal_ids, locator):
    return {
        "unit_id": unit_id,
        "anonymous_proposal_ids": list(proposal_ids),
        "existence_judgment": "confirmed",
        "salience_judgment": "graph_worthy",
        "evidence": [
            {
                "frame_id": 0,
                "coarse_locator": locator,
                "support_quality": "strong",
            }
        ],
    }


def _split_report(verifier_id, *, reverse=False):
    if reverse:
        units = [
            _unit("unit_z", ["p0004", "p0003"], "right bounded unit"),
            _unit("unit_y", ["p0002", "p0001"], "left bounded unit"),
        ]
        pairwise = [
            {
                "unit_id_a": "unit_z",
                "unit_id_b": "unit_y",
                "frame_id": 0,
                "unit_a_coarse_locator": "right bounded unit",
                "unit_b_coarse_locator": "left bounded unit",
                "support_quality": "strong",
            }
        ]
    else:
        units = [
            _unit("unit_a", ["p0001", "p0002"], "left bounded unit"),
            _unit("unit_b", ["p0003", "p0004"], "right bounded unit"),
        ]
        pairwise = [
            {
                "unit_id_a": "unit_a",
                "unit_id_b": "unit_b",
                "frame_id": 0,
                "unit_a_coarse_locator": "left bounded unit",
                "unit_b_coarse_locator": "right bounded unit",
                "support_quality": "moderate",
            }
        ]
    return {
        "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
        "shot_id": "shot_test",
        "verifier_id": verifier_id,
        "reviews": [
            _base_review(
                "c_display",
                split_judgment="split_into_multiple_physical_instances",
                units=units,
                pairwise=pairwise,
            )
        ],
        "warnings": [],
    }


class IntraClusterSpatialSplitAuditTest(unittest.TestCase):
    def _disjoint_fixture(self):
        proposals = [
            _proposal("p0001", "mounted display", [0.10, 0.10, 0.25, 0.35]),
            _proposal("p0002", "mounted display", [0.11, 0.11, 0.26, 0.36]),
            _proposal("p0003", "mounted display", [0.70, 0.12, 0.84, 0.36]),
            _proposal("p0004", "mounted display", [0.69, 0.11, 0.83, 0.35]),
        ]
        decisions = _decisions(
            [_cluster("c_display", [item["anonymous_proposal_id"] for item in proposals])]
        )
        anonymous_view = {"proposals": proposals}
        challenges = ENSEMBLE.build_intra_cluster_divergent_footprint_challenges(
            decisions, anonymous_view
        )
        return decisions, anonymous_view, challenges

    def test_persistent_disjoint_groups_are_review_only_then_exact_consensus(self):
        decisions, _, challenges = self._disjoint_fixture()
        before = copy.deepcopy(decisions)

        self.assertEqual(len(challenges), 1)
        self.assertEqual(
            challenges[0]["effect"], "mandatory_review_no_automatic_split"
        )
        self.assertFalse(challenges[0]["source_or_detector_count_used"])
        self.assertEqual(decisions, before)

        reports = [
            _split_report("verifier_1"),
            _split_report("verifier_2", reverse=True),
        ]
        for report in reports:
            ENSEMBLE.validate_verifier_report(
                report,
                shot_id="shot_test",
                verifier_id=report["verifier_id"],
                target_cluster_ids=["c_display"],
                all_cluster_ids=["c_display"],
                valid_frame_ids=FRAME_IDS,
                target_proposal_ids_by_cluster={
                    "c_display": ["p0001", "p0002", "p0003", "p0004"]
                },
                intra_cluster_split_challenges=challenges,
            )
        consensus = ENSEMBLE.build_intra_cluster_split_consensus(
            shot_id="shot_test",
            challenges=challenges,
            verifier_reports=reports,
        )
        self.assertEqual(
            consensus["exact_consensus_partitions"][0]["proposal_partition"],
            [["p0001", "p0002"], ["p0003", "p0004"]],
        )
        revised = _decisions(
            [
                _cluster("c_left", ["p0001", "p0002"]),
                _cluster("c_right", ["p0003", "p0004"]),
            ]
        )
        audit = ENSEMBLE.enforce_intra_cluster_split_consensus(
            initial_decisions=decisions,
            revised_decisions=revised,
            split_consensus=consensus,
        )
        self.assertEqual(audit["observed_split_count"], 1)
        self.assertFalse(audit["automatic_split"])

    def test_prompts_keep_box_trigger_and_split_authority_separate(self):
        decisions, anonymous_view, challenges = self._disjoint_fixture()
        view = ENSEMBLE._verification_view(
            decisions,
            anonymous_view,
            ["c_display"],
            [],
            challenges,
        )
        prompt = ENSEMBLE._verifier_prompt(
            base="",
            shot_id="shot_test",
            verifier_id="verifier_1",
            verification_view=view,
            valid_frame_ids=FRAME_IDS,
        )
        self.assertIn("divergence never proves multiple objects", prompt)
        self.assertIn("partition every anonymous proposal ID", prompt)
        self.assertIn("every unordered pair", prompt)
        self.assertIn("this verifier cannot split anything", prompt)
        revision = ENSEMBLE._revision_prompt(
            shot_id="shot_test",
            initial_decisions=decisions,
            verifier_reports=[],
            identity_challenge_pairs=[],
            valid_frame_ids=FRAME_IDS,
            intra_cluster_split_consensus={
                "exact_consensus_partitions": []
            },
        )
        self.assertIn("permission to review a split", revision)
        self.assertIn("use exactly the consensus proposal partition", revision)

    def test_inaccurate_divergent_boxes_can_keep_one_unit_and_block_split(self):
        decisions, _, challenges = self._disjoint_fixture()
        reports = []
        for verifier_id in ENSEMBLE.VERIFIER_IDS:
            reports.append(
                {
                    "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
                    "shot_id": "shot_test",
                    "verifier_id": verifier_id,
                    "reviews": [
                        _base_review(
                            "c_display",
                            split_judgment="keep_single_physical_instance",
                        )
                    ],
                    "warnings": [],
                }
            )
        consensus = ENSEMBLE.build_intra_cluster_split_consensus(
            shot_id="shot_test",
            challenges=challenges,
            verifier_reports=reports,
        )
        self.assertEqual(consensus["exact_consensus_partitions"], [])
        unchanged = ENSEMBLE.enforce_intra_cluster_split_consensus(
            initial_decisions=decisions,
            revised_decisions=copy.deepcopy(decisions),
            split_consensus=consensus,
        )
        self.assertEqual(unchanged["observed_split_count"], 0)
        split = _decisions(
            [
                _cluster("c_left", ["p0001", "p0002"]),
                _cluster("c_right", ["p0003", "p0004"]),
            ]
        )
        with self.assertRaisesRegex(
            ENSEMBLE.EnsembleError, "without exact two-verifier"
        ):
            ENSEMBLE.enforce_intra_cluster_split_consensus(
                initial_decisions=decisions,
                revised_decisions=split,
                split_consensus=consensus,
            )

    def test_containment_is_not_a_divergent_footprint_or_auto_action(self):
        proposals = [
            _proposal("p0001", "large host", [0.10, 0.10, 0.90, 0.90]),
            _proposal("p0002", "small item", [0.40, 0.40, 0.50, 0.50]),
        ]
        decisions = _decisions([_cluster("c_display", ["p0001", "p0002"])])
        before = copy.deepcopy(decisions)
        challenges = ENSEMBLE.build_intra_cluster_divergent_footprint_challenges(
            decisions, {"proposals": proposals}
        )
        self.assertEqual(challenges, [])
        self.assertEqual(decisions, before)

    def test_split_singleton_needs_exact_unit_not_initial_target_confirmation(self):
        initial = _decisions([_cluster("c_display", ["p0001", "p0002"])])
        revised = _decisions(
            [
                _cluster("c_unit", ["p0001"]),
                _cluster("c_residual", ["p0002"], decision="reject"),
            ]
        )
        source_map = {
            "mappings": [
                {
                    "anonymous_proposal_id": proposal_id,
                    "source_kind": "detector",
                    "source": "detector_1",
                    "local_id": proposal_id,
                }
                for proposal_id in ("p0001", "p0002")
            ]
        }
        cluster_level_reports = [
            {
                "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
                "shot_id": "shot_test",
                "verifier_id": verifier_id,
                "reviews": [
                    _base_review(
                        "c_display",
                        split_judgment="keep_single_physical_instance",
                    )
                ],
                "warnings": [],
            }
            for verifier_id in ENSEMBLE.VERIFIER_IDS
        ]
        gated, audit = ENSEMBLE.apply_single_detector_consensus_gate(
            revised,
            initial_decisions=initial,
            source_map=source_map,
            verifier_reports=cluster_level_reports,
            verification_target_reasons={
                "c_display": ["persistent_intra_cluster_divergent_footprints"]
            },
            intra_cluster_split_consensus={"exact_consensus_partitions": []},
        )
        self.assertEqual(gated["clusters"][0]["decision"], "abstain")
        self.assertEqual(
            audit["records"][0]["verifier_judgments"][0]["reviews"][0][
                "confirmation_scope"
            ],
            "partial_target_without_exact_unit_confirmation",
        )

        split_reports = [
            {
                **_split_report(verifier_id),
                "reviews": [
                    _base_review(
                        "c_display",
                        split_judgment="split_into_multiple_physical_instances",
                        units=[
                            _unit("unit_a", ["p0001"], "left bounded unit"),
                            _unit("unit_b", ["p0002"], "right bounded unit"),
                        ],
                        pairwise=[
                            {
                                "unit_id_a": "unit_a",
                                "unit_id_b": "unit_b",
                                "frame_id": 0,
                                "unit_a_coarse_locator": "left bounded unit",
                                "unit_b_coarse_locator": "right bounded unit",
                                "support_quality": "strong",
                            }
                        ],
                    )
                ],
            }
            for verifier_id in ENSEMBLE.VERIFIER_IDS
        ]
        exact_consensus = {
            "exact_consensus_partitions": [
                {
                    "cluster_id": "c_display",
                    "proposal_partition": [["p0001"], ["p0002"]],
                }
            ]
        }
        gated, audit = ENSEMBLE.apply_single_detector_consensus_gate(
            revised,
            initial_decisions=initial,
            source_map=source_map,
            verifier_reports=split_reports,
            verification_target_reasons={
                "c_display": ["persistent_intra_cluster_divergent_footprints"]
            },
            intra_cluster_split_consensus=exact_consensus,
        )
        self.assertEqual(gated["clusters"][0]["decision"], "accept")
        self.assertEqual(
            audit["records"][0]["verifier_judgments"][0]["reviews"][0][
                "confirmation_scope"
            ],
            "exact_consensus_split_unit",
        )


if __name__ == "__main__":
    unittest.main()
