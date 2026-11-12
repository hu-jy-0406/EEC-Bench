#!/usr/bin/env python3
"""Option B: freeze text-only requirements, independently verify pixels, aggregate in code."""
import argparse
from collections import defaultdict
import copy
import json
from pathlib import Path
import time

import gs_prompt_binding as binding
from gs_consistency_contract import obj, arr, enum, S, I

ROOT = Path(__file__).resolve().parents[1]
PROMPT = ROOT/'prompts/gs_prompt_alignment_b_v1.txt'
COMPILER = ROOT/'prompts/gs_prompt_alignment_compile_v1.txt'
read, save, sha = binding.read, binding.save, binding.sha
DIMENSIONS = ('presence', 'appearance', 'spatial', 'motion')
DIMENSION_PROFILE = 'four_dimensions_v1'
CLAIM = obj(claim_id=S, dimension=enum(*DIMENSIONS), entity_ids=arr(S), shot_ids=arr(S),
    predicate=S, expected=S, coordinate_frame=enum('none','screen','camera','entity','world'),
    quantifier=enum('exists','start','end','throughout','when_visible','ordered','cross_shot'),
    depends_on=arr(S), evidence=arr(obj(fact_id=S, quote=S)))
COMPILED = obj(claims=arr(CLAIM), excluded_requirements=arr(S))
REVIEW = obj(checks=arr(obj(claim_id=S,status=enum('satisfied','violated','unknown'),
    witnesses=arr(obj(shot_id=S,frame_id=I,observation=S)),blocked_by=arr(S),reason=S)))
COST_BASIS = 'Existing Astra standard API equivalent, not billed: USD/M uncached 10, cache-read 1, cache-write 12.5, output 50; existing long-context multipliers.'


def validate_contract(c, shots=None):
    import jsonschema
    if c.get('schema_version') != 'prompt_alignment_b_v1': raise ValueError('Expected prompt_alignment_b_v1')
    if any(q.get('dimension') == 'temporal' for q in c.get('claims', [])):
        raise ValueError('Temporal alignment was removed; migrate the contract with four-dimensions before scoring')
    ids=c['shot_ids']; shots=shots or [dict(shot_id=s) for s in ids]
    if not ids or len(ids)!=len(set(ids)) or any(not s or Path(s).name!=s or s in ('.','..') for s in ids): raise ValueError('Invalid shot population')
    binding.validate_registry(c['registry'],shots,c['narrative'])
    if c['registry']['shot_ids']!=ids: raise ValueError('Contract shot mismatch')
    facts={f['fact_id']:f['text'] for f in c['narrative']['facts']}
    if len(facts)!=len(c['narrative']['facts']): raise ValueError('Duplicate facts')
    if any(not t or t not in c['reference_text'] for t in facts.values()): raise ValueError('Facts must quote evaluation reference')
    jsonschema.validate({k:c[k] for k in ('claims','excluded_requirements')},COMPILED)
    pids={p['prompt_entity_id'] for p in c['registry']['entities']}; previous={}; signatures=set()
    for q in c['claims']:
        cid=q['claim_id']; scope=q['shot_ids']; entities=q['entity_ids']
        if not cid or cid in previous or not q['predicate'].strip() or not q['expected'].strip(): raise ValueError('Invalid/duplicate claim')
        if not scope or scope!=[s for s in ids if s in scope]: raise ValueError('Invalid claim shot scope/order')
        if not entities or len(entities)!=len(set(entities)) or not set(entities)<=pids: raise ValueError('Invalid claim entities')
        if not q['evidence'] or any(e['fact_id'] not in facts or not e['quote'] or e['quote'] not in facts[e['fact_id']] for e in q['evidence']):
            raise ValueError('Claims require exact reference quotes')
        deps=q['depends_on']
        if len(deps)!=len(set(deps)) or any(d not in previous or previous[d]['shot_ids']!=scope for d in deps):
            raise ValueError('Dependencies must precede child in same evidence scope; no cycles/foreign-shot judgments')
        signature=json.dumps({k:q[k] for k in ('dimension','entity_ids','shot_ids','predicate','expected','quantifier','coordinate_frame')},sort_keys=True)
        if signature in signatures: raise ValueError('Duplicate atomic requirement')
        signatures.add(signature); previous[cid]=q
    # Required/forbidden scheduled entities cannot disappear from the claim population.
    for e in c['registry']['entities']:
        for s in e['schedule']:
            if s['expectation'] in ('required','forbidden') and not any(q['dimension']=='presence' and
                    q['entity_ids']==[e['prompt_entity_id']] and q['shot_ids']==[s['shot_id']] and
                    q['predicate']==('present' if s['expectation']=='required' else 'absent') for q in c['claims']):
                raise ValueError('Missing scheduled presence claim')
    if not previous: raise ValueError('Empty claim population')
    return c


def four_dimension_contract(c):
    """Explicit text-only migration; never edit a frozen source in place."""
    c=copy.deepcopy(c)
    removed=[q for q in c['claims'] if q['dimension']=='temporal']
    ids={q['claim_id'] for q in removed}
    remaining=[q for q in c['claims'] if q['dimension']!='temporal']
    if any(set(q['depends_on']) & ids for q in remaining):
        raise ValueError('Retained claims depend on removed temporal claims; revise the text contract explicitly')
    c['claims']=remaining
    c['dimension_profile']=DIMENSION_PROFILE
    c['excluded_requirements']=list(c['excluded_requirements'])+[
        'User-disabled temporal requirement: '+q['claim_id']+' — '+q['expected'] for q in removed]
    c['dimension_migration']=dict(removed_claim_ids=[q['claim_id'] for q in removed],
        reason='User requested presence/appearance/spatial/motion only', video_evidence_consumed=False)
    return validate_contract(c)


def freeze(c, out):
    validate_contract(c); out=Path(out).resolve()
    out.mkdir(parents=True,exist_ok=False)
    save(out/'contract.json',c);save(out/'narrative.json',c['narrative']);save(out/'prompt_registry.json',c['registry'])
    (out/'reference.md').write_text(c['reference_text'])
    save(out/'freeze.json',dict(protocol='prompt_alignment_b_v1',frozen_at=time.time(),
        contract_sha256=sha(out/'contract.json'),population=len(c['claims']),dimension_profile=DIMENSION_PROFILE,
        video_evidence_consumed=False,claims_source=c.get('claims_source','text-only authoring')))
    return out/'contract.json'


def compile_reference(reference, out, timeout):
    """Separate text-only call; run before any generated-video scoring."""
    src=read(reference); out=Path(out).resolve()
    if set(src)!={'reference_text','shot_ids','narrative','registry'}:
        raise ValueError('Compiler accepts reference text/facts/registry/shot IDs only; no generated evidence')
    binding.validate_registry(src['registry'],[dict(shot_id=s) for s in src['shot_ids']],src['narrative'])
    if out.exists(): raise FileExistsError(out)
    binding.io.safe_compute();out.mkdir(parents=True)
    save(out/'reference_input.json',src)
    raw=binding.call(out/'calls/compiler',src,[],timeout,prompt_path=COMPILER,schema=COMPILED)
    c=dict(src,**raw,schema_version='prompt_alignment_b_v1',dimension_profile=DIMENSION_PROFILE,claims_source='text-only Astra/medium compiler')
    validate_contract(c);path=freeze(c,out/'frozen')
    save(out/'usage.json',usage_summary(out));return path


def review_batch(raw, claims, images):
    import jsonschema
    jsonschema.validate(raw,REVIEW)
    if [r['claim_id'] for r in raw['checks']]!=[q['claim_id'] for q in claims]: raise ValueError('Claim coverage/order changed')
    valid={(f['shot_id'],f['frame_id']) for f in images}; seen={}; result=[]
    for q,r in zip(claims,raw['checks']):
        r=copy.deepcopy(r)
        if not r['reason'].strip(): raise ValueError('Missing judgment reason')
        if any((w['shot_id'],w['frame_id']) not in valid or w['shot_id'] not in q['shot_ids'] or
               not w['observation'].strip() for w in r['witnesses']): raise ValueError('Invented or foreign witness')
        if r['status']!='unknown' and not r['witnesses']: raise ValueError('Decisive judgment without pixels')
        blockers=[d for d in q['depends_on'] if seen[d]['status']!='satisfied']
        if len(r['blocked_by'])!=len(set(r['blocked_by'])) or not set(r['blocked_by'])<=set(blockers): raise ValueError('Invalid dependency attribution')
        # Never count a child as visually true/false with an unestablished prerequisite.
        r['raw_status']=r['status']; r['dependency_adjusted']=bool(blockers and r['status']!='unknown')
        if blockers:r.update(status='unknown',blocked_by=blockers)
        elif r['blocked_by']:raise ValueError('Spurious blocker')
        seen[q['claim_id']]=r; result.append(dict(q,**r))
    return result


def counts(rows):
    t,f,u=(sum(r['status']==s for r in rows) for s in ('satisfied','violated','unknown')); n=t+f+u
    return dict(T=t,F=f,U=u,N=n,score=100*t/(t+f) if t+f else None,
                identification_interval=[100*t/n,100*(t+u)/n] if n else None)


def aggregate(rows):
    if any(r['dimension'] not in DIMENSIONS for r in rows):
        raise ValueError('Only the four active alignment dimensions may be aggregated')
    dimensions={}
    for dim in DIMENSIONS:
        rs=[r for r in rows if r['dimension']==dim]; buckets=defaultdict(list)
        for r in rs:buckets[(tuple(sorted(r['entity_ids'])),tuple(r['shot_ids']))].append(r)
        units=[dict(entity_ids=list(e),shot_ids=list(s),**counts(v)) for (e,s),v in buckets.items()]
        by_entity=defaultdict(list)
        for unit in units:by_entity[tuple(unit['entity_ids'])].append(unit)
        means=[]
        for ids,us in by_entity.items():
            known=[u['score'] for u in us if u['score'] is not None]
            means.append(dict(entity_ids=list(ids),score=sum(known)/len(known) if known else None,
                unknown_scope_count=sum(u['score'] is None for u in us),
                identification_interval=[sum(u['identification_interval'][k] for u in us)/len(us) for k in (0,1)]))
        known=[m['score'] for m in means if m['score'] is not None]
        micro=counts(rs)
        dimensions[dim]=dict(micro=micro,score=sum(known)/len(known) if known else None,
            identification_interval=[sum(m['identification_interval'][k] for m in means)/len(means) for k in (0,1)] if means else None,
            units=units,entity_groups=means,unknown_entity_group_count=sum(m['score'] is None for m in means))
    return dimensions


def usage_summary(out):
    from gs_entity_appearance_compact import cost
    calls=[]
    for path in sorted(Path(out).glob('calls/*/status.json')):
        s=read(path); us=s.get('usage',s.get('known_usage',[])); us=[us] if isinstance(us,dict) else us
        calls.append(dict(call=path.parent.name,status=s['status'],seconds=s['seconds'],usage=us,
            total_tokens=sum(u.get('input_tokens',0)+u.get('output_tokens',0) for u in us),
            standard_api_equivalent_usd=cost(us) if us else None))
    return dict(calls=calls,total_tokens=sum(c['total_tokens'] for c in calls),
        known_standard_api_equivalent_usd=sum(c['standard_api_equivalent_usd'] or 0 for c in calls),
        unavailable_call_costs=sum(c['standard_api_equivalent_usd'] is None for c in calls),cost_basis=COST_BASIS)


def evidence_for(case, scope, visual, bindings, shots, sources):
    """Original own-shot boxes/cameras, no motion labels, fused boxes or prior scores."""
    from gs_shot_motion import classification_geometry
    images=[dict(f,shot_id=s['shot_id']) for s in shots if s['shot_id'] in scope for f in s['frames']]
    graphs=[]
    for sid in scope:
        path=case/'selected'/f'{sid}_scene.json';sources[str(path)]=sha(path);g=read(path)
        graphs.append(dict(shot_id=sid,coordinate_system=g['coordinate_system'],cameras=g['cameras'],
            entities=[dict(entity_id=e['entity_id'],name=e['name'],frame_evidence=[dict(
                frame_id=r['frame_id'],visible=r['visible'],box_xyxy=r['box_xyxy'],
                geometry=classification_geometry(r.get('geometry'))) for r in e['frame_evidence']]) for e in g['entities']]))
    visible=[dict(global_entity_id=e['global_entity_id'],name=e['name'],
                  appearances=[a for a in e['appearances'] if a['shot_id'] in scope])
             for e in visual['entities'] if set(e['observed_shot_ids']) & set(scope)]
    # No out-of-shot names/observations or identity review text in own-shot calls.
    visible=[dict(global_entity_id=e['global_entity_id'],appearances=[{k:a[k] for k in
        ('shot_id','local_entity_id','name','observed_frame_ids','observations')} for a in e['appearances']]) for e in visible]
    gids={e['global_entity_id'] for e in visible}
    bound=[{k:r[k] for k in ('global_entity_id','status','prompt_entity_id','candidate_prompt_entity_ids')} for r in bindings['bindings'] if r['global_entity_id'] in gids]
    return dict(graphs=graphs,visual_entities=visible,bindings=bound,
        image_order=[dict(index=i,shot_id=f['shot_id'],frame_id=f['frame_id'],timestamp_sec=f.get('timestamp_sec')) for i,f in enumerate(images)]),images


def run_batches(items, worker, workers):
    """Scopes have no cross-scope dependencies. Preserve order and drain on failure."""
    if not isinstance(workers,int) or not 1<=workers<=8:raise ValueError('workers must be 1..8')
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(worker,item) for item in items]
        return [future.result() for future in futures]


def run(case, contract, binding_path, out, timeout=1200, *, workers=1, input_transport='canonical'):
    case,contract,binding_path,out=map(lambda p:Path(p).resolve(),(case,contract,binding_path,out))
    if out.exists():raise FileExistsError('Fresh alignment output required')
    if not isinstance(workers,int) or not 1<=workers<=8:raise ValueError('workers must be 1..8')
    if input_transport not in ('canonical','compact'):raise ValueError('Unknown input transport')
    shots=read(case/'raw_manifest.json')['shots'];c=validate_contract(read(contract),shots)
    seal=contract.parent/'freeze.json'
    if seal.exists() and read(seal)['contract_sha256']!=sha(contract):raise ValueError('Frozen contract changed')
    b=read(binding_path);visual_path=case/'global_entities/global_entities.json';visual=read(visual_path)
    # Require binding of the exact reference and exact frozen visual population.
    binding_sources=read(binding_path.parent/'source_hashes.json')
    if binding_sources.get(str(visual_path))!=sha(visual_path) or read(binding_path.parent/'prompt_registry.json')!=c['registry']:
        raise ValueError('Stale or foreign binding reference/population')
    binding.materialize(dict(bindings=[{k:r[k] for k in binding.SCHEMA['properties']['bindings']['items']['properties'] if k in r} for r in b['bindings']]),c['registry'],visual)
    sources={str(p):sha(p) for p in (contract,binding_path,binding_path.parent/'source_hashes.json',visual_path,case/'raw_manifest.json',PROMPT,Path(__file__).resolve(),ROOT/'scripts/gs_prompt_binding.py',ROOT/'scripts/gs_shot_motion.py')}
    for s in shots:
        for f in s['frames']:
            if sha(f['path'])!=f['sha256']:raise ValueError('Original frame changed')
            sources[f['path']]=f['sha256']
    binding.io.safe_compute();out.mkdir(parents=True);save(out/'contract.json',c)
    batches={tuple(q['shot_ids']):[] for q in c['claims']}
    for q in c['claims']:batches[tuple(q['shot_ids'])].append(q)
    started=time.time();results=[];state=dict(status='running',source_case=str(case),frozen_frontend_reuse=True,workers=workers,input_transport=input_transport)
    save(out/'status.json',state)
    try:
        items=[]
        for i,(scope,claims) in enumerate(batches.items()):
            payload,images=evidence_for(case,scope,visual,b,shots,sources)
            fact_ids={v['fact_id'] for q in claims for v in q['evidence']}
            payload.update(protocol='prompt_alignment_b_v1',claims=claims,
                reference_facts=[f for f in c['narrative']['facts'] if f['fact_id'] in fact_ids],
                prompt_entities=[dict(prompt_entity_id=e['prompt_entity_id'],name=e['name'],description=e['description'],
                    schedule=[r for r in e['schedule'] if r['shot_id'] in scope]) for e in c['registry']['entities']])
            items.append((out/'calls'/f'{i:02d}_{"_".join(scope)}',payload,images,claims))
        if input_transport=='compact':
            path=ROOT/'scripts/gs_flow1_compact_payload.py';sources[str(path)]=sha(path)
        save(out/'source_hashes.json',sources)
        def review(item):
            folder,payload,images,claims=item
            raw=binding.call(folder,payload,images,timeout,prompt_path=PROMPT,schema=REVIEW,input_transport=input_transport)
            return review_batch(raw,claims,images)
        results=[row for batch in run_batches(items,review,workers) for row in batch]
        byid={r['claim_id']:r for r in results};results=[byid[q['claim_id']] for q in c['claims']]
        for p,h in sources.items():
            if sha(p)!=h:raise ValueError('Source changed during evaluation: '+p)
        result=dict(protocol='prompt_alignment_b_v1',dimension_profile=DIMENSION_PROFILE,status='success',source_case=str(case),
            contract_sha256=sha(contract),frozen_frontend_reuse=True,checks=results,dimensions=aggregate(results),
            scoring='Equal claims within entity/relationship+scope; equal scopes within entity/relationship; equal entity/relationship groups per dimension. Unknown excluded from conditional scores, retained in intervals. No overall score.',
            limitations='Sparse original keyframes only. Unknown is not success/absence. Intervals bound unknown values, not confidence intervals. No registered cross-shot numeric comparison. Prompt correspondence does not merge cross-scene visual identity.',
            **usage_summary(out))
        save(out/'results.json',result);write_report(out,result);state['status']='success';return result
    except BaseException as exc:state.update(status='failed',error=repr(exc));raise
    finally:
        state.update(seconds=time.time()-started,**usage_summary(out));save(out/'status.json',state)


def write_report(out,result):
    lines=['# Prompt alignment B','',result['scoring'],'','| Dimension | Score | T/F/U | Identification interval |','|---|---:|---|---|']
    for dim,d in result['dimensions'].items():
        m=d['micro'];lines.append(f'| {dim} | {d["score"]} | {m["T"]}/{m["F"]}/{m["U"]} | {d["identification_interval"]} |')
    lines+=['','## Frozen claims and visual evidence','','| ID | Scope | Requirement | Status | Evidence/reason |','|---|---|---|---|---|']
    for r in result['checks']:
        witness='; '.join(f'{w["shot_id"]}:{w["frame_id"]} {w["observation"]}' for w in r['witnesses'])
        cells=[r['claim_id'],','.join(r['shot_ids']),r['expected'],r['status'],r['reason']+' '+witness]
        lines.append('| '+' | '.join(v.replace('|','/').replace('\n',' ') for v in cells)+' |')
    lines+=['',result['limitations'],'',f'Tokens: {result["total_tokens"]}; standard API equivalent USD {result["known_standard_api_equivalent_usd"]:.6f}.',result['cost_basis']]
    (Path(out)/'report.md').write_text('\n'.join(lines)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);subs=p.add_subparsers(dest='phase',required=True)
    cp=subs.add_parser('compile');cp.add_argument('--reference',type=Path,required=True)
    fp=subs.add_parser('freeze');fp.add_argument('--draft',type=Path,required=True)
    mp=subs.add_parser('four-dimensions');mp.add_argument('--draft',type=Path,required=True)
    rp=subs.add_parser('run')
    for k in ('case','contract','binding'):rp.add_argument('--'+k,type=Path,required=True)
    for sub in (cp,fp,mp,rp):sub.add_argument('--out',type=Path,required=True)
    for sub in (cp,rp):sub.add_argument('--timeout',type=int,default=1200)
    rp.add_argument('--workers',type=int,default=1);rp.add_argument('--input-transport',choices=['canonical','compact'],default='canonical')
    a=p.parse_args()
    if a.phase=='freeze':print(freeze(read(a.draft),a.out))
    elif a.phase=='four-dimensions':print(freeze(four_dimension_contract(read(a.draft)),a.out))
    elif a.phase=='compile':print(compile_reference(a.reference,a.out,a.timeout))
    else:print(json.dumps({k:v['score'] for k,v in run(a.case,a.contract,a.binding,a.out,a.timeout,workers=a.workers,input_transport=a.input_transport)['dimensions'].items()}))


if __name__=='__main__':main()
