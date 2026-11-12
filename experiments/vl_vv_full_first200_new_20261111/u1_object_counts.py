#!/usr/bin/env python3
"""Objects per shot in plug-in U1 inventories (first response) and how often the 30-object gate fired, for the full C
run (old entity scope) and this run (new scope). Zero model calls."""
import glob, json, statistics, sys
from pathlib import Path
E = Path(__file__).resolve().parent.parent
for name, pat in (('C full run, old scope', 'vl_vv_full_first200_c_20261110/runs/*/branch/u1/*'),
                  ('this run, new scope', 'vl_vv_full_first200_new_20261111/runs/*/results_with/vv_plugin/u1/*')):
    first, gate_rounds, failed, shots = [], 0, 0, 0
    for shot in glob.glob(str(E / pat)):
        audit = Path(shot) / 'call_repair_audit.json'
        resp = Path(shot) / 'call' / 'response.json'
        if not audit.is_file():
            continue
        shots += 1
        a = json.loads(audit.read_text())
        if resp.is_file():
            try:
                first.append(len(json.loads(resp.read_text())['objects']))
            except Exception:
                pass
        hit = sum(any('at most 30' in e for e in r.get('errors', [])) for r in a.get('rounds', []))
        gate_rounds += hit
        failed += a.get('status') == 'failed'
    if first:
        print(f'{name}: shots {shots}, objects in the first response median {statistics.median(first)}, '
              f'90th pct {sorted(first)[int(0.9 * len(first))]}, max {max(first)}, first response >30: '
              f'{sum(x > 30 for x in first)} ({100 * sum(x > 30 for x in first) / len(first):.1f}%), rounds rejected '
              f'by the cap {gate_rounds}, shots failed {failed}')
