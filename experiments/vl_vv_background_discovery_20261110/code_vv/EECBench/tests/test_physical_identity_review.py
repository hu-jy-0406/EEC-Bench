"""Synthetic, no-model physical identity contract and scope-gate regressions.

The scenarios are invented; none names or encodes an experiment's target count,
location, candidate set, or desired answer. Typed cues are assumed observations,
so these tests establish software behavior and cannot establish visual accuracy.
"""

import copy
import importlib.util
import json
from pathlib import Path
import unittest

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("physical_identity_review_tested", ROOT / "scripts/physical_identity_review.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
SCHEMAS = {role: json.loads((ROOT / "schemas" / f"codex_entity_{role}_v0.6.schema.json").read_text())
           for role in ("adjudication", "verification")}


def evidence(scope, cue="physical_boundary", observation="A closed outline separates the claimed unit from its support."):
    return {"frame_id": 10, "coarse_locator": "At the independently localized claimed region",
            "support_quality": "moderate", "anonymous_proposal_ids": list(scope),
            "cue_type": cue, "observation": observation}


def cluster(key="c1", scope=("p0001",), *, name="bounded object", decision="accept"):
    return {"cluster_id": key, "anonymous_proposal_ids": list(scope), "canonical_name": name,
            "aliases": [], "granularity": "individual", "adjudicator_evidence": [evidence(scope)],
            "frame_presence": [{"frame_id": 10, "status": "visible", "description": "The claimed unit is visible."}],
            "identity_status": "resolved", "decision": decision,
            "decision_reason": "Direct scoped observation.", "uncertainty_flags": [],
            "final_entity": {"name": name, "attributes": [], "entity_confidence": 0.6, "evidence_frame_ids": [10]}
                            if decision == "accept" else None,
            "existence_judgment": "confirmed", "salience_judgment": "graph_worthy",
            "proposal_scope_judgment": "resolved_single_scope", "category_resolution": "resolved",
            "identity_comparisons": [], "revision_resolutions": []}


def ledger(*clusters):
    return {"schema_version": M.SCHEMA_VERSION, "protocol_version": M.BASE_PROTOCOL_VERSION,
            "shot_id": "synthetic", "clusters": list(clusters), "warnings": []}


def review(c):
    return {"cluster_id": c["cluster_id"], "existence_judgment": c["existence_judgment"],
            "salience_judgment": c["salience_judgment"],
            "proposal_scope_judgment": c["proposal_scope_judgment"],
            "category_resolution": c["category_resolution"],
            "same_instance_with_cluster_ids": [], "graph_partition_judgment": "keep_as_separate_node",
            "same_graph_node_with_cluster_ids": [], "observed_independence_evidence": [],
            "intra_cluster_split_judgment": "not_reviewed", "proposed_physical_units": [],
            "pairwise_physical_separation_evidence": [], "evidence": copy.deepcopy(c["adjudicator_evidence"]),
            "identity_comparisons": [], "reason": "Direct scoped observation."}


def report(verifier, *reviews):
    return {"schema_version": M.SCHEMA_VERSION, "protocol_version": M.BASE_PROTOCOL_VERSION,
            "shot_id": "synthetic", "verifier_id": verifier, "reviews": list(reviews), "warnings": []}


def two_reports(*clusters):
    return [report(v, *(review(c) for c in clusters)) for v in ("verifier_1", "verifier_2")]


def comparison(record, other, union, judgment, *, evidence_key="evidence", relation="comparable"):
    indices = []
    if judgment != "unresolved":
        cue = "same_instance_continuity" if judgment == "confirmed_same_scope" else "simultaneous_separation"
        indices = [len(record[evidence_key])]
        record[evidence_key].append(evidence(union, cue, "Both claimed scopes are directly localized and their physical correspondence is visible."))
    record["identity_comparisons"].append({"other_cluster_id": other, "judgment": judgment,
                                            "scope_relation": relation, "evidence_indices": indices})
    if "same_instance_with_cluster_ids" in record:
        record["same_instance_with_cluster_ids"] = M.confirmed_same_scope_ids(record["identity_comparisons"])


def resolution(c, axis, targets, index=0):
    c["revision_resolutions"].append({"axis": axis, "target_cluster_ids": list(targets),
                                        "anonymous_proposal_ids": list(c["anonymous_proposal_ids"]),
                                        "evidence_indices": [index]})


class PhysicalIdentityReviewTests(unittest.TestCase):
    def gate(self, initial, final=None, reports=None, reasons=None, consensus=None):
        if final is None:
            final = copy.deepcopy(initial)
        if reports is None:
            reports = two_reports(*initial["clusters"])
        if reasons is None:
            reasons = {c["cluster_id"]: ["synthetic_review"] for c in initial["clusters"]}
        return M.apply_physical_identity_gate(final, initial_decisions=initial,
                                              verifier_reports=reports, verification_target_reasons=reasons,
                                              intra_cluster_split_consensus=consensus)

    def validate_reports(self, reports, initial, pairs=()):
        scope_map = {c["cluster_id"]: c["anonymous_proposal_ids"] for c in initial["clusters"]}
        for r in reports:
            jsonschema.validate(r, SCHEMAS["verification"])
            M.validate_verifier_identity_fields(r, target_proposal_ids_by_cluster=scope_map,
                                                identity_challenge_pairs=pairs, valid_frame_ids=[10])

    def test_eight_general_physical_cases(self):
        # Static unknowns and action-supported fragments can pass; a name cannot
        # rescue unresolved physical scope or a clearly integrated component.
        scenarios = [
            ("sealed laboratory instrument", "category_unresolved", "confirmed", "graph_worthy", "resolved_single_scope", "physical_boundary", "accept"),
            ("distant bollard", "subtype_unresolved", "confirmed", "graph_worthy", "resolved_single_scope", "physical_boundary", "accept"),
            ("bag-like shadow", "resolved", "uncertain", "ambiguous", "unresolved", "unresolved", "abstain"),
            ("transparent chip being picked up", "category_unresolved", "confirmed", "graph_worthy", "resolved_single_scope", "direct_interaction", "accept"),
            ("one suitcase with alternate names", "subtype_unresolved", "confirmed", "graph_worthy", "resolved_single_scope", "temporal_continuity", "accept"),
            ("two hose reels incorrectly in one scope", "resolved", "confirmed", "graph_worthy", "mixed_scope", "physical_boundary", "abstain"),
            ("crate appearances with unobserved continuity", "resolved", "confirmed", "graph_worthy", "unresolved", "physical_boundary", "abstain"),
            ("molded dashboard vent", "resolved", "confirmed", "background_integrated", "resolved_single_scope", "integrated_component", "abstain"),
        ]
        for name, category, exists, salience, scope_state, cue, expected in scenarios:
            with self.subTest(name=name):
                c = cluster(name=name)
                c.update(category_resolution=category, existence_judgment=exists,
                         salience_judgment=salience, proposal_scope_judgment=scope_state)
                c["adjudicator_evidence"][0]["cue_type"] = cue
                initial = ledger(c)
                reports = two_reports(c)
                jsonschema.validate(initial, SCHEMAS["adjudication"])
                M.validate_adjudication_identity_fields(initial, valid_frame_ids=[10], expected_proposal_ids=["p0001"])
                self.validate_reports(reports, initial)
                gated, _ = self.gate(initial, reports=reports)
                self.assertEqual(gated["clusters"][0]["decision"], expected)

    def test_name_category_flags_confidence_and_support_rating_do_not_change_gate(self):
        for physical in (True, False):
            initial = ledger(cluster())
            if not physical:
                initial["clusters"][0]["existence_judgment"] = "uncertain"
                initial["clusters"][0]["adjudicator_evidence"][0]["cue_type"] = "unresolved"
            baseline, _ = self.gate(initial)
            for name in ("object", "precision spectrometer", "unknown assembly", "exact taxonomy"):
                altered = copy.deepcopy(initial)
                c = altered["clusters"][0]
                c["canonical_name"] = c["final_entity"]["name"] = name
                c["category_resolution"] = "category_unresolved"
                c["uncertainty_flags"] = ["unknown_subtype", "very_strong_confidence"]
                c["final_entity"]["entity_confidence"] = 1.0
                c["adjudicator_evidence"][0]["support_quality"] = "weak"
                result, audit = self.gate(altered)
                self.assertEqual(result["clusters"][0]["decision"], baseline["clusters"][0]["decision"])
                self.assertFalse(audit["support_quality_used"])
                self.assertFalse(audit["name_or_category_used"])

    def test_honest_uncertain_alias_is_valid_and_never_projected(self):
        a, b = cluster(), cluster("c2", ("p0002",))
        reports = two_reports(a, b)
        pairs = [{"cluster_id_a": "c1", "cluster_id_b": "c2"}]
        for r in reports:
            for own, other in ((r["reviews"][0], "c2"), (r["reviews"][1], "c1")):
                comparison(own, other, ("p0001", "p0002"), "unresolved")
        self.validate_reports(reports, ledger(a, b), pairs)
        self.assertEqual(reports[0]["reviews"][0]["same_instance_with_cluster_ids"], [])
        result, _ = self.gate(ledger(a, b), reports=reports)
        self.assertEqual([c["decision"] for c in result["clusters"]], ["abstain", "abstain"])
        reports[0]["reviews"][0]["same_instance_with_cluster_ids"] = ["c2"]
        with self.assertRaisesRegex(M.PhysicalIdentityContractError, "exactly project"):
            self.validate_reports(reports, ledger(a, b), pairs)

    def test_confirmed_distinct_preserves_two_identical_units(self):
        a, b = cluster(name="hose reel"), cluster("c2", ("p0002",), name="hose reel")
        reports = two_reports(a, b)
        for r in reports:
            comparison(r["reviews"][0], "c2", ("p0001", "p0002"), "confirmed_distinct")
            comparison(r["reviews"][1], "c1", ("p0001", "p0002"), "confirmed_distinct")
        self.validate_reports(reports, ledger(a, b))
        result, _ = self.gate(ledger(a, b), reports=reports)
        self.assertEqual([c["decision"] for c in result["clusters"]], ["accept", "accept"])

    def test_positive_alias_merge_requires_same_scope_not_absence_of_distinctness(self):
        a, b = cluster(), cluster("c2", ("p0002",))
        merged = ledger(cluster("merged", ("p0001", "p0002")))
        reports = two_reports(a, b)
        result, _ = self.gate(ledger(a, b), merged, reports)
        self.assertEqual(result["clusters"][0]["decision"], "abstain")
        for r in reports:
            comparison(r["reviews"][0], "c2", ("p0001", "p0002"), "confirmed_same_scope")
            comparison(r["reviews"][1], "c1", ("p0001", "p0002"), "confirmed_same_scope")
        self.validate_reports(reports, ledger(a, b))
        result, _ = self.gate(ledger(a, b), merged, reports)
        self.assertEqual(result["clusters"][0]["decision"], "accept")
        # The same proof cannot leave both aliases accepted as distinct units.
        result, _ = self.gate(ledger(a, b), reports=reports)
        self.assertEqual([c["decision"] for c in result["clusters"]], ["abstain", "abstain"])

    def test_incomplete_transparent_unit_is_distinct_by_direct_independent_motion(self):
        a, b = cluster(name="transparent unit"), cluster("c2", ("p0002",), name="transparent unit")
        for c in (a, b):
            c["category_resolution"] = "category_unresolved"
            c["adjudicator_evidence"][0]["cue_type"] = "direct_interaction"
            c["adjudicator_evidence"][0]["observation"] = "Handling localizes the unit despite an incomplete transparent edge."
        reports = two_reports(a, b)
        for r in reports:
            for own, other in ((r["reviews"][0], "c2"), (r["reviews"][1], "c1")):
                comparison(own, other, ("p0001", "p0002"), "confirmed_distinct")
                own["evidence"][-1].update(cue_type="independent_interaction_or_trajectory",
                                           observation="The gripped chip rises while the second chip remains on its support, proving two localized physical units despite incomplete edges.")
        self.validate_reports(reports, ledger(a, b))
        result, _ = self.gate(ledger(a, b), reports=reports)
        self.assertEqual([c["decision"] for c in result["clusters"]], ["accept", "accept"])
        # Ordinary continuity is not an independent-identity witness.
        reports[0]["reviews"][0]["evidence"][-1].update(cue_type="temporal_continuity",
                                                       observation="The camera shifts and both proposal descriptions follow one visible track.")
        with self.assertRaisesRegex(M.PhysicalIdentityContractError, "direct identity evidence"):
            self.validate_reports(reports, ledger(a, b))

    def test_whole_part_is_not_same_scope_alias(self):
        a, b = cluster(), cluster("c2", ("p0002",))
        reports = two_reports(a, b)
        for r in reports:
            comparison(r["reviews"][0], "c2", (), "unresolved", relation="whole_part")
            comparison(r["reviews"][1], "c1", (), "unresolved", relation="whole_part")
        self.validate_reports(reports, ledger(a, b))
        result, _ = self.gate(ledger(a, b), ledger(cluster("merged", ("p0001", "p0002"))), reports)
        self.assertEqual(result["clusters"][0]["decision"], "abstain")
        reports[0]["reviews"][0]["identity_comparisons"][0]["judgment"] = "confirmed_same_scope"
        reports[0]["reviews"][0]["identity_comparisons"][0]["evidence_indices"] = [0]
        with self.assertRaisesRegex(M.PhysicalIdentityContractError, "cannot assert"):
            self.validate_reports(reports, ledger(a, b))

    def test_bad_evidence_references_fail_validation(self):
        c = cluster()
        cases = [
            ("frame", lambda x: x["adjudicator_evidence"][0].update(frame_id=999)),
            ("proposal", lambda x: x["adjudicator_evidence"][0].update(anonymous_proposal_ids=["p9999"])),
            ("index", lambda x: resolution(x, "physical_entity", ["c1"], 3)),
            ("bool index", lambda x: resolution(x, "physical_entity", ["c1"], True)),
            ("empty observation", lambda x: x["adjudicator_evidence"][0].update(observation=" ")),
        ]
        for name, mutate in cases:
            with self.subTest(name=name):
                altered = copy.deepcopy(c)
                mutate(altered)
                with self.assertRaises(M.PhysicalIdentityContractError):
                    M.validate_adjudication_identity_fields(ledger(altered), valid_frame_ids=[10])

    def test_confirmed_comparison_needs_both_complete_scopes(self):
        a, b = cluster(), cluster("c2", ("p0002", "p0003"))
        reports = two_reports(a, b)
        comparison(reports[0]["reviews"][0], "c2", ("p0001", "p0002"), "confirmed_distinct")
        with self.assertRaisesRegex(M.PhysicalIdentityContractError, "exact union-scope"):
            self.validate_reports(reports, ledger(a, b))

    def test_every_challenge_partner_is_required(self):
        a, b = cluster(), cluster("c2", ("p0002",))
        with self.assertRaisesRegex(M.PhysicalIdentityContractError, "Missing challenge"):
            self.validate_reports(two_reports(a, b), ledger(a, b), [{"cluster_id_a": "c1", "cluster_id_b": "c2"}])

    def test_revision_can_resolve_disagreement_with_specific_axis_scope_and_cue(self):
        initial = ledger(cluster())
        reports = two_reports(*initial["clusters"])
        reports[1]["reviews"][0].update(existence_judgment="uncertain", proposal_scope_judgment="unresolved")
        result, _ = self.gate(initial, reports=reports)
        self.assertEqual(result["clusters"][0]["decision"], "abstain")
        final = copy.deepcopy(initial)
        c = final["clusters"][0]
        resolution(c, "physical_entity", ["c1"])
        resolution(c, "proposal_scope", ["c1"])
        result, audit = self.gate(initial, final, reports)
        self.assertEqual(result["clusters"][0]["decision"], "accept")
        self.assertEqual(audit["records"][0]["revision_resolutions_used"], ["physical_entity", "proposal_scope"])
        c["adjudicator_evidence"][0]["cue_type"] = "category_only"
        c["adjudicator_evidence"][0]["support_quality"] = "strong"
        c["adjudicator_evidence"][0]["observation"] = "Very confident in the specific label."
        result, _ = self.gate(initial, final, reports)
        self.assertEqual(result["clusters"][0]["decision"], "abstain")

    def test_revision_resolution_cannot_use_wrong_scope_or_wrong_targets(self):
        initial = ledger(cluster())
        reports = two_reports(*initial["clusters"])
        reports[1]["reviews"][0]["existence_judgment"] = "uncertain"
        for mutation in ("wrong_target", "wrong_scope"):
            final = copy.deepcopy(initial)
            c = final["clusters"][0]
            resolution(c, "physical_entity", ["c999"] if mutation == "wrong_target" else ["c1"])
            if mutation == "wrong_scope":
                c["revision_resolutions"][0]["anonymous_proposal_ids"] = ["p0002"]
            result, _ = self.gate(initial, final, reports)
            self.assertEqual(result["clusters"][0]["decision"], "abstain")

    def test_missing_reviews_need_both_resolutions_not_a_strong_name(self):
        initial = ledger(cluster())
        final = copy.deepcopy(initial)
        result, _ = self.gate(initial, final, reports=[])
        self.assertEqual(result["clusters"][0]["decision"], "abstain")
        c = final["clusters"][0]
        resolution(c, "physical_entity", ["c1"])
        result, _ = self.gate(initial, final, reports=[])
        self.assertEqual(result["clusters"][0]["decision"], "abstain")
        resolution(c, "proposal_scope", ["c1"])
        result, _ = self.gate(initial, final, reports=[])
        self.assertEqual(result["clusters"][0]["decision"], "accept")

    def test_unreviewed_clear_anchor_is_preserved_but_new_accept_requires_resolution(self):
        initial = ledger(cluster())
        result, _ = self.gate(initial, reports=[], reasons={})
        self.assertEqual(result["clusters"][0]["decision"], "accept")
        initial["clusters"][0].update(decision="abstain", final_entity=None)
        final = ledger(cluster())
        result, _ = self.gate(initial, final, reports=[], reasons={})
        self.assertEqual(result["clusters"][0]["decision"], "abstain")
        for axis in ("physical_entity", "proposal_scope"):
            resolution(final["clusters"][0], axis, ["c1"])
        result, _ = self.gate(initial, final, reports=[], reasons={})
        self.assertEqual(result["clusters"][0]["decision"], "accept")

    def test_reviewed_anchor_does_not_launder_unreviewed_new_merge_member(self):
        a, b = cluster(), cluster("c2", ("p0002",), decision="abstain")
        final = ledger(cluster("merged", ("p0001", "p0002")))
        merged = final["clusters"][0]
        merged["adjudicator_evidence"].append(evidence(("p0001", "p0002"), "same_instance_continuity"))
        resolution(merged, "instance_correspondence", ["c1", "c2"], 1)
        result, audit = self.gate(ledger(a, b), final, two_reports(a), {"c1": ["review"]})
        self.assertEqual(result["clusters"][0]["decision"], "abstain")
        self.assertIn("physical_entity:missing_exact_scope_revision_resolution", audit["records"][0]["failure_reasons"])
        for axis in ("physical_entity", "proposal_scope"):
            resolution(merged, axis, ["c1", "c2"])
        result, _ = self.gate(ledger(a, b), final, two_reports(a), {"c1": ["review"]})
        self.assertEqual(result["clusters"][0]["decision"], "accept")

    def split_fixture(self):
        parent = cluster("c1", ("p0001", "p0002", "p0003"))
        units = [cluster("u1", ("p0001",)), cluster("u2", ("p0002", "p0003"))]
        reports = two_reports(parent)
        for r in reports:
            row = r["reviews"][0]
            row["intra_cluster_split_judgment"] = "split_into_multiple_physical_instances"
            row["proposal_scope_judgment"] = "mixed_scope"
            row["proposed_physical_units"] = [
                {"unit_id": u["cluster_id"], "anonymous_proposal_ids": u["anonymous_proposal_ids"],
                 "existence_judgment": "confirmed", "salience_judgment": "graph_worthy",
                 "proposal_scope_judgment": "resolved_single_scope", "category_resolution": "resolved",
                 "evidence": copy.deepcopy(u["adjudicator_evidence"])} for u in units]
            row["pairwise_physical_separation_evidence"] = [
                {"unit_id_a": "u1", "unit_id_b": "u2", "frame_id": 10,
                 "unit_a_coarse_locator": "One independent boundary", "unit_b_coarse_locator": "The other independent boundary",
                 "support_quality": "moderate"}]
        consensus = {"exact_consensus_partitions": [{"cluster_id": "c1", "proposal_partition": [["p0001"], ["p0002", "p0003"]]}]}
        return ledger(parent), ledger(*units), reports, consensus

    def test_exact_split_units_pass_but_parent_evidence_never_confirms_child(self):
        initial, final, reports, consensus = self.split_fixture()
        self.validate_reports(reports, initial)
        result, _ = self.gate(initial, final, reports, consensus=consensus)
        self.assertEqual([c["decision"] for c in result["clusters"]], ["accept", "accept"])
        reports[1]["reviews"][0]["proposed_physical_units"][0]["evidence"] = copy.deepcopy(initial["clusters"][0]["adjudicator_evidence"])
        with self.assertRaisesRegex(M.PhysicalIdentityContractError, "outside its allowed scope"):
            self.validate_reports(reports, initial)
        for axis in ("physical_entity", "proposal_scope"):
            resolution(final["clusters"][0], axis, ["c1"])
        result, audit = self.gate(initial, final, reports, consensus=consensus)
        self.assertEqual(result["clusters"][0]["decision"], "abstain")
        self.assertTrue(audit["records"][0]["exact_split_firewall_failed"])

    def test_wrong_or_missing_exact_split_partition_is_closed(self):
        initial, final, reports, consensus = self.split_fixture()
        result, _ = self.gate(initial, final, reports)
        self.assertEqual([c["decision"] for c in result["clusters"]], ["abstain", "abstain"])
        reports[1]["reviews"][0]["proposed_physical_units"][1]["anonymous_proposal_ids"] = ["p0002"]
        result, _ = self.gate(initial, final, reports, consensus=consensus)
        self.assertEqual([c["decision"] for c in result["clusters"]], ["abstain", "abstain"])

    def test_revision_resolves_retained_pair_only_with_pair_scope_and_axis(self):
        a, b = cluster(), cluster("c2", ("p0002",))
        reports = two_reports(a, b)
        for r in reports:
            comparison(r["reviews"][0], "c2", (), "unresolved")
            comparison(r["reviews"][1], "c1", (), "unresolved")
        final = ledger(copy.deepcopy(a), copy.deepcopy(b))
        for own, other in ((final["clusters"][0], "c2"), (final["clusters"][1], "c1")):
            comparison(own, other, ("p0001", "p0002"), "confirmed_distinct", evidence_key="adjudicator_evidence")
            resolution(own, "instance_correspondence", ["c1", "c2"], 1)
        M.validate_adjudication_identity_fields(final, valid_frame_ids=[10])
        result, _ = self.gate(ledger(a, b), final, reports)
        self.assertEqual([c["decision"] for c in result["clusters"]], ["accept", "accept"])
        final["clusters"][0]["revision_resolutions"][0]["target_cluster_ids"] = ["c1"]
        result, audit = self.gate(ledger(a, b), final, reports)
        self.assertEqual([c["decision"] for c in result["clusters"]], ["accept", "accept"])
        self.assertTrue(all(r["identity_pair_judgments"][0]["revision_distinct_proof"]["source_cluster_id"] == "c2"
                            for r in audit["records"]))
        final["clusters"][1]["revision_resolutions"][0]["target_cluster_ids"] = ["c2"]
        result, _ = self.gate(ledger(a, b), final, reports)
        self.assertEqual([c["decision"] for c in result["clusters"]], ["abstain", "abstain"])

    def test_rejected_alternative_does_not_delete_supported_anchor(self):
        a, b = cluster(), cluster("c2", ("p0002",), decision="reject")
        reports = two_reports(a, b)
        for r in reports:
            comparison(r["reviews"][0], "c2", (), "unresolved")
            comparison(r["reviews"][1], "c1", (), "unresolved")
        result, _ = self.gate(ledger(a, b), reports=reports)
        self.assertEqual([c["decision"] for c in result["clusters"]], ["accept", "reject"])

    def test_unary_failed_alternative_does_not_delete_supported_anchor_in_either_order(self):
        a, b = cluster(), cluster("c2", ("p0002",))
        b["existence_judgment"] = "uncertain"
        b["adjudicator_evidence"][0]["cue_type"] = "unresolved"
        reports = two_reports(a, b)
        for r in reports:
            comparison(r["reviews"][0], "c2", (), "unresolved")
            comparison(r["reviews"][1], "c1", (), "unresolved")
        for order in ((a, b), (b, a)):
            result, _ = self.gate(ledger(*order), reports=reports)
            self.assertEqual({c["cluster_id"]: c["decision"] for c in result["clusters"]},
                             {"c1": "accept", "c2": "abstain"})

    def test_transitive_alias_chain_does_not_erase_explicit_distinct_or_unresolved_pair(self):
        a, b, c = cluster(), cluster("c2", ("p0002",)), cluster("c3", ("p0003",))
        initial = ledger(a, b, c)
        for conflict in ("confirmed_distinct", "unresolved"):
            reports = two_reports(a, b, c)
            for r in reports:
                rows = r["reviews"]
                for left, right in ((0, 1), (1, 2)):
                    union = tuple(initial["clusters"][left]["anonymous_proposal_ids"] + initial["clusters"][right]["anonymous_proposal_ids"])
                    comparison(rows[left], rows[right]["cluster_id"], union, "confirmed_same_scope")
                    comparison(rows[right], rows[left]["cluster_id"], union, "confirmed_same_scope")
                comparison(rows[0], "c3", ("p0001", "p0003"), conflict)
                comparison(rows[2], "c1", ("p0001", "p0003"), conflict)
            self.validate_reports(reports, initial)
            merged = ledger(cluster("merged", ("p0001", "p0002", "p0003")))
            result, _ = self.gate(initial, merged, reports)
            self.assertEqual(result["clusters"][0]["decision"], "abstain")
            merged["clusters"][0]["adjudicator_evidence"].append(evidence(("p0001", "p0002", "p0003"), "same_instance_continuity"))
            resolution(merged["clusters"][0], "instance_correspondence", ["c1", "c2", "c3"], 1)
            result, _ = self.gate(initial, merged, reports)
            self.assertEqual(result["clusters"][0]["decision"], "accept")

    def test_unreviewed_ledger_identity_risk_is_not_silently_accepted(self):
        a, b = cluster(), cluster("c2", ("p0002",))
        comparison(a, "c2", (), "unresolved", evidence_key="adjudicator_evidence")
        comparison(b, "c1", (), "unresolved", evidence_key="adjudicator_evidence")
        result, _ = self.gate(ledger(a, b), reports=[], reasons={})
        self.assertEqual([c["decision"] for c in result["clusters"]], ["abstain", "abstain"])

    def test_unreviewed_initial_pair_with_direct_distinct_evidence_is_preserved(self):
        a, b = cluster(), cluster("c2", ("p0002",))
        comparison(a, "c2", ("p0001", "p0002"), "confirmed_distinct", evidence_key="adjudicator_evidence")
        comparison(b, "c1", ("p0001", "p0002"), "confirmed_distinct", evidence_key="adjudicator_evidence")
        result, _ = self.gate(ledger(a, b), reports=[], reasons={})
        self.assertEqual([c["decision"] for c in result["clusters"]], ["accept", "accept"])

    def test_prior_distinct_reviews_do_not_override_final_same_or_unresolved_identity(self):
        a, b = cluster(), cluster("c2", ("p0002",))
        initial = ledger(a, b)
        reports = two_reports(a, b)
        for r in reports:
            comparison(r["reviews"][0], "c2", ("p0001", "p0002"), "confirmed_distinct")
            comparison(r["reviews"][1], "c1", ("p0001", "p0002"), "confirmed_distinct")
        for judgment in ("confirmed_same_scope", "unresolved"):
            final = copy.deepcopy(initial)
            # Even a one-sided new ambiguity must not be overwritten by earlier
            # verifier distinctness or by the other final node's confident name.
            comparison(final["clusters"][0], "c2", ("p0001", "p0002"), judgment,
                       evidence_key="adjudicator_evidence")
            M.validate_adjudication_identity_fields(final, valid_frame_ids=[10])
            result, _ = self.gate(initial, final, reports)
            self.assertEqual([c["decision"] for c in result["clusters"]], ["abstain", "abstain"])

    def test_prior_noncomparable_reviews_cannot_bypass_final_comparable_identity(self):
        a, b = cluster(), cluster("c2", ("p0002",))
        initial = ledger(a, b)
        for relation in ("whole_part", "group_member"):
            reports = two_reports(a, b)
            for r in reports:
                comparison(r["reviews"][0], "c2", (), "unresolved", relation=relation)
                comparison(r["reviews"][1], "c1", (), "unresolved", relation=relation)
            self.validate_reports(reports, initial)
            for judgment in ("confirmed_same_scope", "unresolved", "confirmed_distinct"):
                final = copy.deepcopy(initial)
                for own, other in ((final["clusters"][0], "c2"), (final["clusters"][1], "c1")):
                    comparison(own, other, ("p0001", "p0002"), judgment,
                               evidence_key="adjudicator_evidence")
                M.validate_adjudication_identity_fields(final, valid_frame_ids=[10])
                result, _ = self.gate(initial, final, reports)
                self.assertEqual([c["decision"] for c in result["clusters"]], ["abstain", "abstain"])
                if judgment == "confirmed_distinct":
                    for own in final["clusters"]:
                        resolution(own, "instance_correspondence", ["c1", "c2"], 1)
                    result, _ = self.gate(initial, final, reports)
                    self.assertEqual([c["decision"] for c in result["clusters"]], ["accept", "accept"])

    def test_gate_is_order_invariant_and_does_not_mutate_input(self):
        initial = ledger(cluster(), cluster("c2", ("p0002",)))
        final = copy.deepcopy(initial)
        reports = two_reports(*initial["clusters"])
        for r in reports:
            comparison(r["reviews"][0], "c2", (), "unresolved")
            comparison(r["reviews"][1], "c1", (), "unresolved")
        before = copy.deepcopy((initial, final, reports))
        result, _ = self.gate(initial, final, reports)
        self.assertEqual((initial, final, reports), before)
        final["clusters"].reverse()
        reversed_result, _ = self.gate(initial, final, list(reversed(reports)))
        self.assertEqual({c["cluster_id"]: c["decision"] for c in result["clusters"]},
                         {c["cluster_id"]: c["decision"] for c in reversed_result["clusters"]})

    def test_duplicate_verifier_cannot_supply_two_independent_votes(self):
        initial = ledger(cluster())
        r = two_reports(*initial["clusters"])[0]
        with self.assertRaisesRegex(M.PhysicalIdentityContractError, "duplicate"):
            self.gate(initial, reports=[r, copy.deepcopy(r)])

    def test_schema_versions_and_verifier_only_prompt(self):
        for schema in SCHEMAS.values():
            jsonschema.Draft202012Validator.check_schema(schema)
        prompt = M.build_verifier_prompt(shot_id="synthetic", verifier_id="verifier_1",
                                        verification_view={"targets": [], "cluster_index": [],
                                                           "identity_challenge_pairs": [],
                                                           "intra_cluster_divergent_footprint_challenges": []},
                                        valid_frame_ids=[10], reference_frames=[{"frame_id": 10, "path": "/synthetic.jpg"}],
                                        allowed_input_paths=["/synthetic.jpg"])
        self.assertIn(M.SCHEMA_VERSION, prompt)
        self.assertIn("Failure to observe two separate objects does not prove one object", prompt)
        self.assertNotIn("all-entity inventory stage", prompt)
        self.assertNotIn("fixed detector_1 through detector_4", prompt)
        with self.assertRaises(M.PhysicalIdentityContractError):
            M.build_verifier_prompt(shot_id="synthetic", verifier_id="verifier_1",
                                    verification_view={"final_answers": []}, valid_frame_ids=[10],
                                    reference_frames=[], allowed_input_paths=[])

    def test_transport_schemas_omit_api_rejected_unique_items_keyword(self):
        # Actual API failure: invalid_json_schema at anonymous_proposal_ids,
        # because uniqueItems is not in the supported transport-schema dialect.
        # Draft202012Validator.check_schema alone does not detect that mismatch.
        def rejected_paths(value, path=()):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key == "uniqueItems":
                        yield "/".join((*path, key))
                    yield from rejected_paths(child, (*path, key))
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    yield from rejected_paths(child, (*path, str(index)))

        for role, schema in SCHEMAS.items():
            with self.subTest(role=role):
                self.assertEqual(list(rejected_paths(schema)), [])

    def test_all_transport_unique_arrays_remain_strict_runtime_constraints(self):
        # Every one of the seven removed schema keywords remains enforced by the
        # local extension validator, including both evidence-ID and index arrays.
        a, b = cluster(), cluster("c2", ("p0002",))
        comparison(a, "c2", ("p0001", "p0002"), "confirmed_distinct",
                   evidence_key="adjudicator_evidence")
        resolution(a, "physical_entity", ["c1"])
        adjudication = ledger(a, b)
        ra, rb = review(cluster()), review(b)
        comparison(ra, "c2", ("p0001", "p0002"), "confirmed_distinct")
        verification = report("verifier_1", ra, rb)
        cases = [
            ("adjudication", ("clusters", 0, "adjudicator_evidence", 0, "anonymous_proposal_ids")),
            ("adjudication", ("clusters", 0, "identity_comparisons", 0, "evidence_indices")),
            ("adjudication", ("clusters", 0, "revision_resolutions", 0, "target_cluster_ids")),
            ("adjudication", ("clusters", 0, "revision_resolutions", 0, "anonymous_proposal_ids")),
            ("adjudication", ("clusters", 0, "revision_resolutions", 0, "evidence_indices")),
            ("verification", ("reviews", 0, "evidence", 0, "anonymous_proposal_ids")),
            ("verification", ("reviews", 0, "identity_comparisons", 0, "evidence_indices")),
        ]

        def validate_runtime(role, payload):
            if role == "adjudication":
                M.validate_adjudication_identity_fields(payload, valid_frame_ids=[10],
                                                        expected_proposal_ids=["p0001", "p0002"])
            else:
                M.validate_verifier_identity_fields(payload,
                    target_proposal_ids_by_cluster={"c1": ["p0001"], "c2": ["p0002"]},
                    identity_challenge_pairs=[], valid_frame_ids=[10])

        originals = {"adjudication": adjudication, "verification": verification}
        for role, path in cases:
            with self.subTest(role=role, path=path):
                payload = copy.deepcopy(originals[role])
                jsonschema.validate(payload, SCHEMAS[role])
                validate_runtime(role, payload)
                array = payload
                for key in path:
                    array = array[key]
                array.append(array[0])
                # Transport is deliberately permissive for this keyword; runtime
                # must reject, rather than silently deduplicating with a set.
                jsonschema.validate(payload, SCHEMAS[role])
                with self.assertRaisesRegex(M.PhysicalIdentityContractError, "unique"):
                    validate_runtime(role, payload)

    def test_shared_evidence_scope_uniqueness_in_units_and_independence_records(self):
        initial, _, reports, _ = self.split_fixture()
        for location in ("physical_unit", "observed_independence_evidence"):
            payload = copy.deepcopy(reports[0])
            row = payload["reviews"][0]
            if location == "physical_unit":
                array = row["proposed_physical_units"][0]["evidence"][0]["anonymous_proposal_ids"]
            else:
                row["observed_independence_evidence"] = [evidence(("p0001",))]
                array = row["observed_independence_evidence"][0]["anonymous_proposal_ids"]
            array.append(array[0])
            jsonschema.validate(payload, SCHEMAS["verification"])
            with self.subTest(location=location):
                with self.assertRaisesRegex(M.PhysicalIdentityContractError, "unique"):
                    self.validate_reports([payload], initial)


if __name__ == "__main__":
    unittest.main()
