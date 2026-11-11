#!/usr/bin/env python3
"""Sanity check of finished tasks: V-V detection mode/calls/repairs, prompt hashes, issue and verdict counts, scoring."""
import json, glob, collections, statistics as st
from pathlib import Path
EXP = Path(__file__).resolve().parent
rows = []
hashes = collections.Counter()
for p in glob.glob(str(EXP / 'runs/claims/*.json')):
    s = json.load(open(p))
    if s['status'] != 'success':
        continue
    prog = json.load(open(EXP / 'runs' / s['run'] / 'progress.json'))['tasks'][s['task_id']]
    out = Path(prog['output_dir'])
    det = json.load(open(out / 'vv_detection/result.json'))
    rev = json.load(open(out / 'vv_review/result.json'))
    sc = json.load(open(out / 'episode_scoring/result.json'))
    sh = json.load(open(out / 'vv_detection/source_hashes.json'))
    for k, v in sh.items():
        if 'prompt' in k or k.endswith('.txt'):
            hashes[(k, str(v)[:12])] += 1
    items = det.get('item_calls') or {}
    verdicts = collections.Counter(u.get('verdict') for u in rev.get('units') or [])
    st6 = sc['consistency_issue_statistics']['total']
    rows.append(dict(tid=s['task_id'], run=s['run'], mode=det.get('vv_detection_mode'), calls=det.get('calls'),
                     items=len(items), item_repairs=sum(v.get('repair_rounds', 0) for v in items.values()),
                     det_repairs=det.get('repair_rounds'), cands=len(det.get('issues') or []),
                     confirmed=verdicts.get('confirmed', 0), rejected=verdicts.get('rejected', 0),
                     uncertain=verdicts.get('uncertain', 0), vv_unspec=st6['with_unspecified_subject'],
                     vv_conf_stat=st6['confirmed_issues'], vv=sc['scores']['v_v']['overall'], vl=sc['scores']['v_l'],
                     uec=sc['scores']['uec']))
print('tasks', len(rows))
print('modes', collections.Counter(r['mode'] for r in rows))
print('calls', collections.Counter(r['calls'] for r in rows).most_common(8))
print('items', collections.Counter(r['items'] for r in rows))
print('item repair rounds total', sum(r['item_repairs'] for r in rows), 'tasks with any', sum(r['item_repairs'] > 0 for r in rows))
print('det repair_rounds field', collections.Counter(str(r['det_repairs']) for r in rows).most_common(5))
print('prompt hashes'); [print(' ', k, c) for k, c in sorted(hashes.items())]
print('zero candidates', sum(r['cands'] == 0 for r in rows), 'zero confirmed', sum(r['confirmed'] == 0 for r in rows))
print('confirmed stat mismatch', [r['tid'] for r in rows if r['confirmed'] != r['vv_conf_stat']][:10])
for key in ('cands', 'confirmed', 'rejected', 'uncertain'):
    print(key, 'sum', sum(r[key] for r in rows), 'mean', round(st.mean(r[key] for r in rows), 2), 'max', max(r[key] for r in rows))
tot = sum(r['confirmed'] for r in rows); u = sum(r['vv_unspec'] for r in rows)
print('confirmed V-V', tot, 'with unspecified subject', u, 'share', round(u / tot, 4) if tot else None)
for mode in ('reuse', 'full'):
    sub = [r for r in rows if r['run'].startswith('reuse') == (mode == 'reuse')]
    t = sum(r['confirmed'] for r in sub); uu = sum(r['vv_unspec'] for r in sub)
    print(mode, len(sub), 'confirmed', t, 'unspec', uu, 'mean V-V', round(st.mean(r['vv'] for r in sub), 2),
          'mean V-L', round(st.mean(r['vl'] for r in sub), 2), 'mean UEC', round(st.mean(r['uec'] for r in sub), 2))
