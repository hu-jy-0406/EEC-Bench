import contextlib
import io
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import ensemble_shot_entity_detection as ENSEMBLE  # noqa: E402
import prompt_unbound_common as MODULE  # noqa: E402
import run_prompt_unbound_prefilter as PREFILTER  # noqa: E402


def entity(entity_id, name, box=None):
    boxes = []
    if box is not None:
        boxes.append(
            {
                "frame_id": 10,
                "bbox_xyxy_normalized": box,
                "score": 0.8,
            }
        )
    return {
        "id": entity_id,
        "name": name,
        "grounding": {"status": "grounded" if boxes else "not_found", "boxes": boxes},
    }


def base_graph():
    return {
        "schema_version": "0.1",
        "video_id": "episode",
        "shot_id": "shot1",
        "shot_metadata": {
            "source_video": "/tmp/shot1.mp4",
            "num_frames": 11,
            "fps": 5.0,
            "duration_sec": 2.2,
            "reference_frame_ids": [10],
        },
        "extraction_metadata": {},
        "entities": [],
        "relations": [],
        "warnings": [],
    }


def scheduled_entity(entity_id, name, box=None):
    result = entity(entity_id, name, box)
    result.update(
        {
            "description": name,
            "entity_type": "object",
            "schedule_category": "objects",
        }
    )
    result["grounding"]["query"] = name
    return result


def ensemble_proposal(local_id, name="desk", frame_id=10, bbox=None):
    if bbox is None:
        bbox = [0.1, 0.1, 0.9, 0.9]
    return {
        "local_id": local_id,
        "proposed_name": name,
        "canonical_head": name,
        "entity_type": "furniture",
        "granularity": "whole_instance",
        "attributes": [],
        "evidence_frame_ids": [frame_id],
        "coarse_locators": [{"frame_id": frame_id, "description": "lower center"}],
        "frame_presence": [
            {
                "frame_id": frame_id,
                "status": "visible",
                "description": "localized at lower center",
                "bbox_xyxy_normalized": bbox,
            }
        ],
        "self_confidence": 0.8,
        "uncertainty_flags": [],
    }


def detector_coverage_audit(entities, frame_ids=None, residual_added_local_ids=None):
    if frame_ids is None:
        frame_ids = sorted(
            {
                presence["frame_id"]
                for proposal in entities
                for presence in proposal["frame_presence"]
            }
        )
    local_ids = [proposal["local_id"] for proposal in entities]
    residual_ids = list(residual_added_local_ids or [])
    spatial_cells = [
        {
            "cell": cell,
            "best_frame_id": frame_ids[0],
            "represented_local_ids": local_ids if index == 0 else [],
        }
        for index, cell in enumerate(ENSEMBLE.DETECTOR_SPATIAL_CELLS)
    ]
    content_strata = [
        {
            "stratum": stratum,
            "represented_local_ids": local_ids if index == 0 else [],
        }
        for index, stratum in enumerate(ENSEMBLE.DETECTOR_CONTENT_STRATA)
    ]
    return {
        "reviewed_frame_ids": list(frame_ids),
        "spatial_cells": spatial_cells,
        "content_strata": content_strata,
        "temporal_reveal_checks": [
            {
                "earlier_frame_id": earlier,
                "later_frame_id": later,
                "newly_revealed_cells": [],
                "added_local_ids": [],
            }
            for earlier, later in zip(frame_ids, frame_ids[1:])
        ],
        "residual_added_local_ids": residual_ids,
    }


def ensemble_ledger(
    detector_id,
    source_kind,
    entities,
    shot_id="shot1",
):
    return {
        "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
        "shot_id": shot_id,
        "detector_id": detector_id,
        "source_kind": source_kind,
        "accessed_input_paths": [],
        "entities": entities,
        "coverage_audit": detector_coverage_audit(entities),
        "warnings": [],
    }


class PromptUnboundPipelineTest(unittest.TestCase):
    def test_ensemble_codex_schemas_use_supported_fixed_value_form(self):
        for schema_path in (
            ENSEMBLE.DETECTOR_SCHEMA,
            ENSEMBLE.ADJUDICATION_SCHEMA,
            ENSEMBLE.VERIFICATION_SCHEMA,
            ENSEMBLE.MATCHING_SCHEMA,
            ENSEMBLE.PROJECT_ROOT / "schemas/codex_entity_adjudication_v0.6.schema.json",
            ENSEMBLE.PROJECT_ROOT / "schemas/codex_entity_verification_v0.6.schema.json",
        ):
            schema_text = schema_path.read_text(encoding="utf-8")
            payload = json.loads(schema_text)
            self.assertIsInstance(payload, dict)
            self.assertNotIn("uniqueItems", schema_text)
            self.assertNotIn('"const"', schema_text)
            protocol_schema = payload["properties"]["protocol_version"]
            self.assertEqual(protocol_schema["type"], "string")
            self.assertEqual(protocol_schema["enum"], [ENSEMBLE.PROTOCOL_VERSION])

    def test_active_codex_output_schemas_have_no_ref_siblings(self):
        schema_paths = (
            ENSEMBLE.DETECTOR_SCHEMA,
            ENSEMBLE.ADJUDICATION_SCHEMA,
            ENSEMBLE.VERIFICATION_SCHEMA,
            ENSEMBLE.MATCHING_SCHEMA,
            ENSEMBLE.GRANULARITY_FAMILY_SCHEMA,
            ENSEMBLE.ACCEPTED_ASSEMBLY_SCHEMA,
            ENSEMBLE.PROJECT_ROOT / "schemas/codex_entity_adjudication_v0.6.schema.json",
            ENSEMBLE.PROJECT_ROOT / "schemas/codex_entity_verification_v0.6.schema.json",
        )

        def assert_compatible(value, *, schema_path, location="$root"):
            if isinstance(value, dict):
                if "$ref" in value:
                    self.assertEqual(
                        set(value),
                        {"$ref"},
                        f"{schema_path.name}:{location} has a $ref sibling",
                    )
                for key, child in value.items():
                    assert_compatible(
                        child,
                        schema_path=schema_path,
                        location=f"{location}/{key}",
                    )
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    assert_compatible(
                        child,
                        schema_path=schema_path,
                        location=f"{location}/{index}",
                    )

        for schema_path in schema_paths:
            assert_compatible(
                json.loads(schema_path.read_text(encoding="utf-8")),
                schema_path=schema_path,
            )

    def test_inventory_registry_boundary_and_semantic_projection(self):
        registry = ENSEMBLE.build_prompt_bound_registry(
            "shot1",
            [scheduled_entity("pb1", "woman", [0.1, 0.1, 0.9, 0.9])],
        )
        semantic = ENSEMBLE.semantic_prompt_bound_registry(registry)
        self.assertEqual(
            set(semantic["entities"][0]),
            {"registry_id", "name", "description", "entity_type"},
        )
        self.assertNotIn("detected_boxes", json.dumps(semantic))
        base = ENSEMBLE._inventory_base_prompt(
            shot_id="shot1",
            shot_manifest={"reference_frames": []},
            allowed_input_paths=[],
            skill_text="inventory policy",
        )
        self.assertNotIn('"name": "woman"', base)
        matcher = ENSEMBLE._matcher_prompt(
            shot_id="shot1",
            shot_manifest={"reference_frames": []},
            semantic_registry=semantic,
            inventory_view={"clusters": []},
            allowed_input_paths=[],
            skill_text="matching policy",
        )
        self.assertIn('"name": "woman"', matcher)
        self.assertNotIn("detected_boxes", matcher)

    def test_presence_and_matcher_accounting_are_exhaustive(self):
        ledger = ensemble_ledger(
            "detector_1",
            "detector",
            [ensemble_proposal("d1_e1")],
        )
        with self.assertRaises(ENSEMBLE.EnsembleError):
            ENSEMBLE.validate_ledger(
                ledger,
                shot_id="shot1",
                detector_id="detector_1",
                source_kind="detector",
                valid_frame_ids=[10, 20],
                allowed_input_paths=[],
            )
        matches = {
            "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
            "shot_id": "shot1",
            "matcher_id": "prompt_bound_matcher",
            "matches": [
                {
                    "cluster_id": "c1",
                    "status": "unbound",
                    "matched_registry_ids": [],
                    "evidence_frame_ids": [10],
                    "reason": "not a registry instance",
                }
            ],
            "warnings": [],
        }
        with self.assertRaises(ENSEMBLE.EnsembleError):
            ENSEMBLE.validate_prompt_bound_matches(
                matches,
                shot_id="shot1",
                accepted_cluster_ids=["c1", "c2"],
                registry_ids=["pb1"],
                valid_frame_ids=[10],
            )

    def test_detector_presence_requires_tight_boxes_only_when_visible(self):
        valid = ensemble_ledger(
            "detector_1",
            "detector",
            [ensemble_proposal("d1_e1")],
        )
        ENSEMBLE.validate_ledger(
            valid,
            shot_id="shot1",
            detector_id="detector_1",
            source_kind="detector",
            valid_frame_ids=[10],
            allowed_input_paths=[],
        )

        missing_box = json.loads(json.dumps(valid))
        del missing_box["entities"][0]["frame_presence"][0][
            "bbox_xyxy_normalized"
        ]
        with self.assertRaisesRegex(ENSEMBLE.EnsembleError, "valid tight box"):
            ENSEMBLE.validate_ledger(
                missing_box,
                shot_id="shot1",
                detector_id="detector_1",
                source_kind="detector",
                valid_frame_ids=[10],
                allowed_input_paths=[],
            )

        nonvisible_box = json.loads(json.dumps(valid))
        nonvisible_box["entities"][0]["frame_presence"].append(
            {
                "frame_id": 20,
                "status": "absent",
                "description": "outside the frame",
                "bbox_xyxy_normalized": [0.1, 0.1, 0.2, 0.2],
            }
        )
        with self.assertRaisesRegex(ENSEMBLE.EnsembleError, "box must be null"):
            ENSEMBLE.validate_ledger(
                nonvisible_box,
                shot_id="shot1",
                detector_id="detector_1",
                source_kind="detector",
                valid_frame_ids=[10, 20],
                allowed_input_paths=[],
            )

    def test_detector_attribute_evidence_frames_are_current_and_unique(self):
        proposal = ensemble_proposal("d1_e1")
        proposal["attributes"] = [
            {
                "name": "material",
                "value": "wood",
                "evidence_frame_ids": [10],
            }
        ]
        valid = ensemble_ledger("detector_1", "detector", [proposal])
        validation_kwargs = {
            "shot_id": "shot1",
            "detector_id": "detector_1",
            "source_kind": "detector",
            "valid_frame_ids": [10],
            "allowed_input_paths": [],
        }
        ENSEMBLE.validate_ledger(valid, **validation_kwargs)

        for label, evidence in (
            ("empty", []),
            ("duplicate", [10, 10]),
            ("unknown", [20]),
        ):
            with self.subTest(case=label):
                invalid = json.loads(json.dumps(valid))
                invalid["entities"][0]["attributes"][0][
                    "evidence_frame_ids"
                ] = evidence
                with self.assertRaisesRegex(
                    ENSEMBLE.EnsembleError, "invalid evidence frame IDs"
                ):
                    ENSEMBLE.validate_ledger(invalid, **validation_kwargs)

    def test_detector_coverage_audit_strict_structure_with_nonfatal_cross_indexes(
        self,
    ):
        proposal = ensemble_proposal("d1_e1")
        proposal["frame_presence"].append(
            {
                "frame_id": 20,
                "status": "visible",
                "description": "localized at lower center",
                "bbox_xyxy_normalized": [0.1, 0.1, 0.9, 0.9],
            }
        )
        ledger = ensemble_ledger("detector_1", "detector", [proposal])
        ledger["coverage_audit"] = detector_coverage_audit(
            [proposal], frame_ids=[10, 20]
        )
        validation_kwargs = {
            "shot_id": "shot1",
            "detector_id": "detector_1",
            "source_kind": "detector",
            "valid_frame_ids": [10, 20],
            "allowed_input_paths": [],
        }
        diagnostics = ENSEMBLE.validate_ledger(ledger, **validation_kwargs)
        self.assertEqual(diagnostics["unindexed_spatial_local_ids"], [])
        self.assertEqual(diagnostics["unindexed_content_stratum_local_ids"], [])
        self.assertFalse(diagnostics["has_nonfatal_cross_index_omissions"])

        missing_audit = json.loads(json.dumps(ledger))
        missing_audit.pop("coverage_audit")
        with self.assertRaisesRegex(ENSEMBLE.EnsembleError, "coverage_audit"):
            ENSEMBLE.validate_ledger(missing_audit, **validation_kwargs)

        wrong_frames = json.loads(json.dumps(ledger))
        wrong_frames["coverage_audit"]["reviewed_frame_ids"] = [20, 10]
        with self.assertRaisesRegex(ENSEMBLE.EnsembleError, "reviewed_frame_ids"):
            ENSEMBLE.validate_ledger(wrong_frames, **validation_kwargs)

        missing_cell = json.loads(json.dumps(ledger))
        missing_cell["coverage_audit"]["spatial_cells"].pop()
        with self.assertRaisesRegex(ENSEMBLE.EnsembleError, "all nine cells"):
            ENSEMBLE.validate_ledger(missing_cell, **validation_kwargs)

        duplicate_cell = json.loads(json.dumps(ledger))
        duplicate_cell["coverage_audit"]["spatial_cells"][1]["cell"] = (
            duplicate_cell["coverage_audit"]["spatial_cells"][0]["cell"]
        )
        with self.assertRaisesRegex(ENSEMBLE.EnsembleError, "exactly once"):
            ENSEMBLE.validate_ledger(duplicate_cell, **validation_kwargs)

        missing_stratum = json.loads(json.dumps(ledger))
        missing_stratum["coverage_audit"]["content_strata"].pop()
        with self.assertRaisesRegex(ENSEMBLE.EnsembleError, "all five strata"):
            ENSEMBLE.validate_ledger(missing_stratum, **validation_kwargs)

        duplicate_stratum = json.loads(json.dumps(ledger))
        duplicate_stratum["coverage_audit"]["content_strata"][1]["stratum"] = (
            duplicate_stratum["coverage_audit"]["content_strata"][0]["stratum"]
        )
        with self.assertRaisesRegex(ENSEMBLE.EnsembleError, "exactly once"):
            ENSEMBLE.validate_ledger(duplicate_stratum, **validation_kwargs)

        wrong_pair = json.loads(json.dumps(ledger))
        wrong_pair["coverage_audit"]["temporal_reveal_checks"][0][
            "later_frame_id"
        ] = 10
        with self.assertRaisesRegex(ENSEMBLE.EnsembleError, "adjacent frame pair"):
            ENSEMBLE.validate_ledger(wrong_pair, **validation_kwargs)

        unknown_local_id = json.loads(json.dumps(ledger))
        unknown_local_id["coverage_audit"]["spatial_cells"][0][
            "represented_local_ids"
        ] = ["not_a_proposal"]
        with self.assertRaisesRegex(ENSEMBLE.EnsembleError, "unknown local IDs"):
            ENSEMBLE.validate_ledger(unknown_local_id, **validation_kwargs)

        unknown_temporal_local_id = json.loads(json.dumps(ledger))
        unknown_temporal_local_id["coverage_audit"]["temporal_reveal_checks"][0][
            "added_local_ids"
        ] = ["not_a_proposal"]
        with self.assertRaisesRegex(ENSEMBLE.EnsembleError, "unknown local IDs"):
            ENSEMBLE.validate_ledger(
                unknown_temporal_local_id, **validation_kwargs
            )

        missing_residual_field = json.loads(json.dumps(ledger))
        missing_residual_field["coverage_audit"].pop("residual_added_local_ids")
        with self.assertRaisesRegex(ENSEMBLE.EnsembleError, "local IDs"):
            ENSEMBLE.validate_ledger(missing_residual_field, **validation_kwargs)

        missing_spatial_representation = json.loads(json.dumps(ledger))
        missing_spatial_representation["coverage_audit"]["spatial_cells"][0][
            "represented_local_ids"
        ] = []
        diagnostics = ENSEMBLE.validate_ledger(
            missing_spatial_representation, **validation_kwargs
        )
        self.assertEqual(diagnostics["unindexed_spatial_local_ids"], ["d1_e1"])
        self.assertTrue(diagnostics["has_nonfatal_cross_index_omissions"])

        missing_stratum_representation = json.loads(json.dumps(ledger))
        missing_stratum_representation["coverage_audit"]["content_strata"][0][
            "represented_local_ids"
        ] = []
        diagnostics = ENSEMBLE.validate_ledger(
            missing_stratum_representation, **validation_kwargs
        )
        self.assertEqual(
            diagnostics["unindexed_content_stratum_local_ids"], ["d1_e1"]
        )
        self.assertTrue(diagnostics["has_nonfatal_cross_index_omissions"])

        nonresidual_temporal_addition = json.loads(json.dumps(ledger))
        nonresidual_temporal_addition["coverage_audit"]["temporal_reveal_checks"][
            0
        ]["added_local_ids"] = ["d1_e1"]
        diagnostics = ENSEMBLE.validate_ledger(
            nonresidual_temporal_addition, **validation_kwargs
        )
        self.assertEqual(diagnostics["pass2_residual_local_ids"], [])
        self.assertEqual(
            diagnostics["temporal_revealed_or_confirmed_local_ids"], ["d1_e1"]
        )

    def test_box_trajectory_flags_switch_without_swallowing_small_held_prop(self):
        def boxed_proposal(proposal_id, boxes):
            return {
                "anonymous_proposal_id": proposal_id,
                "frame_presence": [
                    {
                        "frame_id": frame_id,
                        "status": "visible",
                        "description": "tightly localized",
                        "bbox_xyxy_normalized": bbox,
                    }
                    for frame_id, bbox in boxes.items()
                ],
            }

        paper_box = [0.10, 0.10, 0.30, 0.25]
        other_box = [0.60, 0.60, 0.82, 0.78]
        proposals = [
            boxed_proposal("p_paper", {frame: paper_box for frame in range(4)}),
            boxed_proposal("p_other", {frame: other_box for frame in (4, 5)}),
            boxed_proposal(
                "p_switch",
                {
                    **{frame: paper_box for frame in range(4)},
                    **{frame: other_box for frame in (4, 5)},
                },
            ),
            boxed_proposal(
                "p_person", {frame: [0.35, 0.10, 0.90, 0.95] for frame in range(6)}
            ),
            boxed_proposal(
                "p_pen", {frame: [0.52, 0.42, 0.55, 0.50] for frame in range(6)}
            ),
        ]
        source_map = {
            "mappings": [
                {
                    "anonymous_proposal_id": proposal["anonymous_proposal_id"],
                    "source": "detector_1",
                }
                for proposal in proposals
            ]
        }
        challenges = ENSEMBLE.build_box_redundancy_challenges(
            {"proposals": proposals}, source_map
        )
        self.assertEqual(
            [item["target_proposal_id"] for item in challenges], ["p_switch"]
        )
        self.assertEqual(challenges[0]["pattern"], "track_switch_candidate")
        self.assertEqual(
            challenges[0]["covering_proposal_ids"], ["p_other", "p_paper"]
        )
        self.assertEqual(challenges[0]["coverage_ratio"], 1.0)

    def test_prefilter_defaults_to_high_recall_prompt_v03(self):
        self.assertEqual(
            PREFILTER.PROMPT_VERSION,
            "shot_prompt_unbound_entity_graph_v0.3",
        )
        self.assertEqual(
            PREFILTER.DEFAULT_PROMPT.name,
            "shot_prompt_unbound_entity_graph_v0.3.md",
        )
        prompt = PREFILTER.DEFAULT_PROMPT.read_text(encoding="utf-8")
        self.assertIn("a detected box is not an exclusion mask", prompt)
        self.assertIn("prompt-bound location", prompt)
        self.assertIn("major support or container region", prompt)
        self.assertIn(
            "Repeat this inspection around every supplied detector box",
            prompt,
        )
        self.assertIn("unrelated to the main action", prompt)
        self.assertIn("They belong to the person node", prompt)
        self.assertIn("ordinary functional-whole/component conflicts", prompt)
        args = PREFILTER.parse_args(["/tmp/experiment"])
        self.assertEqual(args.entity_detection_mode, "single")
        self.assertEqual(args.ensemble_max_workers, 4)

    def test_schedule_targets_use_registry_descriptions(self):
        schedule = {
            "characters": ["The Woman"],
            "places": ["The Study"],
            "objects": [],
        }
        descriptions = {
            "Character 1": {
                "name": "The Woman",
                "description": "A woman with short dark hair.",
            }
        }
        targets = MODULE.targets_for_shot(schedule, descriptions)
        self.assertEqual(
            [target.entity_type for target in targets], ["character", "location"]
        )
        self.assertEqual(targets[0].description, "A woman with short dark hair.")
        self.assertEqual(targets[1].description, "The Study")

    def test_shots_map_to_numerically_sorted_schedule_keys(self):
        shots = [Path("shot1.mp4"), Path("shot2.mp4"), Path("shot10.mp4")]
        schedule = {"10:1": {}, "2:1": {}, "1:1": {}}
        mapped = MODULE.map_shots_to_schedule(shots, schedule)
        self.assertEqual([key for _, key in mapped], ["1:1", "2:1", "10:1"])

    def test_articles_do_not_change_entity_name(self):
        self.assertEqual(
            MODULE.name_similarity("The red notebook", "red notebook"), 1.0
        )

    def test_name_alone_does_not_delete_when_prompt_detector_misses(self):
        result = MODULE.classify_graph_entities(
            [entity("e1", "woman")],
            [entity("pb1", "The woman")],
        )
        self.assertEqual(result["prompt_bound_graph_entity_ids"], [])
        self.assertEqual(result["prompt_unbound_graph_entity_ids"], ["e1"])
        self.assertEqual(
            result["all_pair_comparisons"][0]["match_reason"],
            "semantic_identity_without_grounding",
        )

    def test_name_and_box_match_can_resolve_nonexact_name(self):
        result = MODULE.classify_graph_entities(
            [entity("e1", "notebook", [0.1, 0.1, 0.4, 0.4])],
            [entity("pb1", "red notebook", [0.1, 0.1, 0.4, 0.4])],
        )
        self.assertEqual(result["prompt_bound_graph_entity_ids"], ["e1"])
        self.assertEqual(result["matches"][0]["match_reason"], "name_plus_grounding")

    def test_matching_is_one_to_one(self):
        result = MODULE.classify_graph_entities(
            [
                entity("e1", "woman", [0.1, 0.1, 0.5, 0.9]),
                entity("e2", "woman", [0.1, 0.1, 0.5, 0.9]),
            ],
            [entity("pb1", "The woman", [0.1, 0.1, 0.5, 0.9])],
        )
        self.assertEqual(len(result["prompt_bound_graph_entity_ids"]), 1)
        self.assertEqual(len(result["prompt_unbound_graph_entity_ids"]), 1)

    def test_near_identical_boxes_do_not_delete_semantically_unrelated_entity(self):
        result = MODULE.classify_graph_entities(
            [entity("e1", "writing implement", [0.1, 0.1, 0.5, 0.9])],
            [entity("pb1", "The woman", [0.1, 0.1, 0.5, 0.9])],
        )
        self.assertEqual(result["prompt_bound_graph_entity_ids"], [])
        self.assertEqual(result["prompt_unbound_graph_entity_ids"], ["e1"])
        self.assertEqual(
            result["all_pair_comparisons"][0]["match_reason"],
            "grounding_overlap_without_semantic_identity",
        )

    def test_pale_book_is_not_deleted_as_red_notebook_from_box_overlap(self):
        result = MODULE.classify_graph_entities(
            [entity("e1", "pale book", [0.1, 0.1, 0.5, 0.5])],
            [entity("pb1", "red notebook", [0.1, 0.1, 0.5, 0.5])],
        )
        self.assertEqual(result["prompt_bound_graph_entity_ids"], [])
        self.assertEqual(result["prompt_unbound_graph_entity_ids"], ["e1"])

    def test_strong_ensemble_evidence_blocks_postcheck_veto(self):
        result = MODULE.classify_graph_entities(
            [entity("e1", "notebook", [0.1, 0.1, 0.5, 0.5])],
            [entity("pb1", "red notebook", [0.1, 0.1, 0.5, 0.5])],
            protected_unbound_entity_ids=["e1"],
        )
        self.assertEqual(result["prompt_bound_graph_entity_ids"], [])
        self.assertEqual(result["prompt_unbound_graph_entity_ids"], ["e1"])
        self.assertEqual(len(result["protected_unbound_conflicts"]), 1)
        self.assertEqual(
            result["protected_unbound_conflicts"][0]["match_reason"],
            "protected_unbound_evidence",
        )

    def test_filter_removes_incident_relations(self):
        graph = {
            "entities": [
                entity("e1", "woman"),
                entity("e2", "lamp"),
                entity("e3", "desk"),
            ],
            "relations": [
                {"id": "r1", "subject_id": "e1", "object_id": "e2"},
                {"id": "r2", "subject_id": "e2", "object_id": "e3"},
            ],
            "warnings": [],
        }
        filtered = MODULE.filter_graph_to_unbound(graph, ["e1"], warning="filtered")
        self.assertEqual([item["id"] for item in filtered["entities"]], ["e2", "e3"])
        self.assertEqual([item["id"] for item in filtered["relations"]], ["r2"])
        self.assertIn("filtered", filtered["warnings"])

    def test_prefilter_prompt_contains_names_and_detector_boxes(self):
        sample = MODULE.shot_graph.VideoSample(
            frames={0: None, 10: None},
            frame_paths={},
            num_frames=11,
            fps=5.0,
        )
        prompt_entity = entity("pb1", "The woman", [0.1, 0.2, 0.5, 0.9])
        prompt_entity.update(
            {"description": "A woman with dark hair", "entity_type": "character"}
        )
        with tempfile.TemporaryDirectory() as directory:
            template = Path(directory) / "prompt.md"
            template.write_text("Only extras.", encoding="utf-8")
            prompt = MODULE.build_prompt_unbound_codex_prompt(
                sample, [prompt_entity], template
            )
        self.assertIn('"name": "The woman"', prompt)
        self.assertIn('"bbox_xyxy_normalized"', prompt)
        self.assertIn("frame_id=10", prompt)

    def test_prompt_bound_graph_keeps_positive_detections_and_ledgers_misses(self):
        with tempfile.TemporaryDirectory() as directory:
            frame_path = Path(directory) / "frame_000010.jpg"
            Image.new("RGB", (20, 20), "white").save(frame_path)
            sample = MODULE.shot_graph.VideoSample(
                frames={10: None},
                frame_paths={10: frame_path},
                num_frames=11,
                fps=5.0,
            )
            graph = MODULE.build_prompt_bound_graph(
                [
                    scheduled_entity("pb1", "red notebook", [0.1, 0.1, 0.5, 0.5]),
                    scheduled_entity("pb2", "missing cup"),
                ],
                base_graph(),
                sample,
                n_grounding_calls=2,
            )
        self.assertEqual([item["name"] for item in graph["entities"]], ["red notebook"])
        self.assertEqual(
            set(graph["entities"][0]["grounding"]["boxes"][0]),
            {"frame_id", "bbox_xyxy_normalized", "score"},
        )
        self.assertIn("missing cup", graph["warnings"][-1])

    def test_prefilter_total_graph_remaps_ids_and_preserves_unbound_relations(self):
        with tempfile.TemporaryDirectory() as directory:
            frame_path = Path(directory) / "frame_000010.jpg"
            Image.new("RGB", (20, 20), "white").save(frame_path)
            sample = MODULE.shot_graph.VideoSample(
                frames={10: None},
                frame_paths={10: frame_path},
                num_frames=11,
                fps=5.0,
            )
            bound = MODULE.build_prompt_bound_graph(
                [scheduled_entity("pb1", "woman", [0.0, 0.0, 0.4, 1.0])],
                base_graph(),
                sample,
                n_grounding_calls=1,
            )
            unbound = MODULE.build_prompt_bound_graph(
                [
                    scheduled_entity("u1", "lamp", [0.5, 0.0, 0.8, 0.5]),
                    scheduled_entity("u2", "desk", [0.2, 0.5, 0.9, 1.0]),
                ],
                base_graph(),
                sample,
                n_grounding_calls=2,
            )
            unbound["relations"] = [
                {
                    "id": "r1",
                    "subject_id": "e1",
                    "object_id": "e2",
                    "predicate": "on",
                    "temporal_extent": {
                        "start_frame": 0,
                        "end_frame_exclusive": 11,
                        "precision": "shot",
                    },
                    "confidence": 0.8,
                    "evidence_frame_ids": [10],
                }
            ]
            total = MODULE.merge_prompt_bound_and_unbound_graphs(bound, unbound)
        self.assertEqual([item["id"] for item in total["entities"]], ["e1", "e2", "e3"])
        self.assertEqual(
            [item["name"] for item in total["entities"]], ["woman", "lamp", "desk"]
        )
        self.assertEqual(total["relations"][0]["subject_id"], "e2")
        self.assertEqual(total["relations"][0]["object_id"], "e3")

    def test_grounding_artifacts_include_all_keyframes_and_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frame_dir = root / "frames"
            frame_dir.mkdir()
            frame_path = frame_dir / "frame_000010.jpg"
            Image.new("RGB", (20, 20), "white").save(frame_path)
            sample = MODULE.shot_graph.VideoSample(
                frames={10: None},
                frame_paths={10: frame_path},
                num_frames=11,
                fps=5.0,
            )
            graph = MODULE.build_prompt_bound_graph(
                [scheduled_entity("pb1", "lamp", [0.1, 0.1, 0.8, 0.8])],
                base_graph(),
                sample,
                n_grounding_calls=1,
            )
            graph_path = root / "graph.json"
            MODULE.atomic_write_json(graph_path, graph)
            output_dir = root / "grounding"
            manifest = MODULE.render_grounding_artifacts(
                graph_path, frame_dir, output_dir
            )
            self.assertTrue((output_dir / "frame_000010.grounded.jpg").is_file())
            self.assertTrue((output_dir / "contact_sheet.png").is_file())
            self.assertTrue((output_dir / "grounding_manifest.json").is_file())
            self.assertEqual(manifest["grounding_detection_count"], 1)

    def test_ensemble_anonymization_is_deterministic_with_bounded_panel_labels(self):
        detectors = []
        for role, _, _ in ENSEMBLE.DETECTOR_ROLES:
            detectors.append(
                ensemble_ledger(
                    role,
                    "detector",
                    [ensemble_proposal(f"{role}_e1")],
                )
            )
        view1, source1 = ENSEMBLE.anonymize_proposals(
            detectors, shot_id="shot1", seed=1729
        )
        view2, source2 = ENSEMBLE.anonymize_proposals(
            detectors, shot_id="shot1", seed=1729
        )
        self.assertEqual(view1, view2)
        self.assertEqual(source1, source2)
        serialized = json.dumps(view1)
        serialized_source = json.dumps(source1)
        for forbidden in (
            "detector_id",
            "source_kind",
            "local_id",
            "self_confidence",
            "coverage_audit",
            "proposal_count",
            "denominator",
        ):
            self.assertNotIn(forbidden, serialized)
        for private_audit_field in (
            "coverage_audit",
            "reviewed_frame_ids",
            "spatial_cells",
            "content_strata",
            "temporal_reveal_checks",
            "residual_added_local_ids",
        ):
            self.assertNotIn(private_audit_field, serialized)
            self.assertNotIn(private_audit_field, serialized_source)
        adjudicator_prompt = ENSEMBLE._decision_prompt(
            base="downstream policy",
            shot_id="shot1",
            anonymized_view=view1,
            valid_frame_ids=[10],
        )
        self.assertNotIn("residual_added_local_ids", adjudicator_prompt)
        self.assertEqual(
            [item["panel_id"] for item in view1["detector_panels"]],
            [item[0] for item in ENSEMBLE.DETECTOR_ROLES],
        )
        anonymous_ids = {item["anonymous_proposal_id"] for item in view1["proposals"]}
        mapped_ids = {item["anonymous_proposal_id"] for item in source1["mappings"]}
        panel_ids = {
            proposal_id
            for panel in view1["detector_panels"]
            for proposal_id in panel["anonymous_proposal_ids"]
        }
        private_source_by_id = {
            item["anonymous_proposal_id"]: item["source"]
            for item in source1["mappings"]
        }
        for panel in view1["detector_panels"]:
            self.assertTrue(panel["anonymous_proposal_ids"])
            self.assertTrue(
                all(
                    private_source_by_id[proposal_id] == panel["panel_id"]
                    for proposal_id in panel["anonymous_proposal_ids"]
                )
            )
        self.assertEqual(anonymous_ids, mapped_ids)
        self.assertEqual(anonymous_ids, panel_ids)
        self.assertEqual(len(anonymous_ids), 4)

    def test_detector_panels_are_visible_only_to_inventory_adjudicator_role(self):
        ledger = ensemble_ledger(
            "detector_1",
            "detector",
            [ensemble_proposal("detector_1_e1")],
        )
        anonymous_view, _ = ENSEMBLE.anonymize_proposals(
            [ledger], shot_id="shot1", seed=1729
        )
        proposal_id = anonymous_view["proposals"][0]["anonymous_proposal_id"]
        decisions = {
            "clusters": [
                {
                    "cluster_id": "c1",
                    "anonymous_proposal_ids": [proposal_id],
                    "canonical_name": "desk",
                    "aliases": ["desk"],
                    "granularity": "whole_instance",
                    "decision": "accept",
                    "decision_reason": "visible",
                }
            ]
        }
        adjudicator_prompt = ENSEMBLE._decision_prompt(
            base="",
            shot_id="shot1",
            anonymized_view=anonymous_view,
            valid_frame_ids=[10],
        )
        self.assertIn("detector_panels", adjudicator_prompt)
        self.assertIn("detector_1", adjudicator_prompt)
        self.assertIn("nor authority", adjudicator_prompt)
        self.assertIn("interchangeable", adjudicator_prompt)

        verifier_view = ENSEMBLE._verification_view(
            decisions,
            anonymous_view,
            ["c1"],
            [],
        )
        family_view = ENSEMBLE.family_stage.planner_view(anonymous_view)
        self.assertNotIn("detector_panels", json.dumps(verifier_view))
        self.assertNotIn("detector_1", json.dumps(verifier_view))
        self.assertNotIn("detector_panels", json.dumps(family_view))
        self.assertNotIn("detector_1", json.dumps(family_view))

    def test_detector_panel_uses_one_homogeneous_method(self):
        self.assertEqual(len(ENSEMBLE.DETECTOR_ROLES), 4)
        self.assertEqual(
            {item[1] for item in ENSEMBLE.DETECTOR_ROLES},
            {ENSEMBLE.HOMOGENEOUS_SCAN_VARIANT},
        )
        self.assertEqual(
            {item[2] for item in ENSEMBLE.DETECTOR_ROLES},
            {ENSEMBLE.HOMOGENEOUS_SCAN_INSTRUCTION},
        )
        detector_policy, detector_policy_path, detector_policy_hash = (
            ENSEMBLE._load_detector_policy(ENSEMBLE.DEFAULT_SKILL_DIR)
        )
        self.assertEqual(
            detector_policy_path.name,
            ENSEMBLE.DETECTOR_POLICY_RELATIVE_PATH.name,
        )
        self.assertEqual(len(detector_policy_hash), 64)
        detector_base = ENSEMBLE._detector_base_prompt(
            shot_id="shot1",
            shot_manifest={"reference_frames": []},
            allowed_input_paths=[],
            detector_policy_text=detector_policy,
        )
        prompts = [
            ENSEMBLE._detector_prompt(detector_base, item[0], item[2])
            for item in ENSEMBLE.DETECTOR_ROLES
        ]
        normalized = [
            prompt.replace(f"detector_{index}", "detector_N")
            for index, prompt in enumerate(prompts, start=1)
        ]
        self.assertEqual(len(set(normalized)), 1)
        self.assertIn("bbox_xyxy_normalized", prompts[0])
        self.assertIn("Required three-pass method", prompts[0])
        self.assertIn("chimeric track", prompts[0])
        self.assertIn("Physical distinctness and graph-node partition", prompts[0])
        self.assertIn("compact local assembly", " ".join(prompts[0].split()))
        self.assertIn("coverage_audit", prompts[0])
        self.assertNotIn("accepted-only compact-assembly consensus", prompts[0])
        self.assertNotIn("prompt-bound matcher", prompts[0])
        self.assertNotIn("scan_variant", prompts[0])
        detector_schema = json.loads(ENSEMBLE.DETECTOR_SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(
            ENSEMBLE.DETECTOR_SCHEMA.name,
            "codex_entity_detector_ledger_v0.8.schema.json",
        )
        self.assertIn("coverage_audit", detector_schema["required"])
        self.assertIn(
            "residual_added_local_ids",
            detector_schema["$defs"]["coverageAudit"]["required"],
        )
        self.assertNotIn("scan_variant", detector_schema["required"])
        self.assertNotIn("scan_variant", detector_schema["properties"])

    def test_adjudicator_cannot_add_empty_reviewer_cluster(self):
        decisions = {
            "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
            "shot_id": "shot1",
            "clusters": [
                {
                    "cluster_id": "c1",
                    "anonymous_proposal_ids": [],
                    "canonical_name": "tree",
                    "aliases": ["tree"],
                    "granularity": "group",
                    "adjudicator_evidence": [],
                    "frame_presence": [
                        {
                            "frame_id": 10,
                            "status": "uncertain",
                            "description": "reviewer-only candidate",
                        }
                    ],
                    "identity_status": "ambiguous",
                    "decision": "abstain",
                    "decision_reason": "reviewer-only candidate",
                    "uncertainty_flags": ["reviewer_only"],
                    "final_entity": None,
                }
            ],
            "warnings": [],
        }
        with self.assertRaises(ENSEMBLE.EnsembleError):
            ENSEMBLE.validate_decisions(
                decisions,
                shot_id="shot1",
                anonymous_ids=[],
                valid_frame_ids=[10],
            )

    def test_identity_revision_preserves_deferred_partition_lineage(self):
        initial = {
            "clusters": [
                {
                    "cluster_id": "c_group",
                    "anonymous_proposal_ids": ["p0001", "p0002"],
                    "decision": "reject",
                    "uncertainty_flags": ["group_member_conflict"],
                },
                {
                    "cluster_id": "c_parts",
                    "anonymous_proposal_ids": ["p0003"],
                    "decision": "accept",
                    "uncertainty_flags": [
                        "possible_compact_assembly_partition"
                    ],
                },
            ]
        }
        ENSEMBLE.validate_deferred_partition_lineage(
            initial, json.loads(json.dumps(initial))
        )

        promoted = json.loads(json.dumps(initial))
        promoted["clusters"][0]["decision"] = "accept"
        with self.assertRaisesRegex(
            ENSEMBLE.EnsembleError, "not preserved as a rejected"
        ):
            ENSEMBLE.validate_deferred_partition_lineage(initial, promoted)

        lost_flag = json.loads(json.dumps(initial))
        lost_flag["clusters"][1]["uncertainty_flags"] = []
        with self.assertRaisesRegex(ENSEMBLE.EnsembleError, "flag.*was lost"):
            ENSEMBLE.validate_deferred_partition_lineage(initial, lost_flag)

        split = json.loads(json.dumps(initial))
        split["clusters"][0]["anonymous_proposal_ids"] = ["p0001"]
        split["clusters"].append(
            {
                "cluster_id": "c_group_residual",
                "anonymous_proposal_ids": ["p0002"],
                "decision": "reject",
                "uncertainty_flags": ["group_member_conflict"],
            }
        )
        with self.assertRaisesRegex(ENSEMBLE.EnsembleError, "was split"):
            ENSEMBLE.validate_deferred_partition_lineage(initial, split)

    def test_weak_target_selection_and_verifier_validation(self):
        source_map = {
            "mappings": [
                {
                    "anonymous_proposal_id": "p0001",
                    "source_kind": "detector",
                    "source": "detector_1",
                    "local_id": "d1_e1",
                }
            ]
        }
        cluster = {
            "cluster_id": "c_pen",
            "anonymous_proposal_ids": ["p0001"],
            "canonical_name": "pen",
            "aliases": ["pen"],
            "granularity": "whole_instance",
            "adjudicator_evidence": [],
            "frame_presence": [
                {
                    "frame_id": 10,
                    "status": "uncertain",
                    "description": "subtle boundary",
                }
            ],
            "identity_status": "ambiguous",
            "decision": "abstain",
            "decision_reason": "small object",
            "uncertainty_flags": ["subtle_boundary"],
            "final_entity": None,
        }
        decisions = {
            "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
            "shot_id": "shot1",
            "clusters": [cluster],
            "warnings": [],
        }
        targets, reasons = ENSEMBLE.select_verification_targets(decisions, source_map)
        self.assertEqual(targets, ["c_pen"])
        self.assertIn("detector_support_at_most_2", reasons["c_pen"])
        report = {
            "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
            "shot_id": "shot1",
            "verifier_id": "verifier_1",
            "reviews": [
                {
                    "cluster_id": "c_pen",
                    "existence_judgment": "confirmed",
                    "salience_judgment": "graph_worthy",
                    "same_instance_with_cluster_ids": [],
                    "graph_partition_judgment": "keep_as_separate_node",
                    "same_graph_node_with_cluster_ids": [],
                    "observed_independence_evidence": [
                        {
                            "frame_id": 10,
                            "coarse_locator": "in the person's hand",
                            "support_quality": "moderate",
                        }
                    ],
                    "intra_cluster_split_judgment": "not_reviewed",
                    "proposed_physical_units": [],
                    "pairwise_physical_separation_evidence": [],
                    "evidence": [
                        {
                            "frame_id": 10,
                            "coarse_locator": "in the person's hand",
                            "support_quality": "moderate",
                        }
                    ],
                    "reason": "visible carrying evidence",
                }
            ],
            "warnings": [],
        }
        ENSEMBLE.validate_verifier_report(
            report,
            shot_id="shot1",
            verifier_id="verifier_1",
            target_cluster_ids=targets,
            all_cluster_ids=targets,
            valid_frame_ids=[10],
        )

    def test_pure_group_member_alternative_bypasses_existence_verifiers(self):
        source_map = {
            "mappings": [
                {
                    "anonymous_proposal_id": "p0001",
                    "source_kind": "detector",
                    "source": "detector_1",
                    "local_id": "d1_group",
                }
            ]
        }
        group_alternative = {
            "cluster_id": "c_group",
            "anonymous_proposal_ids": ["p0001"],
            "canonical_name": "compact assembly",
            "identity_status": "resolved",
            "decision": "reject",
            "uncertainty_flags": ["group_member_conflict"],
        }
        decisions = {"clusters": [group_alternative]}
        targets, reasons = ENSEMBLE.select_verification_targets(
            decisions, source_map
        )
        self.assertEqual(targets, [])
        self.assertEqual(reasons, {})

        physically_uncertain = json.loads(json.dumps(decisions))
        physically_uncertain["clusters"][0]["uncertainty_flags"].append(
            "unstable_identity"
        )
        targets, reasons = ENSEMBLE.select_verification_targets(
            physically_uncertain, source_map
        )
        self.assertEqual(targets, ["c_group"])
        self.assertIn("uncertainty_flagged", reasons["c_group"])

    def test_verifier_separates_physical_identity_from_graph_partition(self):
        report = {
            "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
            "shot_id": "shot1",
            "verifier_id": "verifier_1",
            "reviews": [
                {
                    "cluster_id": "c_holder",
                    "existence_judgment": "confirmed",
                    "salience_judgment": "graph_worthy",
                    "same_instance_with_cluster_ids": [],
                    "graph_partition_judgment": "merge_into_compact_composite",
                    "same_graph_node_with_cluster_ids": ["c_implements"],
                    "observed_independence_evidence": [],
                    "intra_cluster_split_judgment": "not_reviewed",
                    "proposed_physical_units": [],
                    "pairwise_physical_separation_evidence": [],
                    "evidence": [
                        {
                            "frame_id": 10,
                            "coarse_locator": "compact stationary assembly",
                            "support_quality": "strong",
                        }
                    ],
                    "reason": "distinct constituents remain coupled in this shot",
                }
            ],
            "warnings": [],
        }
        ENSEMBLE.validate_verifier_report(
            report,
            shot_id="shot1",
            verifier_id="verifier_1",
            target_cluster_ids=["c_holder"],
            all_cluster_ids=["c_holder", "c_implements"],
            valid_frame_ids=[10],
        )
        contradictory = json.loads(json.dumps(report))
        contradictory["reviews"][0]["observed_independence_evidence"] = [
            {
                "frame_id": 10,
                "coarse_locator": "separately handled",
                "support_quality": "strong",
            }
        ]
        with self.assertRaises(ENSEMBLE.EnsembleError):
            ENSEMBLE.validate_verifier_report(
                contradictory,
                shot_id="shot1",
                verifier_id="verifier_1",
                target_cluster_ids=["c_holder"],
                all_cluster_ids=["c_holder", "c_implements"],
                valid_frame_ids=[10],
            )

    def test_whole_component_name_conflict_is_targeted_with_four_of_four_support(self):
        mappings = []
        clusters = []
        for cluster_id, name, offset in (
            ("c_plant", "plant", 0),
            ("c_pot", "plant pot", 4),
        ):
            proposal_ids = []
            for index, (role, _, _) in enumerate(ENSEMBLE.DETECTOR_ROLES, start=1):
                proposal_id = f"p{offset + index:04d}"
                proposal_ids.append(proposal_id)
                mappings.append(
                    {
                        "anonymous_proposal_id": proposal_id,
                        "source_kind": "detector",
                        "source": role,
                        "local_id": f"{role}_{name.replace(' ', '_')}",
                    }
                )
            clusters.append(
                {
                    "cluster_id": cluster_id,
                    "anonymous_proposal_ids": proposal_ids,
                    "canonical_name": name,
                    "aliases": [name],
                    "granularity": "whole_instance",
                    "adjudicator_evidence": [],
                    "frame_presence": [
                        {
                            "frame_id": 10,
                            "status": "visible",
                            "description": "visible at lower center",
                        }
                    ],
                    "identity_status": "resolved",
                    "decision": "accept",
                    "decision_reason": "initially treated as separate",
                    "uncertainty_flags": [],
                    "final_entity": {
                        "name": name,
                        "attributes": [],
                        "entity_confidence": 0.9,
                        "evidence_frame_ids": [10],
                    },
                }
            )
        targets, reasons = ENSEMBLE.select_verification_targets(
            {
                "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
                "shot_id": "shot1",
                "clusters": clusters,
                "warnings": [],
            },
            {"mappings": mappings},
        )
        self.assertEqual(targets, ["c_plant", "c_pot"])
        self.assertEqual(
            reasons["c_plant"],
            ["possible_functional_whole_component_name_overlap"],
        )
        self.assertEqual(
            reasons["c_pot"],
            ["possible_functional_whole_component_name_overlap"],
        )

    def test_coarse_locator_conflict_creates_review_only_identity_challenge(self):
        mappings = []
        proposals = []
        clusters = []
        fixtures = (
            (
                "c_alpha",
                "closed volume",
                "volume",
                "light rectangular object resting on the work desk",
            ),
            (
                "c_beta",
                "writing surface",
                "surface",
                "white rectangular material resting on the desk surface",
            ),
        )
        for cluster_offset, (cluster_id, name, head, locator) in enumerate(fixtures):
            proposal_ids = []
            for index, (role, _, _) in enumerate(ENSEMBLE.DETECTOR_ROLES, start=1):
                proposal_id = f"p{cluster_offset * 4 + index:04d}"
                proposal_ids.append(proposal_id)
                mappings.append(
                    {
                        "anonymous_proposal_id": proposal_id,
                        "source_kind": "detector",
                        "source": role,
                        "local_id": f"{role}_{cluster_id}",
                    }
                )
                proposals.append(
                    {
                        "anonymous_proposal_id": proposal_id,
                        "proposed_name": name,
                        "canonical_head": head,
                        "entity_type": "object",
                        "granularity": "whole_instance",
                        "attributes": [],
                        "evidence_frame_ids": [10],
                        "coarse_locators": [
                            {"frame_id": 10, "description": locator}
                        ],
                        "frame_presence": [
                            {
                                "frame_id": 10,
                                "status": "visible",
                                "description": locator,
                            }
                        ],
                        "uncertainty_flags": (
                            ["subtype_uncertain"] if cluster_offset == 0 else []
                        ),
                    }
                )
            clusters.append(
                {
                    "cluster_id": cluster_id,
                    "anonymous_proposal_ids": proposal_ids,
                    "canonical_name": name,
                    "aliases": [name],
                    "granularity": "whole_instance",
                    "adjudicator_evidence": [],
                    "frame_presence": [
                        {
                            "frame_id": 10,
                            "status": "visible",
                            "description": locator,
                        }
                    ],
                    "identity_status": "resolved",
                    "decision": "accept",
                    "decision_reason": "initially treated as separate",
                    "uncertainty_flags": [],
                    "final_entity": {
                        "name": name,
                        "attributes": [],
                        "entity_confidence": 0.9,
                        "evidence_frame_ids": [10],
                    },
                }
            )
        decisions = {
            "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
            "shot_id": "shot1",
            "clusters": clusters,
            "warnings": [],
        }
        anonymous_view = {
            "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
            "shot_id": "shot1",
            "shuffle_seed": 1729,
            "proposals": proposals,
        }

        pairs = ENSEMBLE.build_identity_challenge_pairs(decisions, anonymous_view)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["effect"], "review_only_no_automatic_merge")
        self.assertIn("coarse_locator_overlap", pairs[0]["trigger_bases"])
        self.assertEqual(decisions["clusters"], clusters)
        targets, reasons = ENSEMBLE.select_verification_targets(
            decisions, {"mappings": mappings}, anonymous_view
        )
        self.assertEqual(targets, ["c_alpha", "c_beta"])
        self.assertEqual(reasons["c_alpha"], ["possible_same_instance_pair"])
        self.assertEqual(reasons["c_beta"], ["possible_same_instance_pair"])
        view = ENSEMBLE._verification_view(
            decisions, anonymous_view, targets, pairs
        )
        self.assertEqual(view["identity_challenge_pairs"], pairs)

    def test_box_challenge_targets_separate_four_of_four_clusters(self):
        proposals = []
        mappings = []
        clusters = []
        for cluster_offset, (cluster_id, name) in enumerate(
            (("c_alpha", "alpha item"), ("c_beta", "beta object"))
        ):
            proposal_ids = []
            for detector_index, (role, _, _) in enumerate(
                ENSEMBLE.DETECTOR_ROLES, start=1
            ):
                proposal_id = f"p{cluster_offset * 4 + detector_index:04d}"
                proposal_ids.append(proposal_id)
                mappings.append(
                    {
                        "anonymous_proposal_id": proposal_id,
                        "source_kind": "detector",
                        "source": role,
                        "local_id": f"{role}_{cluster_id}",
                    }
                )
                proposals.append(
                    {
                        "anonymous_proposal_id": proposal_id,
                        "canonical_head": name,
                        "coarse_locators": [
                            {
                                "frame_id": 10,
                                "description": f"unique locator {cluster_offset}",
                            }
                        ],
                        "uncertainty_flags": [],
                    }
                )
            clusters.append(
                {
                    "cluster_id": cluster_id,
                    "anonymous_proposal_ids": proposal_ids,
                    "canonical_name": name,
                    "decision": "accept",
                    "identity_status": "resolved",
                    "uncertainty_flags": [],
                }
            )
        decisions = {"clusters": clusters}
        anonymous_view = {
            "proposals": proposals,
            "box_redundancy_challenges": [
                {
                    "target_proposal_id": "p0001",
                    "pattern": "single_track_duplicate",
                    "covering_proposal_ids": ["p0005"],
                    "frame_coverage": [
                        {
                            "frame_id": 10,
                            "covering_proposal_id": "p0005",
                            "iou": 0.95,
                        }
                    ],
                    "coverage_ratio": 1.0,
                    "visible_frame_count": 3,
                    "covered_frame_count": 3,
                    "iou_threshold": 0.7,
                    "coverage_threshold": 0.8,
                    "effect": "mandatory_review_no_automatic_delete",
                }
            ],
        }
        pairs = ENSEMBLE.build_identity_challenge_pairs(decisions, anonymous_view)
        self.assertEqual(len(pairs), 1)
        self.assertIn(
            "detector_box_trajectory_coverage", pairs[0]["trigger_bases"]
        )
        targets, reasons = ENSEMBLE.select_verification_targets(
            decisions, {"mappings": mappings}, anonymous_view
        )
        self.assertEqual(targets, ["c_alpha", "c_beta"])
        self.assertEqual(reasons["c_alpha"], ["possible_same_instance_pair"])
        self.assertEqual(reasons["c_beta"], ["possible_same_instance_pair"])

    def test_identity_prompts_require_pairwise_proof_but_protect_held_props(self):
        decision_prompt = ENSEMBLE._decision_prompt(
            base="",
            shot_id="shot1",
            anonymized_view={"proposals": [], "detector_panels": []},
            valid_frame_ids=[10],
        )
        self.assertIn("global duplicate-challenge pass", decision_prompt)
        self.assertIn("box_redundancy_challenges", decision_prompt)
        self.assertIn("switched identity", decision_prompt)
        self.assertIn("simultaneously resolves both physical instances", decision_prompt)
        self.assertIn("regions overlap", decision_prompt)
        self.assertIn("prompt-bound registry is not part of this stage", decision_prompt)
        self.assertIn("graph-node partition are orthogonal", decision_prompt)
        self.assertIn(
            "Do not use lack of observed independence as permission to merge",
            decision_prompt,
        )
        self.assertIn("possible_compact_assembly_partition", decision_prompt)
        self.assertIn("must not coarsen physically distinct anchors", decision_prompt)
        self.assertIn("group_member_conflict", decision_prompt)
        self.assertIn("later source-blind stage", decision_prompt)
        self.assertIn("low-trust position reference", decision_prompt)
        self.assertIn("Independently re-localize each proposal", decision_prompt)
        self.assertIn(
            "separately localizable objects with clearly separated boundaries",
            decision_prompt,
        )
        self.assertIn("one box spans both", decision_prompt)
        self.assertIn("fixed detector panels", decision_prompt)
        self.assertIn("majority vote", decision_prompt)

        verifier_prompt = ENSEMBLE._verifier_prompt(
            base="",
            shot_id="shot1",
            verifier_id="verifier_1",
            verification_view={
                "targets": [],
                "cluster_index": [],
                "identity_challenge_pairs": [],
            },
            valid_frame_ids=[10],
        )
        self.assertIn("identity_challenge_pair", verifier_prompt)
        self.assertIn("regions overlap", verifier_prompt)
        self.assertIn("held or carried prop", verifier_prompt)
        self.assertIn("detector_box_trajectory_coverage", verifier_prompt)
        self.assertIn("graph_partition_judgment", verifier_prompt)
        self.assertIn("same_graph_node_with_cluster_ids", verifier_prompt)
        self.assertIn("Do not reuse a two-boundary witness", verifier_prompt)
        self.assertIn("advisory evidence", verifier_prompt)

        revision_prompt = ENSEMBLE._revision_prompt(
            shot_id="shot1",
            initial_decisions={"clusters": []},
            verifier_reports=[],
            identity_challenge_pairs=[],
            valid_frame_ids=[10],
        )
        self.assertIn("no graph-partition authority", revision_prompt)
        self.assertIn("Never merge physically distinct clusters", revision_prompt)
        self.assertIn("group_member_conflict", revision_prompt)

    def test_strong_ensemble_unbound_ids_use_support_or_two_confirmations(self):
        def cluster(entity_id, support, reports):
            return {
                "decision": "accept",
                "identity_status": "resolved",
                "prompt_bound_check": {"status": "unbound"},
                "agreement": {"proposal_count": support},
                "targeted_verification": {"reports": reports},
                "final_entity_id": entity_id,
            }

        confirmed = [
            {
                "verifier_id": f"verifier_{index}",
                "existence_judgment": "confirmed",
                "salience_judgment": "graph_worthy",
            }
            for index in (1, 2)
        ]
        protected = MODULE.strong_ensemble_unbound_entity_ids(
            {
                "candidate_clusters": [
                    cluster("e_pen", 4, []),
                    cluster("e_book", 2, confirmed),
                    cluster("e_weak", 1, confirmed[:1]),
                ]
            }
        )
        self.assertEqual(protected, ["e_book", "e_pen"])
        inventory_first = MODULE.strong_ensemble_unbound_entity_ids(
            {
                "protocol_version": "single_shot_inventory_first_v0.3",
                "candidate_clusters": [cluster("e_singleton", 1, [])],
            }
        )
        self.assertEqual(inventory_first, ["e_singleton"])
        boxed_inventory_first = MODULE.strong_ensemble_unbound_entity_ids(
            {
                "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
                "candidate_clusters": [cluster("e_boxed_singleton", 1, [])],
            }
        )
        self.assertEqual(boxed_inventory_first, ["e_boxed_singleton"])

    def test_verified_union_keeps_visual_singleton_and_rejects_four_of_four(self):
        source_map = {
            "mappings": [
                {
                    "anonymous_proposal_id": f"p{index:04d}",
                    "source_kind": "detector",
                    "source": role,
                    "local_id": f"{role}_desk",
                }
                for index, (role, _, _) in enumerate(ENSEMBLE.DETECTOR_ROLES, start=1)
            ]
            + [
                {
                    "anonymous_proposal_id": "p0005",
                    "source_kind": "detector",
                    "source": ENSEMBLE.DETECTOR_ROLES[0][0],
                    "local_id": "singleton_book",
                }
            ]
        }
        decisions = {
            "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
            "shot_id": "shot1",
            "clusters": [
                {
                    "cluster_id": "c_desk",
                    "anonymous_proposal_ids": [
                        "p0001",
                        "p0002",
                        "p0003",
                        "p0004",
                    ],
                    "canonical_name": "desk",
                    "aliases": ["desk"],
                    "granularity": "whole_instance",
                    "adjudicator_evidence": [
                        {
                            "frame_id": 10,
                            "coarse_locator": "lower center",
                            "support_quality": "strong",
                        }
                    ],
                    "frame_presence": [
                        {
                            "frame_id": 10,
                            "status": "visible",
                            "description": "visible at lower center",
                        }
                    ],
                    "identity_status": "resolved",
                    "decision": "accept",
                    "decision_reason": "visually confirmed inventory instance",
                    "uncertainty_flags": [],
                    "final_entity": {
                        "name": "desk",
                        "attributes": [],
                        "entity_confidence": 0.9,
                        "evidence_frame_ids": [10],
                    },
                },
                {
                    "cluster_id": "c_book",
                    "anonymous_proposal_ids": ["p0005"],
                    "canonical_name": "book",
                    "aliases": ["book"],
                    "granularity": "whole_instance",
                    "adjudicator_evidence": [
                        {
                            "frame_id": 10,
                            "coarse_locator": "on the desk",
                            "support_quality": "strong",
                        }
                    ],
                    "frame_presence": [
                        {
                            "frame_id": 10,
                            "status": "visible",
                            "description": "visible on the desk",
                        }
                    ],
                    "identity_status": "resolved",
                    "decision": "accept",
                    "decision_reason": "clearly visible physical book",
                    "uncertainty_flags": [],
                    "final_entity": {
                        "name": "book",
                        "attributes": [],
                        "entity_confidence": 0.9,
                        "evidence_frame_ids": [10],
                    },
                },
            ],
            "warnings": [],
        }
        ENSEMBLE.validate_decisions(
            decisions,
            shot_id="shot1",
            anonymous_ids=[f"p{index:04d}" for index in range(1, 6)],
            valid_frame_ids=[10],
        )
        audit, semantics = ENSEMBLE.build_audit_and_semantics(
            decisions,
            source_map,
            {
                "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
                "shot_id": "shot1",
                "matcher_id": "prompt_bound_matcher",
                "matches": [
                    {
                        "cluster_id": "c_desk",
                        "status": "bound",
                        "matched_registry_ids": ["pb1"],
                        "evidence_frame_ids": [10],
                        "reason": "same physical desk",
                    },
                    {
                        "cluster_id": "c_book",
                        "status": "unbound",
                        "matched_registry_ids": [],
                        "evidence_frame_ids": [10],
                        "reason": "not a registry instance",
                    },
                ],
                "warnings": [],
            },
            shot_id="shot1",
        )
        by_name = {
            cluster["canonical_name"]: cluster
            for cluster in audit["candidate_clusters"]
        }
        self.assertEqual(by_name["desk"]["agreement"]["label"], "4/4")
        self.assertEqual(by_name["desk"]["decision"], "reject")
        self.assertEqual(by_name["book"]["agreement"]["label"], "1/4")
        self.assertEqual(by_name["book"]["decision"], "accept")
        self.assertEqual([item["name"] for item in semantics["entities"]], ["book"])
        self.assertEqual(semantics["relations"], [])

    def test_adjudicator_accounting_rejects_duplicate_proposal_membership(self):
        cluster = {
            "cluster_id": "c1",
            "anonymous_proposal_ids": ["p0001"],
            "canonical_name": "desk",
            "aliases": ["desk"],
            "granularity": "whole_instance",
            "adjudicator_evidence": [],
            "frame_presence": [
                {
                    "frame_id": 10,
                    "status": "uncertain",
                    "description": "unclear",
                }
            ],
            "identity_status": "ambiguous",
            "decision": "abstain",
            "decision_reason": "unclear",
            "uncertainty_flags": ["identity"],
            "final_entity": None,
        }
        decisions = {
            "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
            "shot_id": "shot1",
            "clusters": [cluster, {**cluster, "cluster_id": "c2"}],
            "warnings": [],
        }
        with self.assertRaises(ENSEMBLE.EnsembleError):
            ENSEMBLE.validate_decisions(
                decisions,
                shot_id="shot1",
                anonymous_ids=["p0001"],
                valid_frame_ids=[10],
            )

    def test_generic_codex_runner_captures_jsonl_without_stdout_noise(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_path = root / "frame.jpg"
            schema_path = root / "schema.json"
            image_path.write_bytes(b"image")
            schema_path.write_text("{}", encoding="utf-8")
            commands, inputs = [], []

            def fake_popen(command, **kwargs):
                commands.append(command)
                self.assertIs(kwargs["stdin"], ENSEMBLE.subprocess.PIPE)
                self.assertTrue(kwargs["text"])
                process = mock.MagicMock()
                process.__enter__.return_value = process
                process.returncode = 0

                def communicate(*, input, timeout):
                    inputs.append(input)
                    self.assertEqual(timeout, 5)
                    destination = Path(command[command.index("--output-last-message") + 1])
                    destination.write_text('{"entities": []}', encoding="utf-8")
                    kwargs["stdout"].write(
                        b'{"type":"thread.started","thread_id":"thread-1"}\n'
                        b'{"type":"item.completed","item":{"type":"error"}}\n'
                    )
                    kwargs["stderr"].write(b"captured warning\n")
                process.communicate.side_effect = communicate
                return process

            visible_stdout, visible_stderr = io.StringIO(), io.StringIO()
            with mock.patch.object(ENSEMBLE.shutil, "which", return_value="/bin/codex"), \
                 mock.patch.object(ENSEMBLE.subprocess, "Popen", side_effect=fake_popen), \
                 contextlib.redirect_stdout(visible_stdout), \
                 contextlib.redirect_stderr(visible_stderr):
                result = ENSEMBLE.run_codex_json(
                    prompt="prompt", attachments=[image_path], schema_path=schema_path,
                    output_path=root / "answer.json", events_path=root / "events.jsonl",
                    stderr_path=root / "stderr.log", codex_bin="codex", model=None,
                    timeout_sec=5,
                )
                ENSEMBLE.run_codex_json(
                    prompt="phase b", attachments=[image_path], schema_path=schema_path,
                    output_path=root / "resume_answer.json",
                    events_path=root / "resume_events.jsonl",
                    stderr_path=root / "resume_stderr.log", codex_bin="codex", model=None,
                    timeout_sec=5, resume_thread_id="thread-1",
                )
            self.assertEqual(visible_stdout.getvalue(), "")
            self.assertEqual(visible_stderr.getvalue(), "")
            self.assertEqual(result.payload, {"entities": []})
            self.assertEqual(result.thread_id, "thread-1")
            self.assertEqual(inputs, ["prompt", "phase b"])
            self.assertIn("thread.started", (root / "events.jsonl").read_text())
            self.assertIn("captured warning", (root / "stderr.log").read_text())
            self.assertIn("--ephemeral", commands[0])
            self.assertEqual(commands[1][1:3], ["exec", "resume"])
            self.assertNotIn("--ephemeral", commands[1])
            self.assertEqual(commands[1][-2:], ["thread-1", "-"])

    def test_run_codex_json_nonzero_preserves_accounting(self):
        usage = {"input_tokens": 11, "cached_input_tokens": 3,
                 "output_tokens": 5, "total_tokens": 16}
        events = ('{"type":"thread.started","thread_id":"thread-failed"}\n'
                  + json.dumps({"type": "turn.completed", "usage": usage}) + "\n")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            schema = root / "schema.json"
            schema.write_text("{}")

            def fake_popen(command, **kwargs):
                process = mock.MagicMock()
                process.__enter__.return_value = process
                process.returncode = 17

                def communicate(**unused):
                    kwargs["stdout"].write(events.encode())
                    kwargs["stderr"].write(b"failed stderr\n")
                process.communicate.side_effect = communicate
                return process

            with mock.patch.object(ENSEMBLE.shutil, "which", return_value="/bin/codex"), \
                 mock.patch.object(ENSEMBLE.subprocess, "Popen", side_effect=fake_popen), \
                 mock.patch.object(ENSEMBLE.time, "perf_counter", side_effect=[10.0, 12.25]):
                with self.assertRaises(ENSEMBLE.CodexCallError) as raised:
                    ENSEMBLE.run_codex_json(
                        prompt="prompt", attachments=[], schema_path=schema,
                        output_path=root / "answer.json", events_path=root / "events.jsonl",
                        stderr_path=root / "stderr.log", codex_bin="codex", model=None,
                        timeout_sec=5,
                    )
            error = raised.exception
            self.assertEqual(error.failure_kind, "nonzero_exit")
            self.assertEqual(error.runtime_seconds, 2.25)
            self.assertEqual(error.token_usage, usage)
            self.assertEqual(error.thread_id, "thread-failed")
            self.assertEqual(error.returncode, 17)
            self.assertTrue(error.subprocess_started)
            self.assertEqual((root / "events.jsonl").read_text(), events)
            self.assertEqual((root / "stderr.log").read_text(), "failed stderr\n")

    def test_run_codex_json_timeout_preserves_partial_streams(self):
        usage = {"input_tokens": 13, "cached_input_tokens": 2,
                 "output_tokens": 7, "total_tokens": 20}
        partial = ('{"type":"thread.started","thread_id":"thread-timeout"}\n'
                   + json.dumps({"type": "turn.completed", "usage": usage})
                   + '\n{"type":"truncated"')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            schema = root / "schema.json"
            schema.write_text("{}")
            process = mock.MagicMock()
            process.__enter__.return_value = process
            process.returncode = -9

            def fake_popen(command, **kwargs):
                def communicate(*, input, timeout):
                    kwargs["stdout"].write(partial.encode())
                    kwargs["stderr"].write(b"partial timeout stderr\n")
                    # Direct file streams leave these exception buffers empty.
                    raise ENSEMBLE.subprocess.TimeoutExpired(command, timeout)
                process.communicate.side_effect = communicate
                return process

            with mock.patch.object(ENSEMBLE.shutil, "which", return_value="/bin/codex"), \
                 mock.patch.object(ENSEMBLE.subprocess, "Popen", side_effect=fake_popen), \
                 mock.patch.object(ENSEMBLE.time, "perf_counter", side_effect=[20.0, 25.5]):
                with self.assertRaises(ENSEMBLE.CodexCallError) as raised:
                    ENSEMBLE.run_codex_json(
                        prompt="prompt", attachments=[], schema_path=schema,
                        output_path=root / "answer.json", events_path=root / "events.jsonl",
                        stderr_path=root / "stderr.log", codex_bin="codex", model=None,
                        timeout_sec=5,
                    )
            error = raised.exception
            self.assertEqual(error.failure_kind, "timeout")
            self.assertEqual(error.runtime_seconds, 5.5)
            self.assertEqual(error.token_usage, usage)
            self.assertEqual(error.thread_id, "thread-timeout")
            self.assertIsNone(error.returncode)
            process.kill.assert_called_once()
            process.wait.assert_called_once()
            self.assertEqual((root / "events.jsonl").read_text(), partial)
            self.assertEqual((root / "stderr.log").read_text(), "partial timeout stderr\n")

    def test_codex_attempt_accounting_retains_validation_failure(self):
        usage = {
            "input_tokens": 2,
            "cached_input_tokens": 1,
            "output_tokens": 3,
            "total_tokens": 5,
        }
        with tempfile.TemporaryDirectory() as directory:
            accounting = ENSEMBLE._codex_attempt_accounting(
                invocation=ENSEMBLE.CodexInvocation(
                    payload={},
                    token_usage=usage,
                    thread_id="validation-thread",
                    runtime_seconds=1.125,
                ),
                error=ENSEMBLE.EnsembleError("caller validation failed"),
                events_path=Path(directory) / "unused.events.jsonl",
            )
        self.assertEqual(accounting["failure_kind"], "python_validation")
        self.assertEqual(accounting["runtime_seconds"], 1.125)
        self.assertEqual(accounting["token_usage"], usage)
        self.assertEqual(accounting["thread_id"], "validation-thread")
        self.assertEqual(accounting["returncode"], 0)
        self.assertTrue(accounting["subprocess_started"])
        self.assertEqual(
            ENSEMBLE._aggregate_usage([usage, None]),
            {key: None for key in ENSEMBLE.TOKEN_KEYS},
        )

    def test_ensemble_runner_produces_pipeline_compatible_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frame_path = root / "source.jpg"
            Image.new("RGB", (20, 20), "white").save(frame_path)
            sample = MODULE.shot_graph.VideoSample(
                frames={10: None},
                frame_paths={10: frame_path},
                num_frames=11,
                fps=5.0,
            )
            calls = []
            lock = threading.Lock()

            def fake_codex(**kwargs):
                prompt = kwargs["prompt"]
                with lock:
                    calls.append(
                        {
                            "prompt": prompt,
                            "persistent": kwargs.get("persistent", False),
                            "resume": kwargs.get("resume_thread_id"),
                        }
                    )
                if "You are now the adjudicator" in prompt:
                    marker = "anonymized_candidates:\n"
                    view = json.loads(prompt.split(marker, 1)[1])
                    proposal_ids = [
                        item["anonymous_proposal_id"] for item in view["proposals"]
                    ]
                    payload = {
                        "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
                        "shot_id": "shot1",
                        "clusters": [
                            {
                                "cluster_id": "c1",
                                "anonymous_proposal_ids": proposal_ids,
                                "canonical_name": "desk",
                                "aliases": ["desk"],
                                "granularity": "whole_instance",
                                "adjudicator_evidence": [
                                    {
                                        "frame_id": 10,
                                        "coarse_locator": "lower center",
                                        "support_quality": "strong",
                                    }
                                ],
                                "frame_presence": [
                                    {
                                        "frame_id": 10,
                                        "status": "visible",
                                        "description": "visible at lower center",
                                    }
                                ],
                                "identity_status": "resolved",
                                "decision": "accept",
                                "decision_reason": "visually confirmed",
                                "uncertainty_flags": [],
                                "final_entity": {
                                    "name": "desk",
                                    "attributes": [],
                                    "entity_confidence": 0.9,
                                    "evidence_frame_ids": [10],
                                },
                            }
                        ],
                        "warnings": [],
                    }
                    return ENSEMBLE.CodexInvocation(
                        payload, None, "adjudicator-thread", 0.01
                    )
                if "You are the prompt-bound identity matcher" in prompt:
                    return ENSEMBLE.CodexInvocation(
                        {
                            "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
                            "shot_id": "shot1",
                            "matcher_id": "prompt_bound_matcher",
                            "matches": [
                                {
                                    "cluster_id": "c1",
                                    "status": "unbound",
                                    "matched_registry_ids": [],
                                    "evidence_frame_ids": [10],
                                    "reason": "desk is not the registered woman",
                                }
                            ],
                            "warnings": [],
                        },
                        None,
                        None,
                        0.01,
                    )
                role, _, _ = next(
                    item
                    for item in ENSEMBLE.DETECTOR_ROLES
                    if f"Your detector ID is {item[0]}." in prompt
                )
                payload = ensemble_ledger(
                    role,
                    "detector",
                    [ensemble_proposal(f"{role}_e1")],
                )
                if role == "detector_1":
                    for cell in payload["coverage_audit"]["spatial_cells"]:
                        cell["represented_local_ids"] = []
                    for stratum in payload["coverage_audit"]["content_strata"]:
                        stratum["represented_local_ids"] = []
                return ENSEMBLE.CodexInvocation(payload, None, None, 0.01)

            original_group_stage = ENSEMBLE.run_group_member_family_stage
            original_accepted_stage = (
                ENSEMBLE.run_accepted_compact_assembly_stage
            )
            pre_group_baseline = {}

            def provisional_group_stage(**kwargs):
                pre_group_baseline["value"] = json.loads(
                    json.dumps(kwargs["baseline"])
                )
                provisional, stage_result = original_group_stage(**kwargs)
                provisional = json.loads(json.dumps(provisional))
                provisional["clusters"][0]["canonical_name"] = (
                    "provisional-only partition"
                )
                provisional["clusters"][0]["final_entity"]["name"] = (
                    "provisional-only partition"
                )
                return provisional, stage_result

            def accepted_second_gate(**kwargs):
                self.assertEqual(
                    kwargs["baseline"], pre_group_baseline["value"]
                )
                self.assertEqual(
                    kwargs["baseline"]["clusters"][0]["canonical_name"],
                    "desk",
                )
                return original_accepted_stage(**kwargs)

            with mock.patch.object(ENSEMBLE, "_codex_version", return_value="test"):
                with mock.patch.object(
                    ENSEMBLE, "run_codex_json", side_effect=fake_codex
                ):
                    with mock.patch.object(
                        ENSEMBLE,
                        "run_group_member_family_stage",
                        side_effect=provisional_group_stage,
                    ):
                        with mock.patch.object(
                            ENSEMBLE,
                            "run_accepted_compact_assembly_stage",
                            side_effect=accepted_second_gate,
                        ):
                            progress_output = io.StringIO()
                            with contextlib.redirect_stdout(progress_output):
                                result = ENSEMBLE.run_ensemble_detection(
                                    sample=sample,
                                    shot_id="shot1",
                                    prompt_entities=[
                                        scheduled_entity("pb1", "woman")
                                    ],
                                    run_dir=root / "ensemble",
                                    codex_bin="codex",
                                    model=None,
                                    timeout_sec=5,
                                    max_workers=4,
                                )
            progress = progress_output.getvalue()
            self.assertIn("detectors attempt 1: starting 4 parallel calls", progress)
            self.assertIn("detectors attempt 1: 4/4 valid", progress)
            self.assertIn("adjudicator: clustering and reviewing", progress)
            self.assertIn("targeted verification: no weak clusters", progress)
            self.assertEqual(len(calls), 6)
            self.assertEqual(sum(call["resume"] is not None for call in calls), 0)
            self.assertEqual(sum(call["persistent"] for call in calls), 1)
            adjudicator_prompt = next(
                call["prompt"] for call in calls if call["persistent"]
            )
            self.assertIn("no authority to discover", adjudicator_prompt)
            self.assertNotIn('"name": "woman"', adjudicator_prompt)
            matcher_prompt = next(
                call["prompt"]
                for call in calls
                if "You are the prompt-bound identity matcher" in call["prompt"]
            )
            self.assertIn('"name": "woman"', matcher_prompt)
            self.assertNotIn("detected_boxes", matcher_prompt)
            self.assertFalse(
                (root / "ensemble" / "adjudication" / "adjudicator_blind.json").exists()
            )
            self.assertEqual(result.detector_invocations, 4)
            self.assertEqual(result.adjudicator_invocations, 1)
            self.assertEqual(result.verifier_invocations, 0)
            self.assertEqual(result.matcher_invocations, 1)
            self.assertEqual(result.grounding_frame_ids_by_entity, {"e1": [10]})
            self.assertEqual(result.semantics["relations"], [])
            self.assertEqual(result.semantics["entities"][0]["id"], "e1")
            MODULE.shot_graph.normalize_and_validate_semantics(result.semantics, sample)
            self.assertTrue((root / "ensemble" / "final_semantics.json").is_file())
            manifest = json.loads((root / "ensemble" / "run_manifest.json").read_text())
            self.assertEqual(manifest["status"], "success")
            self.assertEqual(
                manifest["detector_policy"]["version"],
                ENSEMBLE.DETECTOR_POLICY_VERSION,
            )
            self.assertEqual(len(manifest["detector_policy"]["sha256"]), 64)
            self.assertNotIn(
                manifest["detector_policy"]["path"], manifest["skill_hashes"]
            )
            self.assertFalse(
                manifest["detector_policy"]["full_downstream_skill_visible"]
            )
            self.assertFalse(
                manifest["detector_policy"]["coverage_audit_downstream_visible"]
            )
            self.assertEqual(
                manifest["detector_coverage_diagnostics"]["status"], "recorded"
            )
            self.assertEqual(
                manifest["detector_coverage_diagnostics"][
                    "detectors_with_nonfatal_cross_index_omissions"
                ],
                ["detector_1"],
            )
            self.assertTrue(
                manifest["detector_coverage_diagnostics"]["private"]
            )
            self.assertFalse(
                manifest["detector_coverage_diagnostics"]["downstream_visible"]
            )
            diagnostics_artifact = manifest["artifacts"][
                "detector_coverage_diagnostics"
            ]
            self.assertTrue(diagnostics_artifact["private"])
            self.assertFalse(diagnostics_artifact["downstream_visible"])
            diagnostics_payload = json.loads(
                Path(diagnostics_artifact["path"]).read_text(encoding="utf-8")
            )
            self.assertEqual(len(diagnostics_payload["detectors"]), 4)
            diagnostics_by_detector = {
                item["detector_id"]: item
                for item in diagnostics_payload["detectors"]
            }
            self.assertEqual(
                diagnostics_by_detector["detector_1"][
                    "unindexed_spatial_local_ids"
                ],
                ["detector_1_e1"],
            )
            self.assertEqual(
                diagnostics_by_detector["detector_1"][
                    "unindexed_content_stratum_local_ids"
                ],
                ["detector_1_e1"],
            )
            self.assertFalse(manifest["granularity_family"]["coarsening_is_final"])
            self.assertTrue(
                manifest["granularity_family"][
                    "accepted_candidate_second_gate_required"
                ]
            )
            self.assertTrue(
                manifest["accepted_compact_assembly"][
                    "uses_pre_group_frozen_baseline"
                ]
            )
            self.assertTrue(
                manifest["artifacts"]["adjudicator_post_group_member"][
                    "provisional_partition_view_only"
                ]
            )
            self.assertIn("partition_gate_handoff", manifest["artifacts"])
            provisional_artifact = json.loads(
                Path(
                    manifest["artifacts"]["adjudicator_post_group_member"][
                        "path"
                    ]
                ).read_text()
            )
            final_artifact = json.loads(
                Path(
                    manifest["artifacts"]["adjudicator_decisions"]["path"]
                ).read_text()
            )
            self.assertEqual(
                provisional_artifact["clusters"][0]["canonical_name"],
                "provisional-only partition",
            )
            self.assertEqual(
                final_artifact["clusters"][0]["canonical_name"], "desk"
            )
            self.assertEqual(len(manifest["adjudicator_initial_attempts"]), 1)
            initial_attempt = manifest["adjudicator_initial_attempts"][0]
            self.assertEqual(initial_attempt["status"], "success")
            self.assertIsNone(initial_attempt["failure_kind"])
            self.assertEqual(initial_attempt["runtime_seconds"], 0.01)
            self.assertEqual(initial_attempt["thread_id"], "adjudicator-thread")
            self.assertEqual(initial_attempt["returncode"], 0)

    def test_ensemble_runner_targeted_verifies_weak_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frame_path = root / "source.jpg"
            Image.new("RGB", (20, 20), "white").save(frame_path)
            sample = MODULE.shot_graph.VideoSample(
                frames={10: None},
                frame_paths={10: frame_path},
                num_frames=11,
                fps=5.0,
            )
            initial_holder = {}
            source_map_visibility = []
            revision_prompts = []
            verifier_attempt_counts = {}
            verifier_prompts = {}
            usage = {
                "input_tokens": 2,
                "cached_input_tokens": 1,
                "output_tokens": 3,
                "total_tokens": 5,
            }

            def make_cluster(cluster_id, proposal_ids, name, decision):
                accepted = decision == "accept"
                return {
                    "cluster_id": cluster_id,
                    "anonymous_proposal_ids": proposal_ids,
                    "canonical_name": name,
                    "aliases": [name],
                    "granularity": "whole_instance",
                    "adjudicator_evidence": (
                        [
                            {
                                "frame_id": 10,
                                "coarse_locator": "lower center",
                                "support_quality": "strong",
                            }
                        ]
                        if accepted
                        else []
                    ),
                    "frame_presence": [
                        {
                            "frame_id": 10,
                            "status": "visible" if accepted else "uncertain",
                            "description": "localized" if accepted else "subtle boundary",
                        }
                    ],
                    "identity_status": "resolved" if accepted else "ambiguous",
                    "decision": decision,
                    "decision_reason": "visually checked",
                    "uncertainty_flags": [] if accepted else ["subtle_boundary"],
                    "final_entity": (
                        {
                            "name": name,
                            "attributes": [],
                            "entity_confidence": 0.9,
                            "evidence_frame_ids": [10],
                        }
                        if accepted
                        else None
                    ),
                }

            def fake_codex(**kwargs):
                prompt = kwargs["prompt"]
                source_map_visibility.append(
                    (root / "ensemble" / "adjudication" / "source_map.json").exists()
                )
                if "Your detector ID is" in prompt:
                    role, _, _ = next(
                        item
                        for item in ENSEMBLE.DETECTOR_ROLES
                        if f"Your detector ID is {item[0]}." in prompt
                    )
                    proposals = [ensemble_proposal(f"{role}_desk")]
                    if role == "detector_1":
                        proposals.append(ensemble_proposal("d1_pen", "pen"))
                    return ENSEMBLE.CodexInvocation(
                        ensemble_ledger(role, "detector", proposals),
                        usage,
                        f"{role}-thread",
                        0.01,
                    )
                if "You are now the adjudicator" in prompt:
                    view = json.loads(prompt.split("anonymized_candidates:\n", 1)[1])
                    desk_ids = [
                        item["anonymous_proposal_id"]
                        for item in view["proposals"]
                        if item["proposed_name"] == "desk"
                    ]
                    pen_ids = [
                        item["anonymous_proposal_id"]
                        for item in view["proposals"]
                        if item["proposed_name"] == "pen"
                    ]
                    payload = {
                        "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
                        "shot_id": "shot1",
                        "clusters": [
                            make_cluster("c_desk", desk_ids, "desk", "accept"),
                            make_cluster("c_pen", pen_ids, "pen", "abstain"),
                        ],
                        "warnings": [],
                    }
                    initial_holder["payload"] = payload
                    return ENSEMBLE.CodexInvocation(
                        payload, usage, "adjudicator-thread", 0.01
                    )
                if "You are an independent targeted verifier" in prompt:
                    verifier_id = next(
                        item
                        for item in ENSEMBLE.VERIFIER_IDS
                        if f"Set verifier_id exactly to {item}" in prompt
                    )
                    verifier_prompts.setdefault(verifier_id, []).append(prompt)
                    verifier_attempt_counts[verifier_id] = (
                        verifier_attempt_counts.get(verifier_id, 0) + 1
                    )
                    payload_verifier_id = verifier_id
                    if (
                        verifier_id == "verifier_2"
                        and verifier_attempt_counts[verifier_id] == 1
                    ):
                        payload_verifier_id = "wrong_verifier_id"
                    payload = {
                        "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
                        "shot_id": "shot1",
                        "verifier_id": payload_verifier_id,
                        "reviews": [
                            {
                                "cluster_id": "c_pen",
                                "existence_judgment": "confirmed",
                                "salience_judgment": "graph_worthy",
                                "same_instance_with_cluster_ids": [],
                                "graph_partition_judgment": "keep_as_separate_node",
                                "same_graph_node_with_cluster_ids": [],
                                "observed_independence_evidence": [
                                    {
                                        "frame_id": 10,
                                        "coarse_locator": "in the person's hand",
                                        "support_quality": "moderate",
                                    }
                                ],
                                "intra_cluster_split_judgment": "not_reviewed",
                                "proposed_physical_units": [],
                                "pairwise_physical_separation_evidence": [],
                                "evidence": [
                                    {
                                        "frame_id": 10,
                                        "coarse_locator": "in the person's hand",
                                        "support_quality": "moderate",
                                    }
                                ],
                                "reason": "visible carrying evidence",
                            }
                        ],
                        "warnings": [],
                    }
                    return ENSEMBLE.CodexInvocation(
                        payload,
                        usage,
                        f"{verifier_id}-attempt-"
                        f"{verifier_attempt_counts[verifier_id]}",
                        0.01,
                    )
                if "Continue as the same adjudicator" in prompt:
                    revision_prompts.append(prompt)
                    initial = initial_holder["payload"]
                    desk = initial["clusters"][0]
                    pen_ids = initial["clusters"][1]["anonymous_proposal_ids"]
                    if len(revision_prompts) == 1:
                        desk = json.loads(json.dumps(desk))
                        desk["anonymous_proposal_ids"].extend(pen_ids)
                    payload = {
                        "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
                        "shot_id": "shot1",
                        "clusters": [
                            desk,
                            make_cluster("c_pen", pen_ids, "pen", "accept"),
                        ],
                        "warnings": [],
                    }
                    return ENSEMBLE.CodexInvocation(
                        payload,
                        usage,
                        f"revision-attempt-{len(revision_prompts)}",
                        0.01,
                    )
                if "accepted_only_source_blind_inventory:" in prompt:
                    accepted_view = json.loads(
                        prompt.split(
                            "accepted_only_source_blind_inventory:\n", 1
                        )[1]
                    )
                    return ENSEMBLE.CodexInvocation(
                        {
                            "protocol_version": (
                                ENSEMBLE.accepted_assembly_stage.PLAN_PROTOCOL
                            ),
                            "shot_id": "shot1",
                            "reviewed_accepted_cluster_ids": [
                                item["cluster_id"]
                                for item in accepted_view["accepted_clusters"]
                            ],
                            "families": [],
                            "warnings": [],
                        },
                        usage,
                        "accepted-assembly-thread",
                        0.01,
                    )
                if "You are the prompt-bound identity matcher" in prompt:
                    return ENSEMBLE.CodexInvocation(
                        {
                            "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
                            "shot_id": "shot1",
                            "matcher_id": "prompt_bound_matcher",
                            "matches": [
                                {
                                    "cluster_id": cluster_id,
                                    "status": "unbound",
                                    "matched_registry_ids": [],
                                    "evidence_frame_ids": [10],
                                    "reason": "registry is empty",
                                }
                                for cluster_id in ("c_desk", "c_pen")
                            ],
                            "warnings": [],
                        },
                        usage,
                        "matcher-thread",
                        0.01,
                    )
                raise AssertionError("unexpected mocked Codex prompt")

            with mock.patch.object(ENSEMBLE, "_codex_version", return_value="test"):
                with mock.patch.object(
                    ENSEMBLE, "run_codex_json", side_effect=fake_codex
                ):
                    result = ENSEMBLE.run_ensemble_detection(
                        sample=sample,
                        shot_id="shot1",
                        prompt_entities=[],
                        run_dir=root / "ensemble",
                        codex_bin="codex",
                        model=None,
                        timeout_sec=5,
                        max_workers=4,
                    )
            self.assertEqual(result.detector_invocations, 4)
            self.assertEqual(result.verifier_invocations, 3)
            self.assertEqual(result.adjudicator_invocations, 3)
            self.assertEqual(result.matcher_invocations, 1)
            self.assertEqual(len(revision_prompts), 2)
            self.assertIn("single accounting-repair retry", revision_prompts[1])
            self.assertIn("duplicate_proposal_owners", revision_prompts[1])
            self.assertEqual(
                {item["name"] for item in result.semantics["entities"]},
                {"desk", "pen"},
            )
            self.assertFalse(any(source_map_visibility))
            audit = json.loads(result.audit_path.read_text())
            pen = next(
                item
                for item in audit["candidate_clusters"]
                if item["canonical_name"] == "pen"
            )
            self.assertTrue(pen["targeted_verification"]["required"])
            self.assertEqual(len(pen["targeted_verification"]["reports"]), 2)
            manifest = json.loads((root / "ensemble" / "run_manifest.json").read_text())
            verifier_2_attempts = [
                item
                for item in manifest["verifier_attempts"]
                if item["verifier_id"] == "verifier_2"
            ]
            self.assertEqual(
                [item["status"] for item in verifier_2_attempts],
                ["failed", "success"],
            )
            self.assertEqual(
                verifier_2_attempts[0]["failure_kind"], "python_validation"
            )
            self.assertEqual(verifier_2_attempts[0]["token_usage"], usage)
            self.assertEqual(
                verifier_2_attempts[0]["thread_id"], "verifier_2-attempt-1"
            )
            self.assertEqual(verifier_2_attempts[0]["returncode"], 0)
            self.assertIn(
                "must be disjoint", verifier_prompts["verifier_2"][0]
            )
            self.assertIn(
                "preceding report failed deterministic validation",
                verifier_prompts["verifier_2"][1],
            )
            self.assertIn(
                "verifier_2: wrong verifier_id",
                verifier_prompts["verifier_2"][1],
            )
            self.assertEqual(
                [item["status"] for item in manifest["adjudicator_revision_attempts"]],
                ["failed", "success"],
            )
            self.assertEqual(
                manifest["token_usage"],
                {key: 11 * usage[key] for key in ENSEMBLE.TOKEN_KEYS},
            )
            self.assertEqual(
                manifest["accepted_compact_assembly"]["status"],
                "deterministically_skipped",
            )
            self.assertEqual(
                manifest["accepted_compact_assembly"][
                    "mandatory_candidate_count"
                ],
                0,
            )
            self.assertEqual(
                manifest["accepted_compact_assembly"][
                    "planner_invocation_count"
                ],
                0,
            )

    def test_initial_adjudicator_validation_failure_is_audited(self):
        usage = {
            "input_tokens": 2,
            "cached_input_tokens": 1,
            "output_tokens": 3,
            "total_tokens": 5,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frame_path = root / "source.jpg"
            Image.new("RGB", (20, 20), "white").save(frame_path)
            sample = MODULE.shot_graph.VideoSample(
                frames={10: None},
                frame_paths={10: frame_path},
                num_frames=11,
                fps=5.0,
            )

            def fake_codex(**kwargs):
                prompt = kwargs["prompt"]
                if "Your detector ID is" in prompt:
                    role, _, _ = next(
                        item
                        for item in ENSEMBLE.DETECTOR_ROLES
                        if f"Your detector ID is {item[0]}." in prompt
                    )
                    return ENSEMBLE.CodexInvocation(
                        ensemble_ledger(
                            role,
                            "detector",
                            [ensemble_proposal(f"{role}_e1")],
                        ),
                        usage,
                        f"{role}-thread",
                        0.25,
                    )
                if "You are now the adjudicator" in prompt:
                    return ENSEMBLE.CodexInvocation(
                        {
                            "protocol_version": ENSEMBLE.PROTOCOL_VERSION,
                            "shot_id": "wrong-shot",
                            "clusters": [],
                            "warnings": [],
                        },
                        usage,
                        "initial-validation-thread",
                        1.5,
                    )
                raise AssertionError("unexpected mocked Codex prompt")

            ensemble_dir = root / "ensemble"
            with mock.patch.object(ENSEMBLE, "_codex_version", return_value="test"):
                with mock.patch.object(
                    ENSEMBLE, "run_codex_json", side_effect=fake_codex
                ):
                    with self.assertRaises(ENSEMBLE.EnsembleError):
                        ENSEMBLE.run_ensemble_detection(
                            sample=sample,
                            shot_id="shot1",
                            prompt_entities=[],
                            run_dir=ensemble_dir,
                            codex_bin="codex",
                            model=None,
                            timeout_sec=5,
                            max_workers=4,
                        )
            manifest = json.loads((ensemble_dir / "run_manifest.json").read_text())
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["detector_invocations"], 4)
            self.assertEqual(manifest["adjudicator_invocations"], 1)
            self.assertEqual(len(manifest["adjudicator_initial_attempts"]), 1)
            initial_attempt = manifest["adjudicator_initial_attempts"][0]
            self.assertEqual(initial_attempt["status"], "failed")
            self.assertEqual(initial_attempt["failure_kind"], "python_validation")
            self.assertEqual(initial_attempt["runtime_seconds"], 1.5)
            self.assertEqual(initial_attempt["token_usage"], usage)
            self.assertEqual(
                initial_attempt["thread_id"], "initial-validation-thread"
            )
            self.assertEqual(initial_attempt["returncode"], 0)
            self.assertEqual(
                manifest["token_usage"],
                {key: 5 * usage[key] for key in ENSEMBLE.TOKEN_KEYS},
            )

    def test_ensemble_stops_incomplete_after_one_detector_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frame_path = root / "source.jpg"
            Image.new("RGB", (20, 20), "white").save(frame_path)
            sample = MODULE.shot_graph.VideoSample(
                frames={10: None},
                frame_paths={10: frame_path},
                num_frames=11,
                fps=5.0,
            )
            calls = []
            lock = threading.Lock()
            usage = {
                "input_tokens": 2,
                "cached_input_tokens": 1,
                "output_tokens": 3,
                "total_tokens": 5,
            }

            def fake_codex(**kwargs):
                prompt = kwargs["prompt"]
                role, _, _ = next(
                    item
                    for item in ENSEMBLE.DETECTOR_ROLES
                    if f"Your detector ID is {item[0]}." in prompt
                )
                with lock:
                    calls.append(role)
                    role_attempt = calls.count(role)
                if role == "detector_4":
                    if role_attempt == 1:
                        return ENSEMBLE.CodexInvocation(
                            ensemble_ledger(
                                "wrong_detector_id",
                                "detector",
                                [ensemble_proposal("detector_4_e1")],
                            ),
                            usage,
                            "detector-4-validation-thread",
                            1.25,
                        )
                    raise ENSEMBLE.CodexCallError(
                        "detector timeout",
                        failure_kind="timeout",
                        runtime_seconds=5.0,
                        token_usage=None,
                        thread_id="detector-4-timeout-thread",
                        returncode=None,
                    )
                return ENSEMBLE.CodexInvocation(
                    ensemble_ledger(
                        role,
                        "detector",
                            [ensemble_proposal(f"{role}_e1")],
                    ),
                    usage,
                    f"{role}-thread",
                    0.01,
                )

            ensemble_dir = root / "ensemble"
            with mock.patch.object(ENSEMBLE, "_codex_version", return_value="test"):
                with mock.patch.object(
                    ENSEMBLE, "run_codex_json", side_effect=fake_codex
                ):
                    with self.assertRaises(ENSEMBLE.EnsembleIncompleteError):
                        ENSEMBLE.run_ensemble_detection(
                            sample=sample,
                            shot_id="shot1",
                            prompt_entities=[],
                            run_dir=ensemble_dir,
                            codex_bin="codex",
                            model=None,
                            timeout_sec=5,
                            max_workers=4,
                        )
            self.assertEqual(len(calls), 5)
            self.assertEqual(calls.count("detector_4"), 2)
            manifest = json.loads((ensemble_dir / "run_manifest.json").read_text())
            self.assertEqual(manifest["status"], "incomplete")
            self.assertGreaterEqual(manifest["runtime_seconds"], 0.0)
            self.assertEqual(manifest["detector_invocations"], 5)
            self.assertEqual(manifest["adjudicator_invocations"], 0)
            self.assertEqual(manifest["verifier_invocations"], 0)
            self.assertEqual(manifest["matcher_invocations"], 0)
            self.assertEqual(manifest["granularity_invocations"], 0)
            detector_4_attempts = [
                item
                for item in manifest["detector_attempts"]
                if item["detector_id"] == "detector_4"
            ]
            self.assertEqual(
                [item["failure_kind"] for item in detector_4_attempts],
                ["python_validation", "timeout"],
            )
            self.assertEqual(detector_4_attempts[0]["runtime_seconds"], 1.25)
            self.assertEqual(detector_4_attempts[0]["token_usage"], usage)
            self.assertEqual(
                detector_4_attempts[0]["thread_id"],
                "detector-4-validation-thread",
            )
            self.assertEqual(detector_4_attempts[0]["returncode"], 0)
            self.assertEqual(detector_4_attempts[1]["runtime_seconds"], 5.0)
            self.assertIsNone(detector_4_attempts[1]["token_usage"])
            self.assertEqual(
                manifest["token_usage"],
                {key: None for key in ENSEMBLE.TOKEN_KEYS},
            )
            self.assertFalse((ensemble_dir / "final_semantics.json").exists())
            self.assertFalse((ensemble_dir / "adjudication").exists())


if __name__ == "__main__":
    unittest.main()
