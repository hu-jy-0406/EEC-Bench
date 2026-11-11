#!/usr/bin/env python3
"""Frozen global registry -> all observed crops -> separate Codex/DINO scores."""
import argparse
import concurrent.futures
import hashlib
import json
import math
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
DIMS = ('structure_shape', 'color_texture_material', 'proportions', 'distinctive_details')
VERSION = 'entity_appearance_separate_v1'

def read(path): return json.loads(Path(path).read_text())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')

def crop_box(boxes, width, height):
    if not boxes: raise ValueError('No candidate boxes')
    for b in boxes:
        if len(b) != 4 or not all(math.isfinite(x) for x in b) or not (0 <= b[0] < b[2] <= width and 0 <= b[1] < b[3] <= height):
            raise ValueError('Invalid unchanged candidate box')
    x0,y0,x1,y1=min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)
    dx,dy=(x1-x0)*.1,(y1-y0)*.1
    return [max(0,math.floor(x0-dx)),max(0,math.floor(y0-dy)),min(width,math.ceil(x1+dx)),min(height,math.ceil(y1+dy))]

def prepare(case, out):
    from PIL import Image
    case,out=Path(case).resolve(),Path(out).resolve()
    out.mkdir(parents=True,exist_ok=False)
    registry_path=case/'global_entities/global_entities.json'
    reg=read(registry_path); manifest=read(case/'raw_manifest.json'); narrative=read(case/'narrative.json')
    sources={}
    def pin(path):
        path=str(Path(path).resolve()); sources[path]=sha(path); return sources[path]
    for path,digest in reg['source_hashes'].items():
        if path.endswith('.json') and pin(path)!=digest: raise ValueError('Frozen registry source changed: '+path)
    for p in (registry_path,case/'raw_manifest.json',case/'narrative.json'): pin(p)
    frames={(s['shot_id'],f['frame_id']):f for s in manifest['shots'] for f in s['frames']}
    for f in frames.values():
        if pin(f['path'])!=f['sha256']: raise ValueError('Frame hash mismatch')
    from gs_shot_prompt_recovery import active_entities_root
    entity_root=active_entities_root(case)
    candidates={}
    for s in manifest['shots']:
        inp=read(entity_root/'shots'/s['shot_id']/'input.json')
        candidates[s['shot_id']]={d['candidate_id']:(f,d) for f in inp['frames'] for d in f['detections']}
    rows=[]
    for entity in reg['entities']:
        eid=entity['global_entity_id']; folder=out/'entities'/eid; folder.mkdir(parents=True)
        apps=[]; missing=[]; attachments=[]
        # A VL/VV specified entity may hold several local entities in one shot (binding v2, 2026-11-02); their
        # appearance IDs then name the local entity so that crops do not collide. One local per shot keeps the old ID.
        locals_per_shot=Counter(local['shot_id'] for local in entity['appearances'])
        for local in entity['appearances']:
            sid=local['shot_id']
            for obs in local['observations']:
                if obs['exist'] is not True or obs['box_xyxy'] is None:
                    missing.append(dict(shot_id=sid,frame_id=obs['frame_id'],reason='No retained original detection; unknown, not absence.')); continue
                frame=frames[sid,obs['frame_id']]
                aid=f'{sid}_{local["local_entity_id"]}_f{obs["frame_id"]}' if locals_per_shot[sid]>1 else f'{sid}_f{obs["frame_id"]}'
                ds=[]
                for cid in obs['candidate_ids']:
                    cf,d=candidates[sid][cid]
                    if cf['frame_id']!=obs['frame_id']: raise ValueError('Wrong candidate frame')
                    ds.append(d)
                selected=[d for d in ds if d['candidate_id']==obs['box_candidate_id']]
                if len(selected)!=1 or selected[0]['box_xyxy']!=obs['box_xyxy']: raise ValueError('Changed canonical box')
                with Image.open(frame['path']) as im:
                    box=crop_box([d['box_xyxy'] for d in ds],*im.size)
                    crop=folder/(aid+'.png'); im.convert('RGB').crop(box).save(crop)
                app=dict(appearance_id=aid,shot_id=sid,local_entity_id=local['local_entity_id'],frame_id=obs['frame_id'],timestamp_sec=frame['timestamp_sec'],
                         local_name=local['name'],original_frame=frame['path'],original_frame_sha256=frame['sha256'],
                         canonical_box_xyxy=obs['box_xyxy'],box_candidate_id=obs['box_candidate_id'],candidates=ds,
                         derived_crop_xyxy=box,crop_path=str(crop),crop_sha256=sha(crop),
                         crop_attachment_index=len(attachments)+1,context_attachment_index=len(attachments)+2)
                apps.append(app)
                attachments.extend([dict(path=str(crop),sha256=app['crop_sha256'],shot_id=sid,frame_id=obs['frame_id']),
                                    dict(path=frame['path'],sha256=frame['sha256'],shot_id=sid,frame_id=obs['frame_id'])])
        payload=dict(protocol=VERSION,global_entity_id=eid,name=entity['name'],scene_id=entity['scene_id'],
                     observed_shot_ids=entity['observed_shot_ids'],normal_story_prompt=narrative,
                     appearances=apps,unknown_observations=missing)
        dump(folder/'input.json',payload); dump(folder/'images.json',attachments)
        rows.append(dict(global_entity_id=eid,name=entity['name'],observed_shot_ids=entity['observed_shot_ids'],
                         appearances=len(apps),unknown_observations=len(missing),input_sha256=sha(folder/'input.json')))
    pin(ROOT/'prompts/appearance/entity_v1.txt'); pin(Path(__file__))
    dump(out/'manifest.json',dict(protocol=VERSION,source_case=str(case),source_registry=str(registry_path),
         registry_counts=reg['counts'],source_hashes=sources,entities=rows,
         preprocessing='Union of unchanged owned candidate boxes per frame, 10% each-side padding, bounds clipped; canonical boxes untouched.',
         dino='Normalized CLS; equal total shot weights in normalized centroid and mean similarities. Native crop -> pinned pretrained processor.',
         aggregation='Equal entity mean separately for each available metric; additionally report multi-shot and single-shot entity subsets; null excluded with counts.',
         model='gpt-6-astra',reasoning='medium',fused_score=False))
    print(json.dumps(dict(out=str(out),entities=len(rows),appearances=sum(x['appearances'] for x in rows))),flush=True)

def schema():
    from gs_consistency_contract import obj,arr,S,enum
    score=dict(type=['number','null'])
    dim=obj(score=dict(type=['integer','null'],enum=[0,25,50,75,100,None]),evidence_appearance_ids=arr(S),reason=S)
    return obj(global_entity_id=S,appearance_checks=arr(obj(appearance_id=S,usability=enum('usable','partial','unusable'),reason=S)),
               dimensions=obj(**{k:dim for k in DIMS}),score=score,expected_changes=arr(S),reason=S,limitations=S)

def validate_codex(result,payload):
    import jsonschema
    jsonschema.validate(result,schema())
    ids=[a['appearance_id'] for a in payload['appearances']]
    if result['global_entity_id']!=payload['global_entity_id'] or [a['appearance_id'] for a in result['appearance_checks']]!=ids:
        raise ValueError('Entity/appearance coverage mismatch')
    usable={a['appearance_id'] for a in result['appearance_checks'] if a['usability']!='unusable'}
    scores=[]
    for dim in result['dimensions'].values():
        evidence=dim['evidence_appearance_ids']
        if len(evidence)!=len(set(evidence)) or not set(evidence)<=set(ids): raise ValueError('Invalid evidence IDs')
        if not dim['reason'].strip(): raise ValueError('Missing dimension reason')
        if dim['score'] is not None:
            if len(set(evidence)&usable)<2: raise ValueError('Score requires two usable/partial witnesses')
            scores.append(dim['score'])
    expected=sum(scores)/len(scores) if scores else None
    if (expected is None)!=(result['score'] is None) or (expected is not None and abs(expected-result['score'])>1e-6):
        raise ValueError('Overall not nonnull dimension mean')
    return result

def verify_sources(out):
    m=read(out/'manifest.json')
    for p,h in m['source_hashes'].items():
        if sha(p)!=h: raise ValueError('Source changed: '+p)
    for e in m['entities']:
        f=out/'entities'/e['global_entity_id']/'input.json'
        if sha(f)!=e['input_sha256']: raise ValueError('Prepared input changed')
    return m

def codex(runs,workers,timeout):
    import run_wedetect_shot_entities as io
    import gs_flow1_compact_transport as transport
    transport.PROMPTS=ROOT/'prompts/appearance'
    disabled=io.disabled_skills_config()
    jobs=[]
    for out in runs:
        m=verify_sources(out)
        for e in m['entities']: jobs.append((out,e))
    def one(job):
        out,e=job; eid=e['global_entity_id']; folder=out/'entities'/eid; resultpath=folder/'codex.json'
        payload=read(folder/'input.json')
        if resultpath.exists():
            result=read(resultpath)
            if result['status']=='success': validate_codex(result['result'],payload)
            return result
        if e['appearances']<2:
            result=dict(status='not_assessable',score=None,reason='Fewer than two observed keyframes')
            dump(resultpath,result); return result
        args=SimpleNamespace(out=out/'calls',model='gpt-6-astra',reasoning='medium',codex_bin='codex',disabled_skills=disabled,timeout=timeout)
        try:
            raw=transport.call(eid,'entity_v1.txt',payload,read(folder/'images.json'),schema(),args)
            validate_codex(raw,payload)
            result=dict(status='success',score=raw['score'],result=raw)
        except Exception as exc:
            result=dict(status='failed',score=None,error=f'{type(exc).__name__}: {exc}')
        dump(resultpath,result)
        print(json.dumps(dict(study=out.name,entity=eid,**{k:v for k,v in result.items() if k!='result'})),flush=True)
        return result
    started=time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool: results=list(pool.map(one,jobs))
    for out in runs: dump(out/'codex_runtime.json',dict(shared_run_seconds=time.time()-started,shared_runs=[str(r) for r in runs],workers=workers,failed=sum(r['status']=='failed' for r in results)))
    if any(r['status']=='failed' for r in results): raise RuntimeError('Codex failures recorded; no silent retries or zero substitution')

def dino_statistics(features,shot_ids):
    import numpy as np
    z=np.asarray(features,dtype=np.float64)
    if z.ndim!=2 or len(z)!=len(shot_ids) or not np.isfinite(z).all(): raise ValueError('Invalid embeddings')
    norms=np.linalg.norm(z,axis=1)
    if (norms<=1e-12).any(): raise ValueError('Zero embedding')
    z=z/norms[:,None]; counts=Counter(shot_ids)
    weights=np.array([1/(len(counts)*counts[s]) for s in shot_ids])
    center=(weights[:,None]*z).sum(0); norm=np.linalg.norm(center)
    sims=(z@(center/norm)).tolist() if norm>1e-12 else None
    return dict(score=float(np.dot(weights,sims)) if len(z)>=2 and sims is not None else None,
                reason='ok' if len(z)>=2 and sims is not None else 'fewer_than_two_or_degenerate_center',
                weights=weights.tolist(),similarities_to_centroid=sims,pairwise_cosines=(z@z.T).tolist())

def dino(runs,model_path,batch_size):
    import os
    import numpy as np
    import torch
    from PIL import Image
    from transformers import AutoImageProcessor,AutoModel
    if not os.environ.get('SLURM_JOB_ID') or not os.environ.get('ROCR_VISIBLE_DEVICES','').startswith('GPU-'): raise RuntimeError('Require guarded allocated UUID GPU')
    if torch.cuda.device_count()!=1: raise RuntimeError('Require exactly one visible GPU')
    started=time.time(); torch.set_num_threads(4)
    processor=AutoImageProcessor.from_pretrained(model_path,local_files_only=True)
    model=AutoModel.from_pretrained(model_path,local_files_only=True).to('cuda').eval()
    model_hashes={p.name:sha(p) for p in Path(model_path).iterdir() if p.name in ('config.json','preprocessor_config.json','model.safetensors')}
    for out in runs:
        m=verify_sources(out); allapps=[]; ranges=[]
        for e in m['entities']:
            apps=read(out/'entities'/e['global_entity_id']/'input.json')['appearances']
            ranges.append((e,apps,len(allapps),len(allapps)+len(apps))); allapps.extend(apps)
        vectors=[]
        for start in range(0,len(allapps),batch_size):
            images=[]
            for a in allapps[start:start+batch_size]:
                if sha(a['crop_path'])!=a['crop_sha256']: raise ValueError('Crop changed')
                with Image.open(a['crop_path']) as im: images.append(im.convert('RGB'))
            inputs=processor(images=images,return_tensors='pt').to('cuda')
            with torch.inference_mode():
                z=model(**inputs).last_hidden_state[:,0,:].float()
                z=torch.nn.functional.normalize(z,dim=-1)
            vectors.append(z.cpu().numpy())
        vectors=np.concatenate(vectors)
        np.savez_compressed(out/'dino_embeddings.npz',embeddings=vectors,keys=np.asarray([e['global_entity_id']+'/'+a['appearance_id'] for e,apps,_,_ in ranges for a in apps]))
        for e,apps,lo,hi in ranges:
            result=dino_statistics(vectors[lo:hi],[a['shot_id'] for a in apps]);result['appearance_ids']=[a['appearance_id'] for a in apps]
            dump(out/'entities'/e['global_entity_id']/'dino.json',result)
        dump(out/'dino_runtime.json',dict(seconds_since_shared_start=time.time()-started,model='facebook/dinov2-base',model_path=str(model_path),model_hashes=model_hashes,
             processor=processor.to_dict(),torch=torch.__version__,device=torch.cuda.get_device_name(),uuid=os.environ['ROCR_VISIBLE_DEVICES'],batch_size=batch_size,appearance_count=len(allapps)))
        print(json.dumps(dict(study=out.name,dino_appearances=len(allapps),seconds=time.time()-started)),flush=True)

def summarize(out):
    m=verify_sources(out); rows=[]; usage=Counter(); failures=[]
    for e in m['entities']:
        folder=out/'entities'/e['global_entity_id']; c=read(folder/'codex.json'); d=read(folder/'dino.json')
        if c['status']=='success': validate_codex(c['result'],read(folder/'input.json'))
        if c['status']=='failed': failures.append(e['global_entity_id'])
        rows.append(dict(**e,codex_score=c['score'],codex_status=c['status'],dino_score=d['score'],
                         codex_reason=c.get('result',{}).get('reason',c.get('reason',c.get('error',''))),
                         limitations=c.get('result',{}).get('limitations','')))
        p=out/'calls'/e['global_entity_id']/'status.json'
        if p.exists():
            state=read(p)
            for u in state.get('usage',state.get('known_usage',[])):
                if u: usage.update({k:v for k,v in u.items() if isinstance(v,(int,float))})
    def group(rs):
        result=dict(entities=len(rs),appearances=sum(r['appearances'] for r in rs))
        for metric in ('codex','dino'):
            vals=[r[metric+'_score'] for r in rs if r[metric+'_score'] is not None]
            result[metric]=dict(score=sum(vals)/len(vals) if vals else None,scored_entities=len(vals),unscored_entities=len(rs)-len(vals))
        return result
    summary=dict(protocol=VERSION,source_case=m['source_case'],aggregation=m['aggregation'],
        all_entities=group(rows),multi_shot_entities=group([r for r in rows if len(r['observed_shot_ids'])>1]),
        single_shot_entities=group([r for r in rows if len(r['observed_shot_ids'])==1]),failed_entities=failures,usage=dict(usage),entities=rows,
        cost=dict(status='unavailable_until_applicable_service_pricing_verified',currency='USD'))
    dump(out/'summary.json',summary)
    lines=['# '+out.name+' appearance consistency','', 'DINO and Codex are independent; no fusion. Equal-entity means; null excluded with explicit counts. Frozen identity results reused, appearance evaluation fresh.','',
           '| Entity | Name | Shots | Frames | Codex /100 | DINO cosine |','|---|---|---|---:|---:|---:|']
    for r in rows:
        fmt=lambda v: 'null' if v is None else f'{v:.4f}'
        lines.append(f'| {r["global_entity_id"]} | {r["name"]} | {", ".join(r["observed_shot_ids"])} | {r["appearances"]} | {fmt(r["codex_score"])} | {fmt(r["dino_score"])} |')
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='entities'},ensure_ascii=False),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['prepare','codex','dino','summarize']);p.add_argument('--case',type=Path);p.add_argument('--out',type=Path)
    p.add_argument('--runs',nargs='+',type=Path);p.add_argument('--workers',type=int,default=3);p.add_argument('--timeout',type=int,default=600)
    p.add_argument('--model-path',type=Path,default=ROOT/'experiments/entitybench-wan21-smoke/cache/models/dinov2-base');p.add_argument('--batch-size',type=int,default=16)
    a=p.parse_args()
    if a.phase=='prepare': prepare(a.case,a.out); return
    runs=[r.resolve() for r in a.runs]
    if a.phase=='codex': codex(runs,a.workers,a.timeout)
    elif a.phase=='dino': dino(runs,a.model_path,a.batch_size)
    else:
        for out in runs: summarize(out)
if __name__=='__main__': main()
