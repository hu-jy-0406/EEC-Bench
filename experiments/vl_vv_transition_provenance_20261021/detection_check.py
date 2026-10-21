#!/usr/bin/env python3
"""#032 Wan2.2 V-L detection: current definitions ("does not conflict with") vs the same
definitions with only the 2026-10-20 "satisfies" sentence restored (definitions_satisfies_variant.txt).
Image labels on (default) in both arms. Usage: python detection_check.py STREAM NSTREAMS
"""
import json, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'scripts')); sys.path.insert(0, str(HERE))
import vl_vv_branch_common as common  # noqa: E402
import run_vl_vv_branch_detection as detection  # noqa: E402
from run_jobs import case_dir  # noqa: E402
CURRENT = common.DEFINITIONS_PATH
ARMS = {'conflict': CURRENT, 'satisfies': HERE / 'definitions_satisfies_variant.txt'}

def main():
    stream, streams = int(sys.argv[1]), int(sys.argv[2])
    jobs = [(arm, k) for arm in ARMS for k in ('a', 'b', 'c')]
    events = (HERE / f'events_detection_stream{stream}.jsonl').open('a')
    for index, (arm, k) in enumerate(jobs):
        out = HERE / 'runs/detection_check' / arm / f'run_{k}' / 'vl_detection'
        if index % streams != stream or out.exists():
            continue
        common.DEFINITIONS_PATH = ARMS[arm]
        out.parent.mkdir(parents=True, exist_ok=True)
        start, error = time.time(), None
        try:
            detection.run(case_dir('p032_wan22'), out, 'vl')
        except Exception as exc:
            error = str(exc)[:500]
        events.write(json.dumps(dict(arm=arm, run=k, error=error, seconds=round(time.time() - start, 1))) + '\n')
        events.flush()

if __name__ == '__main__':
    main()
