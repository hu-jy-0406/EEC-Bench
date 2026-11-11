#!/usr/bin/env python3
"""Coarsen strict graph-granularity families behind an existence write firewall."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import ensemble_shot_entity_detection as ensemble  # noqa: E402
import granularity_family_stage as family_stage  # noqa: E402


FAMILY_PLAN_SCHEMA = (
    PROJECT_ROOT / "schemas" / "codex_granularity_family_plan_v0.3.schema.json"
)
FAMILY_PLAN_PROTOCOL = family_stage.FAMILY_PLAN_PROTOCOL
DEFAULT_SOURCE_RUN = (
    PROJECT_ROOT
    / "experiments"
    / "study_inconsistent_2"
    / "prompt_unbound_prefilter"
    / "detector_adjudicator_only"
    / "run_20260906T172749Z"
)
DEFAULT_OUTPUT_PARENT = (
    PROJECT_ROOT
    / "experiments"
    / "study_inconsistent_2"
    / "prompt_unbound_prefilter"
    / "granularity_family_ablation"
)
DEFAULT_SHOT_DIRS = (
    "inconsistent_study_shot1",
    "inconsitent_study_shot3",
)
DETECTOR_ID_PATTERN = family_stage.DETECTOR_ID_PATTERN
SUPPORT_QUALITY_RANK = family_stage.SUPPORT_QUALITY_RANK
PROPOSAL_FIELDS = family_stage.PROPOSAL_FIELDS
FamilyPlanError = family_stage.FamilyPlanError


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _read_json(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FamilyPlanError(f"Expected a JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


_json_hash = family_stage.json_hash


def _artifact(path: Path) -> Dict[str, str]:
    return {"path": str(path.resolve()), "sha256": _sha256(path)}


_require_unique = family_stage._require_unique
_detector_sort_key = family_stage.detector_sort_key
_planner_view = family_stage.planner_view
_planner_baseline_view = family_stage.planner_baseline_view
_build_prompt = family_stage.build_prompt
build_panel_positions = family_stage.build_panel_positions
_select_resolutions = family_stage.select_resolutions
_merge_frame_presence = family_stage.merge_frame_presence


def validate_family_plan(
    plan: Mapping[str, Any],
    *,
    shot_id: str,
    baseline: Mapping[str, Any],
    anonymous_view: Mapping[str, Any],
    valid_frame_ids: Sequence[int],
) -> None:
    family_stage.validate_family_plan(
        plan,
        shot_id=shot_id,
        baseline=baseline,
        anonymous_view=anonymous_view,
        valid_frame_ids=valid_frame_ids,
        base_protocol=ensemble.PROTOCOL_VERSION,
    )


def validate_source_map(
    source_map: Mapping[str, Any],
    *,
    shot_id: str,
    proposal_ids: set[str],
    detector_ids: Sequence[str],
    anonymous_view: Mapping[str, Any],
    detector_ledgers: Sequence[Mapping[str, Any]],
) -> None:
    family_stage.validate_source_map(
        source_map,
        shot_id=shot_id,
        proposal_ids=proposal_ids,
        detector_ids=detector_ids,
        anonymous_view=anonymous_view,
        detector_ledgers=detector_ledgers,
        base_protocol=ensemble.PROTOCOL_VERSION,
    )


def _assemble_final(
    *,
    baseline: Mapping[str, Any],
    anonymous_view: Mapping[str, Any],
    plan: Mapping[str, Any],
    resolutions: Sequence[Mapping[str, Any]],
    shot_id: str,
    valid_frame_ids: Sequence[int],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    return family_stage.assemble_final(
        baseline=baseline,
        anonymous_view=anonymous_view,
        plan=plan,
        resolutions=resolutions,
        shot_id=shot_id,
        valid_frame_ids=valid_frame_ids,
        base_protocol=ensemble.PROTOCOL_VERSION,
    )


def _attempt_usage(events_path: Path) -> Dict[str, Any] | None:
    if not events_path.is_file():
        return None
    return ensemble.shot_graph.parse_codex_token_usage(
        events_path.read_text(encoding="utf-8")
    )


def _run_one_shot(
    *,
    source_shot_dir: Path,
    output_shot_dir: Path,
    skill_text: str,
    skill_hashes: Mapping[str, str],
    codex_bin: str,
    model: str | None,
    timeout_sec: int,
) -> Dict[str, Any]:
    started = time.perf_counter()
    start_utc = _utc_now()
    shot_manifest_path = source_shot_dir / "input_bundle" / "shot_manifest.json"
    anonymous_path = (
        source_shot_dir / "adjudication" / "anonymized_candidates.json"
    )
    source_map_path = (
        source_shot_dir / "adjudication" / "source_map.private.json"
    )
    baseline_path = (
        source_shot_dir / "adjudication" / "adjudicator_initial.json"
    )
    source_manifest_path = source_shot_dir / "run_manifest.json"
    shot_manifest = _read_json(shot_manifest_path)
    anonymous_view = _read_json(anonymous_path)
    source_map = _read_json(source_map_path)
    baseline = _read_json(baseline_path)
    source_manifest = _read_json(source_manifest_path)
    shot_id = str(shot_manifest["shot_id"])
    if (
        source_manifest.get("shot_id") != shot_id
        or source_manifest.get("status") != "success"
        or source_manifest.get("protocol_version") != ensemble.PROTOCOL_VERSION
    ):
        raise FamilyPlanError("Source shot manifest is incompatible or incomplete")
    detector_counts = source_manifest.get("detector_entity_counts")
    if not isinstance(detector_counts, dict) or len(detector_counts) < 2:
        raise FamilyPlanError("Source manifest lacks a complete detector inventory")
    detector_ids = sorted(
        (str(value) for value in detector_counts), key=_detector_sort_key
    )
    ledger_paths = [
        source_shot_dir / "detector_runs" / f"{detector_id}.json"
        for detector_id in detector_ids
    ]
    actual_ledger_paths = set(
        (source_shot_dir / "detector_runs").glob("detector_*.json")
    )
    if actual_ledger_paths != set(ledger_paths):
        raise FamilyPlanError(
            "Detector ledger files do not exactly match the source manifest"
        )
    frame_ids = [
        int(item["frame_id"]) for item in shot_manifest["reference_frames"]
    ]
    attachments = [
        Path(item["path"]).resolve()
        for item in shot_manifest["reference_frames"]
    ]
    allowed_paths = [str(path) for path in attachments]
    ledgers = [_read_json(path) for path in ledger_paths]
    for detector_id, ledger in zip(detector_ids, ledgers):
        if ledger.get("detector_id") != detector_id:
            raise FamilyPlanError(
                f"Detector ledger identity mismatch: expected {detector_id}"
            )
        expected_count = detector_counts[detector_id]
        if isinstance(expected_count, bool) or not isinstance(expected_count, int):
            raise FamilyPlanError(
                f"Source manifest has invalid count for {detector_id}"
            )
        if expected_count != len(ledger["entities"]):
            raise FamilyPlanError(
                f"Detector entity count mismatch for {detector_id}"
            )
        ensemble.validate_ledger(
            ledger,
            shot_id=shot_id,
            detector_id=detector_id,
            source_kind="detector",
            valid_frame_ids=frame_ids,
            allowed_input_paths=allowed_paths,
        )
    proposal_ids = _require_unique(
        [
            item["anonymous_proposal_id"]
            for item in anonymous_view["proposals"]
        ],
        "anonymous proposal IDs",
    )
    validate_source_map(
        source_map,
        shot_id=shot_id,
        proposal_ids=proposal_ids,
        detector_ids=detector_ids,
        anonymous_view=anonymous_view,
        detector_ledgers=ledgers,
    )
    ensemble.validate_decisions(
        baseline,
        shot_id=shot_id,
        anonymous_ids=sorted(proposal_ids),
        valid_frame_ids=frame_ids,
    )

    frozen_paths = [
        shot_manifest_path,
        *attachments,
        *ledger_paths,
        anonymous_path,
        source_map_path,
        baseline_path,
        source_manifest_path,
    ]
    hashes_before = {str(path.resolve()): _sha256(path) for path in frozen_paths}
    prompts_dir = output_shot_dir / "prompts"
    attempts_dir = output_shot_dir / "codex_attempts"
    adjudication_dir = output_shot_dir / "adjudication"
    planner_work_dir = output_shot_dir / "agent_workdirs" / "family_planner"
    prompts_dir.mkdir(parents=True, exist_ok=False)
    attempts_dir.mkdir(parents=True, exist_ok=False)
    adjudication_dir.mkdir(parents=True, exist_ok=False)
    planner_work_dir.mkdir(parents=True, exist_ok=False)

    planner_view = _planner_view(anonymous_view)
    planner_baseline = _planner_baseline_view(baseline)
    prompt = _build_prompt(
        shot_id=shot_id,
        shot_manifest=shot_manifest,
        anonymous_view=planner_view,
        baseline=planner_baseline,
        skill_text=skill_text,
    )
    prompt_path = prompts_dir / "granularity_family_planner.txt"
    ensemble._atomic_write_text(prompt_path, prompt)
    print(
        f"[family-ablation] {shot_id}: source-blind family planning over "
        f"{len(proposal_ids)} frozen proposals",
        flush=True,
    )

    attempts: List[Dict[str, Any]] = []
    plan: Dict[str, Any] | None = None
    for attempt in range(1, 3):
        output_path = attempts_dir / f"family_plan.attempt{attempt}.json"
        events_path = (
            attempts_dir / f"family_plan.attempt{attempt}.events.jsonl"
        )
        stderr_path = attempts_dir / f"family_plan.attempt{attempt}.stderr.log"
        attempt_started = time.perf_counter()
        invocation: ensemble.CodexInvocation | None = None
        error = None
        try:
            invocation = ensemble.run_codex_json(
                prompt=prompt,
                attachments=attachments,
                schema_path=FAMILY_PLAN_SCHEMA,
                output_path=output_path,
                events_path=events_path,
                stderr_path=stderr_path,
                codex_bin=codex_bin,
                model=model,
                timeout_sec=timeout_sec,
                work_dir=planner_work_dir,
                persistent=False,
                verbose=False,
            )
            validate_family_plan(
                invocation.payload,
                shot_id=shot_id,
                baseline=baseline,
                anonymous_view=planner_view,
                valid_frame_ids=frame_ids,
            )
            plan = invocation.payload
        except Exception as exc:  # bounded identical-input retry
            error = str(exc)
        usage = (
            invocation.token_usage
            if invocation is not None
            else _attempt_usage(events_path)
        )
        attempts.append(
            {
                "attempt": attempt,
                "status": "success" if plan is not None else "failed",
                "error": error,
                "runtime_seconds": round(
                    time.perf_counter() - attempt_started, 6
                ),
                "token_usage": usage,
                "thread_id": (
                    invocation.thread_id if invocation is not None else None
                ),
            }
        )
        if plan is not None:
            break
        if attempt == 1:
            print(
                f"[family-ablation] {shot_id}: first plan invalid; retrying once",
                flush=True,
            )
    if plan is None:
        raise FamilyPlanError(
            f"{shot_id}: no valid family plan after two attempts: "
            f"{attempts[-1]['error']}"
        )

    hashes_after = {str(path.resolve()): _sha256(path) for path in frozen_paths}
    if hashes_after != hashes_before:
        raise FamilyPlanError("A frozen input changed during family planning")
    family_plan_path = adjudication_dir / "granularity_family_plan.json"
    ensemble._atomic_write_json(family_plan_path, plan)

    # Provenance is used by deterministic code only after the source-blind plan freezes.
    panel_positions = build_panel_positions(plan, source_map, detector_ids)
    panel_positions_path = adjudication_dir / "panel_positions.private.json"
    ensemble._atomic_write_json(panel_positions_path, panel_positions)
    spatial_vetoes = family_stage.collect_spatial_vetoes(
        (plan,), baseline=baseline, anonymous_view=anonymous_view,
    )
    resolutions = _select_resolutions(plan, panel_positions, spatial_vetoes=spatial_vetoes)
    resolutions_path = adjudication_dir / "granularity_resolutions.json"
    ensemble._atomic_write_json(
        resolutions_path,
        {
            "protocol_version": FAMILY_PLAN_PROTOCOL,
            "shot_id": shot_id,
            "selection_policy": (
                "all pairwise member boundaries need typed shot-observed independence "
                "evidence to retain members; otherwise coarsen to one group; detector "
                "provenance and counts are audit-only"
            ),
            "resolutions": resolutions,
        },
    )
    final, firewall_audit = _assemble_final(
        baseline=baseline,
        anonymous_view=anonymous_view,
        plan=plan,
        resolutions=resolutions,
        shot_id=shot_id,
        valid_frame_ids=frame_ids,
    )
    ensemble.validate_decisions(
        final,
        shot_id=shot_id,
        anonymous_ids=sorted(proposal_ids),
        valid_frame_ids=frame_ids,
    )
    final_path = adjudication_dir / "adjudicator_decisions.json"
    firewall_path = adjudication_dir / "partition_firewall_audit.json"
    ensemble._atomic_write_json(final_path, final)
    ensemble._atomic_write_json(firewall_path, firewall_audit)

    frozen_inputs = {
        "artifacts": [
            {"path": path, "sha256": digest}
            for path, digest in sorted(hashes_before.items())
        ],
        "source_map_explicitly_supplied_to_family_planner": False,
        "provenance_derived_candidate_diagnostics_supplied_to_planner": False,
        "provenance_derived_baseline_narratives_supplied_to_planner": False,
        "procedurally_isolated_planner_workdir": str(planner_work_dir.resolve()),
        "os_level_read_allowlist_enforced": False,
        "other_shot_explicitly_supplied": False,
        "proposal_count": len(proposal_ids),
        "detector_ids": detector_ids,
    }
    frozen_path = output_shot_dir / "frozen_inputs.json"
    ensemble._atomic_write_json(frozen_path, frozen_inputs)
    decision_counts = {
        decision: sum(
            cluster["decision"] == decision for cluster in final["clusters"]
        )
        for decision in ("accept", "reject", "abstain")
    }
    manifest = {
        "protocol_version": FAMILY_PLAN_PROTOCOL,
        "base_inventory_protocol_version": ensemble.PROTOCOL_VERSION,
        "mode": "source_blind_granularity_family_firewall_ablation",
        "status": "success",
        "start_utc": start_utc,
        "end_utc": _utc_now(),
        "shot_id": shot_id,
        "source_shot_run": str(source_shot_dir.resolve()),
        "detector_ids": detector_ids,
        "family_count": len(plan["families"]),
        "applied_family_count": len(firewall_audit["applied_family_ids"]),
        "baseline_cluster_count": len(baseline["clusters"]),
        "final_cluster_count": len(final["clusters"]),
        "final_decision_counts": decision_counts,
        "source_map_explicitly_supplied_to_model": False,
        "provenance_derived_candidate_diagnostics_supplied_to_model": False,
        "provenance_derived_baseline_narratives_supplied_to_model": False,
        "procedurally_isolated_planner_workdir": str(planner_work_dir.resolve()),
        "os_level_read_allowlist_enforced": False,
        "panel_positions_gate_family_application": False,
        "panel_positions_select_group_vs_members": False,
        "panel_counts_select_partition": False,
        "post_provenance_model_calls": 0,
        "cross_shot_input": False,
        "excluded_stages": [
            "detectors",
            "existence_reconsideration",
            "physical_identity_reconsideration",
            "verifiers",
            "prompt_bound_matcher",
            "grounding",
            "relations",
            "cross_shot_reconciliation",
        ],
        "attempts": attempts,
        "token_usage": ensemble._aggregate_usage(
            [item["token_usage"] for item in attempts]
        ),
        "runtime_seconds": round(time.perf_counter() - started, 6),
        "skill_hashes": dict(skill_hashes),
        "schema_hashes": {
            str(FAMILY_PLAN_SCHEMA.resolve()): _sha256(FAMILY_PLAN_SCHEMA),
            str(ensemble.ADJUDICATION_SCHEMA.resolve()): _sha256(
                ensemble.ADJUDICATION_SCHEMA
            ),
        },
        "artifacts": {
            "frozen_inputs": _artifact(frozen_path),
            "prompt": _artifact(prompt_path),
            "family_plan": _artifact(family_plan_path),
            "panel_positions_private": _artifact(panel_positions_path),
            "resolutions": _artifact(resolutions_path),
            "final_adjudication": _artifact(final_path),
            "partition_firewall_audit": _artifact(firewall_path),
        },
    }
    manifest_path = output_shot_dir / "run_manifest.json"
    ensemble._atomic_write_json(manifest_path, manifest)
    print(
        f"[family-ablation] {shot_id}: complete in "
        f"{manifest['runtime_seconds']:.1f}s; families={manifest['family_count']}, "
        f"applied={manifest['applied_family_count']}, decisions={decision_counts}, "
        f"tokens={manifest['token_usage'].get('total_tokens')}",
        flush=True,
    )
    return manifest


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, default=DEFAULT_SOURCE_RUN)
    parser.add_argument("--output-parent", type=Path, default=DEFAULT_OUTPUT_PARENT)
    parser.add_argument(
        "--shot-dir",
        action="append",
        dest="shot_dirs",
        help="Source shot subdirectory; repeat for multiple shots",
    )
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout-sec", type=int, default=1800)
    parser.add_argument("--max-workers", type=int, default=2)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    source_run = args.source_run.resolve()
    shot_dirs = tuple(args.shot_dirs or DEFAULT_SHOT_DIRS)
    if not shot_dirs:
        raise FamilyPlanError("At least one --shot-dir is required")
    missing = [name for name in shot_dirs if not (source_run / name).is_dir()]
    if missing:
        raise FamilyPlanError(f"Source run is missing shot directories: {missing}")
    if args.max_workers < 1:
        raise FamilyPlanError("--max-workers must be positive")

    run_dir = args.output_parent.resolve() / f"run_{_utc_stamp()}"
    run_dir.mkdir(parents=True, exist_ok=False)
    skill_text, skill_hashes = ensemble._load_skill(ensemble.DEFAULT_SKILL_DIR)
    started = time.perf_counter()
    start_utc = _utc_now()
    print(f"[family-ablation] output: {run_dir}", flush=True)

    manifests: List[Dict[str, Any]] = []
    errors: List[str] = []
    worker_count = min(args.max_workers, len(shot_dirs))
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                _run_one_shot,
                source_shot_dir=source_run / shot_dir,
                output_shot_dir=run_dir / shot_dir,
                skill_text=skill_text,
                skill_hashes=skill_hashes,
                codex_bin=args.codex_bin,
                model=args.model,
                timeout_sec=args.timeout_sec,
            ): shot_dir
            for shot_dir in shot_dirs
        }
        for future in concurrent.futures.as_completed(futures):
            shot_dir = futures[future]
            try:
                manifests.append(future.result())
            except Exception as exc:
                errors.append(f"{shot_dir}: {exc}")
                print(
                    f"[family-ablation] {shot_dir}: FAILED: {exc}", flush=True
                )

    manifests.sort(key=lambda item: item["shot_id"])
    all_usages = [
        attempt["token_usage"]
        for manifest in manifests
        for attempt in manifest["attempts"]
    ]
    top_manifest = {
        "protocol_version": FAMILY_PLAN_PROTOCOL,
        "mode": "source_blind_granularity_family_firewall_ablation",
        "status": (
            "success"
            if not errors and len(manifests) == len(shot_dirs)
            else "failed"
        ),
        "start_utc": start_utc,
        "end_utc": _utc_now(),
        "source_run": str(source_run),
        "run_dir": str(run_dir),
        "shot_dirs": list(shot_dirs),
        "parallel_shot_calls": worker_count > 1,
        "cross_shot_input": False,
        "source_map_explicitly_supplied_to_model": False,
        "selection_policy": (
            "retain members only when typed visual evidence proves every pairwise "
            "member boundary; otherwise choose the coarsest stable group; panel "
            "provenance and detector counts are audit-only"
        ),
        "shots": manifests,
        "errors": errors,
        "token_usage": ensemble._aggregate_usage(all_usages),
        "runtime_seconds": round(time.perf_counter() - started, 6),
        "skill_hashes": dict(skill_hashes),
    }
    ensemble._atomic_write_json(run_dir / "run_manifest.json", top_manifest)
    print(
        f"[family-ablation] finished status={top_manifest['status']} "
        f"runtime={top_manifest['runtime_seconds']:.1f}s "
        f"tokens={top_manifest['token_usage'].get('total_tokens')}",
        flush=True,
    )
    print(f"[family-ablation] run_dir={run_dir}", flush=True)
    return 0 if top_manifest["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
