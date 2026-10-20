#!/usr/bin/env python3
"""Rerun incomplete review outputs without changing candidates or prior evidence."""
import concurrent.futures
import run
from run import HERE,read,dump,io,call,validate_candidate,validate_review
io.safe_compute();run.DISABLED=io.disabled_skills_config()
jobs=[]
for j in read(HERE/'manifest.json')['jobs']:
    d=HERE/'episodes'/j['episode_id']
    if not (d/'status.json').exists() or read(d/'status.json')['status']!='failed':continue
    candidates=sorted(d.glob('candidate_*.json'),key=lambda f:int(f.stem.split('_')[-1]))
    if candidates:
        f=candidates[-1];i=int(f.stem.split('_')[-1])
        if not (d/f'review_{i}.json').exists():jobs.append((d,f,i))
def work(item):
    d,f,i=item;p=read(d/'input.json');c=read(f);validate_candidate(c,p)
    prefix='parallel_' if (d/'parallel_status.json').exists() else ''
    folder=d/'calls'/f'{prefix}review_{i}_coverage_retry1'
    r=call(folder,dict(p,candidate=c),'review');validate_review(r,p)
    dump(d/f'review_{i}.json',r)
    dump(d/'review_recovery.json',dict(status='complete',revision=i,reason='Original independent review did not return an exact claim-ID partition. Fresh independent review saved; original output preserved.'))
    print(d.name,r['verdict'],flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(work,jobs))
