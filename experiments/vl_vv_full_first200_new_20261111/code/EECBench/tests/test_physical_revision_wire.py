"""No-model transport, provenance, and unchanged proof/firewall boundaries."""

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
import physical_revision_wire as W  # noqa: E402
import ensemble_shot_entity_detection as runtime  # noqa: E402

SPEC = importlib.util.spec_from_file_location(
    "wire_identity_fixtures", Path(__file__).with_name("test_physical_identity_review.py"))
F = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(F)


def wire(canonical):
    result = copy.deepcopy(canonical)
    result["schema_version"] = W.WIRE_VERSION
    for cluster in result["clusters"]:
        for row in cluster["revision_resolutions"]:
            del row["anonymous_proposal_ids"]
    return result


def one():
    c = F.cluster("original", ["p0002", "p0001"])
    F.resolution(c, "physical_entity", ["original"])
    return F.ledger(c)


def context(canonical, initial_ids=None):
    return {"valid_frame_ids": [10], "expected_shot_id": "synthetic",
            "expected_proposal_ids": [p for c in canonical["clusters"] for p in c["anonymous_proposal_ids"]],
            "initial_cluster_ids": initial_ids if initial_ids is not None else
            [c["cluster_id"] for c in canonical["clusters"]]}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class PhysicalRevisionWireTests(unittest.TestCase):
    def materialize(self, canonical, initial_ids=None):
        return W.materialize_revision_wire(wire(canonical), **context(canonical, initial_ids))

    def test_static_schema_diff_is_only_header_metadata_and_resolution_owner_omission(self):
        expected = copy.deepcopy(W.CANONICAL_SCHEMA)
        expected["$id"] = W.WIRE_SCHEMA["$id"]
        expected["title"] = W.WIRE_SCHEMA["title"]
        expected["properties"]["schema_version"]["enum"] = [W.WIRE_VERSION]
        row = expected["$defs"]["revision_resolution"]
        row["required"].remove("anonymous_proposal_ids")
        del row["properties"]["anonymous_proposal_ids"]
        self.assertEqual(expected, W.WIRE_SCHEMA)
        jsonschema.Draft202012Validator.check_schema(W.WIRE_SCHEMA)
        self.assertEqual(runtime.validate_codex_schema_transport(W.SCHEMA_PATH), W.WIRE_SCHEMA)
        self.assertNotIn('"uniqueItems"', W.SCHEMA_PATH.read_text())

    def test_exact_roundtrip_order_numbers_null_and_inputs_unchanged(self):
        original = one()
        other = F.cluster("other", ["p0003"], decision="abstain")
        original["clusters"].append(other)
        original["warnings"] = ["Literal $() and Unicode 原始 fields remain text"]
        original["clusters"][0]["final_entity"]["entity_confidence"] = -0.0
        payload = wire(original)
        snapshot = json.dumps(payload, ensure_ascii=False)
        result, audit = W.materialize_revision_wire(payload, **context(original))
        self.assertEqual(digest(result), digest(original))
        self.assertEqual(snapshot, json.dumps(payload, ensure_ascii=False))
        self.assertEqual(result["clusters"][0]["revision_resolutions"][0]["anonymous_proposal_ids"],
                         ["p0002", "p0001"])
        self.assertIsNone(result["clusters"][1]["final_entity"])
        self.assertFalse(audit["visual_accuracy_verified"])
        self.assertFalse(audit["visual_proof_created"])
        self.assertFalse(audit["duplicate_key_check_performed"])
        self.assertIn("exact_two_verifier_split", audit["caller_validation_required"])
        result["clusters"][0]["revision_resolutions"][0]["anonymous_proposal_ids"].clear()
        self.assertEqual(payload["clusters"][0]["anonymous_proposal_ids"], ["p0002", "p0001"])

    def test_raw_text_hash_and_each_pointer_are_deterministic(self):
        original = one()
        payload = wire(original)
        text = "\n " + json.dumps(payload, indent=2) + "\n"
        a = W.materialize_revision_wire_json(text, **context(original))
        b = W.materialize_revision_wire_json(text, **context(original))
        self.assertEqual(a, b)
        result, audit = a
        self.assertEqual(audit["raw_json_text_sha256"], hashlib.sha256(text.encode()).hexdigest())
        self.assertEqual(audit["raw_content_sha256"], digest(payload))
        self.assertEqual(audit["canonical_content_sha256"], digest(result))
        self.assertTrue(audit["duplicate_key_check_performed"])
        insertion = audit["resolution_owner_insertions"][0]
        self.assertEqual(insertion["json_pointer"], "/clusters/0/revision_resolutions/0/anonymous_proposal_ids")
        self.assertEqual(insertion["source_json_pointer"], "/clusters/0/anonymous_proposal_ids")
        self.assertEqual(insertion["owner_cluster_id"], "original")
        self.assertEqual(insertion["wire_resolution_content_sha256"],
                         digest(payload["clusters"][0]["revision_resolutions"][0]))
        self.assertEqual(insertion["canonical_resolution_content_sha256"],
                         digest(result["clusters"][0]["revision_resolutions"][0]))

    def test_empty_resolutions_and_empty_inventory_do_not_generate_proof(self):
        for original in (F.ledger(F.cluster()), F.ledger()):
            with self.subTest(clusters=len(original["clusters"])):
                result, audit = self.materialize(original)
                self.assertEqual(result, original)
                self.assertEqual(audit["resolution_owner_insertions"], [])

    def test_legacy_canonical_and_legacy_array_in_wire_are_rejected(self):
        original = one()
        for payload in (original, {**original, "schema_version": W.WIRE_VERSION}):
            with self.subTest(version=payload["schema_version"]):
                with self.assertRaises(W.RevisionWireError):
                    W.materialize_revision_wire(payload, **context(original))
        malformed_legacy = copy.deepcopy(original)
        malformed_legacy["clusters"][0]["revision_resolutions"][0]["anonymous_proposal_ids"] += ["p9999"]
        with self.assertRaises(W.RevisionWireError):
            W.materialize_revision_wire_json(json.dumps(malformed_legacy), **context(original))

    def test_duplicate_json_keys_root_nested_and_escaped_are_rejected(self):
        text = json.dumps(wire(one()))
        variants = [text.replace('"shot_id": "synthetic"', '"shot_id":"other","shot_id":"synthetic"'),
                    text.replace('"axis": "physical_entity"',
                                 '"axis":"proposal_scope","axis":"physical_entity"'),
                    text.replace('"axis": "physical_entity"',
                                 '"axis":"physical_entity","a\\u0078is":"physical_entity"')]
        for bad in variants:
            with self.subTest(text=bad[:40]):
                with self.assertRaisesRegex(W.RevisionWireError, "Duplicate JSON object key"):
                    W.materialize_revision_wire_json(bad, **context(one()))

    def test_nonfinite_raw_including_overflow_and_nonfinite_objects_fail(self):
        text = json.dumps(wire(one()))
        for number in ("NaN", "Infinity", "-Infinity", "1e999"):
            with self.subTest(number=number):
                bad = text.replace('"entity_confidence": 0.6', '"entity_confidence": ' + number)
                with self.assertRaisesRegex(W.RevisionWireError, "Nonfinite"):
                    W.materialize_revision_wire_json(bad, **context(one()))
        for number in (float("nan"), float("inf")):
            payload = wire(one())
            payload["clusters"][0]["final_entity"]["entity_confidence"] = number
            with self.assertRaises(W.RevisionWireError):
                W.materialize_revision_wire(payload, **context(one()))

    def test_malformed_text_wrappers_trailing_objects_and_wrong_root_fail(self):
        text = json.dumps(wire(one()))
        for bad in ("```json\n" + text + "\n```", text + "{}", "[]", "null", "{", "\ud800"):
            with self.subTest(text=repr(bad[:20])):
                with self.assertRaises(W.RevisionWireError):
                    W.materialize_revision_wire_json(bad, **context(one()))

    def test_non_json_python_values_not_silently_coerced(self):
        for value in (("p0001",), {"p0001"}, {1: "wrong"}):
            payload = wire(one())
            payload["warnings"] = value
            with self.assertRaises(W.RevisionWireError):
                W.materialize_revision_wire(payload, **context(one()))

    def test_unknown_axis_initial_target_and_current_partner_fail(self):
        for kind in ("axis", "initial_target", "current_partner"):
            with self.subTest(kind=kind):
                payload = wire(one())
                row = payload["clusters"][0]
                if kind == "axis":
                    row["revision_resolutions"][0]["axis"] = "new_axis"
                elif kind == "initial_target":
                    row["revision_resolutions"][0]["target_cluster_ids"] = ["unknown"]
                else:
                    row["identity_comparisons"] = [{"other_cluster_id": "unknown", "judgment": "unresolved",
                                                    "scope_relation": "unresolved", "evidence_indices": []}]
                with self.assertRaises(W.RevisionWireError):
                    W.materialize_revision_wire(payload, **context(one()))

    def test_unknown_duplicate_missing_and_cross_owner_proposals_fail(self):
        original = F.ledger(F.cluster("a"), F.cluster("b", ["p0002"]))
        for kind in ("unknown", "within", "cross", "missing", "owner"):
            with self.subTest(kind=kind):
                payload = wire(original)
                if kind == "unknown":
                    payload["clusters"][0]["anonymous_proposal_ids"] = ["p9999"]
                elif kind == "within":
                    payload["clusters"][0]["anonymous_proposal_ids"] *= 2
                elif kind == "cross":
                    payload["clusters"][1]["anonymous_proposal_ids"] = ["p0001"]
                elif kind == "missing":
                    payload["clusters"].pop()
                else:
                    payload["clusters"][1]["cluster_id"] = "a"
                with self.assertRaises(W.RevisionWireError):
                    W.materialize_revision_wire(payload, **context(original))

    def test_invalid_context_does_not_alias_duplicates_bool_or_unknown_shot(self):
        original = one()
        variants = [{"valid_frame_ids": [True]}, {"valid_frame_ids": [10.0]},
                    {"valid_frame_ids": []}, {"valid_frame_ids": [10, 10]},
                    {"expected_proposal_ids": ["p0001", "p0001"]},
                    {"initial_cluster_ids": ["original", "original"]},
                    {"initial_cluster_ids": [1]}, {"expected_shot_id": "other"}]
        for change in variants:
            with self.subTest(change=change):
                with self.assertRaises(W.RevisionWireError):
                    W.materialize_revision_wire(wire(original), **{**context(original), **change})

    def test_invalid_resolution_indices_are_never_fixed_or_borrowed(self):
        original = one()
        for indices in ([], [1], [-1], [True], [0.0], [0, 0]):
            with self.subTest(indices=indices):
                payload = wire(original)
                payload["clusters"][0]["revision_resolutions"][0]["evidence_indices"] = indices
                with self.assertRaises(W.RevisionWireError):
                    W.materialize_revision_wire(payload, **context(original))

    def test_duplicate_resolution_slot_and_duplicate_targets_are_not_merged(self):
        original = one()
        for kind in ("slot", "target"):
            payload = wire(original)
            rows = payload["clusters"][0]["revision_resolutions"]
            if kind == "slot":
                rows.append(copy.deepcopy(rows[0]))
            else:
                rows[0]["target_cluster_ids"] *= 2
            with self.assertRaises(W.RevisionWireError):
                W.materialize_revision_wire(payload, **context(original))

    def test_evidence_scope_frame_types_and_empty_observation_stay_fatal(self):
        for change in ({"anonymous_proposal_ids": ["p9999"]}, {"frame_id": 99},
                       {"frame_id": True}, {"frame_id": 10.0}, {"observation": " "}):
            with self.subTest(change=change):
                payload = wire(one())
                payload["clusters"][0]["adjudicator_evidence"][0].update(change)
                with self.assertRaises(W.RevisionWireError):
                    W.materialize_revision_wire(payload, **context(one()))

    def test_partial_or_wrong_cue_pair_witness_still_fails_canonical(self):
        original = F.ledger(F.cluster("a"), F.cluster("b", ["p0002", "p0003"]))
        F.comparison(original["clusters"][0], "b", ["p0001", "p0002", "p0003"],
                     "confirmed_distinct", evidence_key="adjudicator_evidence")
        F.resolution(original["clusters"][0], "instance_correspondence", ["a", "b"], 1)
        for change in ({"anonymous_proposal_ids": ["p0001", "p0002"]}, {"cue_type": "temporal_continuity"}):
            payload = wire(original)
            payload["clusters"][0]["adjudicator_evidence"][1].update(change)
            with self.assertRaisesRegex(W.RevisionWireError, "exact union-scope"):
                W.materialize_revision_wire(payload, **context(original))

    def test_merge_uses_final_owner_order_and_requires_actual_same_witness_at_gate(self):
        initial = F.ledger(F.cluster("a"), F.cluster("b", ["p0002"]))
        merged = F.cluster("renamed", ["p0002", "p0001"])
        F.resolution(merged, "instance_correspondence", ["b", "a"])
        canonical, _ = self.materialize(F.ledger(merged), ["a", "b"])
        gate = F.PhysicalIdentityReviewTests().gate
        result, _ = gate(initial, canonical)
        self.assertEqual(result["clusters"][0]["decision"], "abstain")
        merged["adjudicator_evidence"].append(F.evidence(["p0002", "p0001"], "same_instance_continuity"))
        merged["revision_resolutions"][0]["evidence_indices"] = [1]
        canonical, _ = self.materialize(F.ledger(merged), ["a", "b"])
        self.assertEqual(canonical["clusters"][0]["revision_resolutions"][0]["target_cluster_ids"], ["b", "a"])
        self.assertEqual(gate(initial, canonical)[0]["clusters"][0]["decision"], "accept")

    def test_split_materialization_never_authorizes_split_or_inherits_parent_proof(self):
        initial = F.ledger(F.cluster("parent", ["p0001", "p0002"]))
        children = F.ledger(F.cluster("child_a"), F.cluster("child_b", ["p0002"]))
        for child in children["clusters"]:
            F.resolution(child, "physical_entity", ["parent"])
        canonical, _ = self.materialize(children, ["parent"])
        self.assertEqual(canonical, children)
        with self.assertRaisesRegex(runtime.EnsembleError, "without exact"):
            runtime.enforce_intra_cluster_split_consensus(
                initial_decisions=initial, revised_decisions=canonical,
                split_consensus={"exact_consensus_partitions": []})
        permitted = {"exact_consensus_partitions": [{"cluster_id": "parent",
                      "proposal_partition": [["p0001"], ["p0002"]]}]}
        self.assertEqual(runtime.enforce_intra_cluster_split_consensus(
            initial_decisions=initial, revised_decisions=canonical,
            split_consensus=permitted)["observed_split_count"], 1)
        # Declaring the partner makes the unchanged parent-sized observation legal
        # context, but cannot turn it into an exact-child physical witness.
        for child, partner in zip(children["clusters"], ("child_b", "child_a")):
            F.comparison(child, partner, [], "unresolved", evidence_key="adjudicator_evidence")
            child["adjudicator_evidence"] = [F.evidence(["p0001", "p0002"])]
        canonical, _ = self.materialize(children, ["parent"])
        for child in canonical["clusters"]:
            self.assertFalse(W.physical._resolution(
                child, "physical_entity", frozenset(["parent"]),
                frozenset(child["anonymous_proposal_ids"]), W.physical.PHYSICAL_CUES))

    def test_remapped_final_cluster_does_not_remap_initial_targets_or_pair_endpoints(self):
        original = one()
        original["clusters"][0]["cluster_id"] = "new_final_name"
        result, _ = self.materialize(original, ["original"])
        self.assertEqual(result["clusters"][0]["revision_resolutions"][0]["target_cluster_ids"], ["original"])
        payload = wire(original)
        payload["clusters"][0]["revision_resolutions"][0]["target_cluster_ids"] = ["new_final_name"]
        with self.assertRaisesRegex(W.RevisionWireError, "unknown initial target"):
            W.materialize_revision_wire(payload, **context(original, ["original"]))

    def test_one_resolution_can_keep_explicit_multiple_pair_refs_without_combination(self):
        original = F.ledger(F.cluster("a"), F.cluster("b", ["p0002"]), F.cluster("c", ["p0003"]))
        owner = original["clusters"][0]
        F.comparison(owner, "b", ["p0001", "p0002"], "confirmed_distinct", evidence_key="adjudicator_evidence")
        F.comparison(owner, "c", ["p0001", "p0003"], "confirmed_distinct", evidence_key="adjudicator_evidence")
        F.resolution(owner, "instance_correspondence", ["old_b", "old_a"], 1)
        owner["revision_resolutions"][0]["evidence_indices"] = [2, 1]
        result, _ = self.materialize(original, ["old_a", "old_b"])
        self.assertEqual(result, original)
        self.assertEqual(result["clusters"][0]["revision_resolutions"][0]["evidence_indices"], [2, 1])
        self.assertEqual(result["clusters"][1]["identity_comparisons"], [])

    def test_failed_canonical_validation_never_mutates_input_or_returns_partial_result(self):
        payload = wire(one())
        payload["clusters"][0]["revision_resolutions"][0]["evidence_indices"] = [999]
        before = copy.deepcopy(payload)
        result = None
        with self.assertRaises(W.RevisionWireError):
            result = W.materialize_revision_wire(payload, **context(one()))
        self.assertIsNone(result)
        self.assertEqual(payload, before)
        self.assertNotIn("anonymous_proposal_ids", payload["clusters"][0]["revision_resolutions"][0])


if __name__ == "__main__":
    unittest.main()
