#!/usr/bin/env python3
"""Pipeline 2: detect scheduled entities first, then ask Codex only for extras."""

from __future__ import annotations

import argparse
import copy
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ensemble_shot_entity_detection import (
    DEFAULT_SKILL_DIR,
    PROTOCOL_VERSION as ENSEMBLE_PROTOCOL_VERSION,
    EnsembleError,
    EnsembleIncompleteError,
    run_ensemble_detection,
)
from prompt_unbound_common import (
    PromptUnboundError,
    RunRecorder,
    aggregate_token_usage,
    atomic_write_json,
    atomic_write_text,
    build_prompt_bound_graph,
    build_prompt_unbound_codex_prompt,
    classify_graph_entities,
    episode_graphs,
    ground_prompt_bound_targets,
    load_schedule_bundle,
    map_shots_to_schedule,
    merge_prompt_bound_and_unbound_graphs,
    parse_shot_keys,
    read_json,
    render_grounding_artifacts,
    run_codex_with_prompt,
    shot_graph,
    strong_ensemble_unbound_entity_ids,
    targets_for_shot,
    validate_thresholds,
)
from role_model_routing import resolve_model_routing


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_PROMPT = PROJECT_ROOT / "prompts" / "shot_prompt_unbound_entity_graph_v0.3.md"
PROMPT_VERSION = "shot_prompt_unbound_entity_graph_v0.3"


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Ground the prompt-bound entity schedule first, show those exclusions "
            "to Codex, and ground/write only prompt-unbound graph entities."
        )
    )
    parser.add_argument("experiment_dir", type=Path)
    parser.add_argument(
        "--schedule-file",
        type=Path,
        help="JSON containing entity_schedule and optionally entity_descriptions "
        "(default: EXPERIMENT_DIR/entity_schedule.json)",
    )
    parser.add_argument(
        "--shot-keys",
        help="Comma-separated schedule keys in naturally sorted shot-file order",
    )
    parser.add_argument("--run-dir", type=Path, help="New output directory")
    parser.add_argument("--shots-subdir", default="shots")
    parser.add_argument("--prompt-template", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--n-reference-frames", type=int, default=6)
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--codex-model")
    parser.add_argument("--codex-review-model", help="Ensemble review roles; omitted inherits --codex-model")
    parser.add_argument("--codex-timeout-sec", type=int, default=900)
    parser.add_argument(
        "--entity-detection-mode",
        choices=("single", "ensemble"),
        default="single",
        help=(
            "single keeps the original one-call extractor; ensemble first builds "
            "an all-entity inventory with four isolated detectors and same-shot "
            "adjudication, then independently projects prompt-unbound clusters"
        ),
    )
    parser.add_argument(
        "--ensemble-max-workers",
        type=int,
        default=4,
        help="Maximum concurrent detector calls; the detector panel remains fixed at four",
    )
    parser.add_argument("--ensemble-shuffle-seed", type=int, default=1729)
    parser.add_argument(
        "--ensemble-detector-closure-max-rounds", type=int, choices=range(5), default=3
    )
    parser.add_argument(
        "--ensemble-generic-identity-support-scope",
        choices=("nonmajority", "all_support"), default="all_support",
    )
    parser.add_argument(
        "--ensemble-identity-review-policy",
        choices=("legacy", "physical_v0.6"), default="legacy",
    )
    parser.add_argument(
        "--ensemble-scope-retention-policy",
        choices=("disabled", "single_survivor_scope_retention_v0.1"), default="disabled",
    )
    parser.add_argument(
        "--ensemble-skill-dir",
        type=Path,
        default=DEFAULT_SKILL_DIR,
        help="Repository-local ensemble-shot-entity-detection skill directory",
    )
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--box-threshold", type=float, default=0.25)
    parser.add_argument("--text-threshold", type=float, default=0.20)
    parser.add_argument("--max-query-attributes", type=int, default=3)
    parser.add_argument("--name-match-threshold", type=float, default=0.88)
    parser.add_argument("--box-iou-threshold", type=float, default=0.50)
    parser.add_argument("--combined-threshold", type=float, default=0.60)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    args.experiment_dir = args.experiment_dir.resolve()
    args.schedule_file = (
        args.schedule_file.resolve()
        if args.schedule_file
        else args.experiment_dir / "entity_schedule.json"
    )
    args.prompt_template = args.prompt_template.resolve()
    args.ensemble_skill_dir = args.ensemble_skill_dir.resolve()
    # Keep the original graph builder's interface without changing the v1 script.
    args.semantic_json = None
    args.skip_grounding = False
    if args.n_reference_frames <= 0:
        parser.error("--n-reference-frames must be positive")
    if args.codex_timeout_sec <= 0:
        parser.error("--codex-timeout-sec must be positive")
    if args.max_query_attributes < 0:
        parser.error("--max-query-attributes cannot be negative")
    if not 1 <= args.ensemble_max_workers <= 4:
        parser.error("--ensemble-max-workers must be in [1, 4]")
    try:
        validate_thresholds(
            ("--box-threshold", args.box_threshold),
            ("--text-threshold", args.text_threshold),
            ("--name-match-threshold", args.name_match_threshold),
            ("--box-iou-threshold", args.box_iou_threshold),
            ("--combined-threshold", args.combined_threshold),
        )
    except PromptUnboundError as exc:
        parser.error(str(exc))
    return args


def default_run_dir(experiment_dir: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return experiment_dir / "prompt_unbound_prefilter" / f"run_{timestamp}"


def _format_duration(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def _filtered_semantics(
    semantics: Dict[str, Any], removed_ids: Sequence[str]
) -> Dict[str, Any]:
    result = copy.deepcopy(semantics)
    removed = set(removed_ids)
    result["entities"] = [
        entity for entity in result["entities"] if entity["id"] not in removed
    ]
    retained = {entity["id"] for entity in result["entities"]}
    result["relations"] = [
        relation
        for relation in result["relations"]
        if relation["subject_id"] in retained and relation["object_id"] in retained
    ]
    if removed:
        result["warnings"].append(
            "Deterministic post-check removed prompt-bound leakage from the "
            "prompt-unbound Codex response; consult the separation audit."
        )
    return result


def _build_final_graph(
    args: argparse.Namespace,
    shot: Path,
    sample: shot_graph.VideoSample,
    semantics: Dict[str, Any],
    grounded_entities: Sequence[Dict[str, Any]],
    n_grounding_calls: int,
    grounding_warnings: Sequence[str],
    token_usage: Optional[Dict[str, Optional[int]]],
    prompt_version: str,
) -> Dict[str, Any]:
    graph = shot_graph.build_final_graph(
        video_path=shot,
        video_id=args.experiment_dir.name,
        shot_id=shot.stem,
        sample=sample,
        semantics=semantics,
        grounded_entities=grounded_entities,
        args=args,
        n_grounding_calls=n_grounding_calls,
        grounding_warnings=grounding_warnings,
        codex_token_usage=token_usage,
    )
    graph["extraction_metadata"]["vlm_prompt_version"] = prompt_version
    shot_graph.validate_final_graph(graph)
    return graph


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.codex_review_model is not None and args.entity_detection_mode != "ensemble":
        raise ValueError("--codex-review-model requires --entity-detection-mode ensemble")
    if args.ensemble_scope_retention_policy != "disabled" and (
        args.entity_detection_mode != "ensemble" or args.ensemble_identity_review_policy != "physical_v0.6"
    ):
        raise ValueError("scope retention requires ensemble physical_v0.6")
    model_routing = resolve_model_routing(args.codex_model, args.codex_review_model)
    shots = episode_graphs.discover_shots(args.experiment_dir / args.shots_subdir)
    schedule, descriptions = load_schedule_bundle(args.schedule_file)
    shot_map = map_shots_to_schedule(shots, schedule, parse_shot_keys(args.shot_keys))
    run_dir = (
        args.run_dir.resolve() if args.run_dir else default_run_dir(args.experiment_dir)
    )
    invoked = [sys.executable, str(Path(__file__).resolve()), *(argv or sys.argv[1:])]
    recorder: Optional[RunRecorder] = None
    usages: List[Optional[Dict[str, Optional[int]]]] = []
    try:
        recorder = RunRecorder(run_dir, "prompt_unbound_prefilter_v2", invoked)
        recorder.manifest.update(
            {
                "experiment_dir": str(args.experiment_dir),
                "schedule_file": str(args.schedule_file),
                "prompt_template": str(args.prompt_template),
                "prompt_version": (
                    PROMPT_VERSION
                    if args.entity_detection_mode == "single"
                    else ENSEMBLE_PROTOCOL_VERSION
                ),
                "entity_detection_mode": args.entity_detection_mode,
                **({"scope_retention_policy": args.ensemble_scope_retention_policy}
                   if args.ensemble_scope_retention_policy != "disabled" else {}),
                **({"review_model": args.codex_review_model} if args.codex_review_model is not None else {}),
                **({"model_routing": model_routing} if model_routing is not None else {}),
                "ensemble_skill_dir": (
                    str(args.ensemble_skill_dir)
                    if args.entity_detection_mode == "ensemble"
                    else None
                ),
                "ensemble_max_workers": (
                    args.ensemble_max_workers
                    if args.entity_detection_mode == "ensemble"
                    else None
                ),
                "ensemble_shuffle_seed": (
                    args.ensemble_shuffle_seed
                    if args.entity_detection_mode == "ensemble"
                    else None
                ),
                "shot_schedule_map": [
                    {"shot": shot.name, "schedule_key": key} for shot, key in shot_map
                ],
            }
        )
        recorder.flush_manifest()

        frame_root = run_dir / "reference_frames"
        bound_dir = run_dir / "prompt_bound_detections"
        prompt_dir = run_dir / "codex_prompts"
        raw_dir = run_dir / "codex_raw_semantics"
        ensemble_root = run_dir / "ensemble_detection"
        audit_dir = run_dir / "separation_audits"
        total_graph_dir = run_dir / "total_entity_graphs"
        bound_graph_dir = run_dir / "prompt_bound_entity_graphs"
        unbound_graph_dir = run_dir / "prompt_unbound_entity_graphs"
        total_grounding_root = run_dir / "total_entity_grounding_results"
        bound_grounding_root = run_dir / "prompt_bound_entity_grounding_results"
        unbound_grounding_root = run_dir / "prompt_unbound_entity_grounding_results"
        sampling_total = bound_total = codex_total = unbound_grounding_total = (
            filter_total
        ) = 0.0
        artifact_total = 0.0
        completed_shot_seconds: List[float] = []
        total_shots = len(shot_map)
        print(
            f"[pipeline] {total_shots} shots; mode={args.entity_detection_mode}; "
            f"output={run_dir}",
            flush=True,
        )

        for shot_index, (shot, schedule_key) in enumerate(shot_map, start=1):
            shot_started = time.perf_counter()
            progress = f"[{shot_index}/{total_shots} {shot.name}]"
            print(f"{progress} starting", flush=True)
            frame_dir = frame_root / shot.stem
            stage_started = time.perf_counter()
            sample = shot_graph.extract_reference_frames(
                shot, args.n_reference_frames, frame_dir
            )
            sampling_seconds = time.perf_counter() - stage_started
            sampling_total += sampling_seconds
            print(
                f"{progress} sampled {len(sample.reference_frame_ids)} frames; "
                "prompt-bound grounding...",
                flush=True,
            )

            targets = targets_for_shot(schedule[schedule_key], descriptions)
            stage_started = time.perf_counter()
            prompt_entities, n_bound_calls, bound_warnings = (
                ground_prompt_bound_targets(
                    targets,
                    sample,
                    device=args.device,
                    box_threshold=args.box_threshold,
                    text_threshold=args.text_threshold,
                )
            )
            bound_seconds = time.perf_counter() - stage_started
            bound_total += bound_seconds
            print(
                f"{progress} prompt-bound grounding done: {len(prompt_entities)} "
                f"entities, {n_bound_calls} calls ({_format_duration(bound_seconds)}); "
                "prompt-unbound detection...",
                flush=True,
            )
            bound_path = bound_dir / f"{shot.stem}.prompt_bound.json"
            atomic_write_json(
                bound_path,
                {
                    "shot": shot.name,
                    "schedule_key": schedule_key,
                    "selector": "entitybench_clip_quality_v1_per_frame",
                    "n_grounding_calls": n_bound_calls,
                    "warnings": bound_warnings,
                    "entities": prompt_entities,
                },
            )

            stage_started = time.perf_counter()
            ensemble_audit_path: Optional[Path] = None
            detector_invocations = 1
            adjudicator_invocations = 0
            verifier_invocations = 0
            matcher_invocations = 0
            granularity_invocations = 0
            grounding_frame_ids_by_entity = None
            if args.entity_detection_mode == "single":
                prompt = build_prompt_unbound_codex_prompt(
                    sample, prompt_entities, args.prompt_template
                )
                prompt_path = prompt_dir / f"{shot.stem}.prompt.txt"
                atomic_write_text(prompt_path, prompt)
                codex_result = run_codex_with_prompt(
                    sample,
                    prompt,
                    codex_bin=args.codex_bin,
                    model=args.codex_model,
                    timeout_sec=args.codex_timeout_sec,
                    work_dir=frame_dir,
                    verbose=args.verbose,
                )
                raw_semantics = codex_result.semantics
                token_usage = codex_result.token_usage
                prompt_version = PROMPT_VERSION
            else:
                ensemble_result = run_ensemble_detection(
                    sample=sample,
                    shot_id=shot.stem,
                    prompt_entities=prompt_entities,
                    run_dir=ensemble_root / shot.stem,
                    codex_bin=args.codex_bin,
                    model=args.codex_model,
                    **({"review_model": args.codex_review_model} if args.codex_review_model is not None else {}),
                    timeout_sec=args.codex_timeout_sec,
                    max_workers=args.ensemble_max_workers,
                    shuffle_seed=args.ensemble_shuffle_seed,
                    skill_dir=args.ensemble_skill_dir,
                    detector_closure_max_rounds=args.ensemble_detector_closure_max_rounds,
                    generic_identity_support_scope=args.ensemble_generic_identity_support_scope,
                    identity_review_policy=args.ensemble_identity_review_policy,
                    **({"scope_retention_policy": args.ensemble_scope_retention_policy}
                       if args.ensemble_scope_retention_policy != "disabled" else {}),
                    verbose=args.verbose,
                )
                raw_semantics = ensemble_result.semantics
                token_usage = ensemble_result.token_usage
                prompt_path = ensemble_result.run_dir / "prompts"
                ensemble_audit_path = ensemble_result.audit_path
                detector_invocations = ensemble_result.detector_invocations
                adjudicator_invocations = ensemble_result.adjudicator_invocations
                verifier_invocations = ensemble_result.verifier_invocations
                matcher_invocations = ensemble_result.matcher_invocations
                granularity_invocations = ensemble_result.granularity_invocations
                grounding_frame_ids_by_entity = (
                    ensemble_result.grounding_frame_ids_by_entity
                )
                prompt_version = ENSEMBLE_PROTOCOL_VERSION
            codex_seconds = time.perf_counter() - stage_started
            codex_total += codex_seconds
            usages.append(token_usage)
            print(
                f"{progress} prompt-unbound detection done: "
                f"{len(raw_semantics.get('entities', []))} candidates "
                f"({_format_duration(codex_seconds)}); grounding...",
                flush=True,
            )
            atomic_write_json(
                raw_dir / f"{shot.stem}.codex_raw_semantics.json",
                raw_semantics,
            )
            semantics = shot_graph.normalize_and_validate_semantics(
                raw_semantics, sample
            )

            stage_started = time.perf_counter()
            grounded_entities, n_unbound_calls, unbound_warnings = (
                shot_graph.ground_entities(
                    semantics["entities"],
                    sample,
                    device=args.device,
                    box_threshold=args.box_threshold,
                    text_threshold=args.text_threshold,
                    max_query_attributes=args.max_query_attributes,
                    grounding_frame_ids_by_entity=grounding_frame_ids_by_entity,
                )
            )
            unbound_grounding_seconds = time.perf_counter() - stage_started
            unbound_grounding_total += unbound_grounding_seconds

            stage_started = time.perf_counter()
            protected_unbound_ids: Sequence[str] = ()
            if ensemble_audit_path is not None:
                protected_unbound_ids = strong_ensemble_unbound_entity_ids(
                    read_json(ensemble_audit_path)
                )
            classification = classify_graph_entities(
                grounded_entities,
                prompt_entities,
                name_match_threshold=args.name_match_threshold,
                box_iou_threshold=args.box_iou_threshold,
                combined_threshold=args.combined_threshold,
                protected_unbound_entity_ids=protected_unbound_ids,
            )
            removed_ids = classification["prompt_bound_graph_entity_ids"]
            clean_semantics = _filtered_semantics(semantics, removed_ids)
            retained_ids = {entity["id"] for entity in clean_semantics["entities"]}
            clean_grounded = [
                entity for entity in grounded_entities if entity["id"] in retained_ids
            ]
            unbound_graph = _build_final_graph(
                args,
                shot,
                sample,
                clean_semantics,
                clean_grounded,
                n_unbound_calls,
                unbound_warnings,
                token_usage,
                prompt_version,
            )
            prompt_bound_graph = build_prompt_bound_graph(
                prompt_entities,
                unbound_graph,
                sample,
                n_grounding_calls=n_bound_calls,
            )
            total_graph = merge_prompt_bound_and_unbound_graphs(
                prompt_bound_graph, unbound_graph
            )
            total_graph_path = total_graph_dir / f"{shot.stem}.total.entity_graph.json"
            bound_graph_path = (
                bound_graph_dir / f"{shot.stem}.prompt_bound.entity_graph.json"
            )
            unbound_graph_path = (
                unbound_graph_dir / f"{shot.stem}.prompt_unbound.entity_graph.json"
            )
            atomic_write_json(total_graph_path, total_graph)
            atomic_write_json(bound_graph_path, prompt_bound_graph)
            atomic_write_json(unbound_graph_path, unbound_graph)
            audit_path = audit_dir / f"{shot.stem}.separation.json"
            atomic_write_json(
                audit_path,
                {
                    "pipeline": (
                        "all_entity_inventory_then_prompt_bound_projection"
                        if args.entity_detection_mode == "ensemble"
                        else "prompt_bound_grounding_then_codex_exclusion"
                    ),
                    "entity_detection_mode": args.entity_detection_mode,
                    "shot": shot.name,
                    "schedule_key": schedule_key,
                    "codex_prompt": str(prompt_path),
                    "ensemble_audit": (
                        str(ensemble_audit_path)
                        if ensemble_audit_path is not None
                        else None
                    ),
                    "prompt_bound_detections": str(bound_path),
                    "codex_emitted_entity_ids": [
                        entity["id"] for entity in grounded_entities
                    ],
                    "postcheck_removed_prompt_bound_leakage_ids": removed_ids,
                    "total_entity_graph": str(total_graph_path),
                    "prompt_bound_entity_graph": str(bound_graph_path),
                    "prompt_unbound_entity_graph": str(unbound_graph_path),
                    **classification,
                },
            )
            filter_seconds = time.perf_counter() - stage_started
            filter_total += filter_seconds

            stage_started = time.perf_counter()
            total_grounding = render_grounding_artifacts(
                total_graph_path,
                frame_dir,
                total_grounding_root / shot.stem,
            )
            bound_grounding = render_grounding_artifacts(
                bound_graph_path,
                frame_dir,
                bound_grounding_root / shot.stem,
            )
            unbound_grounding = render_grounding_artifacts(
                unbound_graph_path,
                frame_dir,
                unbound_grounding_root / shot.stem,
            )
            artifact_seconds = time.perf_counter() - stage_started
            artifact_total += artifact_seconds
            shot_seconds = time.perf_counter() - shot_started
            completed_shot_seconds.append(shot_seconds)
            remaining_shots = total_shots - shot_index
            remaining_eta = (
                sum(completed_shot_seconds) / len(completed_shot_seconds)
            ) * remaining_shots

            recorder.add_shot(
                {
                    "shot": shot.name,
                    "schedule_key": schedule_key,
                    "runtime_seconds": round(shot_seconds, 6),
                    "sampling_runtime_seconds": round(sampling_seconds, 6),
                    "prompt_bound_grounding_runtime_seconds": round(bound_seconds, 6),
                    "codex_runtime_seconds": round(codex_seconds, 6),
                    "prompt_unbound_grounding_runtime_seconds": round(
                        unbound_grounding_seconds, 6
                    ),
                    "postcheck_runtime_seconds": round(filter_seconds, 6),
                    "artifact_rendering_runtime_seconds": round(artifact_seconds, 6),
                    "codex_token_usage": token_usage,
                    "codex_detector_invocations": detector_invocations,
                    "codex_adjudicator_invocations": adjudicator_invocations,
                    "codex_verifier_invocations": verifier_invocations,
                    "codex_matcher_invocations": matcher_invocations,
                    "codex_granularity_invocations": granularity_invocations,
                    "entity_detection_mode": args.entity_detection_mode,
                    "n_prompt_bound_grounding_calls": n_bound_calls,
                    "n_prompt_unbound_grounding_calls": n_unbound_calls,
                    "n_codex_emitted_entities": len(grounded_entities),
                    "n_postcheck_removed_entities": len(removed_ids),
                    "n_prompt_bound_graph_entities": len(
                        prompt_bound_graph["entities"]
                    ),
                    "n_final_prompt_unbound_entities": len(unbound_graph["entities"]),
                    "n_total_graph_entities": len(total_graph["entities"]),
                    "prompt_bound_detections": str(bound_path),
                    "codex_prompt": str(prompt_path),
                    "separation_audit": str(audit_path),
                    "total_entity_graph": str(total_graph_path),
                    "prompt_bound_entity_graph": str(bound_graph_path),
                    "prompt_unbound_graph": str(unbound_graph_path),
                    "total_entity_grounding": total_grounding,
                    "prompt_bound_entity_grounding": bound_grounding,
                    "prompt_unbound_entity_grounding": unbound_grounding,
                }
            )
            print(
                f"{progress} complete: {len(unbound_graph['entities'])} prompt-unbound "
                f"entities; removed {len(removed_ids)}; elapsed={_format_duration(shot_seconds)}; "
                f"remaining ETA≈{_format_duration(remaining_eta)}",
                flush=True,
            )

        recorder.add_stage("reference_frame_sampling", sampling_total)
        recorder.add_stage("prompt_bound_grounding", bound_total)
        recorder.add_stage(
            "codex_prompt_unbound_semantics",
            codex_total,
            entity_detection_mode=args.entity_detection_mode,
        )
        recorder.add_stage("prompt_unbound_grounding", unbound_grounding_total)
        recorder.add_stage("deterministic_leakage_postcheck", filter_total)
        recorder.add_stage("graph_packaging_and_grounding_rendering", artifact_total)
        totals = aggregate_token_usage(usages)
        recorder.finish("success", token_usage=totals)
        print(f"Pre-filter pipeline complete: {run_dir}", flush=True)
        return 0
    except EnsembleIncompleteError as exc:
        if recorder is not None:
            recorder.finish(
                "incomplete",
                token_usage=aggregate_token_usage(usages),
                error=str(exc),
            )
        print(f"incomplete: {exc}", file=sys.stderr)
        return 2
    except (
        EnsembleError,
        PromptUnboundError,
        shot_graph.GraphExtractionError,
        OSError,
    ) as exc:
        if recorder is not None:
            recorder.finish(
                "failed", token_usage=aggregate_token_usage(usages), error=str(exc)
            )
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
