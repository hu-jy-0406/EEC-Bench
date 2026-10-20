#!/usr/bin/env python3
"""HoloCine native-input adaptation with immutable contracts and explicit gates."""
import argparse, ast, collections, concurrent.futures, copy, importlib.util, json, os, pathlib, re, shutil, socket, sys, tempfile, threading, time
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'EECBench/scripts'))
import run_wedetect_shot_entities as io
from gs_consistency_contract import obj,arr,enum,S
read,dump,sha=io.read,io.dump,io.sha
CONTRACTS=ROOT/'EECBench/experiments/episode_contracts_20260921/deliverables/episodes'
QUEUE=ROOT/'EECBench/experiments/source_video_priority_20260921/generation_queue_400.jsonl'
FEAS=ROOT/'EECBench/experiments/generation_feasibility_20260921'
PROMPTER=FEAS/'repos/HoloCine/diffsynth/prompters/wan_prompter.py'
TOKPATH=FEAS/'models/Wan2.2-T2V-A14B/google/umt5-xxl'
DRAFT=obj(global_caption=S,shots=arr(obj(shot_id=S,caption=S)),aliases=arr(obj(entity_label=S,prompt_name=S)),limitations=arr(S))
ISSUE=obj(claim_id=S,problem=S,correction=S)
REVIEW=obj(verdict=enum('pass','fail'),supported_claim_ids=arr(S),unsupported_claims=arr(ISSUE),additions=arr(S),source_omissions=arr(S),schedule_issues=arr(S),alias_issues=arr(S),checked_shot_ids=arr(S))
TOK=None
LOCK=threading.Lock()
DISABLED=None

def tokenizer():
    global TOK
    if TOK is None:
        assert os.environ.get('USE_TORCH')=='0'
        # Execute verbatim tokenizer class and cleaners only, excluding torch/model imports.
        tree=ast.parse(PROMPTER.read_text())
        names={'basic_clean','whitespace_clean','canonicalize','HuggingfaceTokenizer'}
        body=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
        import transformers,ftfy,html,string,regex
        ns=dict(AutoTokenizer=transformers.AutoTokenizer,ftfy=ftfy,html=html,string=string,re=regex)
        exec(compile(ast.Module(body=body,type_ignores=[]),str(PROMPTER),'exec'),ns)
        TOK=ns['HuggingfaceTokenizer'](str(TOKPATH),seq_len=512,clean='whitespace',local_files_only=True)
    return TOK

def render(c):
    return '[global caption] '+c['global_caption'].strip()+' [per shot caption] '+' [shot cut] '.join(s['caption'].strip() for s in c['shots'])

def token_audit(text,nshots):
    with LOCK:
        t=tokenizer()
        kw=dict(return_tensors=None,padding=False,return_mask=True,return_offsets_mapping=True,add_special_tokens=True)
        full=t(text,truncation=False,**kw);prod=t(text,**kw)
        ids=full['input_ids'][0];pi=prod['input_ids'][0]
        offsets=full['offset_mapping'];clean=t._clean(text)
        spans=[];g=re.search(r'\[global caption\]',clean);p=re.search(r'\[per shot caption\]',clean)
        if g and p:
            spans.append((-1,g.start(),p.start()));start=p.start();idx=0
            for m in re.finditer(r'\[shot cut\]',clean):
                spans.append((idx,start,m.end()));idx+=1;start=m.end()
            if start<len(clean):spans.append((idx,start,len(clean)))
        positions={}
        for sid,start,end in spans:
            ind=[i for i,(a,b) in enumerate(offsets) if a!=b and not(b<=start or a>=end)]
            positions[str(sid)]=[min(ind),max(ind)+1] if ind else None
        return dict(tokens=len(ids),limit=512,within_limit=len(ids)<=512,production_ids_equal_untruncated=ids==pi,expected_shots=nshots,shot_spans_complete=len([k for k,v in positions.items() if k!='-1' and v])==nshots,token_positions=positions)

def payload(contract):
    cols=['claim_id','dimension','entity_ids','shot_ids','predicate','expected','coordinate_frame','quantifier']
    return dict(episode_id=contract['episode_id'],source=contract['prompt'],
        entities=[{k:e[k] for k in ['label','name','description']} for e in contract['entity_descriptions'].values()],
        entity_schedule=contract['entity_schedule'],claim_columns=cols,
        claim_rows=[[c[k] for k in cols] for c in contract['claims']],original_ambiguities=contract['unresolved'])

def validate_candidate(c,p):
    import jsonschema
    jsonschema.validate(c,DRAFT)
    assert [x['shot_id'] for x in c['shots']]==[x['shot_id'] for x in p['source']['shots']]
    assert c['global_caption'].strip() and all(x['caption'].strip() for x in c['shots'])
    assert all(mark not in x for x in [c['global_caption']]+[s['caption'] for s in c['shots']] for mark in ['[global caption]','[per shot caption]','[shot cut]'])
    labels={x['label'] for x in p['entities']}
    assert len({x['entity_label'] for x in c['aliases']})==len(c['aliases'])
    assert all(x['entity_label'] in labels for x in c['aliases'])

def validate_review(r,p):
    import jsonschema
    jsonschema.validate(r,REVIEW)
    ids=[x[0] for x in p['claim_rows']];got=r['supported_claim_ids']+[x['claim_id'] for x in r['unsupported_claims']]
    assert len(got)==len(set(got)) and set(got)==set(ids),'Incomplete claim audit'
    assert r['checked_shot_ids']==[s['shot_id'] for s in p['source']['shots']]
    issues=any(r[k] for k in ['unsupported_claims','additions','source_omissions','schedule_issues','alias_issues'])
    assert (r['verdict']=='pass')== (not issues)

def call(folder,p,kind):
    global DISABLED
    if (folder/'response.json').exists() and read(folder/'status.json').get('status')=='success':return read(folder/'response.json')
    folder.mkdir(parents=True,exist_ok=False)
    if DISABLED is None:DISABLED=io.disabled_skills_config()
    prompt=(HERE/(kind+'.txt')).read_text()+'\nINPUT_JSON:\n'+json.dumps(p,ensure_ascii=False,separators=(',',':'))
    (folder/'prompt.txt').write_text(prompt);dump(folder/'input.json',p)
    state=dict(status='running',started=time.time(),model='gpt-6-astra',reasoning='medium');dump(folder/'status.json',state)
    try:
        with tempfile.TemporaryDirectory(prefix='eec-holo-text-') as tmp:
            cmd=['codex','--ask-for-approval','never','exec','--ignore-user-config','-c',DISABLED,'--ephemeral','--skip-git-repo-check','--sandbox','read-only','--color','never','--json','--model','gpt-6-astra','-c','model_reasoning_effort="medium"','-c','project_doc_max_bytes=0','-c','web_search="disabled"','-c','model_instructions_file='+json.dumps(str(HERE/'base.txt')),'--output-schema',str(HERE/(kind+'.schema.json')),'--output-last-message',str(folder/'response.json'),'--cd',tmp]
            for flag in ['shell_tool','unified_exec','view_image','apps','plugins','hooks','multi_agent','memories','skill_search','browser_use','computer_use','code_mode','code_mode_only','workspace_dependencies']:cmd+=['--disable',flag]
            cmd+=['-'];dump(folder/'request.json',dict(command=cmd,prompt_sha256=sha(folder/'prompt.txt')))
            io.run_process(cmd,prompt,pathlib.Path(tmp),folder/'events.jsonl',folder/'stderr.log',900)
        state.update(status='success',usage=io.audit_events(folder/'events.jsonl'));return read(folder/'response.json')
    except BaseException as e:
        state.update(status='failed',error=str(e));raise
    finally:
        state['seconds']=time.time()-state['started'];dump(folder/'status.json',state)

def prepare():
    alloc=io.safe_compute();rows=[json.loads(x) for x in QUEUE.read_text().splitlines() if x.strip()]
    assert len(rows)==400
    if (HERE/'manifest.json').exists():raise FileExistsError('Already prepared')
    jobs=[]
    for i,row in enumerate(rows):
        eid=row['episode_id'];d=HERE/'episodes'/eid;d.mkdir(parents=True,exist_ok=True)
        c=read(CONTRACTS/eid/'contract.json');assert c['episode_id']==eid
        assert c['prompt']['global_prompt']==row['global_prompt']
        assert [(s['shot_id'],s['text']) for s in c['prompt']['shots']]==[(s['shot_id'],s['generation_prompt_en']) for s in row['shots']]
        for name in ['contract.json','alignment_contract.json']:shutil.copyfile(CONTRACTS/eid/name,d/name)
        dump(d/'input.json',payload(c));draft=dict(global_caption=row['global_prompt'],shots=[dict(shot_id=s['shot_id'],caption=s['generation_prompt_en']) for s in row['shots']])
        original=token_audit(render(draft),len(row['shots']));dump(d/'original_token_audit.json',original)
        jobs.append(dict(episode_id=eid,rank=i+1,shot_count=len(row['shots']),claims=len(c['claims']),original_tokens=original['tokens'],contract_sha256=sha(d/'contract.json'),alignment_contract_sha256=sha(d/'alignment_contract.json'),input_sha256=sha(d/'input.json')))
    for k,s in [('draft',DRAFT),('review',REVIEW)]:dump(HERE/(k+'.schema.json'),s)
    shutil.copyfile(ROOT/'EECBench/experiments/episode_contracts_20260921/pricing.json',HERE/'pricing.json')
    dump(HERE/'manifest.json',dict(created=time.time(),allocation=alloc,host=socket.gethostname(),queue_sha256=sha(QUEUE),model='gpt-6-astra',reasoning='medium',jobs=jobs,source_hashes={str(p):sha(p) for p in [HERE/'run.py',HERE/'draft.txt',HERE/'review.txt',HERE/'base.txt',PROMPTER]}))
    pilots=[]
    for n in [4,6,8]:pilots.append(next(j['episode_id'] for j in jobs if j['shot_count']==n))
    largest=max(jobs,key=lambda j:j['original_tokens'])['episode_id']
    if largest not in pilots:pilots.append(largest)
    dump(HERE/'pilot.json',dict(episode_ids=pilots))
    print(json.dumps(dict(episodes=len(jobs),original_over512=sum(j['original_tokens']>512 for j in jobs),min_tokens=min(j['original_tokens'] for j in jobs),max_tokens=max(j['original_tokens'] for j in jobs),pilots=pilots)),flush=True)

def process(job,max_drafts):
    eid=job['episode_id'];d=HERE/'episodes'/eid;p=read(d/'input.json')
    assert sha(d/'input.json')==job['input_sha256']
    assert sha(CONTRACTS/eid/'contract.json')==sha(d/'contract.json')==job['contract_sha256']
    assert sha(CONTRACTS/eid/'alignment_contract.json')==sha(d/'alignment_contract.json')==job['alignment_contract_sha256']
    if (d/'status.json').exists() and read(d/'status.json').get('status')=='ready':
        candidate=read(d/'candidate.json');validate_candidate(candidate,p);r=read(d/'semantic_audit.json');validate_review(r,p)
        ta=token_audit(render(candidate),len(candidate['shots']))
        assert ta['within_limit'] and ta['production_ids_equal_untruncated'] and r['verdict']=='pass' and not candidate['limitations']
        return read(d/'status.json')
    state=dict(episode_id=eid,started=time.time(),status='running');dump(d/'status.json',state)
    try:
        feedback=None;candidate=None
        for attempt in range(1,max_drafts+1):
            wire=copy.deepcopy(p)
            if candidate:wire.update(previous_candidate=candidate,feedback=feedback)
            candidate=call(d/'calls'/f'draft_{attempt}',wire,'draft');validate_candidate(candidate,p)
            ta=token_audit(render(candidate),len(candidate['shots']));dump(d/f'candidate_{attempt}.json',candidate);dump(d/f'tokens_{attempt}.json',ta)
            # Always independent semantic audit, including overlength candidates.
            r=call(d/'calls'/f'review_{attempt}',dict(p,candidate=candidate),'review');validate_review(r,p);dump(d/f'review_{attempt}.json',r)
            ready=ta['within_limit'] and ta['production_ids_equal_untruncated'] and ta['shot_spans_complete'] and r['verdict']=='pass' and not candidate['limitations']
            if ready:break
            feedback=dict(token_audit=ta,audit=r,instruction='Try a more economical exact semantic encoding. Do not lose any fact to satisfy the token limit. Correct every independent audit issue; if no faithful <=512 formulation is possible retain all information and explain the unresolved limit.')
        dump(d/'candidate.json',candidate);(d/'candidate.txt').write_text(render(candidate)+'\n');dump(d/'token_audit.json',ta);dump(d/'semantic_audit.json',r)
        state.update(status='ready' if ready else 'not_ready',tokens=ta['tokens'],semantic_verdict=r['verdict'],unsupported_claims=len(r['unsupported_claims']),additions=len(r['additions']),source_omissions=len(r['source_omissions']),drafts=attempt)
    except Exception as e:state.update(status='failed',error=repr(e))
    state['seconds']=time.time()-state['started'];dump(d/'status.json',state);print(json.dumps(state),flush=True);return state

def usage():
    pr=read(HERE/'pricing.json');counts=collections.Counter();cost=0;unknown=0;calls=[]
    for f in (HERE/'episodes').glob('*/calls/*/status.json'):
        s=read(f)
        if s.get('not_an_api_call'):continue
        u=s.get('usage',[]);valid=bool(u);c=0
        for v in u:
            it,ct,ot=[v.get(k,0) for k in ['input_tokens','cached_input_tokens','output_tokens']]
            valid &= 0<=ct<=it<=pr['max_input_tokens'] and not v.get('cache_write_input_tokens',0)
            for k in ['input_tokens','cached_input_tokens','output_tokens']:counts[k]+=v.get(k,0)
            c+=((it-ct)*pr['input_usd_per_million']+ct*pr['cached_input_usd_per_million']+ot*pr['output_usd_per_million'])/1e6
        if valid:cost+=c
        else:unknown+=1
        calls.append(dict(path=str(f.relative_to(HERE)),status=s['status'],seconds=s.get('seconds'),standard_api_equivalent_usd=c if valid else None))
    result=dict(calls=len(calls),tokens=dict(counts),total_tokens=counts['input_tokens']+counts['output_tokens'],known_standard_api_equivalent_usd=cost,standard_api_equivalent_usd=cost if not unknown else None,unknown_or_inflight=unknown,actual_bill=None,pricing_basis=pr,rows=calls);dump(HERE/'usage_cost.json',result);return result

def run(args):
    global DISABLED
    allocation=io.safe_compute();m=read(HERE/'manifest.json');assert read(HERE/'authorization.json')['authorized'];assert sha(QUEUE)==m['queue_sha256'];jobs=m['jobs']
    if args.pilot:
        ids=read(HERE/'pilot.json')['episode_ids'];jobs=[j for j in jobs if j['episode_id'] in ids]
    if args.exclude_pilot:
        ids=read(HERE/'pilot.json')['episode_ids'];jobs=[j for j in jobs if j['episode_id'] not in ids]
    if args.limit:jobs=jobs[:args.limit]
    tokenizer();DISABLED=io.disabled_skills_config();started=time.time()
    snapshot=HERE/'protocol_snapshots'/str(int(started));snapshot.mkdir(parents=True)
    for name in ['run.py','draft.txt','review.txt','base.txt','draft.schema.json','review.schema.json']:shutil.copyfile(HERE/name,snapshot/name)
    runtime_path=HERE/('runtime_'+args.run_id+'.json')
    dump(runtime_path,dict(status='running',allocation=allocation,host=socket.gethostname(),cpu_affinity=sorted(os.sched_getaffinity(0)),workers=args.workers,episodes=len(jobs),started=started,protocol_snapshot=str(snapshot)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:states=list(pool.map(lambda j:process(j,args.max_drafts),jobs))
    u=usage();dump(HERE/('run_summary_'+args.run_id+'.json'),dict(status_counts=dict(collections.Counter(s['status'] for s in states)),seconds=time.time()-started,states=states,total_tokens=u['total_tokens'],standard_api_equivalent_usd=u['standard_api_equivalent_usd']))
    dump(runtime_path,dict(status='complete',allocation=allocation,host=socket.gethostname(),started=started,finished=time.time(),active_task_processes=False))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('mode',choices=['prepare','run','usage']);a.add_argument('--pilot',action='store_true');a.add_argument('--exclude-pilot',action='store_true');a.add_argument('--run-id',default='main');a.add_argument('--limit',type=int,default=0);a.add_argument('--workers',type=int,default=4);a.add_argument('--max-drafts',type=int,default=2);args=a.parse_args()
    if args.mode=='prepare':prepare()
    elif args.mode=='usage':print(json.dumps(usage()))
    else:run(args)
