#!/usr/bin/env python3
"""Replay spatial computations, single-shot isolation, visual gates, and frozen inputs."""
import argparse,hashlib,json
from pathlib import Path
from run_isolated_shot_static_3d import owned_compute_job
from run_gs_consistency import read,save,sha
from run_gs_spatial_consistency import validate_single,select_common_relations
from gs_spatial_relations import build_relations,DEFAULT_POLICY
from score_gs_spatial_consistency import combine
import run_wedetect_shot_entities as io

def audit(root):
    owned_compute_job();state=read(root/'run.json');base=Path(state['source_run']);graphs=[read(root/'source_snapshot'/n) for n in ['graph_a.json','graph_b.json']];matching=read(root/'source_snapshot/matching.json')
    for name,h in read(root/'source_hashes.json').items():
        assert sha(base/name)==h and sha(root/'source_snapshot'/name)==h
    num=build_relations(graphs,matching);assert num==read(root/'geometry_relations.json')
    observed=[];calls=[];threads=[]
    for i,g in enumerate(graphs):
        d=root/('observe_'+g['shot_id']);p=read(d/'input.json');other=graphs[1-i]['shot_id']
        assert p['graph']['shot_id']==g['shot_id'];assert other not in json.dumps(p,ensure_ascii=False)
        assert all(f['shot_id']==g['shot_id'] for f in p['images'])
        for token in ['/vast/','study_inconsistent','expected_anomalies']:assert token not in json.dumps(p,ensure_ascii=False)
        observed.append(validate_single(read(d/'response.json'),p))
    common,excluded=select_common_relations(graphs,matching,num,observed)
    saved=read(root/'relation_opportunities.json')
    # One explicit normalization-provenance field was added after the calls; preserve equivalent measurement values.
    def semantic(rows):return [{**r,'shot_observations':[{k:v for k,v in o.items() if k!='canonical_endpoint_order_reversed'} for o in r['shot_observations']]} for r in rows]
    assert semantic(common)==semantic(saved['relations']) and excluded==saved['excluded']
    if (root/'verify_relations').exists():
        vp=read(root/'verify_relations/input.json');images=vp['images'];assert semantic(vp['relations'])==semantic([r for r in common if r['candidate_conflict']])
    else:images=read(root/'source_snapshot/payload.json')['images']
    result=combine(read(root/'source_snapshot/score.json'),common,read(root/'verified_relations.json'),images);assert result==read(root/'score.json')
    for d in sorted(root.glob('*/status.json')):
        stage=d.parent;request=read(stage/'request.json');assert sha(stage/'prompt.txt')==request['prompt_sha256'];assert sha(stage/'output.schema.json')==request['schema_sha256'];assert read(d)['status']=='success'
        command=request['command'];assert all(f in command for f in ['--ephemeral','--ignore-user-config','--skip-git-repo-check']);usage=io.audit_events(stage/'events.jsonl');calls.append(dict(stage=stage.name,usage=usage))
        for line in (stage/'events.jsonl').read_text().splitlines():
            x=json.loads(line)
            if x.get('type')=='thread.started':threads.append(x['thread_id'])
    assert len(threads)==len(set(threads))==len(calls)
    for name,h in read(root/'code_hashes.json').items():assert sha(root/'code_snapshot'/name)==h
    # Stress grid changes only uncertainty policy, never models/geometry/labels.
    candidates=[r for r in common if r['candidate_conflict']];sensitivity=[]
    for fraction in [0.,.125,.25,.5]:
        for angle in [0.,15.,30.,45.]:
            policy=dict(DEFAULT_POLICY,center_radius_fraction=fraction,axis_tolerance_deg=angle)
            grid=build_relations(graphs,matching,policy);ix={r['relation_id']:r for r in grid['relations']}
            sensitivity.append(dict(center_radius_fraction=fraction,axis_tolerance_deg=angle,relations=[dict(relation_id=r['relation_id'],passes_geometry=ix[r['relation_id']]['candidate_conflict'],intervals=[m['sensitivity_intervals'][r['axis_index']] for m in ix[r['relation_id']]['measurements']]) for r in candidates]))
    save(root/'sensitivity.json',dict(grid=sensitivity,interpretation='Stress policy sensitivity, not confidence calibration; all original geometry and model evidence held fixed.'))
    report=dict(passed=True,source_hashes_unchanged=True,independent_shot_contexts=2,unique_tool_free_calls=len(calls),all_numeric_opportunities=len(num['relations']),common_support_relations=len(common),confirmed_spatial_relations=result['confirmed_relation_count'],exact_score_replay=True,calls=calls,
        limitation='Audits protocol and numeric reproducibility, not human accuracy or true physical anchor/center geometry.')
    save(root/'audit.json',report);print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);audit(p.parse_args().run.resolve())
