"""Wait for a validated USP candidate and atomically promote it over its fallback."""
import argparse, hashlib, json, os, signal, subprocess, sys, time
from pathlib import Path
from campaign import ROOT, locked, read, write


def stop_worker(name, episode):
    state_path = ROOT / "workers" / f"{name}.json"
    state = read(state_path)
    if state.get("episode_id") != episode:
        raise RuntimeError(f"worker episode changed: {state.get('episode_id')}")
    pid = int(state["pid"])
    proc = Path("/proc") / str(pid)
    if proc.exists():
        args = (proc / "cmdline").read_bytes().split(b"\0")
        expected = str(ROOT / "campaign.py").encode()
        if expected not in args or name.encode() not in args or proc.stat().st_uid != os.getuid():
            raise RuntimeError("refusing to signal an unverified process")
        os.kill(pid, signal.SIGTERM)
        deadline = time.time() + 90
        while proc.exists() and time.time() < deadline:
            time.sleep(1)
        if proc.exists():
            raise RuntimeError(f"worker {name} did not exit after SIGTERM")
    state.update(state="stopped_superseded_by_validated_usp", stopped_at=time.time(),
                 process_exit_verified=True)
    write(state_path, state)
    print(json.dumps({"stopped": name, "episode_id": episode}))


def promote(episode, run_id, timeout_hours):
    candidate = ROOT / "multigpu_attempts" / episode / run_id
    result_path = candidate / "result.json"
    deadline = time.time() + timeout_hours * 3600
    while not result_path.exists():
        if time.time() >= deadline:
            write(candidate / "promotion_timeout.json", {"time": time.time(),
                  "timeout_hours": timeout_hours})
            raise TimeoutError(f"candidate did not validate within {timeout_hours} hours")
        time.sleep(30)

    result = read(result_path)
    video = candidate / "episode.mp4"
    if result.get("episode_id") != episode or result.get("world_size") != 8:
        raise RuntimeError("candidate metadata mismatch")
    if not result.get("finite_latents_and_decoder") or not result.get("full_decode"):
        raise RuntimeError("candidate did not pass full validation")
    if not video.is_file() or hashlib.sha256(video.read_bytes()).hexdigest() != result["video_sha256"]:
        raise RuntimeError("candidate video hash mismatch")

    with locked():
        queue = read(ROOT / "queue.json")
        task = next(t for t in queue["tasks"] if t["episode_id"] == episode)
        if task["status"] == "done":
            write(candidate / "promotion_skipped.json", {"time": time.time(),
                  "reason": "canonical fallback_completed_first", "result": task.get("result")})
            return
        if task["status"] != "running":
            raise RuntimeError(f"unexpected queue status: {task['status']}")
        old_worker = task["worker"]
        old_state = read(ROOT / "workers" / f"{old_worker}.json")
        old_job, old_node = str(old_state["job"]), old_state["node"]
        task.setdefault("interruptions", []).append({"at": time.time(),
              "reason": "superseded_by_validated_usp8_candidate", "worker": old_worker,
              "candidate": str(candidate)})
        task.update(status="multigpu_promoting", worker=f"usp8_{old_node}_replacement")
        write(ROOT / "queue.json", queue)

    command = ["srun", f"--jobid={old_job}", "--overlap", "-w", old_node,
               "-N1", "-n1", "-c1", "--cpu-bind=none", sys.executable,
               str(Path(__file__).resolve()), "stop", "--worker", old_worker,
               "--episode-id", episode]
    subprocess.run(command, check=True)

    destination = ROOT / "videos" / episode
    destination.parent.mkdir(exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise RuntimeError(f"canonical destination already exists: {destination}")
    os.symlink(os.path.relpath(candidate, destination.parent), destination)

    result = dict(result, promoted_at=time.time(), superseded_worker=old_worker,
                  canonical_video=str(destination / "episode.mp4"))
    with locked():
        queue = read(ROOT / "queue.json")
        task = next(t for t in queue["tasks"] if t["episode_id"] == episode)
        if task["status"] != "multigpu_promoting":
            raise RuntimeError(f"promotion status changed: {task['status']}")
        task.update(status="done", worker=result["worker"], result=result,
                    ended=time.time(), error=None)
        write(ROOT / "queue.json", queue)
        if all(t["status"] == "done" for t in queue["tasks"]):
            write(ROOT / "complete.json", {"completed": time.time(), "episodes": 200,
                  "shots": sum(t["shot_count"] for t in queue["tasks"])})
    write(candidate / "promotion.json", {"time": time.time(), "result": result})
    print("USP_PROMOTED", json.dumps(result), flush=True)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    watch = sub.add_parser("watch")
    watch.add_argument("--episode-id", required=True)
    watch.add_argument("--run-id", required=True)
    watch.add_argument("--timeout-hours", type=float, default=5.0)
    stop = sub.add_parser("stop")
    stop.add_argument("--worker", required=True)
    stop.add_argument("--episode-id", required=True)
    args = parser.parse_args()
    if args.action == "stop":
        stop_worker(args.worker, args.episode_id)
    else:
        promote(args.episode_id, args.run_id, args.timeout_hours)


if __name__ == "__main__":
    main()
