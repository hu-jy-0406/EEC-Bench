#!/usr/bin/env python3
"""Pipeline 1: extract a full graph, then remove scheduled prompt-bound entities."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from prompt_unbound_common import (
    PromptUnboundError,
    RunRecorder,
    aggregate_token_usage,
    atomic_write_json,
    atomic_write_text,
    build_prompt_bound_graph,
    classify_graph_entities,
    episode_graphs,
    filter_graph_to_unbound,
    graph_token_usage,
    ground_prompt_bound_targets,
    load_sample_from_graph,
    load_schedule_bundle,
    map_shots_to_schedule,
    parse_shot_keys,
    read_json,
    render_grounding_artifacts,
    shot_graph,
    targets_for_shot,
    validate_thresholds,
)


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
V1_EPISODE_EXTRACTOR = SCRIPT_DIR / "extract_episode_entity_graphs.py"


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the original full-graph extractor, independently ground the "
            "entity schedule with EntityBench's detector/selector, and emit an "
            "auditable prompt-unbound-only graph for every shot."
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
    parser.add_argument(
        "--reuse-graphs-dir",
        type=Path,
        help="Reuse full v1 graphs instead of running v1 (requires --reuse-reference-frames-dir)",
    )
    parser.add_argument("--reuse-reference-frames-dir", type=Path)
    parser.add_argument("--n-reference-frames", type=int, default=6)
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--codex-model")
    parser.add_argument("--codex-timeout-sec", type=int, default=900)
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
    if (args.reuse_graphs_dir is None) != (args.reuse_reference_frames_dir is None):
        parser.error(
            "--reuse-graphs-dir and --reuse-reference-frames-dir must be supplied together"
        )
    if args.n_reference_frames <= 0:
        parser.error("--n-reference-frames must be positive")
    if args.codex_timeout_sec <= 0:
        parser.error("--codex-timeout-sec must be positive")
    if args.max_query_attributes < 0:
        parser.error("--max-query-attributes cannot be negative")
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
    return experiment_dir / "prompt_unbound_posthoc" / f"run_{timestamp}"


def _run_v1(args: argparse.Namespace, run_dir: Path, recorder: RunRecorder) -> tuple[Path, Path]:
    graph_dir = run_dir / "full_entity_graphs"
    frames_dir = run_dir / "reference_frames"
    grounding_dir = run_dir / "full_graph_grounding_results"
    logs_dir = run_dir / "v1_logs"
    command = [
        sys.executable,
        str(V1_EPISODE_EXTRACTOR),
        str(args.experiment_dir),
        "--shots-subdir",
        args.shots_subdir,
        "--graphs-subdir",
        str(graph_dir),
        "--reference-frames-subdir",
        str(frames_dir),
        "--grounding-results-subdir",
        str(grounding_dir),
        "--logs-subdir",
        str(logs_dir),
        "--n-reference-frames",
        str(args.n_reference_frames),
        "--codex-bin",
        args.codex_bin,
        "--codex-timeout-sec",
        str(args.codex_timeout_sec),
        "--device",
        args.device,
        "--box-threshold",
        str(args.box_threshold),
        "--text-threshold",
        str(args.text_threshold),
        "--max-query-attributes",
        str(args.max_query_attributes),
    ]
    if args.codex_model:
        command.extend(["--codex-model", args.codex_model])
    if args.verbose:
        command.append("--verbose")
    recorder.write("v1_command: " + " ".join(json.dumps(part) for part in command))
    started = time.perf_counter()
    result = subprocess.run(command, cwd=str(PROJECT_ROOT), check=False)
    runtime = time.perf_counter() - started
    recorder.add_stage("v1_full_graph_extraction", runtime, returncode=result.returncode)
    if result.returncode != 0:
        raise PromptUnboundError(
            f"Original episode extractor failed with exit code {result.returncode}; "
            f"see {logs_dir}"
        )
    return graph_dir, frames_dir


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    shots = episode_graphs.discover_shots(args.experiment_dir / args.shots_subdir)
    schedule, descriptions = load_schedule_bundle(args.schedule_file)
    shot_map = map_shots_to_schedule(shots, schedule, parse_shot_keys(args.shot_keys))
    run_dir = (args.run_dir.resolve() if args.run_dir else default_run_dir(args.experiment_dir))
    invoked = [sys.executable, str(Path(__file__).resolve()), *(argv or sys.argv[1:])]
    recorder: Optional[RunRecorder] = None
    usages: List[Optional[Dict[str, Optional[int]]]] = []
    try:
        recorder = RunRecorder(run_dir, "prompt_unbound_posthoc_v2", invoked)
        recorder.manifest.update(
            {
                "experiment_dir": str(args.experiment_dir),
                "schedule_file": str(args.schedule_file),
                "shot_schedule_map": [
                    {"shot": shot.name, "schedule_key": key} for shot, key in shot_map
                ],
            }
        )
        recorder.flush_manifest()

        if args.reuse_graphs_dir:
            graph_dir = args.reuse_graphs_dir.resolve()
            frames_dir = args.reuse_reference_frames_dir.resolve()
            recorder.add_stage(
                "v1_full_graph_extraction",
                0.0,
                reused=True,
                graphs_dir=str(graph_dir),
                reference_frames_dir=str(frames_dir),
            )
        else:
            graph_dir, frames_dir = _run_v1(args, run_dir, recorder)

        bound_detection_dir = run_dir / "prompt_bound_detections"
        audit_dir = run_dir / "separation_audits"
        prompt_dir = run_dir / "codex_prompts"
        total_graph_dir = run_dir / "total_entity_graphs"
        bound_graph_dir = run_dir / "prompt_bound_entity_graphs"
        unbound_graph_dir = run_dir / "prompt_unbound_entity_graphs"
        total_grounding_root = run_dir / "total_entity_grounding_results"
        bound_grounding_root = run_dir / "prompt_bound_entity_grounding_results"
        unbound_grounding_root = run_dir / "prompt_unbound_entity_grounding_results"
        grounding_total = 0.0
        comparison_total = 0.0
        artifact_total = 0.0

        for shot, schedule_key in shot_map:
            shot_started = time.perf_counter()
            graph_path = graph_dir / f"{shot.stem}.entity_graph.json"
            graph = read_json(graph_path)
            usages.append(graph_token_usage(graph))
            sample = load_sample_from_graph(graph, frames_dir / shot.stem)
            targets = targets_for_shot(schedule[schedule_key], descriptions)
            prompt_path = prompt_dir / f"{shot.stem}.prompt.txt"
            atomic_write_text(prompt_path, shot_graph.build_codex_prompt(sample))

            stage_started = time.perf_counter()
            prompt_entities, n_calls, grounding_warnings = ground_prompt_bound_targets(
                targets,
                sample,
                device=args.device,
                box_threshold=args.box_threshold,
                text_threshold=args.text_threshold,
            )
            grounding_seconds = time.perf_counter() - stage_started
            grounding_total += grounding_seconds
            bound_detection_path = (
                bound_detection_dir / f"{shot.stem}.prompt_bound.json"
            )
            atomic_write_json(
                bound_detection_path,
                {
                    "shot": shot.name,
                    "schedule_key": schedule_key,
                    "selector": "entitybench_clip_quality_v1_per_frame",
                    "n_grounding_calls": n_calls,
                    "warnings": grounding_warnings,
                    "entities": prompt_entities,
                },
            )

            stage_started = time.perf_counter()
            classification = classify_graph_entities(
                graph.get("entities", []),
                prompt_entities,
                name_match_threshold=args.name_match_threshold,
                box_iou_threshold=args.box_iou_threshold,
                combined_threshold=args.combined_threshold,
            )
            audit = {
                "pipeline": "posthoc_full_graph_then_compare",
                "shot": shot.name,
                "schedule_key": schedule_key,
                "full_graph": str(graph_path),
                "codex_prompt": str(prompt_path),
                "prompt_bound_detections": str(bound_detection_path),
                **classification,
            }
            audit_path = audit_dir / f"{shot.stem}.separation.json"
            unbound_graph = filter_graph_to_unbound(
                graph,
                classification["prompt_bound_graph_entity_ids"],
                warning=(
                    "Derived post hoc by removing one-to-one matches to the prompt-bound "
                    "entity schedule; consult the separation audit for thresholds and evidence."
                ),
            )
            prompt_bound_graph = build_prompt_bound_graph(
                prompt_entities,
                graph,
                sample,
                n_grounding_calls=n_calls,
            )
            total_path = total_graph_dir / f"{shot.stem}.total.entity_graph.json"
            bound_graph_path = (
                bound_graph_dir / f"{shot.stem}.prompt_bound.entity_graph.json"
            )
            unbound_path = (
                unbound_graph_dir / f"{shot.stem}.prompt_unbound.entity_graph.json"
            )
            atomic_write_json(total_path, graph)
            atomic_write_json(bound_graph_path, prompt_bound_graph)
            atomic_write_json(unbound_path, unbound_graph)
            audit.update(
                {
                    "total_entity_graph": str(total_path),
                    "prompt_bound_entity_graph": str(bound_graph_path),
                    "prompt_unbound_entity_graph": str(unbound_path),
                }
            )
            atomic_write_json(audit_path, audit)
            comparison_seconds = time.perf_counter() - stage_started
            comparison_total += comparison_seconds

            stage_started = time.perf_counter()
            total_grounding = render_grounding_artifacts(
                total_path,
                frames_dir / shot.stem,
                total_grounding_root / shot.stem,
            )
            bound_grounding = render_grounding_artifacts(
                bound_graph_path,
                frames_dir / shot.stem,
                bound_grounding_root / shot.stem,
            )
            unbound_grounding = render_grounding_artifacts(
                unbound_path,
                frames_dir / shot.stem,
                unbound_grounding_root / shot.stem,
            )
            artifact_seconds = time.perf_counter() - stage_started
            artifact_total += artifact_seconds

            recorder.add_shot(
                {
                    "shot": shot.name,
                    "schedule_key": schedule_key,
                    "runtime_seconds": round(time.perf_counter() - shot_started, 6),
                    "grounding_runtime_seconds": round(grounding_seconds, 6),
                    "comparison_runtime_seconds": round(comparison_seconds, 6),
                    "artifact_rendering_runtime_seconds": round(artifact_seconds, 6),
                    "codex_token_usage": graph_token_usage(graph),
                    "n_prompt_bound_grounding_calls": n_calls,
                    "n_full_graph_entities": len(graph.get("entities", [])),
                    "n_matched_prompt_bound_entities": len(
                        classification["prompt_bound_graph_entity_ids"]
                    ),
                    "n_prompt_unbound_entities": len(unbound_graph["entities"]),
                    "n_prompt_bound_graph_entities": len(prompt_bound_graph["entities"]),
                    "prompt_bound_detections": str(bound_detection_path),
                    "codex_prompt": str(prompt_path),
                    "separation_audit": str(audit_path),
                    "total_entity_graph": str(total_path),
                    "prompt_bound_entity_graph": str(bound_graph_path),
                    "prompt_unbound_graph": str(unbound_path),
                    "total_entity_grounding": total_grounding,
                    "prompt_bound_entity_grounding": bound_grounding,
                    "prompt_unbound_entity_grounding": unbound_grounding,
                }
            )
            print(
                f"[{shot.name}] prompt-unbound: {len(unbound_graph['entities'])}/"
                f"{len(graph.get('entities', []))} entities ({time.perf_counter() - shot_started:.1f}s)",
                flush=True,
            )

        recorder.add_stage("prompt_bound_grounding", grounding_total)
        recorder.add_stage("posthoc_matching_and_filtering", comparison_total)
        recorder.add_stage("graph_packaging_and_grounding_rendering", artifact_total)
        totals = aggregate_token_usage(usages)
        recorder.finish("success", token_usage=totals)
        print(f"Post-hoc pipeline complete: {run_dir}", flush=True)
        return 0
    except (PromptUnboundError, shot_graph.GraphExtractionError, OSError) as exc:
        if recorder is not None:
            recorder.finish("failed", token_usage=aggregate_token_usage(usages), error=str(exc))
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
