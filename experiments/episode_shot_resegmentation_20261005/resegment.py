#!/usr/bin/env python3
"""Re-segment every evaluated CineTrans/HoloCine episode video at its recorded inference cuts and resample keyframes.

Segments (from cut_records.json): shot k = frames [start_k, start_{k+1}), last shot to the end of the video.
Keyframes: six frames evenly spaced over [a, b] with
  a = start_k for the first shot (frame 0 kept, so first-frame defects stay visible),
  a = start_k + 4 for later shots (skips the first decoded latent group: in HoloCine the first 0-3 frames
      after a recorded cut still show the previous shot because each latent decodes into 4 frames),
  b = end_k - 1 - 4 (0.25 s before the segment's last frame, like the original end margin).
Frames are extracted by exact frame index (one ffmpeg pass per video, -q:v 2 like the original sampler).
Writes keyframes/<model>/<episode_id>/ShotN/frame_00000K.jpg, a vl_vv_keyframes_v2 manifest per video,
and segments.json.  Originals are only read.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

HERE = Path(__file__).resolve().parent
START_INSET = 4      # frames skipped after a recorded cut (one VAE latent group)
END_MARGIN = 4       # frames kept clear before a segment's last frame
LATE_CUT_WINDOW = 8  # a clear visible cut up to 8 frames after the recorded cut moves the first keyframe past it
MIN_CUT_CHANGE = 5.0 # minimum mean absolute gray-level change for a visible cut to count as clear
FPS = 16


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def plan(rec):
    starts = rec['shot_starts']
    ends = starts[1:] + [rec['frames']]
    shots = []
    for k, (s, e) in enumerate(zip(starts, ends)):
        a = s if k == 0 else s + START_INSET
        if k > 0:
            cut = rec['cuts'][k - 1]
            clear = cut['strength'] >= 10 and cut['strength'] * rec['median_change'] >= MIN_CUT_CHANGE
            if clear and s <= cut['visible_start'] <= s + LATE_CUT_WINDOW:
                a = max(a, cut['visible_start'] + 1)
        b = e - 1 - END_MARGIN
        idx = [round(a + j * (b - a) / 5) for j in range(6)]
        shots.append(dict(shot_id=rec['shot_ids'][k], start_frame=s, end_frame_exclusive=e,
                          start_sec=round(s / FPS, 4), end_sec=round(e / FPS, 4), keyframe_indices=idx))
    return shots


def extract(video, indices, folder):
    folder.mkdir(parents=True, exist_ok=True)
    flat = sorted(set(i for shot in indices for i in shot))
    expr = '+'.join(f'eq(n\\,{i})' for i in flat)
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-y', '-threads', '2', '-i', video,
                    '-vf', f'select={expr}', '-vsync', '0', '-q:v', '2', str(folder / 'n_%04d.jpg')], check=True)
    files = sorted(folder.glob('n_*.jpg'))
    if len(files) != len(flat):
        raise RuntimeError(f'{video}: extracted {len(files)} frames, expected {len(flat)}')
    return dict(zip(flat, files))


def main():
    records = json.loads((HERE / 'cut_records.json').read_text())
    if len(sys.argv) > 1:
        records = records[:int(sys.argv[1])]
    summary = []
    for n, rec in enumerate(records, 1):
        shots = plan(rec)
        root = HERE / 'keyframes' / rec['model_id'] / rec['episode_id']
        by_index = extract(rec['video'], [s['keyframe_indices'] for s in shots], root / '_tmp')
        manifest_shots = []
        for shot in shots:
            frames = []
            for fid, idx in enumerate(shot['keyframe_indices']):
                target = root / shot['shot_id'] / f'frame_{fid:06d}.jpg'
                target.parent.mkdir(parents=True, exist_ok=True)
                by_index[idx].replace(target) if not target.exists() else None
                if not target.exists():
                    raise RuntimeError(f'missing {target}')
                frames.append(dict(frame_id=fid, frame_index=idx, timestamp_sec=round(idx / FPS, 4),
                                   segment_timestamp_sec=round((idx - shot['start_frame']) / FPS, 4),
                                   path=str(target), sha256=sha(target)))
            manifest_shots.append(dict(shot_id=shot['shot_id'], video_path=rec['video'], source_scope='episode',
                                       segment_start_frame=shot['start_frame'], segment_end_frame_exclusive=shot['end_frame_exclusive'],
                                       segment_start_sec=shot['start_sec'], segment_duration_sec=round((shot['end_frame_exclusive'] - shot['start_frame']) / FPS, 4),
                                       frames=frames))
        # duplicated indices (none expected) would leave files in _tmp
        leftovers = list((root / '_tmp').glob('*'))
        for f in leftovers:
            f.unlink()
        (root / '_tmp').rmdir()
        manifest = dict(schema_version='vl_vv_keyframes_v2', task_id=rec['task_id'], episode_id=rec['episode_id'],
                        model_id=rec['model_id'], source_videos=[dict(path=rec['video'], frame_count=rec['frames'], fps=FPS)],
                        segmentation=dict(source='inference record', record=rec['record'], shot_starts=rec['shot_starts']),
                        keyframe_policy=f'six evenly spaced frames per recorded shot segment; shot 1 from frame 0, later shots from '
                                        f'the recorded cut + {START_INSET} frames; last keyframe {END_MARGIN} frames before the segment end',
                        shots=manifest_shots)
        (root / 'keyframe_manifest.json').write_text(json.dumps(manifest, indent=1) + '\n')
        summary.append(dict(task_id=rec['task_id'], model_id=rec['model_id'], episode_id=rec['episode_id'],
                            manifest=str(root / 'keyframe_manifest.json'), shots=shots, unused_duplicates=len(leftovers)))
        if n % 25 == 0:
            print(n, 'done', flush=True)
    (HERE / 'segments.json').write_text(json.dumps(summary, indent=1) + '\n')
    print('wrote', len(summary))


if __name__ == '__main__':
    main()
