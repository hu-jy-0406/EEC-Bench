#!/usr/bin/env python3
"""Targeted check of the in-place review-v5 fix ("the requirement is the wording, not another shot's depiction").

Re-reviews (review only, fixed v5, two repeats) the nine frozen discovery outputs that contain the labels the
pre-fix review v5 over-confirmed from an earlier shot's look (jacket pattern) and the labels the entity rule
recovered (trousers, coat, gun, shirt).  Output: runs/fix_check/rep_K/SET/CASE/issue_review.
Usage (inside an existing allocation): python fix_check.py STREAM NSTREAMS [OUTPUT_NAME]
(OUTPUT_NAME defaults to fix_check; fix_check2 holds the re-run after the second in-place sentence.)
"""
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CORE = ROOT / 'experiments/vl_vv_core_review_20261006/runs'
REVIEW = ROOT / 'scripts/run_vl_vv_issue_review.py'
OLD_NEW = ROOT / 'experiments/vl_vv_old_vs_new_20261005/runs/v2'
RESULTS = ROOT / 'experiments/vl_vv_v2_results_20261005/runs/v2'
SOURCES = {'clip/run_a/p069_wan21': RESULTS / 'run_a/p069_wan21', 'clip/run_b/p069_wan21': RESULTS / 'run_b/p069_wan21',
           'clip/run_c/p002_wan21': OLD_NEW / 'run_c/p002_wan21',
           'split/fresh_2/p069_wan21': CORE / 'split/fresh_2/p069_wan21', 'split/fresh_3/p069_wan21': CORE / 'split/fresh_3/p069_wan21',
           'split/fresh_1/p002_wan21': CORE / 'split/fresh_1/p002_wan21', 'split/fresh_2/p002_wan21': CORE / 'split/fresh_2/p002_wan21',
           'v2fresh/fresh_1/p069_wan21': CORE / 'labeling/fresh_1/p069_wan21',
           'v2fresh/fresh_2/p069_wan21': CORE / 'labeling/fresh_2/p069_wan21'}


def case_of(source):
    run = source / 'run.json'
    return json.loads(run.read_text())['case']


def main():
    stream, streams = int(sys.argv[1]), int(sys.argv[2])
    name = sys.argv[3] if len(sys.argv) > 3 else 'fix_check'
    events = (HERE / f'events_{name}_stream{stream}.jsonl').open('a')
    jobs = [(k, key, source) for k in (1, 2) for key, source in SOURCES.items()]
    for index, (k, key, source) in enumerate(jobs):
        out = HERE / 'runs' / name / f'rep_{k}' / key
        if index % streams != stream or out.exists():
            continue
        out.mkdir(parents=True)
        command = [sys.executable, str(REVIEW), '--case', case_of(source), '--issues', str(source / 'issue_discovery/result.json'),
                   '--output', str(out / 'issue_review'), '--review-protocol', 'v5']
        start = time.time()
        with (out / 'issue_review.log').open('w') as log:
            code = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT).returncode
        row = dict(out=str(out.relative_to(HERE)), exit_code=code, seconds=round(time.time() - start, 3))
        events.write(json.dumps(row) + '\n')
        events.flush()


if __name__ == '__main__':
    main()
