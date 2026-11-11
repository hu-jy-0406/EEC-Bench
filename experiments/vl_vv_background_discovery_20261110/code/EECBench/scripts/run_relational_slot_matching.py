#!/usr/bin/env python3
"""Run the frozen five-stage CPU-only geometry matching pilot."""
import argparse
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import time

from relational_slot_matching import Config,build_graph,graph_json,primitive,run_matching,slot_table


def save(path,value):
    path.write_text(json.dumps(primitive(value),ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--config',required=True,type=Path)
    args=p.parse_args()
    cfg=Config(**json.loads(args.config.read_text()))
    args.out.mkdir(parents=True,exist_ok=False)
    t0=time.time()
    data=json.loads(args.input.read_text())
    shots=data['shots']
    if len(shots)!=2:raise ValueError('Exactly two shots required')
    graphs=[]
    input_hash=sha(args.input)
    save(args.out/'frozen_config.json',asdict(cfg))
    for s in shots:
        g=build_graph(s);graphs.append(g)
        save(args.out/f'{g["shot_id"]}_relations.json',graph_json(g))
    print('Stage 1/2: frame graphs and relational neighborhoods complete.',flush=True)
    run=run_matching(*graphs,cfg)
    save(args.out/'matching.json',run)
    print('Stage 3/4/5:',run['search'],'solutions',len(run['solutions']),flush=True)
    variants=[]
    # Values fixed in this entry point before inspecting natural-case output.
    for label,vc in [('null_0.40',replace(cfg,null_cost=.40)),
                     ('null_0.70',replace(cfg,null_cost=.70)),
                     ('tolerance_0.12',replace(cfg,position_tolerance=.12,relation_tolerance=.11))]:
        result=run_matching(*graphs,vc)
        save(args.out/f'variant_{label}.json',result)
        variants.append((label,result));print('Sensitivity:',label,'complete',flush=True)
    # Time subset reruns preserve source entity order/IDs and build geometry anew.
    for label,positions in [('frames_even',[0,2,4]),('frames_odd',[1,3,5])]:
        subset=json.loads(json.dumps(shots))
        for s in subset:
            wanted={s['frames'][i]['frame_id'] for i in positions if i<len(s['frames'])}
            s['frames']=[f for f in s['frames'] if f['frame_id'] in wanted]
            for e in s['entities']:
                e['observations']=[o for o in e['observations'] if o['frame_id'] in wanted]
                e['states']=[st for st in e['states'] if st['frame_id'] in wanted]
        result=run_matching(*(build_graph(s) for s in subset),cfg)
        save(args.out/f'variant_{label}.json',result)
        variants.append((label,result));print('Sensitivity:',label,'complete',flush=True)
    slots=slot_table(*graphs,run,variants)
    save(args.out/'global_slots.json',dict(semantics='structural_candidates_not_physical_identity',slots=slots))
    srcdir=Path(__file__).resolve().parent
    for name in ['run_relational_slot_matching.py','relational_slot_matching.py','render_relational_slots.py']:
        shutil.copy2(srcdir/name,args.out/name)
    summary=dict(shot_ids=[s['shot_id'] for s in shots],entities=[len(s['entities']) for s in shots],
                 nonnull_states=[int(g['observations'].sum()) for g in graphs],
                 directed_edges=[len(g['edges']) for g in graphs],
                 candidate_pairs=len(graphs[0]['ids'])*len(graphs[1]['ids']),
                 best_matches=len(run['solutions'][0]['mapping']) if run['solutions'] else 0,
                 status_counts={status:sum(r['status']==status for r in slots) for status in sorted({r['status'] for r in slots})},
                 sensitivity_variants=[x[0] for x in variants],runtime_seconds=time.time()-t0,
                 input_hash_before=input_hash,input_hash_after=sha(args.input),
                 input_path=str(args.input.resolve()),host=platform.node(),
                 slurm_job_id=os.environ.get('SLURM_JOB_ID'),slurm_step_id=os.environ.get('SLURM_STEP_ID'),
                 code_hashes={name:sha(args.out/name) for name in ['run_relational_slot_matching.py','relational_slot_matching.py','render_relational_slots.py']},
                 config_hash=sha(args.config),names_used_for_matching=False,images_used_for_matching=False,
                 prompts_used_for_matching=False,matching_optimality='not_proven',
                 physical_identity_verified=False,relation_holdout_performed=False,
                 scores_computed=False)
    assert input_hash==summary['input_hash_after']
    save(args.out/'summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
