"""Synthetic transport/proof-boundary tests; no models or image gold labels."""

import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
import physical_completion_patch as M  # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


F = load("patch_identity_fixtures", Path(__file__).with_name("test_physical_identity_review.py"))
C = load("patch_completion_fixtures", Path(__file__).with_name("test_physical_review_completion.py"))


def synthetic(shared=False):
    """Finite authorized slots; initial-target labels are synthetic metadata."""
    candidate = F.ledger(F.cluster("a", ["p0001", "p0002"]), F.cluster("b", ["p0003"]),
                         F.cluster("c", ["p0004"]), F.cluster("untouched", ["p0005", "p0006"]))
    clusters = {row["cluster_id"]: row for row in candidate["clusters"]}
    names = ["a", "b", "c"] if shared else ["a"]
    obligations = {"policy_version": M.completion.OBLIGATION_POLICY, "shot_id": candidate["shot_id"],
                   "cluster_obligations": [], "pair_obligations": []}
    for owner in names:
        scope = clusters[owner]["anonymous_proposal_ids"]
        axes = [{"axis": "instance_correspondence" if shared else "physical_entity",
                 "anonymous_proposal_ids": list(scope), "initial_target_cluster_ids": ["old1", "old2"] if shared else ["a"],
                 "revision_cannot_override": False, "requires_exact_scope_revision_resolution": True,
                 "gate_failure_reasons": ["synthetic exact-scope obligation"]}] if owner == "a" else []
        obligations["cluster_obligations"].append({"cluster_id": owner, "anonymous_proposal_ids": list(scope),
            "candidate_decision": "accept", "gate_result": "abstain", "axis_obligations": axes})
    if shared:
        a = clusters["a"]
        a["adjudicator_evidence"].append(F.evidence(a["anonymous_proposal_ids"], "same_instance_continuity"))
        F.resolution(a, "instance_correspondence", ["old1", "old2"], 1)
        for partner in ("b", "c"):
            F.comparison(a, partner, (), "unresolved", evidence_key="adjudicator_evidence")
            obligations["pair_obligations"].append({
                "cluster_ids": ["a", partner], "initial_target_cluster_ids": ["old1", "old2"],
                "union_anonymous_proposal_ids": a["anonymous_proposal_ids"] + clusters[partner]["anonymous_proposal_ids"],
                "endpoint_records": [{"cluster_id": key, "anonymous_proposal_ids": list(clusters[key]["anonymous_proposal_ids"])}
                                     for key in ("a", partner)]})
    return candidate, obligations


def blank(table):
    return {"schema_version": M.PATCH_VERSION, "shot_id": table["shot_id"],
            "slot_table_sha256": table["slot_table_sha256"], "cluster_updates": [],
            "new_evidence": [], "comparison_updates": [], "resolution_updates": []}


def cluster_update(owner="a", **changes):
    return {"owner_cluster_id": owner, **dict.fromkeys(M._CLUSTER_FIELDS), **changes}


def existing(index):
    return {"kind": "existing", "index": index, "new_evidence_id": None}


def fresh(key):
    return {"kind": "new", "index": None, "new_evidence_id": key}


def resolved_shared_patch(table):
    patch = blank(table)
    for i, partner in enumerate(("b", "c"), 1):
        slot = next(row for row in table["comparison_slots"]
                    if row["owner_cluster_id"] == "a" and row["other_cluster_id"] == partner)
        pair = next(row for row in table["pairs"] if row["pair_id"] == slot["pair_id"])
        patch["new_evidence"].append({"owner_cluster_id": "a", "new_evidence_id": f"n{i}",
            "observation": F.evidence(pair["union_anonymous_proposal_ids"], "simultaneous_separation",
                                      f"Synthetic independent union observation for a and {partner}.")})
        patch["comparison_updates"].append({"slot_id": slot["slot_id"], "judgment": "confirmed_distinct",
                                           "scope_relation": "comparable", "evidence_refs": [fresh(f"n{i}")]})
    slot = next(row for row in table["resolution_slots"] if row["owner_cluster_id"] == "a")
    patch["resolution_updates"] = [{"slot_id": slot["slot_id"],
                                    "evidence_refs": [existing(1), fresh("n1"), fresh("n2")]}]
    return patch


class PhysicalCompletionPatchTests(unittest.TestCase):
    def test_static_schema_matches_pure_schema_and_local_transport_preflight(self):
        import ensemble_shot_entity_detection as runtime
        path = ROOT / "schemas/codex_physical_completion_patch_v0.1.schema.json"
        self.assertEqual(json.loads(path.read_text()), M.PATCH_SCHEMA)
        self.assertEqual(M.PATCH_SCHEMA["$defs"]["evidence"], F.SCHEMAS["adjudication"]["$defs"]["evidence"])
        jsonschema.Draft202012Validator.check_schema(M.PATCH_SCHEMA)
        self.assertEqual(runtime.validate_codex_schema_transport(path), M.PATCH_SCHEMA)

    def test_empty_patch_preserves_entire_ledger_and_has_no_visual_acceptance_claim(self):
        candidate, obligations = synthetic()
        slots = M.build_completion_patch_slots(candidate, obligations)
        snapshot = copy.deepcopy((candidate, obligations, slots))
        result, audit = M.apply_completion_patch(candidate, obligations, slots, blank(slots))
        self.assertEqual(result, candidate)
        self.assertEqual((candidate, obligations, slots), snapshot)
        self.assertFalse(audit["visual_truth_verified"])
        self.assertTrue(audit["full_schema_base_identity_lineage_split_and_gate_validation_required"])
        self.assertEqual(audit["completion_firewall"]["changed_cluster_ids"], [])
        result["clusters"].clear()
        self.assertEqual(candidate, snapshot[0])

    def test_empty_obligations_have_no_editable_slots_or_new_evidence(self):
        candidate, obligations = synthetic()
        obligations["cluster_obligations"] = []
        slots = M.build_completion_patch_slots(candidate, obligations)
        self.assertEqual(slots["owners"], [])
        self.assertEqual(M.apply_completion_patch(candidate, obligations, slots, blank(slots))[0], candidate)
        patch = blank(slots)
        patch["cluster_updates"] = [cluster_update(decision="abstain")]
        with self.assertRaises(M.PhysicalCompletionPatchError):
            M.apply_completion_patch(candidate, obligations, slots, patch)

    def test_withdrawal_updates_only_listed_fields_and_does_not_retype_entity(self):
        candidate, obligations = synthetic()
        slots = M.build_completion_patch_slots(candidate, obligations)
        patch = blank(slots)
        patch["cluster_updates"] = [cluster_update(decision="abstain", existence_judgment="uncertain",
                                                  salience_judgment="ambiguous", decision_reason="Unresolved on review.")]
        result, audit = M.apply_completion_patch(candidate, obligations, slots, patch)
        self.assertIsNone(result["clusters"][0]["final_entity"])
        self.assertEqual(result["clusters"][1:], candidate["clusters"][1:])
        self.assertEqual(result["clusters"][0]["adjudicator_evidence"], candidate["clusters"][0]["adjudicator_evidence"])
        self.assertEqual(audit["completion_firewall"]["withdrawn_accept_cluster_ids"], ["a"])
        patch["cluster_updates"][0]["entity_confidence"] = 0.9
        with self.assertRaises(M.PhysicalCompletionPatchError):
            M.apply_completion_patch(candidate, obligations, slots, patch)

    def test_protected_fields_and_unlisted_axes_are_rejected_even_if_values_match(self):
        candidate, obligations = synthetic()
        slots = M.build_completion_patch_slots(candidate, obligations)
        for change in ({"canonical_name": "override"}, {"anonymous_proposal_ids": ["p0001"]},
                       {"final_entity": {}}, {"identity_status": "resolved"},
                       {"proposal_scope_judgment": "resolved_single_scope"}, {"owner_cluster_id": "untouched"}):
            with self.subTest(change=change):
                patch = blank(slots)
                patch["cluster_updates"] = [cluster_update(**change)]
                with self.assertRaises(M.PhysicalCompletionPatchError):
                    M.apply_completion_patch(candidate, obligations, slots, patch)

    def test_stale_inputs_table_and_patch_binding_are_rejected(self):
        candidate, obligations = synthetic()
        slots = M.build_completion_patch_slots(candidate, obligations)
        for kind in ("candidate", "obligations", "table", "numeric_table_type", "patch_hash", "shot"):
            with self.subTest(kind=kind):
                before, obs, table = copy.deepcopy((candidate, obligations, slots))
                patch = blank(table)
                if kind == "candidate":
                    before["clusters"][-1]["canonical_name"] = "changed immutable baseline"
                elif kind == "obligations":
                    obs["context_note"] = "different source"
                elif kind == "table":
                    table["resolution_slots"][0]["target_cluster_ids"] = ["wrong"]
                elif kind == "numeric_table_type":
                    table["new_evidence_budget"]["per_owner"] = float(M.MAX_NEW_EVIDENCE_PER_OWNER)
                elif kind == "patch_hash":
                    patch["slot_table_sha256"] = "0" * 64
                else:
                    patch["shot_id"] = "another-shot"
                with self.assertRaises(M.PhysicalCompletionPatchError):
                    M.apply_completion_patch(before, obs, table, patch)

    def test_shared_slot_preserves_old_same_and_two_explicit_distinct_witnesses(self):
        candidate, obligations = synthetic(shared=True)
        slots = M.build_completion_patch_slots(candidate, obligations)
        own_slots = [row for row in slots["resolution_slots"] if row["owner_cluster_id"] == "a"]
        self.assertEqual(len(own_slots), 1)
        slot = own_slots[0]
        self.assertEqual(slot["existing_resolution"], candidate["clusters"][0]["revision_resolutions"][0])
        self.assertEqual(slot["existing_resolution"]["evidence_indices"], [1])
        self.assertEqual(len(slot["associated_pair_ids"]), 2)
        self.assertEqual(len(slot["cluster_axis_obligations"]), 1)
        patch = resolved_shared_patch(slots)
        snapshot = copy.deepcopy((candidate, obligations, slots, patch))
        result, audit = M.apply_completion_patch(candidate, obligations, slots, patch)
        self.assertEqual((candidate, obligations, slots, patch), snapshot)
        a = result["clusters"][0]
        self.assertEqual(a["adjudicator_evidence"][:2], candidate["clusters"][0]["adjudicator_evidence"])
        self.assertEqual(a["adjudicator_evidence"][2:], [row["observation"] for row in patch["new_evidence"]])
        self.assertEqual(a["revision_resolutions"][0]["evidence_indices"], [1, 2, 3])
        self.assertEqual(audit["new_evidence_index_map"]["a"], {"n1": 2, "n2": 3})
        self.assertEqual(result["clusters"][1:], candidate["clusters"][1:])
        own = frozenset(a["anonymous_proposal_ids"])
        self.assertTrue(F.M._resolution(a, "instance_correspondence", frozenset(("old1", "old2")), own, F.M.SAME_CUES))
        for partner in result["clusters"][1:3]:
            proof = F.M._distinct_revision_proof(a, other_cluster_id=partner["cluster_id"],
                targets=frozenset(("old1", "old2")), own_scope=own,
                other_scope=frozenset(partner["anonymous_proposal_ids"]))
            self.assertIsNotNone(proof)
            self.assertFalse(proof["independent_observation"])
        jsonschema.validate(result, F.SCHEMAS["adjudication"])
        F.M.validate_adjudication_identity_fields(result, valid_frame_ids=[10],
            expected_proposal_ids=[p for c in candidate["clusters"] for p in c["anonymous_proposal_ids"]])

    def test_missing_explicit_shared_refs_are_not_automatically_filled(self):
        candidate, obligations = synthetic(shared=True)
        slots = M.build_completion_patch_slots(candidate, obligations)
        patch = resolved_shared_patch(slots)
        patch["resolution_updates"][0]["evidence_refs"] = [fresh("n1")]
        result, _ = M.apply_completion_patch(candidate, obligations, slots, patch)
        a = result["clusters"][0]
        self.assertEqual(a["revision_resolutions"][0]["evidence_indices"], [2])
        self.assertEqual(a["adjudicator_evidence"][1], candidate["clusters"][0]["adjudicator_evidence"][1])
        own = frozenset(a["anonymous_proposal_ids"])
        self.assertFalse(F.M._resolution(a, "instance_correspondence", frozenset(("old1", "old2")), own, F.M.SAME_CUES))
        self.assertIsNone(F.M._distinct_revision_proof(a, other_cluster_id="c", targets=frozenset(("old1", "old2")),
                          own_scope=own, other_scope=frozenset(("p0004",))))

    def test_duplicate_rows_never_last_write_win_or_merge_and_inputs_stay_immutable(self):
        candidate, obligations = synthetic(shared=True)
        slots = M.build_completion_patch_slots(candidate, obligations)
        for field in ("cluster_updates", "new_evidence", "comparison_updates", "resolution_updates"):
            with self.subTest(field=field):
                patch = resolved_shared_patch(slots)
                patch["cluster_updates"] = [cluster_update(decision_reason="Explicit update")]
                patch[field].append(copy.deepcopy(patch[field][0]))
                snapshot = copy.deepcopy((candidate, obligations, slots, patch))
                with self.assertRaises(M.PhysicalCompletionPatchError):
                    M.apply_completion_patch(candidate, obligations, slots, patch)
                self.assertEqual((candidate, obligations, slots, patch), snapshot)

    def test_bad_old_new_cross_owner_and_duplicate_refs_are_rejected(self):
        candidate, obligations = synthetic(shared=True)
        slots = M.build_completion_patch_slots(candidate, obligations)
        cases = [[existing(value)] for value in (True, 1.0, -1, 2, 999)]
        cases += [[fresh("missing")], [existing(1), existing(1)], [fresh("n1"), fresh("n1")]]
        for refs in cases:
            with self.subTest(refs=refs):
                patch = resolved_shared_patch(slots)
                patch["resolution_updates"][0]["evidence_refs"] = refs
                with self.assertRaises(M.PhysicalCompletionPatchError):
                    M.apply_completion_patch(candidate, obligations, slots, patch)
        patch = resolved_shared_patch(slots)
        bslot = next(row for row in slots["resolution_slots"] if row["owner_cluster_id"] == "b")
        patch["resolution_updates"] = [{"slot_id": bslot["slot_id"], "evidence_refs": [fresh("n1")]}]
        with self.assertRaises(M.PhysicalCompletionPatchError):
            M.apply_completion_patch(candidate, obligations, slots, patch)

    def test_partial_observation_stays_partial_and_strict_identity_rejects_confirmed_union(self):
        candidate, obligations = synthetic(shared=True)
        slots = M.build_completion_patch_slots(candidate, obligations)
        patch = resolved_shared_patch(slots)
        patch["new_evidence"][0]["observation"]["anonymous_proposal_ids"] = ["p0001", "p0003"]
        result, audit = M.apply_completion_patch(candidate, obligations, slots, patch)
        self.assertEqual(result["clusters"][0]["adjudicator_evidence"][2]["anonymous_proposal_ids"], ["p0001", "p0003"])
        self.assertFalse(audit["evidence_scope_expanded"])
        with self.assertRaisesRegex(ValueError, "exact union-scope"):
            F.M.validate_adjudication_identity_fields(result, valid_frame_ids=[10])

    def test_unknown_other_only_multi_pair_and_duplicate_evidence_scopes_fail(self):
        candidate, obligations = synthetic(shared=True)
        slots = M.build_completion_patch_slots(candidate, obligations)
        for scope in (["unknown"], ["p0003"], ["p0001", "p0003", "p0004"], ["p0001", "p0001"]):
            with self.subTest(scope=scope):
                patch = resolved_shared_patch(slots)
                patch["new_evidence"][0]["observation"]["anonymous_proposal_ids"] = scope
                with self.assertRaises(ValueError):
                    M.apply_completion_patch(candidate, obligations, slots, patch)

    def test_frame_numbers_entity_support_and_finite_values_are_strict(self):
        candidate, obligations = synthetic(shared=True)
        slots = M.build_completion_patch_slots(candidate, obligations)
        for frame in (True, 10.0, 999):
            patch = resolved_shared_patch(slots)
            patch["new_evidence"][0]["observation"]["frame_id"] = frame
            with self.assertRaises(M.PhysicalCompletionPatchError):
                M.apply_completion_patch(candidate, obligations, slots, patch)
        for change in ({"evidence_frame_ids": [10, 10]}, {"evidence_frame_ids": [10.0]},
                       {"entity_confidence": float("nan")}, {"entity_confidence": float("inf")}):
            patch = blank(slots)
            patch["cluster_updates"] = [cluster_update(**change)]
            with self.assertRaises(M.PhysicalCompletionPatchError):
                M.apply_completion_patch(candidate, obligations, slots, patch)

    def test_observation_budget_rejects_without_truncation_or_mutation(self):
        candidate, obligations = synthetic()
        slots = M.build_completion_patch_slots(candidate, obligations)
        for count in (M.MAX_NEW_EVIDENCE_PER_OWNER + 1, M.MAX_NEW_EVIDENCE_TOTAL + 1):
            patch = blank(slots)
            patch["new_evidence"] = [{"owner_cluster_id": "a", "new_evidence_id": f"n{i}",
                                     "observation": F.evidence(["p0001", "p0002"])} for i in range(count)]
            snapshot = copy.deepcopy(candidate)
            with self.assertRaises(M.PhysicalCompletionPatchError):
                M.apply_completion_patch(candidate, obligations, slots, patch)
            self.assertEqual(candidate, snapshot)
            self.assertEqual(len(patch["new_evidence"]), count)

    def test_omitted_slots_stay_unchanged_and_unknown_slot_cannot_edit(self):
        candidate, obligations = synthetic(shared=True)
        slots = M.build_completion_patch_slots(candidate, obligations)
        self.assertEqual(M.apply_completion_patch(candidate, obligations, slots, blank(slots))[0], candidate)
        patch = blank(slots)
        patch["resolution_updates"] = [{"slot_id": "invented", "evidence_refs": [existing(0)]}]
        with self.assertRaises(M.PhysicalCompletionPatchError):
            M.apply_completion_patch(candidate, obligations, slots, patch)

    def test_existing_pair_fixture_passes_gate_without_creating_reciprocal_proof(self):
        initial, candidate, reports, obligations = C.pair_case()
        slots = M.build_completion_patch_slots(candidate, obligations)
        patch = blank(slots)
        slot = next(row for row in slots["resolution_slots"] if row["owner_cluster_id"] == "a")
        patch["resolution_updates"] = [{"slot_id": slot["slot_id"], "evidence_refs": [existing(1)]}]
        result, audit = M.apply_completion_patch(candidate, obligations, slots, patch)
        gated, _ = C.U.gate(initial, result, reports)
        self.assertEqual(gated, result)
        self.assertEqual(result["clusters"][1]["identity_comparisons"], [])
        self.assertFalse(audit["reciprocal_comparisons_inferred"])
        self.assertFalse(audit["independent_observations_created_by_python"])
        reverse = next(row for row in slots["comparison_slots"] if row["owner_cluster_id"] == "b")
        patch["comparison_updates"] = [{"slot_id": reverse["slot_id"], "judgment": "unresolved",
                                        "scope_relation": "comparable", "evidence_refs": []}]
        result, _ = M.apply_completion_patch(candidate, obligations, slots, patch)
        gated, _ = C.U.gate(initial, result, reports)
        self.assertEqual([row["decision"] for row in gated["clusters"][:2]], ["abstain", "abstain"])


if __name__ == "__main__":
    unittest.main()
