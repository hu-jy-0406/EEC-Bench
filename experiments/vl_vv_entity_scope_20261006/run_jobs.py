#!/usr/bin/env python3
"""Runs for the episode-wide entity-description rule (discovery v4, review v5).

review/RUN_SET/...: review v5 + scoring v3 on frozen discovery outputs that were reviewed with review v4 in
vl_vv_core_review_20261006, so the two reviews judge identical candidates:
- clip/v5_1/RUN/CASE: the 24 clip-model runs (discovery v2; earlier: review v2 x2, review v4 x1);
- clip/v5_2, clip/v5_3: two more repeats on the four target runs (#014 run_c, #069 runs a-c);
- v2fresh/fresh_K/CASE: the six fresh discovery-v2 runs of #014 / #069 Wan2.1;
- split/fresh_K/CASE: the twelve discovery-v3 (one label per issue) runs of #002, #014, #069 Wan2.1 and #028 Wan2.2.
pipeline/fresh_K/CASE: fresh discovery v4 + review v5 + scoring v3 (the new default chain) on the same four videos.
Usage (inside an existing allocation): python run_jobs.py STREAM NSTREAMS
"""
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CORE = ROOT / 'experiments/vl_vv_core_review_20261006/runs'
PIPELINE = ROOT / 'scripts/run_vl_vv_pipeline.py'
REVIEW = ROOT / 'scripts/run_vl_vv_issue_review.py'
SCORING = ROOT / 'scripts/run_vl_vv_episode_scoring.py'
OLD_NEW = ROOT / 'experiments/vl_vv_old_vs_new_20261005/runs/v2'
RESULTS = ROOT / 'experiments/vl_vv_v2_results_20261005/runs/v2'
CLIP_MODELS = ('wan21', 'wan22', 'storymem')
TARGETS = [(OLD_NEW, 'run_c', 'p014_wan21'), (RESULTS, 'run_a', 'p069_wan21'),
           (RESULTS, 'run_b', 'p069_wan21'), (RESULTS, 'run_c', 'p069_wan21')]
VIDEOS = [(OLD_NEW, 'run_a', 'p002_wan21'), (OLD_NEW, 'run_a', 'p014_wan21'),
          (RESULTS, 'run_a', 'p069_wan21'), (OLD_NEW, 'run_a', 'p028_wan22')]


def case_of(source):
    return json.loads((source / 'run.json').read_text())['case']


def review_job(source, out, case=None):
    case = case or case_of(source)
    return dict(out=out, steps=[
        ('issue_review', [sys.executable, str(REVIEW), '--case', case, '--issues', str(source / 'issue_discovery/result.json'),
                          '--output', str(out / 'issue_review'), '--review-protocol', 'v5']),
        ('episode_scoring', [sys.executable, str(SCORING), '--review', str(out / 'issue_review/result.json'),
                             '--output', str(out / 'episode_scoring')])])


def jobs():
    out = []
    for base in (OLD_NEW, RESULTS):
        for run in sorted(p for p in base.iterdir() if p.is_dir()):
            for source in sorted(p for p in run.iterdir() if p.is_dir() and p.name.endswith(CLIP_MODELS)):
                out.append(review_job(source, HERE / 'runs/review/clip/v5_1' / run.name / source.name))
    for k in (2, 3):
        for base, run, case_name in TARGETS:
            out.append(review_job(base / run / case_name, HERE / f'runs/review/clip/v5_{k}' / run / case_name))
    for k in (1, 2, 3):
        for _, _, case_name in VIDEOS:
            if case_name in ('p014_wan21', 'p069_wan21'):
                source = CORE / 'labeling' / f'fresh_{k}' / case_name
                out.append(review_job(source, HERE / 'runs/review/v2fresh' / f'fresh_{k}' / case_name))
            source = CORE / 'split' / f'fresh_{k}' / case_name
            out.append(review_job(source, HERE / 'runs/review/split' / f'fresh_{k}' / case_name))
    for k in (1, 2, 3):
        for base, run, case_name in VIDEOS:
            target = HERE / 'runs/pipeline' / f'fresh_{k}' / case_name
            out.append(dict(out=target, parent_only=True, steps=[
                ('pipeline', [sys.executable, str(PIPELINE), '--case', case_of(base / run / case_name), '--output', str(target),
                              '--mode', 'from-registry', '--discovery-protocol', 'v4', '--review-protocol', 'v5'])]))
    return out


def main():
    stream, streams = int(sys.argv[1]), int(sys.argv[2])
    events = (HERE / f'events_stream{stream}.jsonl').open('a')
    for index, job in enumerate(jobs()):
        if index % streams != stream or job['out'].exists():
            continue
        if job.get('parent_only'):
            job['out'].parent.mkdir(parents=True, exist_ok=True)
            log_dir = job['out'].parent
        else:
            job['out'].mkdir(parents=True)
            log_dir = job['out']
        for name, command in job['steps']:
            start = time.time()
            with (log_dir / f'{job["out"].name}_{name}.log').open('w') as log:
                code = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT).returncode
            row = dict(out=str(job['out'].relative_to(HERE)), stage=name, exit_code=code, seconds=round(time.time() - start, 3))
            events.write(json.dumps(row) + '\n')
            events.flush()
            print(json.dumps(row), flush=True)
            if code:
                break


if __name__ == '__main__':
    main()
