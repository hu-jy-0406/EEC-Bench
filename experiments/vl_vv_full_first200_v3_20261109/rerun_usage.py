#!/usr/bin/env python3
"""Tokens, standard-API cost estimate and time of this rerun's NEW model calls.
Full tasks: every call of the case and the output. Reuse tasks: only the calls this run made (V-V detection,
V-V review, episode scoring); the linked first-run frontend and V-L branch are excluded (already paid).
Cost basis as analyze_usage.py (GPT-6 Luna standard API estimate; not a bill)."""
import json
import statistics as st
from collections import defaultdict
from pathlib import Path
import analyze_usage as au

EXP = Path(__file__).resolve().parent
groups = defaultdict(list)
stage_calls = defaultdict(list)
secs = defaultdict(list)
for path in sorted((EXP / 'runs').glob('*/progress.json')):
    for tid, t in json.loads(path.read_text())['tasks'].items():
        if t.get('status') != 'success':
            continue
        reuse = t.get('mode') == 'reuse_vv'
        calls = au.calls_of(t, outputs_only=reuse)
        if reuse:
            calls = [c for c in calls if not c['stage'].startswith(('vl_detection', 'vl_review'))]
        mode = 'reuse' if reuse else ('full_gpu' if path.parent.name.startswith('gpu') else 'full_cpu')
        groups[mode].extend(calls); groups['all'].extend(calls)
        for c in calls:
            stage_calls[c['stage']].append(c)
        if t.get('pipeline_seconds'):
            secs[mode].append(t['pipeline_seconds'])
out = dict(basis=au.BASIS, groups={k: au.totals(v) for k, v in groups.items()},
           stages={k: au.totals(v) for k, v in sorted(stage_calls.items())},
           seconds={k: dict(tasks=len(v), mean=round(st.mean(v), 1), median=round(st.median(v), 1)) for k, v in secs.items()})
(EXP / 'rerun_usage.json').write_text(json.dumps(out, indent=1) + '\n')
print(json.dumps(out, indent=1))
