"""Synthetic initial-only pending preparation tests; no models or visual claims."""

import copy
import importlib.util
import json
from pathlib import Path
import unittest

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("initial_identity_preparation_tested", ROOT / "scripts/physical_identity_review.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
SCHEMA = json.loads((ROOT / "schemas/codex_entity_adjudication_v0.6.schema.json").read_text())


def evidence(scope, cue="physical_boundary"):
    return {"frame_id": 10, "coarse_locator": "The individually localized region",
            "support_quality": "moderate", "anonymous_proposal_ids": list(scope),
            "cue_type": cue, "observation": "The cited physical content has an observable boundary."}


def cluster(key, scope, *, decision="accept"):
    return {"cluster_id": key, "anonymous_proposal_ids": list(scope), "canonical_name": "test unit",
            "aliases": [], "granularity": "individual", "adjudicator_evidence": [evidence(scope)],
            "frame_presence": [{"frame_id": 10, "status": "visible", "description": "The unit is visible."}],
            "identity_status": "resolved", "decision": decision, "decision_reason": "Scoped observation.",
            "uncertainty_flags": [], "final_entity": None if decision != "accept" else
            {"name": "test unit", "attributes": [], "entity_confidence": 0.6, "evidence_frame_ids": [10]},
            "existence_judgment": "confirmed", "salience_judgment": "graph_worthy",
            "proposal_scope_judgment": "resolved_single_scope", "category_resolution": "category_unresolved",
            "identity_comparisons": [], "revision_resolutions": []}


def pair(other, *, judgment="confirmed_distinct", indices=(0,), relation="comparable"):
    return {"other_cluster_id": other, "judgment": judgment,
            "scope_relation": relation, "evidence_indices": list(indices)}


def example():
    # A wrong own-unary reference, despite a valid reverse-direction witness.
    # The scopes and observations are synthetic and contain no experiment IDs.
    a, b = cluster("c1", ("p0001", "p0002")), cluster("c2", ("p0003",))
    a["identity_comparisons"] = [pair("c2")]
    b["adjudicator_evidence"].append(evidence(("p0001", "p0002", "p0003"), "simultaneous_separation"))
    b["identity_comparisons"] = [pair("c1", indices=(1,))]
    return {"schema_version": M.SCHEMA_VERSION, "protocol_version": M.BASE_PROTOCOL_VERSION,
            "shot_id": "synthetic", "clusters": [a, b], "warnings": []}


class InitialIdentityPreparationTests(unittest.TestCase):
    def prepare(self, value, expected=("p0001", "p0002", "p0003")):
        return M.prepare_initial_adjudication_for_review(value, [10], expected)

    def assert_fatal(self, value, expected=("p0001", "p0002", "p0003")):
        before = copy.deepcopy(value)
        with self.assertRaises(M.PhysicalIdentityContractError):
            self.prepare(value, expected)
        self.assertEqual(value, before)

    def test_wrong_unary_reference_becomes_pending_without_reverse_copy(self):
        raw = example()
        jsonschema.validate(raw, SCHEMA)
        before = copy.deepcopy(raw)
        with self.assertRaisesRegex(M.PhysicalIdentityContractError, "exact union-scope"):
            M.validate_adjudication_identity_fields(raw, valid_frame_ids=[10])
        derived, audit = self.prepare(raw)
        expected = copy.deepcopy(raw)
        expected["clusters"][0]["identity_comparisons"][0]["judgment"] = "unresolved"
        self.assertEqual(derived, expected)
        self.assertEqual(raw, before)
        jsonschema.validate(derived, SCHEMA)
        M.validate_adjudication_identity_fields(derived, valid_frame_ids=[10])
        self.assertEqual(len(derived["clusters"][0]["adjudicator_evidence"]), 1)
        self.assertEqual(audit, {
            "policy_version": M.INITIAL_PREPARATION_VERSION,
            "stage": "initial_adjudication", "visual_correction": False,
            "pending_comparisons": [{
                "json_pointer": "/clusters/0/identity_comparisons/0/judgment",
                "cluster_id_a": "c1", "cluster_id_b": "c2",
                "own_cluster_id": "c1", "other_cluster_id": "c2",
                "own_anonymous_proposal_ids": ["p0001", "p0002"],
                "other_anonymous_proposal_ids": ["p0003"],
                "union_anonymous_proposal_ids": ["p0001", "p0002", "p0003"],
                "source_judgment": "confirmed_distinct", "derived_judgment": "unresolved",
                "scope_relation": "comparable", "evidence_indices": [0],
                "reason": "confirmed_comparison_missing_exact_union_scope_identity_witness",
            }],
        })

    def test_valid_same_distinct_and_motion_witnesses_are_unchanged(self):
        for judgment, cue in (("confirmed_same_scope", "same_instance_continuity"),
                              ("confirmed_distinct", "simultaneous_separation"),
                              ("confirmed_distinct", "independent_interaction_or_trajectory")):
            with self.subTest(judgment=judgment, cue=cue):
                raw = example()
                for c in raw["clusters"]:
                    c["adjudicator_evidence"].append(evidence(("p0001", "p0002", "p0003"), cue))
                    c["identity_comparisons"][0].update(judgment=judgment, evidence_indices=[len(c["adjudicator_evidence"]) - 1])
                result, audit = self.prepare(raw)
                self.assertEqual(result, raw)
                self.assertEqual(audit["pending_comparisons"], [])

    def test_partial_union_wrong_cue_or_unreferenced_witness_stays_pending(self):
        for mode in ("partial_union", "wrong_cue", "unreferenced", "separate_observations", "same_needs_same_cue"):
            with self.subTest(mode=mode):
                raw = example()
                c = raw["clusters"][0]
                if mode == "partial_union":
                    c["adjudicator_evidence"][0] = evidence(("p0001", "p0003"), "simultaneous_separation")
                elif mode == "wrong_cue":
                    c["adjudicator_evidence"][0] = evidence(("p0001", "p0002", "p0003"), "same_instance_continuity")
                elif mode == "unreferenced":
                    c["adjudicator_evidence"].append(evidence(("p0001", "p0002", "p0003"), "simultaneous_separation"))
                elif mode == "separate_observations":
                    c["adjudicator_evidence"][0]["cue_type"] = "simultaneous_separation"
                    c["adjudicator_evidence"].append(evidence(("p0003",), "simultaneous_separation"))
                    c["identity_comparisons"][0]["evidence_indices"] = [0, 1]
                else:
                    c["identity_comparisons"][0]["judgment"] = "confirmed_same_scope"
                    c["adjudicator_evidence"][0] = evidence(("p0001", "p0002", "p0003"), "simultaneous_separation")
                result, audit = self.prepare(raw)
                self.assertEqual(result["clusters"][0]["identity_comparisons"][0]["judgment"], "unresolved")
                self.assertEqual(len(audit["pending_comparisons"]), 1)
                self.assertEqual(result["clusters"][0]["adjudicator_evidence"], c["adjudicator_evidence"])

    def test_multiple_pairs_are_all_prepared_without_inventing_reciprocals(self):
        raw = example()
        raw["clusters"].append(cluster("c3", ("p0004",)))
        raw["clusters"][0]["identity_comparisons"].append(pair("c3", judgment="confirmed_same_scope"))
        raw["clusters"][1]["identity_comparisons"][0]["evidence_indices"] = [0]
        result, audit = self.prepare(raw, ("p0001", "p0002", "p0003", "p0004"))
        self.assertEqual([(x["own_cluster_id"], x["other_cluster_id"]) for x in audit["pending_comparisons"]],
                         [("c1", "c2"), ("c1", "c3"), ("c2", "c1")])
        self.assertEqual(result["clusters"][2]["identity_comparisons"], [])

    def test_unresolved_and_noncomparable_unresolved_are_not_promoted(self):
        for relation in M.SCOPE_RELATIONS:
            with self.subTest(relation=relation):
                raw = example()
                raw["clusters"][0]["identity_comparisons"][0] = pair("c2", judgment="unresolved", indices=(), relation=relation)
                result, audit = self.prepare(raw)
                self.assertEqual(result, raw)
                self.assertEqual(audit["pending_comparisons"], [])

    def test_confirmed_reference_and_relation_errors_remain_fatal(self):
        mutations = {
            "null_indices": ("evidence_indices", None),
            "out_of_range": ("evidence_indices", [1]),
            "negative_index": ("evidence_indices", [-1]),
            "bool_index": ("evidence_indices", [True]),
            "duplicate_index": ("evidence_indices", [0, 0]),
            "unknown_partner": ("other_cluster_id", "missing"),
            "self_partner": ("other_cluster_id", "c1"),
            "unknown_judgment": ("judgment", "probably_distinct"),
            "whole_part": ("scope_relation", "whole_part"),
            "group_member": ("scope_relation", "group_member"),
            "unresolved_scope": ("scope_relation", "unresolved"),
        }
        for case, (key, value) in mutations.items():
            with self.subTest(case=case):
                raw = example()
                raw["clusters"][0]["identity_comparisons"][0][key] = value
                self.assert_fatal(raw)

    def test_missing_duplicate_scope_and_evidence_reference_errors_are_fatal(self):
        for case in ("missing_scope", "empty_scope", "duplicate_proposal", "duplicate_cluster", "missing_cluster",
                     "unknown_evidence_id", "duplicate_evidence_id", "invalid_frame", "invalid_cue", "empty_locator", "empty_observation"):
            with self.subTest(case=case):
                raw = example()
                c = raw["clusters"][1]
                if case == "missing_scope":
                    del c["anonymous_proposal_ids"]
                elif case == "empty_scope":
                    c["anonymous_proposal_ids"] = []
                elif case == "duplicate_proposal":
                    # Preserve valid evidence references and the complete
                    # universe, so only the final strict ownership check fails.
                    c["anonymous_proposal_ids"] = ["p0002", "p0003"]
                elif case == "duplicate_cluster":
                    raw["clusters"].append(copy.deepcopy(c))
                elif case == "missing_cluster":
                    raw["clusters"].pop()
                else:
                    key, value = {
                        "unknown_evidence_id": ("anonymous_proposal_ids", ["p9999"]),
                        "duplicate_evidence_id": ("anonymous_proposal_ids", ["p0003", "p0003"]),
                        "invalid_frame": ("frame_id", 11), "invalid_cue": ("cue_type", "strong"),
                        "empty_locator": ("coarse_locator", ""), "empty_observation": ("observation", " "),
                    }[case]
                    c["adjudicator_evidence"][0][key] = value
                self.assert_fatal(raw)

    def test_later_errors_cannot_be_hidden_by_first_pending_candidate(self):
        for case in ("duplicate_partner", "later_unknown_partner", "later_missing_indices", "later_out_of_range",
                     "later_invalid_axis", "wrong_schema", "incomplete_universe", "revision_resolution"):
            with self.subTest(case=case):
                raw = example()
                a, b = raw["clusters"]
                if case == "duplicate_partner":
                    a["identity_comparisons"].append(copy.deepcopy(a["identity_comparisons"][0]))
                elif case == "later_unknown_partner":
                    b["identity_comparisons"][0]["other_cluster_id"] = "missing"
                elif case == "later_missing_indices":
                    del b["identity_comparisons"][0]["evidence_indices"]
                elif case == "later_out_of_range":
                    b["identity_comparisons"][0]["evidence_indices"] = [9]
                elif case == "later_invalid_axis":
                    b["existence_judgment"] = "probably"
                elif case == "wrong_schema":
                    raw["schema_version"] = "legacy"
                elif case == "revision_resolution":
                    b["revision_resolutions"] = [{"axis": "proposal_scope", "target_cluster_ids": ["c2"],
                                                   "anonymous_proposal_ids": ["p0003"], "evidence_indices": [0]}]
                expected = ("p0001", "p0002", "p0003", "p0004") if case == "incomplete_universe" else ("p0001", "p0002", "p0003")
                self.assert_fatal(raw, expected)

    def test_accept_reject_axes_ownership_and_grouping_fields_are_unchanged(self):
        for decision in ("accept", "reject", "abstain"):
            with self.subTest(decision=decision):
                raw = example()
                c = raw["clusters"][0]
                c.update(decision=decision, granularity="compact_assembly", existence_judgment="uncertain",
                         proposal_scope_judgment="mixed_scope", identity_status="ambiguous")
                if decision != "accept":
                    c["final_entity"] = None
                expected = copy.deepcopy(raw)
                expected["clusters"][0]["identity_comparisons"][0]["judgment"] = "unresolved"
                result, _ = self.prepare(raw)
                self.assertEqual(result, expected)

    def test_name_and_order_do_not_determine_conversion(self):
        raw = example()
        baseline, audit = self.prepare(raw)
        changed = copy.deepcopy(raw)
        changed["clusters"].reverse()
        for c in changed["clusters"]:
            c["canonical_name"] = "unknown precision device"
            c["anonymous_proposal_ids"].reverse()
        result, altered_audit = self.prepare(changed)
        def judgments(value):
            return {(c["cluster_id"], p["other_cluster_id"]): p["judgment"]
                    for c in value["clusters"] for p in c["identity_comparisons"]}
        self.assertEqual(judgments(result), judgments(baseline))
        expected_row = copy.deepcopy(audit["pending_comparisons"][0])
        expected_row["json_pointer"] = "/clusters/1/identity_comparisons/0/judgment"
        self.assertEqual(altered_audit["pending_comparisons"], [expected_row])

    def test_determinism_idempotence_and_detached_mutable_state(self):
        raw = example()
        first, audit = self.prepare(raw)
        self.assertEqual(self.prepare(raw), (first, audit))
        second, second_audit = self.prepare(first)
        self.assertEqual(second, first)
        self.assertEqual(second_audit["pending_comparisons"], [])
        # A second invocation creates no conversion audit; it cannot cancel the
        # independently persisted obligations from the first invocation.
        second["clusters"][0]["adjudicator_evidence"][0]["observation"] = "changed"
        self.assertNotEqual(second, first)
        audit["pending_comparisons"][0]["evidence_indices"].append(9)
        self.assertEqual(first["clusters"][0]["identity_comparisons"][0]["evidence_indices"], [0])
        self.assertEqual(raw["clusters"][0]["identity_comparisons"][0]["judgment"], "confirmed_distinct")


if __name__ == "__main__":
    unittest.main()
