#!/usr/bin/env python3
"""Text-only EntityBench-format schedules and four-dimensional prompt contracts."""
import argparse, collections, concurrent.futures, copy, hashlib, html, json, os, re, socket, sys, tempfile, threading, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'EECBench/scripts'))
import run_wedetect_shot_entities as io
import gs_prompt_alignment as align
from gs_consistency_contract import obj, arr, enum, S
read,dump,sha=io.read,io.dump,io.sha
QUEUE=ROOT/'EECBench/experiments/source_video_priority_20260921/generation_queue_400.jsonl'
SOURCE=ROOT/'EECBench/experiments/source_video_400_20260920/deliverables/candidates_400.jsonl'
EV=obj(fact_id=S,quote=S)
ENTITY=obj(label=S,name=S,description=S,evidence=arr(EV))
SCHEDULE=obj(shot_id=S,characters=arr(S),places=arr(S),objects=arr(S))
CLAIM=copy.deepcopy(align.CLAIM)
CLAIM['properties']['quantifier']=enum('exists','start','end','throughout','when_visible','cross_shot','ordered')
COVER=obj(unit_id=S,claim_ids=arr(S),unscored=arr(obj(quote=S,reason=S)))
SCHEMA=obj(entities=arr(ENTITY),schedule=arr(SCHEDULE),claims=arr(CLAIM),coverage=arr(COVER),unresolved=arr(S))
REVIEW=obj(verdict=enum('pass','revised','unresolved'),issues=arr(S),delete_entities=arr(S),upsert_entities=arr(ENTITY),replacement_schedule=arr(SCHEDULE),delete_claims=arr(S),upsert_claims=arr(CLAIM),replacement_coverage=arr(COVER),unresolved=arr(S))
DISABLED=None
API_SEM=None
LOCK=threading.Lock()


def units(facts):
    result=[]
    for f in facts:
        # Exact source substrings; no linguistic normalisation.
        spans=re.split(r'(?<=[.!?])\s+(?=[A-Z0-9])', f['text'])
        for i,t in enumerate(spans):
            result.append(dict(unit_id=f['fact_id']+f'.u{i+1:02d}',fact_id=f['fact_id'],text=t))
    return result


def prepare():
    io.safe_compute()
    if (HERE/'manifest.json').exists():raise FileExistsError('Already prepared')
    rows=[json.loads(x) for x in QUEUE.read_text().splitlines() if x.strip()]
    sources={x['episode_id']:x for x in map(json.loads,SOURCE.read_text().splitlines())}
    assert len(rows)==400 and sum(len(e['shots']) for e in rows)==2000
    jobs=[]
    for i,e in enumerate(rows):
        assert e==sources[e['episode_id']]
        facts=[dict(fact_id='global',text=e['global_prompt'])]+[dict(fact_id=s['shot_id'],text=s['generation_prompt_en']) for s in e['shots']]
        payload=dict(episode_id=e['episode_id'],global_prompt=e['global_prompt'],shots=[dict(shot_id=s['shot_id'],prompt=s['generation_prompt_en']) for s in e['shots']],source_units=units(facts))
        path=HERE/'episodes'/e['episode_id']/'input.json';dump(path,payload)
        # EntityBench key denotes chronological contiguous scene occurrence.
        keys={};block=0;local=0;last=None
        for s in e['shots']:
            if s['scene_id']!=last:block+=1;local=0;last=s['scene_id']
            local+=1;keys[s['shot_id']]=f'{block}:{local}'
        jobs.append(dict(index=i,episode_id=e['episode_id'],shot_count=len(e['shots']),input_sha256=sha(path),schedule_keys=keys))
    for name,schema in [('draft',SCHEMA),('review',REVIEW)]:dump(HERE/(name+'.schema.json'),schema)
    pricing=read(ROOT/'EECBench/experiments/wan_prompt_adaptation_20260921/pricing.json');dump(HERE/'pricing.json',pricing)
    dump(HERE/'manifest.json',dict(schema_version='episode_schedule_claims_v1',created=time.time(),source=str(SOURCE),source_sha256=sha(SOURCE),queue=str(QUEUE),queue_sha256=sha(QUEUE),jobs=jobs,model='gpt-6-astra',reasoning='medium',source_fields=['global_prompt','shots[].generation_prompt_en'],source_scene_metadata_use='key numbering only; NOT supplied to semantic compiler or used as place identity',generated_video_consumed=False))
    snapshot=HERE/'source_snapshot';snapshot.mkdir(exist_ok=True)
    for name in ['run.py','rules.txt','review.txt','base.txt','draft.schema.json','review.schema.json']:(snapshot/name).write_bytes((HERE/name).read_bytes())
    print(json.dumps(dict(prepared=len(jobs),shots=2000)),flush=True)


def facts(src):return [dict(fact_id='global',text=src['global_prompt'])]+[dict(fact_id=s['shot_id'],text=s['prompt']) for s in src['shots']]


def ordered_claims(claims):
    by={c['claim_id']:c for c in claims}
    if len(by)!=len(claims):raise ValueError('Duplicate claim IDs')
    out=[];pending=list(claims);done=set()
    while pending:
        ready=[c for c in pending if set(c['depends_on'])<=done]
        if not ready:raise ValueError('Cyclic or missing claim dependencies')
        for c in ready:out.append(c);done.add(c['claim_id']);pending.remove(c)
    return out


def canonical(data,src):
    shot_ids=[s['shot_id'] for s in src['shots']];sched={s['shot_id']:s for s in data['schedule']}
    registry=dict(schema_version='prompt_registry_v1',shot_ids=shot_ids,entities=[])
    for e in data['entities']:
        kind={'Character':'characters','Location':'places','Object':'objects'}[e['label'].split()[0]]
        rows=[]
        for sid in shot_ids:
            required=e['name'] in sched[sid][kind]
            forbidden=any(c['dimension']=='presence' and c['predicate']=='absent' and c['entity_ids']==[e['label']] and c['shot_ids']==[sid] for c in data['claims'])
            rows.append(dict(shot_id=sid,expectation='required' if required else 'forbidden' if forbidden else 'not_required',reason='Explicit positive schedule' if required else 'Explicit negative prompt claim' if forbidden else 'No required visible observation; not an absence verdict'))
        registry['entities'].append(dict(prompt_entity_id=e['label'],name=e['name'],description=e['description'],evidence=e['evidence'],schedule=rows))
    fs=facts(src)
    excluded=[r['quote']+' — '+r['reason'] for u in data['coverage'] for r in u['unscored']]
    return dict(schema_version='prompt_alignment_b_v1',dimension_profile='four_dimensions_v1',reference_text='\n\n'.join(f['text'] for f in fs),shot_ids=shot_ids,narrative=dict(facts=fs),registry=registry,claims=data['claims'],excluded_requirements=excluded,claims_source='Text-only Astra/medium draft plus independent semantic audit of the original prompts')


def validate(data,src):
    import jsonschema
    jsonschema.validate(data,SCHEMA)
    shot_ids=[s['shot_id'] for s in src['shots']]
    if [s['shot_id'] for s in data['schedule']]!=shot_ids:raise ValueError('Schedule shot coverage/order mismatch')
    labels=[e['label'] for e in data['entities']];names=[e['name'] for e in data['entities']]
    if not labels or len(labels)!=len(set(labels)) or len(names)!=len(set(names)):raise ValueError('Empty/duplicate entity labels or names')
    if any(not re.fullmatch(r'(Character|Location|Object) [1-9][0-9]*',x) for x in labels):raise ValueError('Invalid EntityBench label')
    by={e['name']:e for e in data['entities']};fs={f['fact_id']:f['text'] for f in facts(src)}
    for s in data['schedule']:
        for group,prefix in [('characters','Character'),('places','Location'),('objects','Object')]:
            if len(s[group])!=len(set(s[group])) or any(n not in by or not by[n]['label'].startswith(prefix+' ') for n in s[group]):raise ValueError('Unknown/duplicate/wrong-type schedule reference '+s['shot_id'])
    data['claims']=ordered_claims(data['claims'])
    cs={c['claim_id']:c for c in data['claims']}
    for c in data['claims']:
        if c['dimension']=='presence' and c['predicate'] in ('present','absent'):
            if len(c['entity_ids'])!=1 or len(c['shot_ids'])!=1:raise ValueError('Atomic presence needs one entity/shot')
            same=[x for x in data['claims'] if x['dimension']=='presence' and x['predicate'] in ('present','absent') and x['entity_ids']==c['entity_ids'] and x['shot_ids']==c['shot_ids']]
            if len(same)!=1:raise ValueError('Duplicate/contradictory presence claim '+c['claim_id'])
            entity=next(e for e in data['entities'] if e['label']==c['entity_ids'][0])
            row=next(s for s in data['schedule'] if s['shot_id']==c['shot_ids'][0]);listed=entity['name'] in sum([row[k] for k in ['characters','places','objects']],[])
            if listed!=(c['predicate']=='present'):raise ValueError('Presence/schedule disagreement '+c['claim_id'])
        if c['dimension']!='presence' and len(c['shot_ids'])==1:
            for eid in c['entity_ids']:
                required=[x['claim_id'] for x in data['claims'] if x['dimension']=='presence' and x['predicate']=='present' and x['entity_ids']==[eid] and x['shot_ids']==c['shot_ids']]
                if required and not set(required)<=set(c['depends_on']):raise ValueError('Missing presence dependency '+c['claim_id']+' '+eid)
    if [r['unit_id'] for r in data['coverage']]!=[r['unit_id'] for r in src['source_units']]:raise ValueError('Source-unit coverage/order changed')
    mentioned=set()
    for r,u in zip(data['coverage'],src['source_units']):
        if not r['claim_ids'] and not r['unscored']:raise ValueError('Empty source coverage '+u['unit_id'])
        if len(r['claim_ids'])!=len(set(r['claim_ids'])) or not set(r['claim_ids'])<=set(cs):raise ValueError('Invalid coverage claim refs '+u['unit_id'])
        mentioned.update(r['claim_ids'])
        for x in r['unscored']:
            if not x['quote'] or x['quote'] not in u['text'] or not x['reason'].strip():raise ValueError('Unscored quote not exact in unit '+u['unit_id'])
    if mentioned!=set(cs):raise ValueError('Claims not attributed to source units: '+str(set(cs)-mentioned))
    align.validate_contract(canonical(data,src))
    return data


def apply_review(draft,patch):
    import jsonschema
    jsonschema.validate(patch,REVIEW)
    result=copy.deepcopy(draft)
    def update(key,ident,deletes,upserts):
        original=result[key];known={x[ident] for x in original}
        if len(deletes)!=len(set(deletes)) or not set(deletes)<=known:raise ValueError('Invalid deletion in '+key)
        if len({x[ident] for x in upserts})!=len(upserts):raise ValueError('Duplicate upserts '+key)
        if set(deletes)&{x[ident] for x in upserts}:raise ValueError('Delete/upsert conflict '+key)
        by={x[ident]:x for x in upserts};result[key]=[by.pop(x[ident],x) for x in original if x[ident] not in deletes]+list(by.values())
    update('entities','label',patch['delete_entities'],patch['upsert_entities'])
    update('claims','claim_id',patch['delete_claims'],patch['upsert_claims'])
    update('schedule','shot_id',[],patch['replacement_schedule'])
    update('coverage','unit_id',[],patch['replacement_coverage'])
    result['unresolved']=patch['unresolved']
    changed=any(patch[k] for k in ['delete_entities','upsert_entities','replacement_schedule','delete_claims','upsert_claims','replacement_coverage'])
    if patch['verdict']=='pass' and (changed or patch['issues']):raise ValueError('Pass verdict contains edits/issues')
    if patch['verdict']=='revised' and not changed:raise ValueError('Revised verdict without edit')
    return result


def _call(folder,payload,stage,feedback=None):
    folder.mkdir(parents=True,exist_ok=False)
    prompt=((HERE/'review.txt').read_text() if stage=='review' else '')+(HERE/'rules.txt').read_text()
    if feedback:prompt+='\nPrevious attempt failed a mechanical gate; fix these errors, retaining all substantive requirements:\n'+feedback
    prompt+='\nINPUT_JSON:\n'+json.dumps(payload,ensure_ascii=False,separators=(',',':'))
    (folder/'prompt.txt').write_text(prompt);dump(folder/'input.json',payload)
    state=dict(status='running',started=time.time(),model='gpt-6-astra',reasoning='medium',stage=stage);dump(folder/'status.json',state)
    try:
        with tempfile.TemporaryDirectory(prefix='eec-contract-text-') as tmp:
            cmd=['codex','--ask-for-approval','never','exec','--ignore-user-config','-c',DISABLED,'--ephemeral','--skip-git-repo-check','--sandbox','read-only','--color','never','--json','--model','gpt-6-astra','-c','model_reasoning_effort="medium"','-c','project_doc_max_bytes=0','-c','web_search="disabled"','-c','model_instructions_file='+json.dumps(str(HERE/'base.txt')),'--output-schema',str(HERE/(stage+'.schema.json')),'--output-last-message',str(folder/'response.json'),'--cd',tmp]
            for f in ('shell_tool','unified_exec','view_image','apps','plugins','hooks','multi_agent','memories','skill_search','browser_use','computer_use','code_mode','code_mode_only','workspace_dependencies'):cmd+=['--disable',f]
            cmd+=['-'];dump(folder/'request.json',dict(command=cmd,prompt_sha256=sha(folder/'prompt.txt')))
            io.run_process(cmd,prompt,Path(tmp),folder/'events.jsonl',folder/'stderr.log',1200)
        state.update(status='success',usage=io.audit_events(folder/'events.jsonl'));return read(folder/'response.json')
    except BaseException as e:
        state.update(status='failed',error=str(e))
        try:state['known_usage']=io.audit_events(folder/'events.jsonl')
        except Exception:state['usage_unavailable']=True
        raise
    finally:
        state['seconds']=time.time()-state['started'];dump(folder/'status.json',state)


def call(folder,payload,stage,feedback=None):
    if API_SEM is not None:API_SEM.acquire()
    try:return _call(folder,payload,stage,feedback)
    finally:
        if API_SEM is not None:API_SEM.release()


def release_after_drain(config,workers):
    def same_process(row):
        try:
            fields=Path('/proc/'+str(row['pid'])+'/stat').read_text().split()
            return fields[2]!='Z' and fields[21]==row['start_ticks']
        except FileNotFoundError:return False
    while any(same_process(row) for row in config['drain_processes']):time.sleep(2)
    for _ in range(workers-config['initial_api_slots']):API_SEM.release()
    dump(HERE/'scaling_released.json',dict(released_at=time.time(),api_limit=workers,prior_processes_terminal=True))
    print(json.dumps(dict(event='api_capacity_increased',workers=workers)),flush=True)


def process(job):
    eid=job['episode_id'];folder=HERE/'episodes'/eid;src=read(folder/'input.json');started=time.time()
    try:
        assert sha(folder/'input.json')==job['input_sha256']
        if (folder/'final.json').exists():
            validate(read(folder/'final.json'),src);return dict(episode_id=eid,status='cached')
        for stage in ['draft','review']:
            if (folder/(stage+'.json')).exists():continue
            payload=copy.deepcopy(src)
            if stage=='review':payload['proposal']=read(folder/'draft.json')
            feedback=None
            for attempt in range(1,5):
                dest=folder/'calls'/f'{stage}_{attempt}'
                try:
                    if (dest/'response.json').exists():raw=read(dest/'response.json')
                    elif dest.exists():feedback='Previous call did not return a complete valid JSON.';continue
                    else:raw=call(dest,payload,stage,feedback)
                    result=apply_review(payload['proposal'],raw) if stage=='review' else raw
                    validate(result,src)
                    dump(dest/'validation.json',dict(status='pass'));dump(folder/(stage+'.json'),raw)
                    if stage=='review':dump(folder/'final.json',result)
                    break
                except Exception as e:
                    feedback=str(e);dump(dest/'validation.json',dict(status='failed',error=feedback))
            else:raise ValueError(stage+' failed: '+str(feedback))
        if not (folder/'final.json').exists():
            result=validate(apply_review(read(folder/'draft.json'),read(folder/'review.json')),src)
            dump(folder/'final.json',result)
        result=read(folder/'final.json');state=dict(episode_id=eid,status='success',claims=len(result['claims']),entities=len(result['entities']),seconds=time.time()-started)
    except Exception as e:state=dict(episode_id=eid,status='failed',error=str(e),seconds=time.time()-started)
    dump(folder/'status.json',state)
    with LOCK:print(json.dumps(state,ensure_ascii=False),flush=True)
    return state


def usage():
    prices=read(HERE/'pricing.json');tot=collections.Counter();rows=[];amount=0.;unknown=0
    for p in sorted((HERE/'episodes').glob('*/calls/*/status.json')):
        s=read(p);us=s.get('usage',s.get('known_usage',[]));us=[us] if isinstance(us,dict) else us
        if not us and (p.parent/'events.jsonl').exists():
            us=[ev['usage'] for line in (p.parent/'events.jsonl').read_text().splitlines() if (ev:=json.loads(line)).get('type')=='turn.completed' and ev.get('usage')]
        cost=0.;valid=bool(us)
        for u in us:
            inp,cache,out=[u.get(k,0) for k in ['input_tokens','cached_input_tokens','output_tokens']]
            if not 0<=cache<=inp<=prices['max_input_tokens'] or u.get('cache_write_input_tokens',0):valid=False
            cost+=((inp-cache)*prices['input_usd_per_million']+cache*prices['cached_input_usd_per_million']+out*prices['output_usd_per_million'])/1e6
            for k in ['input_tokens','cached_input_tokens','output_tokens']:tot[k]+=u.get(k,0)
        if valid:amount+=cost
        else:unknown+=1
        rows.append(dict(path=str(p.relative_to(HERE)),status=s['status'],stage=s.get('stage'),started=s['started'],seconds=s.get('seconds'),usage=us,standard_api_equivalent_usd=cost if valid else None))
    result=dict(calls=len(rows),usage=dict(tot),total_tokens=tot['input_tokens']+tot['output_tokens'],standard_api_equivalent_usd=amount if not unknown else None,known_subtotal_usd=amount,unavailable_or_inflight_costs=unknown,pricing=prices,actual_billed_api_usd=None,rows=rows)
    dump(HERE/'usage_cost.json',result);return result


def run(args):
    global DISABLED,API_SEM
    alloc=io.safe_compute();m=read(HERE/'manifest.json')
    assert sha(SOURCE)==m['source_sha256'] and sha(QUEUE)==m['queue_sha256']
    DISABLED=io.disabled_skills_config();jobs=m['jobs']
    if args.pilot:
        jobs=[next(j for j in jobs if j['shot_count']==n) for n in (4,6,8)]
    if args.skip_pilot:
        pilot_ids={next(j['episode_id'] for j in m['jobs'] if j['shot_count']==n) for n in (4,6,8)}
        jobs=[j for j in jobs if j['episode_id'] not in pilot_ids]
    if args.only_unstarted:jobs=[j for j in jobs if not (HERE/'episodes'/j['episode_id']/'calls').exists() and not (HERE/'episodes'/j['episode_id']/'final.json').exists()]
    if args.scale:
        config=read(HERE/'scaling.json');API_SEM=threading.Semaphore(config['initial_api_slots'])
        threading.Thread(target=release_after_drain,args=(config,args.workers),daemon=True).start()
    if args.limit:jobs=jobs[:args.limit]
    started=time.time();dump(HERE/('pilot_runtime.json' if args.pilot else 'runtime.json'),dict(started=started,host=socket.gethostname(),allocation=alloc,workers=args.workers,cpu_affinity=sorted(os.sched_getaffinity(0)),planned=len(jobs)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:states=list(pool.map(process,jobs))
    u=usage();summary=dict(status='failed' if any(s['status']=='failed' for s in states) else 'success',seconds=time.time()-started,planned=len(jobs),failed=[s for s in states if s['status']=='failed'],total_tokens=u['total_tokens'],standard_api_equivalent_usd=u['standard_api_equivalent_usd'])
    dump(HERE/('pilot_summary.json' if args.pilot else 'run_summary.json'),summary);print(json.dumps(summary),flush=True)


def export(wait_for_ready=False):
    io.safe_compute();m=read(HERE/'manifest.json');dest=HERE/'deliverables';dest.mkdir(exist_ok=True);index=[];contracts=[]
    assert sha(SOURCE)==m['source_sha256'] and sha(QUEUE)==m['queue_sha256']
    for j in m['jobs']:
        eid=j['episode_id'];folder=HERE/'episodes'/eid
        while wait_for_ready and not (folder/'final.json').exists():
            if (folder/'status.json').exists() and read(folder/'status.json').get('status')=='failed':
                raise RuntimeError('Episode requires recovery before export: '+eid)
            time.sleep(2)
        assert sha(folder/'input.json')==j['input_sha256']
        src=read(folder/'input.json');data=validate(read(folder/'final.json'),src)
        patch=read(folder/'review.json');assert patch['verdict'] in ('pass','revised','unresolved')
        assert validate(apply_review(read(folder/'draft.json'),patch),src)==data
        schedule={j['schedule_keys'][s['shot_id']]:{k:s[k] for k in ['characters','places','objects']} for s in data['schedule']}
        contract=dict(schema_version='episode_schedule_claims_v1',episode_id=eid,entity_descriptions={e['label']:e for e in data['entities']},entity_schedule=schedule,claims=data['claims'],prompt=dict(global_prompt=src['global_prompt'],shots=[dict(shot_id=s['shot_id'],schedule_key=j['schedule_keys'][s['shot_id']],text=s['prompt']) for s in src['shots']]),coverage=data['coverage'],unresolved=data['unresolved'],provenance=dict(source_sha256=m['source_sha256'],prompt_input_sha256=j['input_sha256'],semantic_review='independent configured Astra/medium text audit; not human annotation'))
        path=dest/'episodes'/eid/'contract.json';dump(path,contract)
        can=canonical(data,src);align.validate_contract(can);dump(dest/'episodes'/eid/'alignment_contract.json',can)
        index.append(dict(episode_id=eid,priority_index=j['index'],shots=j['shot_count'],entities=len(data['entities']),claims=len(data['claims']),dimensions=dict(collections.Counter(c['dimension'] for c in data['claims'])),contract=str(path.relative_to(dest)),sha256=sha(path),alignment_contract=str((path.parent/'alignment_contract.json').relative_to(dest)),review_verdict=patch['verdict'],review_issues=len(patch['issues'])))
        contracts.append(contract)
    assert sha(SOURCE)==m['source_sha256'] and sha(QUEUE)==m['queue_sha256']
    for filename,subset in [('contracts_400.jsonl',contracts),('core_100.jsonl',contracts[:100]),('priority_200.jsonl',contracts[:200]),('stage2_additional_100.jsonl',contracts[100:200]),('stage3_remaining_200.jsonl',contracts[200:])]:
        (dest/filename).write_text(''.join(json.dumps(c,ensure_ascii=False,separators=(',',':'))+'\n' for c in subset))
    dump(dest/'index.json',index)
    audit=dict(status='pass',episodes=len(index),shots=sum(x['shots'] for x in index),entities=sum(x['entities'] for x in index),claims=sum(x['claims'] for x in index),dimensions=dict(sum((collections.Counter(x['dimensions']) for x in index),collections.Counter())),all_semantically_reviewed=True,source_hash_matches_current_manifest=True,all_canonical_contracts_pass_current_evaluator_validator=True,independent_human_semantic_validation=False,unresolved=sum(len(c['unresolved']) for c in contracts))
    dump(HERE/'audit.json',audit);usage();print(json.dumps(audit),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','run','export','usage']);p.add_argument('--pilot',action='store_true');p.add_argument('--skip-pilot',action='store_true');p.add_argument('--only-unstarted',action='store_true');p.add_argument('--scale',action='store_true');p.add_argument('--limit',type=int);p.add_argument('--workers',type=int,default=12);p.add_argument('--wait-for-ready',action='store_true');a=p.parse_args()
    if a.command=='prepare':prepare()
    elif a.command=='run':run(a)
    elif a.command=='export':export(a.wait_for_ready)
    else:print(json.dumps({k:v for k,v in usage().items() if k!='rows'}))
