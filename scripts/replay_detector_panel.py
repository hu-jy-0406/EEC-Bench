#!/usr/bin/env python3
"""Replay only the homogeneous detector panel from immutable prior-run inputs."""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import hashlib
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

import ensemble_shot_entity_detection as ensemble


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
REPOSITORY_ROOT = PROJECT_ROOT.parent


class DetectorReplayError(RuntimeError):
    """Raised when fixed-input detector replay cannot be started safely."""


class DetectorReplayIncompleteError(DetectorReplayError):
    """Raised after the configured detector panel remains incomplete after retry."""


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%SZ")


def _artifact(path: Path) -> Dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "sha256": ensemble._sha256(path),
        "size_bytes": path.stat().st_size,
    }


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed


def _required_model(value: Optional[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DetectorReplayError(
            "An explicit nonempty Codex model is required for reproducible replay"
        )
    return value.strip()


def _json_hash(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validated_detector_role_snapshot(
    roles: Sequence[Tuple[str, str, str]],
) -> Tuple[Tuple[str, str, str], ...]:
    snapshot: list[Tuple[str, str, str]] = []
    for index, item in enumerate(roles):
        if not isinstance(item, (tuple, list)) or len(item) != 3:
            raise DetectorReplayError(
                f"Configured detector role {index} must contain exactly three fields"
            )
        role, variant, instruction = item
        if not all(
            isinstance(value, str) and value.strip()
            for value in (role, variant, instruction)
        ):
            raise DetectorReplayError(
                f"Configured detector role {index} contains an empty field"
            )
        snapshot.append((role, variant, instruction))
    detector_ids = [role for role, _, _ in snapshot]
    if not snapshot or len(detector_ids) != len(set(detector_ids)):
        raise DetectorReplayError(
            "Configured detector roles must be nonempty and unique"
        )
    if (
        len({variant for _, variant, _ in snapshot}) != 1
        or len({instruction for _, _, instruction in snapshot}) != 1
    ):
        raise DetectorReplayError("Configured detector panel is not homogeneous")
    return tuple(snapshot)


def _role_snapshot_record(
    roles: Sequence[Tuple[str, str, str]],
) -> Dict[str, Any]:
    records = [
        {
            "detector_id": role,
            "scan_variant": variant,
            "scan_instruction": instruction,
        }
        for role, variant, instruction in roles
    ]
    return {
        "count": len(records),
        "roles": records,
        "sha256": _json_hash(records),
    }


def _source_shot_dirs(
    source_run: Path, requested_shot_ids: Sequence[str]
) -> list[Path]:
    if not source_run.is_dir():
        raise DetectorReplayError(f"Source run directory is missing: {source_run}")
    by_id = {
        path.name: path
        for path in source_run.iterdir()
        if path.is_dir() and (path / "input_bundle" / "shot_manifest.json").is_file()
    }
    if len(requested_shot_ids) != len(set(requested_shot_ids)):
        raise DetectorReplayError("Requested shot IDs must be unique")
    if requested_shot_ids:
        missing = sorted(set(requested_shot_ids) - set(by_id))
        if missing:
            raise DetectorReplayError(
                f"Requested shots are absent from source run: {missing}"
            )
        return [by_id[shot_id] for shot_id in requested_shot_ids]
    if not by_id:
        raise DetectorReplayError(
            f"No immutable shot input bundles found under {source_run}"
        )
    return [by_id[shot_id] for shot_id in sorted(by_id)]


def _file_hashes(root: Path) -> Dict[str, str]:
    hashes: Dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise DetectorReplayError(
                f"Immutable input bundles may not contain symlinks: {path}"
            )
        if path.is_file():
            hashes[path.relative_to(root).as_posix()] = ensemble._sha256(path)
    if not hashes:
        raise DetectorReplayError(f"Immutable input bundle is empty: {root}")
    return hashes


def _source_frame_path(
    *,
    frame_record: Mapping[str, Any],
    source_input_dir: Path,
) -> Path:
    frame_id = int(frame_record["frame_id"])
    source_input_resolved = source_input_dir.resolve()
    candidates: list[Path] = []
    raw_path = Path(str(frame_record.get("path", "")))
    if raw_path.is_absolute():
        candidates.append(raw_path)
    elif raw_path.name:
        candidates.append(source_input_dir / raw_path)
    candidates.extend(
        [
            source_input_dir / f"frame_{frame_id:06d}.jpg",
            source_input_dir / raw_path.name,
        ]
    )
    existing: list[Path] = []
    for candidate in candidates:
        if not candidate.is_file():
            continue
        if candidate.is_symlink():
            raise DetectorReplayError(
                f"Source detector attachment may not be a symlink: {candidate}"
            )
        resolved = candidate.resolve()
        try:
            resolved.relative_to(source_input_resolved)
        except ValueError as exc:
            raise DetectorReplayError(
                f"Source detector attachment is outside input_bundle: {candidate}"
            ) from exc
        if resolved not in existing:
            existing.append(resolved)
    if len(existing) == 1:
        return existing[0]
    if len(existing) > 1:
        raise DetectorReplayError(
            f"Source frame {frame_id} resolves to multiple attachment files"
        )
    raise DetectorReplayError(
        f"Source input bundle does not contain the recorded frame {frame_id}"
    )


def _load_source_run_manifest(
    *, source_shot_dir: Path, shot_id: str
) -> Tuple[Path, Dict[str, str], Optional[Tuple[str, ...]]]:
    manifest_path = source_shot_dir / "run_manifest.json"
    if not manifest_path.is_file():
        raise DetectorReplayError(
            f"Source shot run_manifest.json is required: {manifest_path}"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DetectorReplayError(
            f"Source shot run manifest is unreadable: {manifest_path}"
        ) from exc
    if not isinstance(manifest, Mapping):
        raise DetectorReplayError("Source shot run manifest must be an object")
    if manifest.get("status") != "success":
        raise DetectorReplayError(
            f"Source shot run status must be success, got {manifest.get('status')!r}"
        )
    if manifest.get("shot_id") != shot_id:
        raise DetectorReplayError(
            "Source shot run manifest shot_id does not match its directory"
        )
    input_hashes = manifest.get("input_hashes")
    if not isinstance(input_hashes, Mapping) or not input_hashes:
        raise DetectorReplayError(
            "Source shot run manifest has no recorded input_hashes trust anchor"
        )
    normalized: Dict[str, str] = {}
    for raw_path, digest in input_hashes.items():
        if (
            not isinstance(raw_path, str)
            or not raw_path
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdefABCDEF" for character in digest)
        ):
            raise DetectorReplayError(
                "Source shot run manifest contains an invalid input hash record"
            )
        normalized[raw_path] = digest.lower()
    detector_paths: Optional[Tuple[str, ...]] = None
    allowed_by_role = manifest.get("allowed_input_paths_by_role")
    if allowed_by_role is not None:
        if not isinstance(allowed_by_role, Mapping):
            raise DetectorReplayError(
                "Source shot run manifest has invalid role input boundaries"
            )
        raw_detector_paths = allowed_by_role.get("detector")
        if (
            not isinstance(raw_detector_paths, list)
            or not raw_detector_paths
            or not all(
                isinstance(path, str) and path for path in raw_detector_paths
            )
            or len(raw_detector_paths) != len(set(raw_detector_paths))
        ):
            raise DetectorReplayError(
                "Source shot run manifest has invalid detector input paths"
            )
        detector_paths = tuple(raw_detector_paths)
    elif source_shot_dir.parent.name == "ensemble_detection":
        raise DetectorReplayError(
            "Full-run source shot has no recorded detector input boundary"
        )
    return manifest_path.resolve(), normalized, detector_paths


def _recorded_attachment_hash(
    *,
    input_hashes: Mapping[str, str],
    source_frame: Path,
    frame_record: Mapping[str, Any],
) -> Tuple[str, str]:
    direct_keys = [str(source_frame.resolve())]
    raw_path = frame_record.get("path")
    if isinstance(raw_path, str) and raw_path:
        direct_keys.append(raw_path)
    relevant_matches = {
        key: digest
        for key, digest in input_hashes.items()
        if key in direct_keys or Path(key).name == source_frame.name
    }
    if not relevant_matches:
        raise DetectorReplayError(
            f"Source run has no recorded input hash for {source_frame.name}"
        )
    if len(set(relevant_matches.values())) != 1:
        raise DetectorReplayError(
            f"Source run records conflicting hashes for {source_frame.name}"
        )
    direct_match_keys = sorted(key for key in direct_keys if key in relevant_matches)
    key = direct_match_keys[0] if direct_match_keys else sorted(relevant_matches)[0]
    return key, relevant_matches[key]


def _prepare_shot_inputs(
    *, source_shot_dir: Path, run_dir: Path
) -> Tuple[list[Path], Dict[str, Any], Dict[str, Any]]:
    source_input_dir = source_shot_dir / "input_bundle"
    source_manifest_path = source_input_dir / "shot_manifest.json"
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    shot_id = source_shot_dir.name
    if source_manifest.get("shot_id") != shot_id:
        raise DetectorReplayError(
            f"Source manifest shot_id does not match its directory: {shot_id}"
        )
    reference_frames = source_manifest.get("reference_frames")
    if not isinstance(reference_frames, list) or not reference_frames:
        raise DetectorReplayError(f"Source shot has no reference frames: {shot_id}")
    (
        source_run_manifest_path,
        recorded_input_hashes,
        recorded_detector_paths,
    ) = _load_source_run_manifest(
        source_shot_dir=source_shot_dir,
        shot_id=shot_id,
    )
    copied_input_dir = run_dir / "input_bundle"
    copied_input_dir.mkdir(parents=True, exist_ok=False)

    attachments: list[Path] = []
    runtime_frames = []
    file_audits = []
    frame_ids: list[int] = []
    for attachment_index, frame_record in enumerate(reference_frames, start=1):
        if not isinstance(frame_record, Mapping):
            raise DetectorReplayError("Reference-frame records must be objects")
        frame_id = int(frame_record["frame_id"])
        if frame_id in frame_ids:
            raise DetectorReplayError(f"Duplicate reference frame ID: {frame_id}")
        frame_ids.append(frame_id)
        source_frame = _source_frame_path(
            frame_record=frame_record,
            source_input_dir=source_input_dir,
        )
        recorded_key, recorded_hash = _recorded_attachment_hash(
            input_hashes=recorded_input_hashes,
            source_frame=source_frame,
            frame_record=frame_record,
        )
        manifest_hash = frame_record.get("sha256")
        if not isinstance(manifest_hash, str) or manifest_hash.lower() != recorded_hash:
            raise DetectorReplayError(
                f"Source shot manifest hash disagrees with run manifest for frame {frame_id}"
            )
        source_hash = ensemble._sha256(source_frame)
        if source_hash != recorded_hash:
            raise DetectorReplayError(
                f"Source attachment hash mismatch for frame {frame_id}"
            )
        suffix = source_frame.suffix or ".jpg"
        copied_frame = copied_input_dir / f"frame_{frame_id:06d}{suffix}"
        shutil.copy2(source_frame, copied_frame)
        copied_frame = copied_frame.resolve()
        copied_hash = ensemble._sha256(copied_frame)
        if copied_hash != recorded_hash:
            raise DetectorReplayError(
                f"Copied attachment hash mismatch for frame {frame_id}"
            )
        attachments.append(copied_frame)
        file_audits.append(
            {
                "frame_id": frame_id,
                "source_path": str(source_frame),
                "copied_path": str(copied_frame),
                "source_run_input_hash_key": recorded_key,
                "recorded_sha256": recorded_hash,
                "source_sha256": source_hash,
                "copied_sha256": copied_hash,
            }
        )
        runtime_frames.append(
            {
                "attachment_index": attachment_index,
                "frame_id": frame_id,
                "timestamp_sec": frame_record["timestamp_sec"],
                "path": str(copied_frame),
                "sha256": ensemble._sha256(copied_frame),
            }
        )
    selected_source_paths = tuple(item["source_path"] for item in file_audits)
    if (
        recorded_detector_paths is not None
        and selected_source_paths != recorded_detector_paths
    ):
        raise DetectorReplayError(
            "Source shot frame selection/order differs from the recorded detector "
            "input boundary"
        )
    runtime_manifest = {
        "shot_id": shot_id,
        "num_frames": int(source_manifest["num_frames"]),
        "fps": float(source_manifest["fps"]),
        "reference_frames": runtime_frames,
    }
    runtime_manifest_path = run_dir / "detector_input_manifest.json"
    ensemble._atomic_write_json(runtime_manifest_path, runtime_manifest)
    copied_files = _file_hashes(copied_input_dir)
    expected_copied_files = {
        Path(item["copied_path"]).name: item["recorded_sha256"]
        for item in file_audits
    }
    if copied_files != expected_copied_files:
        raise DetectorReplayError(
            "Replay input bundle contains files outside the trusted detector attachments"
        )
    bundle_audit = {
        "source_path": str(source_input_dir.resolve()),
        "copied_path": str(copied_input_dir.resolve()),
        "source_run_manifest": _artifact(source_run_manifest_path),
        "source_run_status_success": True,
        "source_run_input_hashes_validated": True,
        "source_detector_input_boundary_validated": (
            recorded_detector_paths is not None
        ),
        "detector_relevant_frames_only": True,
        "prompt_bound_registry_files_copied": False,
        "source_shot_manifest": _artifact(source_manifest_path),
        "runtime_detector_manifest": _artifact(runtime_manifest_path),
        "all_files_exact_hash_match": True,
        "file_count": len(file_audits),
        "files": file_audits,
    }
    return attachments, runtime_manifest, bundle_audit


def _attempt_artifacts(run_dir: Path) -> Dict[str, Dict[str, Any]]:
    artifacts: Dict[str, Dict[str, Any]] = {}
    for directory_name in ("prompts", "codex_attempts"):
        directory = run_dir / directory_name
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if path.is_file():
                artifacts[f"{directory_name}/{path.name}"] = _artifact(path)
    return artifacts


def replay_detector_panel_for_shot(
    *,
    source_shot_dir: Path,
    run_dir: Path,
    codex_bin: str,
    model: Optional[str],
    timeout_sec: int,
    max_workers: int,
    skill_dir: Path,
    detector_roles: Optional[Sequence[Tuple[str, str, str]]] = None,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Replay the configured detector panel for exactly one immutable shot."""
    model = _required_model(model)
    roles = _validated_detector_role_snapshot(
        tuple(ensemble.DETECTOR_ROLES) if detector_roles is None else detector_roles
    )
    if roles != _validated_detector_role_snapshot(tuple(ensemble.DETECTOR_ROLES)):
        raise DetectorReplayError(
            "Detector role snapshot differs from the current configured panel"
        )
    detector_ids = [role for role, _, _ in roles]
    if not 1 <= max_workers <= len(roles):
        raise DetectorReplayError(f"ensemble max_workers must be in [1, {len(roles)}]")
    if timeout_sec < 1:
        raise DetectorReplayError("codex timeout must be positive")

    started = time.perf_counter()
    shot_id = source_shot_dir.name
    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest_path = run_dir / "run_manifest.json"
    manifest: Dict[str, Any] = {
        "protocol_version": ensemble.PROTOCOL_VERSION,
        "replay_kind": "detector_panel_only_fixed_input",
        "status": "running",
        "start_utc": _utc_now(),
        "shot_id": shot_id,
        "source_shot_dir": str(source_shot_dir.resolve()),
        "model": model,
        "model_resolution": "explicit_argument",
        "codex_cli_version": ensemble._codex_version(codex_bin),
        "codex_timeout_sec": timeout_sec,
        "ensemble_max_workers": max_workers,
        "detector_count_expected": len(roles),
        "detector_roles": detector_ids,
        "detector_role_snapshot": _role_snapshot_record(roles),
        "detector_method": roles[0][1],
        "detector_attempts": [],
        "stages_executed": {
            "detectors": True,
            "inventory_adjudicator": False,
            "identity_verifiers": False,
            "graph_partition_planners": False,
            "prompt_bound_matcher": False,
            "grounding_dino": False,
            "relation_extraction": False,
        },
        "isolation": {
            "explicit_attachments_are_single_shot_frames_only": True,
            "cross_shot_content_excluded_from_prompt": True,
            "prompt_bound_registry_excluded_from_attachments": True,
            "prompt_bound_registry_content_excluded_from_prompt": True,
            "filesystem_read_allowlist_enforced": False,
            "detector_method_parity": (
                "same prompt method; only detector_id and local IDs differ"
            ),
        },
        "input_integrity_checks": [],
        "artifacts": {},
    }
    ensemble._atomic_write_json(manifest_path, manifest)
    usages: list[Optional[Dict[str, Optional[int]]]] = []
    invocation_count = 0

    try:
        attachments, shot_manifest, bundle_audit = _prepare_shot_inputs(
            source_shot_dir=source_shot_dir,
            run_dir=run_dir,
        )
        allowed_input_paths = [str(path) for path in attachments]
        detector_policy_text, detector_policy_path, detector_policy_hash = (
            ensemble._load_detector_policy(skill_dir.resolve())
        )
        policy_snapshot = run_dir / "policy" / "detector-protocol.md"
        policy_snapshot.parent.mkdir(parents=True, exist_ok=False)
        shutil.copy2(detector_policy_path, policy_snapshot)
        schema_snapshot = run_dir / "policy" / ensemble.DETECTOR_SCHEMA.name
        shutil.copy2(ensemble.DETECTOR_SCHEMA, schema_snapshot)
        if ensemble._sha256(policy_snapshot) != detector_policy_hash:
            raise DetectorReplayError("Detector policy snapshot hash mismatch")
        if ensemble._sha256(schema_snapshot) != ensemble._sha256(
            ensemble.DETECTOR_SCHEMA
        ):
            raise DetectorReplayError("Detector schema snapshot hash mismatch")

        frozen_detector_inputs = {
            "attachments": {
                str(path.resolve()): ensemble._sha256(path) for path in attachments
            },
            "detector_policy_snapshot_sha256": ensemble._sha256(policy_snapshot),
            "detector_schema_snapshot_sha256": ensemble._sha256(schema_snapshot),
            "detector_role_snapshot_sha256": _role_snapshot_record(roles)["sha256"],
        }

        def assert_frozen_detector_inputs(phase: str) -> None:
            validation_error: Optional[str] = None
            try:
                current_roles = _validated_detector_role_snapshot(
                    tuple(ensemble.DETECTOR_ROLES)
                )
                observed = {
                    "attachments": {
                        str(path.resolve()): ensemble._sha256(path)
                        for path in attachments
                    },
                    "detector_policy_snapshot_sha256": ensemble._sha256(
                        policy_snapshot
                    ),
                    "detector_schema_snapshot_sha256": ensemble._sha256(
                        schema_snapshot
                    ),
                    "detector_role_snapshot_sha256": _role_snapshot_record(
                        current_roles
                    )["sha256"],
                }
                matched = (
                    observed == frozen_detector_inputs and current_roles == roles
                )
                if not matched:
                    validation_error = "hash_or_role_snapshot_mismatch"
            except (DetectorReplayError, OSError) as exc:
                matched = False
                validation_error = str(exc)
            manifest["input_integrity_checks"].append(
                {
                    "phase": phase,
                    "checked_utc": _utc_now(),
                    "matched_frozen_snapshot": matched,
                    "error": validation_error,
                }
            )
            ensemble._atomic_write_json(manifest_path, manifest)
            if not matched:
                raise DetectorReplayError(
                    f"Frozen detector inputs changed before {phase}"
                )

        manifest["input_bundle"] = bundle_audit
        manifest["allowed_input_paths"] = allowed_input_paths
        manifest["input_hashes"] = copy.deepcopy(
            frozen_detector_inputs["attachments"]
        )
        manifest["frozen_detector_inputs"] = copy.deepcopy(frozen_detector_inputs)
        manifest["detector_policy"] = {
            "version": ensemble.DETECTOR_POLICY_VERSION,
            "source": _artifact(detector_policy_path),
            "snapshot": _artifact(policy_snapshot),
            "full_downstream_skill_visible": False,
        }
        manifest["detector_schema"] = {
            "source": _artifact(ensemble.DETECTOR_SCHEMA),
            "snapshot": _artifact(schema_snapshot),
        }
        manifest["source_hashes"] = {
            "ensemble_detector_implementation": _artifact(
                Path(ensemble.__file__).resolve()
            ),
            "detector_replay_utility": _artifact(Path(__file__).resolve()),
        }
        ensemble._atomic_write_json(manifest_path, manifest)

        detector_base = ensemble._detector_base_prompt(
            shot_id=shot_id,
            shot_manifest=shot_manifest,
            allowed_input_paths=allowed_input_paths,
            detector_policy_text=detector_policy_text,
        )
        work_dir = run_dir / "agent_workdirs" / "inventory"
        work_dir.mkdir(parents=True, exist_ok=False)
        detector_dir = run_dir / "detector_runs"
        detector_dir.mkdir(parents=True, exist_ok=False)
        prompt_dir = run_dir / "prompts"
        attempt_dir = run_dir / "codex_attempts"

        def invoke_detector(
            role_data: Tuple[str, str, str], attempt: int
        ) -> Tuple[
            str,
            Optional[Dict[str, Any]],
            Optional[ensemble.CodexInvocation],
            Optional[BaseException],
        ]:
            role, _, instruction = role_data
            prefix = f"{role}.attempt{attempt}"
            prompt = ensemble._detector_prompt(detector_base, role, instruction)
            ensemble._atomic_write_text(prompt_dir / f"{prefix}.txt", prompt)
            output_path = attempt_dir / f"{prefix}.json"
            events_path = attempt_dir / f"{prefix}.events.jsonl"
            invocation: Optional[ensemble.CodexInvocation] = None
            try:
                invocation = ensemble.run_codex_json(
                    prompt=prompt,
                    attachments=attachments,
                    schema_path=schema_snapshot,
                    output_path=output_path,
                    events_path=events_path,
                    stderr_path=attempt_dir / f"{prefix}.stderr.log",
                    codex_bin=codex_bin,
                    model=model,
                    timeout_sec=timeout_sec,
                    work_dir=work_dir,
                    verbose=verbose,
                )
                ensemble.validate_ledger(
                    invocation.payload,
                    shot_id=shot_id,
                    detector_id=role,
                    source_kind="detector",
                    valid_frame_ids=[
                        item["frame_id"] for item in shot_manifest["reference_frames"]
                    ],
                    allowed_input_paths=allowed_input_paths,
                )
                return role, invocation.payload, invocation, None
            except (ensemble.EnsembleError, OSError) as exc:
                return role, None, invocation, exc

        ledgers: Dict[str, Dict[str, Any]] = {}
        pending = list(roles)
        for attempt in (1, 2):
            if not pending:
                break
            assert_frozen_detector_inputs(f"detector_attempt_{attempt}")
            attempt_started = time.perf_counter()
            print(
                f"[detector-replay {shot_id}] attempt {attempt}: "
                f"starting {len(pending)} detector calls",
                flush=True,
            )
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=min(max_workers, len(pending))
            ) as executor:
                futures = [
                    executor.submit(invoke_detector, role_data, attempt)
                    for role_data in pending
                ]
                invocation_count += len(futures)
                outcomes = [future.result() for future in futures]
            valid_count = sum(payload is not None for _, payload, _, _ in outcomes)
            print(
                f"[detector-replay {shot_id}] attempt {attempt}: "
                f"{valid_count}/{len(outcomes)} valid "
                f"({time.perf_counter() - attempt_started:.1f}s)",
                flush=True,
            )
            next_pending = []
            for role, payload, invocation, error in outcomes:
                events_path = attempt_dir / f"{role}.attempt{attempt}.events.jsonl"
                accounting = ensemble._codex_attempt_accounting(
                    invocation=invocation,
                    error=error,
                    events_path=events_path,
                )
                manifest["detector_attempts"].append(
                    {
                        "detector_id": role,
                        "attempt": attempt,
                        "status": "success" if payload is not None else "failed",
                        "error": str(error) if error is not None else None,
                        **accounting,
                    }
                )
                if accounting["subprocess_started"]:
                    usages.append(accounting["token_usage"])
                if payload is None:
                    next_pending.append(next(item for item in roles if item[0] == role))
                    continue
                ledgers[role] = payload
                ensemble._atomic_write_json(detector_dir / f"{role}.json", payload)
            pending = next_pending
            manifest["detector_count_valid"] = len(ledgers)
            manifest["detector_invocations"] = invocation_count
            manifest["token_usage"] = ensemble._aggregate_usage(usages)
            manifest["attempt_artifacts"] = _attempt_artifacts(run_dir)
            ensemble._atomic_write_json(manifest_path, manifest)

        missing = [role for role in detector_ids if role not in ledgers]
        manifest["detector_count_valid"] = len(ledgers)
        manifest["detector_invocations"] = invocation_count
        manifest["token_usage"] = ensemble._aggregate_usage(usages)
        manifest["runtime_seconds"] = round(time.perf_counter() - started, 6)
        manifest["end_utc"] = _utc_now()
        manifest["attempt_artifacts"] = _attempt_artifacts(run_dir)
        manifest["artifacts"]["detector_ledgers"] = {
            role: _artifact(detector_dir / f"{role}.json")
            for role in detector_ids
            if role in ledgers
        }
        if missing:
            manifest["status"] = "incomplete"
            manifest["failure_kind"] = "detector_retry_exhausted"
            manifest["error"] = f"Missing valid detector ledgers after retry: {missing}"
            ensemble._atomic_write_json(manifest_path, manifest)
            raise DetectorReplayIncompleteError(manifest["error"])

        assert_frozen_detector_inputs("success_commit")
        manifest["status"] = "success"
        manifest["failure_kind"] = None
        manifest["error"] = None
        ensemble._atomic_write_json(manifest_path, manifest)
        print(
            f"[detector-replay {shot_id}] complete: {len(ledgers)}/{len(roles)} "
            f"ledgers, {manifest['runtime_seconds']:.1f}s",
            flush=True,
        )
        return copy.deepcopy(manifest)
    except DetectorReplayIncompleteError:
        raise
    except Exception as exc:
        manifest.update(
            {
                "status": "failed",
                "failure_kind": (
                    "setup_failure"
                    if not manifest["detector_attempts"]
                    else "execution_or_integrity_failure"
                ),
                "error": str(exc),
                "end_utc": _utc_now(),
                "runtime_seconds": round(time.perf_counter() - started, 6),
                "detector_invocations": invocation_count,
                "token_usage": ensemble._aggregate_usage(usages),
                "attempt_artifacts": _attempt_artifacts(run_dir),
            }
        )
        ensemble._atomic_write_json(manifest_path, manifest)
        raise


def _default_output_root(source_run: Path) -> Path:
    return source_run.parent / "detector_only_replay" / _utc_stamp()


def run_detector_replay(
    *,
    source_run: Path,
    output_root: Path,
    shot_ids: Sequence[str],
    codex_bin: str,
    model: Optional[str],
    timeout_sec: int,
    max_workers: int,
    parallel_shots: int,
    skill_dir: Path,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Replay panels with explicit per-call attachment and prompt boundaries."""
    model = _required_model(model)
    detector_roles = _validated_detector_role_snapshot(
        tuple(ensemble.DETECTOR_ROLES)
    )
    source_run = source_run.resolve()
    shot_dirs = _source_shot_dirs(source_run, shot_ids)
    detector_count = len(detector_roles)
    if not 1 <= max_workers <= detector_count:
        raise DetectorReplayError(
            f"ensemble max_workers must be in [1, {detector_count}]"
        )
    if parallel_shots < 1:
        raise DetectorReplayError("parallel_shots must be at least 1")
    if timeout_sec < 1:
        raise DetectorReplayError("codex timeout must be positive")
    output_root = output_root.resolve()
    try:
        output_root.relative_to(source_run)
    except ValueError:
        pass
    else:
        raise DetectorReplayError("Output root may not be inside the source run")
    output_root.mkdir(parents=True, exist_ok=False)
    top_manifest_path = output_root / "replay_manifest.json"
    top_manifest: Dict[str, Any] = {
        "replay_kind": "detector_panel_only_fixed_input",
        "status": "running",
        "start_utc": _utc_now(),
        "source_run": str(source_run),
        "output_root": str(output_root),
        "model": model,
        "model_resolution": "explicit_argument",
        "requested_shot_ids": [path.name for path in shot_dirs],
        "parallel_shots": parallel_shots,
        "ensemble_max_workers": max_workers,
        "detector_count_per_shot": detector_count,
        "detector_method": detector_roles[0][1],
        "detector_role_snapshot": _role_snapshot_record(detector_roles),
        "explicit_attachments_are_single_shot_frames_only": True,
        "cross_shot_content_excluded_from_prompt": True,
        "prompt_bound_registry_excluded_from_attachments": True,
        "prompt_bound_registry_content_excluded_from_prompt": True,
        "filesystem_read_allowlist_enforced": False,
        "downstream_stages_executed": False,
        "results": [],
    }
    ensemble._atomic_write_json(top_manifest_path, top_manifest)
    print(
        f"[detector-replay] starting {len(shot_dirs)} shot(s), "
        f"parallel_shots={parallel_shots}, detector_workers={max_workers}",
        flush=True,
    )

    def replay(source_shot_dir: Path) -> Dict[str, Any]:
        shot_id = source_shot_dir.name
        print(f"[detector-replay] {shot_id}: preparing immutable input", flush=True)
        try:
            result = replay_detector_panel_for_shot(
                source_shot_dir=source_shot_dir,
                run_dir=output_root / shot_id,
                codex_bin=codex_bin,
                model=model,
                timeout_sec=timeout_sec,
                max_workers=max_workers,
                skill_dir=skill_dir,
                detector_roles=detector_roles,
                verbose=verbose,
            )
        except DetectorReplayIncompleteError as exc:
            shot_manifest_path = output_root / shot_id / "run_manifest.json"
            return {
                "shot_id": shot_id,
                "status": "incomplete",
                "failure_kind": "detector_retry_exhausted",
                "error": str(exc),
                "run_manifest": (
                    str(shot_manifest_path.resolve())
                    if shot_manifest_path.is_file()
                    else None
                ),
            }
        except Exception as exc:
            shot_manifest_path = output_root / shot_id / "run_manifest.json"
            failure_kind = "setup_or_execution_failure"
            if shot_manifest_path.is_file():
                try:
                    child_manifest = json.loads(
                        shot_manifest_path.read_text(encoding="utf-8")
                    )
                except (OSError, json.JSONDecodeError):
                    child_manifest = None
                if isinstance(child_manifest, Mapping):
                    failure_kind = str(
                        child_manifest.get("failure_kind") or failure_kind
                    )
            return {
                "shot_id": shot_id,
                "status": "failed",
                "failure_kind": failure_kind,
                "error": str(exc),
                "run_manifest": (
                    str(shot_manifest_path.resolve())
                    if shot_manifest_path.is_file()
                    else None
                ),
            }
        return {
            "shot_id": shot_id,
            "status": "success",
            "failure_kind": None,
            "error": None,
            "detector_count_valid": result["detector_count_valid"],
            "detector_invocations": result["detector_invocations"],
            "runtime_seconds": result["runtime_seconds"],
            "token_usage": result["token_usage"],
            "run_manifest": str(
                (output_root / shot_id / "run_manifest.json").resolve()
            ),
        }

    results = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(parallel_shots, len(shot_dirs))
    ) as executor:
        future_by_shot = {
            executor.submit(replay, shot_dir): shot_dir.name for shot_dir in shot_dirs
        }
        for future in concurrent.futures.as_completed(future_by_shot):
            result = future.result()
            results.append(result)
            print(
                f"[detector-replay] {result['shot_id']}: {result['status']}",
                flush=True,
            )

    results.sort(key=lambda item: item["shot_id"])
    result_statuses = {item["status"] for item in results}
    if result_statuses == {"success"}:
        aggregate_status = "success"
    elif "failed" in result_statuses:
        aggregate_status = "failed"
    else:
        aggregate_status = "incomplete"
    top_manifest.update(
        {
            "status": aggregate_status,
            "end_utc": _utc_now(),
            "results": results,
        }
    )
    ensemble._atomic_write_json(top_manifest_path, top_manifest)
    print(
        f"[detector-replay] {top_manifest['status']}: {output_root}",
        flush=True,
    )
    return top_manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_run", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--shots", nargs="*", default=[])
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--codex-model", required=True)
    parser.add_argument("--codex-timeout-sec", type=_positive_int, default=1800)
    parser.add_argument("--ensemble-max-workers", type=_positive_int, default=4)
    parser.add_argument("--parallel-shots", type=_positive_int, default=1)
    parser.add_argument(
        "--ensemble-skill-dir",
        type=Path,
        default=REPOSITORY_ROOT
        / ".agents"
        / "skills"
        / "ensemble-shot-entity-detection",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    source_run = args.source_run.resolve()
    output_root = (
        args.output_root.resolve()
        if args.output_root is not None
        else _default_output_root(source_run).resolve()
    )
    try:
        manifest = run_detector_replay(
            source_run=source_run,
            output_root=output_root,
            shot_ids=args.shots,
            codex_bin=args.codex_bin,
            model=args.codex_model,
            timeout_sec=args.codex_timeout_sec,
            max_workers=args.ensemble_max_workers,
            parallel_shots=args.parallel_shots,
            skill_dir=args.ensemble_skill_dir,
            verbose=args.verbose,
        )
    except (DetectorReplayError, ensemble.EnsembleError, OSError, ValueError) as exc:
        print(f"[detector-replay] failed: {exc}", flush=True)
        return 2
    if manifest["status"] == "success":
        return 0
    return 1 if manifest["status"] == "incomplete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
