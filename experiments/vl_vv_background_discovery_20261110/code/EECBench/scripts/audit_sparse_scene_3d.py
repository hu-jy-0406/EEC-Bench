#!/usr/bin/env python3
"""Read-only source/schema/call/replay audit, with post-run bounds revision explicit."""
import argparse
import json
from pathlib import Path
import numpy as np
import run_wedetect_shot_entities as io
from sparse_scene_3d import validate,audit_geometry,validate_3d_alignment
from align_sparse_scene_3d import compare_scenes
from materialize_sparse_scene_3d import materialize,validate_frames
from export_sparse_scene_3d_schemas import SCENE_SCHEMA
from partial_scene_contract import schema_validate


def audit(root):
    r=root/'run01';a=root/'alignment01';state=io.read(r/'run.json');assert state['status']=='success'
    assert io.read(a/'run.json')['status']=='success'
    for name,h in io.read(r/'source_hashes.json').items():assert io.sha(r/'source_snapshot'/name)==h
    for run in [r,a]:
        for name,h in io.read(run/'code_hashes.json').items():assert io.sha(run/'code_snapshot'/name)==h
        for f in io.read(run/'manifest.json')['images']:assert io.sha(f['path'])==f['sha256']
    raws=[];qualities=[]
    for sid in state['shots']:
        d=r/('scene_'+sid);raw=io.read(d/'response.json');payload=io.read(d/'input.json');validate(raw,payload)
        assert not any(k in payload for k in ['relations','anchors','source','policy'])
        g=io.read(r/'source_snapshot'/('graph_'+sid+'.json'))
        for k in ('shot_id','entities','frames','entity_scopes'):assert payload[k]==g[k]
        quality=audit_geometry(raw,payload);assert quality==io.read(d/'geometry_audit.json')
        raws.append(raw);qualities.append(quality)
    al=io.read(a/'alignment.json');eligible=io.read(a/'eligible_groups.json')
    validate_3d_alignment(al,[g['group_id'] for g in eligible])
    incoming=io.read(a/'alignment/input.json')
    for side,i in [('a',0),('b',1)]:
        ids={g[side+'_ids'][0] for g in eligible}
        assert {e['entity_id'] for e in incoming['scenes'][i]['anchor_entities']}==ids
        assert all(e['alignment_role']=='structural_candidate' for e in incoming['scenes'][i]['anchor_entities'])
    result=compare_scenes(raws,qualities,io.read(r/'source_snapshot/alignment.json'),al,io.read(r/'source_snapshot/policy.json'))
    assert result==io.read(a/'comparison_tight_bounds.json')
    scene=materialize(r,a);assert scene==io.read(root/'scene_graph.json');validate_frames(scene);schema_validate(scene,SCENE_SCHEMA)
    usage=[];tids=[];calls=[]
    for d in [r/('scene_'+s) for s in state['shots']]+[a/'alignment']:
        req=io.read(d/'request.json');assert io.sha(d/'prompt.txt')==req['prompt_sha256'];assert io.sha(d/'output.schema.json')==req['schema_sha256']
        usage+=io.audit_events(d/'events.jsonl');events=[json.loads(l) for l in (d/'events.jsonl').read_text().splitlines() if l]
        tid=[x['thread_id'] for x in events if x['type']=='thread.started'];assert len(tid)==1;tids+=tid
        if d.name.startswith('scene_'):assert {f['shot_id'] for f in req['images']}=={d.name[6:]}
        calls.append(dict(stage=d.name,seconds=io.read(d/'status.json')['seconds'],images=len(req['images'])))
    assert len(set(tids))==3
    totals={k:sum(u.get(k,0) for u in usage) for k in ('input_tokens','output_tokens','cached_input_tokens')};totals['total_tokens']=totals['input_tokens']+totals['output_tokens']
    data=dict(status='pass',new_model_calls=3,usage=totals,stages=calls,entities=len(scene['entities']),coordinate_frames=len(scene['frames']),
        matched_entity_pairs=len(result['items'])//3,summary=result['summary'],
        checks=['source and code snapshots','image hashes','single-shot isolation','stable-only 3D alignment payload','schema and all-node/state coverage','SO3 frame forest','projection replay','analytic-bound comparison replay','canonical scene replay'],
        limitations='No 3D ground truth or calibrated probability. Initial coarse-bound comparison retained; final report uses comparison_tight_bounds.json. Alignment candidates are provisional, not a uniquely verified world registration.')
    io.dump(root/'audit.json',data);print(json.dumps(data,ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);audit(p.parse_args().root)
