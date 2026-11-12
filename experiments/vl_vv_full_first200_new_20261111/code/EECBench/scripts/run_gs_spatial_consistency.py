#!/usr/bin/env python3
"""Extend a frozen Gs consistency run with independent local relational evidence."""
import argparse,copy,hashlib,itertools,json,os,shutil,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import run_wedetect_shot_entities as io
import run_partial_scene_comparison as transport
from run_isolated_shot_static_3d import owned_compute_job
from run_gs_consistency import clean_graph,read,save,sha,validate_match
from gs_spatial_relations import build_relations,basis
from gs_relation_contract import SHOT_SCHEMA,VERIFY_SCHEMA

def expected_pairs(placements,references):
    pairs=[]
    for ref in references:
        ids=sorted(p['entity_id'] for p in placements if p['support_verified'] and p['support_entity_id']==ref['origin_anchor_id'])
        for i,j in itertools.combinations(ids,2):
            for axis in ['cross_anchor_up','toward_reference','vertical']:pairs.append((i,j,ref['origin_anchor_id'],ref['reference_anchor_id'],axis))
    return pairs

def validate_single(raw,payload):
    import jsonschema
    jsonschema.validate(raw,SHOT_SCHEMA)
    if raw['shot_id']!=payload['graph']['shot_id']:raise ValueError('Foreign shot')
    if [p['entity_id'] for p in raw['placements']]!=payload['target_entity_ids']:raise ValueError('Placement coverage')
    nodes={e['entity_id'] for e in payload['graph']['entities']};fids={f['frame_id'] for f in payload['images']}
    for p in raw['placements']:
        if p['support_entity_id'] is not None and p['support_entity_id'] not in nodes:raise ValueError('Invented support')
        if not set(p['frame_ids'])<=fids or (p['support_verified'] and (p['support_entity_id'] is None or len(set(p['frame_ids']))<2)):raise ValueError('Unsupported placement')
    keys=[tuple(r[k] for k in ['subject_id','object_id','origin_anchor_id','reference_anchor_id','axis']) for r in raw['relations']]
    expected=expected_pairs(raw['placements'],payload['references'])
    if len(keys)!=len(set(keys)) or set(keys)!=set(expected):raise ValueError('Exact common-support pair/axis coverage required')
    for r in raw['relations']:
        for w in r['evidence']:
            if w['frame_id'] not in fids:raise ValueError('Foreign witness frame')
            width,height=next(f['image_size'] for f in payload['images'] if f['frame_id']==w['frame_id'])
            for name in ['subject_region_xyxy','object_region_xyxy','reference_region_xyxy']:
                b=w[name]
                if len(b)!=4 or not all(np.isfinite(b)) or not(0<=b[0]<b[2]<=width and 0<=b[1]<b[3]<=height):raise ValueError('Invalid witness pixels')
    return raw

def select_common_relations(graphs,matching,numeric,observations):
    groups={g['group_id']:g for g in matching['groups']};index=[]
    for raw in observations:index.append({tuple(r[k] for k in ['subject_id','object_id','origin_anchor_id','reference_anchor_id','axis']):r for r in raw['relations']})
    rows=[];excluded=[]
    for r in numeric['relations']:
        local=[]
        for side,ix in zip(['a','b'],index):
            ids=[groups[x][side+'_ids'][0] for x in r['endpoint_groups']];anchors=[groups[x][side+'_ids'][0] for x in r['anchor_groups']]
            key=(*sorted(ids),*anchors,r['axis']);obs=copy.deepcopy(ix.get(key))
            if obs:
                obs['canonical_endpoint_order_reversed']=ids!=sorted(ids)
                if obs['canonical_endpoint_order_reversed']:obs['order']={'positive':'negative','negative':'positive','unknown':'unknown'}[obs['order']]
            local.append(obs)
        if all(local):rows.append(dict(**r,shot_observations=local))
        else:excluded.append(dict(relation_id=r['relation_id'],reason='no_verified_common_support_in_both_shots'))
    return rows,excluded

def main(a):
    job=owned_compute_job()
    if os.getloadavg()[0]>max(8,(os.cpu_count() or 1)*.5):raise RuntimeError('Busy node')
    a.source_run=a.source_run.resolve();a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=a.resume)
    base=a.source_run;graphs=[read(base/n) for n in ['graph_a.json','graph_b.json']];matching=read(base/'matching.json');validate_match(matching,graphs)
    if read(base/'run.json')['status']!='success':raise ValueError('Completed source run required')
    for n in ['graph_a.json','graph_b.json','matching.json','score.json','manifest.json','payload.json']:
        dest=a.out/'source_snapshot'/n;dest.parent.mkdir(exist_ok=True);shutil.copy2(base/n,dest)
    save(a.out/'source_hashes.json',{n:sha(base/n) for n in ['graph_a.json','graph_b.json','matching.json','score.json','manifest.json','payload.json']})
    numeric=build_relations(graphs,matching);save(a.out/'geometry_relations.json',numeric)
    anchors={g['group_id']:g for g in matching['groups'] if g['group_id'] in numeric['anchor_groups']}
    imagegroups=[];payloads=[]
    for graph,side,src in zip(graphs,['a','b'],read(base/'manifest.json')['sources'][2:]):
        source=read(Path(src['path']))['shots'][0];images=[dict(f,shot_id=graph['shot_id']) for f in source['calibration']['images']]
        for f in images:
            if sha(f['path'])!=f['sha256']:raise ValueError('Image changed')
        imagegroups.append(images);node={e['entity_id']:e for e in graph['entities']};refs=[]
        for k,l in itertools.combinations(anchors.values(),2):
            ki,li=k[side+'_ids'][0],l[side+'_ids'][0]
            try:rot,scale=basis(node[ki]['geometry']['center_world'],node[li]['geometry']['center_world'],[0,0,1])
            except ValueError:continue  # Degenerate reference directions remain unassessed.
            refs.append(dict(origin_anchor_id=ki,reference_anchor_id=li,basis_world=rot.tolist(),up_world=[0,0,1],anchor_baseline=scale))
        targets=[g[side+'_ids'][0] for g in matching['groups'] if g['identity']=='matched' and g['group_id'] not in anchors]
        payloads.append(dict(graph=clean_graph(graph),references=refs,target_entity_ids=targets,
            images=[dict(attachment_index=i+1,shot_id=graph['shot_id'],frame_id=f['frame_id'],image_size=next(c['image_size'] for c in graph['cameras'] if c['frame_id']==f['frame_id'])) for i,f in enumerate(images)]))
    args=SimpleNamespace(out=a.out,model=a.model,reasoning=a.reasoning,codex_bin=a.codex_bin,timeout=a.timeout,disabled_skills=io.disabled_skills_config())
    state=dict(status='running',version='gs-consistency-spatial-v1.2',allocation=job,started=time.time(),source_run=str(base),geometry_unchanged=True)
    save(a.out/'run.json',state)
    def call(stage,prompt,payload,images,schema):
        d=a.out/stage
        if a.resume and d.exists():
            if read(d/'status.json')['status']!='success' or read(d/'input.json')!=payload:raise ValueError('Changed or failed stage '+stage)
            return read(d/'response.json')
        return transport.call(stage,prompt,payload,images,schema,args)
    try:
        def observe(i):
            raw=call('observe_'+graphs[i]['shot_id'],'gs_relation_shot_v1.txt',payloads[i],imagegroups[i],SHOT_SCHEMA)
            return validate_single(raw,payloads[i])
        with ThreadPoolExecutor(max_workers=2) as pool:observations=list(pool.map(observe,range(2)))
        save(a.out/'shot_relations.json',observations)
        common,excluded=select_common_relations(graphs,matching,numeric,observations);save(a.out/'relation_opportunities.json',dict(relations=common,excluded=excluded))
        candidates=[r for r in common if r['candidate_conflict']]
        images=[f for group in imagegroups for f in group]
        sizes={(g['shot_id'],c['frame_id']):c['image_size'] for g in graphs for c in g['cameras']}
        ix=[dict(attachment_index=i+1,shot_id=f['shot_id'],frame_id=f['frame_id'],image_size=sizes[(f['shot_id'],f['frame_id'])]) for i,f in enumerate(images)]
        verify_payload=dict(graphs=[clean_graph(g) for g in graphs],matching=matching,relations=candidates,images=ix)
        if candidates:verified=call('verify_relations','gs_relation_verify_v1.txt',verify_payload,images,VERIFY_SCHEMA)
        else:verified=dict(relations=[],limitations='No numeric conflicts on verified shared supports')
        save(a.out/'verified_relations.json',verified)
        from score_gs_spatial_consistency import combine,render
        result=combine(read(base/'score.json'),common,verified,ix);save(a.out/'score.json',result);render(a.out,result,graphs,common)
        snapshot=a.out/'code_snapshot';snapshot.mkdir(exist_ok=True)
        for name in ['gs_spatial_relations.py','gs_relation_contract.py','run_gs_spatial_consistency.py','score_gs_spatial_consistency.py','run_partial_scene_comparison.py']:
            shutil.copy2(Path(__file__).with_name(name),snapshot/name)
        for name in ['gs_relation_shot_v1.txt','gs_relation_verify_v1.txt']:shutil.copy2(transport.PROMPTS/name,snapshot/name)
        save(a.out/'code_hashes.json',{p.name:sha(p) for p in snapshot.iterdir()})
        state.update(status='success',score=result['score'],counts=result['weights']);print(json.dumps({k:v for k,v in result.items() if k not in ['groups','spatial_relations']},ensure_ascii=False),flush=True)
    except BaseException as ex:state.update(status='failed',error=repr(ex));raise
    finally:
        state.update(ended=time.time(),calls=[dict(stage=p.parent.name,**read(p)) for p in a.out.glob('*/status.json')]);save(a.out/'run.json',state)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source-run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--resume',action='store_true');p.add_argument('--model',default='gpt-6-astra');p.add_argument('--reasoning',default='medium');p.add_argument('--codex-bin',default='codex');p.add_argument('--timeout',type=int,default=1800);main(p.parse_args())
