"""Synthetic initial context projection tests, with no models or pixel labels."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
import initial_context_quarantine as M  # noqa: E402

SPEC = importlib.util.spec_from_file_location(
    "quarantine_fixtures", Path(__file__).with_name("test_physical_identity_review.py"))
F = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(F)


def three_scopes():
    raw = F.ledger(F.cluster("a", ["p0001", "p0002"]), F.cluster("b", ["p0003", "p0004"]),
                   F.cluster("c", ["p0005"]), F.cluster("d", ["p0006"]))
    union = [p for row in raw["clusters"][:3] for p in row["anonymous_proposal_ids"]]
    for row in raw["clusters"][:3]:
        row["adjudicator_evidence"].append(F.evidence(union, "simultaneous_separation", "A broad three-scope contextual observation."))
    a, b, c, _ = raw["clusters"]
    F.comparison(a, "b", a["anonymous_proposal_ids"] + b["anonymous_proposal_ids"],
                 "confirmed_distinct", evidence_key="adjudicator_evidence")
    for row, partner in ((b, "c"), (c, "a"), (c, "b")):
        row["identity_comparisons"].append({"other_cluster_id": partner, "judgment": "unresolved",
                                            "scope_relation": "group_member", "evidence_indices": [1]})
    return raw


def universe(raw):
    return [pid for cluster in raw["clusters"] for pid in cluster["anonymous_proposal_ids"]]


def project(raw, expected=None):
    return M.project_initial_context(raw, [10], universe(raw) if expected is None else expected)


def content_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class InitialContextQuarantineTests(unittest.TestCase):
    def test_all_eligible_owners_are_projected_with_complete_reversible_sidecar(self):
        raw = three_scopes()
        original = copy.deepcopy(raw)
        jsonschema.validate(raw, F.SCHEMAS["adjudication"])
        with self.assertRaisesRegex(ValueError, "outside its allowed scope"):
            F.M.validate_adjudication_identity_fields(raw, valid_frame_ids=[10])
        projected, audit = project(raw)
        self.assertEqual(raw, original)
        self.assertEqual(audit["policy_version"], "initial_context_quarantine_v0.2")
        self.assertEqual(audit["stage"], "initial_adjudication")
        self.assertEqual(audit["raw_sha256"], content_hash(raw))
        self.assertEqual(audit["projected_sha256"], content_hash(projected))
        self.assertEqual(audit["review_scope_ids"], ["a", "b", "c"])
        self.assertEqual(audit["evidence_index_maps"], {"a": [0, None, 1], "b": [0, None], "c": [0, None], "d": [0]})
        self.assertFalse(audit["visual_correction"])
        self.assertEqual(audit["shadow_pending_comparison_count"], 0)
        self.assertEqual(audit["shadow_validation_policy"], "initial_identity_pending_v0.2")
        self.assertTrue(audit["strict_shadow_validation_passed"])
        self.assertTrue(audit["requires_pending_preparation_before_use"])
        self.assertNotIn("raw_contract_failed", audit)
        self.assertEqual(len(audit["quarantined_evidence"]), 3)
        for item in audit["quarantined_evidence"]:
            _, _, raw_position, _, evidence_position = item["original_json_pointer"].split("/")
            observation = raw["clusters"][int(raw_position)]["adjudicator_evidence"][int(evidence_position)]
            self.assertEqual(item["observation"], observation)
            self.assertEqual(item["observation_sha256"], content_hash(observation))
            self.assertEqual(item["scope_owner_ids"], ["a", "b", "c"])
            for reference in item["references"]:
                self.assertEqual(reference["original_evidence_indices"], [1])
                self.assertEqual(reference["projected_evidence_indices"], [])
                self.assertEqual(reference["judgment"], "unresolved")
                self.assertEqual(reference["scope_relation"], "group_member")
        reconstructed = copy.deepcopy(projected)
        quarantined = {(item["owner_cluster_id"], item["original_evidence_index"]): item["observation"]
                       for item in audit["quarantined_evidence"]}
        for old, row in zip(raw["clusters"], reconstructed["clusters"]):
            mapping = audit["evidence_index_maps"][row["cluster_id"]]
            kept = row["adjudicator_evidence"]
            row["adjudicator_evidence"] = [copy.deepcopy(quarantined[(row["cluster_id"], i)]) if new is None else kept[new]
                                            for i, new in enumerate(mapping)]
            row["identity_comparisons"] = copy.deepcopy(old["identity_comparisons"])
        self.assertEqual(reconstructed, raw)
        jsonschema.validate(projected, F.SCHEMAS["adjudication"])
        F.M.validate_adjudication_identity_fields(projected, valid_frame_ids=[10], expected_proposal_ids=universe(raw))

    def test_declared_neighbors_do_not_exempt_already_allowed_wide_context(self):
        raw = three_scopes()
        # Every owner now declares all contextual neighbors, so raw strict passes.
        a, b, _, _ = raw["clusters"]
        for row, partner in ((a, "c"), (b, "a")):
            row["identity_comparisons"].append({"other_cluster_id": partner, "judgment": "unresolved",
                                                "scope_relation": "whole_part", "evidence_indices": []})
        F.M.validate_adjudication_identity_fields(raw, valid_frame_ids=[10])
        projected, audit = project(raw)
        self.assertEqual(len(audit["quarantined_evidence"]), 3)
        self.assertEqual([len(row["identity_comparisons"]) for row in projected["clusters"]],
                         [len(row["identity_comparisons"]) for row in raw["clusters"]])

    def test_normal_own_and_exact_binary_proofs_are_unchanged(self):
        raw = F.ledger(F.cluster("a", ["p0001", "p0002"]), F.cluster("b", ["p0003"]))
        F.comparison(raw["clusters"][0], "b", universe(raw), "confirmed_distinct", evidence_key="adjudicator_evidence")
        projected, audit = project(raw)
        self.assertEqual(projected, raw)
        self.assertEqual(audit["quarantined_evidence"], [])
        self.assertEqual(audit["review_scope_ids"], [])
        self.assertEqual(audit["evidence_index_maps"], {"a": [0, 1], "b": [0]})

    def test_undeclared_binary_partner_receives_no_new_exception(self):
        raw = F.ledger(F.cluster("a", ["p0001"]), F.cluster("b", ["p0002"]))
        raw["clusters"][0]["adjudicator_evidence"].append(F.evidence(universe(raw)))
        with self.assertRaisesRegex(ValueError, "outside its allowed scope"):
            project(raw)

    def test_unreferenced_context_needs_no_reciprocal_observations(self):
        raw = three_scopes()
        for row in raw["clusters"][1:3]:
            row["adjudicator_evidence"] = row["adjudicator_evidence"][:1]
            row["identity_comparisons"] = []
        projected, audit = project(raw)
        self.assertEqual(len(audit["quarantined_evidence"]), 1)
        self.assertEqual(audit["quarantined_evidence"][0]["references"], [])
        self.assertEqual(audit["review_scope_ids"], ["a", "b", "c"])
        self.assertEqual(projected["clusters"][1:], raw["clusters"][1:])

    def test_positive_reference_is_fatal_even_with_another_exact_union_witness(self):
        raw = three_scopes()
        raw["clusters"][0]["identity_comparisons"][0]["evidence_indices"] = [2, 1]
        original = copy.deepcopy(raw)
        with self.assertRaisesRegex(ValueError, "positive or unauthorized"):
            project(raw)
        self.assertEqual(raw, original)

    def test_unresolved_references_are_limited_to_whole_part_and_group_member(self):
        for relation in ("whole_part", "group_member", "comparable", "unresolved"):
            with self.subTest(relation=relation):
                raw = three_scopes()
                raw["clusters"][1]["identity_comparisons"][0]["scope_relation"] = relation
                if relation in {"whole_part", "group_member"}:
                    projected, _ = project(raw)
                    self.assertEqual(projected["clusters"][1]["identity_comparisons"][0]["scope_relation"], relation)
                else:
                    with self.assertRaisesRegex(ValueError, "positive or unauthorized"):
                        project(raw)

    def test_any_partial_wide_scope_or_missing_owner_is_fatal(self):
        for scope in (["p0001", "p0003", "p0004", "p0005"],
                      ["p0001", "p0002", "p0003", "p0005"],
                      ["p0003", "p0004", "p0005", "p0006"]):
            with self.subTest(scope=scope):
                raw = three_scopes()
                raw["clusters"][0]["adjudicator_evidence"][1]["anonymous_proposal_ids"] = scope
                with self.assertRaisesRegex(ValueError, "full owner and every complete"):
                    project(raw)

    def test_quarantine_does_not_legalize_another_undeclared_partial_observation(self):
        raw = three_scopes()
        raw["clusters"][0]["adjudicator_evidence"].append(F.evidence(["p0001", "p0005"]))
        with self.assertRaisesRegex(ValueError, "outside its allowed scope"):
            project(raw)

    def test_all_structure_and_reference_errors_remain_fatal_before_any_projection(self):
        for case in ("unknown_id", "duplicate_id", "bad_frame_bool", "bad_frame_float", "bad_frame_unknown",
                     "empty_text", "invalid_cue", "invalid_quality", "duplicate_owner", "duplicate_proposal",
                     "bad_index_bool", "bad_index_float", "bad_index_range", "duplicate_index",
                     "unknown_partner", "self_partner", "duplicate_partner", "initial_resolution", "nonfinite"):
            with self.subTest(case=case):
                raw = three_scopes()
                row = raw["clusters"][2]
                observation = row["adjudicator_evidence"][1]
                pair = row["identity_comparisons"][0]
                if case == "unknown_id":
                    observation["anonymous_proposal_ids"].append("unknown")
                elif case == "duplicate_id":
                    observation["anonymous_proposal_ids"].append("p0001")
                elif case.startswith("bad_frame"):
                    observation["frame_id"] = {"bad_frame_bool": True, "bad_frame_float": 10.0, "bad_frame_unknown": 99}[case]
                elif case == "empty_text":
                    observation["observation"] = "   "
                elif case == "invalid_cue":
                    observation["cue_type"] = "made_up"
                elif case == "invalid_quality":
                    observation["support_quality"] = "made_up"
                elif case == "duplicate_owner":
                    raw["clusters"][-1]["cluster_id"] = "a"
                elif case == "duplicate_proposal":
                    raw["clusters"][-1]["anonymous_proposal_ids"] = ["p0001"]
                elif case.startswith("bad_index"):
                    pair["evidence_indices"] = [{"bad_index_bool": True, "bad_index_float": 1.0, "bad_index_range": 9}[case]]
                elif case == "duplicate_index":
                    pair["evidence_indices"] = [1, 1]
                elif case in {"unknown_partner", "self_partner"}:
                    pair["other_cluster_id"] = "unknown" if case == "unknown_partner" else "c"
                elif case == "duplicate_partner":
                    row["identity_comparisons"].append(copy.deepcopy(pair))
                elif case == "initial_resolution":
                    F.resolution(row, "proposal_scope", ["c"], 0)
                else:
                    row["final_entity"]["entity_confidence"] = float("nan")
                with self.assertRaises(ValueError):
                    project(raw, ["p0001", "p0002", "p0003", "p0004", "p0005", "p0006"])

    def test_shadow_checks_pending_without_applying_or_hiding_its_changes(self):
        raw = three_scopes()
        raw["clusters"][0]["identity_comparisons"][0]["evidence_indices"] = [0]
        projected, audit = project(raw)
        comparison = projected["clusters"][0]["identity_comparisons"][0]
        self.assertEqual(comparison["judgment"], "confirmed_distinct")
        self.assertEqual(comparison["evidence_indices"], [0])
        self.assertEqual(audit["shadow_pending_comparison_count"], 1)
        with self.assertRaisesRegex(ValueError, "exact union-scope"):
            F.M.validate_adjudication_identity_fields(projected, valid_frame_ids=[10])
        derived, pending = F.M.prepare_initial_adjudication_for_review(projected, [10], universe(raw))
        self.assertEqual(derived["clusters"][0]["identity_comparisons"][0]["judgment"], "unresolved")
        self.assertEqual(len(pending["pending_comparisons"]), 1)
        self.assertEqual(derived["clusters"][0]["adjudicator_evidence"], projected["clusters"][0]["adjudicator_evidence"])

    def test_review_owners_include_abstained_rejected_and_unobserving_scopes_without_promotion(self):
        raw = three_scopes()
        raw["clusters"][1].update(decision="abstain", final_entity=None)
        raw["clusters"][2].update(decision="reject", final_entity=None)
        for row in raw["clusters"][1:3]:
            row["adjudicator_evidence"] = row["adjudicator_evidence"][:1]
            row["identity_comparisons"] = []
        projected, audit = project(raw)
        self.assertEqual(audit["review_scope_ids"], ["a", "b", "c"])
        self.assertEqual([row["decision"] for row in projected["clusters"]], ["accept", "abstain", "reject", "accept"])
        self.assertEqual(projected["clusters"][1:], raw["clusters"][1:])

    def test_multiple_context_indices_and_retained_positive_indices_remap_exactly(self):
        raw = three_scopes()
        b = raw["clusters"][1]
        b["adjudicator_evidence"].append(copy.deepcopy(b["adjudicator_evidence"][1]))
        b["identity_comparisons"][0]["evidence_indices"] = [1, 2, 0]
        projected, audit = project(raw)
        self.assertEqual(audit["evidence_index_maps"]["b"], [0, None, None])
        self.assertEqual(projected["clusters"][1]["identity_comparisons"][0]["evidence_indices"], [0])
        a_comparison = projected["clusters"][0]["identity_comparisons"][0]
        self.assertEqual(a_comparison["evidence_indices"], [1])
        self.assertEqual(a_comparison["judgment"], "confirmed_distinct")
        for item in audit["quarantined_evidence"]:
            if item["owner_cluster_id"] == "b":
                self.assertEqual(item["references"][0]["original_evidence_indices"], [1, 2, 0])
                self.assertEqual(item["references"][0]["projected_evidence_indices"], [0])

    def test_repeated_projection_does_not_replace_original_review_obligations(self):
        raw = three_scopes()
        first, audit = project(raw)
        again, same_audit = project(raw)
        self.assertEqual((again, same_audit), (first, audit))
        second, second_audit = project(first)
        self.assertEqual(second, first)
        self.assertEqual(second_audit["quarantined_evidence"], [])
        self.assertEqual(audit["review_scope_ids"], ["a", "b", "c"])
        first["clusters"][0]["adjudicator_evidence"][0]["observation"] = "mutated returned object"
        audit["quarantined_evidence"][0]["observation"]["anonymous_proposal_ids"].clear()
        self.assertEqual(len(raw["clusters"][0]["adjudicator_evidence"][1]["anonymous_proposal_ids"]), 5)

    def test_cluster_order_changes_only_paths_and_order_not_eligibility(self):
        raw = three_scopes()
        baseline, audit = project(raw)
        raw["clusters"].reverse()
        projected, reverse_audit = project(raw)
        self.assertEqual(projected["clusters"], list(reversed(baseline["clusters"])))
        self.assertEqual(reverse_audit["evidence_index_maps"], audit["evidence_index_maps"])
        self.assertEqual(reverse_audit["review_scope_ids"], audit["review_scope_ids"])


if __name__ == "__main__":
    unittest.main()
