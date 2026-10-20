#!/usr/bin/env python3
"""Motion and encoding audit of the first-200 multimodel source videos.

Part 1 (all 1,000 episode videos): per-shot motion from decoded frames.
  Frames are decoded at 8 fps, 208x120 grayscale. Per shot:
  - mad: mean absolute difference between consecutive sampled frames (0-255)
  - first_last: mean absolute difference between the shot's first and last frame
  Episode-level videos (CineTrans, HoloCine) are split at the cumulative
  per-shot target durations, the same time split the evaluator uses; frame
  pairs that straddle a cut are excluded.
Part 2 (re-encode control): a fixed random sample of Wan2.2 and StoryMem shots
  is decoded and re-saved exactly like HoloCine's official save_video
  (imageio writer, fps=16, quality=5). Bitrate and motion are compared before
  and after, to separate the encoding setting from content motion.
No model calls; CPU only. Source videos are read only.
"""
import json
import random
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import imageio.v2 as imageio
import imageio_ffmpeg
import numpy as np

HERE = Path(__file__).resolve().parent
WORKLIST = HERE.parent / 'vl_vv_multimodel_first200_20260926/batch/worklist.jsonl'
FF = imageio_ffmpeg.get_ffmpeg_exe()
W, H, FPS = 208, 120, 8


def frames(path):
    out = subprocess.run([FF, '-v', 'error', '-i', str(path), '-vf', f'fps={FPS},scale={W}:{H},format=gray',
                          '-f', 'rawvideo', '-'], capture_output=True, check=True).stdout
    return np.frombuffer(out, np.uint8).reshape(-1, H, W).astype(np.float32)


def shot_stats(arr):
    if len(arr) < 2:
        return None
    diffs = np.abs(np.diff(arr, axis=0)).mean(axis=(1, 2))
    return dict(mad=float(diffs.mean()), first_last=float(np.abs(arr[-1] - arr[0]).mean()), n=int(len(arr)))


def task_motion(task):
    shots = task['shots']
    out = []
    if task['shots'][0]['source_scope'] == 'shot':
        for s in shots:
            out.append(shot_stats(frames(s['source_video'])))
    else:
        arr = frames(shots[0]['source_video'])
        start = 0.0
        for s in shots:
            end = start + s['target_duration_seconds']
            a, b = int(round(start * FPS)), int(round(end * FPS))
            out.append(shot_stats(arr[a:b]))
            start = end
    return dict(model_id=task['model_id'], priority=task['generation_priority'], shots=out)


def reencode(item):
    model, path = item
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / 'q5.mp4'
        reader = imageio.get_reader(path)
        writer = imageio.get_writer(target, fps=16, quality=5)
        n = 0
        for frame in reader:
            writer.append_data(frame)
            n += 1
        reader.close()
        writer.close()
        secs = n / 16
        before, after = shot_stats(frames(path)), shot_stats(frames(target))
        return dict(model_id=model, source=path, frames=n,
                    mbps_before=Path(path).stat().st_size * 8 / secs / 1e6,
                    mbps_after=target.stat().st_size * 8 / secs / 1e6,
                    mad_before=before['mad'], mad_after=after['mad'],
                    first_last_before=before['first_last'], first_last_after=after['first_last'])


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 16
    tasks = [json.loads(line) for line in WORKLIST.read_text().splitlines() if line.strip()]
    with ProcessPoolExecutor(workers) as pool:
        motion = list(pool.map(task_motion, tasks, chunksize=4))
    (HERE / 'motion_per_task.json').write_text(json.dumps(motion) + '\n')
    rng = random.Random(20261002)
    sample = []
    for model in ('wan22', 'storymem'):
        paths = sorted({s['source_video'] for t in tasks if t['model_id'] == model for s in t['shots']})
        sample += [(model, p) for p in rng.sample(paths, 40)]
    with ProcessPoolExecutor(workers) as pool:
        control = list(pool.map(reencode, sample))
    (HERE / 'reencode_control.json').write_text(json.dumps(control, indent=1) + '\n')
    print('done', len(motion), len(control))


if __name__ == '__main__':
    main()
