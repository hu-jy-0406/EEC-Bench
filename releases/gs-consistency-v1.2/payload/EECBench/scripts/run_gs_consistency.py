#!/usr/bin/env python3
"""Frozen Gs -> identities -> numeric diagnostics -> two isolated witness reviews -> score."""
import argparse, copy, hashlib, json, os, shutil, socket, time
from pathlib import Path
from types import SimpleNamespace
import run_partial_scene_comparison as transport
import run_wedetect_shot_entities as io
from run_isolated_shot_static_3d import owned_compute_job
from gs_consistency_contract import VERSION,MATCH_SCHEMA,CHECK_SCHEMA

def read(p):return json.loads(Path(p).read_text())
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def clean_graph(g):
    nodes=[]
    for e in g['entities']:
        rows=[{k:r[k] for k in ('frame_id','visible','box_xyxy','eligible','selected','weight','reason','geometry','projection_iou','center_robust_residual') if k in r} for r in e['frame_evidence']]
        nodes.append({**{k:e[k] for k in ('entity_id','name','geometry','reliability','fused_projection_median_iou','center_dispersion_relative')},
                      'center_mad_xyz':e['aggregation'].get('center_mad_xyz'),'frame_evidence':rows})
    return dict(shot_id=g['shot_id'],method=g['method'],coordinate_system=g['coordinate_system'],cameras=g['cameras'],entities=nodes)
def validate_match(m,graphs):
    import jsonschema
    jsonschema.validate(m,MATCH_SCHEMA)
    ids=[g['group_id'] for g in m['groups']]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate groups')
    for side,graph in zip(['a','b'],graphs):
        actual=[i for g in m['groups'] for i in g[side+'_ids']]
        if len(actual)!=len(set(actual)) or set(actual)!={e['entity_id'] for e in graph['entities']}:raise ValueError('Incomplete/duplicate entity partition')
    for g in m['groups']:
        if not g['a_ids'] and not g['b_ids']:raise ValueError('Empty group')
        if g['identity']=='matched' and (len(g['a_ids'])!=1 or len(g['b_ids'])!=1):raise ValueError('Matched must be one-to-one')
        if g['identity']=='unmatched' and (bool(g['a_ids'])==bool(g['b_ids']) or len(g['a_ids'])+len(g['b_ids'])!=1):raise ValueError('Unmatched must be singleton')
        if g['anchor_eligible'] and g['identity']!='matched':raise ValueError('Unmatched anchor')
def main(a):
    job=owned_compute_job()
    if os.getloadavg()[0]>max(8,(os.cpu_count() or 1)*.5):raise RuntimeError('Busy node')
    a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=a.resume)
    paths=[a.graph_a.resolve(),a.graph_b.resolve(),a.source_a.resolve(),a.source_b.resolve()]
    sources=[dict(path=str(p),sha256=sha(p)) for p in paths]
    graphs=[read(p) for p in paths[:2]]
    if graphs[0]['shot_id']==graphs[1]['shot_id']:raise ValueError('Different shots required')
    payload=dict(protocol='gs-consistency-v1',graphs=[clean_graph(g) for g in graphs],images=[])
    images=[]
    for graph,p in zip(graphs,paths[2:]):
        source=read(p)['shots'][0]
        if source['shot_id']!=graph['shot_id']:raise ValueError('Wrong source shot')
        for f in source['calibration']['images']:
            if sha(f['path'])!=f['sha256']:raise ValueError('Image changed')
            images.append(dict(f,shot_id=graph['shot_id']))
            payload['images'].append(dict(attachment_index=len(images),shot_id=graph['shot_id'],frame_id=f['frame_id'],image_size=graph['cameras'][0]['image_size']))
    # Whitelist only: no issue-bearing paths, historical anomaly judgments or mutable project memory in prompts.
    for p in paths[:2]:shutil.copy2(p,a.out/(('graph_a' if p==paths[0] else 'graph_b')+'.json'))
    current=dict(sources=sources,images=[dict(shot_id=f['shot_id'],frame_id=f['frame_id'],sha256=f['sha256']) for f in images],model=a.model,reasoning=a.reasoning)
    if a.resume and (a.out/'manifest.json').exists() and read(a.out/'manifest.json')!=current:raise ValueError('Resume inputs/config changed')
    save(a.out/'manifest.json',current);save(a.out/'payload.json',payload)
    args=SimpleNamespace(out=a.out,model=a.model,reasoning=a.reasoning,codex_bin=a.codex_bin,timeout=a.timeout,disabled_skills=io.disabled_skills_config())
    state=dict(version=VERSION,status='running',host=socket.gethostname(),allocation=job,started=time.time())
    save(a.out/'run.json',state)
    def call(stage,prompt,data,schema):
        d=a.out/stage
        if a.resume and d.exists():
            if read(d/'status.json')['status']!='success' or read(d/'input.json')!=data:raise ValueError('Cannot reuse failed/changed call '+stage)
            return read(d/'response.json')
        return transport.call(stage,prompt,data,images,schema,args)
    try:
        matching=call('matching','gs_consistency_match_v1.txt',payload,MATCH_SCHEMA);validate_match(matching,graphs);save(a.out/'matching.json',matching)
        from gs_consistency_geometry import diagnose
        diagnostics=diagnose(graphs,matching);save(a.out/'geometry_diagnostics.json',diagnostics)
        check_payload=dict(**payload,matching=matching,geometry_diagnostics=diagnostics)
        reviews=[]
        # Fresh processes, same inputs, no prior review text; agreement is a gate, not independent probabilities.
        for name in ['witness','verification']:
            reviews.append(call(name,'gs_consistency_check_v1.txt',check_payload,CHECK_SCHEMA))
        from score_gs_consistency import score,report
        initial=score(graphs,matching,diagnostics,reviews,payload['images'])
        if initial['recheck_candidate_ids']:
            proposals=[]
            for gid in initial['recheck_candidate_ids']:
                rows=[next(r for r in review['checks'] if r['group_id']==gid) for review in reviews]
                proposals.append(dict(group_id=gid,witness_proposals=[{k:r[k] for k in ['affected_location','gs_evidence','visual_evidence','counterfactual_test','alternative_explanations']} for r in rows]))
            recheck_payload=dict(**check_payload,recheck_groups=initial['recheck_candidate_ids'],witness_proposals=proposals)
            reviews.append(call('recheck','gs_consistency_refine_v1.txt',recheck_payload,CHECK_SCHEMA))
        result=score(graphs,matching,diagnostics,reviews,payload['images']);save(a.out/'score.json',result);report(a.out,result,matching)
        snapshot=a.out/'code_snapshot';snapshot.mkdir(exist_ok=True)
        for name in ['run_gs_consistency.py','gs_consistency_contract.py','gs_consistency_geometry.py','score_gs_consistency.py','run_partial_scene_comparison.py']:
            shutil.copy2(Path(__file__).with_name(name),snapshot/name)
        for name in ['gs_consistency_match_v1.txt','gs_consistency_check_v1.txt','gs_consistency_refine_v1.txt']:
            shutil.copy2(transport.PROMPTS/name,snapshot/name)
        save(a.out/'code_hashes.json',{p.name:sha(p) for p in snapshot.iterdir()})
        state.update(status='success',score=result['score'],coverage=result['coverage'])
        print(json.dumps({k:v for k,v in result.items() if k!='groups'},ensure_ascii=False),flush=True)
    except BaseException as e:
        state.update(status='failed',error=repr(e));raise
    finally:
        state.update(ended=time.time(),calls=[dict(stage=p.parent.name,**read(p)) for p in a.out.glob('*/status.json')]);save(a.out/'run.json',state)
if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ['graph-a','graph-b','source-a','source-b','out']:p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--resume',action='store_true');p.add_argument('--model',default='gpt-6-astra');p.add_argument('--reasoning',default='medium');p.add_argument('--codex-bin',default='codex');p.add_argument('--timeout',type=int,default=1800)
    main(p.parse_args())
