#!/usr/bin/env python3
"""Aggregate the 20-video missed-issue audit (assistant judgment by Claude subagents, not human annotation).
Reads audit20/<task>/{blind_findings,trace,pipeline}.json; writes audit20_summary.json; prints tables."""
import json, collections
from pathlib import Path
A = Path(__file__).resolve().parent / 'audit20'
rows, prim, sec, prec = [], [], [], []
pipe_unspec = 0
for d in sorted(p for p in A.iterdir() if p.is_dir()):
    b = json.loads((d / 'blind_findings.json').read_text()); t = json.loads((d / 'trace.json').read_text())
    pl = json.loads((d / 'pipeline.json').read_text())
    tp = {x['id']: x for x in t.get('primary') or []}; ts = {x['id']: x for x in t.get('secondary') or []}
    for f in b.get('primary') or []:
        x = tp.get(f['id'], {})
        prim.append(dict(task=d.name, id=f['id'], entity=f.get('entity'), scope=f.get('scope'), sure=f.get('sure'), what=f.get('what'),
                         ledger_status=x.get('ledger_status'), vv_outcome=x.get('vv_outcome'), matched=x.get('matched_ids')))
    for f in b.get('secondary') or []:
        x = ts.get(f['id'], {})
        sec.append(dict(task=d.name, id=f['id'], scope=f.get('scope'), sure=f.get('sure'), what=f.get('what'), vv_outcome=x.get('vv_outcome')))
    for x in t.get('pipeline_unspecified_confirmed') or []:
        prec.append(dict(task=d.name, **x))
    n_unspec = sum(1 for u in pl['vv_review_units'] if u['verdict'] == 'confirmed' and any(l == 'unspecified' for _, l in (u.get('subjects_with_labels') or [])))
    n_conf = sum(1 for u in pl['vv_review_units'] if u['verdict'] == 'confirmed')
    pipe_unspec += n_unspec
    rows.append(dict(task=d.name, primary=len(b.get('primary') or []), secondary=len(b.get('secondary') or []),
                     pipeline_confirmed_vv=n_conf, pipeline_confirmed_with_unspecified=n_unspec,
                     ledger_unspecified=sum(1 for e in pl['ledger'] if e['label'] == 'unspecified'),
                     ledger_unspecified_multi_shot=sum(1 for e in pl['ledger'] if e['label'] == 'unspecified' and len(e['shots']) >= 2)))
C = collections.Counter
summary = dict(
    videos=len(rows), primary=len(prim), secondary=len(sec),
    primary_by_outcome=C(p['vv_outcome'] for p in prim), primary_by_ledger=C(p['ledger_status'] for p in prim),
    primary_by_scope=C(p['scope'] for p in prim), primary_by_sure=C(p['sure'] for p in prim),
    secondary_by_outcome=C(s['vv_outcome'] for s in sec),
    precision=C(p['real'] for p in prec), pipeline_confirmed_vv=sum(r['pipeline_confirmed_vv'] for r in rows),
    pipeline_confirmed_with_unspecified=pipe_unspec,
    ledger_unspecified=sum(r['ledger_unspecified'] for r in rows), ledger_unspecified_multi_shot=sum(r['ledger_unspecified_multi_shot'] for r in rows),
    videos_with_primary=sum(r['primary'] > 0 for r in rows))
(A.parent / 'audit20_summary.json').write_text(json.dumps(dict(summary=summary, per_video=rows, primary=prim, secondary=sec, precision=prec), indent=1, ensure_ascii=False) + '\n')
print(json.dumps(summary, indent=1, ensure_ascii=False))
for r in rows: print(r)
print('--- primary findings')
for p in prim: print(p['task'], p['id'], p['scope'], p['sure'], p['ledger_status'], p['vv_outcome'], '|', p['entity'], '|', (p['what'] or '')[:150])
print('--- precision')
for p in prec: print(p)
