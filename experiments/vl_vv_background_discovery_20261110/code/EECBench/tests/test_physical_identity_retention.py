"""Opt-in subset proof and pair boundaries; synthetic evidence is not pixel truth."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


F = load("retention_physical_fixtures", ROOT / "tests/test_physical_identity_review.py")
M = F.M
R = load("retention_gate_test_helper", ROOT / "scripts/proposal_scope_retention.py")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def request(retained=("p0001",), parent="parent", scope=("p0001", "p0002", "p0003")):
    return {
        "parent_cluster_id": parent, "parent_anonymous_proposal_ids": list(scope),
        "retained_anonymous_proposal_ids": list(retained),
        "residual_anonymous_proposal_ids": sorted(set(scope) - set(retained)),
        "existence_judgment": "confirmed", "salience_judgment": "graph_worthy",
        "proposal_scope_judgment": "resolved_single_scope", "residual_status": "unresolved",
        "retained_evidence": [F.evidence(retained)],
        "physical_evidence_indices": [0], "scope_evidence_indices": [0],
        "reason": "One supported scope; the remaining claims have unconfirmed correspondence.",
    }


def extended(reports):
    for report in reports:
        report["scope_retention_policy"] = R.POLICY_VERSION
        report["retention_requests"] = []
    return reports


def consensus(initial, reports):
    sources = {row["verifier_id"]: {
        "source_id": "synthetic-source:" + row["verifier_id"],
        "thread_id": "synthetic-thread:" + row["verifier_id"], "report_sha256": digest(row),
    } for row in reports}
    return R.build_retention_consensus(reports, initial_decisions=initial,
                                      valid_frame_ids=[10], report_sources=sources)


def fixture(neighbor=False):
    parent = F.cluster("parent", ("p0001", "p0002", "p0003"))
    parent["proposal_scope_judgment"] = "mixed_scope"
    old = [parent]
    after = [F.cluster("survivor", ("p0001",)), F.cluster("residual_a", ("p0002",), decision="abstain"),
             F.cluster("residual_b", ("p0003",), decision="reject")]
    if neighbor:
        other = F.cluster("neighbor", ("p0004",))
        old.append(other)
        after.append(copy.deepcopy(other))
    reports = extended(F.two_reports(*old))
    for report in reports:
        report["retention_requests"] = [request()]
    return F.ledger(*old), F.ledger(*after), reports


def gate(initial, final, reports, agreement, split=None):
    return M.apply_physical_identity_gate(
        final, initial_decisions=initial, verifier_reports=reports,
        verification_target_reasons={row["cluster_id"]: ["synthetic_review"] for row in initial["clusters"]},
        intra_cluster_split_consensus=split, retention_consensus=agreement)


def old_pair(reports, relation="whole_part", judgment="unresolved"):
    for report in reports:
        for own, other in ((report["reviews"][0], "neighbor"), (report["reviews"][1], "parent")):
            F.comparison(own, other, ("p0001", "p0002", "p0003", "p0004"), judgment, relation=relation)


def final_relation(final, relation="whole_part", scope=("p0001", "p0004"), cue="integrated_component"):
    for own, other in ((final["clusters"][0], "neighbor"), (final["clusters"][-1], "survivor")):
        index = len(own["adjudicator_evidence"])
        own["adjudicator_evidence"].append(F.evidence(scope, cue))
        own["identity_comparisons"].append({"other_cluster_id": other, "judgment": "unresolved",
                                             "scope_relation": relation, "evidence_indices": [index]})


def decisions(result):
    return {row["cluster_id"]: row["decision"] for row in result["clusters"]}


class PhysicalIdentityRetentionTests(unittest.TestCase):
    def test_exact_two_subset_requests_pass_without_physical_residual_or_input_mutation(self):
        initial, final, reports = fixture()
        agreement = consensus(initial, reports)
        before = copy.deepcopy([initial, final, reports, agreement])
        M.validate_adjudication_identity_fields(final, valid_frame_ids=[10])
        result, audit = gate(initial, final, reports, agreement)
        self.assertEqual(decisions(result), {"survivor": "accept", "residual_a": "abstain", "residual_b": "reject"})
        self.assertEqual([initial, final, reports, agreement], before)
        self.assertEqual(result["clusters"][1:], final["clusters"][1:])
        row = audit["records"][0]
        self.assertFalse(row["exact_split_firewall_failed"])
        self.assertEqual(row["revision_resolutions_used"], [])
        self.assertEqual([x["scope_kind"] for x in row["verifier_judgments"]],
                         ["exact_retention_survivor_subset"] * 2)
        retained = audit["scope_retention"]
        self.assertEqual(retained["transition_audit"]["externally_authorized_split_parent_ids"], [])
        self.assertEqual(retained["exact_subset_proofs"][0]["proofs"][0]["request_index"], 0)
        self.assertEqual(retained["verifier_report_sha256s"]["verifier_1"], digest(reports[0]))
        self.assertEqual(retained["independent_source_authentication"], "caller_supplied_not_self_proven")
        self.assertFalse(retained["residual_existence_asserted"])
        self.assertFalse(retained["pixel_truth_verified"])

    def test_default_none_still_refuses_contraction_and_has_no_retention_audit(self):
        initial, final, reports = fixture()
        result, audit = gate(initial, final, reports, None)
        self.assertEqual(result["clusters"][0]["decision"], "abstain")
        self.assertTrue(audit["records"][0]["exact_split_firewall_failed"])
        self.assertNotIn("scope_retention", audit)
        kwargs = dict(initial_decisions=initial, verifier_reports=reports,
                      verification_target_reasons={"parent": ["synthetic_review"]})
        self.assertEqual((result, audit), M.apply_physical_identity_gate(final, **kwargs))

    def test_empty_opt_in_requests_leave_unchanged_old_gate_and_audit_records_equal(self):
        initial = F.ledger(F.cluster())
        reports = extended(F.two_reports(*initial["clusters"]))
        old, old_audit = gate(initial, initial, reports, None)
        new, new_audit = gate(initial, initial, reports, consensus(initial, reports))
        self.assertEqual(old, new)
        del new_audit["scope_retention"]
        self.assertEqual(old_audit, new_audit)

    def test_final_own_axes_and_exact_scope_evidence_are_still_mandatory(self):
        for field, value in (("existence_judgment", "uncertain"), ("salience_judgment", "ambiguous"),
                             ("proposal_scope_judgment", "unresolved"), ("identity_status", "ambiguous")):
            with self.subTest(field=field):
                initial, final, reports = fixture()
                final["clusters"][0][field] = value
                result, audit = gate(initial, final, reports, consensus(initial, reports))
                self.assertEqual(result["clusters"][0]["decision"], "abstain")
                self.assertEqual(audit["scope_retention"]["gated_survivor_results"][0]["decision"], "abstain")
        initial, final, reports = fixture()
        final["clusters"][0]["adjudicator_evidence"] = copy.deepcopy(initial["clusters"][0]["adjudicator_evidence"])
        result, _ = gate(initial, final, reports, consensus(initial, reports))
        self.assertEqual(result["clusters"][0]["decision"], "abstain")

    def test_revision_resolutions_never_replace_missing_or_disagreeing_subset_vote(self):
        for missing in (True, False):
            with self.subTest(missing=missing):
                initial, final, reports = fixture()
                reports[1]["retention_requests"] = [] if missing else [request(("p0002",))]
                for axis in ("physical_entity", "proposal_scope"):
                    F.resolution(final["clusters"][0], axis, ["parent"])
                with self.assertRaisesRegex(M.PhysicalIdentityContractError, "exact retention consensus"):
                    gate(initial, final, reports, consensus(initial, reports))

    def test_uncited_good_evidence_cannot_repair_bad_indexed_subset_proof(self):
        initial, final, reports = fixture()
        reports[1]["retention_requests"][0]["retained_evidence"].append(F.evidence(("p0001",), "category_only"))
        agreement = consensus(initial, reports)
        # Even consistently rehashed current reports cannot alter the dedicated
        # index selection into a valid proof merely because row zero is good.
        reports[1]["retention_requests"][0]["physical_evidence_indices"] = [1]
        agreement["input_binding"]["verifier_reports"] = copy.deepcopy(reports)
        agreement["input_binding"]["report_sources"]["verifier_2"]["report_sha256"] = digest(reports[1])
        with self.assertRaisesRegex(M.PhysicalIdentityContractError, "exact-retained-scope"):
            gate(initial, final, reports, agreement)

    def test_consensus_cannot_be_reused_with_other_initial_or_current_reports(self):
        for changed in ("initial", "review", "request", "header", "missing_report", "roster"):
            with self.subTest(changed=changed):
                initial, final, reports = fixture()
                agreement = consensus(initial, reports)
                if changed == "initial":
                    initial["warnings"].append("different original artifact")
                elif changed == "review":
                    reports[0]["reviews"][0]["reason"] = "Changed complete report."
                elif changed == "request":
                    reports[0]["retention_requests"][0]["reason"] = "Changed subset statement."
                elif changed == "header":
                    reports[0].pop("scope_retention_policy")
                elif changed == "missing_report":
                    reports.pop()
                else:
                    agreement["input_binding"]["verifier_ids"] = ["different", "verifier_2"]
                with self.assertRaises(M.PhysicalIdentityContractError):
                    gate(initial, final, reports, agreement)

    def test_rehashed_consensus_still_requires_distinct_source_thread_and_full_review(self):
        for changed in ("source_id", "thread_id", "missing_review"):
            with self.subTest(changed=changed):
                initial, final, reports = fixture()
                agreement = consensus(initial, reports)
                if changed == "missing_review":
                    reports[0]["reviews"] = []
                    agreement = consensus(initial, reports)
                else:
                    sources = agreement["input_binding"]["report_sources"]
                    sources["verifier_2"][changed] = sources["verifier_1"][changed]
                with self.assertRaises(M.PhysicalIdentityContractError):
                    gate(initial, final, reports, agreement)

    def test_residual_accept_scope_repartition_absorption_and_proposal_loss_are_fatal(self):
        for change in ("accept_residual", "extra_survivor_scope", "lose", "duplicate", "absorb"):
            with self.subTest(change=change):
                initial, final, reports = fixture(neighbor=True)
                agreement = consensus(initial, reports)
                if change == "accept_residual":
                    final["clusters"][1] = F.cluster("residual_a", ("p0002",))
                elif change == "extra_survivor_scope":
                    final["clusters"][0] = F.cluster("survivor", ("p0001", "p0002"))
                    final["clusters"].pop(1)
                elif change == "lose":
                    final["clusters"].pop(1)
                elif change == "duplicate":
                    final["clusters"][1]["anonymous_proposal_ids"].append("p0001")
                else:
                    final["clusters"][0] = F.cluster("survivor", ("p0001", "p0004"))
                    final["clusters"].pop()
                with self.assertRaises(M.PhysicalIdentityContractError):
                    gate(initial, final, reports, agreement)

    def test_retention_parent_cannot_overlap_ordinary_split_even_when_not_applied(self):
        initial, final, reports = fixture()
        split = {"exact_consensus_partitions": [{"cluster_id": "parent", "proposal_partition": [
            ["p0001"], ["p0002", "p0003"]]}]}
        for revised in (initial, final):
            with self.subTest(applied=revised is final), self.assertRaisesRegex(
                    M.PhysicalIdentityContractError, "overlaps retention"):
                gate(initial, revised, reports, consensus(initial, reports), split)

    def test_disjoint_ordinary_split_still_requires_its_own_two_verifier_units(self):
        old, final, reports, split = F.PhysicalIdentityReviewTests().split_fixture()
        reports = extended(reports)
        retained_old, retained_final, retained_reports = fixture()
        old["clusters"].extend(retained_old["clusters"])
        final["clusters"].extend(retained_final["clusters"])
        # Keep the ordinary split's proposal universe separate from the retained
        # parent's universe, while exercising both transitions in the same gate.
        for row in old["clusters"][:1] + final["clusters"][:2]:
            row["anonymous_proposal_ids"] = [value.replace("p000", "p010") for value in row["anonymous_proposal_ids"]]
            for item in row["adjudicator_evidence"]:
                item["anonymous_proposal_ids"] = [value.replace("p000", "p010") for value in item["anonymous_proposal_ids"]]
        split["exact_consensus_partitions"][0]["proposal_partition"] = [["p0101"], ["p0102", "p0103"]]
        for report, retained_report in zip(reports, retained_reports):
            row = report["reviews"][0]
            for item in row["evidence"]:
                item["anonymous_proposal_ids"] = [value.replace("p000", "p010") for value in item["anonymous_proposal_ids"]]
            for unit in row["proposed_physical_units"]:
                unit["anonymous_proposal_ids"] = [value.replace("p000", "p010") for value in unit["anonymous_proposal_ids"]]
                for item in unit["evidence"]:
                    item["anonymous_proposal_ids"] = [value.replace("p000", "p010") for value in item["anonymous_proposal_ids"]]
            report["reviews"].extend(retained_report["reviews"])
            report["retention_requests"] = retained_report["retention_requests"]
        result, audit = gate(old, final, reports, consensus(old, reports), split)
        self.assertEqual([x["decision"] for x in result["clusters"]],
                         ["accept", "accept", "accept", "abstain", "reject"])
        self.assertEqual(audit["scope_retention"]["transition_audit"]["externally_authorized_split_parent_ids"], ["c1"])
        reports[1]["reviews"][0]["proposed_physical_units"][0]["evidence"] = []
        for axis in ("physical_entity", "proposal_scope"):
            F.resolution(final["clusters"][0], axis, ["c1"])
        result, audit = gate(old, final, reports, consensus(old, reports), split)
        self.assertEqual(result["clusters"][0]["decision"], "abstain")
        self.assertTrue(audit["records"][0]["exact_split_firewall_failed"])

    def test_changed_endpoint_never_inherits_parent_relation_or_distinct_proof(self):
        for relation, judgment in (("whole_part", "unresolved"), ("group_member", "unresolved"),
                                   ("comparable", "confirmed_distinct")):
            with self.subTest(relation=relation):
                initial, final, reports = fixture(neighbor=True)
                old_pair(reports, relation, judgment)
                result, audit = gate(initial, final, reports, consensus(initial, reports))
                self.assertEqual(decisions(result)["survivor"], "abstain")
                self.assertEqual(decisions(result)["neighbor"], "abstain")
                self.assertEqual(audit["scope_retention"]["final_relation_proofs"], [])

    def test_ordinary_split_neighbor_relation_unchanged_with_empty_or_unrelated_retention(self):
        for unrelated_retention in (False, True):
            with self.subTest(unrelated_retention=unrelated_retention):
                old, final, reports, split = F.PhysicalIdentityReviewTests().split_fixture()
                reports = extended(reports)
                neighbor = F.cluster("neighbor", ("p0004",))
                old["clusters"].append(neighbor)
                final["clusters"].append(copy.deepcopy(neighbor))
                for report in reports:
                    report["reviews"].append(F.review(neighbor))
                    F.comparison(report["reviews"][0], "neighbor", (), "unresolved", relation="whole_part")
                    F.comparison(report["reviews"][1], "c1", (), "unresolved", relation="whole_part")
                baseline, _ = gate(old, final, reports, None, split)
                self.assertEqual(decisions(baseline), {"u1": "accept", "u2": "accept", "neighbor": "accept"})
                if unrelated_retention:
                    # A separate source universe makes no relation claim about
                    # the ordinary split or its unchanged neighbor.
                    retained_old, retained_final, retained_reports = json.loads(
                        json.dumps(fixture()).replace("p000", "p010"))
                    old["clusters"].extend(retained_old["clusters"])
                    final["clusters"].extend(retained_final["clusters"])
                    for report, retained_report in zip(reports, retained_reports):
                        report["reviews"].extend(retained_report["reviews"])
                        report["retention_requests"] = retained_report["retention_requests"]
                result, audit = gate(old, final, reports, consensus(old, reports), split)
                for key, value in decisions(baseline).items():
                    self.assertEqual(decisions(result)[key], value)
                self.assertEqual(audit["scope_retention"]["final_relation_proofs"], [])
                if unrelated_retention:
                    self.assertEqual(decisions(result)["survivor"], "accept")
                    self.assertEqual(decisions(result)["residual_a"], "abstain")
                    self.assertEqual(decisions(result)["residual_b"], "reject")

    def test_current_reciprocal_relation_needs_both_indexed_exact_final_unions(self):
        for relation in ("whole_part", "group_member"):
            with self.subTest(relation=relation):
                initial, final, reports = fixture(neighbor=True)
                old_pair(reports, relation)
                final_relation(final, relation)
                M.validate_adjudication_identity_fields(final, valid_frame_ids=[10])
                result, audit = gate(initial, final, reports, consensus(initial, reports))
                self.assertEqual(decisions(result)["survivor"], "accept")
                self.assertEqual(decisions(result)["neighbor"], "accept")
                proof, = audit["scope_retention"]["final_relation_proofs"]
                self.assertEqual(proof["union_anonymous_proposal_ids"], ["p0001", "p0004"])
                self.assertEqual([x["exact_union_witness_indices"] for x in proof["endpoints"]], [[1], [1]])
                self.assertFalse(proof["evidence_copied_or_rebound"])

    def test_relation_wrong_scope_empty_indices_one_sided_bad_cue_and_conflict_fail(self):
        for change in ("old_union", "empty", "one_sided", "category", "conflict", "bool_index"):
            with self.subTest(change=change):
                initial, final, reports = fixture(neighbor=True)
                old_pair(reports)
                final_relation(final)
                row = final["clusters"][0]
                if change == "old_union":
                    row["adjudicator_evidence"][1]["anonymous_proposal_ids"] = ["p0001", "p0002", "p0003", "p0004"]
                elif change == "empty":
                    row["identity_comparisons"][0]["evidence_indices"] = []
                elif change == "one_sided":
                    row["identity_comparisons"] = []
                elif change == "category":
                    row["adjudicator_evidence"][1]["cue_type"] = "category_only"
                elif change == "conflict":
                    row["identity_comparisons"][0]["scope_relation"] = "group_member"
                else:
                    row["identity_comparisons"][0]["evidence_indices"] = [True]
                result, _ = gate(initial, final, reports, consensus(initial, reports))
                self.assertEqual(decisions(result)["survivor"], "abstain")
                self.assertEqual(decisions(result)["neighbor"], "abstain")

    def test_no_old_pair_does_not_let_empty_final_relation_bypass_new_scope_duty(self):
        initial, final, reports = fixture(neighbor=True)
        final_relation(final)
        for row in (final["clusters"][0], final["clusters"][-1]):
            row["identity_comparisons"][0]["evidence_indices"] = []
        result, _ = gate(initial, final, reports, consensus(initial, reports))
        self.assertEqual(decisions(result)["survivor"], "abstain")
        self.assertEqual(decisions(result)["neighbor"], "abstain")

    def test_final_exact_union_distinct_resolution_can_discharge_changed_pair_in_either_order(self):
        initial, final, reports = fixture(neighbor=True)
        old_pair(reports)
        survivor = final["clusters"][0]
        F.comparison(survivor, "neighbor", ("p0001", "p0004"), "confirmed_distinct",
                     evidence_key="adjudicator_evidence")
        F.resolution(survivor, "instance_correspondence", ["parent", "neighbor"], 1)
        M.validate_adjudication_identity_fields(final, valid_frame_ids=[10])
        for reverse in (False, True):
            revised = copy.deepcopy(final)
            if reverse:
                revised["clusters"].reverse()
            result, audit = gate(initial, revised, reports, consensus(initial, reports))
            self.assertEqual(decisions(result)["survivor"], "accept")
            self.assertEqual(decisions(result)["neighbor"], "accept")
            for row in audit["records"]:
                self.assertTrue(row["identity_pair_judgments"][0]["revision_distinct_proof_used"])
        survivor["revision_resolutions"][0]["target_cluster_ids"] = ["parent"]
        result, _ = gate(initial, final, reports, consensus(initial, reports))
        self.assertEqual(decisions(result)["survivor"], "abstain")
        self.assertEqual(decisions(result)["neighbor"], "abstain")


if __name__ == "__main__":
    unittest.main()
