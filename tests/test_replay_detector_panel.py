import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import replay_detector_panel as REPLAY  # noqa: E402


FRAME_IDS = [10, 20]


def _coverage_audit():
    return {
        "reviewed_frame_ids": list(FRAME_IDS),
        "spatial_cells": [
            {
                "cell": cell,
                "best_frame_id": FRAME_IDS[0],
                "represented_local_ids": [],
            }
            for cell in REPLAY.ensemble.DETECTOR_SPATIAL_CELLS
        ],
        "content_strata": [
            {"stratum": stratum, "represented_local_ids": []}
            for stratum in REPLAY.ensemble.DETECTOR_CONTENT_STRATA
        ],
        "temporal_reveal_checks": [
            {
                "earlier_frame_id": earlier,
                "later_frame_id": later,
                "newly_revealed_cells": [],
                "added_local_ids": [],
            }
            for earlier, later in zip(FRAME_IDS, FRAME_IDS[1:])
        ],
        "residual_added_local_ids": [],
    }


def _empty_ledger(detector_id, shot_id, attachments):
    return {
        "protocol_version": REPLAY.ensemble.PROTOCOL_VERSION,
        "shot_id": shot_id,
        "detector_id": detector_id,
        "source_kind": "detector",
        "accessed_input_paths": [str(path) for path in attachments],
        "entities": [],
        "coverage_audit": _coverage_audit(),
        "warnings": [],
    }


def _write_source_shot(source_run, shot_id):
    shot_dir = source_run / shot_id
    input_dir = shot_dir / "input_bundle"
    input_dir.mkdir(parents=True)
    reference_frames = []
    for attachment_index, frame_id in enumerate(FRAME_IDS, start=1):
        frame_path = input_dir / f"frame_{frame_id:06d}.jpg"
        frame_path.write_bytes(f"{shot_id}-frame-{frame_id}".encode())
        reference_frames.append(
            {
                "attachment_index": attachment_index,
                "frame_id": frame_id,
                "timestamp_sec": float(frame_id) / 10.0,
                "path": str(frame_path.resolve()),
                "sha256": REPLAY.ensemble._sha256(frame_path),
            }
        )
    registry_path = input_dir / "prompt_bound_registry.json"
    semantic_registry_path = input_dir / "prompt_bound_registry_semantic.json"
    registry_path.write_text('{"private":"registry-secret"}\n', encoding="utf-8")
    semantic_registry_path.write_text(
        '{"private":"semantic-registry-secret"}\n', encoding="utf-8"
    )
    manifest = {
        "shot_id": shot_id,
        "num_frames": 21,
        "fps": 10.0,
        "reference_frames": reference_frames,
        "prompt_bound_registry": str(registry_path.resolve()),
        "prompt_bound_registry_semantic": str(semantic_registry_path.resolve()),
    }
    (input_dir / "shot_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    input_hashes = {
        str(path.resolve()): REPLAY.ensemble._sha256(path)
        for path in input_dir.iterdir()
        if path.is_file() and path.name != "shot_manifest.json"
    }
    (shot_dir / "run_manifest.json").write_text(
        json.dumps(
            {
                "status": "success",
                "shot_id": shot_id,
                "input_hashes": input_hashes,
                "allowed_input_paths_by_role": {
                    "detector": [item["path"] for item in reference_frames]
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return input_dir


def _write_skill(root):
    skill_dir = root / "skill"
    policy_path = skill_dir / "references" / "detector-protocol.md"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        "DETECTOR_POLICY_TEST_MARKER\nInspect every frame in three passes.\n",
        encoding="utf-8",
    )
    return skill_dir


class FakeCodexPanel:
    def __init__(self, fail_predicate=None):
        self.fail_predicate = fail_predicate or (lambda *_: False)
        self.calls = []
        self.lock = threading.Lock()

    def __call__(
        self,
        *,
        prompt,
        attachments,
        schema_path,
        output_path,
        events_path,
        stderr_path,
        codex_bin,
        model,
        timeout_sec,
        work_dir,
        verbose,
    ):
        del codex_bin, timeout_sec, work_dir, verbose
        prefix = output_path.name.removesuffix(".json")
        detector_id, attempt_label = prefix.split(".attempt")
        attempt = int(attempt_label)
        shot_id = attachments[0].parent.parent.name
        call = {
            "shot_id": shot_id,
            "detector_id": detector_id,
            "attempt": attempt,
            "prompt": prompt,
            "attachments": [str(path) for path in attachments],
            "schema_path": schema_path,
            "model": model,
        }
        with self.lock:
            self.calls.append(call)

        events_path.parent.mkdir(parents=True, exist_ok=True)
        events_path.write_text(
            json.dumps(
                {
                    "type": "thread.started",
                    "thread_id": f"thread-{shot_id}-{detector_id}-{attempt}",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        stderr_path.write_text("", encoding="utf-8")
        usage = {
            "input_tokens": 100,
            "cached_input_tokens": 0,
            "output_tokens": 10,
            "total_tokens": 110,
        }
        if self.fail_predicate(shot_id, detector_id, attempt):
            stderr_path.write_text("synthetic detector failure\n", encoding="utf-8")
            raise REPLAY.ensemble.CodexCallError(
                "synthetic detector failure",
                failure_kind="nonzero_exit",
                runtime_seconds=0.1,
                token_usage=usage,
                thread_id=f"thread-{shot_id}-{detector_id}-{attempt}",
                returncode=1,
            )

        payload = _empty_ledger(detector_id, shot_id, attachments)
        REPLAY.ensemble._atomic_write_json(output_path, payload)
        return REPLAY.ensemble.CodexInvocation(
            payload=payload,
            token_usage=usage,
            thread_id=f"thread-{shot_id}-{detector_id}-{attempt}",
            runtime_seconds=0.1,
        )


class DetectorPanelReplayTest(unittest.TestCase):
    def test_parallel_fixed_input_replay_is_isolated_and_detector_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_run = root / "source_run"
            source_inputs = {
                shot_id: _write_source_shot(source_run, shot_id)
                for shot_id in ("shot_alpha", "shot_beta")
            }
            skill_dir = _write_skill(root)
            output_root = root / "output"
            fake = FakeCodexPanel(
                fail_predicate=lambda shot_id, detector_id, attempt: (
                    shot_id == "shot_alpha"
                    and detector_id == "detector_2"
                    and attempt == 1
                )
            )
            real_base_prompt = REPLAY.ensemble._detector_base_prompt
            real_role_prompt = REPLAY.ensemble._detector_prompt
            with (
                mock.patch.object(
                    REPLAY.ensemble,
                    "run_codex_json",
                    side_effect=fake,
                ),
                mock.patch.object(
                    REPLAY.ensemble,
                    "_codex_version",
                    return_value="codex-test",
                ),
                mock.patch.object(
                    REPLAY.ensemble,
                    "_detector_base_prompt",
                    wraps=real_base_prompt,
                ) as base_prompt_mock,
                mock.patch.object(
                    REPLAY.ensemble,
                    "_detector_prompt",
                    wraps=real_role_prompt,
                ) as role_prompt_mock,
                mock.patch.object(
                    REPLAY.ensemble,
                    "run_ensemble_detection",
                    side_effect=AssertionError("full ensemble must not run"),
                ),
                mock.patch.object(
                    REPLAY.ensemble,
                    "anonymize_proposals",
                    side_effect=AssertionError("adjudication must not run"),
                ),
            ):
                manifest = REPLAY.run_detector_replay(
                    source_run=source_run,
                    output_root=output_root,
                    shot_ids=["shot_alpha", "shot_beta"],
                    codex_bin="codex-test",
                    model="codex-test-model",
                    timeout_sec=60,
                    max_workers=4,
                    parallel_shots=2,
                    skill_dir=skill_dir,
                )

            self.assertEqual(manifest["status"], "success")
            self.assertEqual(manifest["model"], "codex-test-model")
            self.assertTrue(
                manifest["explicit_attachments_are_single_shot_frames_only"]
            )
            self.assertTrue(manifest["cross_shot_content_excluded_from_prompt"])
            self.assertFalse(manifest["filesystem_read_allowlist_enforced"])
            self.assertNotIn("cross_shot_model_input", manifest)
            self.assertFalse(manifest["downstream_stages_executed"])
            self.assertEqual(base_prompt_mock.call_count, 2)
            self.assertEqual(role_prompt_mock.call_count, 9)
            self.assertEqual(len(fake.calls), 9)
            call_counts = {
                shot_id: sum(call["shot_id"] == shot_id for call in fake.calls)
                for shot_id in source_inputs
            }
            self.assertEqual(call_counts, {"shot_alpha": 5, "shot_beta": 4})

            for call in fake.calls:
                shot_id = call["shot_id"]
                other_shot = "shot_beta" if shot_id == "shot_alpha" else "shot_alpha"
                self.assertIn(f"shot_id: {shot_id}", call["prompt"])
                self.assertNotIn(other_shot, call["prompt"])
                self.assertIn("DETECTOR_POLICY_TEST_MARKER", call["prompt"])
                self.assertIn("coverage_audit", call["prompt"])
                self.assertNotIn("registry-secret", call["prompt"])
                self.assertEqual(call["model"], "codex-test-model")
                self.assertEqual(
                    call["schema_path"].name,
                    REPLAY.ensemble.DETECTOR_SCHEMA.name,
                )
                self.assertEqual(
                    REPLAY.ensemble._sha256(call["schema_path"]),
                    REPLAY.ensemble._sha256(REPLAY.ensemble.DETECTOR_SCHEMA),
                )
                self.assertTrue(
                    all(
                        f"/{shot_id}/input_bundle/" in path
                        for path in call["attachments"]
                    )
                )

            for shot_id in source_inputs:
                shot_run = output_root / shot_id
                shot_manifest = json.loads(
                    (shot_run / "run_manifest.json").read_text(encoding="utf-8")
                )
                self.assertEqual(shot_manifest["status"], "success")
                self.assertEqual(shot_manifest["detector_count_valid"], 4)
                self.assertEqual(
                    shot_manifest["stages_executed"],
                    {
                        "detectors": True,
                        "inventory_adjudicator": False,
                        "identity_verifiers": False,
                        "graph_partition_planners": False,
                        "prompt_bound_matcher": False,
                        "grounding_dino": False,
                        "relation_extraction": False,
                    },
                )
                self.assertTrue(
                    shot_manifest["input_bundle"]["all_files_exact_hash_match"]
                )
                self.assertTrue(
                    shot_manifest["input_bundle"][
                        "source_run_input_hashes_validated"
                    ]
                )
                self.assertFalse(
                    shot_manifest["input_bundle"][
                        "prompt_bound_registry_files_copied"
                    ]
                )
                copied_input = shot_run / "input_bundle"
                self.assertEqual(
                    {path.name for path in copied_input.iterdir()},
                    {f"frame_{frame_id:06d}.jpg" for frame_id in FRAME_IDS},
                )
                self.assertFalse(
                    (copied_input / "prompt_bound_registry.json").exists()
                )
                self.assertFalse((copied_input / "shot_manifest.json").exists())
                self.assertEqual(
                    len(shot_manifest["input_integrity_checks"]),
                    3 if shot_id == "shot_alpha" else 2,
                )
                self.assertTrue(
                    all(
                        item["matched_frozen_snapshot"]
                        for item in shot_manifest["input_integrity_checks"]
                    )
                )
                self.assertEqual(shot_manifest["model"], "codex-test-model")
                for detector_index in range(1, 5):
                    ledger_path = (
                        shot_run / "detector_runs" / f"detector_{detector_index}.json"
                    )
                    self.assertTrue(ledger_path.is_file())
                self.assertFalse((shot_run / "adjudication").exists())
                self.assertFalse((shot_run / "matching").exists())
                self.assertFalse((shot_run / "final_semantics.json").exists())
                artifact_names = set(shot_manifest["attempt_artifacts"])
                self.assertTrue(
                    any(name.endswith(".events.jsonl") for name in artifact_names)
                )
                self.assertTrue(
                    any(name.endswith(".stderr.log") for name in artifact_names)
                )
                self.assertTrue(
                    any(name.startswith("prompts/") for name in artifact_names)
                )

            alpha_attempts = json.loads(
                (output_root / "shot_alpha" / "run_manifest.json").read_text(
                    encoding="utf-8"
                )
            )["detector_attempts"]
            detector_two = [
                item for item in alpha_attempts if item["detector_id"] == "detector_2"
            ]
            self.assertEqual(
                [(item["attempt"], item["status"]) for item in detector_two],
                [(1, "failed"), (2, "success")],
            )
            detector_two_calls = sorted(
                (
                    call
                    for call in fake.calls
                    if call["shot_id"] == "shot_alpha"
                    and call["detector_id"] == "detector_2"
                ),
                key=lambda item: item["attempt"],
            )
            self.assertEqual(len(detector_two_calls), 2)
            for field in ("prompt", "attachments", "schema_path", "model"):
                self.assertEqual(
                    detector_two_calls[0][field], detector_two_calls[1][field]
                )

    def test_retry_exhaustion_is_incomplete_and_never_runs_downstream(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_run = root / "source_run"
            _write_source_shot(source_run, "shot_only")
            skill_dir = _write_skill(root)
            output_root = root / "output"
            fake = FakeCodexPanel(
                fail_predicate=lambda _shot_id, detector_id, _attempt: (
                    detector_id == "detector_4"
                )
            )
            with (
                mock.patch.object(REPLAY.ensemble, "run_codex_json", side_effect=fake),
                mock.patch.object(
                    REPLAY.ensemble,
                    "_codex_version",
                    return_value="codex-test",
                ),
            ):
                manifest = REPLAY.run_detector_replay(
                    source_run=source_run,
                    output_root=output_root,
                    shot_ids=["shot_only"],
                    codex_bin="codex-test",
                    model="codex-test-model",
                    timeout_sec=60,
                    max_workers=4,
                    parallel_shots=1,
                    skill_dir=skill_dir,
                )

            self.assertEqual(manifest["status"], "incomplete")
            self.assertEqual(manifest["results"][0]["status"], "incomplete")
            self.assertEqual(
                manifest["results"][0]["failure_kind"],
                "detector_retry_exhausted",
            )
            shot_run = output_root / "shot_only"
            shot_manifest = json.loads(
                (shot_run / "run_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(shot_manifest["status"], "incomplete")
            self.assertEqual(shot_manifest["detector_count_valid"], 3)
            self.assertEqual(shot_manifest["detector_invocations"], 5)
            self.assertIn("detector_4", shot_manifest["error"])
            self.assertFalse((shot_run / "detector_runs" / "detector_4.json").exists())
            failed = [
                item
                for item in shot_manifest["detector_attempts"]
                if item["detector_id"] == "detector_4"
            ]
            self.assertEqual(len(failed), 2)
            self.assertTrue(all(item["status"] == "failed" for item in failed))
            self.assertFalse((shot_run / "adjudication").exists())

    def test_source_run_manifest_is_required_successful_and_hash_anchored(self):
        cases = (
            "missing_manifest",
            "failed_status",
            "missing_attachment_hash",
            "conflicting_attachment_hash",
            "attachment_mismatch",
            "frame_selection_mismatch",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source_run = root / "source_run"
                input_dir = _write_source_shot(source_run, "shot_only")
                source_manifest = source_run / "shot_only" / "run_manifest.json"
                if case == "missing_manifest":
                    source_manifest.unlink()
                elif case == "failed_status":
                    payload = json.loads(source_manifest.read_text(encoding="utf-8"))
                    payload["status"] = "failed"
                    source_manifest.write_text(
                        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
                    )
                elif case == "missing_attachment_hash":
                    payload = json.loads(source_manifest.read_text(encoding="utf-8"))
                    frame_key = next(
                        key
                        for key in payload["input_hashes"]
                        if key.endswith(f"frame_{FRAME_IDS[0]:06d}.jpg")
                    )
                    del payload["input_hashes"][frame_key]
                    source_manifest.write_text(
                        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
                    )
                elif case == "frame_selection_mismatch":
                    shot_manifest_path = input_dir / "shot_manifest.json"
                    payload = json.loads(
                        shot_manifest_path.read_text(encoding="utf-8")
                    )
                    payload["reference_frames"].pop()
                    shot_manifest_path.write_text(
                        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
                    )
                elif case == "conflicting_attachment_hash":
                    payload = json.loads(source_manifest.read_text(encoding="utf-8"))
                    payload["input_hashes"][
                        f"/conflicting/alias/frame_{FRAME_IDS[0]:06d}.jpg"
                    ] = "0" * 64
                    source_manifest.write_text(
                        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
                    )
                else:
                    (input_dir / f"frame_{FRAME_IDS[0]:06d}.jpg").write_bytes(
                        b"post-run mutation"
                    )

                fake = FakeCodexPanel()
                with (
                    mock.patch.object(
                        REPLAY.ensemble, "run_codex_json", side_effect=fake
                    ),
                    mock.patch.object(
                        REPLAY.ensemble,
                        "_codex_version",
                        return_value="codex-test",
                    ),
                ):
                    manifest = REPLAY.run_detector_replay(
                        source_run=source_run,
                        output_root=root / "output",
                        shot_ids=["shot_only"],
                        codex_bin="codex-test",
                        model="codex-test-model",
                        timeout_sec=60,
                        max_workers=4,
                        parallel_shots=1,
                        skill_dir=_write_skill(root),
                    )

                self.assertEqual(manifest["status"], "failed")
                self.assertEqual(manifest["results"][0]["status"], "failed")
                self.assertEqual(
                    manifest["results"][0]["failure_kind"], "setup_failure"
                )
                self.assertEqual(fake.calls, [])
                child_manifest = json.loads(
                    (
                        root / "output" / "shot_only" / "run_manifest.json"
                    ).read_text(encoding="utf-8")
                )
                self.assertEqual(child_manifest["status"], "failed")
                self.assertEqual(child_manifest["failure_kind"], "setup_failure")

    def test_frozen_attachment_is_rechecked_before_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_run = root / "source_run"
            _write_source_shot(source_run, "shot_only")
            fake = FakeCodexPanel(
                fail_predicate=lambda _shot_id, detector_id, attempt: (
                    detector_id == "detector_2" and attempt == 1
                )
            )

            def mutate_after_failed_call(**kwargs):
                try:
                    return fake(**kwargs)
                finally:
                    if kwargs["output_path"].name == "detector_2.attempt1.json":
                        kwargs["attachments"][0].write_bytes(b"mutated replay frame")

            with (
                mock.patch.object(
                    REPLAY.ensemble,
                    "run_codex_json",
                    side_effect=mutate_after_failed_call,
                ),
                mock.patch.object(
                    REPLAY.ensemble,
                    "_codex_version",
                    return_value="codex-test",
                ),
            ):
                manifest = REPLAY.run_detector_replay(
                    source_run=source_run,
                    output_root=root / "output",
                    shot_ids=["shot_only"],
                    codex_bin="codex-test",
                    model="codex-test-model",
                    timeout_sec=60,
                    max_workers=4,
                    parallel_shots=1,
                    skill_dir=_write_skill(root),
                )

            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["results"][0]["status"], "failed")
            child_manifest = json.loads(
                (
                    root / "output" / "shot_only" / "run_manifest.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(
                child_manifest["failure_kind"], "execution_or_integrity_failure"
            )
            self.assertEqual(child_manifest["detector_invocations"], 4)
            self.assertEqual(
                [
                    (item["phase"], item["matched_frozen_snapshot"])
                    for item in child_manifest["input_integrity_checks"]
                ],
                [("detector_attempt_1", True), ("detector_attempt_2", False)],
            )

    def test_success_commit_rejects_attachment_or_role_snapshot_drift(self):
        for drift_kind in ("attachment", "roles"):
            with (
                self.subTest(drift_kind=drift_kind),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                source_run = root / "source_run"
                _write_source_shot(source_run, "shot_only")
                original_roles = tuple(REPLAY.ensemble.DETECTOR_ROLES)
                fake = FakeCodexPanel()

                def mutate_after_last_success(**kwargs):
                    result = fake(**kwargs)
                    if len(fake.calls) == len(original_roles):
                        if drift_kind == "attachment":
                            kwargs["attachments"][0].write_bytes(
                                b"mutated before success commit"
                            )
                        else:
                            REPLAY.ensemble.DETECTOR_ROLES = original_roles[:-1]
                    return result

                try:
                    with (
                        mock.patch.object(
                            REPLAY.ensemble,
                            "run_codex_json",
                            side_effect=mutate_after_last_success,
                        ),
                        mock.patch.object(
                            REPLAY.ensemble,
                            "_codex_version",
                            return_value="codex-test",
                        ),
                    ):
                        manifest = REPLAY.run_detector_replay(
                            source_run=source_run,
                            output_root=root / "output",
                            shot_ids=["shot_only"],
                            codex_bin="codex-test",
                            model="codex-test-model",
                            timeout_sec=60,
                            max_workers=1,
                            parallel_shots=1,
                            skill_dir=_write_skill(root),
                        )
                finally:
                    REPLAY.ensemble.DETECTOR_ROLES = original_roles

                self.assertEqual(manifest["status"], "failed")
                child_manifest = json.loads(
                    (
                        root / "output" / "shot_only" / "run_manifest.json"
                    ).read_text(encoding="utf-8")
                )
                self.assertEqual(child_manifest["status"], "failed")
                self.assertEqual(
                    child_manifest["input_integrity_checks"][-1]["phase"],
                    "success_commit",
                )
                self.assertFalse(
                    child_manifest["input_integrity_checks"][-1][
                        "matched_frozen_snapshot"
                    ]
                )

    def test_detector_count_ablation_uses_one_frozen_role_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_run = root / "source_run"
            _write_source_shot(source_run, "shot_only")
            roles = tuple(REPLAY.ensemble.DETECTOR_ROLES[:3])
            fake = FakeCodexPanel()
            with (
                mock.patch.object(REPLAY.ensemble, "DETECTOR_ROLES", roles),
                mock.patch.object(REPLAY.ensemble, "run_codex_json", side_effect=fake),
                mock.patch.object(
                    REPLAY.ensemble,
                    "_codex_version",
                    return_value="codex-test",
                ),
            ):
                manifest = REPLAY.run_detector_replay(
                    source_run=source_run,
                    output_root=root / "output",
                    shot_ids=["shot_only"],
                    codex_bin="codex-test",
                    model="codex-test-model",
                    timeout_sec=60,
                    max_workers=3,
                    parallel_shots=1,
                    skill_dir=_write_skill(root),
                )

            self.assertEqual(manifest["status"], "success")
            self.assertEqual(manifest["detector_count_per_shot"], 3)
            self.assertEqual(manifest["detector_role_snapshot"]["count"], 3)
            self.assertEqual(len(fake.calls), 3)
            child_manifest = json.loads(
                (
                    root / "output" / "shot_only" / "run_manifest.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(
                child_manifest["detector_role_snapshot"],
                manifest["detector_role_snapshot"],
            )

    def test_setup_failure_takes_precedence_over_parallel_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_run = root / "source_run"
            _write_source_shot(source_run, "shot_good")
            _write_source_shot(source_run, "shot_bad")
            bad_manifest_path = source_run / "shot_bad" / "run_manifest.json"
            bad_manifest = json.loads(bad_manifest_path.read_text(encoding="utf-8"))
            bad_manifest["status"] = "failed"
            bad_manifest_path.write_text(
                json.dumps(bad_manifest, indent=2) + "\n", encoding="utf-8"
            )
            fake = FakeCodexPanel()
            with (
                mock.patch.object(REPLAY.ensemble, "run_codex_json", side_effect=fake),
                mock.patch.object(
                    REPLAY.ensemble,
                    "_codex_version",
                    return_value="codex-test",
                ),
            ):
                manifest = REPLAY.run_detector_replay(
                    source_run=source_run,
                    output_root=root / "output",
                    shot_ids=["shot_good", "shot_bad"],
                    codex_bin="codex-test",
                    model="codex-test-model",
                    timeout_sec=60,
                    max_workers=4,
                    parallel_shots=2,
                    skill_dir=_write_skill(root),
                )

            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(
                {item["shot_id"]: item["status"] for item in manifest["results"]},
                {"shot_bad": "failed", "shot_good": "success"},
            )
            self.assertEqual(len(fake.calls), 4)

    def test_selection_and_resource_arguments_fail_before_model_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_run = root / "source_run"
            _write_source_shot(source_run, "shot_only")
            skill_dir = _write_skill(root)

            with self.assertRaisesRegex(REPLAY.DetectorReplayError, "unique"):
                REPLAY._source_shot_dirs(source_run, ["shot_only", "shot_only"])
            with self.assertRaisesRegex(REPLAY.DetectorReplayError, "absent"):
                REPLAY._source_shot_dirs(source_run, ["missing_shot"])
            with self.assertRaisesRegex(REPLAY.DetectorReplayError, "explicit"):
                REPLAY.run_detector_replay(
                    source_run=source_run,
                    output_root=root / "missing_model",
                    shot_ids=["shot_only"],
                    codex_bin="codex-test",
                    model=None,
                    timeout_sec=60,
                    max_workers=4,
                    parallel_shots=1,
                    skill_dir=skill_dir,
                )
            self.assertFalse((root / "missing_model").exists())
            with self.assertRaisesRegex(REPLAY.DetectorReplayError, "explicit"):
                REPLAY.run_detector_replay(
                    source_run=source_run,
                    output_root=root / "blank_model",
                    shot_ids=["shot_only"],
                    codex_bin="codex-test",
                    model="   ",
                    timeout_sec=60,
                    max_workers=4,
                    parallel_shots=1,
                    skill_dir=skill_dir,
                )
            self.assertFalse((root / "blank_model").exists())
            with self.assertRaises(SystemExit) as parser_exit:
                REPLAY.build_parser().parse_args([str(source_run)])
            self.assertEqual(parser_exit.exception.code, 2)
            with self.assertRaisesRegex(
                REPLAY.DetectorReplayError, "Output root may not be inside"
            ):
                REPLAY.run_detector_replay(
                    source_run=source_run,
                    output_root=source_run / "nested_output",
                    shot_ids=["shot_only"],
                    codex_bin="codex-test",
                    model="codex-test-model",
                    timeout_sec=60,
                    max_workers=4,
                    parallel_shots=1,
                    skill_dir=skill_dir,
                )
            for label, kwargs, expected in (
                (
                    "too many detector workers",
                    {"max_workers": 5, "parallel_shots": 1, "timeout_sec": 60},
                    "max_workers",
                ),
                (
                    "zero parallel shots",
                    {"max_workers": 4, "parallel_shots": 0, "timeout_sec": 60},
                    "parallel_shots",
                ),
                (
                    "zero timeout",
                    {"max_workers": 4, "parallel_shots": 1, "timeout_sec": 0},
                    "timeout",
                ),
            ):
                with self.subTest(case=label):
                    with self.assertRaisesRegex(REPLAY.DetectorReplayError, expected):
                        REPLAY.run_detector_replay(
                            source_run=source_run,
                            output_root=root / f"invalid_{label.replace(' ', '_')}",
                            shot_ids=["shot_only"],
                            codex_bin="codex-test",
                            model="codex-test-model",
                            skill_dir=skill_dir,
                            **kwargs,
                        )

    def test_main_exit_codes_distinguish_success_incomplete_and_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for status, expected_code in (
                ("success", 0),
                ("incomplete", 1),
                ("failed", 2),
            ):
                with self.subTest(status=status), mock.patch.object(
                    REPLAY,
                    "run_detector_replay",
                    return_value={"status": status},
                ):
                    code = REPLAY.main(
                        [
                            str(root / "source"),
                            "--output-root",
                            str(root / f"output_{status}"),
                            "--codex-model",
                            "codex-test-model",
                        ]
                    )
                self.assertEqual(code, expected_code)


if __name__ == "__main__":
    unittest.main()
