#!/usr/bin/env python3
"""Replace rounded clip durations with exact frame-count durations for concatenated clip videos."""
import json
import subprocess
from pathlib import Path

path = Path(__file__).resolve().parent / 'page/video/timing.json'
timing = json.loads(path.read_text())
for key, v in timing.items():
    if v['scope'] != 'shot':
        continue
    acc = 0.0
    for src, shot in zip(v['sources'], v['shots']):
        out = subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-count_packets',
                                       '-show_entries', 'stream=nb_read_packets,r_frame_rate', '-of', 'json', src['path']])
        s = json.loads(out)['streams'][0]
        num, den = map(int, s['r_frame_rate'].split('/'))
        old = shot['start']
        shot['start'] = round(acc, 4)
        for fid, ts in v['frames'][shot['shot_id']].items():
            v['frames'][shot['shot_id']][fid] = round(ts - old + acc, 4)
        acc += int(s['nb_read_packets']) * den / num
    v['duration'] = round(acc, 4)
path.write_text(json.dumps(timing, indent=1) + '\n')
print({k: (v['scope'], v['duration']) for k, v in timing.items()})
