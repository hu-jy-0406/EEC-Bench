"""Detect hard cuts in the probe videos with the same rule as cinetrans_cut_audit_20261003/cuts2.py
(16 fps, 208x120 gray; cut when diff > max(12, 4 x local median)) and compare to the
configured shot boundaries (mask_info latent frames x 4)."""
import json
import subprocess
import numpy as np
import imageio_ffmpeg
from pathlib import Path

FF = imageio_ffmpeg.get_ffmpeg_exe()
W, H = 208, 120


def frames(path):
    raw = subprocess.run([FF, '-v', 'error', '-i', str(path), '-vf', f'scale={W}:{H},format=gray',
                          '-f', 'rawvideo', '-'], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, H, W).astype(np.float32)


out = {}
for cfg in sorted(Path('configs').glob('*.yaml')):
    c = json.loads(cfg.read_text())
    video = Path(c['save_file'])
    if not video.exists():
        out[cfg.stem] = dict(status='missing video')
        continue
    a = frames(video)
    d = np.abs(np.diff(a, axis=0)).mean(axis=(1, 2))
    cuts = []
    for i in range(len(d)):
        lo, hi = max(0, i - 16), min(len(d), i + 17)
        med = np.median(np.r_[d[lo:i], d[i + 1:hi]])
        if d[i] > max(12.0, 4 * med):
            cuts.append(i + 1)
    # Boundaries in pixel frames: first shot keeps the extra leading latent frame.
    bounds, acc = [], 0
    for k, n in enumerate(c['mask_info'][:-1]):
        acc += (n - 1) * 4 + 1 if k == 0 else n * 4
        bounds.append(acc)
    shot_frames = [0] + bounds + [len(a)]
    mids = [a[(shot_frames[k] + shot_frames[k + 1]) // 2] for k in range(len(shot_frames) - 1)]
    out[cfg.stem] = dict(frames=len(a), shots=len(c['mask_info']), expected_boundaries=bounds,
                         detected_cuts=cuts,
                         adjacent_mid_frame_diff=[round(float(np.abs(mids[k + 1] - mids[k]).mean()), 1)
                                                  for k in range(len(mids) - 1)])
Path('cuts.json').write_text(json.dumps(out, indent=1) + '\n')
print(json.dumps(out, indent=1))
