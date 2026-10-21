#!/usr/bin/env python3
"""V-L review on frozen candidates: new wording ("does not conflict with") vs old ("satisfies").

Re-reviews the 16 V-L detection results of experiments/vl_vv_branch_split_20261009/runs/main
(8 videos x run_a/run_b; unlabeled images) with the default review v6. Arm "new" uses the
current prompts; arm "old" points the loader at source_before/ (pre-change copies) and is a
repeat of the original reviews, giving run-to-run noise. Image labels are off in both arms so
that only the wording differs from the original reviews.

Usage (inside an existing allocation, through scripts/openai_api_env.sh):
  python review_check.py STREAM NSTREAMS
"""
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
os.environ['EECBENCH_IMAGE_LABELS'] = 'off'

import vl_vv_branch_common as common  # noqa: E402
import run_vl_vv_branch_review as review  # noqa: E402

SPLIT = ROOT / 'experiments/vl_vv_branch_split_20261009'
sys.path.insert(0, str(SPLIT))
from run_jobs import CASES, case_dir  # noqa: E402

BEFORE = HERE / 'source_before'
# The config change (an unused basis description) does not reach any prompt or schema,
# so both arms render with the current config.
NEW = dict(definitions=common.DEFINITIONS_PATH, prompt=common.REVIEW['vl']['prompt'])
OLD = dict(definitions=BEFORE / 'vl_vv_branch_definitions_v1.txt', prompt=BEFORE / 'vl_vv_issue_review_v6_vl.txt')


def use(paths):
    common.DEFINITIONS_PATH = paths['definitions']
    common.REVIEW['vl']['prompt'] = paths['prompt']


def jobs():
    return [(arm, run, key) for arm in ('new', 'old') for run in ('run_a', 'run_b') for key in CASES]


def main():
    stream, streams = int(sys.argv[1]), int(sys.argv[2])
    events = (HERE / f'events_stream{stream}.jsonl').open('a')
    for index, (arm, run, key) in enumerate(jobs()):
        out = HERE / 'runs' / arm / run / key / 'vl_review'
        if index % streams != stream or out.exists():
            continue
        use(NEW if arm == 'new' else OLD)
        detection = SPLIT / 'runs/main' / run / key / 'vl_detection/result.json'
        out.parent.mkdir(parents=True, exist_ok=True)
        start, error = time.time(), None
        try:
            review.run(case_dir(key), detection, out, 'vl')
        except Exception as exc:  # recorded, the stream continues
            error = str(exc)[:500]
        events.write(json.dumps(dict(arm=arm, run=run, case=key, error=error,
                                     seconds=round(time.time() - start, 1))) + '\n')
        events.flush()


if __name__ == '__main__':
    main()
