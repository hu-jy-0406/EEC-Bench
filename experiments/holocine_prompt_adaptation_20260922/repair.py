#!/usr/bin/env python3
"""Bounded follow-up of terminal exceptions, never overlap an active episode."""
import argparse,concurrent.futures,json,time
import run
from run import HERE,read,dump,io,process,tokenizer

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--max-tokens',type=int,default=560);ap.add_argument('--max-drafts',type=int,default=5);ap.add_argument('--workers',type=int,default=8);ap.add_argument('--all-semantic',action='store_true');args=ap.parse_args()
    io.safe_compute();assert read(HERE/'authorization.json')['authorized'];jobs=[]
    for j in read(HERE/'manifest.json')['jobs']:
        p=HERE/'episodes'/j['episode_id']/'status.json'
        if not p.exists():continue
        s=read(p)
        if s['status']!='not_ready':continue
        if s.get('tokens',100000)>args.max_tokens and not(args.all_semantic and s.get('semantic_verdict')!='pass'):continue
        count=max([int(f.stem.split('_')[-1]) for f in p.parent.glob('candidate_*.json')],default=0)
        if count>=args.max_drafts:continue
        jobs.append(j)
    dump(HERE/('repair_plan_'+str(int(time.time()))+'.json'),dict(episodes=[j['episode_id'] for j in jobs],max_tokens=args.max_tokens,max_drafts=args.max_drafts,workers=args.workers))
    original_call=run.call
    def routed_call(folder,p,kind):
        if (folder.parent.parent/'parallel_status.json').exists():
            folder=folder.parent/('parallel_'+folder.name)
        recovery=folder.parent/(folder.name+'_coverage_retry1')
        if kind=='review' and (recovery/'response.json').exists() and read(recovery/'status.json').get('status')=='success':
            return read(recovery/'response.json')
        return original_call(folder,p,kind)
    run.call=routed_call
    tokenizer();run.DISABLED=io.disabled_skills_config()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:states=list(pool.map(lambda j:process(j,args.max_drafts),jobs))
    print(json.dumps(dict(episodes=len(states),states=states)),flush=True)
