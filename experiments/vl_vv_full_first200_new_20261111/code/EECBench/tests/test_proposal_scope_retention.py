"""One positive subset and an honestly unresolved remainder; no model calls."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import proposal_scope_retention as R  # noqa: E402


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def cluster(key, proposals, decision="accept"):
    return {"cluster_id": key, "anonymous_proposal_ids": proposals, "decision": decision,
            "final_entity": {"name": "synthetic visible scope"} if decision == "accept" else None}


def initial():
    return {"shot_id": "synthetic", "clusters": [cluster("parent", ["p1", "p2", "p3", "p4"])],
            "attempts": [{"status": "failed", "subprocess_started": True,
                          "usage": {"input_tokens": 19, "output_tokens": 7}},
                         {"status": "failed", "subprocess_started": None, "usage": None}]}


def request(retained=("p1", "p2")):
    return {
        "parent_cluster_id": "parent", "parent_anonymous_proposal_ids": ["p1", "p2", "p3", "p4"],
        "retained_anonymous_proposal_ids": list(retained),
        "residual_anonymous_proposal_ids": sorted({"p1", "p2", "p3", "p4"} - set(retained)),
        "existence_judgment": "confirmed", "salience_judgment": "graph_worthy",
        "proposal_scope_judgment": "resolved_single_scope", "residual_status": "unresolved",
        "reason": "The visible extent supports this subset; the other claims remain unconfirmed.",
        "retained_evidence": [{"frame_id": 4, "coarse_locator": "visible compact boundary",
                               "support_quality": "moderate", "anonymous_proposal_ids": list(retained),
                               "cue_type": "physical_boundary", "observation": "One visible connected boundary."}],
        "physical_evidence_indices": [0], "scope_evidence_indices": [0],
    }


def reports():
    return [{"shot_id": "synthetic", "verifier_id": key, "retention_requests": [request()],
             "original_parent_review": {"proposal_scope_judgment": "mixed_scope"},
             "attempts": [{"status": "failed", "usage": {"total_tokens": 26}},
                          {"status": "success", "usage": {"total_tokens": 31}}]}
            for key in R.VERIFIER_IDS]


def sources(rows):
    return {row["verifier_id"]: {"source_id": "source:" + row["verifier_id"],
                                "thread_id": "thread:" + row["verifier_id"],
                                "report_sha256": digest(row)} for row in rows}


def consensus(ledger=None, rows=None, private=None):
    ledger = initial() if ledger is None else ledger
    rows = reports() if rows is None else rows
    return R.build_retention_consensus(rows, initial_decisions=ledger, valid_frame_ids=[4, 8],
                                      report_sources=sources(rows) if private is None else private)


def revised():
    return {"shot_id": "synthetic", "clusters": [cluster("survivor", ["p2", "p1"]),
            cluster("uncertain_remainder", ["p3"], "abstain"), cluster("rejected_claim", ["p4"], "reject")]}


class ProposalScopeRetentionTests(unittest.TestCase):
    def check_request(self, value):
        return R.validate_retention_request(value, parent_cluster_id="parent",
                                            parent_proposal_ids=["p1", "p2", "p3", "p4"],
                                            valid_frame_ids=[4, 8])

    def test_polluted_parent_can_keep_one_scope_without_positive_remainder_or_mutation(self):
        before, rows, after = initial(), reports(), revised()
        private = sources(rows)
        original = deepcopy([before, rows, private, after])
        agreement = consensus(before, rows, private)
        audit = R.validate_retention_transition(before, after, agreement)
        self.assertEqual(audit["audited_parent_ids"], ["parent"])
        self.assertEqual(audit["audited_transitions"][0]["final_accepted_count"], 1)
        self.assertEqual(audit["audited_transitions"][0]["residual_anonymous_proposal_ids"], ["p3", "p4"])
        self.assertTrue(audit["all_original_proposals_accounted_once"])
        self.assertFalse(agreement["physical_split_authorization"])
        self.assertFalse(agreement["residual_existence_asserted"])
        self.assertFalse(agreement["automatic_acceptance"])
        self.assertFalse(audit["pixel_truth_verified"])
        self.assertIn("caller_supplied", agreement["independent_source_authentication"])
        self.assertEqual([before, rows, private, after], original)
        agreement["input_binding"]["verifier_reports"][0]["attempts"].clear()
        self.assertEqual([before, rows, private, after], original)

    def test_complete_parent_need_not_apply_consensus_for_any_decision(self):
        for decision in ("accept", "abstain", "reject"):
            with self.subTest(decision=decision):
                after = {"shot_id": "synthetic", "clusters": [cluster("renamed", ["p4", "p2", "p1", "p3"], decision)]}
                audit = R.validate_retention_transition(initial(), after, consensus())
                self.assertEqual(audit["audited_transitions"], [])
                self.assertEqual(audit["not_applied_transitions"][0]["disposition"], "not_applied")
                self.assertEqual(audit["not_applied_transitions"][0]["final_decision"], decision)
                self.assertTrue(audit["outer_schema_physical_pair_and_lineage_validation_required"])

    def test_retained_survivor_can_still_be_withdrawn(self):
        for decision in ("abstain", "reject"):
            after = revised()
            after["clusters"][0] = cluster("survivor", ["p1", "p2"], decision)
            audit = R.validate_retention_transition(initial(), after, consensus())
            self.assertEqual(audit["audited_transitions"][0]["final_accepted_count"], 0)

    def test_complete_parent_and_exact_complement_strictness(self):
        changes = [
            ("parent_cluster_id", "unknown"), ("parent_anonymous_proposal_ids", ["p1", "p2", "p3"]),
            ("retained_anonymous_proposal_ids", []), ("retained_anonymous_proposal_ids", ["p1", "p1"]),
            ("retained_anonymous_proposal_ids", ["p1", "p2", "p3", "p4"]),
            ("retained_anonymous_proposal_ids", ["p1", "other"]),
            ("residual_anonymous_proposal_ids", []), ("residual_anonymous_proposal_ids", ["p3"]),
            ("residual_anonymous_proposal_ids", ["p2", "p3", "p4"]),
            ("residual_status", "nonexistent"), ("reason", "  "), ("existence_judgment", "unresolved"),
            ("salience_judgment", "not_graph_worthy"), ("proposal_scope_judgment", "mixed_scope"),
        ]
        for key, value in changes:
            with self.subTest(key=key, value=value):
                raw = request()
                raw[key] = value
                with self.assertRaises(R.RetentionContractError):
                    self.check_request(raw)
        for extra in ("new_proposal_ids", "accepted_entity_count", "intra_cluster_split_judgment"):
            raw = request()
            raw[extra] = []
            with self.assertRaises(R.RetentionContractError):
                self.check_request(raw)

    def test_own_subset_proof_cannot_borrow_parent_partial_external_or_category_evidence(self):
        for ids in (["p1", "p2", "p3", "p4"], ["p1"], ["p1", "other"]):
            with self.subTest(ids=ids):
                raw = request()
                raw["retained_evidence"][0]["anonymous_proposal_ids"] = ids
                with self.assertRaises(R.RetentionContractError):
                    self.check_request(raw)
        for cue in ("category_only", "unresolved", "non_entity", "integrated_component", [], None):
            with self.subTest(cue=cue):
                raw = request()
                raw["retained_evidence"][0]["cue_type"] = cue
                with self.assertRaises(R.RetentionContractError):
                    self.check_request(raw)

    def test_uncited_partial_and_shared_index_are_honest_but_each_axis_needs_own_witness(self):
        raw = request()
        raw["retained_evidence"].append({**deepcopy(raw["retained_evidence"][0]),
                                          "anonymous_proposal_ids": ["p1"], "cue_type": "unresolved"})
        self.check_request(raw)
        raw["scope_evidence_indices"] = [1]
        with self.assertRaises(R.RetentionContractError):
            self.check_request(raw)
        raw = request()
        raw["retained_evidence"].append({**deepcopy(raw["retained_evidence"][0]),
                                          "frame_id": 8, "cue_type": "same_instance_continuity"})
        raw["scope_evidence_indices"] = [1]
        self.check_request(raw)
        raw["physical_evidence_indices"] = [1]
        with self.assertRaises(R.RetentionContractError):
            self.check_request(raw)

    def test_indices_true_integer_nonempty_unique_and_every_selected_row_exact(self):
        for key in ("physical_evidence_indices", "scope_evidence_indices"):
            for value in ([], None, [True], [0.0], [-1], [1], [0, 0], ["0"]):
                with self.subTest(key=key, value=value):
                    raw = request()
                    raw[key] = value
                    with self.assertRaises(R.RetentionContractError):
                        self.check_request(raw)
            raw = request()
            raw["retained_evidence"].append({**deepcopy(raw["retained_evidence"][0]), "cue_type": "unresolved"})
            raw[key] = [0, 1]
            with self.assertRaises(R.RetentionContractError):
                self.check_request(raw)

    def test_frame_and_evidence_shape_failures(self):
        for value in (True, 4.0, None, "4", -1, 9):
            raw = request()
            raw["retained_evidence"][0]["frame_id"] = value
            with self.subTest(value=value), self.assertRaises(R.RetentionContractError):
                self.check_request(raw)
        for key, value in (("coarse_locator", " "), ("observation", ""), ("support_quality", None),
                           ("anonymous_proposal_ids", ["p1", "p1"]), ("invented_bbox", [0, 0, 1, 1])):
            raw = request()
            raw["retained_evidence"][0][key] = value
            with self.subTest(key=key), self.assertRaises(R.RetentionContractError):
                self.check_request(raw)
        raw = request()
        del raw["retained_evidence"][0]["coarse_locator"]
        with self.assertRaises(R.RetentionContractError):
            self.check_request(raw)
        for frames in ([], [4, 4], [True], [4.0], [-1]):
            with self.subTest(frames=frames), self.assertRaises(R.RetentionContractError):
                R.validate_retention_request(request(), parent_cluster_id="parent",
                                             parent_proposal_ids=["p1", "p2", "p3", "p4"], valid_frame_ids=frames)

    def test_only_initially_accepted_nonsingleton_parents_eligible(self):
        for decision in ("reject", "abstain"):
            ledger = initial()
            ledger["clusters"][0] = cluster("parent", ["p1", "p2", "p3", "p4"], decision)
            with self.assertRaisesRegex(R.RetentionContractError, "initially accept"):
                consensus(ledger)
        ledger = initial()
        ledger["clusters"][0]["anonymous_proposal_ids"] = ["p1"]
        with self.assertRaisesRegex(R.RetentionContractError, "initially accept"):
            consensus(ledger)

    def test_private_source_independence_and_report_hash_binding(self):
        for field in ("source_id", "thread_id"):
            rows = reports()
            private = sources(rows)
            private["verifier_2"][field] = private["verifier_1"][field]
            with self.subTest(field=field), self.assertRaises(R.RetentionContractError):
                consensus(rows=rows, private=private)
        rows = reports()
        private = sources(rows)
        rows[0]["retention_requests"][0]["reason"] += " Changed after authentication."
        with self.assertRaisesRegex(R.RetentionContractError, "hash mismatch"):
            consensus(rows=rows, private=private)
        private = sources(reports())
        private["verifier_1"]["report_sha256"] = "F" * 64
        with self.assertRaises(R.RetentionContractError):
            consensus(private=private)

    def test_exact_roster_shot_and_one_request_per_parent(self):
        for mode in ("one_report", "duplicate_report", "unknown_verifier", "wrong_shot", "duplicate_parent", "unknown_parent"):
            rows = reports()
            if mode == "one_report":
                rows.pop()
            elif mode == "duplicate_report":
                rows[1] = deepcopy(rows[0])
            elif mode == "unknown_verifier":
                rows[1]["verifier_id"] = "third_verifier"
            elif mode == "wrong_shot":
                rows[1]["shot_id"] = "another_shot"
            elif mode == "duplicate_parent":
                rows[1]["retention_requests"].append(request())
            else:
                rows[1]["retention_requests"][0]["parent_cluster_id"] = "unknown"
            with self.subTest(mode=mode), self.assertRaises(R.RetentionContractError):
                consensus(rows=rows)

    def test_missing_or_disagreeing_subset_is_no_consensus_not_malformed(self):
        for mode in ("missing", "disagreement"):
            rows = reports()
            rows[1]["retention_requests"] = [] if mode == "missing" else [request(("p1", "p3"))]
            agreement = consensus(rows=rows)
            self.assertEqual(agreement["records"][0]["status"], "no_consensus")
            audit = R.validate_retention_transition(initial(), initial(), agreement)
            self.assertEqual(audit["not_applied_transitions"][0]["disposition"], "not_applied")
            with self.assertRaisesRegex(R.RetentionContractError, "lacks exact"):
                R.validate_retention_transition(initial(), revised(), agreement)

    def test_order_independent_exact_set_consensus_and_empty_opt_in(self):
        rows = reports()
        rows[1]["retention_requests"][0] = request(("p2", "p1"))
        self.assertEqual(consensus(rows=rows)["records"][0]["status"], "authorized_single_survivor")
        for row in rows:
            row["retention_requests"] = []
        agreement = consensus(rows=rows)
        self.assertEqual(agreement["records"], [])
        audit = R.validate_retention_transition(initial(), initial(), agreement)
        self.assertEqual(audit["outer_validation_only_parent_ids"], ["parent"])
        with self.assertRaisesRegex(R.RetentionContractError, "Unauthorized scope"):
            R.validate_retention_transition(initial(), revised(), agreement)

    def test_final_ownership_loss_duplicate_new_and_shot_change_rejected(self):
        variants = []
        value = revised()
        value["clusters"].pop()
        variants.append(value)
        value = revised()
        value["clusters"].append(cluster("duplicate", ["p1"], "reject"))
        variants.append(value)
        value = revised()
        value["clusters"].append(cluster("invented", ["new"], "reject"))
        variants.append(value)
        value = revised()
        value["clusters"][1]["cluster_id"] = "survivor"
        variants.append(value)
        value = revised()
        value["shot_id"] = "other_shot"
        variants.append(value)
        for value in variants:
            with self.subTest(value=value), self.assertRaises(R.RetentionContractError):
                R.validate_retention_transition(initial(), value, consensus())

    def test_remainder_accept_and_nonaccept_entity_and_different_survivor_fail(self):
        variants = []
        value = revised()
        value["clusters"][1] = cluster("extra", ["p3"])
        variants.append(value)
        value = revised()
        value["clusters"][1]["final_entity"] = {"name": "hidden accepted scope"}
        variants.append(value)
        value = revised()
        value["clusters"][0]["anonymous_proposal_ids"] = ["p1", "p3"]
        value["clusters"][1]["anonymous_proposal_ids"] = ["p2"]
        variants.append(value)
        value = revised()
        value["clusters"][0]["anonymous_proposal_ids"] = ["p1", "p2", "p3"]
        value["clusters"].pop(1)
        variants.append(value)
        value = revised()
        value["clusters"][0]["anonymous_proposal_ids"] = ["p1"]
        value["clusters"].append(cluster("second_retained_owner", ["p2"], "abstain"))
        variants.append(value)
        for value in variants:
            with self.subTest(value=value), self.assertRaises(R.RetentionContractError):
                R.validate_retention_transition(initial(), value, consensus())

    def test_cross_parent_absorption_in_either_direction_forbidden(self):
        before = initial()
        before["clusters"].append(cluster("unrelated", ["q1", "q2"]))
        for receiving in ("survivor", "uncertain_remainder", "unrelated"):
            after = revised()
            after["clusters"].append(cluster("unrelated", ["q1", "q2"]))
            if receiving == "unrelated":
                after["clusters"][1]["anonymous_proposal_ids"] = ["p3", "q1", "q2"]
                after["clusters"].pop()
            else:
                row = next(x for x in after["clusters"] if x["cluster_id"] == receiving)
                row["anonymous_proposal_ids"].append("q1")
                after["clusters"][-1]["anonymous_proposal_ids"] = ["q2"]
            with self.subTest(receiving=receiving), self.assertRaisesRegex(R.RetentionContractError, "absorbed"):
                R.validate_retention_transition(before, after, consensus(before),
                                                 independently_authorized_split_parent_ids=["unrelated"])

    def test_unrelated_complete_parent_merge_and_independently_authorized_split_remain_outer_checks(self):
        before = initial()
        before["clusters"] += [cluster("a", ["a1", "a2"]), cluster("b", ["b1"]), cluster("c", ["c1"])]
        after = revised()
        after["clusters"] += [cluster("a_part1", ["a1"]), cluster("a_part2", ["a2"]),
                              cluster("merged_bc", ["b1", "c1"])]
        agreement = consensus(before)
        with self.assertRaisesRegex(R.RetentionContractError, "Unauthorized scope"):
            R.validate_retention_transition(before, after, agreement)
        audit = R.validate_retention_transition(before, after, agreement,
                                                 independently_authorized_split_parent_ids=["a"])
        self.assertEqual(audit["audited_parent_ids"], ["parent"])
        self.assertEqual(audit["outer_validation_only_parent_ids"], ["a", "b", "c"])
        self.assertEqual(audit["externally_authorized_split_parent_ids"], ["a"])
        self.assertTrue(audit["outer_schema_physical_pair_and_lineage_validation_required"])
        for ids in (["parent"], ["unknown"], ["a", "a"]):
            with self.subTest(ids=ids), self.assertRaises(R.RetentionContractError):
                R.validate_retention_transition(before, after, agreement,
                                                 independently_authorized_split_parent_ids=ids)

    def test_consensus_and_complete_initial_binding_cannot_be_forged_or_truncated(self):
        for mutation in ("version", "authorization", "subset", "proof", "initial", "hash", "extra"):
            agreement = consensus()
            before = initial()
            if mutation == "version":
                agreement["policy_version"] = "future"
            elif mutation == "authorization":
                agreement["automatic_acceptance"] = True
            elif mutation == "subset":
                agreement["records"][0]["retained_anonymous_proposal_ids"] = ["p1"]
            elif mutation == "proof":
                agreement["records"][0]["proofs"].pop()
            elif mutation == "initial":
                before["attempts"].pop()
            elif mutation == "hash":
                agreement["input_binding"]["report_sources"]["verifier_1"]["report_sha256"] = "0" * 64
            else:
                agreement["new_members"] = []
            with self.subTest(mutation=mutation), self.assertRaises(R.RetentionContractError):
                R.validate_retention_transition(before, revised(), agreement)

    def test_failures_leave_known_failure_cost_unknowns_and_all_ledgers_unchanged(self):
        before, rows, after = initial(), reports(), revised()
        private = sources(rows)
        snapshot = deepcopy([before, rows, after, private])
        agreement = consensus(before, rows, private)
        after["clusters"][1] = cluster("illegal_second_accept", ["p3"])
        failing_snapshot = deepcopy(after)
        with self.assertRaises(R.RetentionContractError):
            R.validate_retention_transition(before, after, agreement)
        self.assertEqual(after, failing_snapshot)
        self.assertEqual([before, rows, private], [snapshot[0], snapshot[1], snapshot[3]])
        private["verifier_2"]["thread_id"] = private["verifier_1"]["thread_id"]
        failing_private = deepcopy(private)
        with self.assertRaises(R.RetentionContractError):
            consensus(before, rows, private)
        self.assertEqual(private, failing_private)
        self.assertEqual(before["attempts"][0]["usage"], {"input_tokens": 19, "output_tokens": 7})
        self.assertIsNone(before["attempts"][1]["usage"])
        self.assertEqual(rows, snapshot[1])


if __name__ == "__main__":
    unittest.main()
