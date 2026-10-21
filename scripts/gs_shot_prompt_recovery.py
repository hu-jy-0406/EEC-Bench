#!/usr/bin/env python3
"""Own-shot prompt binding, reverse coverage, one targeted GDINO pass, deterministic freeze."""
import argparse,copy,json,os,shutil,subprocess,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import run_wedetect_shot_entities as io
from gs_consistency_contract import obj,arr,enum,S,I
from gs_prompt_binding import call,validate_registry
import vl_vv_repair_loop as repair_loop

B=Path(__file__).resolve().parents[1]
PYTHON=Path('/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python')
read,save,sha=io.read,io.dump,io.sha

def active_entities_root(case):
    case=Path(case);p=case/'shot_prompt_recovery/results.json'
    if p.exists():
        if read(p)['status']!='success':raise ValueError('Incomplete prompt recovery must not feed downstream')
        return case/'shot_prompt_recovery/entities'
    if (case/'shot_prompt_recovery/run.json').exists():raise ValueError('Prompt recovery not finalized')
    return case/'entities'

def own_payload(case,shot,registry,narrative):
    sid=shot['shot_id'];path=case/'entities/shots'/sid;original=read(path/'entities.json')
    facts=[f for f in narrative['facts'] if f.get('shot_id') in (None,sid)]
    prompts=[]
    for p in registry['entities']:
        schedule=next(s for s in p['schedule'] if s['shot_id']==sid)
        # Prompt inventory is text, not visual evidence. Never include other-shot rows/facts.
        prompts.append(dict(prompt_entity_id=p['prompt_entity_id'],name=p['name'],description=p['description'],expectation=schedule['expectation'],schedule_reason=schedule['reason']))
    return dict(shot_id=sid,prompt_entities=prompts,narrative=facts,entities=original['entities'],image_order=[dict(frame_id=f['frame_id'],attachment_index=i+1) for i,f in enumerate(shot['frames'])])

def binding_schema(pids):
    common=dict(entity_id=S,reason=S)
    return obj(bindings=arr({'anyOf':[
        obj(**common,status=enum('bound'),prompt_entity_id=enum(*pids),candidate_prompt_entity_ids=dict(type='array',items=S,maxItems=0),witness_frame_ids=dict(type='array',items=I,minItems=1)),
        obj(**common,status=enum('unbound'),prompt_entity_id=dict(type='null'),candidate_prompt_entity_ids=dict(type='array',items=S,maxItems=0),witness_frame_ids=dict(type='array',items=I,maxItems=0))]}),
        queries=arr(obj(prompt_entity_id=enum(*pids),detection_query=S)))

def normalize_binding(raw, payload):
    """Normalize duplicate prompt entity bindings to the local entity with most witness frames."""
    raw = copy.deepcopy(raw)
    bound_pids = {}
    for r in raw.get('bindings', []):
        if r.get('status') == 'bound':
            bound_pids.setdefault(r.get('prompt_entity_id'), []).append(r)
    for pid, rows in bound_pids.items():
        if len(rows) > 1:
            rows.sort(key=lambda r: len(r.get('witness_frame_ids', [])), reverse=True)
            for r in rows[1:]:
                r['status'] = 'unbound'
                r['prompt_entity_id'] = None
                r['witness_frame_ids'] = []
                r['candidate_prompt_entity_ids'] = []
                r['reason'] = (r.get('reason', '') + ' [normalized: prompt entity already bound to local entity with more witness frames]').strip()
    return raw


def binding_errors(raw,payload):
    """Return (every problem, normalized binding); normalize_binding runs first as before."""
    raw = normalize_binding(raw, payload)
    entities={e['entity_id']:e for e in payload['entities']};pids={p['prompt_entity_id'] for p in payload['prompt_entities']}
    errors=[]
    ids=[r['entity_id'] for r in raw['bindings']]
    if len(ids)!=len(set(ids)) or set(ids)!=set(entities):
        errors.append(f'Binding inventory must be exact once (missing local entities {sorted(set(entities)-set(ids))}; unknown {sorted(set(ids)-set(entities))}; repeated {sorted({i for i in ids if ids.count(i)>1})})')
    used=set()
    for index,r in enumerate(raw['bindings']):
        where=f'bindings[{index}] entity {r["entity_id"]}'
        if not r['reason'].strip():errors.append(f'Empty reason ({where})')
        if r['status']=='bound':
            pid=r['prompt_entity_id'];entity=entities.get(r['entity_id'])
            valid={o['frame_id'] for o in entity['observations'] if o['box_xyxy'] is not None} if entity else set()
            if pid not in pids:errors.append(f'Unsupported/duplicate binding ({where}: unknown prompt_entity_id {pid!r})')
            elif pid in used:errors.append(f'Unsupported/duplicate binding ({where}: prompt entity {pid!r} is already bound to another local entity)')
            if not r['witness_frame_ids']:errors.append(f'Unsupported/duplicate binding ({where}: bound entity needs witness_frame_ids)')
            elif not set(r['witness_frame_ids'])<=valid:errors.append(f'Unsupported/duplicate binding ({where}: witness frames {sorted(set(r["witness_frame_ids"])-valid)} have no detected box for this entity; frames with boxes are {sorted(valid)})')
            used.add(pid)
        elif r['prompt_entity_id'] is not None or r['witness_frame_ids'] or r['candidate_prompt_entity_ids']:
            errors.append(f'Unbound field inconsistency ({where}: unbound requires prompt_entity_id null and empty witness/candidate lists)')
    queries=raw['queries'];qids=[r['prompt_entity_id'] for r in queries]
    if len(qids)!=len(set(qids)) or set(qids)!=pids:
        errors.append(f'Queries must cover prompt inventory (missing {sorted(pids-set(qids))}; unknown {sorted(set(qids)-pids)}; repeated {sorted({q for q in qids if qids.count(q)>1})})')
    for q in queries:
        t=q['detection_query']
        if not t.strip() or not t.endswith('.') or '\n' in t or len(t)>180:
            errors.append(f'Invalid detection query (prompt entity {q["prompt_entity_id"]!r}: must be one nonempty line ending with "." and at most 180 characters)')
    return errors,raw

def validate_binding(raw,payload):
    errors,raw=binding_errors(raw,payload)
    if errors:raise ValueError('; '.join(errors))
    return raw

def coverage(payload,binding,frames):
    by={r['prompt_entity_id']:r['entity_id'] for r in binding['bindings'] if r['status']=='bound'}
    entities={e['entity_id']:e for e in payload['entities']};queries={r['prompt_entity_id']:r['detection_query'] for r in binding['queries']};fids=[f['frame_id'] for f in frames];rows=[]
    for p in payload['prompt_entities']:
        pid=p['prompt_entity_id'];eid=by.get(pid);observed=[] if eid is None else [o['frame_id'] for o in entities[eid]['observations'] if o['box_xyxy'] is not None]
        gaps=[f for f in fids if f not in observed];required=p['expectation']=='required'
        rows.append(dict(prompt_entity_id=pid,entity_id=eid,expectation=p['expectation'],observed_frame_ids=observed,missing_detection_frame_ids=gaps if required else [],query=queries[pid],status='covered' if observed and not gaps else 'partial' if observed else 'uncovered' if required else 'not_required'))
    return rows

def bind_one(case,out,shot,registry,narrative,model,reasoning):
    sid=shot['shot_id'];payload=own_payload(case,shot,registry,narrative)
    folder=out/'calls'/f'{sid}_binding'
    audit_path=folder.parent/f'{folder.name}_repair_audit.json'
    if audit_path.exists() and read(audit_path).get('status')=='passed':
        if read(folder/'input.json')!=payload:raise ValueError('Changed binding input on resume')
        raw=validate_binding(read(Path(read(audit_path)['rounds'][-1]['call_folder'])/'response.json'),payload)
    elif (folder/'status.json').exists() and read(folder/'status.json')['status']=='success' and not audit_path.exists():
        if read(folder/'input.json')!=payload:raise ValueError('Changed binding input on resume')
        raw=validate_binding(read(folder/'response.json'),payload)
    else:
        raw = None
        schema=binding_schema([p['prompt_entity_id'] for p in payload['prompt_entities']])
        for attempt in range(1, 4):
            archive_failed_attempt(folder)
            try:
                # All binding problems go back to the model together in the
                # same conversation; only transport failures restart afresh.
                raw,_,_,_=repair_loop.call_with_repair(folder,payload,[dict(f,shot_id=sid) for f in shot['frames']],1800,
                    prompt_path=B/'prompts/gs_shot_prompt_binding_v1.txt',schema=schema,model=model,reasoning=reasoning,
                    collect_errors=lambda r:binding_errors(r,payload),stage=f'{sid} prompt binding')
                break
            except Exception as exc:
                if attempt == 3 or 'repair rounds' in str(exc):
                    raise
    rows=coverage(payload,raw,shot['frames']);save(out/'shots'/sid/'binding_initial.json',raw);save(out/'shots'/sid/'coverage_initial.json',rows)
    return sid,payload,raw,rows

def archive_failed_attempt(folder):
    """Move an interrupted attempt (call, its repair calls and audit) aside; never delete billed calls."""
    siblings=[p for p in folder.parent.glob(folder.name+'*') if p.name==folder.name or p.name.startswith(folder.name+'_repair_')]
    if not siblings:return
    if folder.exists() and read(folder/'status.json')['status']=='running':raise ValueError('Refuse concurrent call replacement')
    i=1
    while any(folder.parent.glob(f'{folder.name}_failed{i}*')):i+=1
    for p in siblings:p.rename(p.with_name(p.name.replace(folder.name,f'{folder.name}_failed{i}',1)))

def materialize_grounding(original, payload, own, new_frames, binding, coverage_rows):
    """Attach one deterministic GDINO box per target/frame without a VLM review.

    Grounding DINO is run separately for each requested prompt instance and
    carries that prompt_entity_id in its raw output. For multiple candidates
    from the same detector query/frame, retain the highest score (then ID);
    retain the rest as explicitly rejected detector candidates. This only
    fills missing schedule rows and never changes an original WeDetect box.
    """
    candidates={d['candidate_id']:(f['frame_id'],d) for f in new_frames for d in f['detections']}
    pending={r['prompt_entity_id']:set(r['missing_detection_frame_ids']) for r in coverage_rows if r['missing_detection_frame_ids']}
    old={e['entity_id']:e for e in original['entities']}
    oldbound={r['entity_id']:r['prompt_entity_id'] for r in binding['bindings'] if r['status']=='bound'}
    byprompt={pid:eid for eid,pid in oldbound.items()}
    prompt_names={p['prompt_entity_id']:p['name'] for p in own['prompt_entities']}
    eligible={}
    for cid,(fid,c) in candidates.items():
        pid=c.get('prompt_entity_id')
        if pid in pending and fid in pending[pid]:
            eligible.setdefault((pid,fid),[]).append((cid,c))
    selected={}
    for key,rows in eligible.items():
        cid,c=sorted(rows,key=lambda row:(-row[1]['score'],row[0]))[0]
        selected[cid]=(key[0],key[1])
    canonical=dict(shot_id=original['shot_id'],
        entities=[{k:copy.deepcopy(e[k]) for k in ['entity_id','name','candidate_ids']} for e in original['entities']],
        rejected_detections=copy.deepcopy(original['rejected_detections']))
    maxid=max([int(e[1:]) for e in old if e.startswith('e') and e[1:].isdigit()]+[0])
    missing_pids=[pid for pid in pending if pid not in byprompt and any(p==pid for p,_ in selected.values())]
    created={pid:f'e{maxid+i}' for i,pid in enumerate(sorted(missing_pids),1)}
    canonical['entities'] += [dict(entity_id=eid,name=prompt_names[pid],candidate_ids=[]) for pid,eid in created.items()]
    target={e['entity_id']:e for e in canonical['entities']}
    for cid,(fid,c) in candidates.items():
        selected_row=selected.get(cid)
        if selected_row is None:
            canonical['rejected_detections'].append(dict(candidate_id=cid,reason='Not the highest-score valid Grounding DINO candidate for its requested prompt entity and frame.'))
            continue
        pid,_=selected_row; eid=byprompt.get(pid,created.get(pid))
        if eid is None: raise ValueError('Selected recovery candidate lacks a target entity')
        if eid in old and any(o['frame_id']==fid and o['box_xyxy'] is not None for o in old[eid]['observations']):
            raise ValueError('Grounding recovery cannot replace an original box')
        target[eid]['candidate_ids'].append(cid)
    merged=copy.deepcopy(payload)
    byfid={f['frame_id']:f for f in merged['frames']}
    for f in new_frames:byfid[f['frame_id']]['detections']+=copy.deepcopy(f['detections'])
    result=io.validate_result(canonical,merged)
    for e in result['entities']:
        for o in e['observations']:
            if o['box_candidate_id'] in candidates:
                o['reason']='Original Grounding DINO recovery box; highest score for its requested prompt entity in this frame; coordinates unchanged.'
        if e['entity_id'] in old:
            for before,after in zip(old[e['entity_id']]['observations'],e['observations']):
                if before['box_xyxy'] is not None and (before['box_xyxy']!=after['box_xyxy'] or before['box_candidate_id']!=after['box_candidate_id']):
                    raise ValueError('Original observation changed')
    final=copy.deepcopy(binding)
    for pid,eid in created.items():
        obs=next(x for x in result['entities'] if x['entity_id']==eid)['observations']
        final['bindings'].append(dict(entity_id=eid,status='bound',prompt_entity_id=pid,candidate_prompt_entity_ids=[],
            witness_frame_ids=[o['frame_id'] for o in obs if o['box_xyxy'] is not None],
            reason='Directly recovered by the prompt-targeted Grounding DINO query.'))
    return result,merged,canonical,final

def recover_one(case,out,shot,item):
    sid,own,binding,rows=item;path=case/'entities/shots'/sid
    original=read(path/'entities.json');payload=read(path/'input.json');newframes=[]
    for f in shot['frames']:
        p=out/'grounding'/sid/f"frame_{f['frame_id']:06d}.json"
        if p.exists():
            d=read(p)
            newframes.append(dict(frame_id=f['frame_id'],detections=[x for x in d['detections'] if x['valid_box']]))
    candidates=[d for f in newframes for d in f['detections']]
    if candidates:
        result,merged,canonical,final=materialize_grounding(original,payload,own,newframes,binding,rows)
    else:
        result,merged,canonical,final=original,payload,read(path/'response.json'),binding
    updated=dict(own,entities=result['entities']);validate_binding(final,updated)
    finalcov=coverage(updated,final,shot['frames']);dest=out/'entities/shots'/sid
    save(dest/'entities.json',result);save(dest/'input.json',merged);save(dest/'response.json',canonical)
    save(out/'shots'/sid/'binding_final.json',final);save(out/'shots'/sid/'coverage_final.json',finalcov)
    return dict(shot_id=sid,initial_entities=len(original['entities']),final_entities=len(result['entities']),
        initial_coverage=rows,final_coverage=finalcov,new_candidates=len(candidates),final_bindings=final['bindings'])

def run(case,registry_path,out=None,workers=2,grounding_python=PYTHON,device='cpu',narrative_path=None,gpu=None,gpu_uuid=None,resume=False,model='gpt-6-astra',reasoning='medium'):
    case=Path(case).resolve();out=Path(out).resolve() if out else case/'shot_prompt_recovery'
    if out.exists() and not resume:raise FileExistsError('Use fresh recovery output or explicit --resume')
    if resume:
        previous=read(out/'run.json')
        if previous['status']!='failed':raise ValueError('Resume only failed runs')
        if any(sha(p)!=h for p,h in read(out/'source_hashes.json').items()):raise ValueError('Changed source on resume')
        if read(out/'prompt_registry.json')!=read(registry_path):raise ValueError('Changed registry on resume')
        save(out/'attempts'/f"run_{previous['started']}.json",previous)
    if (case/'inputs').exists() and any((case/'inputs').glob('*.json')):raise ValueError('Run recovery before geometry input freeze; use a fresh case for replays')
    io.safe_compute();shots=io.load_manifest(case/'raw_manifest.json');narrative=read(narrative_path or case/'narrative.json');registry=validate_registry(read(registry_path),shots,narrative)
    if not registry['entities']:raise ValueError('Empty registry')
    out.mkdir(parents=True,exist_ok=resume);start=time.time();state=dict(status='running',started=start,protocol='shot_prompt_recovery_v2_direct_grounding',workers=workers,device=device)
    save(out/'run.json',state);save(out/'prompt_registry.json',registry)
    sources={str(p):sha(p) for p in [Path(registry_path),Path(narrative_path or case/'narrative.json'),case/'raw_manifest.json']}
    sources.update({str(case/'entities/shots'/s['shot_id']/n):sha(case/'entities/shots'/s['shot_id']/n) for s in shots for n in ['input.json','entities.json','response.json']})
    save(out/'source_hashes.json',sources)
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:items=list(pool.map(lambda s:bind_one(case,out,s,registry,narrative,model,reasoning),shots))
        tasks=[]
        for shot,item in zip(shots,items):
            for f in shot['frames']:
                targets=[dict(prompt_entity_id=r['prompt_entity_id'],query=r['query']) for r in item[3] if f['frame_id'] in r['missing_detection_frame_ids']]
                if targets:tasks.append(dict(f,shot_id=shot['shot_id'],targets=targets))
        request=dict(frames=tasks,rounds=1,policy='required prompt instance frame gaps only; unresolved is not absent')
        if resume and (out/'grounding_request.json').exists() and read(out/'grounding_request.json')!=request:raise ValueError('Changed grounding requests on resume')
        save(out/'grounding_request.json',request)
        grounded=(out/'grounding/run.json').exists() and read(out/'grounding/run.json')['status']=='success'
        if grounded and read(out/'grounding/run.json')['request_sha256']!=sha(out/'grounding_request.json'):raise ValueError('Grounding request hash mismatch')
        if tasks and not grounded:
            env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',TOKENIZERS_PARALLELISM='false',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
            # Pi3X geometry injects a private dependency tree into the outer
            # pipeline.  Grounding-DINO must import its own vace environment,
            # otherwise that tree can shadow sklearn dependencies.
            env.pop('PYTHONPATH',None)
            if device=='cpu':env.update(ROCR_VISIBLE_DEVICES='-1',CUDA_VISIBLE_DEVICES='')
            cmd=[str(grounding_python),str(B/'scripts/gs_grounding_recovery.py'),'--request',str(out/'grounding_request.json'),'--output',str(out/'grounding'),'--device',device]
            if device=='cuda':
                if gpu is None or not gpu_uuid:raise ValueError('GPU mode requires physical index and UUID')
                cmd=[str(PYTHON),str(B/'experiments/study2_detection_only_fresh_20260918/guard_gpu.py'),str(gpu),gpu_uuid]+cmd
            save(out/'grounding_command.json',dict(command=cmd))
            with (out/'grounding.log').open('w') as f:subprocess.run(cmd,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
        with ThreadPoolExecutor(max_workers=workers) as pool:rows=list(pool.map(lambda pair:recover_one(case,out,*pair),zip(shots,items)))
        if any(sha(p)!=h for p,h in sources.items()):raise ValueError('Source mutated during recovery')
        save(out/'entities/manifest.json',dict(shots=shots));save(out/'results.json',dict(status='success',protocol=state['protocol'],shots=rows,source_entities=str(case/'entities'),rounds=1))
        state['status']='success'
    except BaseException as e:state.update(status='failed',error=repr(e));raise
    finally:state.update(seconds=time.time()-start);save(out/'run.json',state)
    return rows

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case',type=Path,required=True);p.add_argument('--registry',type=Path,required=True);p.add_argument('--out',type=Path);p.add_argument('--workers',type=int,default=2);p.add_argument('--grounding-python',type=Path,default=PYTHON);p.add_argument('--device',choices=['cpu','cuda'],default='cpu');p.add_argument('--narrative',type=Path);p.add_argument('--gpu',type=int);p.add_argument('--gpu-uuid');p.add_argument('--resume',action='store_true');p.add_argument('--model',default='gpt-6-astra');p.add_argument('--reasoning',choices=['low','medium','high','xhigh','max','ultra'],default='medium');a=p.parse_args()
    if a.workers<1:p.error('Positive workers required')
    run(a.case,a.registry,a.out,a.workers,a.grounding_python,a.device,a.narrative,a.gpu,a.gpu_uuid,a.resume,a.model,a.reasoning)
