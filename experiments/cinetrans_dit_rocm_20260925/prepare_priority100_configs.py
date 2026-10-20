import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
QUEUE = (
    ROOT.parent
    / "wan_generation_400_20260921"
    / "prompt_revision_20260922"
    / "input_queue_400.v2.jsonl"
)
UPSTREAM = ROOT / "upstream"
BASE = ROOT / "checkpoints" / "Wan2.1-T2V-1.3B"
LORA = ROOT / "checkpoints" / "CineTrans-DiT" / "weights.pt"
OUT = ROOT / "run_priority100"
FPS = 16


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main():
    episodes = [json.loads(line) for line in QUEUE.open()]
    episodes.sort(key=lambda item: item["generation_priority"])
    episodes = episodes[:100]
    manifest = []
    for episode in episodes:
        priority = int(episode["generation_priority"])
        episode_id = episode["episode_id"]
        shots = episode["shots"]
        durations = [int(shot["target_duration_seconds"]) for shot in shots]
        total_seconds = sum(durations)
        frame_num = total_seconds * FPS + 1
        if (frame_num - 1) % 4:
            raise ValueError(f"frame count not 4n+1: {episode_id}")
        temporal_latents = (frame_num - 1) // 4 + 1
        mask_info = [duration * FPS // 4 for duration in durations]
        mask_info[0] += temporal_latents - sum(mask_info)
        if sum(mask_info) != temporal_latents:
            raise ValueError(f"invalid shot partition: {episode_id}")

        shot_prompts = [shot["wan_prompt_en"] for shot in shots]
        global_prompt = episode["global_prompt_original"]
        if any(not text for text in shot_prompts) or not global_prompt:
            raise ValueError(f"missing prompt: {episode_id}")
        prompts = shot_prompts + [global_prompt]
        if len(mask_info) != len(prompts) - 1:
            raise ValueError(f"prompt/mask cardinality mismatch: {episode_id}")

        case_dir = OUT / "videos" / episode_id
        case_dir.mkdir(parents=True, exist_ok=True)
        config = {
            "task": "t2v-1.3B",
            "size": "832*480",
            "ckpt_dir": str(BASE),
            "offload_model": True,
            "t5_cpu": True,
            "sample_shift": 8,
            "sample_guide_scale": 6,
            "prompt": prompts,
            "frame_num": frame_num,
            "mask_info": mask_info,
            "ulysses_size": 1,
            "ring_size": 1,
            "t5_fsdp": False,
            "dit_fsdp": False,
            "save_file": str(case_dir / "video.mp4"),
            "prompt_extend_target_lang": "zh",
            "use_prompt_extend": False,
            "prompt_extend_method": "local_qwen",
            "prompt_extend_model": None,
            "base_seed": 42,
            "image": None,
            "first_frame": None,
            "last_frame": None,
            "sample_solver": "unipc",
            "lora_path": str(LORA),
            "lora_rank": 64,
            "sample_steps": 50,
            "general_prompt": True,
            "start_masked_layer": 6,
            "end_masked_layer": 27,
            "mask_p": 0,
        }
        config_path = OUT / "configs" / f"priority_{priority:03d}.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        manifest.append(
            {
                "generation_priority": priority,
                "episode_id": episode_id,
                "shot_count": len(shots),
                "target_duration_seconds": total_seconds,
                "frame_num": frame_num,
                "temporal_latents": temporal_latents,
                "mask_info": mask_info,
                "config_path": str(config_path),
                "output_path": str(case_dir / "video.mp4"),
                "shot_prompt_sha256": [digest(text) for text in shot_prompts],
                "global_prompt_sha256": digest(global_prompt),
                "shot_prompt_source_field": "wan_prompt_en",
                "global_prompt_source_field": "global_prompt_original",
            }
        )

        saved = json.loads(config_path.read_text(encoding="utf-8"))
        if saved["prompt"] != prompts:
            raise AssertionError(f"prompt text changed: {episode_id}")
    manifest_path = OUT / "selected_priority100.jsonl"
    manifest_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in manifest),
        encoding="utf-8",
    )
    print(f"episodes={len(manifest)}")
    print(f"shots={sum(row['shot_count'] for row in manifest)}")
    print(f"duration_seconds={sum(row['target_duration_seconds'] for row in manifest)}")
    print(f"manifest={manifest_path}")


if __name__ == "__main__":
    main()
