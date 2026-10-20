#!/usr/bin/env python3
"""Choose a fully audited revision without changing any semantic verdict."""
import argparse,json
from run import HERE,read,dump,render,token_audit,validate_candidate,validate_review,io

def select(pilot=False):
    io.safe_compute();m=read(HERE/'manifest.json');ids=set(read(HERE/'pilot.json')['episode_ids'])
    changes=[]
    for j in m['jobs']:
        if pilot and j['episode_id'] not in ids:continue
        d=HERE/'episodes'/j['episode_id'];sf=d/'status.json'
        if not sf.exists() or read(sf)['status']=='running':continue
        p=read(d/'input.json');options=[]
        for f in d.glob('candidate_*.json'):
            i=int(f.stem.split('_')[-1]);rf=d/f'review_{i}.json'
            if not rf.exists():continue
            c=read(f);r=read(rf)
            try:validate_candidate(c,p);validate_review(r,p)
            except Exception:continue
            ta=token_audit(render(c),len(c['shots']))
            ready=r['verdict']=='pass' and ta['within_limit'] and ta['production_ids_equal_untruncated'] and ta['shot_spans_complete'] and not c['limitations']
            issues=sum(len(r[k]) for k in ['unsupported_claims','additions','source_omissions','schedule_issues','alias_issues'])
            # Fidelity precedes length for diagnostic candidates. Never promote an overlength prompt.
            key=(not ready,r['verdict']!='pass',issues,ta['tokens'],i)
            options.append((key,i,c,r,ta,ready))
        if not options:continue
        _,i,c,r,ta,ready=min(options,key=lambda x:x[0]);old=read(sf)
        dump(d/'candidate.json',c);(d/'candidate.txt').write_text(render(c)+'\n');dump(d/'semantic_audit.json',r);dump(d/'token_audit.json',ta)
        state=dict(old,status='ready' if ready else 'not_ready',tokens=ta['tokens'],semantic_verdict=r['verdict'],unsupported_claims=len(r['unsupported_claims']),additions=len(r['additions']),source_omissions=len(r['source_omissions']),selected_revision=i)
        if 'error' in state:state['historical_processing_error']=state.pop('error')
        dump(sf,state)
        selection=dict(episode_id=j['episode_id'],selected_revision=i,criteria='all_gates_pass_then_semantic_pass_then_issue_count_then_token_count; no verdict edits',considered=[dict(revision=o[1],ready=o[5],semantic_verdict=o[3]['verdict'],tokens=o[4]['tokens']) for o in sorted(options,key=lambda x:x[1])])
        dump(d/'selection.json',selection)
        if old.get('tokens')!=ta['tokens'] or old.get('semantic_verdict')!=r['verdict']:changes.append(selection)
    print(json.dumps(dict(changed=len(changes),rows=changes)),flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--pilot',action='store_true');args=a.parse_args();select(args.pilot)
