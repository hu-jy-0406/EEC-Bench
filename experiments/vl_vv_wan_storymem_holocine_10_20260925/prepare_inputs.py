#!/usr/bin/env python3
"""Freeze keyframes for ten fresh episodes across Wan2.2, StoryMem and HoloCine."""
import concurrent.futures
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
CONTRACT_ROOT = ROOT / 'experiments/episode_contracts_20260921/deliverables'
WAN_ROOT = ROOT / 'experiments/wan_generation_400_20260921/videos'
STORYMEM_ROOT = ROOT / 'data/generated/storymem_200_hf/storymem_outputs/priority100_hpsv3/episodes'
HOLOCINE_ROOT = ROOT / 'experiments/holocine_generation_200_20260922/attempts'
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
MODELS = ('wan22', 'storymem', 'holocine')
PRIORITY_TO_EPISODE = {
    0: '74Od5-Fmf60_s00006_n4_clean_v2',
    1: '74S1Iw0gJrA_s00006_n4_clean_v2',
    2: 'kTAOppBVgsU_s00001_n6_clean_v2',
    5: '7M9pU29bOeY_s00004_n4_clean_v2',
    7: '2hEV6a24yXc_s00017_n8_clean_v3_alt8',
    8: '6kwhPKkHFpA_s00007_n4_clean_v2',
    9: 'v9I0QHOiU0Y_s00050_n4_clean_v2',
    10: 'KFuxHDKp2oc_s00012_n6_clean_v2',
    12: 'tIB4z4uMeNs_s00023_n4_clean_v2',
    13: 'MTYQT6fSzaE_s00091_n4_clean_v2',
}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def probe(path):
    frames, duration = imageio_ffmpeg.count_frames_and_secs(str(path))
    if int(frames) <= 0 or float(duration) <= 0:
        raise ValueError(f'Invalid or empty video: {path}')
    return int(frames), float(duration)


def contract_path(episode):
    path = CONTRACT_ROOT / 'episodes' / episode / 'contract.json'
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def source_for(model, episode, shot_index, shot_count):
    shot_name = f'Shot{shot_index + 1}'
    if model == 'wan22':
        path = WAN_ROOT / episode / f'{shot_name}.mp4'
        kind = 'per_shot_video'
    elif model == 'storymem':
        path = STORYMEM_ROOT / episode / 'shots' / f'01_{shot_index + 1:02d}.mp4'
        kind = 'downloaded_per_shot_video'
    elif model == 'holocine':
        results = sorted((HOLOCINE_ROOT / episode).glob('*/result.json'))
        if len(results) != 1:
            raise ValueError(f'{episode}: expected one HoloCine result, found {len(results)}')
        result = read(results[0])
        expected_frames = shot_count * 80 + 1
        if result.get('frames') != expected_frames:
            raise ValueError(f'{episode}: HoloCine result frame count is not {expected_frames}')
        path = results[0].parent / 'episode.mp4'
        kind = 'episode_video_fixed_5s_shot_window'
    else:
        raise ValueError(f'Unknown model: {model}')
    if not path.is_file():
        raise FileNotFoundError(path)
    if kind == 'episode_video_fixed_5s_shot_window':
        return path, shot_index * 5.0, 5.0, expected_frames, kind
    frames, duration = probe(path)
    return path, 0.0, duration, frames, kind


def sample_times(kind, duration, offset):
    safe = 4.75 if kind == 'episode_video_fixed_5s_shot_window' else duration - max(0.25, duration * 0.05)
    if safe <= 0:
        raise ValueError(f'Video window too short: {duration}')
    return [offset + safe * i / 5 for i in range(6)]


def build_one(model, episode, priority_index, shot_count):
    started = time.time()
    case_root = OUT / model / episode
    if case_root.exists():
        raise FileExistsError(f'Fresh output required: {case_root}')
    contract = contract_path(episode)
    frame_root = case_root / 'frames'
    shots, sources = [], []
    for shot_index in range(shot_count):
        shot_id = f'Shot{shot_index + 1}'
        video, offset, duration, source_frames, kind = source_for(model, episode, shot_index, shot_count)
        video_hash = sha(video)
        frame_rows = []
        for frame_id, timestamp in enumerate(sample_times(kind, duration, offset)):
            output = frame_root / shot_id / f'frame_{frame_id:06d}.jpg'
            output.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run([FFMPEG, '-v', 'error', '-threads', '1', '-ss', f'{timestamp:.9f}',
                            '-i', str(video), '-frames:v', '1', '-q:v', '2', '-y', str(output)], check=True)
            if not output.is_file() or output.stat().st_size == 0:
                raise RuntimeError(f'No frame extracted: {video} at {timestamp:.6f}s')
            frame_rows.append(dict(frame_id=frame_id, timestamp_sec=timestamp,
                                   path=str(output.resolve()), sha256=sha(output)))
        shots.append(dict(shot_id=shot_id, video_path=str(video.resolve()), frames=frame_rows))
        sources.append(dict(shot_id=shot_id, video_path=str(video.resolve()), video_sha256=video_hash,
                            source_frames=source_frames, offset_sec=offset,
                            window_duration_sec=duration, extraction_kind=kind))
    case_root.mkdir(parents=True, exist_ok=True)
    manifest_path = case_root / 'keyframes.json'
    manifest = dict(shots=shots,
                    keyframe_policy='Six uniform original-keyframe samples per generated shot; HoloCine uses fixed five-second windows.')
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    sources_path = case_root / 'source_videos.json'
    sources_path.write_text(json.dumps(dict(model=model, episode_id=episode, priority_index=priority_index,
                                            contract_path=str(contract.resolve()), contract_sha256=sha(contract),
                                            shots=sources), ensure_ascii=False, indent=2) + '\n')
    case = case_root / 'case'
    subprocess.run([sys.executable, str(ROOT / 'scripts/run_vl_vv_detection.py'), 'prepare',
                    '--manifest', str(manifest_path.resolve()), '--contract', str(contract.resolve()),
                    '--case', str(case.resolve())], check=True)
    state = dict(status='prepared', model=model, episode_id=episode, priority_index=priority_index,
                 shot_count=shot_count, keyframe_count=shot_count * 6, seconds=time.time() - started,
                 source_hashes={str(contract.resolve()): sha(contract),
                                **{row['video_path']: row['video_sha256'] for row in sources}})
    (case_root / 'prepare.json').write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')
    return dict(model=model, episode_id=episode, priority_index=priority_index, shot_count=shot_count,
                case=str(case.resolve()), keyframe_manifest=str(manifest_path.resolve()),
                source_videos=str(sources_path.resolve()), prepare_seconds=state['seconds'])


def main():
    if not os.environ.get('SLURM_JOB_ID'):
        raise RuntimeError('Run input preparation on an existing allocated compute node')
    os.environ['ROCR_VISIBLE_DEVICES'] = '-1'
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    OUT.mkdir(parents=True, exist_ok=True)
    index = read(CONTRACT_ROOT / 'index.json')
    by_rank = {row['priority_index']: row for row in index}
    selected = []
    for rank, expected_id in PRIORITY_TO_EPISODE.items():
        row = by_rank.get(rank)
        if not row or row['episode_id'] != expected_id:
            raise ValueError(f'Contract index changed at priority {rank}')
        selected.append(dict(priority_index=rank, episode_id=expected_id, shot_count=row['shots']))
    (OUT / 'selected_episodes.json').write_text(json.dumps(dict(
        selection_rule='Contract priority indices 0,1,2,5,7,8,9,10,12,13; excludes every episode in the earlier four-episode multimodel pilot.',
        source_contract_index=str((CONTRACT_ROOT / 'index.json').resolve()),
        episodes=selected), ensure_ascii=False, indent=2) + '\n')
    jobs = [(model, row['episode_id'], row['priority_index'], row['shot_count'])
            for row in selected for model in MODELS]
    results, failures = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(build_one, *job): job for job in jobs}
        for future in concurrent.futures.as_completed(futures):
            job = futures[future]
            try:
                results.append(future.result())
            except BaseException as exc:
                failures.append(dict(model=job[0], episode_id=job[1], error=str(exc)))
    (OUT / 'prepared_cases.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')
    (OUT / 'prepare_failures.json').write_text(json.dumps(failures, ensure_ascii=False, indent=2) + '\n')
    if failures:
        raise RuntimeError(f'{len(failures)} input preparation cases failed; see prepare_failures.json')
    if len(results) != 30:
        raise RuntimeError(f'Expected 30 prepared model/episode cases, got {len(results)}')
    print(json.dumps(dict(status='success', episodes=len(selected), cases=len(results),
                          shots_per_model=sum(x['shot_count'] for x in selected),
                          keyframes=sum(x['shot_count'] * 6 for x in results)), ensure_ascii=False))


if __name__ == '__main__':
    main()
