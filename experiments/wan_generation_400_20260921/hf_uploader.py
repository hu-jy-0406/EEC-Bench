#!/usr/bin/env python3
"""Incremental uploader for Wan2.2 generations to Hugging Face dataset."""
import argparse
import hashlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parents[2]
VIDEOS_DIR = ROOT / 'videos'
QUEUE_FILE = ROOT.parent / 'wan_prompt_adaptation_20260921/deliverables/generation_queue_400.jsonl'
REGISTRY_FILE = ROOT / 'uploaded_episodes.json'
REPO_ID = 'BlueSourceJY/ERCBench-Wan2.2-T2V-A14B-400'


def load_queue():
    queue = [json.loads(line) for line in QUEUE_FILE.read_text().splitlines() if line.strip()]
    return {ep['episode_id']: ep for ep in queue}


def load_uploaded():
    if REGISTRY_FILE.exists():
        try:
            return set(json.loads(REGISTRY_FILE.read_text()))
        except Exception:
            pass
    return set()


def save_uploaded(uploaded_set):
    temp = REGISTRY_FILE.with_suffix('.json.tmp')
    temp.write_text(json.dumps(sorted(uploaded_set), indent=2) + '\n')
    os.replace(temp, REGISTRY_FILE)


def upload_one_episode(api, episode_id, ep_info, video_dir):
    ep_json_path = video_dir / 'episode.json'
    ep_mp4_path = video_dir / 'episode.mp4'
    if not ep_json_path.exists() or not ep_mp4_path.exists():
        return False

    ep_json = json.loads(ep_json_path.read_text())
    
    # Check that all shots are present
    shots = []
    for s in ep_info['shots']:
        sid = s['shot_id']
        shot_mp4 = video_dir / f'{sid}.mp4'
        shot_json_path = video_dir / f'{sid}.json'
        if not shot_mp4.exists() or not shot_json_path.exists():
            return False
        shot_json = json.loads(shot_json_path.read_text())
        shots.append({
            'shot_id': sid,
            'scene_id': s.get('scene_id'),
            'filename': f'shots/{sid}.mp4',
            'target_duration_seconds': s['target_duration_seconds'],
            'prompt': s['wan_prompt_en'],
            'prompt_sha256': s['wan_sha256'],
            'seed': shot_json['seed'],
            'video_sha256': shot_json['sha256'],
            'video_bytes': shot_mp4.stat().st_size
        })

    meta = {
        'episode_id': episode_id,
        'generation_priority': ep_info['generation_priority'],
        'target_duration_seconds': ep_info['target_duration_seconds'],
        'model': 'Wan-AI/Wan2.2-T2V-A14B',
        'inference_code': 'https://github.com/Wan-Video/Wan2.2',
        'task': 't2v-A14B',
        'width': 832,
        'height': 480,
        'fps': 16,
        'frame_count': 81,
        'sample_solver': 'unipc',
        'sample_steps': 40,
        'sample_shift': 12.0,
        'guide_scale': [3.0, 4.0],
        'precision': 'BF16',
        'episode_video': 'episode.mp4',
        'episode_video_sha256': ep_json['sha256'],
        'shots': shots
    }

    with tempfile.TemporaryDirectory(prefix='hf-wan-') as tmp:
        stage = Path(tmp) / episode_id
        stage.mkdir()
        (stage / 'shots').mkdir()
        (stage / 'metadata.json').write_text(json.dumps(meta, indent=2))
        shutil.copy2(ep_mp4_path, stage / 'episode.mp4')
        for s in ep_info['shots']:
            sid = s['shot_id']
            shutil.copy2(video_dir / f'{sid}.mp4', stage / 'shots' / f'{sid}.mp4')

        print(f"[{time.strftime('%X')}] Uploading {episode_id} (Priority {ep_info['generation_priority']})...", flush=True)
        api.upload_folder(
            folder_path=str(stage),
            path_in_repo=f'episodes/{episode_id}',
            repo_id=REPO_ID,
            repo_type='dataset',
            commit_message=f'Upload episode {episode_id} (priority {ep_info["generation_priority"]})'
        )
        print(f"[{time.strftime('%X')}] Successfully uploaded {episode_id}!", flush=True)
    return True


def run(daemon=False, interval=20):
    api = HfApi()
    ep_map = load_queue()
    uploaded = load_uploaded()
    print(f"Starting HF uploader for {REPO_ID} (already uploaded: {len(uploaded)} episodes)...", flush=True)

    while True:
        # Check all candidate directories
        all_dirs = sorted([p for p in VIDEOS_DIR.iterdir() if p.is_dir()])
        newly_uploaded = 0
        for p in all_dirs:
            eid = p.name
            if eid in uploaded:
                continue
            if eid not in ep_map:
                continue
            if (p / 'episode.json').exists():
                try:
                    success = upload_one_episode(api, eid, ep_map[eid], p)
                    if success:
                        uploaded.add(eid)
                        save_uploaded(uploaded)
                        newly_uploaded += 1
                except Exception as exc:
                    print(f"Upload error for {eid}: {exc}", flush=True)
                    time.sleep(5)

        if not daemon:
            break
        time.sleep(interval)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--daemon', action='store_true', help='Run continuously in background')
    parser.add_argument('--interval', type=int, default=20, help='Polling interval in seconds')
    args = parser.parse_args()
    run(daemon=args.daemon, interval=args.interval)
