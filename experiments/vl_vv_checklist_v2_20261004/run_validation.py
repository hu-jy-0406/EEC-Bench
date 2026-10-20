#!/usr/bin/env python3
"""Run discovery v2 -> review v2 -> scoring v3 on frozen first-200 detection cases.

Reuses each historical case's frozen entity ledger read-only (from-registry
semantics) and writes fresh outputs under validation/<priority>_<model>/.
API-only stages, executed sequentially; no GPU work.  Invoke through
EECBench/scripts/openai_api_env.sh.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNS = [ROOT / 'experiments/vl_vv_multimodel_first200_run02/final_scores.jsonl',
        ROOT / 'experiments/vl_vv_multimodel_first200_run02_b/final_scores.jsonl']
ROUND1 = [(2, 'wan21'), (14, 'wan21'), (14, 'storymem'), (28, 'wan22'), (28, 'cinetrans'), (14, 'holocine')]
# Held-out cases (not used to refine the prompts): audit-reported misses.
HELD_OUT = [(69, 'wan21'), (68, 'holocine'), (180, 'cinetrans'), (47, 'wan21')]
# Fresh held-out cases for round 3 (audit-reported within-shot defects).
HELD_OUT_3 = [(15, 'cinetrans'), (165, 'cinetrans'), (32, 'wan22'), (47, 'storymem')]
ROUNDS = {'validation_round1': ROUND1, 'validation_round2': ROUND1 + HELD_OUT,
          'validation_round3': ROUND1 + HELD_OUT + HELD_OUT_3}
SCRIPTS = ROOT / 'scripts'


def historical():
    rows = {}
    for path in RUNS:
        for line in path.read_text().splitlines():
            row = json.loads(line)
            rows[(row['generation_priority'], row['model_id'])] = row
    return rows


def main():
    rows = historical()
    name = sys.argv[1] if len(sys.argv) > 1 else 'validation_round2'
    cases = ROUNDS[name]
    out_root = HERE / name
    out_root.mkdir(exist_ok=True)
    events = (out_root / 'events.jsonl').open('a')
    for priority, model in cases:
        row = rows[(priority, model)]
        case = Path(row['output_dir']).parent / 'work/case'
        out = out_root / f'p{priority:03d}_{model}'
        if out.exists():
            print(f'skip existing {out}', flush=True)
            continue
        out.mkdir()
        stages = [
            ('issue_discovery', [sys.executable, str(SCRIPTS / 'run_vl_vv_issue_discovery.py'), '--case', str(case),
                                 '--output', str(out / 'issue_discovery'), '--protocol', 'v2']),
            ('issue_review', [sys.executable, str(SCRIPTS / 'run_vl_vv_issue_review.py'), '--case', str(case),
                              '--issues', str(out / 'issue_discovery/result.json'), '--output', str(out / 'issue_review')]),
            ('episode_scoring', [sys.executable, str(SCRIPTS / 'run_vl_vv_episode_scoring.py'),
                                 '--review', str(out / 'issue_review/result.json'), '--output', str(out / 'episode_scoring')]),
        ]
        for name, command in stages:
            start = time.time()
            with (out / f'{name}.log').open('w') as log:
                code = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT).returncode
            event = dict(priority=priority, model=model, stage=name, exit_code=code,
                         seconds=round(time.time() - start, 3), case=str(case), at=time.time())
            events.write(json.dumps(event) + '\n')
            events.flush()
            print(json.dumps(event), flush=True)
            if code:
                break


if __name__ == '__main__':
    main()
