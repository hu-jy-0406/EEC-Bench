#!/usr/bin/env python3
"""Generate one EntityBench episode with a single reusable Wan2.1 pipeline."""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import torch


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--script-json", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--wan-root", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--base-seed", type=int, default=20260810)
    parser.add_argument("--sample-steps", type=int, default=20)
    parser.add_argument("--max-shots", type=int, default=0)
    return parser.parse_args()


def atomic_write_json(path: Path, payload):
    temporary = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    os.replace(temporary, path)


def main():
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    for path, label in (
        (args.script_json, "EntityBench script"),
        (args.wan_root, "Wan2.1 source"),
        (args.checkpoint, "Wan2.1 checkpoint"),
    ):
        if not path.exists():
            raise FileNotFoundError(f"{label} not found: {path}")

    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError(
            "Expected exactly one Slurm-bound ROCm GPU; "
            f"available={torch.cuda.is_available()} count={torch.cuda.device_count()}"
        )

    sys.path.insert(0, str(args.wan_root.resolve()))
    import wan
    from wan.configs import SIZE_CONFIGS, WAN_CONFIGS
    from wan.utils.utils import cache_video

    script = json.loads(args.script_json.read_text())
    episode_id = args.script_json.stem
    episode_dir = args.output_root / episode_id
    episode_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = episode_dir / "generation_manifest.json"

    shots = []
    global_index = 0
    for scene in script.get("scenes", []):
        scene_num = int(scene["scene_num"])
        for shot_index, prompt in enumerate(scene.get("video_prompts", []), start=1):
            shots.append(
                {
                    "global_index": global_index,
                    "scene_num": scene_num,
                    "shot_num": shot_index,
                    "prompt": prompt,
                    "seed": args.base_seed + global_index,
                }
            )
            global_index += 1
    if args.max_shots > 0:
        shots = shots[: args.max_shots]

    config = WAN_CONFIGS["t2v-1.3B"]
    manifest = {
        "episode_id": episode_id,
        "generator": "Wan2.1-T2V-1.3B",
        "checkpoint": str(args.checkpoint.resolve()),
        "size": "832*480",
        "frame_num": 81,
        "fps": config.sample_fps,
        "sample_solver": "unipc",
        "sample_steps": args.sample_steps,
        "sample_shift": 8.0,
        "sample_guide_scale": 6.0,
        "base_seed": args.base_seed,
        "offload_model": True,
        "device_name": torch.cuda.get_device_name(0),
        "torch_version": torch.__version__,
        "rocr_visible_devices": os.environ.get("ROCR_VISIBLE_DEVICES", ""),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID", ""),
        "shots": shots,
        "completed": [],
    }
    if manifest_path.exists():
        prior = json.loads(manifest_path.read_text())
        manifest["completed"] = prior.get("completed", [])
    atomic_write_json(manifest_path, manifest)

    logging.info("GPU: %s", manifest["device_name"])
    logging.info("Episode: %s (%d shots)", episode_id, len(shots))
    logging.info("Creating one reusable WanT2V pipeline")
    pipeline = wan.WanT2V(
        config=config,
        checkpoint_dir=str(args.checkpoint),
        device_id=0,
        rank=0,
        t5_fsdp=False,
        dit_fsdp=False,
        use_usp=False,
        t5_cpu=False,
    )

    completed = set(manifest["completed"])
    for shot in shots:
        filename = f"{shot['scene_num']:03d}_{shot['shot_num']:03d}.mp4"
        output_path = episode_dir / filename
        if output_path.exists() and output_path.stat().st_size > 0:
            logging.info("Resume: keeping existing %s", output_path)
            completed.add(filename)
            continue

        started = time.time()
        logging.info(
            "Generating %s seed=%d prompt=%r",
            filename,
            shot["seed"],
            shot["prompt"],
        )
        video = pipeline.generate(
            shot["prompt"],
            size=SIZE_CONFIGS["832*480"],
            frame_num=81,
            shift=8.0,
            sample_solver="unipc",
            sampling_steps=args.sample_steps,
            guide_scale=6.0,
            seed=shot["seed"],
            offload_model=True,
        )
        temporary_path = output_path.with_name(output_path.stem + ".partial.mp4")
        cache_video(
            tensor=video[None],
            save_file=str(temporary_path),
            fps=config.sample_fps,
            nrow=1,
            normalize=True,
            value_range=(-1, 1),
        )
        os.replace(temporary_path, output_path)
        del video
        torch.cuda.empty_cache()
        completed.add(filename)
        manifest["completed"] = sorted(completed)
        atomic_write_json(manifest_path, manifest)
        logging.info(
            "Completed %s in %.1f seconds (%d bytes)",
            filename,
            time.time() - started,
            output_path.stat().st_size,
        )

    logging.info("Finished %d/%d requested shots", len(completed), len(shots))


if __name__ == "__main__":
    main()

