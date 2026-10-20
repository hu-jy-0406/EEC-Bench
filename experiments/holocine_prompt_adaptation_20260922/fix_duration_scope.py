#!/usr/bin/env python3
"""Remove two reviewer-identified unsupported duration constraints, then reaudit."""
import concurrent.futures,copy
import run
from run import HERE,read,dump,io,call,validate_candidate,validate_review,render,token_audit,tokenizer
io.safe_compute();tokenizer();run.DISABLED=io.disabled_skills_config()
jobs=[('NqbWXgVLkvo_s00011_n4_clean_v2',''),('i7HpHtcwB3w_s00194_n8_clean_v2','Shots 1–7: five seconds each. ')]
def work(item):
    eid,replacement=item;d=HERE/'episodes'/eid;p=read(d/'input.json');c=copy.deepcopy(read(d/'candidate.json'))
    assert c['global_caption'].startswith('Five seconds per shot. ')
    c['global_caption']=replacement+c['global_caption'][len('Five seconds per shot. '):]
    validate_candidate(c,p);i=6;dump(d/f'candidate_{i}.json',c);dump(d/f'tokens_{i}.json',token_audit(render(c),len(c['shots'])))
    prefix='parallel_' if (d/'parallel_status.json').exists() else ''
    r=call(d/'calls'/f'{prefix}review_{i}_duration_scope',dict(p,candidate=c),'review');validate_review(r,p)
    dump(d/f'review_{i}.json',r)
    dump(d/'duration_scope_correction.json',dict(revision=i,operation='Only replace initial duration clause with source-supported scope; independently reaudit all claims and source.',replacement=replacement,verdict=r['verdict']))
    print(eid,r['verdict'],flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(work,jobs))
