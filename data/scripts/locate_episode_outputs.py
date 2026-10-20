#!/usr/bin/env python3
"""Locate aligned StoryMem, Wan2.2, and HoloCine outputs by episode ID."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[3]
STORYMEM_ROOT = WORKSPACE / "EECBench/data/generated/storymem_200_hf"
WAN_ROOT = WORKSPACE / "EECBench/experiments/wan_generation_400_20260921"
HOLO_ROOT = WORKSPACE / "EECBench/experiments/holocine_generation_200_20260922"


def read_json(path: Path):
    return json.loads(path.read_text())


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def absolute(path: str | Path | None) -> str | None:
    if path is None:
        return None
    value = Path(path)
    if not value.is_absolute():
        value = WORKSPACE / value
    return str(value.resolve())


def existing(path: str | Path | None) -> bool:
    value = absolute(path)
    return bool(value and Path(value).is_file())


def shot_number(shot_id: str) -> int:
    assert shot_id.startswith("Shot")
    return int(shot_id[4:])


def load_indexes() -> tuple[dict[str, dict], dict[str, list[dict]]]:
    episodes = {
        row["episode_id"]: row
        for row in read_jsonl(STORYMEM_ROOT / "index/episodes.jsonl")
    }
    shots: dict[str, list[dict]] = {}
    for row in read_jsonl(STORYMEM_ROOT / "index/shots.jsonl"):
        shots.setdefault(row["episode_id"], []).append(row)
    for rows in shots.values():
        rows.sort(key=lambda row: row["shot_index"])
    return episodes, shots


def locate_wan(episode_id: str, canonical_shots: list[dict], queue: list[dict]) -> dict:
    tasks = sorted(
        (task for task in queue if task["episode_id"] == episode_id),
        key=lambda task: shot_number(task["shot_id"]),
    )
    canonical = {row["shot_id"]: row for row in canonical_shots}
    shot_rows = []
    for task in tasks:
        result = task.get("result") or {}
        output = result.get("output") or WAN_ROOT / "videos" / episode_id / f"{task['shot_id']}.mp4"
        shot_rows.append({
            "shot_id": task["shot_id"],
            "status": task["status"],
            "prompt": task["prompt"],
            "prompt_sha256": task["prompt_sha256"],
            "matches_canonical_storymem_prompt": (
                task["shot_id"] in canonical
                and task["prompt_sha256"] == canonical[task["shot_id"]]["prompt_sha256"]
                and task["prompt"] == canonical[task["shot_id"]]["prompt"]
            ),
            "video_path": absolute(output),
            "video_exists": existing(output),
            "video_sha256": result.get("sha256"),
            "seed": task["seed"],
        })
    episode_video = WAN_ROOT / "videos" / episode_id / "episode.mp4"
    episode_metadata = WAN_ROOT / "videos" / episode_id / "episode.json"
    complete = (
        len(tasks) == len(canonical_shots)
        and all(row["status"] == "done" and row["video_exists"] for row in shot_rows)
        and episode_video.is_file()
        and episode_metadata.is_file()
    )
    return {
        "status": "complete" if complete else "incomplete",
        "shot_count": len(shot_rows),
        "all_prompts_match_canonical_storymem": all(
            row["matches_canonical_storymem_prompt"] for row in shot_rows
        ) and len(shot_rows) == len(canonical_shots),
        "episode_video_path": absolute(episode_video),
        "episode_video_exists": episode_video.is_file(),
        "episode_metadata_path": absolute(episode_metadata),
        "shots": shot_rows,
    }


def locate_holocine(episode_id: str, canonical_shots: list[dict], queue: list[dict]) -> dict:
    task = next((item for item in queue if item["episode_id"] == episode_id), None)
    if task is None:
        return {"status": "not_in_queue"}
    result = task.get("result") or {}
    attempt = result.get("attempt")
    episode_video = Path(attempt) / "episode.mp4" if attempt else None
    result_path = Path(attempt) / "result.json" if attempt else None
    worker_state = None
    worker = task.get("worker")
    worker_path = HOLO_ROOT / "workers" / f"{worker}.json" if worker else None
    if worker_path and worker_path.is_file():
        state = read_json(worker_path)
        if state.get("episode_id") == episode_id:
            worker_state = {
                key: state.get(key)
                for key in ("state", "step", "steps", "worker", "node", "job", "heartbeat")
            }
    structured_prompt_path = HOLO_ROOT / "inputs" / episode_id / "structured_prompt.json"
    structured = read_json(structured_prompt_path)
    assert structured["shot_ids"] == [row["shot_id"] for row in canonical_shots]
    assert structured["shot_captions"] == [row["prompt"] for row in canonical_shots]
    boundaries = [0, *task["cuts"], task["frames"]]
    shot_rows = []
    for index, canonical in enumerate(canonical_shots):
        shot_rows.append({
            "shot_id": canonical["shot_id"],
            "shared_shot_prompt": structured["shot_captions"][index],
            "shared_shot_prompt_sha256": canonical["prompt_sha256"],
            "matches_canonical_storymem_prompt": True,
            "source_episode_video_path": absolute(episode_video),
            "source_episode_video_exists": existing(episode_video),
            "frame_start_inclusive": boundaries[index],
            "frame_end_exclusive": boundaries[index + 1],
            "materialized_shot_video_path": None,
            "available_as_frame_segment": existing(episode_video),
        })
    return {
        "status": task["status"],
        "rank": task["rank"],
        "shot_count": task["shot_count"],
        "prompt": task["prompt"],
        "prompt_sha256": task["prompt_sha256"],
        "additional_global_caption": structured["global_caption"],
        "all_shot_prompts_match_canonical_storymem": True,
        "full_model_input_differs_from_per_shot_models": True,
        "seed": task["seed"],
        "frames": task["frames"],
        "cut_frame_indices": task["cuts"],
        "attempts": task["attempts"],
        "episode_video_path": absolute(episode_video),
        "episode_video_exists": existing(episode_video),
        "result_path": absolute(result_path),
        "result": result or None,
        "worker_state": worker_state,
        "structured_prompt_path": absolute(structured_prompt_path),
        "shots": shot_rows,
    }


def locate(episode_id: str, episodes: dict[str, dict], shots: dict[str, list[dict]], wan_queue, holo_queue) -> dict:
    if episode_id not in episodes:
        raise KeyError(f"episode_id is not in the pinned StoryMem-200 index: {episode_id}")
    episode = episodes[episode_id]
    canonical_shots = shots[episode_id]
    return {
        "episode_id": episode_id,
        "generation_priority": episode["generation_priority"],
        "canonical": {
            "story_script_path": absolute(episode["story_script_path"]),
            "contract_path": absolute(episode["contract_path"]),
            "alignment_contract_path": absolute(episode["alignment_contract_path"]),
            "entity_schedule_path": absolute(episode["entity_schedule_path"]),
        },
        "storymem": {
            "status": "complete",
            "episode_video_path": absolute(episode["full_episode_video_path"]),
            "shots": [
                {
                    "shot_id": row["shot_id"],
                    "prompt": row["prompt"],
                    "prompt_sha256": row["prompt_sha256"],
                    "video_path": absolute(row["generated_shot_path"]),
                }
                for row in canonical_shots
            ],
        },
        "wan22": locate_wan(episode_id, canonical_shots, wan_queue),
        "holocine": locate_holocine(episode_id, canonical_shots, holo_queue),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("episode_id", nargs="?")
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    if not args.episode_id and not args.audit:
        parser.error("provide EPISODE_ID or --audit")

    episodes, shots = load_indexes()
    wan_queue = read_json(WAN_ROOT / "queue.json")["tasks"]
    holo_queue = read_json(HOLO_ROOT / "queue.json")["tasks"]
    if args.audit:
        rows = [locate(episode_id, episodes, shots, wan_queue, holo_queue) for episode_id in episodes]
        summary = {
            "episode_count": len(rows),
            "wan22_complete": sum(row["wan22"]["status"] == "complete" for row in rows),
            "wan22_all_prompts_match": sum(
                row["wan22"]["all_prompts_match_canonical_storymem"] for row in rows
            ),
            "holocine_complete": sum(
                row["holocine"]["status"] == "done" and row["holocine"]["episode_video_exists"]
                for row in rows
            ),
            "all_three_share_exact_per_shot_prompts": sum(
                row["wan22"]["all_prompts_match_canonical_storymem"]
                and row["holocine"]["all_shot_prompts_match_canonical_storymem"]
                for row in rows
            ),
            "both_complete": sum(
                row["wan22"]["status"] == "complete"
                and row["holocine"]["status"] == "done"
                and row["holocine"]["episode_video_exists"]
                for row in rows
            ),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    print(json.dumps(locate(args.episode_id, episodes, shots, wan_queue, holo_queue), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
