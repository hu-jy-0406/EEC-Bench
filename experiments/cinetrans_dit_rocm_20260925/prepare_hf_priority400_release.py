#!/usr/bin/env python3
"""Prepare a full 400-episode prompt release while preserving prior video QA."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EXP = ROOT / "EECBench/experiments/cinetrans_dit_rocm_20260925"
STAGING = EXP / "hf_release_upload_staging"
QUEUE = ROOT / "EECBench/experiments/wan_generation_400_20260921/prompt_revision_20260922/input_queue_400.v2.jsonl"
SELECTED = EXP / "run_priority100/selected_priority100.jsonl"
MANIFEST_100 = STAGING / "runs/priority_1_100_manifest.jsonl"
PROMPT_DIR = STAGING / "prompts/episodes"
MANIFEST_400 = STAGING / "runs/priority_1_400_manifest.jsonl"

OLD_REPO = "BlueSourceJY/eec-bench-cinetrans-dit-priority100"
NEW_REPO = "BlueSourceJY/eec-bench-cinetrans-dit-priority400"
SOURCE_REPO = "BlueSourceJY/eec-bench-storymem-400-wan2.1-t2v-1.3b"
SOURCE_REVISION = "3d803b02b06749da72022177d822b1f9d98698ae"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def write_jsonl(path: Path, values: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(value, ensure_ascii=False) + "\n" for value in values))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> None:
    queue = read_jsonl(QUEUE)
    selected = read_jsonl(SELECTED)
    manifest100 = read_jsonl(MANIFEST_100)
    if len(queue) != 400 or len({row["episode_id"] for row in queue}) != 400:
        raise SystemExit("Expected 400 unique queue episodes")
    ids = [row["episode_id"] for row in queue]
    if [row["episode_id"] for row in selected] != ids[:100]:
        raise SystemExit("Priority-100 set no longer matches the first 100 queue IDs")
    if [row["episode_id"] for row in manifest100] != ids[:100]:
        raise SystemExit("Existing release manifest no longer matches the first 100 queue IDs")
    for row in queue:
        if not row.get("global_prompt_original") or not row.get("shots"):
            raise SystemExit(f"Missing global prompt or shots: {row.get('episode_id')}")
        for shot in row["shots"]:
            prompt = shot.get("wan_prompt_en")
            if not prompt or sha256_text(prompt) != shot.get("wan_sha256"):
                raise SystemExit(f"Prompt/hash mismatch: {row['episode_id']} {shot.get('shot_id')}")
            if sha256_text(shot.get("generation_prompt_en_original", "")) != shot.get("original_sha256"):
                raise SystemExit(f"Original prompt/hash mismatch: {row['episode_id']} {shot.get('shot_id')}")

    queue_sha = hashlib.sha256(QUEUE.read_bytes()).hexdigest()
    old_manifest = {row["episode_id"]: row for row in manifest100}
    prompt_records: list[dict] = []
    manifest400: list[dict] = []

    # Existing generated metadata must still contain precisely the queued prompt text.
    metadata_by_id: dict[str, dict] = {}
    for metadata_path in (STAGING / "episodes").glob("*/metadata.json"):
        metadata = json.loads(metadata_path.read_text())
        metadata_by_id[metadata["episode_id"]] = metadata

    for priority, row in enumerate(queue, start=1):
        episode_id = row["episode_id"]
        shots = []
        for shot in row["shots"]:
            shots.append({
                "shot_id": shot["shot_id"],
                "source_scene_id": shot.get("scene_id"),
                "target_duration_seconds": shot["target_duration_seconds"],
                "prompt": shot["wan_prompt_en"],
                "prompt_sha256": shot["wan_sha256"],
                "source_prompt_en_original": shot["generation_prompt_en_original"],
                "source_prompt_sha256": shot["original_sha256"],
                "context_additions": shot.get("context_additions", []),
            })
        prompt_record = {
            "schema_version": 1,
            "episode_id": episode_id,
            "generation_priority": priority,
            "shot_count": row["shot_count"],
            "target_duration_seconds": row["target_duration_seconds"],
            "source_dataset": SOURCE_REPO,
            "source_revision": SOURCE_REVISION,
            "source_queue": "input_queue_400.v2.jsonl",
            "source_queue_sha256": queue_sha,
            "global_prompt": row["global_prompt_original"],
            "global_prompt_sha256": sha256_text(row["global_prompt_original"]),
            "shots": shots,
        }
        prompt_relpath = f"prompts/episodes/{episode_id}.json"
        prompt_records.append(prompt_record)
        write_json(STAGING / prompt_relpath, prompt_record)

        if priority <= 100:
            prior = old_manifest[episode_id]
            status = prior["qc_status"]
            video_available = bool(prior.get("included_in_dataset"))
            metadata = metadata_by_id.get(episode_id)
            if video_available:
                if metadata is None:
                    raise SystemExit(f"Missing uploaded metadata for included video: {episode_id}")
                queued = {s["shot_id"]: s for s in row["shots"]}
                if metadata.get("global_prompt") != row["global_prompt_original"]:
                    raise SystemExit(f"Global prompt changed in existing metadata: {episode_id}")
                if len(metadata.get("shots", [])) != len(row["shots"]):
                    raise SystemExit(f"Shot count changed in existing metadata: {episode_id}")
                for generated_shot in metadata["shots"]:
                    source_shot = queued[generated_shot["shot_id"]]
                    if generated_shot["prompt"] != source_shot["wan_prompt_en"]:
                        raise SystemExit(f"Per-shot prompt changed in existing metadata: {episode_id} {generated_shot['shot_id']}")
                    if generated_shot["prompt_sha256"] != source_shot["wan_sha256"]:
                        raise SystemExit(f"Per-shot prompt hash changed in existing metadata: {episode_id} {generated_shot['shot_id']}")
        else:
            prior = None
            status = "prompt_only_not_attempted_in_priority100_run"
            video_available = False

        full_row = {
            "generation_priority": priority,
            "episode_id": episode_id,
            "shot_count": row["shot_count"],
            "target_duration_seconds": row["target_duration_seconds"],
            "prompt_available": True,
            "prompt_path": prompt_relpath,
            "generation_status": status,
            "video_available": video_available,
            "video_path": prior.get("video_path") if prior else None,
        }
        if prior:
            full_row["priority100_run_record"] = prior
        manifest400.append(full_row)

    write_jsonl(MANIFEST_400, manifest400)
    qhash = queue_sha
    source_readme = (
        f"Prompts are derived from `{SOURCE_REPO}` pinned to snapshot "
        f"`{SOURCE_REVISION}`. The 400 records follow the exact order of "
        f"`input_queue_400.v2.jsonl` (SHA-256 `{qhash}`); original episode IDs "
        "are preserved. Existing full-episode source artifacts remain attached "
        "to the 26 videos that passed the priority-100 QA."
    )
    (STAGING / "source/README.md").write_text(source_readme + "\n")

    status_counts = Counter(row["generation_status"] for row in manifest400)
    summary = {
        "dataset_repo": NEW_REPO,
        "source_dataset": SOURCE_REPO,
        "source_revision": SOURCE_REVISION,
        "source_queue": "input_queue_400.v2.jsonl",
        "source_queue_sha256": queue_sha,
        "episodes_with_prompts": len(prompt_records),
        "prompt_files": len(prompt_records),
        "episodes_with_validated_videos": sum(row["video_available"] for row in manifest400),
        "generation_status_counts": dict(sorted(status_counts.items())),
        "manifest": "runs/priority_1_400_manifest.jsonl",
        "prompt_layout": "prompts/episodes/<episode_id>.json",
    }
    write_json(STAGING / "runs/priority_1_400_summary.json", summary)

    readme = f'''---
language:
- en
tags:
- video-generation
- cinetrans
- eec-bench
license: other
---
# CineTrans-DiT prompts and generations for EEC-Bench

Private release of the exact CineTrans generation prompts for all 400 episodes in the frozen EEC-Bench queue, plus the completed videos that passed QA. Every prompt record is keyed by its original `episode_id`.

## Coverage

- `prompts/episodes/<episode_id>.json`: exact prompt inputs for all 400 episodes. Each file includes the original episode ID, queue priority, source provenance, `global_prompt`, each per-shot `prompt`, and SHA-256 hashes. Per-shot prompt text is the frozen `wan_prompt_en`; the global text is `global_prompt_original`.
- The generation run covered only the first 100 queue entries. It produced 26 validated videos; 22 entries have failed terminal attempts and 52 have no completion event. The remaining 300 have prompts in this dataset but were not attempted in that run.
- `episodes/<episode_id>/video.mp4` and `metadata.json` exist only for the 26 validated videos. Original source artifacts for those videos remain under each episode's `source/` directory.
- `runs/priority_1_400_manifest.jsonl` maps all 400 original IDs to prompt files and generation/video status. `runs/priority_1_100_manifest.jsonl` preserves the original partial-run manifest.

## Inference and validation

CineTrans-DiT uses the Wan2.1-T2V-1.3B backbone with the released CineTrans LoRA. For the completed priority-100 run, per-shot `wan_prompt_en` and the episode's `global_prompt_original` were used unchanged. The 26 included videos passed H.264, 832x480, 16 fps, and expected-duration checks; FFmpeg decoded every full file, and a midpoint frame from each shot was reviewed. This is a coarse visual correspondence audit, not frame-by-frame semantic scoring.
'''
    (STAGING / "README.md").write_text(readme)

    print(json.dumps({
        "queue_episodes": len(queue),
        "prompt_records": len(prompt_records),
        "existing_video_metadata_checked": len(metadata_by_id),
        "existing_100_manifest_entries": len(manifest100),
        "videos_in_400_manifest": summary["episodes_with_validated_videos"],
        "generation_status_counts": dict(sorted(status_counts.items())),
        "source_queue_sha256": queue_sha,
        "new_manifest": str(MANIFEST_400.relative_to(STAGING)),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
