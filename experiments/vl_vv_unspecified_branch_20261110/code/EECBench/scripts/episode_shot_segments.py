#!/usr/bin/env python3
"""Shot segmentation of single-video episodes (CineTrans-DiT, HoloCine) at the cuts used at inference.

Every evaluation must sample keyframes for these models from the recorded inference cuts, not from the
nominal 5-second grid (user decision 2026-10-05).  Records:

- CineTrans-DiT: `mask_info` = latent frames per shot, from the Hugging Face `metadata.json` next to the
  video or from the local run config whose `save_file` is the video.  With the Wan2.1 VAE (latent 0 ->
  frame 0, latent t>=1 -> frames 4t-3..4t), shot k starts at frame 4*sum(mask_info[:k]) - 3 and the video
  has 4*sum(mask_info) - 3 frames.
- HoloCine: `cuts` (the `shot_cut_frames` passed to the official generate_episode) and `frames`, from the
  attempt `input.json` named by `result.json` next to the video; the recorded video SHA-256 must match.

Keyframes: six evenly spaced frame indices per shot over [a, b]: a = 0 for shot 1; a = recorded cut +
START_INSET for later shots (the first decoded latent group can still show the previous shot), or the frame
after a clear visible cut that lands within LATE_CUT_WINDOW frames of the recorded cut; b = shot end - 1 -
END_MARGIN.  Frames are extracted by exact index.  There is no fallback to the nominal grid: a missing or
inconsistent record is an error.
"""
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CINETRANS_LOCAL_CONFIGS = ROOT / 'experiments/cinetrans_dit_rocm_20260925/run_priority100/configs'
SEGMENTATION_SOURCE = 'inference record'
MANIFEST_SCHEMA = 'vl_vv_keyframes_v2'
FPS = 16
START_INSET = 4
END_MARGIN = 4
LATE_CUT_WINDOW = 8
CLEAR_RATIO = 10.0
MIN_CUT_CHANGE = 5.0
SAMPLE_W, SAMPLE_H = 208, 120
POLICY = (f'shots segmented at recorded inference cuts; six evenly spaced frames per shot; shot 1 from frame 0, later '
          f'shots from the recorded cut + {START_INSET} frames (or after a clear visible cut within {LATE_CUT_WINDOW} '
          f'frames); last keyframe {END_MARGIN} frames before the shot end')


def _read(path):
    return json.loads(Path(path).read_text())


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        import shutil
        path = shutil.which('ffmpeg')
        if not path:
            raise RuntimeError('No ffmpeg available (install imageio-ffmpeg or put ffmpeg on PATH)')
        return path


def _starts_from_latents(latents):
    starts, total = [0], 0
    for n in latents[:-1]:
        total += n
        starts.append(4 * total - 3)
    return starts, 4 * sum(latents) - 3


def recorded_shot_starts(model_id, video, upstream):
    """Return dict(starts, frames, record) from the inference record of one episode video."""
    video, upstream = Path(video).resolve(), Path(upstream)
    if model_id == 'cinetrans':
        meta = upstream / 'metadata.json'
        if meta.is_file():
            latents = _read(meta)['mask']['mask_info']
            starts, frames = _starts_from_latents(latents)
            return dict(starts=starts, frames=frames, record=dict(file=str(meta), mask_info=latents))
        for config in sorted(CINETRANS_LOCAL_CONFIGS.glob('*.yaml')):
            data = _read(config)
            if Path(data.get('save_file', '')).resolve() == video:
                starts, frames = _starts_from_latents(data['mask_info'])
                if frames != data['frame_num']:
                    raise ValueError(f'{config}: mask_info implies {frames} frames, frame_num is {data["frame_num"]}')
                return dict(starts=starts, frames=frames, record=dict(file=str(config), mask_info=data['mask_info']))
        raise ValueError(f'No CineTrans inference record (metadata.json or run config) for {video}')
    if model_id == 'holocine':
        result_path = upstream / 'result.json'
        if not result_path.is_file():
            raise ValueError(f'No HoloCine result.json for {video}')
        result = _read(result_path)
        attempt = Path(result['attempt']) / 'input.json'
        data = _read(attempt)
        if sha256(video) != result['video_sha256']:
            raise ValueError(f'{video} does not match the recorded HoloCine video SHA-256')
        return dict(starts=[0] + list(data['cuts']), frames=data['frames'],
                    record=dict(file=str(attempt), cuts=data['cuts'], result_file=str(result_path),
                                recorded_video_sha256=result['video_sha256']))
    raise ValueError(f'No recorded-cut segmentation is defined for model {model_id!r}')


def frame_changes(video):
    """(decoded frame count, mean absolute grayscale change between consecutive frames at 208x120)."""
    raw = subprocess.run([ffmpeg(), '-v', 'error', '-threads', '2', '-i', str(video), '-vf', f'scale={SAMPLE_W}:{SAMPLE_H}',
                          '-pix_fmt', 'gray', '-f', 'rawvideo', '-'], capture_output=True, check=True).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, SAMPLE_H * SAMPLE_W).astype(np.float32)
    return len(frames), np.abs(np.diff(frames, axis=0)).mean(axis=1)


def measure_cuts(starts, diff):
    """Strongest change near each recorded cut; returns (cuts, median change)."""
    median = float(np.median(diff)) or 1e-6
    cuts = []
    for c in starts[1:]:
        lo, hi = max(0, c - 5), min(len(diff), c + LATE_CUT_WINDOW)
        i = lo + int(np.argmax(diff[lo:hi]))
        cuts.append(dict(recorded_start=c, visible_start=i + 1, offset=i + 1 - c, strength=round(float(diff[i]) / median, 1)))
    return cuts, round(median, 3)


def keyframe_plan(starts, total_frames, cuts, median_change):
    """Six keyframe indices per recorded shot segment."""
    ends = list(starts[1:]) + [total_frames]
    plan = []
    for k, (s, e) in enumerate(zip(starts, ends)):
        a = s if k == 0 else s + START_INSET
        if k > 0:
            cut = cuts[k - 1]
            clear = cut['strength'] >= CLEAR_RATIO and cut['strength'] * median_change >= MIN_CUT_CHANGE
            if clear and s <= cut['visible_start'] <= s + LATE_CUT_WINDOW:
                a = max(a, cut['visible_start'] + 1)
        b = e - 1 - END_MARGIN
        if b - a < 5:
            raise ValueError(f'Shot segment [{s}, {e}) is too short for six keyframes')
        plan.append(dict(start_frame=s, end_frame_exclusive=e, keyframe_indices=[round(a + j * (b - a) / 5) for j in range(6)]))
    return plan


def extract_frames(video, indices, targets):
    """Write frame `indices[i]` of `video` to `targets[i]` (JPEG, -q:v 2), selecting by exact frame index."""
    order = sorted(range(len(indices)), key=lambda i: indices[i])
    unique = sorted(set(indices))
    if len(unique) != len(indices):
        raise ValueError('Keyframe indices must be distinct')
    tmp = Path(targets[0]).parent.parent / '_extract_tmp'
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        expr = '+'.join(f'eq(n\\,{i})' for i in unique)
        subprocess.run([ffmpeg(), '-v', 'error', '-y', '-threads', '2', '-i', str(video), '-vf', f'select={expr}',
                        '-vsync', '0', '-q:v', '2', str(tmp / 'n_%04d.jpg')], check=True)
        files = sorted(tmp.glob('n_*.jpg'))
        if len(files) != len(unique):
            raise RuntimeError(f'{video}: extracted {len(files)} frames, expected {len(unique)}')
        for rank, i in enumerate(order):
            Path(targets[i]).parent.mkdir(parents=True, exist_ok=True)
            files[rank].replace(targets[i])
    finally:
        for leftover in tmp.glob('*'):
            leftover.unlink()
        tmp.rmdir()


def is_record_segmented(manifest):
    """True when the manifest has no single-video episode shots or was segmented at recorded cuts."""
    episode_shots = [s for s in manifest.get('shots', []) if s.get('source_scope') == 'episode']
    if not episode_shots:
        return True
    return (manifest.get('segmentation') or {}).get('source') == SEGMENTATION_SOURCE and all(
        'segment_start_frame' in s and all('frame_index' in f for f in s.get('frames', [])) for s in episode_shots)


def require_record_segmentation(manifest, allow_legacy=False, where='case'):
    if is_record_segmented(manifest) or allow_legacy:
        return
    raise ValueError(f'{where}: episode-video keyframes were sampled on the nominal 5 s grid. Evaluations must use '
                     'keyframes segmented at the recorded inference cuts (scripts/episode_shot_segments.py); pass '
                     '--allow-legacy-nominal-keyframes only to reproduce historical results.')
