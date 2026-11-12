#!/usr/bin/env python3
"""Frozen static sets -> identities -> prompt policy -> two scoped review branches."""
import argparse
import copy
import itertools
import json
import os
from pathlib import Path
import shutil
import socket
import time
from types import SimpleNamespace

import run_partial_scene_comparison as transport
import run_wedetect_shot_entities as io
from run_isolated_shot_static_3d import owned_compute_job
from run_gs_consistency import read, save, sha, validate_match
from gs_consistency_contract import MATCH_SCHEMA
from static_set_contract import VERSION, POLICY_SCHEMA, PRESENCE_SCHEMA, RELATION_SCHEMA


def compact_graph(g):
    return dict(shot_id=g['shot_id'], coordinate_system=g['coordinate_system'],
        entities=[dict(entity_id=e['entity_id'], name=e['name'],
            geometry={k:e['geometry'][k] for k in ['center_world','size_xyz','R_world_from_object']} if e['geometry'] else None,
            reliability=e['reliability'], center_dispersion_relative=e['center_dispersion_relative'],
            observations=[{k:r[k] for k in ['frame_id','visible','box_xyxy','selected'] if k in r} for r in e['frame_evidence']]) for e in g['entities']])


def validate_policy(policy, matching, facts):
    import jsonschema
    jsonschema.validate(policy, POLICY_SCHEMA)
    expected={g['group_id'] for g in matching['groups']}
    ids=[r['group_id'] for r in policy['groups']]
    if set(ids)!=expected or len(ids)!=len(expected):raise ValueError('Policy coverage')
    factids={r['fact_id'] for r in facts['facts']}
    for row in policy['groups']:
        if not set(row['prompt_fact_ids'])<=factids:raise ValueError('Invented prompt facts')
        if 'change_allowed' in [row['presence'],row['layout']] and (not row['prompt_fact_ids'] or not row['allowed_change_scope'].strip()):
            raise ValueError('Permission needs cited facts and explicit scope')


def make_queries(matching, policy, graphs):
    from gs_spatial_relations import build_relations
    pmap={r['group_id']:r for r in policy['groups']}
    numeric_matching=copy.deepcopy(matching)
    for g in numeric_matching['groups']:
        g['anchor_eligible'] &= pmap[g['group_id']]['layout']=='stable'
    numeric=build_relations(graphs,numeric_matching)
    # All resolved static pairs are admitted before looking for numeric changes.
    common=[g['group_id'] for g in matching['groups'] if g['identity']=='matched']
    pairs=[dict(pair_id='pair_'+a+'_'+b, endpoint_groups=[a,b]) for a,b in itertools.combinations(common,2)]
    for row in pairs:
        row['numeric_relation_ids']=[r['relation_id'] for r in numeric['relations'] if set(r['endpoint_groups'])==set(row['endpoint_groups'])]
    return dict(pairs=pairs, one_sided_group_ids=[g['group_id'] for g in matching['groups'] if g['identity']=='unmatched'],
        unresolved_group_ids=[g['group_id'] for g in matching['groups'] if g['identity'] in ['ambiguous','scope_mismatch']]), numeric


def run(a):
    job=owned_compute_job()
    if os.getloadavg()[0]>max(8,(os.cpu_count() or 1)*.5):raise RuntimeError('Busy compute node')
    a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=a.resume)
    source=read(a.source_run/'manifest.json')
    graphpaths=[a.source_run/n for n in ['graph_a.json','graph_b.json']]
    sourcepaths=[Path(r['path']) for r in source['sources'][2:]]
    motionpaths=[a.motion_a,a.motion_b]
    paths=graphpaths+sourcepaths+motionpaths+[a.narrative]
    current=dict(version=VERSION,sources={str(p.resolve()):sha(p) for p in paths},model=a.model,reasoning=a.reasoning)
    if a.resume and (a.out/'manifest.json').exists() and read(a.out/'manifest.json')!=current:raise ValueError('Changed resume sources/config')
    save(a.out/'manifest.json',current)
    graphs=[read(p) for p in graphpaths]
    facts=read(a.narrative)
    if not facts['facts']:raise ValueError('Narrative facts must be explicit')
    auxiliaries=[];images=[];image_index=[]
    for g,p,motionpath in zip(graphs,sourcepaths,motionpaths):
        src=read(p)['shots'][0];motion=read(motionpath)
        if src['shot_id']!=g['shot_id'] or motion['shot_id']!=g['shot_id']:raise ValueError('Shot mismatch')
        status={e['entity_id']:e for e in motion['entities']}
        if set(status)!={e['entity_id'] for e in src['entities']}:raise ValueError('Motion inventory coverage')
        if {eid for eid,v in status.items() if v['status']=='static'}!={e['entity_id'] for e in g['entities']}:raise ValueError('Static scope changed')
        auxiliaries.append(dict(shot_id=g['shot_id'],entities=[dict(entity_id=e['entity_id'],name=e['name'],
            status=status[e['entity_id']]['status'], observations=[{k:r[k] for k in ['frame_id','exist','visible','box_xyxy']} for r in e['observations']],
            motion_evidence=status[e['entity_id']]['visual_evidence'],motion_intervals=status[e['entity_id']]['motion_intervals']) for e in src['entities']]))
        for f in src['calibration']['images']:
            if sha(f['path'])!=f['sha256']:raise ValueError('Original image hash changed')
            images.append(dict(f,shot_id=g['shot_id']))
            size=next(c['image_size'] for c in g['cameras'] if c['frame_id']==f['frame_id'])
            image_index.append(dict(attachment_index=len(images),shot_id=g['shot_id'],frame_id=f['frame_id'],image_size=size))
    for name,g in zip(['graph_a.json','graph_b.json'],graphs):save(a.out/name,g)
    save(a.out/'auxiliary_inventories.json',auxiliaries);save(a.out/'narrative.json',facts)
    save(a.out/'images.json',images);save(a.out/'image_index.json',image_index)
    base=dict(graphs=[compact_graph(g) for g in graphs],images=image_index,
        scope='Only supplied static graph nodes are score units; other motion labels are auxiliary evidence only.')
    args=SimpleNamespace(out=a.out,model=a.model,reasoning=a.reasoning,codex_bin=a.codex_bin,timeout=a.timeout,disabled_skills=io.disabled_skills_config())
    snapshot=a.out/'code_snapshot';snapshot.mkdir(exist_ok=True)
    code=[Path(__file__),Path(__file__).with_name('static_set_contract.py'),Path(__file__).with_name('score_static_set_consistency.py'),
          Path(__file__).with_name('gs_spatial_relations.py'),Path(__file__).with_name('run_partial_scene_comparison.py'),Path(__file__).with_name('run_wedetect_shot_entities.py')]
    code+=list(transport.PROMPTS.glob('static_set_*v1.3.txt'))+[transport.PROMPTS/'gs_consistency_match_v1.txt']
    hashes={p.name:sha(p) for p in code if p.exists()}
    if a.resume and (a.out/'code_hashes.json').exists():
        previous=read(a.out/'code_hashes.json')
        # A prepared run may initially stop after matching while later-stage
        # code is completed. Every file already snapshotted must stay identical.
        if any(hashes.get(k)!=v for k,v in previous.items()):raise ValueError('Changed snapshotted code')
    for p in code:
        if p.exists():shutil.copy2(p,snapshot/p.name)
    save(a.out/'code_hashes.json',hashes)
    state=dict(status='running',version=VERSION,started=time.time(),host=socket.gethostname(),allocation=job)
    save(a.out/'run.json',state)
    def call(stage,prompt,data,schema,attached=images):
        directory=a.out/stage
        if a.resume and directory.exists():
            if read(directory/'status.json')['status']!='success' or read(directory/'input.json')!=data:raise ValueError('Changed/failed stage '+stage)
            return read(directory/'response.json')
        return transport.call(stage,prompt,data,attached,schema,args)
    try:
        matching=call('matching','gs_consistency_match_v1.txt',base,MATCH_SCHEMA)
        validate_match(matching,graphs);save(a.out/'matching.json',matching)
        print('matching complete',flush=True)
        if a.stop_after=='matching':state['status']='prepared_matching';return
        names={e['entity_id']:e['name'] for g in graphs for e in g['entities']}
        policy_payload=dict(groups=[dict(group_id=g['group_id'],a_names=[names[i] for i in g['a_ids']],b_names=[names[i] for i in g['b_ids']],identity=g['identity']) for g in matching['groups']],
            narrative_facts=facts['facts'])
        policy=call('policy','static_set_policy_v1.3.txt',policy_payload,POLICY_SCHEMA,attached=[])
        validate_policy(policy,matching,facts);save(a.out/'policy.json',policy)
        print('policy complete',flush=True)
        if a.stop_after=='policy':state['status']='prepared_policy';return
        queries,numeric=make_queries(matching,policy,graphs)
        save(a.out/'queries.json',queries);save(a.out/'numeric_relations.json',numeric)
        common_payload=dict(**base,matching=matching,policy=policy,narrative_facts=facts['facts'])
        presence_payload=dict(**common_payload,target_group_ids=queries['one_sided_group_ids'],auxiliary_inventories=auxiliaries)
        numeric_compact=[]
        for r in numeric['relations']:
            numeric_compact.append(dict(relation_id=r['relation_id'],endpoint_groups=r['endpoint_groups'],anchor_groups=r['anchor_groups'],axis=r['axis'],
                candidate_conflict=r['candidate_conflict'],measurements=[{k:v for k,v in m.items() if k in ['status','reason','frame_ids','nominal','sensitivity_intervals','robust_signs']} for m in r['measurements']]))
        relation_payload=dict(**common_payload,pairs=queries['pairs'],numeric_policy=numeric['policy'],numeric_relations=numeric_compact)
        pres=[];rels=[]
        # Fresh, independent contexts: reviewer 2 never receives reviewer 1.
        # Sequential calls are intentional: bounded service/resource use.
        for n in [1,2]:
            pres.append(call(f'presence_{n}','static_set_presence_v1.3.txt',presence_payload,PRESENCE_SCHEMA))
            print(f'presence {n} complete',flush=True)
        for n in [1,2]:
            rels.append(call(f'relations_{n}','static_set_relations_v1.3.txt',relation_payload,RELATION_SCHEMA))
            print(f'relations {n} complete',flush=True)
        from score_static_set_consistency import score, report
        result=score(graphs,matching,policy,auxiliaries,queries,numeric,pres,rels,image_index)
        save(a.out/'score.json',result);report(a.out,result,matching,graphs)
        assert current['sources']=={str(p.resolve()):sha(p) for p in paths}
        for f in images:
            assert sha(f['path'])==f['sha256']
        save(a.out/'audit.json',dict(status='pass',source_hashes_unchanged=True,static_sets_unchanged=True,original_12_jpegs_unchanged=True,
            score_units_static_only=True,narrative_policy_before_verdicts=True,policy_receives_images=False,
            previous_scores_or_expected_labels_supplied=False,independent_reviews_same_inputs=True,geometry_refitted=False))
        state.update(status='success',score=result['overall']['score'],coverage=result['overall']['coverage'])
        print(json.dumps(result['overall'],ensure_ascii=False),flush=True)
    except BaseException as e:
        state.update(status='failed',error=repr(e));raise
    finally:
        state.update(ended=time.time(),calls=[dict(stage=p.parent.name,**read(p)) for p in sorted(a.out.glob('*/status.json'))])
        save(a.out/'run.json',state)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ['source-run','motion-a','motion-b','narrative','out']:p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--resume',action='store_true');p.add_argument('--stop-after',choices=['matching','policy','all'],default='all')
    p.add_argument('--model',default='gpt-6-astra');p.add_argument('--reasoning',default='medium')
    p.add_argument('--codex-bin',default='/vast/users/guangyi.chen/.local/bin/codex');p.add_argument('--timeout',type=int,default=1800)
    run(p.parse_args())
