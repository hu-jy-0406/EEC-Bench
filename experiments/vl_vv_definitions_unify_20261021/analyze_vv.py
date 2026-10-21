#!/usr/bin/env python3
"""Summarize the V-V detection A/B (with / without the permissibility paragraph) -> analysis_vv.json."""
import collections, glob, json
from pathlib import Path
HERE = Path(__file__).resolve().parent
rows = []
for f in sorted(glob.glob(str(HERE / 'runs/vv_check/*/run_*/*/vv_detection/result.json'))):
    parts = Path(f).parts
    arm, run, case = parts[-5], parts[-4], parts[-3]
    d = json.load(open(f)); raw = d.get('model_output') or {}
    judg = collections.Counter(c['judgment'] for c in raw.get('observed_changes', []))
    audit = json.load(open(Path(f).parent / 'call_repair_audit.json'))
    rows.append(dict(arm=arm, run=run, case=case, issues=len(d['issues']), repair_rounds=audit.get('repair_rounds'),
                     normal=judg.get('normal', 0), abnormal=judg.get('abnormal', 0), uncertain=judg.get('uncertain', 0),
                     issue_list=[dict(id=i['issue_id'], subcategory=i['subcategory'], shots=i['shot_ids'],
                                      description=i['description']) for i in d['issues']]))
json.dump(rows, open(HERE / 'analysis_vv.json', 'w'), ensure_ascii=False, indent=1)
for arm in ('without', 'with'):
    sel = [r for r in rows if r['arm'] == arm]
    print(f"== {arm}: runs {len(sel)}, issues {sum(r['issues'] for r in sel)}, changes normal/abnormal/uncertain "
          f"{sum(r['normal'] for r in sel)}/{sum(r['abnormal'] for r in sel)}/{sum(r['uncertain'] for r in sel)}, "
          f"repair rounds {sum(r['repair_rounds'] or 0 for r in sel)}")
for case in sorted({r['case'] for r in rows}):
    for arm in ('without', 'with'):
        for r in [r for r in rows if r['case'] == case and r['arm'] == arm]:
            print(f"{case} {arm:7s} {r['run']} issues={r['issues']} n/a/u={r['normal']}/{r['abnormal']}/{r['uncertain']}")
            for i in r['issue_list']:
                print(f"      {i['id']} {i['subcategory']} {i['shots']} {i['description'][:110]}")
