import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "extract_shot_entity_graph.py"
SPEC = importlib.util.spec_from_file_location("extract_shot_entity_graph", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ExtractShotEntityGraphTest(unittest.TestCase):
    def make_sample(self):
        return MODULE.VideoSample(
            frames={0: None, 10: None, 19: None},
            frame_paths={},
            num_frames=20,
            fps=10.0,
        )

    def valid_semantics(self):
        return {
            "entities": [
                {
                    "id": "e1",
                    "name": " Woman ",
                    "attributes": [
                        {
                            "name": "Clothing",
                            "value": "Red Coat",
                            "confidence": 0.8,
                            "evidence_frame_ids": [10],
                        }
                    ],
                    "entity_confidence": 0.9,
                    "evidence_frame_ids": [10],
                },
                {
                    "id": "e2",
                    "name": "apple",
                    "attributes": [],
                    "entity_confidence": 0.85,
                    "evidence_frame_ids": [10],
                },
            ],
            "relations": [
                {
                    "id": "r1",
                    "subject_id": "e1",
                    "object_id": "e2",
                    "predicate": " Holding ",
                    "temporal_extent": {
                        "start_frame": 5,
                        "end_frame_exclusive": 15,
                        "precision": "segment",
                    },
                    "confidence": 0.75,
                    "evidence_frame_ids": [10],
                }
            ],
            "warnings": [],
        }

    def test_uniform_indices_include_endpoints(self):
        self.assertEqual(MODULE.uniform_indices(20, 3), [0, 10, 19])
        self.assertEqual(MODULE.uniform_indices(2, 6), [0, 1])
        self.assertEqual(MODULE.uniform_indices(1, 6), [0])

    def test_codex_prompt_requires_a_scene_entity(self):
        sample = MODULE.VideoSample(
            frames={0: None},
            frame_paths={},
            num_frames=1,
            fps=1.0,
        )
        prompt = MODULE.build_codex_prompt(sample)
        self.assertEqual(MODULE.PROMPT_VERSION, "shot_entity_graph_v0.2")
        self.assertIn(
            "Every output must include at least one scene/location entity",
            prompt,
        )
        self.assertIn("primary visually observable physical setting", prompt)

    def test_imageio_ffmpeg_fallback_uses_native_decoded_frame_count(self):
        class FakeReader:
            def __init__(self):
                self.closed = False

            def __next__(self):
                return {"fps": 24.04}

            def close(self):
                self.closed = True

        reader = FakeReader()
        fake_module = types.SimpleNamespace(
            count_frames_and_secs=lambda path: (361, 15.01),
            read_frames=lambda path, pix_fmt: reader,
            get_ffmpeg_exe=lambda: str(SCRIPT),
        )
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            sys.modules, {"imageio_ffmpeg": fake_module}
        ), mock.patch("subprocess.run") as run:
            run.return_value.returncode = 0
            frame_dir = Path(directory)
            for index in range(1, 7):
                from PIL import Image
                Image.new("RGB", (4, 4)).save(
                    frame_dir / f"ffmpeg_selected_{index:06d}.jpg"
                )
            sample = MODULE._extract_reference_frames_imageio_ffmpeg(
                Path("vfr.mp4"), 6, frame_dir
            )

        self.assertTrue(reader.closed)
        self.assertEqual(sample.num_frames, 361)
        self.assertEqual(sample.fps, 24.04)
        self.assertEqual(sample.reference_frame_ids, [0, 72, 144, 216, 288, 360])
        command = run.call_args.args[0]
        self.assertIn("-vsync", command)
        self.assertIn("0", command)

    def test_semantics_are_normalized_and_validated(self):
        graph = MODULE.normalize_and_validate_semantics(
            self.valid_semantics(), self.make_sample()
        )
        self.assertEqual(graph["entities"][0]["name"], "woman")
        self.assertEqual(graph["entities"][0]["attributes"][0]["value"], "red coat")
        self.assertEqual(graph["relations"][0]["predicate"], "holding")

    def test_dangling_relation_is_rejected(self):
        graph = self.valid_semantics()
        graph["relations"][0]["object_id"] = "e9"
        with self.assertRaisesRegex(MODULE.GraphExtractionError, "missing entity"):
            MODULE.normalize_and_validate_semantics(graph, self.make_sample())

    def test_unsupplied_evidence_frame_is_rejected(self):
        graph = self.valid_semantics()
        graph["entities"][0]["evidence_frame_ids"] = [9]
        with self.assertRaisesRegex(MODULE.GraphExtractionError, "not supplied"):
            MODULE.normalize_and_validate_semantics(graph, self.make_sample())

    def test_unknown_interval_requires_null_boundaries(self):
        graph = self.valid_semantics()
        extent = graph["relations"][0]["temporal_extent"]
        extent["precision"] = "unknown"
        with self.assertRaisesRegex(MODULE.GraphExtractionError, "null boundaries"):
            MODULE.normalize_and_validate_semantics(graph, self.make_sample())

    def test_grounding_query_uses_high_confidence_attributes(self):
        entity = self.valid_semantics()["entities"][0]
        entity["attributes"].extend([
            {
                "name": "hair",
                "value": "long black hair",
                "confidence": 0.9,
                "evidence_frame_ids": [10],
            },
            {
                "name": "pose",
                "value": "standing",
                "confidence": 0.2,
                "evidence_frame_ids": [10],
            },
        ])
        self.assertEqual(
            MODULE.build_grounding_query(entity, 2),
            "woman long black hair red coat",
        )

    def test_entitybench_grounding_defaults(self):
        args = MODULE.parse_args([
            "shot.mp4", "--skip-grounding", "--skip-annotated-video"
        ])
        self.assertEqual(args.box_threshold, 0.25)
        self.assertEqual(args.text_threshold, 0.20)
        self.assertFalse(hasattr(args, "max_temporal_area_ratio"))

    def test_schema_files_are_valid_json(self):
        schema_dir = SCRIPT.parents[1] / "schemas"
        for path in schema_dir.glob("*.schema.json"):
            with self.subTest(path=path.name):
                parsed = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(parsed["type"], "object")

    def test_codex_jsonl_token_usage_is_parsed(self):
        jsonl = "\n".join([
            '{"type":"thread.started","thread_id":"test"}',
            '{"type":"item.completed","item":{"type":"agent_message"}}',
            '{"type":"turn.completed","usage":{"input_tokens":120,'
            '"cached_input_tokens":20,"output_tokens":30}}',
        ])
        self.assertEqual(
            MODULE.parse_codex_token_usage(jsonl),
            {
                "input_tokens": 120,
                "cached_input_tokens": 20,
                "output_tokens": 30,
                "total_tokens": 150,
            },
        )

    def test_responses_api_style_token_usage_is_parsed(self):
        jsonl = (
            '{"response":{"usage":{"prompt_tokens":50,'
            '"prompt_tokens_details":{"cached_tokens":10},'
            '"completion_tokens":7,"total_tokens":57}}}'
        )
        self.assertEqual(
            MODULE.parse_codex_token_usage(jsonl),
            {
                "input_tokens": 50,
                "cached_input_tokens": 10,
                "output_tokens": 7,
                "total_tokens": 57,
            },
        )

    def test_malformed_codex_events_do_not_break_usage_parsing(self):
        self.assertIsNone(MODULE.parse_codex_token_usage("warning text\n{}\n"))

    def test_same_name_assignment_does_not_reuse_one_box(self):
        candidates = {
            "e1": [
                {"bbox": (0, 0, 10, 10), "confidence": 0.9},
                {"bbox": (20, 0, 30, 10), "confidence": 0.5},
            ],
            "e2": [
                {"bbox": (0, 0, 10, 10), "confidence": 0.8},
                {"bbox": (20, 0, 30, 10), "confidence": 0.7},
            ],
        }
        assigned, ambiguous = MODULE.assign_same_name_candidates(candidates, 0.8)
        self.assertEqual(set(assigned), {"e1", "e2"})
        self.assertEqual(assigned["e1"]["bbox"], (0, 0, 10, 10))
        self.assertEqual(assigned["e2"]["bbox"], (20, 0, 30, 10))
        self.assertEqual(ambiguous, set())

    def test_different_entities_do_not_reuse_near_identical_box(self):
        candidates = {
            "e1": [
                {"bbox": (5, 1, 79, 99), "confidence": 0.50},
            ],
            "e3": [
                {"bbox": (5, 1, 80, 99), "confidence": 0.41},
                {"bbox": (39, 82, 57, 99), "confidence": 0.35},
            ],
        }
        assigned, ambiguous = MODULE.assign_distinct_entity_candidates(
            candidates, 0.85
        )
        self.assertEqual(assigned["e1"]["bbox"], (5, 1, 79, 99))
        self.assertEqual(assigned["e3"]["bbox"], (39, 82, 57, 99))
        self.assertEqual(ambiguous, set())

    def test_nested_part_is_not_rejected_as_duplicate(self):
        candidates = {
            "person": [
                {"bbox": (0, 0, 100, 100), "confidence": 0.8},
            ],
            "glasses": [
                {"bbox": (30, 15, 70, 35), "confidence": 0.7},
            ],
        }
        assigned, ambiguous = MODULE.assign_distinct_entity_candidates(
            candidates, 0.85
        )
        self.assertEqual(set(assigned), {"person", "glasses"})
        self.assertEqual(ambiguous, set())

    def test_temporally_isolated_large_box_is_rejected(self):
        huge = {"bbox": (5, 1, 80, 99), "confidence": 0.41}
        small_1 = {"bbox": (39, 82, 57, 99), "confidence": 0.60}
        small_2 = {"bbox": (34, 81, 52, 99), "confidence": 0.61}
        small_3 = {"bbox": (33, 80, 51, 99), "confidence": 0.62}
        support = MODULE.temporal_candidate_support(
            {32: [huge], 48: [small_1], 64: [small_2], 80: [small_3]},
            frame_width=100,
            frame_height=100,
            max_area_ratio=8.0,
            max_center_distance=0.75,
            max_aspect_ratio=4.0,
        )
        self.assertEqual(support[id(huge)], 0)
        self.assertEqual(support[id(small_1)], 2)
        self.assertEqual(support[id(small_2)], 2)
        self.assertEqual(support[id(small_3)], 2)

    def test_gradual_scale_change_remains_supported(self):
        first = {"bbox": (0, 0, 10, 10), "confidence": 0.6}
        second = {"bbox": (0, 0, 20, 20), "confidence": 0.6}
        third = {"bbox": (0, 0, 40, 40), "confidence": 0.6}
        support = MODULE.temporal_candidate_support(
            {0: [first], 10: [second], 20: [third]},
            frame_width=100,
            frame_height=100,
            max_area_ratio=4.0,
            max_center_distance=0.75,
            max_aspect_ratio=4.0,
        )
        self.assertEqual(support[id(first)], 1)
        self.assertEqual(support[id(second)], 2)
        self.assertEqual(support[id(third)], 1)

    def test_no_temporal_consensus_does_not_force_rejection(self):
        first = {"bbox": (0, 0, 10, 10), "confidence": 0.6}
        second = {"bbox": (0, 0, 40, 40), "confidence": 0.6}
        support = MODULE.temporal_candidate_support(
            {0: [first], 10: [second]},
            frame_width=100,
            frame_height=100,
            max_area_ratio=8.0,
            max_center_distance=0.75,
            max_aspect_ratio=4.0,
        )
        self.assertEqual(support[id(first)], 0)
        self.assertEqual(support[id(second)], 0)

    def test_unique_temporal_outlier_is_replaced_by_stable_low_score_candidate(self):
        class FakeFrame:
            shape = (100, 100, 3)

        correct_0 = {"bbox": (10, 10, 30, 40), "confidence": 0.55}
        correct_1 = {"bbox": (11, 10, 31, 40), "confidence": 0.54}
        wrong = {"bbox": (60, 10, 95, 95), "confidence": 0.90}
        rescue = {"bbox": (12, 10, 32, 40), "confidence": 0.21}
        correct_3 = {"bbox": (10, 11, 30, 41), "confidence": 0.53}
        selected = {
            0: {"e1": correct_0},
            10: {"e1": correct_1},
            20: {"e1": wrong},
            30: {"e1": correct_3},
        }
        raw = {
            0: {"e1": [correct_0]},
            10: {"e1": [correct_1]},
            20: {"e1": [wrong, rescue]},
            30: {"e1": [correct_3]},
        }
        sample = MODULE.VideoSample(
            frames={frame_id: FakeFrame() for frame_id in selected},
            frame_paths={},
            num_frames=31,
            fps=10.0,
        )

        warnings = MODULE.repair_single_frame_temporal_outliers(
            selected, raw, sample, {"e1": "side table"}, max_entity_box_iou=0.85
        )

        self.assertIs(selected[20]["e1"], rescue)
        self.assertTrue(any("overridden" in warning for warning in warnings))

    def test_temporal_rescue_requires_three_stable_frames(self):
        class FakeFrame:
            shape = (100, 100, 3)

        selected = {
            0: {"e1": {"bbox": (10, 10, 30, 40), "confidence": 0.5}},
            10: {"e1": {"bbox": (11, 10, 31, 40), "confidence": 0.5}},
            20: {"e1": {"bbox": (60, 10, 95, 95), "confidence": 0.9}},
        }
        raw = {frame_id: {"e1": [candidate["e1"]]} for frame_id, candidate in selected.items()}
        sample = MODULE.VideoSample(
            frames={frame_id: FakeFrame() for frame_id in selected},
            frame_paths={},
            num_frames=21,
            fps=10.0,
        )

        warnings = MODULE.repair_single_frame_temporal_outliers(
            selected, raw, sample, {"e1": "object"}, max_entity_box_iou=0.85
        )

        self.assertEqual(warnings, [])
        self.assertEqual(selected[20]["e1"]["bbox"], (60, 10, 95, 95))

    def test_joint_matching_avoids_greedy_cardinality_failure(self):
        box_a = (0, 0, 10, 10)
        box_b = (20, 0, 30, 10)
        e1_a = {"bbox": box_a, "confidence": 0.90}
        e1_b = {"bbox": box_b, "confidence": 0.89}
        e2_a = {"bbox": box_a, "confidence": 0.88}
        assigned, ambiguous = MODULE.assign_distinct_entity_candidates(
            {"e1": [e1_a, e1_b], "e2": [e2_a]}, 0.85
        )
        self.assertEqual(assigned["e1"], e1_b)
        self.assertEqual(assigned["e2"], e2_a)
        self.assertEqual(ambiguous, set())

    def test_temporal_utility_beats_higher_cross_query_confidence(self):
        shared_man = {"bbox": (5, 1, 80, 99), "confidence": 0.50}
        wrong_cup = {"bbox": (5, 1, 80, 99), "confidence": 0.60}
        real_cup = {"bbox": (39, 82, 57, 99), "confidence": 0.35}
        candidates = {"man": [shared_man], "cup": [wrong_cup, real_cup]}
        utilities = {
            id(shared_man): 2.50,
            id(wrong_cup): 0.60,
            id(real_cup): 1.35,
        }
        selected, unassigned, ambiguous = MODULE.assign_joint_entity_candidates(
            candidates,
            utilities,
            {"man": 0.5, "cup": 0.5},
            0.85,
        )
        self.assertEqual(selected["man"], shared_man)
        self.assertEqual(selected["cup"], real_cup)
        self.assertEqual(unassigned, set())
        self.assertEqual(ambiguous, set())

    def test_ground_entities_uses_entitybench_candidate_score_per_frame(self):
        class FakeFrame:
            shape = (100, 100, 3)

            def __init__(self, frame_id):
                self.frame_id = frame_id

        frame_ids = [0, 10]
        sample = MODULE.VideoSample(
            frames={frame_id: FakeFrame(frame_id) for frame_id in frame_ids},
            frame_paths={
                frame_id: Path(f"/tmp/frame_{frame_id:06d}.jpg")
                for frame_id in frame_ids
            },
            num_frames=11,
            fps=10.0,
        )
        entities = [
            {
                "id": "e1",
                "name": "cup",
                "attributes": [],
                "entity_confidence": 0.9,
                "evidence_frame_ids": frame_ids,
            },
        ]
        wrong = {"bbox": (0, 0, 80, 80), "confidence": 0.90}
        correct = {"bbox": (40, 40, 60, 60), "confidence": 0.30}

        def fake_ground(frame, **kwargs):
            return [dict(wrong), dict(correct)]

        def fake_crop(frame, bbox):
            return bbox

        def fake_clip(crop, query, device):
            return 0.10 if crop == wrong["bbox"] else 0.40

        def fake_selection(clip_score, crop, frame_shape):
            return {"clip": clip_score, "selection": clip_score}

        with mock.patch.object(
            MODULE,
            "_load_grounding_functions",
            return_value=(
                lambda **kwargs: object(),
                lambda **kwargs: object(),
                fake_ground,
                fake_crop,
                fake_clip,
                fake_selection,
            ),
        ):
            grounded, n_calls, warnings = MODULE.ground_entities(
                entities,
                sample,
                device="cpu",
                box_threshold=0.25,
                text_threshold=0.20,
                max_query_attributes=0,
            )

        self.assertEqual(n_calls, 2)
        self.assertEqual(grounded[0]["grounding"]["status"], "grounded")
        self.assertEqual(
            [box["score"] for box in grounded[0]["grounding"]["boxes"]],
            [0.30, 0.30],
        )
        self.assertEqual(
            grounded[0]["grounding"]["boxes"][0]["bbox_xyxy_normalized"],
            [0.4, 0.4, 0.6, 0.6],
        )
        self.assertEqual(
            grounded[0]["reference_grounding"][0]["reference_frame_path"],
            "/tmp/frame_000000.jpg",
        )
        self.assertEqual(warnings, [])

    def test_equal_temporal_support_does_not_use_cross_query_confidence(self):
        man = {"bbox": (5, 1, 80, 99), "confidence": 0.50}
        cup = {"bbox": (5, 1, 80, 99), "confidence": 0.60}
        selected, unassigned, ambiguous = MODULE.assign_joint_entity_candidates(
            {"man": [man], "cup": [cup]},
            {id(man): 4.50, id(cup): 4.60},
            {"man": 0.5, "cup": 0.5},
            0.85,
            support_scores={id(man): 1.0, id(cup): 1.0},
            support_ambiguity_margin=0.10,
        )
        self.assertEqual(selected, {})
        self.assertEqual(unassigned, {"man", "cup"})
        self.assertEqual(ambiguous, {"man", "cup"})

    def test_clearly_stronger_temporal_support_wins_box_conflict(self):
        man = {"bbox": (5, 1, 80, 99), "confidence": 0.50}
        cup = {"bbox": (5, 1, 80, 99), "confidence": 0.90}
        selected, unassigned, ambiguous = MODULE.assign_joint_entity_candidates(
            {"man": [man], "cup": [cup]},
            {id(man): 4.50, id(cup): 2.90},
            {"man": 0.5, "cup": 0.5},
            0.85,
            support_scores={id(man): 1.0, id(cup): 0.4},
            support_ambiguity_margin=0.10,
        )
        self.assertEqual(selected, {"man": man})
        self.assertEqual(unassigned, {"cup"})
        self.assertEqual(ambiguous, set())

    def test_candidate_sanitization_rejects_invalid_and_caps(self):
        candidates = [
            {"bbox": (0, 0, 10, 10), "confidence": 0.2},
            {"bbox": (1, 1, 11, 11), "confidence": 0.9},
            {"bbox": (-1, 0, 10, 10), "confidence": 0.8},
            {"bbox": (0, 0, 10, 10), "confidence": float("nan")},
            {"bbox": (0, 0, 10), "confidence": 0.7},
        ]
        valid, rejected, truncated = MODULE.sanitize_grounding_candidates(
            candidates,
            frame_width=100,
            frame_height=100,
            max_candidates=1,
        )
        self.assertEqual(rejected, 3)
        self.assertEqual(truncated, 1)
        self.assertEqual(valid[0]["confidence"], 0.9)
        self.assertEqual(valid[0]["bbox"], (1, 1, 11, 11))
        self.assertTrue(all(isinstance(value, int) for value in valid[0]["bbox"]))

    def test_joint_search_budget_fails_explicitly(self):
        candidate = {"bbox": (0, 0, 10, 10), "confidence": 0.9}
        with self.assertRaisesRegex(
            MODULE.GraphExtractionError, "exceeded the deterministic search budget"
        ):
            MODULE.assign_joint_entity_candidates(
                {"e1": [candidate]},
                {id(candidate): 0.9},
                {"e1": 0.0},
                0.85,
                max_search_nodes=1,
            )


if __name__ == "__main__":
    unittest.main()
