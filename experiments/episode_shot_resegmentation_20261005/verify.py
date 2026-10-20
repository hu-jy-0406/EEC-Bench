#!/usr/bin/env python3
"""Verify re-segmented keyframes: exact frame identity (sample of videos) and position relative to visible cuts (all videos)."""
import json, random, subprocess
from pathlib import Path
import numpy as np, imageio_ffmpeg
from PIL import Image

HERE = Path(__file__).resolve().parent
W, H = 208, 120
records = {r['task_id']: r for r in json.loads((HERE / 'cut_records.json').read_text())}
segments = json.loads((HERE / 'segments.json').read_text())

def decode(video):
    raw = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-threads', '2', '-i', video, '-vf', f'scale={W}:{H}',
                          '-pix_fmt', 'gray', '-f', 'rawvideo', '-'], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, H * W).astype(np.float32)

random.seed(7)
sample = random.sample(segments, 12)
identity = dict(checked=0, exact=0, worst=[])
for seg in sample:
    frames = decode(records[seg['task_id']]['video'])
    man = json.loads(Path(seg['manifest']).read_text())
    for shot in man['shots']:
        for f in shot['frames']:
            img = np.asarray(Image.open(f['path']).convert('L').resize((W, H), Image.BILINEAR), np.float32).reshape(-1)
            err = np.abs(frames - img).mean(axis=1)
            best = int(np.argmin(err))
            identity['checked'] += 1
            identity['exact'] += best == f['frame_index']
            if best != f['frame_index']:
                identity['worst'].append((seg['task_id'], shot['shot_id'], f['frame_index'], best, round(float(err[f['frame_index']] - err[best]), 3)))

placement = {m: dict(clear_cuts=0, new_after_visible=0, old_after_visible=0) for m in ('cinetrans', 'holocine')}
for seg in segments:
    rec = records[seg['task_id']]
    for k, cut in enumerate(rec['cuts'], start=1):
        if cut['strength'] < 10 or cut['strength'] * rec['median_change'] < 5.0:
            continue
        p = placement[rec['model_id']]
        p['clear_cuts'] += 1
        new_f0 = seg['shots'][k]['keyframe_indices'][0]
        old_f0 = round(rec['nominal_starts_sec'][k] * 16)
        p['new_after_visible'] += new_f0 >= cut['visible_start']
        p['old_after_visible'] += old_f0 >= cut['visible_start']
out = dict(frame_identity=identity, first_keyframe_vs_visible_cut=placement)
(HERE / 'verification.json').write_text(json.dumps(out, indent=1) + '\n')
print(json.dumps(dict(frame_identity={k: v for k, v in identity.items() if k != 'worst'}, mismatches=identity['worst'][:5], placement=placement), indent=1))
