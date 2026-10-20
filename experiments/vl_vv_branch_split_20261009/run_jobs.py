#!/usr/bin/env python3
"""Live validation of the branch-separated chain (discovery v5 -> review v6 -> scoring v5).

Each job runs scripts/run_vl_vv_pipeline.py --mode from-registry (default chain) on a
frozen clip-model case of the 14-video reference set
(experiments/vl_vv_v2_results_20261005/results_reference.json); episode-video cases
(CineTrans/HoloCine) are excluded because their frozen keyframes use the retired grid.

Usage (inside an existing allocation, API only):
  python run_jobs.py SET STREAM NSTREAMS     SET = smoke | smoke2 | main
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
CASES = {
    'p002_wan21': 'wan21/priority_002_74S1Iw0gJrA_s00006_n4_clean_v2',
    'p014_wan21': 'wan21/priority_014_MTYQT6fSzaE_s00091_n4_clean_v2',
    'p014_storymem': 'storymem/priority_014_MTYQT6fSzaE_s00091_n4_clean_v2',
    'p028_wan22': 'wan22/priority_028_N39I1LM-HGY_s00208_n8_clean_v3_alt8',
    'p032_wan22': 'wan22/priority_032_DwiiGopbVNQ_s00017_n6_clean_v2',
    'p047_wan21': 'wan21/priority_047_vT7JOS_cHDE_s00055_n8_clean_v2',
    'p047_storymem': 'storymem/priority_047_vT7JOS_cHDE_s00055_n8_clean_v2',
    'p069_wan21': 'wan21/priority_069_pwSkfvXD_ug_s00037_n4_clean_v2',
}


def case_dir(key):
    return FIRST200 / CASES[key] / 'attempt_01/work/case'


def jobs(name):
    if name == 'smoke':
        return [(HERE / 'runs/smoke' / 'p002_wan21', 'p002_wan21')]
    if name == 'smoke2':  # after the grouped contract-checking template (template v2)
        return [(HERE / 'runs/smoke2' / key, key) for key in ('p002_wan21', 'p047_wan21')]
    if name == 'main':
        return [(HERE / 'runs/main' / f'run_{k}' / key, key) for k in ('a', 'b') for key in CASES]
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
