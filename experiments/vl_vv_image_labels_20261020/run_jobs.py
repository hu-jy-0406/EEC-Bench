#!/usr/bin/env python3
"""Live check of shot/frame image labels (default on since 2026-10-20).

Reruns the default branch chain (discovery v5 -> review v6 -> scoring v5) with
--mode from-registry on the frozen #002 Wan2.1 case used in
experiments/vl_vv_branch_split_20261009 (runs/main/run_a|run_b, unlabeled
images). Only the image labels differ from those runs.

Usage (inside an existing allocation, API only):
  python run_jobs.py SET STREAM NSTREAMS     SET = p002
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
CASES = {'p002_wan21': 'wan21/priority_002_74S1Iw0gJrA_s00006_n4_clean_v2'}


def case_dir(key):
    return FIRST200 / CASES[key] / 'attempt_01/work/case'


def jobs(name):
    if name == 'p002':
        return [(HERE / 'runs' / f'run_{k}' / 'p002_wan21', 'p002_wan21') for k in ('a', 'b', 'c')]
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
