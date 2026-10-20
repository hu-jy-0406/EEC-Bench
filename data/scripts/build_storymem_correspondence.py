#!/usr/bin/env python3
"""Build and validate the StoryMem episode/prompt/contract/video index."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[3]
INPUT_ROOT = WORKSPACE / "EECBench/exports/storymem_hf_priority50_20260922/storymem_inputs/episodes"


def read_json(path: Path):
    return json.loads(path.read_text())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def workspace_path(path: Path) -> str:
    return path.relative_to(WORKSPACE).as_posix()


def atomic_json(path: Path, value) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temp.replace(path)


def atomic_jsonl(path: Path, rows: list[dict]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    temp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset_root", type=Path)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()

    dataset_root = args.dataset_root.resolve()
    metadata_paths = sorted(dataset_root.glob("storymem_outputs/*/episodes/*/metadata.json"))
    assert len(metadata_paths) == 200, len(metadata_paths)

    episodes: list[dict] = []
    shots: list[dict] = []
    episode_ids: set[str] = set()
    priorities: set[int] = set()
    relocated_paths = 0
    derived_shot_probes = 0

    for metadata_path in metadata_paths:
        metadata = read_json(metadata_path)
        episode_id = metadata["episode_id"]
        priority = metadata["generation_priority"]
        assert episode_id not in episode_ids, episode_id
        assert priority not in priorities, priority
        episode_ids.add(episode_id)
        priorities.add(priority)
        assert metadata["generated"] and metadata["complete"]
        assert not metadata["missing_shot_videos"]

        input_dir = INPUT_ROOT / episode_id
        story_script_path = input_dir / "story_script.json"
        entity_schedule_path = input_dir / "entity_schedule.json"
        contract_path = input_dir / "contract.json"
        alignment_contract_path = input_dir / "alignment_contract.json"
        for path in (story_script_path, entity_schedule_path, contract_path, alignment_contract_path):
            assert path.is_file(), path

        source = metadata["source_prompt_record"]
        assert sha256(story_script_path) == source["story_script_sha256"]
        assert sha256(entity_schedule_path) == source["entity_schedule_sha256"]
        assert sha256(contract_path) == source["contract_sha256"]
        assert sha256(alignment_contract_path) == source["alignment_contract_sha256"]
        assert read_json(story_script_path) == metadata["story_script"]
        assert read_json(entity_schedule_path) == metadata["entity_schedule"]
        assert read_json(contract_path) == metadata["contract"]
        assert read_json(alignment_contract_path) == metadata["alignment_contract"]

        recorded_full_video_path = dataset_root / metadata["full_episode_video_path"]
        full_video_path = recorded_full_video_path
        if not full_video_path.is_file():
            full_video_path = metadata_path.parent / "full_episode.mp4"
            relocated_paths += 1
        assert full_video_path.is_file(), full_video_path
        full_probe = metadata["full_episode_video_probe"]
        assert full_probe["valid"]
        assert full_video_path.stat().st_size == full_probe["size_bytes"]

        contract = metadata["contract"]
        script_scenes = {scene["scene_num"]: scene for scene in metadata["story_script"]["scenes"]}
        episode_shots: list[dict] = []
        assert len(metadata["shots"]) == metadata["shot_count"]
        for shot_index, shot in enumerate(metadata["shots"], 1):
            shot_id = shot["shot_id"]
            scene = script_scenes[shot["storymem_scene_num"]]
            prompt = scene["video_prompts"][shot["storymem_shot_num"] - 1]
            assert prompt == shot.get("prompt", prompt)
            assert hashlib.sha256(prompt.encode()).hexdigest() == shot["prompt_sha256"]

            if "video_path" in shot:
                recorded_video_path = dataset_root / shot["video_path"]
                video_path = recorded_video_path
                if not video_path.is_file():
                    video_path = metadata_path.parent / "shots" / shot["storymem_output_name"]
                    relocated_paths += 1
            else:
                recorded_video_path = None
                video_path = metadata_path.parent / "shots" / shot["storymem_output_name"]
            assert video_path.is_file(), video_path
            if "video_probe" in shot:
                video_probe = shot["video_probe"]
                assert shot.get("generated", True) and video_probe["valid"]
                assert video_path.stat().st_size == video_probe["size_bytes"]
            else:
                video_probe = {
                    "valid": True,
                    "size_bytes": video_path.stat().st_size,
                    "source": "derived_from_complete_episode_metadata_and_file_presence",
                }
                derived_shot_probes += 1
            schedule_key = shot["contract_schedule_key"]
            assert schedule_key in contract["entity_schedule"]
            claims = [claim for claim in contract["claims"] if shot_id in claim["shot_ids"]]

            row = {
                "episode_id": episode_id,
                "generation_priority": priority,
                "shot_index": shot_index,
                "shot_id": shot_id,
                "source_scene_id": shot["source_scene_id"],
                "contract_schedule_key": schedule_key,
                "storymem_scene_num": shot["storymem_scene_num"],
                "storymem_shot_num": shot["storymem_shot_num"],
                "prompt": prompt,
                "prompt_sha256": shot["prompt_sha256"],
                "scheduled_entities": contract["entity_schedule"][schedule_key],
                "contract_claim_ids": [claim["claim_id"] for claim in claims],
                "contract_claims": claims,
                "generated_shot_path": workspace_path(video_path),
                "recorded_generated_shot_path": (
                    workspace_path(recorded_video_path) if recorded_video_path is not None else None
                ),
                "video_probe": video_probe,
                "metadata_path": workspace_path(metadata_path),
                "story_script_path": workspace_path(story_script_path),
                "contract_path": workspace_path(contract_path),
                "alignment_contract_path": workspace_path(alignment_contract_path),
                "entity_schedule_path": workspace_path(entity_schedule_path),
            }
            shots.append(row)
            episode_shots.append({
                "shot_id": shot_id,
                "shot_index": shot_index,
                "generated_shot_path": row["generated_shot_path"],
                "contract_schedule_key": schedule_key,
                "prompt_sha256": shot["prompt_sha256"],
            })

        output_batch = metadata_path.relative_to(dataset_root).parts[1]
        episodes.append({
            "episode_id": episode_id,
            "generation_priority": priority,
            "in_core_100": metadata["in_core_100"],
            "output_batch": output_batch,
            "shot_count": metadata["shot_count"],
            "target_duration_seconds": metadata["target_duration_seconds"],
            "story_name": metadata["story_script"]["story_name"],
            "story_overview": metadata["story_script"]["story_overview"],
            "metadata_path": workspace_path(metadata_path),
            "story_script_path": workspace_path(story_script_path),
            "contract_path": workspace_path(contract_path),
            "alignment_contract_path": workspace_path(alignment_contract_path),
            "entity_schedule_path": workspace_path(entity_schedule_path),
            "full_episode_video_path": workspace_path(full_video_path),
            "recorded_full_episode_video_path": workspace_path(recorded_full_video_path),
            "full_episode_video_probe": full_probe,
            "contract_claim_count": len(contract["claims"]),
            "shots": episode_shots,
        })

    assert priorities == set(range(1, 201))
    episodes.sort(key=lambda row: row["generation_priority"])
    shots.sort(key=lambda row: (row["generation_priority"], row["shot_index"]))
    assert sum(row["shot_count"] for row in episodes) == len(shots)

    index_root = dataset_root / "index"
    index_root.mkdir(parents=True, exist_ok=True)
    atomic_jsonl(index_root / "episodes.jsonl", episodes)
    atomic_jsonl(index_root / "shots.jsonl", shots)
    summary = {
        "schema_version": "eec_storymem_correspondence_v1",
        "source_repository": "BlueSourceJY/eec-bench-storymem-400",
        "source_revision": args.revision,
        "episode_count": len(episodes),
        "shot_count": len(shots),
        "generation_priorities": [episodes[0]["generation_priority"], episodes[-1]["generation_priority"]],
        "shot_count_distribution": dict(sorted(Counter(row["shot_count"] for row in episodes).items())),
        "output_batches": dict(sorted(Counter(row["output_batch"] for row in episodes).items())),
        "all_metadata_complete": True,
        "all_video_files_exist": True,
        "all_available_recorded_video_sizes_match": True,
        "derived_shot_probe_count": derived_shot_probes,
        "all_embedded_inputs_match_canonical_local_files": True,
        "metadata_paths_relocated_to_actual_batch": relocated_paths,
        "episodes_index": "index/episodes.jsonl",
        "shots_index": "index/shots.jsonl",
    }
    atomic_json(index_root / "summary.json", summary)
    readme = """# StoryMem generated evaluation dataset\n\nThis directory is the local snapshot of `BlueSourceJY/eec-bench-storymem-400`.\n\n- `index/episodes.jsonl` maps every episode to its canonical StoryMem script, contract, entity schedule, full video, and generated shots.\n- `index/shots.jsonl` is the evaluation-ready shot table: each row contains the exact prompt, contract schedule entry, applicable contract claims, and generated shot path.\n- `index/summary.json` records the pinned Hugging Face revision and validation totals.\n\nAll paths in the indexes are relative to the EEC-Bench workspace root. The build validates all 200 metadata records, prompt hashes, canonical input hashes/content, and recorded video file sizes.\n"""
    (dataset_root / "README_LOCAL.md").write_text(readme)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
