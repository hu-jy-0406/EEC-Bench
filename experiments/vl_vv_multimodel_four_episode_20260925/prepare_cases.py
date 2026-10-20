#!/usr/bin/env python3
"""Build immutable six-keyframe detection cases for the selected model outputs."""
import hashlib, json, subprocess, sys
import imageio_ffmpeg
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
EPISODES = [
    '52apMIyJVlc_s00176_n6_clean_v2', '8iDEmCxXz-A_s00025_n6_clean_v2',
    '9ugYT3Xc59s_s00093_n4_clean_v2', 'Wl6COOA3V6Y_s00022_n4_clean_v2',
]
MODELS = ('veo31', 'wan22', 'storymem', 'holocine')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()


FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

def probe(path):
    _, seconds = imageio_ffmpeg.count_frames_and_secs(str(path))
    return float(seconds)


def source(model, episode, index):
    shot = f'Shot{index + 1}'
    if model == 'veo31':
        path = ROOT / 'experiments/veo_generation_priority100_20260923/run02/videos' / episode / f'{shot}.mp4'
        return path, 0.0, probe(path), 'per_shot_video'
    if model == 'wan22':
        path = ROOT / 'experiments/wan_generation_400_20260921/videos' / episode / f'{shot}.mp4'
        return path, 0.0, probe(path), 'per_shot_video'
    if model == 'storymem':
        path = ROOT / 'data/generated/storymem_200_hf/storymem_outputs/priority100_hpsv3/episodes' / episode / 'shots' / f'01_{index + 1:02d}.mp4'
        return path, 0.0, probe(path), 'downloaded_per_shot_video'
    path = ROOT / 'experiments/holocine_generation_200_20260922/attempts' / episode
    candidates = sorted(path.glob('*/result.json'))
    if len(candidates) != 1: raise ValueError(f'{episode}: expected exactly one completed HoloCine result')
    result = json.loads(candidates[0].read_text())
    video = candidates[0].parent / 'episode.mp4'
    if not video.is_file() or result.get('frames') != (6 if '_n6_' in episode else 4) * 80 + 1:
        raise ValueError(f'{episode}: invalid HoloCine completion')
    return video, 5.0 * index, 5.0, 'episode_video_fixed_5s_shot_window'


def frame_times(kind, duration, offset):
    if kind == 'episode_video_fixed_5s_shot_window':
        safe = 4.75
    else:
        safe = duration - max(0.25, duration * 0.05)
    return [offset + safe * i / 5 for i in range(6)]


def build(model, episode):
    contract = ROOT / 'experiments/episode_contracts_20260921/deliverables/episodes' / episode / 'contract.json'
    if not contract.is_file(): raise FileNotFoundError(contract)
    nshots = 6 if '_n6_' in episode else 4
    root = OUT / model / episode
    if root.exists(): raise FileExistsError(f'fresh output required: {root}')
    frames_root = root / 'frames'
    rows = []
    sources = []
    for index in range(nshots):
        sid = f'Shot{index + 1}'
        video, offset, duration, kind = source(model, episode, index)
        if not video.is_file(): raise FileNotFoundError(video)
        times = frame_times(kind, duration, offset)
        frows = []
        for frame_id, ts in enumerate(times):
            target = frames_root / sid / f'frame_{frame_id:06d}.jpg'
            target.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run([FFMPEG, '-v', 'error', '-ss', f'{ts:.9f}', '-i', str(video), '-frames:v', '1', '-q:v', '2', '-y', str(target)], check=True)
            frows.append(dict(frame_id=frame_id, timestamp_sec=ts, path=str(target.resolve()), sha256=sha(target)))
        rows.append(dict(shot_id=sid, video_path=str(video.resolve()), frames=frows))
        sources.append(dict(shot_id=sid, video_path=str(video.resolve()), video_sha256=sha(video), offset_sec=offset, window_duration_sec=duration, extraction_kind=kind))
    manifest = dict(shots=rows, keyframe_policy='six uniform samples over each native shot video, or each fixed 5s HoloCine shot window before its next cut')
    root.mkdir(parents=True, exist_ok=True)
    (root / 'keyframes.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    (root / 'source_videos.json').write_text(json.dumps(dict(model=model, episode_id=episode, contract_path=str(contract.resolve()), contract_sha256=sha(contract), shots=sources), ensure_ascii=False, indent=2) + '\n')
    case = root / 'case'
    subprocess.run([sys.executable, str(ROOT / 'scripts/run_vl_vv_detection.py'), 'prepare', '--manifest', str(root / 'keyframes.json'), '--contract', str(contract), '--case', str(case)], check=True)
    return dict(model=model, episode_id=episode, case=str(case), keyframe_manifest=str(root / 'keyframes.json'), source_videos=str(root / 'source_videos.json'))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for model in MODELS:
        for episode in EPISODES:
            results.append(build(model, episode))
    (OUT / 'prepared_cases.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')

if __name__ == '__main__':
    main()
