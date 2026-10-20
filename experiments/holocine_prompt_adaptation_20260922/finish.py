#!/usr/bin/env python3
"""Finalize only once all adaptation/review writers have terminated."""
import runpy
from run import HERE,read,io
io.safe_compute()
assert read(HERE/'runtime_full396.json')['status']=='complete'
assert read(HERE/'runtime_parallel64.json')['status']=='complete'
for p in (HERE/'episodes').glob('*/status.json'):
    assert read(p)['status']!='running',str(p)
for p in (HERE/'episodes').glob('*/calls/*/status.json'):
    assert read(p)['status']!='running',str(p)
from select_best import select
select()
from export import export
export()
for name in ['audit_handoff.py','package.py','summarize_delivery.py','progress.py']:
    runpy.run_path(str(HERE/name),run_name='__main__')
