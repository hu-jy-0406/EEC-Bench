#!/usr/bin/env python3
"""Prepare one fresh full-pipeline case from a frozen cohort task row.

Clip models (one file per shot): six uniform timestamps per clip, unchanged.
Single-video episodes (CineTrans-DiT, HoloCine): shots are segmented at the cuts recorded at inference and
keyframes are sampled by exact frame index (scripts/episode_shot_segments.py; user decision 2026-10-05).
--legacy-nominal-keyframes restores the historical nominal 5 s grid, for reproducing old results only.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DETECTION = ROOT / 'EECBench/scripts/run_vl_vv_detection.py'
sys.path.insert(0, str(ROOT / 'EECBench/scripts'))
import episode_shot_segments as segments  # noqa: E402


def read(path):
    return json.loads(Path(path).read_text())


def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def media_tools():
    ffmpeg = shutil.which('ffmpeg')
    ffprobe = shutil.which('ffprobe')
    if ffmpeg and ffprobe:
        return ffmpeg, ffprobe, None
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe(), None, imageio_ffmpeg


def duration(video, ffprobe, imageio_ffmpeg):
    if ffprobe:
        value = subprocess.check_output([
            ffprobe, '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=nokey=1:noprint_wrappers=1', str(video)
        ], text=True)
        return float(value.strip())
    _, seconds = imageio_ffmpeg.count_frames_and_secs(str(video))
    return float(seconds)


def recorded_cut_shots(task, frames_root, ffprobe, imageio_ffmpeg):
    """Segment a single-video episode at its recorded inference cuts and extract keyframes by frame index."""
    videos = {str(Path(s['source_video']).resolve()) for s in task['shots']}
    if len(videos) != 1:
        raise ValueError(f'{task["task_id"]}: an episode-scope task must reference one video')
    video = videos.pop()
    first = task['shots'][0]
    if not Path(video).is_file() or Path(video).stat().st_size != first['source_bytes']:
        raise ValueError(f'Video source missing or size mismatch: {video}')
    record = segments.recorded_shot_starts(task['model_id'], video, first['source']['upstream_path'])
    if len(record['starts']) != len(task['shots']):
        raise ValueError(f'{task["task_id"]}: record has {len(record["starts"])} shots, task has {len(task["shots"])}')
    decoded, diff = segments.frame_changes(video)
    if decoded != record['frames']:
        raise ValueError(f'{task["task_id"]}: decoded {decoded} frames, record says {record["frames"]}')
    cuts, median = segments.measure_cuts(record['starts'], diff)
    plan = segments.keyframe_plan(record['starts'], record['frames'], cuts, median)
    targets = [frames_root / shot['shot_id'] / f'frame_{k:06d}.jpg' for shot in task['shots'] for k in range(6)]
    segments.extract_frames(video, [i for p in plan for i in p['keyframe_indices']], targets)
    digest = sha(video)
    seconds = duration(video, ffprobe, imageio_ffmpeg)
    shots = []
    for shot, part in zip(task['shots'], plan):
        start = part['start_frame']
        frames = []
        for k, index in enumerate(part['keyframe_indices']):
            path = frames_root / shot['shot_id'] / f'frame_{k:06d}.jpg'
            frames.append(dict(frame_id=k, frame_index=index, timestamp_sec=round(index / segments.FPS, 9),
                               segment_timestamp_sec=round((index - start) / segments.FPS, 9), path=str(path), sha256=sha(path)))
        shots.append(dict(
            shot_id=shot['shot_id'], video_path=video, source_scope='episode', source_shot_id=shot.get('source_shot_id'),
            source_video_sha256=digest, source_video_duration_sec=round(seconds, 9),
            segment_start_frame=start, segment_end_frame_exclusive=part['end_frame_exclusive'],
            segment_start_sec=round(start / segments.FPS, 9),
            segment_duration_sec=round((part['end_frame_exclusive'] - start) / segments.FPS, 9),
            nominal_segment_start_sec=shot.get('episode_offset_sec'), frames=frames))
    segmentation = dict(source=segments.SEGMENTATION_SOURCE, record=record['record'], shot_starts=record['starts'],
                        frame_count=record['frames'], measured_cuts=cuts, median_change=median)
    return shots, segmentation, {video: seconds}, {video: digest}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task', type=Path, required=True)
    parser.add_argument('--task-id')
    parser.add_argument('--work-root', type=Path, required=True)
    parser.add_argument('--legacy-nominal-keyframes', action='store_true',
                        help='Historical nominal 5 s grid for single-video episodes; only to reproduce old results')
    args = parser.parse_args()
    text = args.task.read_text()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = [json.loads(line) for line in text.splitlines() if line.strip()]
    if isinstance(parsed, dict) and 'shots' in parsed:
        task = parsed
    else:
        matches = [item for item in parsed if item.get('task_id') == args.task_id]
        if len(matches) != 1:
            raise ValueError(f'Expected exactly one task row for {args.task_id}, got {len(matches)}')
        task = matches[0]
    if args.task_id and task.get('task_id') != args.task_id:
        raise ValueError(f'Task ID mismatch: expected {args.task_id}, got {task.get("task_id")}')
    work = args.work_root.resolve()
    if work.exists():
        raise FileExistsError(f'Attempt directory already exists: {work}')
    work.mkdir(parents=True)
    frames_root = work / 'frames'
    frames_root.mkdir()
    case = work / 'case'
    manifest_path = work / 'input_manifest.json'
    ffmpeg, ffprobe, imageio_ffmpeg = media_tools()
    started = time.time()

    durations = {}
    source_hashes = {}
    shots = []
    cumulative_target = 0.0
    segmentation = None
    if task['source_scope'] == 'episode' and not args.legacy_nominal_keyframes:
        shots, segmentation, durations, source_hashes = recorded_cut_shots(task, frames_root, ffprobe, imageio_ffmpeg)
        cumulative_target = sum(float(s['target_duration_seconds']) for s in task['shots'])
    for shot in ([] if segmentation else task['shots']):
        video = Path(shot['source_video']).resolve()
        if not video.is_file() or video.stat().st_size != shot['source_bytes']:
            raise ValueError(f'Video source missing or size mismatch: {video}')
        key = str(video)
        if key not in durations:
            durations[key] = duration(video, ffprobe, imageio_ffmpeg)
            source_hashes[key] = sha(video)
        media_duration = durations[key]

        if shot['source_scope'] == 'shot':
            segment_start = 0.0
            segment_duration = media_duration
        else:
            segment_start = float(shot['episode_offset_sec'])
            segment_duration = min(float(shot['target_duration_seconds']), max(0.0, media_duration - segment_start))
            if segment_duration < float(shot['target_duration_seconds']) - 0.25:
                raise ValueError(f'{task["task_id"]}/{shot["shot_id"]}: source episode ends before the scheduled segment')

        if segment_duration <= 0:
            raise ValueError(f'No decodable duration for {task["task_id"]}/{shot["shot_id"]}')
        last_time = max(0.0, segment_duration - max(0.25, segment_duration * 0.05))
        frame_rows = []
        for index in range(6):
            local_ts = last_time * index / 5
            ts = segment_start + local_ts
            output = frames_root / shot['shot_id'] / f'frame_{index:06d}.jpg'
            output.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run([
                ffmpeg, '-v', 'error', '-ss', f'{ts:.9f}', '-i', str(video),
                '-frames:v', '1', '-q:v', '2', '-y', str(output)
            ], check=True)
            if not output.is_file() or output.stat().st_size == 0:
                raise RuntimeError(f'No keyframe decoded: {task["task_id"]}/{shot["shot_id"]}@{ts:.6f}s')
            frame_rows.append(dict(frame_id=index, timestamp_sec=round(ts, 9),
                                   segment_timestamp_sec=round(local_ts, 9), path=str(output), sha256=sha(output)))
        shots.append(dict(
            shot_id=shot['shot_id'], video_path=str(video), source_scope=shot['source_scope'],
            source_shot_id=shot.get('source_shot_id'), source_video_sha256=source_hashes[key],
            source_video_duration_sec=round(media_duration, 9),
            segment_start_sec=round(segment_start, 9), segment_duration_sec=round(segment_duration, 9),
            frames=frame_rows,
        ))
        cumulative_target += float(shot['target_duration_seconds'])

    if task['source_scope'] == 'episode':
        longest = max(durations.values())
        if longest < cumulative_target - 0.25 or longest > cumulative_target + 2.0:
            raise ValueError(f'{task["task_id"]}: episode video duration {longest:.3f}s does not match target schedule {cumulative_target:.3f}s')

    manifest = dict(
        schema_version='vl_vv_keyframes_v1', task_id=task['task_id'],
        episode_id=task['episode_id'], model_name=task['model_name'], variant=task['variant'],
        keyframe_policy='six uniform timestamps per generated shot clip; for episode-only outputs, six timestamps within each source-contract shot-duration interval',
        source_videos=[dict(path=path, sha256=digest, duration_sec=round(durations[path], 9)) for path, digest in source_hashes.items()],
        shots=shots,
    )
    if segmentation:
        manifest.update(schema_version=segments.MANIFEST_SCHEMA, keyframe_policy=segments.POLICY, segmentation=segmentation)
    write(manifest_path, manifest)
    command = [sys.executable, str(DETECTION), 'prepare', '--manifest', str(manifest_path),
               '--contract', task['contract_path'], '--case', str(case)]
    if args.legacy_nominal_keyframes:
        command.append('--allow-legacy-nominal-keyframes')
    subprocess.run(command, check=True)
    write(case / 'benchmark_metadata.json', dict(
        protocol='vl_vv_multimodel_case_metadata_v1', task_id=task['task_id'],
        generation_priority=task['generation_priority'], episode_id=task['episode_id'],
        model_id=task['model_id'], model_name=task['model_name'], variant=task['variant'],
        source_scope=task['source_scope'], source_metadata_path=task['source_metadata_path'],
        canonical_prompt_path=task['canonical_prompt_path'],
        model_prompt_artifacts=task['model_prompt_artifacts'],
        contract_path=task['contract_path'], contract_sha256=task['contract_sha256'],
        prepared_at_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        source_videos=[dict(path=path, sha256=digest) for path, digest in source_hashes.items()],
    ))
    write(work / 'preparation.json', dict(status='success', task_id=task['task_id'],
        seconds=round(time.time() - started, 3), case=str(case), manifest=str(manifest_path),
        source_video_count=len(source_hashes), keyframe_count=sum(len(x['frames']) for x in shots)))
    print(json.dumps(dict(status='success', case=str(case), preparation=str(work / 'preparation.json')), ensure_ascii=False))


if __name__ == '__main__':
    main()
