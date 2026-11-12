#!/usr/bin/env python3
"""Hypothesis-preserving 3D alignment and uncertainty-aware relation diagnostics."""
import argparse
import itertools
import os
from pathlib import Path
import shutil
import time
from collections import Counter
import numpy as np
import run_wedetect_shot_entities as io
import run_partial_scene_comparison as calls
from sparse_scene_3d import ALIGN_SCHEMA,validate_3d_alignment,compare_order_hypotheses,quat_matrix,sim3
from partial_scene_contract import evidence
from compare_partial_scenes import rules_for


def static_box(entity):
    boxes=[s['bbox3d'] for s in entity['states']]
    if not boxes or any(b is None for b in boxes):return None
    # Distinct temporal hypotheses are not collapsed into a static mean.
    return boxes[0] if all(b==boxes[0] for b in boxes) else None


def qualified_options(eid,quality):
    # A necessary, deliberately conservative projection check, not accuracy validation.
    cams={c['frame_id']:c for c in quality['cameras']}
    options=set()
    for r in quality['projected_boxes']:
        if r['entity_id']!=eid or not r.get('all_corners_in_front') or r.get('visible_box_coverage',0)<.65:continue
        c=cams[r['frame_id']]
        if c['observed_corners']<4:continue
        if r['camera_variant']=='raw':valid=c['camera_above_surface'] and c['raw_corner_rmse_px'] is not None and c['raw_corner_rmse_px']<=20
        else:valid=c.get('plane_corner_rmse_px') is not None and c['plane_corner_rmse_px']<=20 and c['plane_camera_center'][2]>0
        if valid:options.add((r['camera_variant'],r['frame_id']))
    return options


def independent_hypotheses(hypotheses,test_groups):
    # Do not silently remove an inconvenient alternative. Re-estimation without
    # the tested entities is required if any candidate depended on them.
    return [] if any(set(h['anchor_group_ids'])&set(test_groups) for h in hypotheses) else hypotheses


def compare_scenes(raws,qualities,identity,alignment,policy):
    nodes=[{e['entity_id']:e for e in r['entities']} for r in raws]
    matched=[g for g in identity['groups'] if g['status']=='matched'];items=[]
    for g1,g2 in itertools.combinations(matched,2):
        boxes=[static_box(nodes[i][g[side+'_ids'][0]]) for side,i in [('a',0),('b',1)] for g in (g1,g2)]
        refs=[(raws[i]['shot_id'],g[side+'_ids'][0]) for side,i in [('a',0),('b',1)] for g in (g1,g2)]
        rule=rules_for(policy,refs)
        # Anchors involved in a tested pair cannot certify their own alignment.
        hypotheses=independent_hypotheses(alignment['hypotheses'],{g1['group_id'],g2['group_id']})
        for axis,vector in zip('xyz',np.eye(3)):
            base=dict(groups=[g1['group_id'],g2['group_id']],axis=axis,scope='obb_centers',continuity_rule=rule,
                eligible_alignment_hypotheses=[h['hypothesis_id'] for h in hypotheses])
            if any(b is None for b in boxes):out=dict(status='dynamic_or_geometry_unresolved')
            else:
                passed=all(qualified_options(g1[side+'_ids'][0],qualities[i]) & qualified_options(g2[side+'_ids'][0],qualities[i]) for side,i in [('a',0),('b',1)])
                out=compare_order_hypotheses(*boxes,vector,hypotheses,passed)
                if out['status']=='conflict' and rule!='must_persist':out['status']='explained_change' if rule=='may_change' else 'continuity_unresolved'
            items.append(dict(**base,**out))
    return dict(protocol_version='sparse_scene_3d_v0.3',items=items,summary=dict(Counter(r['status'] for r in items)),
        caveat='Diagnostic under heuristic box/transform intervals; projection compatibility is necessary, not proof of correct 3D. Anchor-dependent pairs are withheld to avoid self-confirmation.')


def run(args):
    io.safe_compute()
    if os.getloadavg()[0]>max(8,(os.cpu_count() or 1)*.5):raise RuntimeError('Compute node busy')
    root=args.source_run;state=io.read(root/'run.json');assert state['status']=='success'
    raws=[io.read(root/('scene_'+s)/'response.json') for s in state['shots']]
    qualities=[io.read(root/('scene_'+s)/'geometry_audit.json') for s in state['shots']]
    basegraphs=[io.read(root/'source_snapshot'/('graph_'+s+'.json')) for s in state['shots']]
    identity=io.read(root/'source_snapshot/alignment.json');policy=io.read(root/'source_snapshot/policy.json')
    nodes=[{e['entity_id']:e for e in r['entities']} for r in raws]
    eligible=[g for g in identity['groups'] if g['status']=='matched' and all(nodes[i][g[side+'_ids'][0]]['alignment_role']=='structural_candidate' for side,i in [('a',0),('b',1)])]
    args.out.mkdir(parents=True,exist_ok=False)
    images=io.read(root/'manifest.json')['images']
    io.dump(args.out/'manifest.json',dict(images=images));io.dump(args.out/'eligible_groups.json',eligible)
    code=args.out/'code_snapshot';code.mkdir()
    paths=[Path(__file__),Path(__file__).with_name('sparse_scene_3d.py'),Path(calls.__file__),calls.PROMPTS/'sparse_scene_3d_alignment_v0.3.txt']
    for p in paths:shutil.copy2(p,code/p.name)
    io.dump(args.out/'code_hashes.json',{p.name:io.sha(p) for p in paths})
    clean=[]
    for i,side in enumerate(('a','b')):
        ids={g[side+'_ids'][0] for g in eligible};r=raws[i]
        clean.append(dict(shot_id=r['shot_id'],reference=r['reference'],cameras=r['cameras'],
            anchor_entities=[dict(**nodes[i][eid],name=next(e['name'] for e in basegraphs[i]['entities'] if e['entity_id']==eid)) for eid in sorted(ids)],
            projection_diagnostics=qualities[i]['cameras']))
    args.disabled_skills=io.disabled_skills_config();start=time.time()
    runstate=dict(status='running',source_run=str(root),started=start,eligible_anchor_groups=[g['group_id'] for g in eligible],
        source_hashes={str(p.relative_to(root)):io.sha(p) for p in [root/'source_snapshot/alignment.json',*[root/('scene_'+s)/'response.json' for s in state['shots']]]})
    io.dump(args.out/'run.json',runstate)
    try:
        al=calls.call('alignment','sparse_scene_3d_alignment_v0.3.txt',dict(scenes=clean,eligible_identity_groups=eligible,
            images=[dict(attachment_index=i+1,shot_id=f['shot_id'],frame_id=f['frame_id']) for i,f in enumerate(images)]),images,ALIGN_SCHEMA,args)
        validate_3d_alignment(al,[g['group_id'] for g in eligible])
        for h in al['hypotheses']:
            for side,g in zip(('a','b'),basegraphs):evidence(h['evidence_'+side],g)
        io.dump(args.out/'alignment.json',al)
        result=compare_scenes(raws,qualities,identity,al,policy);io.dump(args.out/'comparison.json',result)
        io.dump(args.out/'comparison_tight_bounds.json',result)
        # Keep each scene hypothesis separate. Do not average uncertain 180-degree alternatives.
        joined=[]
        for h in al['hypotheses']:
            transformed=[];r=quat_matrix(h['rotation_wxyz'])
            for e in raws[1]['entities']:
                states=[]
                for s in e['states']:
                    b=s['bbox3d']
                    states.append(dict(frame_ids=s['frame_ids'],center_in_A=sim3([b['center_world']],r,h['translation_xyz'],h['scale'])[0].tolist() if b else None,
                        size_in_A=(h['scale']*np.array(b['size_xyz'])).tolist() if b else None,
                        rotation_in_A=(r@quat_matrix(b['rotation_wxyz'])).tolist() if b else None,original_state=s))
                transformed.append(dict(entity_id=e['entity_id'],states=states))
            joined.append(dict(transform=h,shot_b_in_shot_a_frame=transformed))
        io.dump(args.out/'aligned_scene_hypotheses.json',dict(reference_shot=raws[0],target_shot=raws[1],hypotheses=joined,
            comparison=result,identity=identity,uncertainty_note='Original state errors and transform uncertainty retained; transformed centers are nominal only.'))
        runstate.update(status='success',summary=result['summary'])
    except BaseException as exc:runstate.update(status='failed',error=repr(exc));raise
    finally:
        runstate.update(seconds=time.time()-start,ended=time.time());io.dump(args.out/'run.json',runstate)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source-run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--model',default='gpt-6-astra');p.add_argument('--reasoning',default='medium');p.add_argument('--codex-bin',default='codex');p.add_argument('--timeout',type=int,default=1800)
    a=p.parse_args();a.source_run=a.source_run.resolve();a.out=a.out.resolve();run(a)
