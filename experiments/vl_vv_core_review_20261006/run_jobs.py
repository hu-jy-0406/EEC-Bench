#!/usr/bin/env python3
"""Runs for the core-problem review test (review v4) and the labeling retest.

Phase 1 (independent jobs):
- labeling/fresh_K/CASE: fresh discovery v2 (new V-L / V-V definitions) + review v2 (original review logic) +
  scoring v3 on #014 and #069 Wan2.1, K = 1..3 (run_vl_vv_pipeline.py from-registry);
- fixed/PROTOCOL_K/RUN/CASE: review + scoring v3 on an existing discovery result (fixed candidates):
  v4_1 on all 24 clip-model runs; v4_2, v4_3 and v2_3 on the four target runs (#014 run_c, #069 runs a-c);
  v4_1..3 and v2_2..3 on #068 HoloCine run_a (I5).  The original reviews count as v2_1 and the earlier
  repeat (vl_vv_partial_review_20261006/runs_v2_repeat) as v2_2.
Phase 2: fresh_v4/fresh_K/CASE: review v4 + scoring v3 on the phase-1 fresh discoveries; labeling/v1_rerun_K/
p069_wan21: two old-pipeline runs (discovery v1 -> review v1 -> scoring v2) so that #069 has three old-pipeline
runs like #014 (historical + two reruns from vl_vv_old_vs_new_20261005); split/fresh_K/CASE: discovery v3 (one
label per issue, linked V-V / V-L pairs) + review v4 + scoring v3 on #002, #014, #069 Wan2.1 and #028 Wan2.2.

#068 HoloCine's case uses the historical nominal-grid keyframes on which I5 was proposed, so its review runs with
--allow-legacy-nominal-keyframes: a fixed-input rule test on the historical candidate, not a new evaluation.
Usage (inside an existing allocation): python run_jobs.py PHASE STREAM NSTREAMS
"""
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PIPELINE = ROOT / 'scripts/run_vl_vv_pipeline.py'
REVIEW = ROOT / 'scripts/run_vl_vv_issue_review.py'
SCORING = ROOT / 'scripts/run_vl_vv_episode_scoring.py'
OLD_NEW = ROOT / 'experiments/vl_vv_old_vs_new_20261005/runs/v2'
RESULTS = ROOT / 'experiments/vl_vv_v2_results_20261005/runs/v2'
CLIP_MODELS = ('wan21', 'wan22', 'storymem')
TARGETS = [(OLD_NEW, 'run_c', 'p014_wan21'), (RESULTS, 'run_a', 'p069_wan21'),
           (RESULTS, 'run_b', 'p069_wan21'), (RESULTS, 'run_c', 'p069_wan21')]
HOLOCINE = (OLD_NEW, 'run_a', 'p068_holocine')
FRESH_CASES = [(OLD_NEW, 'run_a', 'p014_wan21'), (RESULTS, 'run_a', 'p069_wan21')]
SPLIT_CASES = [(OLD_NEW, 'run_a', 'p002_wan21'), (OLD_NEW, 'run_a', 'p014_wan21'),
               (RESULTS, 'run_a', 'p069_wan21'), (OLD_NEW, 'run_a', 'p028_wan22')]


def case_of(source):
    return json.loads((source / 'run.json').read_text())['case']


def review_job(source, run, case_name, protocol, k, legacy=False, base='fixed'):
    out = HERE / 'runs' / base / f'{protocol}_{k}' / run / case_name
    review = [sys.executable, str(REVIEW), '--case', case_of(source), '--issues', str(source / 'issue_discovery/result.json'),
              '--output', str(out / 'issue_review'), '--review-protocol', protocol]
    if legacy:
        review.append('--allow-legacy-nominal-keyframes')
    scoring = [sys.executable, str(SCORING), '--review', str(out / 'issue_review/result.json'), '--output', str(out / 'episode_scoring')]
    return dict(out=out, steps=[('issue_review', review), ('episode_scoring', scoring)])


def phase1():
    jobs = []
    for k in (1, 2, 3):
        for base, run, case_name in FRESH_CASES:
            out = HERE / 'runs/labeling' / f'fresh_{k}' / case_name
            jobs.append(dict(out=out, steps=[('pipeline', [sys.executable, str(PIPELINE), '--case', case_of(base / run / case_name),
                                                           '--output', str(out), '--mode', 'from-registry',
                                                           '--discovery-protocol', 'v2', '--review-protocol', 'v2'])],
                             make_parent_only=True))
    for base in (OLD_NEW, RESULTS):
        for run in sorted(p for p in base.iterdir() if p.is_dir()):
            for source in sorted(p for p in run.iterdir() if p.is_dir() and p.name.endswith(CLIP_MODELS)):
                jobs.append(review_job(source, run.name, source.name, 'v4', 1))
    for base, run, case_name in TARGETS:
        for protocol, k in (('v4', 2), ('v4', 3), ('v2', 3)):
            jobs.append(review_job(base / run / case_name, run, case_name, protocol, k))
    base, run, case_name = HOLOCINE
    for protocol, k in (('v4', 1), ('v4', 2), ('v4', 3), ('v2', 2), ('v2', 3)):
        jobs.append(review_job(base / run / case_name, run, case_name, protocol, k, legacy=True))
    return jobs


def phase2():
    jobs = []
    base, run, case_name = FRESH_CASES[1]
    for k in (1, 2):
        out = HERE / 'runs/labeling' / f'v1_rerun_{k}' / case_name
        jobs.append(dict(out=out, steps=[('pipeline', [sys.executable, str(PIPELINE), '--case', case_of(base / run / case_name),
                                                       '--output', str(out), '--mode', 'from-registry',
                                                       '--discovery-protocol', 'v1'])],
                         make_parent_only=True))
    for k in (1, 2, 3):
        for _, _, case_name in FRESH_CASES:
            source = HERE / 'runs/labeling' / f'fresh_{k}' / case_name
            jobs.append(review_job(source, f'fresh_{k}', case_name, 'v4', 1, base='fresh_v4'))
    for k in (1, 2, 3):
        for base, run, case_name in SPLIT_CASES:
            out = HERE / 'runs/split' / f'fresh_{k}' / case_name
            jobs.append(dict(out=out, steps=[('pipeline', [sys.executable, str(PIPELINE), '--case', case_of(base / run / case_name),
                                                           '--output', str(out), '--mode', 'from-registry',
                                                           '--discovery-protocol', 'v3', '--review-protocol', 'v4'])],
                             make_parent_only=True))
    return jobs


def main():
    phase, stream, streams = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    jobs = phase1() if phase == '1' else phase2()
    events = (HERE / f'events_phase{phase}_stream{stream}.jsonl').open('a')
    for index, job in enumerate(jobs):
        if index % streams != stream or job['out'].exists():
            continue
        if job.get('make_parent_only'):
            job['out'].parent.mkdir(parents=True, exist_ok=True)
            log_dir = job['out'].parent
        else:
            job['out'].mkdir(parents=True)
            log_dir = job['out']
        for name, command in job['steps']:
            start = time.time()
            with (log_dir / f'{job["out"].name}_{name}.log').open('w') as log:
                code = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT).returncode
            row = dict(phase=phase, out=str(job['out'].relative_to(HERE)), stage=name, exit_code=code,
                       seconds=round(time.time() - start, 3))
            events.write(json.dumps(row) + '\n')
            events.flush()
            print(json.dumps(row), flush=True)
            if code:
                break


if __name__ == '__main__':
    main()
