"""Initial-only empty proof withdrawal; synthetic fixtures, no model/pixel gold."""

import copy
import json
import unittest

import jsonschema

from test_initial_context_quarantine import M as CONTEXT, three_scopes, universe
from test_initial_identity_preparation import SCHEMA, example, evidence
from test_pending_identity_review_audit import audit, gate, setup_pair
from test_physical_identity_review import two_reports
from test_prompt_unbound_pipelines import ENSEMBLE


M = CONTEXT.identity
IDS = ["p0001", "p0002", "p0003"]


def empty_example(judgment="confirmed_distinct"):
    value = example()
    value["clusters"][0]["identity_comparisons"][0].update(
        judgment=judgment, evidence_indices=[])
    return value


def pipeline(raw, ids=IDS):
    projected, context_audit = CONTEXT.project_initial_context(raw, [10], ids)
    derived, pending = M.prepare_initial_adjudication_for_review(projected, [10], ids)
    return projected, context_audit, derived, pending


class InitialEmptyReferencePreparationTests(unittest.TestCase):
    def test_both_positive_judgments_withdraw_only_judgment_and_record_exact_scope(self):
        for judgment in ("confirmed_same_scope", "confirmed_distinct"):
            with self.subTest(judgment=judgment):
                raw = empty_example(judgment)
                before = copy.deepcopy(raw)
                jsonschema.validate(raw, SCHEMA)
                with self.assertRaisesRegex(ValueError, "evidence_indices"):
                    M.validate_adjudication_identity_fields(raw, valid_frame_ids=[10])
                projected, context_audit, derived, pending = pipeline(raw)
                self.assertEqual(raw, before)
                self.assertEqual(projected, raw)
                expected = copy.deepcopy(raw)
                expected["clusters"][0]["identity_comparisons"][0]["judgment"] = "unresolved"
                self.assertEqual(derived, expected)
                jsonschema.validate(derived, SCHEMA)
                M.validate_adjudication_identity_fields(derived, valid_frame_ids=[10], expected_proposal_ids=IDS)
                self.assertEqual(context_audit["policy_version"], "initial_context_quarantine_v0.2")
                self.assertEqual(context_audit["shadow_validation_policy"], "initial_identity_pending_v0.2")
                self.assertEqual(context_audit["shadow_pending_comparison_count"], 1)
                self.assertTrue(context_audit["requires_pending_preparation_before_use"])
                self.assertEqual(pending["policy_version"], "initial_identity_pending_v0.2")
                self.assertFalse(pending["visual_correction"])
                self.assertEqual(len(pending["pending_comparisons"]), 1)
                row = pending["pending_comparisons"][0]
                self.assertEqual(row["json_pointer"], "/clusters/0/identity_comparisons/0/judgment")
                self.assertEqual(row["evidence_indices"], [])
                self.assertEqual(row["source_judgment"], judgment)
                self.assertEqual(row["own_anonymous_proposal_ids"], IDS[:2])
                self.assertEqual(row["other_anonymous_proposal_ids"], IDS[2:])
                self.assertEqual(row["union_anonymous_proposal_ids"], IDS)

    def test_local_unreferenced_and_reciprocal_witnesses_are_never_borrowed(self):
        raw = empty_example()
        raw["clusters"][0]["adjudicator_evidence"].append(evidence(IDS, "simultaneous_separation"))
        _, _, derived, pending = pipeline(raw)
        self.assertEqual(derived["clusters"][0]["identity_comparisons"][0]["evidence_indices"], [])
        self.assertEqual(derived["clusters"][1], raw["clusters"][1])
        self.assertEqual(derived["clusters"][0]["adjudicator_evidence"], raw["clusters"][0]["adjudicator_evidence"])
        self.assertEqual(len(pending["pending_comparisons"]), 1)

    def test_empty_evidence_inventory_can_be_withdrawn_without_inventing_observation(self):
        raw = empty_example()
        raw["clusters"][0].update(adjudicator_evidence=[], decision="abstain", final_entity=None,
                                  existence_judgment="uncertain", identity_status="ambiguous")
        _, _, derived, pending = pipeline(raw)
        self.assertEqual(derived["clusters"][0]["adjudicator_evidence"], [])
        self.assertEqual(derived["clusters"][0]["decision"], "abstain")
        self.assertEqual(len(pending["pending_comparisons"]), 1)

    def test_legal_unresolved_empty_is_unchanged_for_every_relation(self):
        for relation in M.SCOPE_RELATIONS:
            with self.subTest(relation=relation):
                raw = empty_example("unresolved")
                raw["clusters"][0]["identity_comparisons"][0]["scope_relation"] = relation
                _, context_audit, derived, pending = pipeline(raw)
                self.assertEqual(derived, raw)
                self.assertEqual(pending["pending_comparisons"], [])
                self.assertEqual(context_audit["shadow_pending_comparison_count"], 0)

    def test_invalid_indices_remain_fatal_in_both_initial_guards(self):
        for value in (None, False, 0, "", {}, (), [True], [0.0], [-1], [1], [0, 0]):
            with self.subTest(value=value):
                raw = empty_example()
                raw["clusters"][0]["identity_comparisons"][0]["evidence_indices"] = value
                before = copy.deepcopy(raw)
                for fn in (CONTEXT.project_initial_context, M.prepare_initial_adjudication_for_review):
                    with self.assertRaises(ValueError):
                        fn(raw, [10], IDS)
                self.assertEqual(raw, before)
        raw = empty_example()
        del raw["clusters"][0]["identity_comparisons"][0]["evidence_indices"]
        with self.assertRaises(ValueError):
            pipeline(raw)

    def test_empty_refs_cannot_hide_relation_partner_or_ownership_errors(self):
        cases = ("whole_part", "group_member", "unresolved", "self", "unknown", "duplicate_partner",
                 "duplicate_owner", "missing_owner", "unknown_observation", "initial_resolution")
        for case in cases:
            with self.subTest(case=case):
                raw = empty_example()
                left, right = raw["clusters"]
                pair = left["identity_comparisons"][0]
                if case in M.SCOPE_RELATIONS:
                    pair["scope_relation"] = case
                elif case in {"self", "unknown"}:
                    pair["other_cluster_id"] = "c1" if case == "self" else "absent"
                elif case == "duplicate_partner":
                    left["identity_comparisons"].append(copy.deepcopy(pair))
                elif case == "duplicate_owner":
                    right["anonymous_proposal_ids"].append("p0002")
                elif case == "missing_owner":
                    raw["clusters"].pop()
                elif case == "unknown_observation":
                    right["adjudicator_evidence"][0]["anonymous_proposal_ids"] = ["absent"]
                else:
                    right["revision_resolutions"] = [{"axis": "physical_entity"}]
                with self.assertRaises(ValueError):
                    pipeline(raw)

    def test_quarantine_then_pending_preserves_empty_refs_and_complete_obligations(self):
        raw = three_scopes()
        raw["clusters"][0]["identity_comparisons"][0]["evidence_indices"] = []
        projected, context_audit, derived, pending = pipeline(raw, universe(raw))
        self.assertEqual(len(context_audit["quarantined_evidence"]), 3)
        self.assertEqual(context_audit["review_scope_ids"], ["a", "b", "c"])
        self.assertEqual(context_audit["shadow_pending_comparison_count"], 1)
        self.assertEqual(projected["clusters"][0]["identity_comparisons"][0]["judgment"], "confirmed_distinct")
        self.assertEqual(pending["pending_comparisons"][0]["evidence_indices"], [])
        self.assertEqual(pending["pending_comparisons"][0]["union_anonymous_proposal_ids"],
                         ["p0001", "p0002", "p0003", "p0004"])
        expected = copy.deepcopy(projected)
        expected["clusters"][0]["identity_comparisons"][0]["judgment"] = "unresolved"
        self.assertEqual(derived, expected)

    def test_empty_pair_does_not_hide_wide_positive_or_partial_context(self):
        for case in ("positive_wide", "partial_wide"):
            with self.subTest(case=case):
                raw = three_scopes()
                raw["clusters"][0]["identity_comparisons"][0]["evidence_indices"] = []
                if case == "positive_wide":
                    raw["clusters"][1]["identity_comparisons"][0].update(
                        judgment="confirmed_same_scope", scope_relation="comparable")
                else:
                    raw["clusters"][1]["adjudicator_evidence"][1]["anonymous_proposal_ids"].remove("p0001")
                with self.assertRaises(ValueError):
                    pipeline(raw, universe(raw))

    def test_strict_verifier_and_revision_still_reject_empty_positive_refs(self):
        for judgment in ("confirmed_same_scope", "confirmed_distinct"):
            with self.subTest(judgment=judgment):
                raw = empty_example(judgment)
                reports = two_reports(*raw["clusters"])
                report = reports[0]
                report["reviews"][0]["identity_comparisons"] = copy.deepcopy(raw["clusters"][0]["identity_comparisons"])
                with self.assertRaisesRegex(ValueError, "evidence_indices"):
                    M.validate_verifier_identity_fields(report,
                        target_proposal_ids_by_cluster={"c1": IDS[:2], "c2": IDS[2:]},
                        identity_challenge_pairs=[], valid_frame_ids=[10])
                raw["clusters"][0]["revision_resolutions"] = [{
                    "axis": "instance_correspondence", "target_cluster_ids": ["c1", "c2"],
                    "anonymous_proposal_ids": IDS[:2], "evidence_indices": [0]}]
                with self.assertRaisesRegex(ValueError, "evidence_indices"):
                    M.validate_adjudication_identity_fields(raw, valid_frame_ids=[10])
                with self.assertRaisesRegex(ValueError, "revision resolutions"):
                    M.prepare_initial_adjudication_for_review(raw, [10], IDS)

    def test_forced_scopes_and_two_verifier_disposition_survive_empty_initial_refs(self):
        raw, final, reports, _ = setup_pair()
        raw["clusters"][0]["identity_comparisons"][0].update(judgment="confirmed_distinct", evidence_indices=[])
        _, _, initial, pending = pipeline(raw, universe(raw))
        rows = pending["pending_comparisons"]
        pairs, targets, reasons = ENSEMBLE.add_pending_identity_review_obligations(
            decisions=initial, pending_comparisons=rows,
            identity_challenge_pairs=[], target_ids=[], target_reasons={})
        self.assertEqual(targets, ["a", "b"])
        self.assertEqual(set(reasons), {"a", "b"})
        self.assertEqual(len(pairs), 1)
        self.assertNotIn("confirmed_distinct", json.dumps(pairs))
        accepted, proof = gate(initial, final, reports)
        result = audit(initial, accepted, reports, rows, proof)
        self.assertTrue(result["all_pending_pairs_contract_resolved"], result)
        self.assertFalse(result["pixel_truth_verified"])
        for missing in (reports[:1], reports[1:]):
            result = audit(initial, accepted, missing, rows, proof)
            self.assertFalse(result["all_pending_pairs_contract_resolved"])
            self.assertTrue(result["unresolved_coverage_risk"])
        partial = copy.deepcopy(reports)
        partial[1]["reviews"][0]["evidence"][0]["anonymous_proposal_ids"] = ["p1"]
        self.assertFalse(audit(initial, accepted, partial, rows, proof)["all_pending_pairs_contract_resolved"])
        changed = copy.deepcopy(rows)
        changed[0]["own_anonymous_proposal_ids"] = ["p1"]
        with self.assertRaisesRegex(ENSEMBLE.EnsembleError, "complete initial scopes"):
            ENSEMBLE.add_pending_identity_review_obligations(decisions=initial, pending_comparisons=changed,
                identity_challenge_pairs=[], target_ids=[], target_reasons={})

    def test_repeat_projection_does_not_discharge_original_pending_sidecar(self):
        raw = empty_example()
        first = pipeline(raw)
        self.assertEqual(pipeline(raw), first)
        derived, pending = first[2:]
        second, later_audit = M.prepare_initial_adjudication_for_review(derived, [10], IDS)
        self.assertEqual(second, derived)
        self.assertEqual(later_audit["pending_comparisons"], [])
        self.assertEqual(len(pending["pending_comparisons"]), 1)
        pending["pending_comparisons"][0]["evidence_indices"].append(0)
        self.assertEqual(raw["clusters"][0]["identity_comparisons"][0]["evidence_indices"], [])


if __name__ == "__main__":
    unittest.main()
