#!/usr/bin/env python3
"""Re-review existing discovery v2 outputs with review v3 (true / partly true / false) and score them with v4.

Inputs are the 24 clip-model runs (Wan2.1, Wan2.2, StoryMem; 8 videos x runs a-c) of
vl_vv_old_vs_new_20261005 and vl_vv_v2_results_20261005.  Each keeps its frozen detection case and its
issue_discovery/result.json (read-only), so review v2 and review v3 judge the same candidates.  Episode
videos (CineTrans, HoloCine) are excluded: their cases use the retired nominal-grid keyframes.
A second pass with REVIEW_PROTOCOL v2 repeats the old review on the same candidates (output runs_v2_repeat/)
to measure run-to-run variance of the reviewer itself.
Usage (inside an existing allocation): python run_rereview.py STREAM NSTREAMS [REVIEW_PROTOCOL]
"""
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
API = ROOT / 'scripts/openai_api_env.sh'
REVIEW = ROOT / 'scripts/run_vl_vv_issue_review.py'
SCORING = ROOT / 'scripts/run_vl_vv_episode_scoring.py'
SOURCES = [ROOT / 'experiments/vl_vv_old_vs_new_20261005/runs/v2', ROOT / 'experiments/vl_vv_v2_results_20261005/runs/v2']
CLIP_MODELS = ('wan21', 'wan22', 'storymem')


def sources():
    rows = []
    for base in SOURCES:
        for run in sorted(p for p in base.iterdir() if p.is_dir()):
            for src in sorted(p for p in run.iterdir() if p.is_dir() and p.name.endswith(CLIP_MODELS)):
                rows.append(dict(source=src, run=run.name, case_name=src.name, experiment=base.parents[1].name))
    return rows


def main():
    stream, streams = int(sys.argv[1]), int(sys.argv[2])
    protocol = sys.argv[3] if len(sys.argv) > 3 else 'v3'
    runs_dir, tag = (HERE / 'runs', '') if protocol == 'v3' else (HERE / f'runs_{protocol}_repeat', f'_{protocol}_repeat')
    events = (HERE / f'events{tag}_stream{stream}.jsonl').open('a')
    for index, row in enumerate(sources()):
        if index % streams != stream:
            continue
        src = row['source']
        out = runs_dir / row['run'] / row['case_name']
        if out.exists():
            continue
        out.mkdir(parents=True)
        case = json.loads((src / 'run.json').read_text())['case']
        steps = [('issue_review', [sys.executable, str(REVIEW), '--case', case, '--issues', str(src / 'issue_discovery/result.json'),
                                   '--output', str(out / 'issue_review'), '--review-protocol', protocol]),
                 ('episode_scoring', [sys.executable, str(SCORING), '--review', str(out / 'issue_review/result.json'),
                                      '--output', str(out / 'episode_scoring')])]
        for name, command in steps:
            start = time.time()
            with (out / f'{name}.log').open('w') as log:
                code = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT).returncode
            event = dict(run=row['run'], case=row['case_name'], source=str(src), stage=name, exit_code=code,
                         seconds=round(time.time() - start, 3))
            events.write(json.dumps(event) + '\n')
            events.flush()
            print(json.dumps(event), flush=True)
            if code:
                break


if __name__ == '__main__':
    main()
