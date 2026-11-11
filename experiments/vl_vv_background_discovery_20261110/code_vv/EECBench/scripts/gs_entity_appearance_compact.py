#!/usr/bin/env python3
"""Compact all-appearance VLM scorer; native-pixel crop sheets, short text/output.

Canonical per-frame evidence and raw DINO scores are reused unchanged. This is
an explicit context reduction, not a lossless encoding of full-frame imagery.
"""
import argparse
import concurrent.futures
import json
import shutil
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from collections import Counter
import gs_entity_appearance as base
from gs_consistency_contract import obj,arr,S,I

ROOT=Path(__file__).resolve().parents[1]
PROTOCOL='entity_appearance_compact_v2'
PROMPT=ROOT/'prompts/appearance/entity_compact_v2.txt'
SCHEMA=obj(u=arr(dict(type='integer',enum=[0,1,2])),
    s=arr(dict(type=['integer','null'],enum=[0,25,50,75,100,None])),
    e=arr(arr(I)),why=dict(type='string',maxLength=160),
    limits=dict(type='string',maxLength=120),expected_changes=arr(S))
read,dump,sha=base.read,base.dump,base.sha


def sheets(payload,folder,max_side=1024):
    """Shelf pack in original appearance order; never rescale/reencode crop pixels."""
    from PIL import Image,ImageDraw
    folder.mkdir(parents=True,exist_ok=True)
    margin,gap,label=8,8,20
    result=[];rows=[];audit=[];panels=[];x=y=margin;rowheight=0;usedw=usedh=0
    def flush():
        if not panels:return
        canvas=Image.new('RGB',(usedw+margin,usedh+margin),(245,245,245));draw=ImageDraw.Draw(canvas)
        for idx,im,rect in panels:
            canvas.paste(im,(rect[0],rect[1]));draw.text((rect[0],rect[1]-label+3),f'A{idx}',fill=(0,0,0))
        path=folder/f'sheet_{len(result)}.png';canvas.save(path)
        for idx,im,rect in panels:
            if canvas.crop(rect).tobytes()!=im.tobytes():raise ValueError('Sheet changed crop pixels')
        result.append(dict(path=str(path.resolve()),sha256=sha(path),shot_id='sheet',frame_id=len(result)))
    for idx,a in enumerate(payload['appearances']):
        if sha(a['crop_path'])!=a['crop_sha256']:raise ValueError('Original crop changed')
        with Image.open(a['crop_path']) as image:im=image.convert('RGB')
        w,h=im.size;cellw=max(w,40);cellh=h+label
        if x>margin and x+cellw+margin>max_side:x=margin;y+=rowheight+gap;rowheight=0
        if panels and y+cellh+margin>max_side:
            flush();panels=[];x=y=margin;rowheight=0;usedw=usedh=0
        rect=[x,y+label,x+w,y+label+h];sheet=len(result)
        panels.append((idx,im,rect));rowheight=max(rowheight,cellh);usedw=max(usedw,x+cellw);usedh=max(usedh,y+cellh)
        origin=a['derived_crop_xyxy'];boxes=[[b['box_xyxy'][j]-origin[j%2] for j in range(4)] for b in a['candidates']]
        rows.append([a['shot_id'],a['frame_id'],a['timestamp_sec'],sheet,rect,boxes])
        audit.append(dict(index=idx,appearance_id=a['appearance_id'],crop_path=a['crop_path'],crop_sha256=a['crop_sha256'],sheet_index=sheet,rect=rect,size=[w,h]))
        x+=cellw+gap
    flush()
    return rows,result,audit


def wire_payload(payload,rows):
    # Exact relevant narrative text retained. Files/hashes/confidences/local provenance stay local.
    return dict(entity=payload['global_entity_id'],name=payload['name'],
                facts=payload['normal_story_prompt']['facts'],rows=rows)


def expand(raw,payload):
    import jsonschema
    jsonschema.validate(raw,SCHEMA)
    n=len(payload['appearances'])
    if len(raw['u'])!=n or len(raw['s'])!=4 or len(raw['e'])!=4:raise ValueError('Wrong coverage or dimension lengths')
    if not raw['why'].strip():raise ValueError('Missing concise explanation')
    for score,ids in zip(raw['s'],raw['e']):
        if len(ids)!=len(set(ids)) or any(i<0 or i>=n for i in ids):raise ValueError('Invalid/duplicate panel evidence')
        if score is not None and sum(raw['u'][i]>0 for i in ids)<2:raise ValueError('Need two usable/partial witnesses')
    facts={f['fact_id'] for f in payload['normal_story_prompt']['facts']}
    if not set(raw['expected_changes'])<=facts:raise ValueError('Unknown narrative fact')
    vals=[s for s in raw['s'] if s is not None]
    result=dict(global_entity_id=payload['global_entity_id'],
        appearance_checks=[dict(appearance_id=a['appearance_id'],usability=['unusable','partial','usable'][raw['u'][i]],reason='Compact per-panel status; see shared explanation/limitations.') for i,a in enumerate(payload['appearances'])],
        dimensions={dim:dict(score=score,evidence_appearance_ids=[payload['appearances'][i]['appearance_id'] for i in ids],reason='Shared explanation: '+raw['why']) for dim,score,ids in zip(base.DIMS,raw['s'],raw['e'])},
        score=sum(vals)/len(vals) if vals else None,expected_changes=raw['expected_changes'],reason=raw['why'],limitations=raw['limits'])
    return base.validate_codex(result,payload)


def prepare(source,out,defer_dino=False):
    source,out=Path(source).resolve(),Path(out).resolve()
    # The baseline implementation and input hashes must still match; never rewrite history.
    m=base.verify_sources(source);out.mkdir(parents=True,exist_ok=False)
    sources={str(source/'manifest.json'):sha(source/'manifest.json'),str(PROMPT):sha(PROMPT),str(Path(__file__).resolve()):sha(__file__),
             str(ROOT/'scripts/gs_entity_appearance.py'):sha(ROOT/'scripts/gs_entity_appearance.py'),
             str(ROOT/'scripts/run_wedetect_shot_entities.py'):sha(ROOT/'scripts/run_wedetect_shot_entities.py')}
    entities=[]
    for entry in m['entities']:
        eid=entry['global_entity_id'];old=source/'entities'/eid;folder=out/'entities'/eid;folder.mkdir(parents=True)
        payload=read(old/'input.json')
        for name in (('input.json',) if defer_dino else ('input.json','dino.json')):
            shutil.copy2(old/name,folder/name);sources[str(old/name)]=sha(old/name)
        rows,images,audit=sheets(payload,folder/'sheets')
        wire=wire_payload(payload,rows)
        dump(folder/'wire.json',wire);dump(folder/'images.json',images);dump(folder/'sheet_audit.json',audit)
        entities.append(dict(**entry,sheets=len(images),wire_bytes=len(json.dumps(wire,ensure_ascii=False,separators=(',',':')).encode()),
                             wire_sha256=sha(folder/'wire.json'),sheet_audit_sha256=sha(folder/'sheet_audit.json'),images_sha256=sha(folder/'images.json')))
    dump(out/'manifest.json',dict(protocol=PROTOCOL,source=str(source),source_hashes=sources,entities=entities,
         model='gpt-6-astra',reasoning='medium',appearance_population='all original positive observations, no sampling',
         images='native-pixel crop contact sheets; repeated full-scene contexts omitted; original contexts retained locally',
         output='four score/status/evidence arrays, one shared short explanation; entity mean computed locally',
         dino='pending independent DINO branch' if defer_dino else 'unchanged original scores reused; no GPU run',
         dino_pending=defer_dino,aggregation=m['aggregation']))
    print(json.dumps(dict(out=str(out),entities=len(entities),sheets=sum(e['sheets'] for e in entities))),flush=True)


def bind_dino(out):
    """Join independent DINO results after scoring; never pass DINO to the VLM.

    The integrated report barrier waits for BOTH writers. Pin every result before
    marking the join complete; missing files fail instead of creating null scores.
    """
    out=Path(out);m=verify(out)
    if not m.get('dino_pending',False):
        return
    source=Path(m['source']);base.verify_sources(source)
    bindings=[]
    for e in m['entities']:
        old=source/'entities'/e['global_entity_id'];dest=out/'entities'/e['global_entity_id']
        if sha(old/'input.json')!=e['input_sha256']:
            raise ValueError('DINO source appearance population changed')
        bindings.append((old/'dino.json',dest/'dino.json',sha(old/'dino.json')))
    for src,dest,digest in bindings:
        shutil.copy2(src,dest)
        if sha(dest)!=digest:raise ValueError('DINO changed during join')
        m['source_hashes'][str(src)]=digest
    m.update(dino_pending=False,dino='independent DINO branch joined after Codex scoring')
    dump(out/'manifest.json',m)


def verify(out):
    m=read(out/'manifest.json')
    for p,h in m['source_hashes'].items():
        if sha(p)!=h:raise ValueError('Changed pinned source: '+p)
    for e in m['entities']:
        f=out/'entities'/e['global_entity_id']
        for name,key in [('input.json','input_sha256'),('wire.json','wire_sha256'),('sheet_audit.json','sheet_audit_sha256'),('images.json','images_sha256')]:
            if sha(f/name)!=e[key]:raise ValueError('Changed prepared artifact: '+str(f/name))
    return m


def call(folder,payload,images,disabled,timeout):
    import run_wedetect_shot_entities as io
    folder.mkdir(parents=True,exist_ok=False)
    prompt=PROMPT.read_text()+'\nINPUT:\n'+json.dumps(payload,ensure_ascii=False,separators=(',',':'))
    (folder/'prompt.txt').write_text(prompt);dump(folder/'output.schema.json',SCHEMA);dump(folder/'input.json',payload)
    state=dict(status='running',started=time.time(),model='gpt-6-astra',reasoning='medium');dump(folder/'status.json',state)
    try:
        with tempfile.TemporaryDirectory(prefix='eec-appearance-') as tmp:
            command=[io.resolve_codex_bin('codex'),'--ask-for-approval','never','exec','--ignore-user-config','-c',disabled,'--ephemeral','--skip-git-repo-check',
                '--sandbox','read-only','--color','never','--json','--model','gpt-6-astra','-c','model_reasoning_effort="medium"',
                '-c','project_doc_max_bytes=0','-c','web_search="disabled"','--output-schema',str(folder/'output.schema.json'),
                '--output-last-message',str(folder/'response.json'),'--cd',tmp]
            for feature in ('shell_tool','unified_exec','view_image','apps','plugins','hooks','multi_agent','memories','skill_search','browser_use','computer_use','code_mode','code_mode_only','workspace_dependencies'):
                command+=['--disable',feature]
            for i,img in enumerate(images):
                target=Path(tmp)/f'image_{i}.png';shutil.copy2(img['path'],target)
                if sha(target)!=img['sha256']:raise ValueError('Sheet changed before call')
                command+=['--image',str(target)]
            command+=['-']
            dump(folder/'request.json',dict(command=command,images=images,prompt_sha256=sha(folder/'prompt.txt'),schema_sha256=sha(folder/'output.schema.json')))
            io.run_process(command,prompt,Path(tmp),folder/'events.jsonl',folder/'stderr.log',timeout)
        state.update(status='success',usage=io.audit_events(folder/'events.jsonl'))
        return read(folder/'response.json')
    except BaseException as exc:
        state.update(status='failed',error=str(exc));raise
    finally:
        state.update(ended=time.time(),seconds=time.time()-state['started']);dump(folder/'status.json',state)


def score(runs,workers,only,timeout):
    import run_wedetect_shot_entities as io
    disabled=io.disabled_skills_config();jobs=[]
    for out in runs:
        m=verify(out)
        for e in m['entities']:
            if not only or out.name+'/'+e['global_entity_id'] in only:jobs.append((out,e))
    def one(job):
        out,e=job;eid=e['global_entity_id'];f=out/'entities'/eid;p=read(f/'input.json')
        if (f/'codex.json').exists():
            result=read(f/'codex.json')
            if result['status']=='success':base.validate_codex(result['result'],p)
            return result
        if e['appearances']<2:result=dict(status='not_assessable',score=None,reason='Fewer than two appearances')
        else:
            try:
                raw=call(out/'calls'/eid,read(f/'wire.json'),read(f/'images.json'),disabled,timeout)
                expanded=expand(raw,p);result=dict(status='success',score=expanded['score'],result=expanded)
            except Exception as exc:result=dict(status='failed',score=None,error=str(exc))
        dump(f/'codex.json',result)
        print(json.dumps(dict(study=out.name,entity=eid,status=result['status'],score=result['score'],error=result.get('error'))),flush=True)
        return result
    started=time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:results=list(pool.map(one,jobs))
    print(json.dumps(dict(phase='scored',seconds=time.time()-started,failed=sum(r['status']=='failed' for r in results))),flush=True)
    if any(r['status']=='failed' for r in results):raise RuntimeError('Failures recorded; no automatic retries')


def cost(usage):
    # Standard API equivalent at official Astra prices verified 2026-09-20.
    total=0
    for u in usage:
        i,c,w,o=u['input_tokens'],u.get('cached_input_tokens',0),u.get('cache_write_input_tokens',0),u['output_tokens']
        im,om=(2,1.5) if i>272000 else (1,1)
        total+=((i-c-w)*10*im+c*im+w*12.5*im+o*50*om)/1e6
    return total


def report(runs,output):
    from PIL import Image
    rows=[];old_usage=[];new_usage=[];calls=[];all_coverage=0;inputs_old=inputs_new=0
    for out in runs:
        m=verify(out);source=Path(m['source'])
        for e in m['entities']:
            eid=e['global_entity_id'];folder=out/'entities'/eid
            if not (folder/'codex.json').exists():continue
            c=read(folder/'codex.json');old=read(source/'entities'/eid/'codex.json');p=read(folder/'input.json');d=read(folder/'dino.json')
            if c['status']=='failed':raise ValueError('Cannot report failed entity as valid')
            if c['status']=='success':
                base.validate_codex(c['result'],p)
                assert expand(read(out/'calls'/eid/'response.json'),p)==c['result']
            assert d==read(source/'entities'/eid/'dino.json')
            images=read(folder/'images.json');mapping=read(folder/'sheet_audit.json')
            assert [a['appearance_id'] for a in mapping]==[a['appearance_id'] for a in p['appearances']]
            for a in mapping:
                img=images[a['sheet_index']];assert sha(img['path'])==img['sha256']
                with Image.open(img['path']) as im,Image.open(a['crop_path']) as crop:
                    assert im.crop(a['rect']).tobytes()==crop.convert('RGB').tobytes()
                all_coverage+=1
            if c['status']=='success':
                status=read(out/'calls'/eid/'status.json');assert status['status']=='success';calls.append(status)
                old_usage+=read(source/'calls'/eid/'status.json')['usage'];new_usage+=status['usage']
                inputs_old+=len(read(source/'entities'/eid/'images.json'));inputs_new+=len(images)
            a,b=old['score'],c['score']
            rows.append(dict(study=out.name,entity=eid,name=e['name'],shots=e['observed_shot_ids'],old=a,new=b,
                delta=b-a if a is not None and b is not None else None,dino=d['score'],old_dimensions=[old.get('result',{}).get('dimensions',{}).get(k,{}).get('score') for k in base.DIMS],
                new_dimensions=[c.get('result',{}).get('dimensions',{}).get(k,{}).get('score') for k in base.DIMS],reason=c.get('result',{}).get('reason',''),limits=c.get('result',{}).get('limitations','')))
    def usage(us):
        u=Counter()
        for x in us:u.update(x)
        return dict(**u,total_tokens=u['input_tokens']+u['output_tokens'],api_equivalent_usd=cost(us))
    before,after=usage(old_usage),usage(new_usage)
    scored=[r for r in rows if r['delta'] is not None]
    summary=dict(protocol=PROTOCOL,entities=len(rows),calls=len(calls),all_appearances_pixel_audit=all_coverage,
        original_image_attachments=inputs_old,new_sheet_attachments=inputs_new,before=before,after=after,
        token_reduction=1-after['total_tokens']/before['total_tokens'],cost_reduction=1-after['api_equivalent_usd']/before['api_equivalent_usd'],
        equal_scores=sum(abs(r['delta'])<1e-8 for r in scored),scored_entities=len(scored),
        score_mae=sum(abs(r['delta']) for r in scored)/len(scored),max_score_delta=max(abs(r['delta']) for r in scored),
        wall_seconds=max(s['ended'] for s in calls)-min(s['started'] for s in calls),
        rates_source='https://developers.openai.com/api/docs/models/gpt-6-astra',rate_verified_date='2026-09-20',
        rows=rows)
    dump(output,summary)
    print(json.dumps({k:v for k,v in summary.items() if k!='rows'},ensure_ascii=False),flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['prepare','score','report']);p.add_argument('--source',type=Path);p.add_argument('--out',type=Path)
    p.add_argument('--runs',nargs='+',type=Path);p.add_argument('--only',nargs='*');p.add_argument('--workers',type=int,default=3);p.add_argument('--timeout',type=int,default=600)
    a=p.parse_args()
    if a.phase=='prepare':prepare(a.source,a.out)
    elif a.phase=='score':score([r.resolve() for r in a.runs],a.workers,a.only,a.timeout)
    else:report([r.resolve() for r in a.runs],a.out)
if __name__=='__main__':main()
