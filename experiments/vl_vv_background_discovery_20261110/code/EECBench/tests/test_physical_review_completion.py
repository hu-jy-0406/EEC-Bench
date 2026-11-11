"""No-model checks for a bounded semantic completion prompt and edit firewall.

Invented observations below are contract fixtures, not pixel truth. The final
test explicitly shows why the scope firewall cannot replace physical validation.
"""

import copy
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


F = load("completion_fixtures", Path(__file__).with_name("test_physical_identity_review.py"))
U = load("completion_pair_fixtures", Path(__file__).with_name("test_undirected_distinct_revision.py"))
OB = load("completion_obligations", ROOT / "scripts/physical_review_obligations.py")
M = load("physical_review_completion_tested", ROOT / "scripts/physical_review_completion.py")


def checklist(initial, candidate, reports, consensus=None):
    _, audit = F.M.apply_physical_identity_gate(
        candidate, initial_decisions=initial, verifier_reports=reports,
        verification_target_reasons={x["cluster_id"]: ["synthetic"] for x in initial["clusters"]},
        intra_cluster_split_consensus=consensus)
    return OB.build_physical_review_obligations(
        initial_decisions=initial, candidate_decisions=candidate,
        verifier_reports=reports, gate_audit=audit)


def unary():
    initial = F.ledger(F.cluster("a", ["p1", "p2"]), F.cluster("b", ["q1"]))
    candidate = copy.deepcopy(initial)
    reports = F.two_reports(*initial["clusters"])
    reports[1]["reviews"][0]["salience_judgment"] = "background_integrated"
    return initial, candidate, reports, checklist(initial, candidate, reports)


def pair_case():
    initial, candidate, reports = U.fixture()
    candidate["clusters"][0]["revision_resolutions"] = []
    third = F.cluster("c", ["r1"])
    initial["clusters"].append(copy.deepcopy(third))
    candidate["clusters"].append(copy.deepcopy(third))
    for report in reports:
        report["reviews"].append(F.review(third))
    return initial, candidate, reports, checklist(initial, candidate, reports)


def prompt_args(initial, candidate, reports, obligations):
    proposals = []
    for c in initial["clusters"]:
        for proposal_id in c["anonymous_proposal_ids"]:
            proposals.append({"anonymous_proposal_id": proposal_id,
                              "proposed_name": "laboratory fixture " + proposal_id,
                              "canonical_head": "fixture", "entity_type": "object",
                              "granularity": "individual", "attributes": [], "evidence_frame_ids": [10],
                              "coarse_locators": [{"frame_id": 10, "description": "Distinct outline for " + proposal_id}],
                              "frame_presence": [{"frame_id": 10, "status": "visible",
                                                  "bbox_xyxy_normalized": [0.1, 0.2, 0.4, 0.6]}],
                              "uncertainty_flags": []})
    frames = [{"frame_id": key, "path": f"/original/frame_{key}.jpg", "attachment_index": i}
              for i, key in enumerate((10, 20, 30, 40, 50, 60), 1)]
    return {"candidate_decisions": candidate,
            "initial_scope_map": {c["cluster_id"]: list(c["anonymous_proposal_ids"]) for c in initial["clusters"]},
            "verifier_reports": reports, "obligations": obligations,
            "anonymous_view": {"shot_id": initial["shot_id"], "proposals": proposals},
            "reference_frames": frames, "allowed_input_paths": [x["path"] for x in frames],
            "physical_identity_rule": F.M.PHYSICAL_IDENTITY_RULE}


class PhysicalReviewCompletionTests(unittest.TestCase):
    def test_noop_and_cluster_order_are_valid_without_visual_claims(self):
        _, before, _, obligations = unary()
        for reverse in (False, True):
            after = copy.deepcopy(before)
            if reverse:
                after["clusters"].reverse()
            result = M.validate_completion_scope(before, after, obligations)
            self.assertEqual(result["reviewed_cluster_ids"], ["a"])
            self.assertEqual(result["changed_cluster_ids"], [])
            self.assertEqual(result["unchanged_cluster_ids"], ["a", "b"])
            self.assertEqual(result["cluster_order_changed"], reverse)
            self.assertFalse(result["visual_truth_verified"])
            self.assertFalse(result["independent_verifier_added"])

    def test_reuse_existing_observation_needs_no_copied_or_new_evidence(self):
        _, before, _, obligations = unary()
        after = copy.deepcopy(before)
        F.resolution(after["clusters"][0], "physical_entity", ["a"], 0)
        result = M.validate_completion_scope(before, after, obligations)
        self.assertEqual(result["changed_fields_by_cluster"], {"a": ["revision_resolutions"]})
        self.assertEqual(result["appended_evidence_indices_by_cluster"], {})
        self.assertEqual(after["clusters"][0]["adjudicator_evidence"], before["clusters"][0]["adjudicator_evidence"])

    def test_new_semantic_observation_and_withdrawal_are_allowed(self):
        for decision in ("abstain", "reject"):
            _, before, _, obligations = unary()
            after = copy.deepcopy(before)
            row = after["clusters"][0]
            row.update(decision=decision, final_entity=None, salience_judgment="ambiguous",
                       existence_judgment="uncertain", decision_reason="The original outline is not separable on reinspection.")
            row["adjudicator_evidence"].append(F.evidence(["p1", "p2"], "unresolved", "The support and claimed boundary cannot be distinguished."))
            result = M.validate_completion_scope(before, after, obligations)
            self.assertEqual(result["withdrawn_accept_cluster_ids"], ["a"])
            self.assertEqual(result["appended_evidence_indices_by_cluster"], {"a": [1]})

    def test_names_attributes_and_nonreviewed_clusters_are_protected(self):
        mutations = ("canonical_name", "aliases", "granularity", "frame_presence", "uncertainty_flags",
                     "category_resolution", "entity_name", "attributes", "nonreviewed", "warnings")
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                _, before, _, obligations = unary()
                after = copy.deepcopy(before)
                row = after["clusters"][0]
                if mutation == "entity_name":
                    row["final_entity"]["name"] = "different instrument"
                elif mutation == "attributes":
                    row["final_entity"]["attributes"] = [{"name": "material", "value": "new", "confidence": 1.0, "evidence_frame_ids": [10]}]
                elif mutation == "nonreviewed":
                    after["clusters"][1]["decision_reason"] = "New nonreviewed explanation"
                elif mutation == "warnings":
                    after["warnings"].append("New warning")
                else:
                    row[mutation] = "changed"
                with self.assertRaises(M.PhysicalReviewCompletionError):
                    M.validate_completion_scope(before, after, obligations)

    def test_exact_ownership_no_add_drop_merge_split_duplicate_or_retarget(self):
        for mutation in ("added", "dropped", "duplicate_cluster", "renamed_id", "duplicate_proposal", "moved", "split", "merged"):
            with self.subTest(mutation=mutation):
                _, before, _, obligations = unary()
                after = copy.deepcopy(before)
                if mutation == "added":
                    after["clusters"].append(F.cluster("new", ["new_p"]))
                elif mutation == "dropped":
                    after["clusters"].pop()
                elif mutation == "duplicate_cluster":
                    after["clusters"].append(copy.deepcopy(after["clusters"][0]))
                elif mutation == "renamed_id":
                    after["clusters"][0]["cluster_id"] = "new"
                elif mutation == "duplicate_proposal":
                    after["clusters"][0]["anonymous_proposal_ids"].append("p1")
                elif mutation == "moved":
                    after["clusters"][0]["anonymous_proposal_ids"] = ["p1", "q1"]
                    after["clusters"][1]["anonymous_proposal_ids"] = ["p2"]
                elif mutation == "split":
                    after["clusters"][0]["anonymous_proposal_ids"] = ["p1"]
                    after["clusters"].append(F.cluster("new", ["p2"]))
                else:
                    after["clusters"][0]["anonymous_proposal_ids"].append("q1")
                    after["clusters"].pop()
                with self.assertRaises(M.PhysicalReviewCompletionError):
                    M.validate_completion_scope(before, after, obligations)

    def test_membership_order_can_change_within_reviewed_scope(self):
        _, before, _, obligations = unary()
        after = copy.deepcopy(before)
        after["clusters"][0]["anonymous_proposal_ids"].reverse()
        self.assertEqual(M.validate_completion_scope(before, after, obligations)["changed_cluster_ids"], ["a"])

    def test_old_evidence_indices_and_observations_are_immutable(self):
        for mutation in ("delete", "reorder", "rewrite", "rebind"):
            _, before, _, obligations = pair_case()
            after = copy.deepcopy(before)
            evidence = after["clusters"][0]["adjudicator_evidence"]
            if mutation == "delete":
                evidence.pop()
            elif mutation == "reorder":
                evidence.reverse()
            elif mutation == "rewrite":
                evidence[0]["observation"] = "A different observation"
            else:
                evidence[0]["anonymous_proposal_ids"] = ["p1"]
            with self.assertRaises(M.PhysicalReviewCompletionError):
                M.validate_completion_scope(before, after, obligations)

    def test_pair_only_cannot_change_unary_scope_or_salience(self):
        for field, value in (("existence_judgment", "uncertain"), ("salience_judgment", "background_integrated"),
                             ("proposal_scope_judgment", "mixed_scope")):
            _, before, _, obligations = pair_case()
            after = copy.deepcopy(before)
            after["clusters"][0][field] = value
            with self.assertRaisesRegex(M.PhysicalReviewCompletionError, "outside checklist axis"):
                M.validate_completion_scope(before, after, obligations)

    def test_listed_pair_can_remain_unresolved_or_gain_original_evidence_resolution(self):
        for unresolved in (False, True):
            _, before, _, obligations = pair_case()
            after = copy.deepcopy(before)
            if unresolved:
                after["clusters"][0]["identity_comparisons"][0]["judgment"] = "unresolved"
                after["clusters"][0]["identity_status"] = "ambiguous"
            else:
                F.resolution(after["clusters"][0], "instance_correspondence", ["a", "b"], 1)
            result = M.validate_completion_scope(before, after, obligations)
            self.assertEqual(result["reviewed_cluster_ids"], ["a", "b"])
            self.assertEqual(result["changed_cluster_ids"], ["a"])

    def test_either_pair_endpoint_can_append_its_own_exact_union_observation(self):
        _, before, _, obligations = pair_case()
        after = copy.deepcopy(before)
        U.prove(after["clusters"][1], "a", ["p1", "p2", "q1", "q2"], ["a", "b"])
        result = M.validate_completion_scope(before, after, obligations)
        self.assertEqual(result["appended_evidence_indices_by_cluster"], {"b": [1]})
        self.assertEqual(result["changed_cluster_ids"], ["b"])

    def test_partial_observation_can_be_retained_without_upgrading_its_scope(self):
        _, before, _, obligations = pair_case()
        after = copy.deepcopy(before)
        narrow = F.evidence(["p1"], "unresolved", "Only this proposal fragment is localized on reinspection.")
        after["clusters"][0]["adjudicator_evidence"].append(narrow)
        result = M.validate_completion_scope(before, after, obligations)
        self.assertEqual(after["clusters"][0]["adjudicator_evidence"][-1]["anonymous_proposal_ids"], ["p1"])
        self.assertEqual(result["appended_evidence_indices_by_cluster"], {"a": [2]})
        self.assertFalse(result["visual_truth_verified"])

    def test_evidence_cannot_join_two_separate_authorized_pairs(self):
        initial, before, reports, _ = pair_case()
        for report in reports:
            F.comparison(report["reviews"][0], "c", (), "unresolved")
            F.comparison(report["reviews"][2], "a", (), "unresolved")
        obligations = checklist(initial, before, reports)
        self.assertEqual({tuple(x["cluster_ids"]) for x in obligations["pair_obligations"]}, {("a", "b"), ("a", "c")})
        after = copy.deepcopy(before)
        after["clusters"][0]["adjudicator_evidence"].append(F.evidence(["p1", "q1", "r1"]))
        with self.assertRaisesRegex(M.PhysicalReviewCompletionError, "unauthorized scope"):
            M.validate_completion_scope(before, after, obligations)

    def test_unlisted_pair_resolution_or_evidence_cannot_be_added(self):
        for mutation in ("pair", "axis", "retarget", "evidence", "other_only_evidence"):
            _, before, _, obligations = pair_case()
            after = copy.deepcopy(before)
            row = after["clusters"][0]
            if mutation == "pair":
                F.comparison(row, "c", (), "unresolved", evidence_key="adjudicator_evidence")
            elif mutation == "axis":
                F.resolution(row, "physical_entity", ["a"], 0)
            elif mutation == "retarget":
                F.resolution(row, "instance_correspondence", ["a", "c"], 1)
            elif mutation == "evidence":
                row["adjudicator_evidence"].append(F.evidence(["p1", "p2", "r1"]))
            else:
                row["adjudicator_evidence"].append(F.evidence(["q1", "q2"]))
            with self.assertRaises(M.PhysicalReviewCompletionError):
                M.validate_completion_scope(before, after, obligations)

    def test_existing_pair_or_resolution_cannot_be_silently_deleted(self):
        for field in ("identity_comparisons", "revision_resolutions"):
            _, before, _, obligations = pair_case()
            F.resolution(before["clusters"][0], "physical_entity", ["a"], 0)
            after = copy.deepcopy(before)
            after["clusters"][0][field] = []
            with self.assertRaises(M.PhysicalReviewCompletionError):
                M.validate_completion_scope(before, after, obligations)

    def test_split_authorization_remains_locked(self):
        initial, before, reports, _ = F.PhysicalIdentityReviewTests().split_fixture()
        obligations = checklist(initial, before, reports)
        for item in obligations["cluster_obligations"]:
            item["axis_obligations"] = [x for x in item["axis_obligations"] if x["axis"] == "split_authorization"]
        after = copy.deepcopy(before)
        F.resolution(after["clusters"][0], "proposal_scope", ["c1"])
        with self.assertRaises(M.PhysicalReviewCompletionError):
            M.validate_completion_scope(before, after, obligations)
        after = copy.deepcopy(before)
        after["clusters"][0].update(decision="abstain", final_entity=None)
        self.assertTrue(M.validate_completion_scope(before, after, obligations)["withdrawn_accept_cluster_ids"])

    def test_separate_permitted_axis_resolution_cannot_override_failed_split_gate(self):
        initial, before, reports, _ = F.PhysicalIdentityReviewTests().split_fixture()
        obligations = checklist(initial, before, reports)
        after = copy.deepcopy(before)
        for row in after["clusters"]:
            for axis in ("physical_entity", "proposal_scope"):
                F.resolution(row, axis, ["c1"], 0)
        M.validate_completion_scope(before, after, obligations)
        gated, _ = F.M.apply_physical_identity_gate(
            after, initial_decisions=initial, verifier_reports=reports,
            verification_target_reasons={"c1": ["synthetic"]})
        self.assertTrue(all(row["decision"] == "abstain" for row in gated["clusters"]))

    def test_preexisting_nonaccept_cannot_be_promoted(self):
        _, before, _, obligations = unary()
        before["clusters"][1].update(decision="abstain", final_entity=None)
        after = copy.deepcopy(before)
        after["clusters"][1] = F.cluster("b", ["q1"])
        with self.assertRaises(M.PhysicalReviewCompletionError):
            M.validate_completion_scope(before, after, obligations)

    def test_stale_or_malformed_checklists_fail_closed(self):
        for mutation in ("policy", "scope", "union", "endpoint", "duplicate_pair", "axis_scope", "decision", "missing_endpoint_obligation", "nonaccept_endpoint"):
            _, before, _, obligations = pair_case()
            if mutation == "policy":
                obligations["policy_version"] = "old"
            elif mutation == "scope":
                obligations["cluster_obligations"][0]["anonymous_proposal_ids"] = ["missing"]
            elif mutation == "union":
                obligations["pair_obligations"][0]["union_anonymous_proposal_ids"] = ["p1", "q1"]
            elif mutation == "endpoint":
                obligations["pair_obligations"][0]["endpoint_records"].pop()
            elif mutation == "duplicate_pair":
                obligations["pair_obligations"].append(copy.deepcopy(obligations["pair_obligations"][0]))
            elif mutation == "axis_scope":
                obligations["cluster_obligations"][0]["axis_obligations"] = [{"axis": "physical_entity", "anonymous_proposal_ids": ["p1"],
                    "initial_target_cluster_ids": ["a"], "revision_cannot_override": False}]
            elif mutation == "decision":
                obligations["cluster_obligations"][0]["candidate_decision"] = "abstain"
            elif mutation == "missing_endpoint_obligation":
                obligations["cluster_obligations"].pop()
            else:
                before["clusters"][1].update(decision="abstain", final_entity=None)
            with self.assertRaises(M.PhysicalReviewCompletionError):
                M.validate_completion_scope(before, before, obligations)

    def test_prompt_is_deterministic_readonly_and_preserves_pixel_review_material(self):
        args = prompt_args(*unary())
        snapshot = copy.deepcopy(args)
        first = M.build_completion_prompt(**args)
        self.assertEqual(first, M.build_completion_prompt(**args))
        self.assertEqual(args, snapshot)
        material = json.loads(first.split("Source-blind review material:\n", 1)[1])
        self.assertEqual(material["candidate_complete_ledger"], args["candidate_decisions"])
        self.assertEqual(material["reviewable_cluster_ids"], ["a"])
        self.assertEqual(material["permitted_resolution_slots"], [{"cluster_id": "a", "axis": "physical_entity",
            "target_cluster_ids": ["a"], "anonymous_proposal_ids": ["p1", "p2"]}])
        self.assertEqual(material["original_verifier_reports"][1]["reviews"], args["verifier_reports"][1]["reviews"])
        proposals = material["complete_original_proposals_for_contributing_initial_scopes"]
        self.assertEqual({x["anonymous_proposal_id"] for x in proposals}, {"p1", "p2"})
        self.assertIn("Distinct outline for p1", first)
        self.assertIn("bbox_xyxy_normalized", first)
        self.assertIn("background_integrated", first)
        self.assertEqual(len(material["original_frame_mapping"]), 6)
        self.assertIn("its resolution scope stays that endpoint's own scope", first)
        for text in ("at most one", "not a format-only repair", "a new independent verifier", "Honest unresolved", "append-only", "not a final inventory"):
            self.assertIn(text, first)

    def test_source_panel_registry_structures_are_not_forwarded(self):
        args = prompt_args(*unary())
        marker = "FORBIDDEN_METADATA_SENTINEL"
        args["anonymous_view"]["detector_panels"] = [{"panel_id": marker}]
        args["anonymous_view"]["registry"] = marker
        args["candidate_decisions"]["source"] = marker
        args["candidate_decisions"]["clusters"][0]["panel_id"] = marker
        for proposal in args["anonymous_view"]["proposals"]:
            proposal["source"] = marker
            proposal["coarse_locators"][0]["source_panel"] = marker
            proposal["frame_presence"][0]["private_metadata"] = marker
        args["verifier_reports"][0]["reviews"][0]["evidence"][0]["source"] = marker
        args["obligations"]["private_provenance"] = marker
        self.assertNotIn(marker, M.build_completion_prompt(**args))

    def test_prompt_checks_full_initial_lineage_including_split_parent(self):
        initial, candidate, reports, _ = F.PhysicalIdentityReviewTests().split_fixture()
        obligations = checklist(initial, candidate, reports)
        args = prompt_args(initial, candidate, reports, obligations)
        prompt = M.build_completion_prompt(**args)
        self.assertIn("p0001", prompt)
        self.assertIn("p0002", prompt)
        for mutation in ("initial_universe", "axis_target", "initial_full_scope", "contributing_scope"):
            bad = copy.deepcopy(args)
            if mutation == "initial_universe":
                bad["initial_scope_map"]["c1"].append("unknown")
            elif mutation == "axis_target":
                bad["obligations"]["cluster_obligations"][0]["axis_obligations"][0]["initial_target_cluster_ids"] = ["unknown"]
            elif mutation == "initial_full_scope":
                bad["obligations"]["cluster_obligations"][0]["initial_targets"][0]["anonymous_proposal_ids"] = ["p0001"]
            else:
                bad["obligations"]["cluster_obligations"][0]["initial_targets"][0]["contributing_anonymous_proposal_ids"] = ["p0001", "p0002"]
            with self.assertRaises(M.PhysicalReviewCompletionError):
                M.build_completion_prompt(**bad)

    def test_prompt_pair_lineage_cannot_use_only_one_endpoint(self):
        args = prompt_args(*pair_case())
        args["obligations"]["pair_obligations"][0]["initial_target_cluster_ids"] = ["a"]
        with self.assertRaisesRegex(M.PhysicalReviewCompletionError, "complete union lineage"):
            M.build_completion_prompt(**args)

    def test_prompt_rejects_other_shot_missing_reports_proposals_or_image_mapping(self):
        for mutation in ("shot", "roster", "proposal", "frame", "path", "extra_path", "rule", "no_obligations"):
            args = prompt_args(*unary())
            if mutation == "shot":
                args["verifier_reports"][0]["shot_id"] = "another_shot"
            elif mutation == "roster":
                args["verifier_reports"].pop()
            elif mutation == "proposal":
                args["anonymous_view"]["proposals"].pop()
            elif mutation == "frame":
                args["reference_frames"][0]["frame_id"] = True
            elif mutation == "path":
                args["reference_frames"][0]["path"] = "relative.jpg"
            elif mutation == "extra_path":
                args["allowed_input_paths"].append("/different_shot.jpg")
            elif mutation == "rule":
                args["physical_identity_rule"] = ""
            else:
                args["obligations"]["cluster_obligations"] = []
            with self.assertRaises(M.PhysicalReviewCompletionError):
                M.build_completion_prompt(**args)

    def test_scope_firewall_does_not_replace_strict_evidence_validation(self):
        initial, before, _, obligations = unary()
        after = copy.deepcopy(before)
        F.resolution(after["clusters"][0], "physical_entity", ["a"], 99)
        self.assertTrue(M.validate_completion_scope(before, after, obligations)["scope_contract_valid"])
        with self.assertRaises(F.M.PhysicalIdentityContractError):
            F.M.validate_adjudication_identity_fields(
                after, valid_frame_ids=[10], expected_proposal_ids=[p for c in initial["clusters"] for p in c["anonymous_proposal_ids"]])


if __name__ == "__main__":
    unittest.main()
