#!/usr/bin/env python3
"""Counts, usage and cost of the discovery calls (GPT-6 Luna standard estimate: USD 0.10/M uncached input, 0.01/M
cached, 0.50/M output; not a bill). Writes discovery_summary.json."""
import json, collections
from pathlib import Path
HERE = Path(__file__).resolve().parent
rows, objs = [], []
tok = collections.Counter()
for st in sorted(HERE.glob('runs/*/*/status.json')):
    s = json.loads(st.read_text()); task, shot = st.parent.parent.name, st.parent.name
    o = json.loads((st.parent / 'response.json').read_text())['objects'] if s['status'] == 'success' else []
    for u in s.get('usage') or []:
        tok['input'] += u['input_tokens']; tok['cached'] += u['cached_input_tokens']; tok['output'] += u['output_tokens']; tok['calls'] += 1
    rows.append(dict(task=task, shot=shot, status=s['status'], objects=len(o), seconds=round(s['seconds'], 1)))
    objs += [dict(task=task, shot=shot, **x) for x in o]
usd = ((tok['input'] - tok['cached']) * .10 + tok['cached'] * .01 + tok['output'] * .50) / 1e6
out = dict(shots=len(rows), failed=sum(r['status'] != 'success' for r in rows), objects=len(objs),
           per_shot=round(len(objs) / len(rows), 2), in_prompt=collections.Counter(o['in_prompt'] for o in objs),
           usage=dict(tok), usd_estimate=round(usd, 6), mean_seconds=round(sum(r['seconds'] for r in rows) / len(rows), 1))
(HERE / 'discovery_summary.json').write_text(json.dumps(dict(summary=out, shots=rows, objects=objs), indent=1, ensure_ascii=False) + '\n')
print(json.dumps(out, indent=1, ensure_ascii=False))
