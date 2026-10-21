#!/usr/bin/env python3
"""Live check after removing V-V transition_realization and narrowing part_of_entity (2026-10-21).

Reruns the default branch chain (discovery v5 -> review v6 -> scoring v5) with
--mode from-registry on three frozen cases (#002, #032, #047 Wan2.1) of
experiments/vl_vv_branch_split_20261009; image labels on (default).
Checks that V-V detection validates without transition_realization and how
worn items are labelled.

Usage (inside an existing allocation, API only):
  python run_jobs.py SET STREAM NSTREAMS     SET = check
"""
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PIPELINE = ROOT / 'scripts/run_vl_vv_pipeline.py'
FIRST200 = ROOT / 'experiments/vl_vv_multimodel_first200_run02'
CASES = {'p002_wan21': 'wan21/priority_002_74S1Iw0gJrA_s00006_n4_clean_v2',
         'p032_wan22': 'wan22/priority_032_DwiiGopbVNQ_s00017_n6_clean_v2',
         'p047_wan21': 'wan21/priority_047_vT7JOS_cHDE_s00055_n8_clean_v2'}


def case_dir(key):
    return FIRST200 / CASES[key] / 'attempt_01/work/case'


def jobs(name):
    if name == 'check':
        return [(HERE / 'runs' / key, key) for key in CASES]
    raise ValueError(f'Unknown job set {name}')


def main():
    name, stream, streams = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    events = (HERE / f'events_{name}_stream{stream}.jsonl').open('a')
    for index, (out, key) in enumerate(jobs(name)):
        if index % streams != stream or out.exists():
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        log = out.parent / f'{out.name}.log'
        start = time.time()
        with log.open('w') as stream_log:
            code = subprocess.run([sys.executable, str(PIPELINE), '--case', str(case_dir(key)), '--output', str(out),
                                   '--mode', 'from-registry'], stdout=stream_log, stderr=subprocess.STDOUT).returncode
        events.write(json.dumps(dict(job=str(out.relative_to(HERE)), case=key, exit_code=code,
                                     seconds=round(time.time() - start, 1), finished=time.time())) + '\n')
        events.flush()


if __name__ == '__main__':
    main()
