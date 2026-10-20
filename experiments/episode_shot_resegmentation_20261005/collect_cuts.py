#!/usr/bin/env python3
"""Recover the shot cuts used at inference for every evaluated CineTrans and HoloCine video, and measure them.

Records:
- CineTrans-DiT (official multi-shot script): metadata.json `mask.mask_info` = latent frames per shot.
  With the Wan2.1 VAE (latent 0 -> frame 0, latent t>=1 -> frames 4t-3..4t), shot k starts at frame
  4*sum(mask_info[:k]) - 3 (shot 1 at frame 0) and the video has 4*sum(mask_info) - 3 frames.
- HoloCine (official generate_episode): attempt input.json `cuts` = shot_cut_frames passed to inference.
Checks: recorded frame count == decoded frame count; HoloCine recorded video SHA-256 == evaluated file.
Measurement: per-frame mean absolute grayscale difference at 208x120; for each recorded cut the strongest
change within frames [cut-4, cut+8] and its strength relative to the video's median change.

Writes cut_records.json.  Read-only on all inputs.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import imageio_ffmpeg

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WORKLIST = ROOT / 'experiments/vl_vv_multimodel_first200_20260926/batch/worklist.jsonl'
HOLO = ROOT / 'experiments/holocine_generation_200_20260922'
W, H = 208, 120


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def frame_diffs(video):
    raw = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-threads', '2', '-i', video,
                          '-vf', f'scale={W}:{H}', '-pix_fmt', 'gray', '-f', 'rawvideo', '-'],
                         capture_output=True, check=True).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, H * W).astype(np.float32)
    return len(frames), np.abs(np.diff(frames, axis=0)).mean(axis=1)


def recorded(task):
    video = task['shots'][0]['source_video']
    upstream = Path(task['shots'][0]['source']['upstream_path'])
    if task['model_id'] == 'cinetrans':
        meta = read(upstream / 'metadata.json')
        latents = meta['mask']['mask_info']
        starts, acc = [0], 0
        for n in latents[:-1]:
            acc += n
            starts.append(4 * acc - 3)
        return dict(video=video, frames=4 * sum(latents) - 3, fps=meta['fps'], shot_starts=starts,
                    record=dict(file=str(upstream / 'metadata.json'), mask_info=latents, frame_count=meta['frame_count']))
    result = read(upstream / 'result.json')
    attempt = read(Path(result['attempt']) / 'input.json')
    return dict(video=video, frames=attempt['frames'], fps=16, shot_starts=[0] + list(attempt['cuts']),
                record=dict(file=str(Path(result['attempt']) / 'input.json'), cuts=attempt['cuts'], frame_count=attempt['frames'],
                            result_file=str(upstream / 'result.json'), recorded_video_sha256=result['video_sha256']))


def main():
    tasks = [json.loads(l) for l in WORKLIST.read_text().splitlines() if l.strip()]
    tasks = [t for t in tasks if t['model_id'] in ('cinetrans', 'holocine')]
    if len(sys.argv) > 1:
        tasks = tasks[:int(sys.argv[1])]
    out = []
    for n, task in enumerate(tasks, 1):
        rec = recorded(task)
        decoded, diff = frame_diffs(rec['video'])
        med = float(np.median(diff)) or 1e-6
        checks = dict(frame_count_matches=decoded == rec['frames'], decoded_frames=decoded,
                      shot_count_matches=len(rec['shot_starts']) == task['shot_count'])
        if 'recorded_video_sha256' in rec['record']:
            checks['video_sha256_matches'] = sha(rec['video']) == rec['record']['recorded_video_sha256']
        cuts = []
        for c in rec['shot_starts'][1:]:
            lo, hi = max(0, c - 5), min(len(diff), c + 8)          # diff[i]: change from frame i to i+1
            i = lo + int(np.argmax(diff[lo:hi]))
            cuts.append(dict(recorded_start=c, visible_start=i + 1, offset=i + 1 - c,
                             strength=round(float(diff[i]) / med, 1)))
        near = {c['visible_start'] for c in cuts} | set(rec['shot_starts'][1:])
        strong = [dict(start=i + 1, strength=round(float(diff[i]) / med, 1)) for i in range(len(diff))
                  if diff[i] / med >= 20 and all(abs(i + 1 - s) > 8 for s in near)]
        out.append(dict(task_id=task['task_id'], priority=task['generation_priority'], episode_id=task['episode_id'],
                        model_id=task['model_id'], shot_ids=[s['shot_id'] for s in task['shots']],
                        nominal_starts_sec=[s.get('episode_offset_sec') for s in task['shots']],
                        median_change=round(med, 3), checks=checks, cuts=cuts, unplanned_strong_changes=strong, **rec))
        if n % 25 == 0:
            print(n, 'done', flush=True)
    (HERE / 'cut_records.json').write_text(json.dumps(out, indent=1) + '\n')
    print('wrote', len(out))


if __name__ == '__main__':
    main()
