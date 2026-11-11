"""Bounded CPU tests: exact input bytes, source locks and experimental difference."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ensemble_shot_entity_detection as ensemble  # noqa: E402

HELPER = ROOT / "experiments/study_inconsistent_2/entity_discovery_iterations/detector_coordinate_metadata.py"
spec = importlib.util.spec_from_file_location("coordinate_metadata_test_helper", HELPER)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def dump(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


class MetadataTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.refs = []
        for index, size in enumerate([(31, 11), (11, 31), (17, 17), (19, 7), (7, 19), (29, 13)], 1):
            path = self.root / f"frame_{index:06d}.jpg"
            Image.new("RGB", size, (index, 4, 8)).save(path)
            self.refs.append({"attachment_index": index, "frame_id": index,
                              "timestamp_sec": index / 10, "path": str(path), "sha256": helper.digest(path)})

    def rewrite(self, index, writer):
        path = Path(self.refs[index]["path"])
        writer(path)
        self.refs[index]["sha256"] = helper.digest(path)

    def test_dimensions_from_original_bytes_and_no_mutation(self):
        before = {row["path"]: Path(row["path"]).read_bytes() for row in self.refs}
        original = copy.deepcopy(self.refs)
        result = helper.derive_frame_metadata(self.refs)
        self.assertEqual([(r["width"], r["height"]) for r in result],
                         [(31, 11), (11, 31), (17, 17), (19, 7), (7, 19), (29, 13)])
        self.assertEqual(self.refs, original)
        self.assertTrue(all(Path(path).read_bytes() == raw for path, raw in before.items()))

    def test_prompt_has_exact_utf8_prefix_and_only_whitelisted_metadata(self):
        baseline = "完整 D1 policy\r\nUnicode α and final newline\n"
        metadata = helper.derive_frame_metadata(self.refs)
        result = helper.build_prompt_pair(baseline, metadata)
        self.assertEqual(result["baseline"].encode(), baseline.encode())
        self.assertEqual(result["metadata"].encode()[:len(baseline.encode())], baseline.encode())
        suffix = result["metadata"][len(baseline):]
        self.assertEqual(json.loads(suffix[len(helper.METADATA_INSTRUCTIONS):]), metadata)
        self.assertNotIn(str(self.root), suffix)
        self.assertIn("divided by that image's height", suffix)
        self.assertIn("divided by that image's width", suffix)
        metadata[0]["candidate_answer"] = "private"
        with self.assertRaises(ValueError):
            helper.build_prompt_pair(baseline, metadata)

    def test_hash_mismatch_before_decoding(self):
        Path(self.refs[0]["path"]).write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            helper.derive_frame_metadata(self.refs)

    def test_corrupt_image_and_truncated_payload(self):
        for raw in (b"not an image", Path(self.refs[0]["path"]).read_bytes()[:100]):
            with self.subTest(length=len(raw)):
                self.rewrite(0, lambda p: p.write_bytes(raw))
                with self.assertRaises(Exception):
                    helper.derive_frame_metadata(self.refs)

    def test_exif_orientation_must_be_absent_or_exact_one(self):
        for orientation in (1, 2, 6, 0):
            with self.subTest(orientation=orientation):
                def save(path):
                    exif = Image.Exif()
                    exif[274] = orientation
                    Image.new("RGB", (23, 9)).save(path, exif=exif)
                self.rewrite(0, save)
                if orientation == 1:
                    self.assertEqual(helper.derive_frame_metadata(self.refs)[0]["width"], 23)
                else:
                    with self.assertRaisesRegex(ValueError, "EXIF"):
                        helper.derive_frame_metadata(self.refs)

    def test_multi_image_rejected(self):
        def save(path):
            Image.new("RGB", (5, 7)).save(path, format="GIF", save_all=True,
                append_images=[Image.new("RGB", (5, 7), "white")])
        self.rewrite(0, save)
        with self.assertRaisesRegex(ValueError, "single image"):
            helper.derive_frame_metadata(self.refs)

    def test_frame_count_order_aliases_paths_and_extra_metadata(self):
        mutations = [lambda x: x.pop(), lambda x: x.reverse(),
                     lambda x: x[0].update(frame_id=True), lambda x: x[0].update(attachment_index=1.0),
                     lambda x: x[0].update(timestamp_sec=float("nan")),
                     lambda x: x[0].update(width=999),
                     lambda x: x[1].update(path=x[0]["path"], sha256=x[0]["sha256"])]
        for mutate in mutations:
            refs = copy.deepcopy(self.refs)
            mutate(refs)
            with self.subTest(refs=refs[0]), self.assertRaises(ValueError):
                helper.derive_frame_metadata(refs)

    def test_symlink_file_and_parent_rejected(self):
        link = self.root / "alias.jpg"
        link.symlink_to(self.refs[0]["path"])
        self.refs[0]["path"] = str(link)
        with self.assertRaisesRegex(ValueError, "symlink"):
            helper.derive_frame_metadata(self.refs)
        parent = self.root / "alias_dir"
        parent.symlink_to(self.root, target_is_directory=True)
        self.refs[0]["path"] = str(parent / "frame_000001.jpg")
        with self.assertRaisesRegex(ValueError, "symlink"):
            helper.derive_frame_metadata(self.refs)


class PreparationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        sources = {}
        for relative, source in (
            (helper.ENSEMBLE_RELATIVE, Path(ensemble.__file__)),
            (helper.SCHEMA_RELATIVE, ensemble.DETECTOR_SCHEMA),
            (helper.POLICY_RELATIVE, ROOT.parent / helper.POLICY_RELATIVE),
        ):
            dest = self.root / "frozen_workspace" / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
            sources[relative] = helper.digest(dest)
        self.runtime = SimpleNamespace(
            __file__=str(self.root / "frozen_workspace" / helper.ENSEMBLE_RELATIVE),
            DETECTOR_SCHEMA=self.root / "frozen_workspace" / helper.SCHEMA_RELATIVE,
            DETECTOR_ROLES=ensemble.DETECTOR_ROLES,
            _detector_base_prompt=ensemble._detector_base_prompt, _detector_prompt=ensemble._detector_prompt)
        configdir = self.root / "execution_config"
        configdir.mkdir()
        cli = configdir / "fake_cli"
        wrapper = configdir / "codex.sh"
        cli.write_bytes(b"mock CLI: must never execute")
        wrapper.write_bytes(b"mock wrapper: must never execute")
        config = {"model": helper.MODEL, "reasoning_effort": helper.REASONING_EFFORT,
                  "codex_binary": str(cli), "codex_binary_sha256": helper.digest(cli),
                  "codex_wrapper": str(wrapper)}
        dump(configdir / "model_config.json", config)
        inputs = {}
        for shot in ("z_last", "a_first", "b_second"):
            bundle = self.root / "frozen_inputs" / shot / "input_bundle"
            bundle.mkdir(parents=True)
            refs = []
            for index in range(6):
                path = bundle / f"frame_{index:06d}.jpg"
                Image.new("RGB", (17 + index, 11)).save(path)
                refs.append({"attachment_index": index + 1, "frame_id": index,
                             "timestamp_sec": index / 2, "path": str(path), "sha256": helper.digest(path)})
                inputs[f"{shot}/{path.name}"] = helper.digest(path)
            dump(bundle / "prompt_bound_registry_semantic.json", {"private": "MUST_NOT_LEAK"})
            dump(bundle / "prompt_bound_registry.json", {"private": "LEGACY_MUST_NOT_LEAK"})
            dump(bundle / "shot_manifest.json", {"shot_id": shot, "reference_frames": refs,
                 "prompt_bound_registry_semantic": "MUST_NOT_LEAK", "other_metadata": "PRIVATE"})
            for name in ("prompt_bound_registry_semantic.json", "shot_manifest.json"):
                inputs[f"{shot}/{name}"] = helper.digest(bundle / name)
        self.batch = {"shots": ["z_last", "a_first", "b_second"], "model": helper.MODEL,
                      "reasoning_effort": helper.REASONING_EFFORT, "model_config": config,
                      "source_hashes": sources, "input_hashes": inputs,
                      "execution_hashes": {str(p): helper.digest(p) for p in configdir.iterdir()},
                      "results": [{"old_answer": "DO_NOT_READ_OR_LEAK"}]}
        dump(self.root / "robustness_manifest.json", self.batch)

    def ready(self):
        result = helper.prepare_material(self.root, self.runtime)
        self.assertEqual(result["status"], "ready", result)
        return result

    def test_real_d1_builder_sorted_selection_complete_input_locks_no_answers(self):
        result = self.ready()
        self.assertEqual([c["shot_id"] for c in result["contexts"]], ["a_first", "b_second"])
        self.assertEqual(len(result["input_hashes"]), 27)
        for context in result["contexts"]:
            self.assertEqual(len(context["attachments"]), 6)
            manifest = json.loads(Path(context["shot_manifest"]).read_text())
            policy = (self.root / "frozen_workspace" / helper.POLICY_RELATIVE).read_text()
            expected = ensemble._detector_prompt(ensemble._detector_base_prompt(
                shot_id=context["shot_id"], shot_manifest=manifest,
                allowed_input_paths=context["attachments"], detector_policy_text=policy),
                "detector_1", ensemble.DETECTOR_ROLES[0][2])
            self.assertEqual(context["prompts"]["baseline"].encode(), expected.encode())
            for prompt in context["prompts"].values():
                self.assertNotIn("MUST_NOT_LEAK", prompt)
                self.assertNotIn("PRIVATE", prompt)
                self.assertNotIn("DO_NOT_READ_OR_LEAK", prompt)
            for arm, prompt in context["prompts"].items():
                self.assertEqual(context["prompt_sha256s"][arm], hashlib.sha256(prompt.encode()).hexdigest())

    def test_mutable_batch_results_never_change_preparation(self):
        first = self.ready()
        self.batch.update(status="running", results=[{"new_live_output": "SECRET"}], pid=123)
        dump(self.root / "robustness_manifest.json", self.batch)
        self.assertEqual(self.ready(), first)

    def test_source_cli_or_input_tamper_is_explicit_failure_without_prompt(self):
        paths = [self.root / "frozen_workspace" / helper.POLICY_RELATIVE,
                 Path(self.batch["model_config"]["codex_binary"]),
                 self.root / "frozen_inputs/a_first/input_bundle/frame_000000.jpg"]
        for path in paths:
            raw = path.read_bytes()
            path.write_bytes(raw + b"tamper")
            result = helper.prepare_material(self.root, self.runtime)
            self.assertEqual(result["status"], "input_failed")
            self.assertNotIn("contexts", result)
            self.assertFalse(result["subprocess_started"])
            self.assertFalse(result["subprocess_start_unknown"])
            self.assertIsNone(result["token_usage"])
            self.assertIn("error", result)
            path.write_bytes(raw)

    def test_declared_frame_path_cannot_rebind_even_with_correct_content_hash(self):
        path = self.root / "frozen_inputs/a_first/input_bundle/shot_manifest.json"
        manifest = json.loads(path.read_text())
        manifest["reference_frames"][0]["path"] = str(self.root / "frozen_inputs/b_second/input_bundle/frame_000000.jpg")
        dump(path, manifest)
        self.batch["input_hashes"]["a_first/shot_manifest.json"] = helper.digest(path)
        dump(self.root / "robustness_manifest.json", self.batch)
        result = helper.prepare_material(self.root, self.runtime)
        self.assertEqual(result["status"], "input_failed")
        self.assertIn("declared source/frame", result["error"]["message"])

    def test_fully_rehashed_invalid_image_still_fails_before_invocation(self):
        path = self.root / "frozen_inputs/a_first/input_bundle/frame_000000.jpg"
        path.write_bytes(b"invalid picture")
        manifest_path = path.parent / "shot_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["reference_frames"][0]["sha256"] = helper.digest(path)
        dump(manifest_path, manifest)
        for item in (path, manifest_path):
            self.batch["input_hashes"][f"a_first/{item.name}"] = helper.digest(item)
        dump(self.root / "robustness_manifest.json", self.batch)
        result = helper.prepare_material(self.root, self.runtime)
        self.assertEqual(result["status"], "input_failed")
        self.assertEqual(result["stage"], "context_01:original_images")
        self.assertIsNone(result["token_usage"])

    def test_interrupt_is_not_masked_as_input_failure(self):
        with patch.object(helper, "_load", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                helper.prepare_material(self.root, self.runtime)


if __name__ == "__main__":
    unittest.main()
