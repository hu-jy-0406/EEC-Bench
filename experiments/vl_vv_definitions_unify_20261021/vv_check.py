#!/usr/bin/env python3
"""V-V detection with vs without the 2026-10-21 permissibility paragraph ("a change that does
not conflict with the prompt ... is normal; an unexplained change of the same entity ... is a V-V
issue, even when the prompt does not describe the changed attribute").

Arm "with": current prompts. Arm "without": source_before/vl_vv_issue_discovery_v5_vv.txt (same
file without that paragraph). Image labels on. Frozen registries of the 2026-10-09 reference set.
Usage (inside an existing allocation, via scripts/openai_api_env.sh): python vv_check.py STREAM NSTREAMS
"""
import json, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'scripts')); sys.path.insert(0, str(ROOT / 'experiments/vl_vv_branch_split_20261009'))
import vl_vv_branch_common as common  # noqa: E402
import run_vl_vv_branch_detection as detection  # noqa: E402
from run_jobs import case_dir  # noqa: E402
ARMS = {'with': common.DISCOVERY['vv']['prompt'], 'without': HERE / 'source_before/vl_vv_issue_discovery_v5_vv.txt'}
CASES = ('p002_wan21', 'p028_wan22', 'p014_wan21', 'p014_storymem')

def jobs():
    return [(arm, key, run) for arm in ARMS for key in CASES for run in ('a', 'b')]

def main():
    stream, streams = int(sys.argv[1]), int(sys.argv[2])
    events = (HERE / f'events_vv_stream{stream}.jsonl').open('a')
    for index, (arm, key, run) in enumerate(jobs()):
        out = HERE / 'runs/vv_check' / arm / f'run_{run}' / key / 'vv_detection'
        if index % streams != stream or out.exists():
            continue
        common.DISCOVERY['vv']['prompt'] = ARMS[arm]
        out.parent.mkdir(parents=True, exist_ok=True)
        start, error = time.time(), None
        try:
            detection.run(case_dir(key), out, 'vv')
        except Exception as exc:
            error = str(exc)[:500]
        events.write(json.dumps(dict(arm=arm, case=key, run=run, error=error, seconds=round(time.time() - start, 1))) + '\n')
        events.flush()

if __name__ == '__main__':
    main()
