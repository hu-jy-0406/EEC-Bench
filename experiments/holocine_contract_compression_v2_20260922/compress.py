#!/usr/bin/env python3
"""Contract-first continuation, preserving the original 400-episode delivery."""
import argparse,collections,concurrent.futures,copy,json,os,pathlib,shutil,sys,time
HERE=pathlib.Path(__file__).resolve().parent
OLD=HERE.parent/'holocine_prompt_adaptation_20260922'
sys.path.insert(0,str(OLD));import run as old
old.HERE=HERE
read,dump,sha=old.read,old.dump,old.sha

def prepare():
    old.io.safe_compute();HERE.mkdir(exist_ok=True)
    assert read(OLD/'authorization.json')['authorized']
    for name in ['base.txt','draft.schema.json','review.schema.json','pricing.json']:
        shutil.copyfile(OLD/name,HERE/name)
    jobs=read(OLD/'manifest.json')['jobs'];idx={r['episode_id']:r for r in read(OLD/'deliverables/index.json')['episodes']}
    selected=[j for j in jobs if not idx[j['episode_id']]['generation_allowed']]
    assert len(selected)==159
    for j in selected:
        d=HERE/'episodes'/j['episode_id'];d.mkdir(parents=True,exist_ok=True)
        for name in ['input.json','contract.json','alignment_contract.json','shot_mapping.json']:
            shutil.copyfile(OLD/'episodes'/j['episode_id']/name,d/name)
        dump(d/'baseline.json',dict(candidate=read(OLD/'episodes'/j['episode_id']/'candidate.json'),token_audit=read(OLD/'episodes'/j['episode_id']/'token_audit.json'),semantic_audit=read(OLD/'episodes'/j['episode_id']/'semantic_audit.json')))
    m=read(OLD/'manifest.json');m['jobs']=selected;dump(HERE/'manifest.json',m)
    dump(HERE/'authorization.json',dict(authorized=True,parent_authorization=str(OLD/'authorization.json'),user_request='holocine自己的论文里面我记得可以生成好多好多shot不是吗？那样prompt不得更长？我觉得还是能继续压缩的，但始终保持相对于contract不丢失关键信息',scope='Continue159 on configured Codex/Astra medium with full frozen-contract coverage; unscored source decoration may be omitted. Existing parallel authorization persists.'))
    print(json.dumps(dict(prepared=len(selected))),flush=True)

def process(j,max_drafts):
    eid=j['episode_id'];d=HERE/'episodes'/eid;p=read(d/'input.json');baseline=read(d/'baseline.json')
    assert sha(d/'input.json')==j['input_sha256']
    assert sha(d/'contract.json')==sha(old.CONTRACTS/eid/'contract.json')==j['contract_sha256']
    assert sha(d/'alignment_contract.json')==sha(old.CONTRACTS/eid/'alignment_contract.json')==j['alignment_contract_sha256']
    if (d/'status.json').exists() and read(d/'status.json')['status']=='ready':return read(d/'status.json')
    state=dict(episode_id=eid,status='running',started=time.time());dump(d/'status.json',state)
    c=baseline['candidate'];feedback=dict(token_audit=baseline['token_audit'],instruction='Rebuild a minimum contract-sufficient prompt using the current contract-first scope. Every frozen contract fact must remain. Existing candidate is a factual reference, not wording to preserve.')
    try:
        for i in range(1,max_drafts+1):
            wire=copy.deepcopy(p);wire.update(previous_candidate=c,feedback=feedback)
            c=old.call(d/'calls'/f'draft_{i}',wire,'draft');old.validate_candidate(c,p)
            ta=old.token_audit(old.render(c),j['shot_count']);dump(d/f'candidate_{i}.json',c);dump(d/f'tokens_{i}.json',ta)
            r=old.call(d/'calls'/f'review_{i}',dict(p,candidate=c),'review');old.validate_review(r,p);dump(d/f'review_{i}.json',r)
            ready=r['verdict']=='pass' and ta['within_limit'] and ta['production_ids_equal_untruncated'] and ta['shot_spans_complete'] and not c['limitations']
            if ready:break
            feedback=dict(token_audit=ta,audit=r,instruction='Correct every contract issue and compress structurally. Preserve all frozen contract requirements; remove only semantically redundant words or unscored source decoration. Tokenizer feedback is exact. Do not add boilerplate limitations if the candidate actually fits.')
        dump(d/'candidate.json',c);dump(d/'token_audit.json',ta);dump(d/'semantic_audit.json',r)
        (d/'candidate.txt').write_text(old.render(c)+'\n')
        state.update(status='ready' if ready else 'not_ready',tokens=ta['tokens'],semantic_verdict=r['verdict'],drafts=i,unsupported_claims=len(r['unsupported_claims']),additions=len(r['additions']))
    except Exception as e:state.update(status='failed',error=repr(e))
    state['seconds']=time.time()-state['started'];dump(d/'status.json',state);print(json.dumps(state),flush=True);return state

def run(args):
    allocation=old.io.safe_compute();assert read(HERE/'authorization.json')['authorized'];old.tokenizer();old.DISABLED=old.io.disabled_skills_config()
    jobs=read(HERE/'manifest.json')['jobs'];start=time.time()
    snap=HERE/'protocol_snapshots'/str(int(start));snap.mkdir(parents=True)
    for name in ['compress.py','draft.txt','review.txt','base.txt','draft.schema.json','review.schema.json']:shutil.copyfile(HERE/name,snap/name)
    dump(HERE/'runtime.json',dict(status='running',started=start,workers=args.workers,episodes=len(jobs),allocation=allocation,cpu_affinity=sorted(os.sched_getaffinity(0)),snapshot=str(snap)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:states=list(pool.map(lambda j:process(j,args.max_drafts),jobs))
    u=old.usage();dump(HERE/'summary.json',dict(states=dict(collections.Counter(s['status'] for s in states)),rows=states,usage=u))
    dump(HERE/'runtime.json',dict(status='complete',started=start,finished=time.time(),seconds=time.time()-start,active_model_calls=False));print(json.dumps(dict(done=len(states),counts=collections.Counter(s['status'] for s in states))),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['prepare','run','progress']);ap.add_argument('--workers',type=int,default=64);ap.add_argument('--max-drafts',type=int,default=2);args=ap.parse_args()
    if args.mode=='prepare':prepare()
    elif args.mode=='run':run(args)
    else:
        old.io.safe_compute();states=[]
        for j in read(HERE/'manifest.json')['jobs']:
            p=HERE/'episodes'/j['episode_id']/'status.json';states.append(read(p) if p.exists() else dict(status='pending'))
        u=old.usage();result=dict(states=dict(collections.Counter(s['status'] for s in states)),calls=u['calls'],tokens=u['total_tokens'],known_standard_api_equivalent_usd=u['known_standard_api_equivalent_usd'],unknown_or_inflight=u['unknown_or_inflight'],failed=[s for s in states if s['status']=='failed']);dump(HERE/'progress.json',result);print(json.dumps(result),flush=True)
