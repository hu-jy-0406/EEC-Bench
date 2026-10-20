"""Generate one campaign episode with HoloCine USP on all visible GPUs.

The result is an isolated validated candidate. The canonical queue and videos
symlink stay untouched while the single-GPU fallback is running.
"""
import argparse, hashlib, json, os, socket, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
FEAS = HERE.parent / "generation_feasibility_20260921"
SHARED = HERE.parent / "holocine_shared_prompts_20260922"
sys.path[:0] = [str(HERE), str(FEAS / "holocine_deps"), str(FEAS / "deps"),
                str(FEAS / "repos/HoloCine"), str(SHARED)]
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
from campaign import NEGATIVE, load_pipe, read, write


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--episode-id", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    import imageio_ffmpeg
    import numpy as np
    import torch
    import torch.distributed as dist
    from diffsynth import save_video
    from text_context import generate_episode, validate_prompt

    rank = int(os.environ["RANK"])
    world = int(os.environ["WORLD_SIZE"])
    if world < 2:
        raise RuntimeError("USP requires at least two ranks")
    cache = Path("/tmp/eecbench_holocine200_miopen") / f"usp_{args.run_id}_r{rank}"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.update(MIOPEN_USER_DB_PATH=str(cache), MIOPEN_CUSTOM_CACHE_DIR=str(cache))

    queue = read(HERE / "queue.json")
    task = next(t for t in queue["tasks"] if t["episode_id"] == args.episode_id)
    out = HERE / "multigpu_attempts" / args.episode_id / args.run_id
    if rank == 0:
        out.mkdir(parents=True, exist_ok=False)
        write(out / "input.json", task)
        write(out / "launch.json", {
            "episode_id": args.episode_id, "run_id": args.run_id,
            "node": socket.gethostname(), "world_size": world,
            "started": time.time(), "mode": "mapped", "use_usp": True,
            "single_gpu_fallback_worker": task.get("worker"),
        })

    pipe = load_pipe("mapped", use_usp=True)
    torch.cuda.synchronize()
    if rank == 0:
        write(out / "state.json", {"state": "model_ready", "step": 0,
              "steps": 50, "time": time.time(), "world_size": world,
              "node": socket.gethostname()})
        write(out / "text_audit.json", validate_prompt(pipe, task["prompt"], task["shot_count"]))

    scheduler_step = pipe.scheduler.step
    def finite_step(*values, **kwargs):
        output = scheduler_step(*values, **kwargs)
        if not torch.isfinite(output).all().item():
            raise RuntimeError("Nonfinite diffusion latent")
        return output
    pipe.scheduler.step = finite_step

    original_convert = pipe.vae_output_to_video
    def finite_pixels(value, *values, **kwargs):
        if not torch.isfinite(value).all().item():
            raise RuntimeError("Nonfinite decoded tensor")
        return original_convert(value, *values, **kwargs)
    pipe.vae_output_to_video = finite_pixels

    def progress(iterator):
        for index, timestep in enumerate(iterator):
            started = time.perf_counter()
            yield timestep
            torch.cuda.synchronize()
            seconds = time.perf_counter() - started
            if rank == 0:
                row = {"step": index + 1, "seconds": seconds,
                       "timestep": float(timestep), "time": time.time()}
                with (out / "steps.jsonl").open("a") as handle:
                    handle.write(json.dumps(row) + "\n")
                write(out / "state.json", {"state": "denoising", "step": index + 1,
                      "steps": 50, "last_step_seconds": seconds, "time": time.time(),
                      "world_size": world, "node": socket.gethostname()})

    started = time.perf_counter()
    torch.cuda.reset_peak_memory_stats()
    video = generate_episode(
        pipe, task["prompt"], task["shot_count"], num_frames=task["frames"],
        shot_cut_frames=task["cuts"], width=832, height=480,
        num_inference_steps=50, cfg_scale=5.0, sigma_shift=5.0,
        negative_prompt=NEGATIVE, tiled=True, seed=task["seed"],
        progress_bar_cmd=progress)
    generation_seconds = time.perf_counter() - started
    peaks = [None] * world
    dist.all_gather_object(peaks, torch.cuda.max_memory_allocated() / 2**30)

    if rank == 0:
        if len(video) != task["frames"]:
            raise RuntimeError(f"frame count {len(video)} != {task['frames']}")
        low, high = 255, 0
        for image in video:
            array = np.asarray(image)
            if array.shape != (480, 832, 3) or not np.isfinite(array).all():
                raise RuntimeError(f"invalid decoded frame: {array.shape}")
            low, high = min(low, int(array.min())), max(high, int(array.max()))
        if high <= low:
            raise RuntimeError("constant output")
        path = out / "episode.mp4"
        save_video(video, str(path), fps=16, quality=5)
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-threads", "2",
                        "-i", str(path), "-f", "null", "-"],
                       check=True, capture_output=True)
        decoded, seconds = imageio_ffmpeg.count_frames_and_secs(str(path))
        if decoded != task["frames"]:
            raise RuntimeError(f"ffmpeg frame count {decoded} != {task['frames']}")
        result = {
            "episode_id": task["episode_id"], "rank": task["rank"],
            "frames": decoded, "seconds": seconds,
            "generation_seconds": generation_seconds,
            "finite_latents_and_decoder": True, "full_decode": True,
            "prompt_sha256": task["prompt_sha256"], "seed": task["seed"],
            "worker": f"usp8_{socket.gethostname()}", "world_size": world,
            "peak_gib_by_rank": peaks, "completed": time.time(),
            "video_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "attempt": str(out), "use_usp": True,
        }
        write(out / "result.json", result)
        write(out / "state.json", {"state": "validated_candidate", "step": 50,
              "steps": 50, "time": time.time(), "result": result})
        print("USP_CANDIDATE_DONE", json.dumps(result), flush=True)
    dist.barrier()
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
