#!/usr/bin/env python3
"""Run the current v2 chain (3 runs each) on the five tested videos that so far had only older-prompt v2 runs.

Same frozen detection cases (read-only), run_vl_vv_pipeline.py --mode from-registry
--discovery-protocol v2, inside an existing allocation (API-only, no GPU).
Usage: openai_api_env.sh python run_remaining.py RUN_ID   (run_a | run_b | run_c)
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
CASES = [(14, 'holocine'), (32, 'wan22'), (47, 'storymem'), (69, 'wan21'), (165, 'cinetrans')]


def main():
    run_id = sys.argv[1]
    cases = {}
    for path in HISTORICAL:
        for line in path.read_text().splitlines():
            row = json.loads(line)
            cases[(row['generation_priority'], row['model_id'])] = Path(row['output_dir']).parent / 'work/case'
    events = (HERE / f'events_{run_id}.jsonl').open('a')
    for priority, model in CASES:
        out = HERE / 'runs/v2' / run_id / f'p{priority:03d}_{model}'
        if out.exists():
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        start = time.time()
        with (out.parent / f'p{priority:03d}_{model}.log').open('w') as log:
            code = subprocess.run([sys.executable, str(PIPELINE), '--case', str(cases[(priority, model)]), '--output', str(out),
                                   '--mode', 'from-registry', '--discovery-protocol', 'v2'], stdout=log, stderr=subprocess.STDOUT).returncode
        row = dict(run_id=run_id, priority=priority, model=model, exit_code=code, seconds=round(time.time() - start, 3))
        events.write(json.dumps(row) + '\n'); events.flush(); print(json.dumps(row), flush=True)


if __name__ == '__main__':
    main()
