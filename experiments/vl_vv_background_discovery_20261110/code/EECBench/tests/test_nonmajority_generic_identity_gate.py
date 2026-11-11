import copy
import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import ensemble_shot_entity_detection as ENSEMBLE  # noqa: E402


FRAME_ID = 10
DEFAULT_ROSTER = tuple(f"detector_{index}" for index in range(1, 5))


def _cluster(
    cluster_id,
    proposal_ids,
    *,
    canonical_name="small object",
    final_name=None,
    flags=None,
):
    final_name = final_name or canonical_name
    return {
        "cluster_id": cluster_id,
        "anonymous_proposal_ids": list(proposal_ids),
        "canonical_name": canonical_name,
        "aliases": [canonical_name],
        "granularity": "whole_instance",
        "adjudicator_evidence": [
            {
                "frame_id": FRAME_ID,
                "coarse_locator": "lower center",
                "support_quality": "moderate",
            }
        ],
        "frame_presence": [
            {
                "frame_id": FRAME_ID,
                "status": "visible",
                "description": "bounded candidate",
            }
        ],
        "identity_status": "resolved",
        "decision": "accept",
        "decision_reason": "accepted by the revised adjudicator",
        "uncertainty_flags": list(
            flags if flags is not None else ["exact_subtype_uncertain"]
        ),
        "final_entity": {
            "name": final_name,
            "attributes": [],
            "entity_confidence": 0.8,
            "evidence_frame_ids": [FRAME_ID],
        },
    }


def _decisions(cluster):
    return {
        "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
        "shot_id": "shot_test",
        "clusters": [cluster],
        "warnings": [],
    }


def _source_map(proposal_sources):
    return {
        "mappings": [
            {
                "anonymous_proposal_id": proposal_id,
                "source_kind": "detector",
                "source": source,
                "local_id": f"{source}_{proposal_id}",
            }
            for proposal_id, source in proposal_sources.items()
        ]
    }


def _review(
    cluster_id,
    *,
    quality="moderate",
    independence_quality=None,
    existence="confirmed",
    salience="graph_worthy",
):
    independence = []
    if independence_quality is not None:
        independence.append(
            {
                "frame_id": FRAME_ID,
                "coarse_locator": "separately handled candidate",
                "support_quality": independence_quality,
            }
        )
    return {
        "cluster_id": cluster_id,
        "existence_judgment": existence,
        "salience_judgment": salience,
        "same_instance_with_cluster_ids": [],
        "graph_partition_judgment": "keep_as_separate_node",
        "same_graph_node_with_cluster_ids": [],
        "observed_independence_evidence": independence,
        "intra_cluster_split_judgment": "not_reviewed",
        "proposed_physical_units": [],
        "pairwise_physical_separation_evidence": [],
        "evidence": [
            {
                "frame_id": FRAME_ID,
                "coarse_locator": "bounded candidate",
                "support_quality": quality,
            }
        ],
        "reason": "independent review",
    }


def _reports(
    cluster_id="c_initial",
    *,
    qualities=("moderate", "moderate"),
    independence_qualities=(None, None),
):
    return [
        {
            "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
            "shot_id": "shot_test",
            "verifier_id": verifier_id,
            "reviews": [
                _review(
                    cluster_id,
                    quality=quality,
                    independence_quality=independence_quality,
                )
            ],
            "warnings": [],
        }
        for verifier_id, quality, independence_quality in zip(
            ENSEMBLE.VERIFIER_IDS,
            qualities,
            independence_qualities,
        )
    ]


def _run_gate(
    decisions,
    *,
    initial_decisions=None,
    proposal_sources=None,
    reports=None,
    reasons=None,
    roster=DEFAULT_ROSTER,
    split_consensus=None,
):
    initial_decisions = initial_decisions or decisions
    proposal_sources = proposal_sources or {
        proposal_id: f"detector_{index}"
        for index, proposal_id in enumerate(
            decisions["clusters"][0]["anonymous_proposal_ids"], start=1
        )
    }
    return ENSEMBLE.apply_nonmajority_generic_identity_gate(
        decisions,
        initial_decisions=initial_decisions,
        source_map=_source_map(proposal_sources),
        verifier_reports=reports if reports is not None else _reports(),
        verification_target_reasons=(
            reasons
            if reasons is not None
            else {"c_initial": ["detector_support_at_most_2"]}
        ),
        expected_detector_ids=roster,
        intra_cluster_split_consensus=split_consensus,
    )


class NonmajorityGenericIdentityGateTest(unittest.TestCase):
    def test_nonmajority_placeholder_uncertain_moderate_only_abstains(self):
        decisions = _decisions(_cluster("c_initial", ["p1", "p2"]))
        original = copy.deepcopy(decisions)

        gated, audit = _run_gate(decisions)

        self.assertEqual(decisions, original)
        cluster = gated["clusters"][0]
        self.assertEqual(cluster["decision"], "abstain")
        self.assertEqual(cluster["identity_status"], "ambiguous")
        self.assertIsNone(cluster["final_entity"])
        self.assertIn(
            "nonmajority_generic_identity_evidence_gate",
            cluster["uncertainty_flags"],
        )
        record = audit["records"][0]
        self.assertEqual(record["detector_support"], 2)
        self.assertEqual(record["detector_denominator"], 4)
        self.assertTrue(all(record["predicates"].values()))
        self.assertEqual(record["result"], "changed_to_abstain")
        self.assertFalse(record["rescues"]["unanimous_strong_confirmation"])
        self.assertFalse(
            record["rescues"]["unanimous_independence_confirmation"]
        )
        ENSEMBLE.validate_decisions(
            gated,
            shot_id="shot_test",
            anonymous_ids=["p1", "p2"],
            valid_frame_ids=[FRAME_ID],
        )

    def test_majority_support_is_outside_gate(self):
        decisions = _decisions(_cluster("c_initial", ["p1", "p2", "p3"]))

        gated, audit = _run_gate(decisions)

        self.assertEqual(gated, decisions)
        self.assertEqual(audit["records"], [])

    def test_five_detector_roster_uses_true_nonmajority_boundary(self):
        roster = tuple(f"detector_{index}" for index in range(1, 6))
        two_source = _decisions(_cluster("c_initial", ["p1", "p2"]))
        three_source = _decisions(_cluster("c_initial", ["p1", "p2", "p3"]))

        gated_two, audit_two = _run_gate(two_source, roster=roster)
        gated_three, audit_three = _run_gate(three_source, roster=roster)

        self.assertEqual(gated_two["clusters"][0]["decision"], "abstain")
        self.assertEqual(audit_two["records"][0]["detector_denominator"], 5)
        self.assertEqual(gated_three, three_source)
        self.assertEqual(audit_three["records"], [])

    def test_specific_accepted_identity_is_not_gated(self):
        decisions = _decisions(
            _cluster(
                "c_initial",
                ["p1", "p2"],
                canonical_name="mounted textile panel",
            )
        )

        gated, audit = _run_gate(decisions)

        self.assertEqual(gated, decisions)
        record = audit["records"][0]
        self.assertFalse(record["predicates"]["placeholder_only_identity"])
        self.assertEqual(record["result"], "kept_accept")

    def test_specific_alias_does_not_rescue_placeholder_final_identity(self):
        cluster = _cluster("c_initial", ["p1", "p2"])
        cluster["aliases"] = ["specific subtype guess"]
        decisions = _decisions(cluster)

        gated, audit = _run_gate(decisions)

        self.assertEqual(gated["clusters"][0]["decision"], "abstain")
        self.assertTrue(
            audit["records"][0]["predicates"]["placeholder_only_identity"]
        )

    def test_generic_name_without_identity_uncertainty_is_not_gated(self):
        decisions = _decisions(
            _cluster(
                "c_initial",
                ["p1", "p2"],
                flags=["small_low_contrast_candidate"],
            )
        )

        gated, audit = _run_gate(decisions)

        self.assertEqual(gated, decisions)
        self.assertFalse(
            audit["records"][0]["predicates"]["identity_or_subtype_uncertain"]
        )

    def test_unanimous_strong_confirmation_rescues(self):
        decisions = _decisions(_cluster("c_initial", ["p1", "p2"]))

        gated, audit = _run_gate(
            decisions,
            reports=_reports(qualities=("strong", "strong")),
        )

        self.assertEqual(gated, decisions)
        self.assertTrue(
            audit["records"][0]["rescues"]["unanimous_strong_confirmation"]
        )

    def test_unanimous_supported_independence_rescues(self):
        decisions = _decisions(_cluster("c_initial", ["p1", "p2"]))

        gated, audit = _run_gate(
            decisions,
            reports=_reports(
                independence_qualities=("moderate", "strong")
            ),
        )

        self.assertEqual(gated, decisions)
        self.assertTrue(
            audit["records"][0]["rescues"][
                "unanimous_independence_confirmation"
            ]
        )

    def test_one_strong_verifier_is_not_a_unanimous_rescue(self):
        decisions = _decisions(_cluster("c_initial", ["p1", "p2"]))

        gated, audit = _run_gate(
            decisions,
            reports=_reports(qualities=("strong", "moderate")),
        )

        self.assertEqual(gated["clusters"][0]["decision"], "abstain")
        self.assertFalse(
            audit["records"][0]["rescues"]["unanimous_strong_confirmation"]
        )

    def test_missing_verifier_fails_closed(self):
        decisions = _decisions(_cluster("c_initial", ["p1", "p2"]))

        gated, audit = _run_gate(
            decisions,
            reports=_reports()[:1],
        )

        self.assertEqual(gated["clusters"][0]["decision"], "abstain")
        verifier_records = {
            item["verifier_id"]: item
            for item in audit["records"][0]["verifier_judgments"]
        }
        self.assertFalse(verifier_records["verifier_2"]["complete"])

    def test_partial_target_cannot_reuse_parent_strong_evidence(self):
        initial = _decisions(_cluster("c_initial", ["p1", "p2"]))
        revised = _decisions(_cluster("c_child", ["p1"]))

        gated, audit = _run_gate(
            revised,
            initial_decisions=initial,
            proposal_sources={"p1": "detector_1", "p2": "detector_2"},
            reports=_reports(qualities=("strong", "strong")),
            split_consensus={"exact_consensus_partitions": []},
        )

        self.assertEqual(gated["clusters"][0]["decision"], "abstain")
        summaries = audit["records"][0]["verifier_judgments"]
        self.assertTrue(
            all(
                item["reviews"][0]["confirmation_scope"]
                == "partial_target_without_exact_unit_confirmation"
                for item in summaries
            )
        )

    def test_exact_split_child_uses_unit_evidence_and_pairwise_separation(self):
        initial = _decisions(_cluster("c_initial", ["p1", "p2"]))
        revised = _decisions(_cluster("c_child", ["p1"]))
        reports = []
        for verifier_id in ENSEMBLE.VERIFIER_IDS:
            review = _review("c_initial", quality="strong")
            review.update(
                {
                    "intra_cluster_split_judgment": (
                        "split_into_multiple_physical_instances"
                    ),
                    "proposed_physical_units": [
                        {
                            "unit_id": "u1",
                            "anonymous_proposal_ids": ["p1"],
                            "existence_judgment": "confirmed",
                            "salience_judgment": "graph_worthy",
                            "evidence": [
                                {
                                    "frame_id": FRAME_ID,
                                    "coarse_locator": "first bounded unit",
                                    "support_quality": "moderate",
                                }
                            ],
                        },
                        {
                            "unit_id": "u2",
                            "anonymous_proposal_ids": ["p2"],
                            "existence_judgment": "confirmed",
                            "salience_judgment": "graph_worthy",
                            "evidence": [
                                {
                                    "frame_id": FRAME_ID,
                                    "coarse_locator": "second bounded unit",
                                    "support_quality": "moderate",
                                }
                            ],
                        },
                    ],
                    "pairwise_physical_separation_evidence": [
                        {
                            "unit_id_a": "u1",
                            "unit_id_b": "u2",
                            "frame_id": FRAME_ID,
                            "unit_a_coarse_locator": "first bounded unit",
                            "unit_b_coarse_locator": "second bounded unit",
                            "support_quality": "moderate",
                        }
                    ],
                }
            )
            reports.append(
                {
                    "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
                    "shot_id": "shot_test",
                    "verifier_id": verifier_id,
                    "reviews": [review],
                    "warnings": [],
                }
            )

        gated, audit = _run_gate(
            revised,
            initial_decisions=initial,
            proposal_sources={"p1": "detector_1", "p2": "detector_2"},
            reports=reports,
            split_consensus={
                "exact_consensus_partitions": [
                    {
                        "cluster_id": "c_initial",
                        "proposal_partition": [["p1"], ["p2"]],
                    }
                ]
            },
        )

        self.assertEqual(gated, revised)
        record = audit["records"][0]
        self.assertFalse(record["rescues"]["unanimous_strong_confirmation"])
        self.assertTrue(
            record["rescues"]["unanimous_independence_confirmation"]
        )
        for verifier in record["verifier_judgments"]:
            unit_review = verifier["reviews"][0]
            self.assertEqual(
                unit_review["confirmation_scope"], "exact_consensus_split_unit"
            )
            self.assertEqual(
                unit_review["evidence_support_qualities"], ["moderate"]
            )

    def test_unknown_source_or_invalid_roster_is_rejected(self):
        decisions = _decisions(_cluster("c_initial", ["p1", "p2"]))

        with self.assertRaises(ENSEMBLE.EnsembleError):
            _run_gate(
                decisions,
                proposal_sources={"p1": "detector_1", "p2": "detector_9"},
            )
        with self.assertRaises(ENSEMBLE.EnsembleError):
            _run_gate(decisions, roster=("detector_1", "detector_1"))


if __name__ == "__main__":
    unittest.main()
