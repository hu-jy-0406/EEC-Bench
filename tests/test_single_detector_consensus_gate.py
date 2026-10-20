import copy
import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import ensemble_shot_entity_detection as ENSEMBLE  # noqa: E402


def _cluster(cluster_id, proposal_ids):
    return {
        "cluster_id": cluster_id,
        "anonymous_proposal_ids": list(proposal_ids),
        "canonical_name": "small object",
        "aliases": ["small object"],
        "granularity": "whole_instance",
        "adjudicator_evidence": [],
        "frame_presence": [],
        "identity_status": "resolved",
        "decision": "accept",
        "decision_reason": "accepted by the revised adjudicator",
        "uncertainty_flags": [],
        "final_entity": {
            "name": "small object",
            "attributes": [],
            "entity_confidence": 0.9,
            "evidence_frame_ids": [10],
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


def _verifier_report(
    verifier_id,
    *,
    cluster_id="c_initial",
    existence="confirmed",
    salience="graph_worthy",
):
    return {
        "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
        "shot_id": "shot_test",
        "verifier_id": verifier_id,
        "reviews": [
            {
                "cluster_id": cluster_id,
                "existence_judgment": existence,
                "salience_judgment": salience,
            }
        ],
        "warnings": [],
    }


def _run_gate(
    decisions,
    *,
    initial_decisions=None,
    source_map=None,
    verifier_reports=None,
    verification_target_reasons=None,
):
    return ENSEMBLE.apply_single_detector_consensus_gate(
        decisions,
        initial_decisions=initial_decisions or decisions,
        source_map=source_map or _source_map({"p0001": "detector_1"}),
        verifier_reports=(
            verifier_reports
            if verifier_reports is not None
            else [
                _verifier_report("verifier_1"),
                _verifier_report("verifier_2"),
            ]
        ),
        verification_target_reasons=(
            verification_target_reasons
            if verification_target_reasons is not None
            else {"c_initial": ["detector_support_at_most_2"]}
        ),
    )


class SingleDetectorConsensusGateTest(unittest.TestCase):
    def test_one_detector_with_two_confirmations_stays_accepted(self):
        decisions = _decisions(_cluster("c_initial", ["p0001"]))
        decisions_before = copy.deepcopy(decisions)

        gated, audit = _run_gate(decisions)

        self.assertEqual(gated, decisions_before)
        self.assertEqual(decisions, decisions_before)
        self.assertEqual(len(audit["records"]), 1)
        record = audit["records"][0]
        self.assertTrue(record["unanimous_confirmed_graph_worthy"])
        self.assertEqual(record["result"], "kept_accept")
        self.assertEqual(
            [item["confirmed_graph_worthy"] for item in record["verifier_judgments"]],
            [True, True],
        )

    def test_any_ambiguous_salience_changes_singleton_to_abstain(self):
        for ambiguous_verifier in ENSEMBLE.VERIFIER_IDS:
            with self.subTest(ambiguous_verifier=ambiguous_verifier):
                decisions = _decisions(_cluster("c_initial", ["p0001"]))
                reports = [
                    _verifier_report(
                        verifier_id,
                        salience=(
                            "ambiguous"
                            if verifier_id == ambiguous_verifier
                            else "graph_worthy"
                        ),
                    )
                    for verifier_id in ENSEMBLE.VERIFIER_IDS
                ]

                gated, audit = _run_gate(
                    decisions, verifier_reports=reports
                )

                cluster = gated["clusters"][0]
                self.assertEqual(cluster["decision"], "abstain")
                self.assertEqual(cluster["identity_status"], "ambiguous")
                self.assertIsNone(cluster["final_entity"])
                self.assertIn(
                    "single_detector_consensus_gate_not_unanimous",
                    cluster["uncertainty_flags"],
                )
                self.assertEqual(
                    audit["records"][0]["result"], "changed_to_abstain"
                )
                self.assertFalse(
                    audit["records"][0]["unanimous_confirmed_graph_worthy"]
                )

    def test_missing_verifier_changes_singleton_to_abstain(self):
        decisions = _decisions(_cluster("c_initial", ["p0001"]))

        gated, audit = _run_gate(
            decisions,
            verifier_reports=[_verifier_report("verifier_1")],
        )

        self.assertEqual(gated["clusters"][0]["decision"], "abstain")
        self.assertIsNone(gated["clusters"][0]["final_entity"])
        judgments = {
            item["verifier_id"]: item
            for item in audit["records"][0]["verifier_judgments"]
        }
        self.assertTrue(judgments["verifier_1"]["complete"])
        self.assertFalse(judgments["verifier_2"]["complete"])
        self.assertFalse(judgments["verifier_2"]["confirmed_graph_worthy"])

    def test_two_detector_cluster_is_not_gated(self):
        decisions = _decisions(
            _cluster("c_initial", ["p0001", "p0002"])
        )
        decisions_before = copy.deepcopy(decisions)

        gated, audit = _run_gate(
            decisions,
            source_map=_source_map(
                {"p0001": "detector_1", "p0002": "detector_2"}
            ),
            verifier_reports=[],
        )

        self.assertEqual(gated, decisions_before)
        self.assertEqual(audit["records"], [])

    def test_revision_split_cannot_reuse_initial_review_by_proposal_overlap(self):
        initial = _decisions(
            _cluster("c_initial", ["p0001", "p0002"])
        )
        revised = _decisions(_cluster("c_revision", ["p0002"]))

        gated, audit = _run_gate(
            revised,
            initial_decisions=initial,
            source_map=_source_map(
                {"p0001": "detector_1", "p0002": "detector_1"}
            ),
        )

        self.assertEqual(gated["clusters"][0]["cluster_id"], "c_revision")
        self.assertEqual(gated["clusters"][0]["decision"], "abstain")
        self.assertEqual(
            audit["records"][0]["initial_target_cluster_ids"], ["c_initial"]
        )
        self.assertFalse(
            audit["records"][0]["unanimous_confirmed_graph_worthy"]
        )
        self.assertEqual(
            audit["records"][0]["verifier_judgments"][0]["reviews"][0][
                "confirmation_scope"
            ],
            "partial_target_without_exact_unit_confirmation",
        )


if __name__ == "__main__":
    unittest.main()
