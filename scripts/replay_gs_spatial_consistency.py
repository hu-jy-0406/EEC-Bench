#!/usr/bin/env python3
"""Recompute numeric relations and score from cached, immutable inference evidence."""
import argparse,json
from pathlib import Path
from run_isolated_shot_static_3d import owned_compute_job
from run_gs_consistency import read
from gs_spatial_relations import build_relations
from run_gs_spatial_consistency import validate_single,select_common_relations
from score_gs_spatial_consistency import combine

def replay(root):
    owned_compute_job()
    graphs=[read(root/'source_snapshot'/n) for n in ['graph_a.json','graph_b.json']]
    matching=read(root/'source_snapshot/matching.json')
    numeric=build_relations(graphs,matching)
    assert numeric==read(root/'geometry_relations.json'),'Numeric replay differs'
    observations=[validate_single(read(root/('observe_'+g['shot_id'])/'response.json'),read(root/('observe_'+g['shot_id'])/'input.json')) for g in graphs]
    common,_=select_common_relations(graphs,matching,numeric,observations)
    images=[dict(shot_id=g['shot_id'],frame_id=c['frame_id'],image_size=c['image_size']) for g in graphs for c in g['cameras']]
    result=combine(read(root/'source_snapshot/score.json'),common,read(root/'verified_relations.json'),images)
    assert result==read(root/'score.json'),'Score replay differs'
    return dict(passed=True,numeric_relations=len(numeric['relations']),common_support_relations=len(common),confirmed_spatial_relations=result['confirmed_relation_count'],score=result['score'],new_model_calls=0,external_original_files_needed=False)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args();print(json.dumps(replay(a.run.resolve())))
