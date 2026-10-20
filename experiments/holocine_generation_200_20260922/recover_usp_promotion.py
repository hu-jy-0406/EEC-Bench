#!/usr/bin/env python3
"""Safely finish a USP promotion interrupted after its fallback exited."""
import argparse
import hashlib
import os
from pathlib import Path

from campaign import ROOT, locked, read, write


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--episode-id", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    candidate = ROOT / "multigpu_attempts" / args.episode_id / args.run_id
    result = read(candidate / "result.json")
    video = candidate / "episode.mp4"
    if result.get("episode_id") != args.episode_id or result.get("world_size") != 8:
        raise RuntimeError("candidate metadata mismatch")
    if not result.get("finite_latents_and_decoder") or not result.get("full_decode"):
        raise RuntimeError("candidate did not pass full validation")
    if not video.is_file() or hashlib.sha256(video.read_bytes()).hexdigest() != result["video_sha256"]:
        raise RuntimeError("candidate video hash mismatch")

    destination = ROOT / "videos" / args.episode_id
    with locked():
        queue = read(ROOT / "queue.json")
        task = next(task for task in queue["tasks"] if task["episode_id"] == args.episode_id)
        if task["status"] != "multigpu_promoting":
            raise RuntimeError(f"unexpected queue status: {task['status']}")
        if destination.exists() or destination.is_symlink():
            raise RuntimeError(f"canonical destination already exists: {destination}")
        destination.parent.mkdir(exist_ok=True)
        os.symlink(os.path.relpath(candidate, destination.parent), destination)
        result = dict(result, promoted_at=__import__("time").time(),
                      canonical_video=str(destination / "episode.mp4"),
                      recovery="promotion_watcher_exited_after_fallback_stop")
        task.update(status="done", worker=result["worker"], result=result,
                    ended=__import__("time").time(), error=None)
        write(ROOT / "queue.json", queue)
        if all(task["status"] == "done" for task in queue["tasks"]):
            write(ROOT / "complete.json", {"completed": __import__("time").time(),
                                             "episodes": 200,
                                             "shots": sum(task["shot_count"] for task in queue["tasks"])})
    write(candidate / "promotion.json", {"result": result, "recovered": True})
    print("USP_PROMOTED", result["episode_id"], result["video_sha256"])


if __name__ == "__main__":
    main()
