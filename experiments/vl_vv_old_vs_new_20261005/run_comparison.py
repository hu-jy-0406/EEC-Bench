#!/usr/bin/env python3
"""Rerun selected first-200 cases through the old (v1) and new (v2) evaluator chains.

Both chains run through run_vl_vv_pipeline.py --mode from-registry on the same
frozen detection case (entity ledger, keyframes, contract), so only issue
discovery, review and scoring differ.  API-only; run inside an existing
allocation (the pipeline requires SLURM_JOB_ID).  One stream processes its
(protocol, run) pairs sequentially; outputs are never overwritten.

Usage: openai_api_env.sh python run_comparison.py STREAM   (STREAM in 1..3)
"""
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PIPELINE = ROOT / 'scripts/run_vl_vv_pipeline.py'
HISTORICAL = [ROOT / 'experiments/vl_vv_multimodel_first200_run02/final_scores.jsonl',
              ROOT / 'experiments/vl_vv_multimodel_first200_run02_b/final_scores.jsonl']
# Representative v1 failures: owner examples, transition failures, attribute
# swaps, within-shot defects, a consistent control and a known-hard case.
CASES = [(2, 'wan21'), (14, 'wan21'), (14, 'storymem'), (28, 'wan22'), (28, 'cinetrans'),
         (180, 'cinetrans'), (47, 'wan21'), (15, 'cinetrans'), (68, 'holocine')]
STREAMS = {1: [('v2', 'run_a'), ('v1', 'rerun_a')],
           2: [('v2', 'run_b'), ('v1', 'rerun_b')],
           3: [('v2', 'run_c')]}


def historical_cases():
    rows = {}
    for path in HISTORICAL:
        for line in path.read_text().splitlines():
            row = json.loads(line)
            rows[(row['generation_priority'], row['model_id'])] = Path(row['output_dir']).parent / 'work/case'
    return rows


def main():
    stream = int(sys.argv[1])
    cases = historical_cases()
    events = (HERE / f'events_stream{stream}.jsonl').open('a')
    for protocol, run_id in STREAMS[stream]:
        for priority, model in CASES:
            out = HERE / 'runs' / protocol / run_id / f'p{priority:03d}_{model}'
            if out.exists():
                print(f'skip existing {out}', flush=True)
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            log = out.parent / f'p{priority:03d}_{model}.log'
            start = time.time()
            command = [sys.executable, str(PIPELINE), '--case', str(cases[(priority, model)]), '--output', str(out),
                       '--mode', 'from-registry', '--discovery-protocol', protocol]
            with log.open('w') as stream_log:
                code = subprocess.run(command, stdout=stream_log, stderr=subprocess.STDOUT).returncode
            row = dict(protocol=protocol, run_id=run_id, priority=priority, model=model, exit_code=code,
                       seconds=round(time.time() - start, 3), output=str(out), at=time.time())
            events.write(json.dumps(row) + '\n')
            events.flush()
            print(json.dumps(row), flush=True)


if __name__ == '__main__':
    main()
