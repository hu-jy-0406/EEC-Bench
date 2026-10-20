#!/usr/bin/env python3
"""Text-only append-only Wan adapter; offline token hard gate and provenance audit."""
import argparse
import concurrent.futures
import copy
import csv
import hashlib
import html
import importlib.util
import json
import os
from pathlib import Path
import socket
import statistics
import sys
import tempfile
import threading
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SCRIPTS = ROOT / 'EECBench/scripts'
sys.path.insert(0, str(SCRIPTS))
import run_wedetect_shot_entities as io
from gs_consistency_contract import obj, arr, S

PRIORITY = ROOT / 'EECBench/experiments/source_video_priority_20260921'
SOURCE = ROOT / 'EECBench/experiments/source_video_400_20260920/deliverables/candidates_400.jsonl'
QUEUE = PRIORITY / 'generation_queue_400.jsonl'
FEAS = ROOT / 'EECBench/experiments/generation_feasibility_20260921'
WRAPPER = FEAS / 'repos/Wan2.2/wan/modules/tokenizers.py'
TOKPATH = FEAS / 'models/Wan2.2-T2V-A14B/google/umt5-xxl'
SCHEMA = obj(episodes=arr(obj(episode_id=S, shots=arr(obj(shot_id=S,
    additions=arr(obj(text=S, target_quote=S, evidence=arr(obj(source_shot_id=S, quote=S)), reason=S)),
    unresolved_dependencies=arr(S))))))
LOCK = threading.Lock()
TOK = None
DISABLED = None
read, dump, sha = io.read, io.dump, io.sha


def tokens(text):
    global TOK
    with LOCK:
        if TOK is None:
            if os.environ.get('USE_TORCH') != '0': raise ValueError('Require USE_TORCH=0')
            spec = importlib.util.spec_from_file_location('wan_tokenizer', WRAPPER)
            mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
            TOK = mod.HuggingfaceTokenizer(str(TOKPATH), seq_len=512, clean='whitespace', local_files_only=True)
        kw = dict(return_tensors=None, padding=False, add_special_tokens=True, return_attention_mask=False)
        full = TOK(text, truncation=False, **kw)[0]
        prod = TOK(text, **kw)[0]
        if len(full) > 512 or full != prod: raise ValueError('512-token hard gate failed')
        return len(full)


def materialize(original, additions):
    return original + ((' ' + ' '.join(a['text'] for a in additions)) if additions else '')


def validate(result, payload, check_tokens=True):
    import jsonschema
    jsonschema.validate(result, SCHEMA)
    if [x['episode_id'] for x in result['episodes']] != [x['episode_id'] for x in payload['episodes']]:
        raise ValueError('Episode coverage/order changed')
    for ep, src in zip(result['episodes'], payload['episodes']):
        if [s['shot_id'] for s in ep['shots']] != [s['shot_id'] for s in src['shots']]:
            raise ValueError('Shot coverage/order changed')
        prior = {'global': src['global_prompt']}
        for shot, orig in zip(ep['shots'], src['shots']):
            text = orig['generation_prompt_en']
            if shot['unresolved_dependencies']:
                raise ValueError('Unresolved dependency: ' + src['episode_id'] + '/' + shot['shot_id'] + ': ' + str(shot['unresolved_dependencies']))
            seen = set()
            for a in shot['additions']:
                if not a['text'].strip() or a['text'] != a['text'].strip() or '\n' in a['text']:
                    raise ValueError('Invalid append text')
                if not a['target_quote'] or a['target_quote'] not in text:
                    raise ValueError('Target quote not exact in ' + src['episode_id'] + '/' + shot['shot_id'])
                if not a['reason'].strip() or not a['evidence']:
                    raise ValueError('Missing dependency reason/evidence')
                if a['text'] in seen or a['text'].casefold() in text.casefold():
                    raise ValueError('Literal redundant addition')
                seen.add(a['text'])
                for ev in a['evidence']:
                    if ev['source_shot_id'] not in prior or not ev['quote'] or ev['quote'] not in prior[ev['source_shot_id']]:
                        raise ValueError('Nonexact or future evidence: ' + src['episode_id'] + '/' + shot['shot_id'] + ': ' + str(ev))
            final = materialize(text, shot['additions'])
            assert final[:len(text)] == text
            if check_tokens: tokens(final)
            prior[orig['shot_id']] = text
    return result


def prepare():
    io.safe_compute()
    rows = [json.loads(x) for x in QUEUE.read_text().splitlines()]
    assert len(rows) == 400 and sum(len(r['shots']) for r in rows) == 2000
    if (HERE / 'manifest.json').exists(): raise FileExistsError('Already prepared')
    jobs = []
    for offset in range(0, len(rows), 4):
        payload = {'episodes': [{
            'episode_id': r['episode_id'], 'global_prompt': r['global_prompt'],
            'shots': [{k: s[k] for k in ('shot_id', 'scene_id', 'generation_prompt_en')} for s in r['shots']]
        } for r in rows[offset:offset+4]]}
        bid = f'b{offset//4:03d}'
        path = HERE / 'batches' / bid / 'input.json'; dump(path, payload)
        jobs.append(dict(batch_id=bid, episode_ids=[x['episode_id'] for x in payload['episodes']], input_sha256=sha(path)))
    dump(HERE / 'output.schema.json', SCHEMA)
    pricing = ROOT / 'EECBench/experiments/source_video_400_20260920/pricing.json'
    dump(HERE / 'pricing.json', read(pricing))
    dump(HERE / 'manifest.json', dict(protocol='wan_context_append_v1', model='gpt-6-astra', reasoning='medium',
        source=str(SOURCE), source_sha256=sha(SOURCE), queue=str(QUEUE), queue_sha256=sha(QUEUE),
        original_text_policy='byte_exact_prefix_no_rewrite', token_limit_including_special=512,
        batches=jobs, created=time.time(), source_hashes={str(p):sha(p) for p in
            [HERE/'run.py',HERE/'rules.txt',HERE/'review.txt',HERE/'base.txt',HERE/'output.schema.json',WRAPPER]}))
    print(json.dumps({'prepared_episodes':400,'batches':len(jobs)}), flush=True)


def verify_sources():
    m = read(HERE/'manifest.json')
    assert sha(SOURCE) == m['source_sha256'] and sha(QUEUE) == m['queue_sha256']
    for p,h in m['source_hashes'].items():
        if sha(p) != h: raise ValueError('Prepared protocol changed: ' + p)
    for j in m['batches']:
        assert sha(HERE/'batches'/j['batch_id']/'input.json') == j['input_sha256']
    return m


def call(folder, payload, review=False, feedback=None, timeout=600):
    folder.mkdir(parents=True, exist_ok=False)
    prompt = ((HERE/'review.txt').read_text() if review else '') + (HERE/'rules.txt').read_text()
    if feedback:
        prompt += '\nThe previous attempt failed a mechanical gate. Correct it without changing the constraints:\n' + feedback
    prompt += '\nINPUT_JSON:\n' + json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    (folder/'prompt.txt').write_text(prompt)
    dump(folder/'input.json',payload)
    state=dict(status='running', started=time.time(),model='gpt-6-astra',reasoning='medium')
    dump(folder/'status.json',state)
    try:
        with tempfile.TemporaryDirectory(prefix='eec-wan-text-') as tmp:
            cmd=['codex','--ask-for-approval','never','exec','--ignore-user-config','-c',DISABLED,
                 '--ephemeral','--skip-git-repo-check','--sandbox','read-only','--color','never','--json',
                 '--model','gpt-6-astra','-c','model_reasoning_effort="medium"',
                 '-c','project_doc_max_bytes=0','-c','web_search="disabled"',
                 '-c','model_instructions_file='+json.dumps(str(HERE/'base.txt')),
                 '--output-schema',str(HERE/'output.schema.json'),
                 '--output-last-message',str(folder/'response.json'),'--cd',tmp]
            for f in ('shell_tool','unified_exec','view_image','apps','plugins','hooks','multi_agent','memories',
                      'skill_search','browser_use','computer_use','code_mode','code_mode_only','workspace_dependencies'):
                cmd += ['--disable',f]
            cmd += ['-']
            dump(folder/'request.json',dict(command=cmd,prompt_sha256=sha(folder/'prompt.txt')))
            io.run_process(cmd,prompt,Path(tmp),folder/'events.jsonl',folder/'stderr.log',timeout)
        state.update(status='success',usage=io.audit_events(folder/'events.jsonl'))
        return read(folder/'response.json')
    except BaseException as e:
        state.update(status='failed',error=str(e))
        if (folder/'events.jsonl').exists():
            try: state['known_usage']=io.audit_events(folder/'events.jsonl')
            except Exception: state['usage_unavailable']=True
        raise
    finally:
        state['seconds']=time.time()-state['started'];dump(folder/'status.json',state)


def run_batch(job):
    folder=HERE/'batches'/job['batch_id']; payload=read(folder/'input.json')
    try:
        if (folder/'final.json').exists():
            validate(read(folder/'final.json'),payload)
            return dict(batch=job['batch_id'],status='cached')
        stages=[('draft',False),('review',True)]
        for name,is_review in stages:
            path=folder/(name+'.json')
            if path.exists():
                candidate=validate(read(path),payload)
                continue
            wire=copy.deepcopy(payload)
            if is_review: wire['proposal']=read(folder/'draft.json')
            feedback=None
            for attempt in range(1,4):
                dest=folder/'calls'/f'{name}_{attempt}'
                try:
                    if dest.exists() and (dest/'response.json').exists(): candidate=read(dest/'response.json')
                    elif dest.exists():
                        feedback='Previous call failed or timed out; supply complete valid output.';continue
                    else: candidate=call(dest,wire,review=is_review,feedback=feedback)
                    validate(candidate,payload)
                    dump(dest/'validation.json',dict(status='pass'))
                    dump(path,candidate)
                    break
                except Exception as e:
                    feedback=str(e)
                    dump(dest/'validation.json',dict(status='failed',error=feedback))
            else: raise ValueError(name+' did not pass: '+str(feedback))
        dump(folder/'final.json',candidate)
        state=dict(batch=job['batch_id'],status='success',episodes=len(payload['episodes']),
            changed_shots=sum(bool(s['additions']) for e in candidate['episodes'] for s in e['shots']))
    except Exception as e:
        state=dict(batch=job['batch_id'],status='failed',error=str(e))
    dump(folder/'status.json',state)
    print(json.dumps(state,ensure_ascii=False),flush=True)
    return state


def usage():
    prices=read(HERE/'pricing.json'); calls=[]; total={'input_tokens':0,'cached_input_tokens':0,'output_tokens':0}; amount=0.; unknown=0
    for p in sorted((HERE/'batches').glob('*/calls/*/status.json')):
        s=read(p); us=s.get('usage',s.get('known_usage',[])); us=[us] if isinstance(us,dict) else us
        cost=0.; valid=bool(us)
        for u in us:
            inp,cache,out=(u.get(k,0) for k in ('input_tokens','cached_input_tokens','output_tokens'))
            if not (0<=cache<=inp<=prices['max_input_tokens']) or u.get('cache_write_input_tokens',0): valid=False
            cost+=((inp-cache)*prices['input_usd_per_million']+cache*prices['cached_input_usd_per_million']+out*prices['output_usd_per_million'])/1e6
            for k in total: total[k]+=u.get(k,0)
        if valid: amount+=cost
        else: unknown+=1
        calls.append(dict(path=str(p),status=s['status'],seconds=s['seconds'],usage=us,standard_api_equivalent_usd=cost if valid else None))
    result=dict(calls=len(calls),usage=total,total_tokens=total['input_tokens']+total['output_tokens'],
        standard_api_equivalent_usd=amount if not unknown else None,known_subtotal_usd=amount,
        unavailable_or_inflight_costs=unknown,pricing=prices,rows=calls,actual_billed_amount_available=False)
    dump(HERE/'usage_cost.json',result)
    return result


def run(limit,workers):
    global DISABLED
    alloc=io.safe_compute();manifest=verify_sources();DISABLED=io.disabled_skills_config()
    jobs=manifest['batches'][:limit] if limit else manifest['batches']
    started=time.time();dump(HERE/'runtime.json',dict(status='running',started=started,allocation=alloc,host=socket.gethostname(),cpu_affinity=sorted(os.sched_getaffinity(0)),workers=workers,planned_batches=len(jobs)))
    tokens('Offline tokenizer warmup.')
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        states=list(pool.map(run_batch,jobs))
    u=usage();result=dict(status='failed' if any(s['status']=='failed' for s in states) else 'success',
        seconds=time.time()-started,planned_batches=len(jobs),failed=[s for s in states if s['status']=='failed'],
        total_tokens=u['total_tokens'],standard_api_equivalent_usd=u['standard_api_equivalent_usd'])
    dump(HERE/'run_summary.json',result); print(json.dumps(result,ensure_ascii=False),flush=True)


def export():
    io.safe_compute();manifest=verify_sources();all_final={}
    for job in manifest['batches']:
        folder=HERE/'batches'/job['batch_id']
        final=validate(read(folder/'final.json'),read(folder/'input.json'))
        for e in final['episodes']:
            if e['episode_id'] in all_final: raise ValueError('Duplicate episode')
            all_final[e['episode_id']]=e
    rows=[json.loads(x) for x in QUEUE.read_text().splitlines()]
    dest=HERE/'deliverables';dest.mkdir(exist_ok=True)
    output=[];flat=[];changed=0;additions=0
    for i,r in enumerate(rows):
        entry=dict(episode_id=r['episode_id'],generation_priority=i+1,shot_count=r['shot_count'],
                   target_duration_seconds=r['target_duration_seconds'],global_prompt_original=r['global_prompt'],
                   protocol='wan_context_append_v1',shots=[])
        for s,a in zip(r['shots'],all_final[r['episode_id']]['shots']):
            original=s['generation_prompt_en'];final=materialize(original,a['additions']);n=tokens(final);n0=tokens(original)
            changed+=bool(a['additions']);additions+=len(a['additions'])
            p=dest/'prompts'/r['episode_id']/(s['shot_id']+'.txt');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(final)
            entry['shots'].append(dict(shot_id=s['shot_id'],scene_id=s['scene_id'],target_duration_seconds=s['target_duration_seconds'],
                generation_prompt_en_original=original,wan_prompt_en=final,context_additions=a['additions'],
                wan_tokens_including_special=n,original_tokens_including_special=n0,prompt_file=str(p),
                original_sha256=hashlib.sha256(original.encode()).hexdigest(),wan_sha256=hashlib.sha256(final.encode()).hexdigest()))
            flat.append(dict(episode_id=r['episode_id'],generation_priority=i+1,shot_id=s['shot_id'],
                changed=bool(a['additions']),original_tokens=n0,wan_tokens=n,added_tokens=n-n0,prompt_file=str(p)))
        output.append(entry)
    for name,count in [('generation_queue_400',400),('core_100',100),('priority_200',200)]:
        (dest/(name+'.jsonl')).write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in output[:count]))
    for name,subset in [('stage2_additional_100',output[100:200]),('stage3_remaining_200',output[200:])]:
        (dest/(name+'.jsonl')).write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in subset))
    with (dest/'token_audit.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
    u=usage()
    audit=dict(episodes=len(output),shots=len(flat),changed_shots=changed,unchanged_shots=len(flat)-changed,
        additions=additions,wan_tokens_max=max(x['wan_tokens'] for x in flat),wan_tokens_mean=statistics.mean(x['wan_tokens'] for x in flat),
        over_512=0,all_originals_byte_exact_prefix=True,all_additions_exact_source_quoted=True,
        future_shot_evidence_count=0,all_shots_independent_model_reviewed=True,formal_schedule_compiled=False,
        source_sha256=sha(SOURCE),priority_queue_sha256=sha(QUEUE),generation_started=False,gpu_work=False,
        total_tokens=u['total_tokens'],standard_api_equivalent_usd=u['standard_api_equivalent_usd'])
    dump(HERE/'audit.json',audit)
    # Standalone review page, escaped original and appended spans.
    cards=[]
    for e in output:
        ss=[]
        for s in e['shots']:
            app=' '.join(a['text'] for a in s['context_additions'])
            ss.append('<h4>'+html.escape(s['shot_id'])+' — '+str(s['wan_tokens_including_special'])+' tokens</h4><p>'+html.escape(s['generation_prompt_en_original'])+(' <mark>'+html.escape(app)+'</mark>' if app else '')+'</p>')
        cards.append('<details><summary>'+str(e['generation_priority'])+' · '+html.escape(e['episode_id'])+'</summary>'+''.join(ss)+'</details>')
    (dest/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>Wan prompt context additions</title><style>body{max-width:1100px;margin:40px auto;font:16px/1.6 sans-serif}details{border-bottom:1px solid #ddd;padding:12px}mark{background:#fff0ae}</style><h1>Wan prompt context additions</h1><p>Original text is unchanged; appended descriptions are highlighted.</p>'+''.join(cards))
    print(json.dumps(audit,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('phase',choices=['prepare','run','export','usage']);ap.add_argument('--limit-batches',type=int,default=0);ap.add_argument('--workers',type=int,default=8)
    a=ap.parse_args()
    if a.phase=='prepare': prepare()
    elif a.phase=='run': run(a.limit_batches,a.workers)
    elif a.phase=='export': export()
    else:
        u=usage();print(json.dumps({k:u[k] for k in ['calls','total_tokens','standard_api_equivalent_usd','unavailable_or_inflight_costs']}))
