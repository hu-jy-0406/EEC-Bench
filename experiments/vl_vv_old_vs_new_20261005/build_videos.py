#!/usr/bin/env python3
"""Make one web-playable MP4 per case from the evaluated generated video(s), plus shot timing.

Per-shot models (Wan2.1, Wan2.2, StoryMem): the shot clips are concatenated in
manifest order.  Episode models (CineTrans, HoloCine): the single episode video
is re-encoded whole.  Same resolution and frame rate, H.264 CRF 26, no audio,
faststart.  Originals are only read.  Writes page/video/<case>.mp4 and
page/video/timing.json (shot start times and keyframe times in the web video).
"""
import json
import subprocess
from pathlib import Path

import imageio_ffmpeg

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / 'page/video'
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
HISTORICAL = [ROOT / 'experiments/vl_vv_multimodel_first200_run02/final_scores.jsonl',
              ROOT / 'experiments/vl_vv_multimodel_first200_run02_b/final_scores.jsonl']
ENCODE = ['-c:v', 'libx264', '-preset', 'medium', '-crf', '26', '-pix_fmt', 'yuv420p',
          '-movflags', '+faststart', '-an', '-threads', '4']


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = {}
    for path in HISTORICAL:
        for line in path.read_text().splitlines():
            row = json.loads(line)
            rows[(row['generation_priority'], row['model_id'])] = Path(row['output_dir']).parent / 'work/case/raw_manifest.json'
    timing = {}
    for case in json.loads((HERE / 'reference.json').read_text())['cases']:
        key = case['key']
        manifest = json.loads(rows[(case['priority'], case['model'])].read_text())
        shots = manifest['shots']
        target = OUT / f'{key}.mp4'
        if shots[0]['source_scope'] == 'shot':
            inputs = [shot['video_path'] for shot in shots]
            durations = [shot['source_video_duration_sec'] for shot in shots]
            starts = [sum(durations[:i]) for i in range(len(shots))]
            command = [FFMPEG, '-y', '-v', 'error']
            for path in inputs:
                command += ['-i', path]
            graph = ''.join(f'[{i}:v:0]' for i in range(len(inputs))) + f'concat=n={len(inputs)}:v=1:a=0[v]'
            command += ['-filter_complex', graph, '-map', '[v]'] + ENCODE + [str(target)]
            sources = [dict(path=p, sha256=s['source_video_sha256']) for p, s in zip(inputs, shots)]
            total = sum(durations)
        else:
            source = shots[0]['video_path']
            starts = [shot['segment_start_sec'] for shot in shots]
            command = [FFMPEG, '-y', '-v', 'error', '-i', source] + ENCODE + [str(target)]
            sources = [dict(path=source, sha256=shots[0]['source_video_sha256'])]
            total = shots[0]['source_video_duration_sec']
        subprocess.run(command, check=True)
        timing[key] = dict(
            scope=shots[0]['source_scope'], duration=round(total, 3),
            shots=[dict(shot_id=s['shot_id'], start=round(t, 3)) for s, t in zip(shots, starts)],
            frames={s['shot_id']: {str(f['frame_id']): round(t + f['segment_timestamp_sec'], 3) for f in s['frames']}
                    for s, t in zip(shots, starts)},
            sources=sources, bytes=target.stat().st_size)
        print(key, round(target.stat().st_size / 1e6, 2), 'MB', flush=True)
    (OUT / 'timing.json').write_text(json.dumps(timing, indent=1) + '\n')
    print('total MB', round(sum(t['bytes'] for t in timing.values()) / 1e6, 2))


if __name__ == '__main__':
    main()
