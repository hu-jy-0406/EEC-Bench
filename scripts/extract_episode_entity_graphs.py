#!/usr/bin/env python3
"""Extract entity graphs and grounded reference frames for one episode folder."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SHOT_EXTRACTOR = SCRIPT_DIR / "extract_shot_entity_graph.py"

sys.path.insert(0, str(SCRIPT_DIR))
from render_entity_graph_reference_frames import (  # noqa: E402
    RenderError,
    render_reference_sheet,
)


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
TOKEN_KEYS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "total_tokens",
)


class EpisodeExtractionError(RuntimeError):
    """Raised when a strict episode extraction cannot be completed."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def natural_sort_key(path: Path) -> Tuple[Any, ...]:
    parts = re.split(r"(\d+)", path.name.lower())
    return tuple(int(part) if part.isdigit() else part for part in parts)


def discover_shots(shots_dir: Path) -> List[Path]:
    if not shots_dir.is_dir():
        raise EpisodeExtractionError(f"Shot directory does not exist: {shots_dir}")
    shots = sorted(
        (
            path.resolve()
            for path in shots_dir.iterdir()
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
        ),
        key=natural_sort_key,
    )
    if not shots:
        supported = ", ".join(sorted(VIDEO_EXTENSIONS))
        raise EpisodeExtractionError(
            f"No shot videos found in {shots_dir} (supported: {supported})"
        )
    return shots


def read_graph(path: Path) -> Dict[str, Any]:
    try:
        graph = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EpisodeExtractionError(f"Cannot read generated graph {path}: {exc}") from exc
    if not isinstance(graph, dict):
        raise EpisodeExtractionError(f"Generated graph is not an object: {path}")
    return graph


def graph_token_usage(graph: Mapping[str, Any]) -> Optional[Dict[str, Optional[int]]]:
    metadata = graph.get("extraction_metadata")
    if not isinstance(metadata, Mapping):
        return None
    usage = metadata.get("codex_token_usage")
    if not isinstance(usage, Mapping):
        return None
    normalized: Dict[str, Optional[int]] = {}
    for key in TOKEN_KEYS:
        value = usage.get(key)
        normalized[key] = value if isinstance(value, int) and not isinstance(value, bool) else None
    return normalized


def aggregate_token_usage(
    usages: Sequence[Optional[Mapping[str, Optional[int]]]],
) -> Dict[str, Optional[int]]:
    totals: Dict[str, Optional[int]] = {}
    for key in TOKEN_KEYS:
        values = [usage.get(key) if usage is not None else None for usage in usages]
        totals[key] = (
            sum(int(value) for value in values)
            if values and all(isinstance(value, int) and not isinstance(value, bool) for value in values)
            else None
        )
    return totals


def format_token_usage(usage: Optional[Mapping[str, Optional[int]]]) -> str:
    if usage is None:
        return "unavailable"
    return ", ".join(
        f"{key}={usage.get(key) if usage.get(key) is not None else 'unavailable'}"
        for key in TOKEN_KEYS
    )


class RunLog:
    def __init__(self, path: Path, *, overwrite: bool) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "w" if overwrite else "x"
        try:
            self._handle = path.open(mode, encoding="utf-8", buffering=1)
        except FileExistsError as exc:
            raise EpisodeExtractionError(
                f"Log already exists; choose another --log-file or use --overwrite: {path}"
            ) from exc
        self.path = path

    def write(self, line: str = "") -> None:
        self._handle.write(line.rstrip("\n") + "\n")
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()


def prepare_shot_outputs(
    graph_path: Path,
    frame_dir: Path,
    grounding_dir: Path,
    *,
    overwrite: bool,
) -> None:
    existing = [path for path in (graph_path, frame_dir, grounding_dir) if path.exists()]
    if existing and not overwrite:
        joined = ", ".join(str(path) for path in existing)
        raise EpisodeExtractionError(
            f"Output already exists for this shot: {joined}. Use --overwrite to replace it."
        )
    if overwrite:
        if graph_path.is_file():
            graph_path.unlink()
        for directory in (frame_dir, grounding_dir):
            if directory.is_dir():
                shutil.rmtree(directory)
    frame_dir.mkdir(parents=True, exist_ok=False)
    grounding_dir.mkdir(parents=True, exist_ok=False)
    graph_path.parent.mkdir(parents=True, exist_ok=True)


def build_shot_command(
    args: argparse.Namespace,
    shot: Path,
    graph_path: Path,
    frame_dir: Path,
) -> List[str]:
    command = [
        sys.executable,
        str(SHOT_EXTRACTOR),
        str(shot),
        "--output", str(graph_path),
        "--video-id", args.experiment_dir.name,
        "--shot-id", shot.stem,
        "--keep-reference-frames", str(frame_dir),
        "--skip-annotated-video",
        "--n-reference-frames", str(args.n_reference_frames),
        "--codex-bin", args.codex_bin,
        "--codex-timeout-sec", str(args.codex_timeout_sec),
        "--device", args.device,
        "--box-threshold", str(args.box_threshold),
        "--text-threshold", str(args.text_threshold),
        "--max-query-attributes", str(args.max_query_attributes),
    ]
    if args.codex_model:
        command.extend(["--codex-model", args.codex_model])
    if args.skip_grounding:
        command.append("--skip-grounding")
    if args.verbose:
        command.append("--verbose")
    return command


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Process every naturally sorted shot in EXPERIMENT_DIR/shots and save "
            "per-shot graphs, original reference frames, grounded reference frames, "
            "contact sheets, and an episode run log."
        )
    )
    parser.add_argument("experiment_dir", type=Path)
    parser.add_argument("--shots-subdir", default="shots")
    parser.add_argument("--graphs-subdir", default="entity_graphs")
    parser.add_argument("--reference-frames-subdir", default="reference_frames")
    parser.add_argument("--grounding-results-subdir", default="grounding_results")
    parser.add_argument("--logs-subdir", default="logs")
    parser.add_argument("--log-file", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--n-reference-frames", type=int, default=6)
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--codex-model")
    parser.add_argument("--codex-timeout-sec", type=int, default=900)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--box-threshold", type=float, default=0.25)
    parser.add_argument("--text-threshold", type=float, default=0.20)
    parser.add_argument("--max-query-attributes", type=int, default=3)
    parser.add_argument(
        "--skip-grounding",
        action="store_true",
        help="Run semantic extraction only; intended for CPU/schema diagnostics",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    args.experiment_dir = args.experiment_dir.resolve()
    if args.n_reference_frames <= 0:
        parser.error("--n-reference-frames must be positive")
    if args.codex_timeout_sec <= 0:
        parser.error("--codex-timeout-sec must be positive")
    if args.max_query_attributes < 0:
        parser.error("--max-query-attributes cannot be negative")
    for name in ("box_threshold", "text_threshold"):
        value = getattr(args, name)
        if not 0 <= value <= 1:
            parser.error(f"--{name.replace('_', '-')} must be in [0, 1]")
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    started_utc = utc_now()
    started_perf = time.perf_counter()
    timestamp = started_utc.strftime("%Y%m%dT%H%M%SZ")
    logs_dir = args.experiment_dir / args.logs_subdir
    log_path = (
        args.log_file.resolve()
        if args.log_file
        else logs_dir / f"entity_graph_episode_{timestamp}.log"
    )
    invoked_argv = list(argv) if argv is not None else sys.argv[1:]
    run_command = [sys.executable, str(Path(__file__).resolve()), *invoked_argv]

    log: Optional[RunLog] = None
    shot_records: List[Dict[str, Any]] = []
    shot_count = 0
    status = "failed"
    error_message: Optional[str] = None
    try:
        log = RunLog(log_path, overwrite=args.overwrite)
        shots_dir = args.experiment_dir / args.shots_subdir
        shots = discover_shots(shots_dir)
        graph_dir = args.experiment_dir / args.graphs_subdir
        frames_root = args.experiment_dir / args.reference_frames_subdir
        grounding_root = args.experiment_dir / args.grounding_results_subdir
        shot_count = len(shots)

        log.write("EEC-Bench episode entity-graph extraction")
        log.write(f"status: running")
        log.write(f"start_utc: {iso_utc(started_utc)}")
        log.write(f"command: {shlex.join(run_command)}")
        log.write(f"experiment_dir: {args.experiment_dir}")
        log.write(f"shots_dir: {shots_dir}")
        log.write(f"shot_count: {len(shots)}")
        print(
            f"Episode entity graphs: {shot_count} shot(s), device={args.device}",
            flush=True,
        )
        print(f"Run log: {log_path}", flush=True)

        for index, shot in enumerate(shots, start=1):
            graph_path = graph_dir / f"{shot.stem}.entity_graph.json"
            frame_dir = frames_root / shot.stem
            grounding_dir = grounding_root / shot.stem
            contact_sheet = grounding_dir / "contact_sheet.png"
            prepare_shot_outputs(
                graph_path, frame_dir, grounding_dir, overwrite=args.overwrite
            )
            command = build_shot_command(args, shot, graph_path, frame_dir)
            shot_started_utc = utc_now()
            shot_started_perf = time.perf_counter()
            log.write()
            log.write(f"[shot {index}/{len(shots)}] {shot.name}")
            log.write(f"start_utc: {iso_utc(shot_started_utc)}")
            log.write(f"command: {shlex.join(command)}")

            print(
                f"[{index}/{shot_count}] {shot.name}: extracting...",
                flush=True,
            )
            result = subprocess.run(
                command,
                cwd=str(PROJECT_ROOT),
                text=True,
                capture_output=True,
                check=False,
            )
            if result.stdout.strip():
                log.write("stdout:")
                log.write(result.stdout.rstrip())
            if result.stderr.strip():
                log.write("stderr:")
                log.write(result.stderr.rstrip())
            if result.returncode != 0:
                raise EpisodeExtractionError(
                    f"Shot extractor failed for {shot.name} with exit code "
                    f"{result.returncode}; see {log_path}"
                )

            graph = read_graph(graph_path)
            try:
                reference_count, detection_count = render_reference_sheet(
                    graph_path,
                    frame_dir,
                    contact_sheet,
                    annotated_dir=grounding_dir,
                )
            except (OSError, RenderError) as exc:
                raise EpisodeExtractionError(
                    f"Reference grounding rendering failed for {shot.name}: {exc}"
                ) from exc

            runtime = time.perf_counter() - shot_started_perf
            usage = graph_token_usage(graph)
            shot_record = {
                "shot": shot.name,
                "runtime_seconds": runtime,
                "token_usage": usage,
                "graph": str(graph_path),
                "reference_frames": str(frame_dir),
                "grounding_results": str(grounding_dir),
                "reference_frame_count": reference_count,
                "grounding_detection_count": detection_count,
            }
            shot_records.append(shot_record)
            log.write(f"end_utc: {iso_utc(utc_now())}")
            log.write(f"runtime_seconds: {runtime:.6f}")
            log.write(f"codex_token_usage: {format_token_usage(usage)}")
            log.write(f"graph: {graph_path}")
            log.write(f"reference_frames: {frame_dir}")
            log.write(f"grounding_results: {grounding_dir}")
            log.write(f"reference_frame_count: {reference_count}")
            log.write(f"grounding_detection_count: {detection_count}")
            log.write("status: success")
            print(
                f"[{index}/{shot_count}] {shot.name}: done "
                f"({runtime:.1f}s, {detection_count} box(es))",
                flush=True,
            )

        status = "success"
        return 0
    except (EpisodeExtractionError, OSError) as exc:
        error_message = str(exc)
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        total_runtime = time.perf_counter() - started_perf
        if log is not None:
            totals = aggregate_token_usage(
                [record["token_usage"] for record in shot_records]
            )
            log.write()
            log.write("[episode summary]")
            log.write(f"end_utc: {iso_utc(utc_now())}")
            log.write(f"status: {status}")
            log.write(f"completed_shots: {len(shot_records)}")
            log.write(f"total_runtime_seconds: {total_runtime:.6f}")
            log.write(f"total_codex_token_usage: {format_token_usage(totals)}")
            if error_message:
                log.write(f"error: {error_message}")
            log.close()
            if status == "success":
                print(
                    f"Episode complete: {len(shot_records)}/{shot_count} shot(s) "
                    f"in {total_runtime:.1f}s",
                    flush=True,
                )
            else:
                print(f"Run log: {log.path}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
