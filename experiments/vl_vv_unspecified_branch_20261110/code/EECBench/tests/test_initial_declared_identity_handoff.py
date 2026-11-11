"""Neutral complete-scope comparison delivery, without model or image claims."""

import copy
import json
import unittest

from test_physical_identity_review import M as PHYSICAL, cluster, comparison, ledger, two_reports
from test_prompt_unbound_pipelines import ENSEMBLE as M


def inputs():
    groups = [("a", "alpha", [f"p{i:04d}" for i in range(1, 5)]),
              ("b", "beta", [f"p{i:04d}" for i in range(5, 9)])]
    initial = ledger(*(cluster(key, ids, name=name) for key, name, ids in groups))
    proposals, mappings = [], []
    for key, name, ids in groups:
        for i, pid in enumerate(ids):
            proposals.append({"anonymous_proposal_id": pid, "proposed_name": name,
                              "canonical_head": name, "granularity": "single_object",
                              "coarse_locators": [{"frame_id": 10, "description": name}],
                              "frame_presence": [{"frame_id": 10, "status": "visible",
                                                  "bbox_xyxy_normalized": [0.1, 0.2, 0.3, 0.4]}]})
            mappings.append({"anonymous_proposal_id": pid, "source_kind": "detector",
                             "source": M.DETECTOR_ROLES[i][0], "local_id": key + str(i)})
    return initial, {"proposals": proposals}, {"mappings": mappings}


def declare(initial, judgment="confirmed_distinct", relation="comparable", reciprocal=False):
    left, right = initial["clusters"]
    union = left["anonymous_proposal_ids"] + right["anonymous_proposal_ids"]
    comparison(left, right["cluster_id"], union, judgment,
               evidence_key="adjudicator_evidence", relation=relation)
    if reciprocal:
        comparison(right, left["cluster_id"], union, judgment,
                   evidence_key="adjudicator_evidence", relation=relation)


def route(initial, anonymous, sources):
    pairs = M.build_identity_challenge_pairs(initial, anonymous, include_initial_comparisons=True)
    targets, reasons = M.select_verification_targets(initial, sources, anonymous, include_initial_comparisons=True)
    view = M._verification_view(initial, anonymous, targets, pairs)
    audit = M.audit_initial_declared_identity_handoff(initial, view)
    return pairs, targets, reasons, view, audit


class InitialDeclaredIdentityHandoffTests(unittest.TestCase):
    def test_heuristically_unrelated_positive_pair_is_delivered_in_full(self):
        initial, anonymous, sources = inputs()
        declare(initial, reciprocal=True)
        before = copy.deepcopy((initial, anonymous, sources))
        PHYSICAL.validate_adjudication_identity_fields(initial, valid_frame_ids=[10])
        self.assertEqual(M.build_identity_challenge_pairs(initial, anonymous), [])
        self.assertEqual(M.select_verification_targets(initial, sources, anonymous), ([], {}))
        pairs, targets, reasons, view, audit = route(initial, anonymous, sources)
        self.assertEqual(targets, ["a", "b"])
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["trigger_bases"], ["physical_scope_comparison"])
        self.assertEqual(audit["source_comparison_count"], 2)
        self.assertEqual(audit["declared_pair_count"], 1)
        self.assertEqual(audit["required_partners_by_cluster"], {"a": ["b"], "b": ["a"]})
        self.assertEqual(audit["required_verifier_ids"], ["verifier_1", "verifier_2"])
        self.assertEqual(audit["records"][0]["source_comparison_json_pointers"],
                         ["/clusters/0/identity_comparisons/0", "/clusters/1/identity_comparisons/0"])
        for target, owner in zip(view["targets"], initial["clusters"]):
            self.assertEqual([p["anonymous_proposal_id"] for p in target["proposals"]], owner["anonymous_proposal_ids"])
            self.assertIn("initial_declared_identity_comparison", reasons[owner["cluster_id"]])
        self.assertEqual((initial, anonymous, sources), before)

    def test_all_legal_judgments_and_relations_have_identical_neutral_questions(self):
        baseline = None
        for judgment, relation in ([("confirmed_same_scope", "comparable"), ("confirmed_distinct", "comparable")]
                + [("unresolved", r) for r in ("comparable", "whole_part", "group_member", "unresolved")]):
            with self.subTest(judgment=judgment, relation=relation):
                initial, anonymous, sources = inputs()
                declare(initial, judgment, relation)
                pairs, _, _, view, audit = route(initial, anonymous, sources)
                if baseline is None:
                    baseline = copy.deepcopy(view)
                self.assertEqual(view, baseline)
                for forbidden in ("judgment", "evidence_indices", "adjudicator_evidence", "source_comparison_count",
                                  "support_quality", "scope_relation", "initial_declared_identity_comparison"):
                    self.assertNotIn(forbidden, json.dumps(view))
                self.assertEqual(pairs[0]["effect"], "review_only_no_automatic_merge")
                self.assertFalse(audit["source_assertions_used_as_proof"])

    def test_reciprocal_and_heuristic_duplicates_form_one_required_pair(self):
        initial, anonymous, sources = inputs()
        for c in initial["clusters"]:
            c["canonical_name"] = "shared category"
        declare(initial, reciprocal=True)
        pairs, _, _, _, audit = route(initial, anonymous, sources)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["trigger_bases"].count("physical_scope_comparison"), 1)
        self.assertIn("same_canonical_name", pairs[0]["trigger_bases"])
        self.assertEqual(audit["source_comparison_count"], 2)

    def test_rejected_deferred_and_abstained_endpoints_are_reviewed_not_promoted(self):
        for decision in ("reject", "abstain"):
            for both in (False, True):
                with self.subTest(decision=decision, both=both):
                    initial, anonymous, sources = inputs()
                    declare(initial, "unresolved", "group_member")
                    for c in initial["clusters"] if both else initial["clusters"][:1]:
                        c.update(decision=decision, final_entity=None, uncertainty_flags=["group_member_conflict"])
                    before = copy.deepcopy(initial)
                    _, targets, _, _, _ = route(initial, anonymous, sources)
                    self.assertEqual(targets, ["a", "b"])
                    self.assertEqual(initial, before)
                    gated, _ = PHYSICAL.apply_physical_identity_gate(initial, initial_decisions=initial,
                        verifier_reports=[], verification_target_reasons={key: ["review"] for key in targets})
                    for old, new in zip(initial["clusters"], gated["clusters"]):
                        if old["decision"] != "accept":
                            self.assertEqual(new, old)

    def test_absent_legacy_fields_and_default_off_preserve_old_behavior(self):
        initial, anonymous, sources = inputs()
        for c in initial["clusters"]:
            del c["identity_comparisons"]
        self.assertEqual(M.build_identity_challenge_pairs(initial, anonymous),
                         M.build_identity_challenge_pairs(initial, anonymous, include_initial_comparisons=True))
        self.assertEqual(M.select_verification_targets(initial, sources, anonymous),
                         M.select_verification_targets(initial, sources, anonymous, include_initial_comparisons=True))
        declare_target = inputs()[0]
        declare(declare_target)
        self.assertEqual(M.build_identity_challenge_pairs(declare_target, anonymous), [])

    def test_missing_self_duplicate_or_noncomparable_positive_endpoints_are_fatal(self):
        cases = ("missing", "self", "duplicate", "null", "row_null", "noncomparable", "unknown_judgment", "partial_owner")
        for case in cases:
            with self.subTest(case=case):
                initial, anonymous, sources = inputs()
                declare(initial)
                left = initial["clusters"][0]
                row = left["identity_comparisons"][0]
                if case in {"missing", "self"}:
                    row["other_cluster_id"] = "absent" if case == "missing" else "a"
                elif case == "duplicate":
                    left["identity_comparisons"].append(copy.deepcopy(row))
                elif case == "null":
                    left["identity_comparisons"] = None
                elif case == "row_null":
                    left["identity_comparisons"] = [None]
                elif case == "noncomparable":
                    row["scope_relation"] = "whole_part"
                elif case == "unknown_judgment":
                    row["judgment"] = "probably_distinct"
                else:
                    initial["clusters"][1]["anonymous_proposal_ids"].append("p0001")
                with self.assertRaises(M.EnsembleError):
                    route(initial, anonymous, sources)

    def test_actual_compact_handoff_rejects_omitted_pair_or_incomplete_target(self):
        initial, anonymous, sources = inputs()
        declare(initial)
        view = route(initial, anonymous, sources)[3]
        for case in ("pair", "target", "proposal", "duplicate_target", "duplicate_pair"):
            with self.subTest(case=case):
                changed = copy.deepcopy(view)
                if case == "pair":
                    changed["identity_challenge_pairs"] = []
                elif case == "target":
                    changed["targets"].pop()
                elif case == "proposal":
                    changed["targets"][1]["proposals"].pop()
                elif case == "duplicate_target":
                    changed["targets"].append(copy.deepcopy(changed["targets"][0]))
                else:
                    changed["identity_challenge_pairs"].append(copy.deepcopy(changed["identity_challenge_pairs"][0]))
                with self.assertRaises(M.EnsembleError):
                    M.audit_initial_declared_identity_handoff(initial, changed)

    def test_both_verifiers_must_answer_both_sides_but_unresolved_remains_valid(self):
        initial, anonymous, sources = inputs()
        declare(initial)
        pairs = route(initial, anonymous, sources)[0]
        scope_map = {c["cluster_id"]: c["anonymous_proposal_ids"] for c in initial["clusters"]}
        reports = two_reports(*initial["clusters"])
        def validate(report):
            PHYSICAL.validate_verifier_identity_fields(report, target_proposal_ids_by_cluster=scope_map,
                                                       identity_challenge_pairs=pairs, valid_frame_ids=[10])
        for report in reports:
            with self.assertRaises(ValueError):
                validate(report)
            for own, other in zip(report["reviews"], ("b", "a")):
                comparison(own, other, [], "unresolved")
            validate(report)
            missing = copy.deepcopy(report)
            missing["reviews"][1]["identity_comparisons"] = []
            with self.assertRaises(ValueError):
                validate(missing)
        gated, _ = PHYSICAL.apply_physical_identity_gate(initial, initial_decisions=initial,
            verifier_reports=reports, verification_target_reasons={key: ["review"] for key in scope_map})
        self.assertEqual([c["decision"] for c in gated["clusters"]], ["abstain", "abstain"])

    def test_cluster_order_does_not_change_pair_or_complete_target_set(self):
        initial, anonymous, sources = inputs()
        declare(initial, reciprocal=True)
        expected = route(initial, anonymous, sources)
        initial["clusters"].reverse()
        changed = route(initial, anonymous, sources)
        self.assertEqual(changed[:3], expected[:3])
        self.assertEqual(changed[4]["required_partners_by_cluster"], expected[4]["required_partners_by_cluster"])


if __name__ == "__main__":
    unittest.main()
