"""Synthetic CPU-only binding coverage and non-laundering regressions."""

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import blind_survey_binding as binding  # noqa: E402
import blind_pixel_survey as survey  # noqa: E402
from test_physical_identity_review import cluster, review, report  # noqa: E402


def views():
    rows = []
    frames = [0, 2, 4, 6, 8, 10]
    for frame in frames:
        rows.append(
            {
                "attachment_index": len(rows) + 1,
                "view_id": f"frame_{frame}_original",
                "frame_id": frame,
                "kind": "original",
                "source_size": [100, 80],
                "crop_xyxy": [0, 0, 100, 80],
                "output_size": [100, 80],
                "scale": 1,
                "path": f"private-frame-{frame}",
                "detector_private": "secret-source-vote",
            }
        )
    for frame in (frames[0], frames[-1]):
        for index, box in enumerate(
            ([0, 0, 60, 48], [40, 0, 100, 48], [0, 32, 60, 80], [40, 32, 100, 80]), 1
        ):
            rows.append(
                {
                    "attachment_index": len(rows) + 1,
                    "view_id": f"frame_{frame}_corner_{index}",
                    "frame_id": frame,
                    "kind": "crop",
                    "source_size": [100, 80],
                    "crop_xyxy": box,
                    "output_size": [60, 48],
                    "scale": 1,
                    "path": f"private-crop-{frame}-{index}",
                }
            )
    return {
        "protocol_version": survey.PROTOCOL_VERSION,
        "views": rows,
        "attachments": [r["path"] for r in rows],
    }


def raw_survey():
    return {
        "schema_version": survey.SCHEMA_VERSION,
        "regions": [
            {
                "region_id": f"r{i:04d}",
                "frame_id": 0,
                "view_id": "frame_0_original",
                "visual_description": "A visible bounded region.",
                "scope_kind": "whole",
                "boundary_status": "clear",
                "bbox_xyxy": [10 * i, 10, 10 * i + 5, 20],
            }
            for i in (1, 2)
        ],
        "tracks": [
            {
                "track_id": "t0001",
                "visual_description": "Unresolved provisional organization.",
                "scope_kind": "unknown",
                "frame_states": [
                    {
                        "frame_id": f,
                        "visibility": "visible" if f == 0 else "uncertain",
                        "region_ids": ["r0001", "r0002"] if f == 0 else [],
                        "note": "Provisional track, no identity claim.",
                    }
                    for f in (0, 2, 4, 6, 8, 10)
                ],
            }
        ],
        "region_relations": [],
        "coverage_notes": "A synthetic incomplete survey.",
    }


def binding_row(cid, pid, refs):
    return {
        "target_cluster_id": cid,
        "anonymous_proposal_id": pid,
        "binding_relation": "complete_region_scope",
        "region_ids": refs,
        "frame_references": [{"region_id": rid, "frame_id": 0} for rid in refs],
        "localization_or_trajectory_conflict": {
            "status": "none_observed",
            "explanation": "No observed conflict in this synthetic record.",
        },
        "limitation": "Exact physical correspondence remains a visual assertion.",
    }


class BlindSurveyBindingTests(unittest.TestCase):
    def setUp(self):
        self.bundle = views()
        self.raw = raw_survey()
        self.targets = {"c1": ["p0001"], "c2": ["p0002"]}
        self.payload = {
            "schema_version": binding.BINDING_VERSION,
            "chain_id": "test_chain",
            "survey_sha256": binding.survey_content_sha256(self.raw),
            "verifier_report": report(
                "verifier_1",
                review(cluster("c1", ["p0001"])),
                review(cluster("c2", ["p0002"])),
            ),
            "bindings": [
                binding_row("c1", "p0001", ["r0001"]),
                binding_row("c2", "p0002", ["r0002"]),
            ],
        }

    def args(self):
        return {
            "locked_survey": self.raw,
            "derived_survey": survey.validate_survey(self.raw, self.bundle),
            "target_proposal_ids_by_cluster": self.targets,
            "chain_id": "test_chain",
            "survey_sha256": binding.survey_content_sha256(self.raw),
            "view_bundle": self.bundle,
        }

    def run_binding(self):
        return binding.validate_binding(self.payload, **self.args())

    def sync_hash(self):
        self.payload["survey_sha256"] = binding.survey_content_sha256(self.raw)

    def test_complete_coverage_never_changes_report_or_survey(self):
        before = copy.deepcopy((self.payload, self.raw, self.bundle, self.targets))
        audit = self.run_binding()
        self.assertTrue(audit["all_target_proposals_covered"])
        self.assertFalse(audit["pixel_truth_verified"])
        self.assertTrue(audit["requires_original_verifier_contract_validation"])
        self.assertEqual(before, (self.payload, self.raw, self.bundle, self.targets))
        audit["records"][0]["region_ids"].append("not-shared")
        self.assertEqual(self.payload["bindings"][0]["region_ids"], ["r0001"])

    def test_missing_unknown_duplicate_or_wrong_owner_is_fatal(self):
        for mode in ("missing", "unknown", "duplicate", "retarget"):
            with self.subTest(mode=mode):
                saved = copy.deepcopy(self.payload)
                if mode == "missing":
                    self.payload["bindings"].pop()
                if mode == "unknown":
                    self.payload["bindings"][0]["anonymous_proposal_id"] = "new"
                if mode == "duplicate":
                    self.payload["bindings"].append(
                        copy.deepcopy(self.payload["bindings"][0])
                    )
                if mode == "retarget":
                    self.payload["bindings"][0]["target_cluster_id"] = "c2"
                with self.assertRaises(ValueError):
                    self.run_binding()
                self.payload = saved

    def test_lock_and_derived_tampering_is_fatal(self):
        for mode in (
            "chain",
            "hash",
            "derived_description",
            "derived_box",
            "derived_raw_field",
        ):
            with self.subTest(mode=mode):
                args = self.args()
                if mode == "chain":
                    args["chain_id"] = "other_chain"
                if mode == "hash":
                    args["survey_sha256"] = "0" * 64
                if mode == "derived_description":
                    args["derived_survey"]["regions"][0]["visual_description"] = (
                        "retargeted"
                    )
                if mode == "derived_box":
                    args["derived_survey"]["regions"][0]["original_bbox_xyxy"][0] += 1
                if mode == "derived_raw_field":
                    args["derived_survey"]["coverage_notes"] = "changed"
                with self.assertRaises(ValueError):
                    binding.validate_binding(self.payload, **args)

    def test_region_and_frame_references_are_exact(self):
        for mode in (
            "unknown",
            "duplicate",
            "missing_frame",
            "other_frame",
            "float",
            "bool",
            "extra_frame",
        ):
            with self.subTest(mode=mode):
                saved = copy.deepcopy(self.payload)
                row = self.payload["bindings"][0]
                if mode == "unknown":
                    row["region_ids"] = ["r9999"]
                if mode == "duplicate":
                    row["region_ids"].append("r0001")
                if mode == "missing_frame":
                    row["frame_references"] = []
                if mode == "other_frame":
                    row["frame_references"][0]["frame_id"] = 2
                if mode == "float":
                    row["frame_references"][0]["frame_id"] = 0.0
                if mode == "bool":
                    row["frame_references"][0]["frame_id"] = False
                if mode == "extra_frame":
                    row["frame_references"].append(
                        copy.deepcopy(row["frame_references"][0])
                    )
                with self.assertRaises(ValueError):
                    self.run_binding()
                self.payload = saved

    def test_partial_multiple_and_unresolved_preserved(self):
        for relation in (
            "part_of_region_scope",
            "multiple_region_scopes",
            "unresolved",
        ):
            with self.subTest(relation=relation):
                self.payload["bindings"][0] = binding_row(
                    "c1", "p0001", ["r0001", "r0002"]
                )
                self.payload["bindings"][0]["binding_relation"] = relation
                self.payload["bindings"][0]["localization_or_trajectory_conflict"][
                    "status"
                ] = "unresolved"
                original = copy.deepcopy(self.payload)
                audit = self.run_binding()
                self.assertTrue(audit["correspondence_risk"])
                self.assertEqual(self.payload, original)
                self.assertEqual(audit["records"][0]["binding_relation"], relation)

    def test_no_region_is_valid_only_as_unresolved(self):
        row = self.payload["bindings"][0]
        row["region_ids"] = []
        row["frame_references"] = []
        with self.assertRaises(ValueError):
            self.run_binding()
        row["binding_relation"] = "unresolved"
        self.assertTrue(self.run_binding()["correspondence_risk"])

    def test_multiple_requires_multiple_references_not_copying(self):
        self.payload["bindings"][0]["binding_relation"] = "multiple_region_scopes"
        with self.assertRaises(ValueError):
            self.run_binding()

    def test_shared_track_is_not_same_instance_proof(self):
        r = self.payload["verifier_report"]["reviews"][0]
        r["identity_comparisons"] = [
            {
                "other_cluster_id": "c2",
                "judgment": "confirmed_distinct",
                "scope_relation": "comparable",
                "evidence_indices": [],
            }
        ]
        self.assertEqual(self.run_binding()["relationship_diagnostics"], [])

    def test_explicit_conflicting_identity_is_diagnostic_not_repair(self):
        self.raw["region_relations"] = [
            {
                "region_id_a": "r0001",
                "region_id_b": "r0002",
                "identity": "distinct",
                "scope_relation": "comparable",
                "visual_evidence": "Separate boundaries are asserted.",
            }
        ]
        self.sync_hash()
        r = self.payload["verifier_report"]["reviews"][0]
        r["identity_comparisons"] = [
            {
                "other_cluster_id": "c2",
                "judgment": "confirmed_same_scope",
                "scope_relation": "comparable",
                "evidence_indices": [],
            }
        ]
        original = copy.deepcopy(self.payload)
        audit = self.run_binding()
        self.assertEqual(len(audit["relationship_diagnostics"]), 1)
        self.assertEqual(self.payload, original)
        self.assertFalse(audit["scope_or_evidence_rebound"])
        self.payload["bindings"][0]["binding_relation"] = "part_of_region_scope"
        self.assertEqual(self.run_binding()["relationship_diagnostics"], [])

    def test_same_region_complete_claim_cannot_hide_distinct_report(self):
        self.payload["bindings"][1] = binding_row("c2", "p0002", ["r0001"])
        r = self.payload["verifier_report"]["reviews"][0]
        r["identity_comparisons"] = [
            {
                "other_cluster_id": "c2",
                "judgment": "confirmed_distinct",
                "scope_relation": "comparable",
                "evidence_indices": [],
            }
        ]
        self.assertEqual(len(self.run_binding()["relationship_diagnostics"]), 1)

    def test_complete_mapping_across_explicit_distinct_regions_is_only_diagnostic(self):
        self.raw["region_relations"] = [
            {
                "region_id_a": "r0001",
                "region_id_b": "r0002",
                "identity": "distinct",
                "scope_relation": "comparable",
                "visual_evidence": "Two separated outlines.",
            }
        ]
        self.sync_hash()
        self.payload["bindings"][0] = binding_row("c1", "p0001", ["r0001", "r0002"])
        original = copy.deepcopy(self.payload)
        audit = self.run_binding()
        self.assertIn(
            "complete_binding_spans_explicit_distinct_regions",
            [d["kind"] for d in audit["relationship_diagnostics"]],
        )
        self.assertEqual(self.payload, original)

    def test_null_survey_geometry_preserved_and_audited(self):
        self.raw["regions"][0].update(bbox_xyxy=None, boundary_status="uncertain")
        self.sync_hash()
        audit = self.run_binding()
        self.assertTrue(audit["correspondence_risk"])
        self.assertFalse(
            audit["referenced_survey_region_limitations"][0]["geometry_available"]
        )
        self.assertEqual(
            self.payload["bindings"][0]["binding_relation"], "complete_region_scope"
        )

    def test_schema_preserves_full_original_verifier_contract(self):
        schema = json.loads(binding.SCHEMA_PATH.read_text())
        original = json.loads(
            (ROOT / "schemas/codex_entity_verification_v0.6.schema.json").read_text()
        )
        expected = {
            k: v
            for k, v in original.items()
            if k not in ("$schema", "$id", "title", "$defs")
        }
        self.assertEqual(schema["properties"]["verifier_report"], expected)
        for key, value in original["$defs"].items():
            self.assertEqual(schema["$defs"][key], value)
        del self.payload["verifier_report"]["reviews"][0]["evidence"]
        with self.assertRaises(ValueError):
            self.run_binding()

    def test_empty_survey_retains_all_unresolved_proposals(self):
        self.raw["regions"] = []
        self.raw["tracks"] = []
        self.sync_hash()
        for row in self.payload["bindings"]:
            row.update(
                binding_relation="unresolved", region_ids=[], frame_references=[]
            )
        self.assertEqual(self.run_binding()["target_proposal_count"], 2)

    def test_empty_targets_valid_but_not_an_accuracy_claim(self):
        self.targets = {}
        self.payload["verifier_report"]["reviews"] = []
        self.payload["bindings"] = []
        audit = self.run_binding()
        self.assertTrue(audit["all_target_proposals_covered"])
        self.assertFalse(audit["discovery_completeness_established"])

    def test_target_map_and_report_scope_mismatches_are_fatal(self):
        args = self.args()
        args["target_proposal_ids_by_cluster"]["c2"] = ["p0001"]
        with self.assertRaises(ValueError):
            binding.validate_binding(self.payload, **args)
        self.targets = {"c1": ["p0001"], "c2": ["p0002"]}
        self.payload["verifier_report"]["reviews"].pop()
        with self.assertRaises(ValueError):
            self.run_binding()

    def test_partial_visible_boundary_does_not_force_whole_scope_truth(self):
        self.raw["regions"][0].update(boundary_status="partial", scope_kind="unknown")
        self.sync_hash()
        audit = self.run_binding()
        self.assertEqual(
            audit["records"][0]["binding_relation"], "complete_region_scope"
        )
        self.assertFalse(audit["pixel_truth_verified"])

    def test_prompt_nested_report_and_whitelisted_geometry(self):
        standard = 'Return only the original verifier JSON.\n{"schema_version":"physical_identity_review_v0.6"}'
        args = self.args()
        args.pop("target_proposal_ids_by_cluster")
        prompt = binding.build_binding_prompt(standard_verifier_prompt=standard, **args)
        self.assertIn(standard, prompt)
        self.assertIn("verifier_report ONLY", prompt)
        self.assertIn("test_chain", prompt)
        self.assertNotIn("private-frame", prompt)
        self.assertNotIn("secret-source-vote", prompt)
        self.assertIn("NOT same-instance proof", prompt)

    def test_finite_hash_and_unknown_output_field(self):
        with self.assertRaises(ValueError):
            binding.survey_content_sha256({"x": float("nan")})
        self.payload["bindings"][0]["corrected_bbox"] = [0, 0, 1, 1]
        with self.assertRaises(ValueError):
            self.run_binding()

    def test_local_schema_transport_preflight_only(self):
        from ensemble_shot_entity_detection import validate_codex_schema_transport

        validate_codex_schema_transport(binding.SCHEMA_PATH)


if __name__ == "__main__":
    unittest.main()
