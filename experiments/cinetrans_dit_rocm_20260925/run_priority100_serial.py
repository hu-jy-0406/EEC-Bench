#!/usr/bin/env python3
"""Run priority-ordered CineTrans episodes sequentially on one guarded GPU.

The runner checks the existing Slurm allocation before each episode, invokes
the workspace GPU guard for every launch, validates each finished MP4, and
stops early when the remaining allocation is too short for the next episode.
"""

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[3]
EXP = ROOT / "EECBench/experiments/cinetrans_dit_rocm_20260925"
RUN = EXP / "run_priority100"
UPSTREAM = EXP / "upstream"
MANIFEST = RUN / "selected_priority100.jsonl"
GUARD = ROOT / "EECBench/scripts/guard_geocalib_boxer_gpu.py"
DEFAULT_GPU_UUID = "GPU-d79d4a081e34548d"


def remaining_seconds(job_id: str) -> int | None:
    result = subprocess.run(
        ["squeue", "-h", "-j", job_id, "-o", "%L"],
        check=True, capture_output=True, text=True,
    )
    value = result.stdout.strip()
    if not value or value in {"NOT_SET", "UNLIMITED"}:
        return None
    days = 0
    if "-" in value:
        day_part, value = value.split("-", 1)
        days = int(day_part)
    parts = [int(part) for part in value.split(":")]
    if len(parts) == 3:
        hours, minutes, seconds = parts
    elif len(parts) == 2:
        hours, minutes, seconds = 0, *parts
    else:
        raise ValueError(f"unrecognized squeue time-left value: {value!r}")
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def valid_video(path: Path, expected_frames: int) -> tuple[bool, str]:
    if not path.is_file() or path.stat().st_size == 0:
        return False, "missing_or_empty"
    try:
        # Compute nodes lack the system ffprobe binary; use the ffmpeg binary
        # already bundled with imageio_ffmpeg in the generation environment.
        import imageio_ffmpeg
        reader = imageio_ffmpeg.read_frames(str(path), pix_fmt="rgb24")
        metadata = next(reader)
        reader.close()
        reported_frames = round(float(metadata["duration"]) * float(metadata["fps"]))
        if reported_frames != expected_frames:
            return False, f"duration_fps_frames_{reported_frames}_expected_{expected_frames}"
        return True, json.dumps(metadata, sort_keys=True)
    except Exception as exc:  # noqa: BLE001 - retain precise validation reason
        return False, f"ffprobe_{type(exc).__name__}:{exc}"


def write_event(path: Path, event: dict) -> None:
    event["utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        stream.flush()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", default=os.environ.get("SLURM_JOB_ID", "214135"))
    parser.add_argument("--start-priority", type=int, default=1)
    parser.add_argument("--end-priority", type=int, default=100)
    parser.add_argument("--worker-count", type=int, default=1)
    parser.add_argument("--worker-index", type=int, default=0,
                        help="zero-based disjoint priority stride assigned to this worker")
    parser.add_argument("--gpu-index", type=int, default=0,
                        help="rocm-smi physical index on the full node")
    parser.add_argument("--gpu-uuid", default=DEFAULT_GPU_UUID)
    parser.add_argument("--run-id", default=None,
                        help="unique event/log/cache namespace for resumed campaigns")
    parser.add_argument("--skip-priority", type=int, action="append", default=[],
                        help="priority already owned by another live worker; may be repeated")
    parser.add_argument("--reserve-seconds", type=int, default=900)
    parser.add_argument("--seconds-per-shot", type=int, default=840,
                        help="conservative admission estimate from the completed 4-shot pilot")
    parser.add_argument("--fixed-margin-seconds", type=int, default=600,
                        help="per-episode model load/decode/encode safety margin")
    args = parser.parse_args()
    if args.worker_count < 1 or not 0 <= args.worker_index < args.worker_count:
        parser.error("worker index must be in [0, worker-count)")

    run_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.run_id or "")
    if args.run_id and not run_id:
        parser.error("run-id must contain at least one safe filename character")
    if run_id:
        worker_label = f"{run_id}_worker{args.worker_index:02d}"
        events_path = RUN / f"{run_id}_worker{args.worker_index:02d}_events.jsonl"
        log_suffix = worker_label
    elif args.worker_count == 1:
        events_path = RUN / "serial_batch_events.jsonl"
        log_suffix = "serial"
    else:
        events_path = RUN / f"serial_batch_worker{args.worker_index:02d}_events.jsonl"
        log_suffix = f"worker{args.worker_index:02d}"
    summaries = [json.loads(line) for line in MANIFEST.read_text(encoding="utf-8").splitlines() if line]
    env = os.environ.copy()
    env.update({
        "OMP_NUM_THREADS": "4",
        "MKL_NUM_THREADS": "4",
        "OPENBLAS_NUM_THREADS": "1",
        "TOKENIZERS_PARALLELISM": "false",
        "PYTHONUNBUFFERED": "1",
        "MPLCONFIGDIR": "/tmp/cinetrans-mpl",
        "PYTORCH_HIP_ALLOC_CONF": "expandable_segments:True",
    })
    # MIOpen's default /tmp find database is shared by concurrent jobs on a
    # node and can fail with readonly SQLite errors during VAE decode. Give
    # each dedicated GPU worker writable, isolated databases and caches.
    gpu_key = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.gpu_uuid.removeprefix("GPU-"))
    cache_root = Path("/tmp") / "eecbench-cinetrans-miopen" / str(args.job_id) / \
        (run_id or "default") / socket.gethostname() / gpu_key
    for key, subdir in (("MIOPEN_USER_DB_PATH", "user-db"),
                        ("MIOPEN_CUSTOM_CACHE_DIR", "cache"),
                        ("MPLCONFIGDIR", "matplotlib")):
        cache_path = cache_root / subdir
        cache_path.mkdir(parents=True, exist_ok=True)
        env[key] = str(cache_path)
    env.pop("HIP_VISIBLE_DEVICES", None)
    env.pop("CUDA_VISIBLE_DEVICES", None)

    for priority, row in enumerate(summaries, start=1):
        if priority < args.start_priority or priority > args.end_priority:
            continue
        if (priority - args.start_priority) % args.worker_count != args.worker_index:
            continue
        if priority in args.skip_priority:
            write_event(events_path, {
                "priority": priority, "episode_id": row["episode_id"],
                "status": "skipped_live_worker_owned",
            })
            continue
        config_path = RUN / "configs" / f"priority_{priority:03d}.yaml"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        output = Path(config["save_file"])
        episode_id = row["episode_id"]
        shots = int(row["shot_count"])
        expected = int(config["frame_num"])

        is_valid, detail = valid_video(output, expected)
        if is_valid:
            write_event(events_path, {
                "priority": priority, "episode_id": episode_id,
                "shot_count": shots, "status": "already_valid_skip",
                "output": str(output), "validation": detail,
            })
            continue

        left = remaining_seconds(args.job_id)
        estimated_needed = shots * args.seconds_per_shot + args.fixed_margin_seconds
        if left is not None and left < estimated_needed + args.reserve_seconds:
            write_event(events_path, {
                "priority": priority, "episode_id": episode_id,
                "shot_count": shots, "status": "stopped_time_guard",
                "seconds_left": left, "estimated_episode_seconds": estimated_needed,
                "reserve_seconds": args.reserve_seconds,
            })
            print(f"STOP priority={priority:03d}: {left}s left, "
                  f"need about {estimated_needed + args.reserve_seconds}s", flush=True)
            break

        archived_output = None
        if output.exists():
            archived = output.with_name(
                f"{output.name}.invalid_{run_id or log_suffix}_{time.time_ns()}"
            )
            os.replace(output, archived)
            archived_output = str(archived)

        log_path = RUN / "logs" / f"priority_{priority:03d}_{log_suffix}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        write_event(events_path, {
            "priority": priority, "episode_id": episode_id,
            "shot_count": shots, "status": "launching",
            "seconds_left_before_launch": left,
            "estimated_episode_seconds": estimated_needed,
            "archived_invalid_output": archived_output,
            "config": str(config_path), "log": str(log_path),
        })
        command = [
            sys.executable, str(GUARD), str(args.gpu_index), args.gpu_uuid, sys.executable,
            str(UPSTREAM / "generate.py"),
            "--config", str(Path("..") / "run_priority100" / "configs" /
                             f"priority_{priority:03d}.yaml"),
        ]
        with log_path.open("w", encoding="utf-8") as log_stream:
            result = subprocess.run(
                command, cwd=UPSTREAM, env=env, stdout=log_stream,
                stderr=subprocess.STDOUT, check=False,
            )
        elapsed = time.monotonic() - started
        is_valid, detail = valid_video(output, expected)
        status = "completed" if result.returncode == 0 and is_valid else "failed"
        write_event(events_path, {
            "priority": priority, "episode_id": episode_id,
            "shot_count": shots, "status": status,
            "returncode": result.returncode,
            "wall_seconds": round(elapsed, 3),
            "output": str(output), "output_bytes": output.stat().st_size if output.exists() else 0,
            "validation": detail,
            "log": str(log_path),
        })
        print(f"{status.upper()} priority={priority:03d} shots={shots} "
              f"wall={elapsed:.1f}s output={output}", flush=True)
        if status != "completed":
            print(f"STOP after failed episode; inspect {log_path}", flush=True)
            return result.returncode or 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
