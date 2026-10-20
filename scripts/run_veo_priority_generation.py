#!/usr/bin/env python3
"""Generate priority-ranked EEC-Bench shots with Veo through the Gemini API.

The runner deliberately uses only the Veo-specific prompt field and keeps a
durable ledger. It never prints API keys and only retries transport/rate-limit
failures before a long-running operation has been accepted.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
MODEL = "veo-3.1-fast-generate-preview"
TRANSIENT_HTTP = {429, 500, 502, 503, 504}
WRITE_LOCK = threading.Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_request(url: str, key: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="GET" if body is None else "POST",
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def download(url: str, key: str, output: Path) -> None:
    request = urllib.request.Request(url, headers={"x-goog-api-key": key})
    temporary = output.with_suffix(output.suffix + ".partial")
    with urllib.request.urlopen(request, timeout=300) as response, temporary.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    temporary.replace(output)


def operation_video_uri(payload: Any) -> str | None:
    if isinstance(payload, dict):
        uri = payload.get("uri")
        if isinstance(uri, str) and uri:
            return uri
        for value in payload.values():
            found = operation_video_uri(value)
            if found:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = operation_video_uri(value)
            if found:
                return found
    return None


def append_event(path: Path, event: dict[str, Any]) -> None:
    with WRITE_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def describe_error(exc: BaseException) -> dict[str, Any]:
    if isinstance(exc, urllib.error.HTTPError):
        try:
            body = exc.read().decode("utf-8", errors="replace")[:2000]
        except Exception:
            body = ""
        return {"type": "http", "code": exc.code, "message": str(exc.reason), "response": body}
    return {"type": type(exc).__name__, "message": str(exc)}


def generate_one(task: dict[str, Any], args: argparse.Namespace, key: str, events: Path) -> dict[str, Any]:
    started = time.monotonic()
    prefix = {"episode_id": task["episode_id"], "shot_id": task["shot_id"], "generation_priority": task["generation_priority"]}
    output = Path(args.output) / "videos" / task["episode_id"] / f"{task['shot_id']}.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.stat().st_size > 0:
        event = {**prefix, "event": "skipped_existing", "at": utc_now(), "path": str(output), "bytes": output.stat().st_size}
        append_event(events, event)
        return {"status": "skipped_existing", **prefix, "elapsed_seconds": 0.0}

    request_body = {
        "instances": [{"prompt": task["prompt"]}],
        "parameters": {
            "aspectRatio": args.aspect_ratio,
            "resolution": args.resolution,
            "durationSeconds": str(args.duration_seconds),
            "sampleCount": 1,
            "personGeneration": "allow_all",
        },
    }
    operation_name: str | None = None
    for attempt in range(1, args.submit_attempts + 1):
        try:
            response = json_request(f"{BASE_URL}/models/{args.model}:predictLongRunning", key, request_body)
            operation_name = response.get("name")
            if not operation_name:
                raise RuntimeError(f"response did not contain operation name: {json.dumps(response)[:400]}")
            append_event(events, {**prefix, "event": "submitted", "at": utc_now(), "attempt": attempt, "operation": operation_name})
            break
        except Exception as exc:  # request has not been accepted, so retry is safe
            detail = describe_error(exc)
            retryable = detail.get("code") in TRANSIENT_HTTP or detail["type"] in {"TimeoutError", "URLError"}
            append_event(events, {**prefix, "event": "submit_error", "at": utc_now(), "attempt": attempt, "error": detail, "retryable": retryable})
            if not retryable or attempt == args.submit_attempts:
                return {"status": "submit_error", **prefix, "elapsed_seconds": time.monotonic() - started, "error": detail}
            time.sleep(min(args.retry_cap_seconds, (2 ** (attempt - 1)) + random.random()))

    assert operation_name is not None
    deadline = time.monotonic() + args.operation_timeout_seconds
    while time.monotonic() < deadline:
        try:
            status = json_request(f"{BASE_URL}/{operation_name}", key)
        except Exception as exc:
            detail = describe_error(exc)
            append_event(events, {**prefix, "event": "poll_error", "at": utc_now(), "operation": operation_name, "error": detail})
            time.sleep(args.poll_seconds)
            continue
        if not status.get("done"):
            time.sleep(args.poll_seconds)
            continue
        if "error" in status:
            event = {**prefix, "event": "operation_error", "at": utc_now(), "operation": operation_name, "error": status["error"]}
            append_event(events, event)
            return {"status": "operation_error", **prefix, "elapsed_seconds": time.monotonic() - started, "error": status["error"]}
        uri = operation_video_uri(status.get("response", {}))
        if not uri:
            detail = {"type": "missing_video_uri", "message": json.dumps(status)[:1000]}
            append_event(events, {**prefix, "event": "operation_error", "at": utc_now(), "operation": operation_name, "error": detail})
            return {"status": "operation_error", **prefix, "elapsed_seconds": time.monotonic() - started, "error": detail}
        try:
            download(uri, key, output)
        except Exception as exc:
            detail = describe_error(exc)
            append_event(events, {**prefix, "event": "download_error", "at": utc_now(), "operation": operation_name, "error": detail})
            return {"status": "download_error", **prefix, "elapsed_seconds": time.monotonic() - started, "error": detail}
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        result = {"status": "success", **prefix, "at": utc_now(), "operation": operation_name, "path": str(output), "bytes": output.stat().st_size, "sha256": digest, "elapsed_seconds": time.monotonic() - started}
        append_event(events, {**result, "event": "success"})
        return result
    detail = {"type": "operation_timeout", "message": f"exceeded {args.operation_timeout_seconds} seconds"}
    append_event(events, {**prefix, "event": "operation_timeout", "at": utc_now(), "operation": operation_name, "error": detail})
    return {"status": "operation_timeout", **prefix, "elapsed_seconds": time.monotonic() - started, "error": detail}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--priority-csv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--duration-seconds", type=int, default=6, choices=(4, 6, 8))
    parser.add_argument("--resolution", default="720p", choices=("720p",))
    parser.add_argument("--aspect-ratio", default="16:9", choices=("16:9", "9:16"))
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--operation-timeout-seconds", type=int, default=1800)
    parser.add_argument("--submit-attempts", type=int, default=4)
    parser.add_argument("--retry-cap-seconds", type=int, default=60)
    args = parser.parse_args()
    if args.workers < 1:
        raise ValueError("--workers must be positive")
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is unset; invoke through scripts/gemini_env.sh")

    priorities: dict[str, int] = {}
    with args.priority_csv.open(encoding="utf-8", newline="") as handle:
        for item in csv.DictReader(handle):
            priorities[item["episode_id"]] = int(item["generation_priority"])
    rows = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line]
    selected = sorted((row for row in rows if row["episode_id"] in priorities), key=lambda row: priorities[row["episode_id"]])[:args.episodes]
    if len(selected) != args.episodes:
        raise RuntimeError(f"only found {len(selected)} of requested {args.episodes} priority episodes")
    tasks = [
        {"episode_id": row["episode_id"], "generation_priority": priorities[row["episode_id"]], "shot_id": shot["shot_id"], "prompt": shot["generation_prompt_en_veo_6s"]}
        for row in selected for shot in row["shots"]
    ]
    args.output.mkdir(parents=True, exist_ok=True)
    events = args.output / "events.jsonl"
    run = {
        "started_at": utc_now(), "model": args.model, "duration_seconds": args.duration_seconds,
        "resolution": args.resolution, "aspect_ratio": args.aspect_ratio, "workers": args.workers,
        "episodes": len(selected), "shot_requests": len(tasks), "priority_range": [priorities[selected[0]["episode_id"]], priorities[selected[-1]["episode_id"]]],
        "input": str(args.input), "priority_csv": str(args.priority_csv),
    }
    (args.output / "run.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
    with (args.output / "selected_episodes.jsonl").open("w", encoding="utf-8") as handle:
        for row in selected:
            handle.write(json.dumps({"episode_id": row["episode_id"], "generation_priority": priorities[row["episode_id"]], "shot_count": len(row["shots"])}) + "\n")
    append_event(events, {"event": "run_started", **run})

    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(generate_one, task, args, key, events) for task in tasks]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results.append(result)
            print(json.dumps({"completed": len(results), "total": len(tasks), "status": result["status"], "episode_id": result["episode_id"], "shot_id": result["shot_id"]}), flush=True)
    completed_at = utc_now()
    summary = {"run": run, "completed_at": completed_at, "status_counts": {}, "results": results}
    for result in results:
        summary["status_counts"][result["status"]] = summary["status_counts"].get(result["status"], 0) + 1
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    append_event(events, {"event": "run_finished", "at": completed_at, "status_counts": summary["status_counts"]})
    print(json.dumps({"event": "run_finished", "status_counts": summary["status_counts"]}), flush=True)
    if summary["status_counts"].get("success", 0) != len(tasks):
        sys.exit(2)


if __name__ == "__main__":
    main()
