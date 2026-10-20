import copy
import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from gs_temporal_core import within_proposals,boundary_proposals,aggregate,cosine,score
from gs_temporal_contract import GATES,validate_expectation
from gs_temporal_review import validate_checks,local_payloads,local_gate
from run_gs_temporal import plan,scope_for


def box(p):
    return dict(center_world=p,size_xyz=[1,1,1],R_world_from_object=[[1,0,0],[0,1,0],[0,0,1]])


def graph(sid='shot1',fids=(0,1,2),positions=None):
    positions=positions or [[[0,0,0]]*len(fids),[[1,0,0]]*len(fids)]
    return dict(shot_id=sid,cameras=[dict(frame_id=f) for f in fids],entities=[dict(entity_id=f'{sid}/e{i}',name=str(i),motion_status='moving',geometry=box([99,99,99]),frame_evidence=[dict(frame_id=f,visible=True,box_xyxy=[1,1,4,4],geometry=box(p),selected=False,eligible=False,reason='robust_center_outlier') for f,p in zip(fids,ps)]) for i,ps in enumerate(positions)])


def expectation(g):
    fs=[c['frame_id'] for c in g['cameras']]
    return dict(shot_id=g['shot_id'],camera_assessment='fixed',limitations='',entities=[dict(entity_id=e['entity_id'],observed_status='moving',uncertainty='sampled only',intervals=[dict(start_frame_id=a,end_frame_id=b,expected='static',observed='changed',basis='continuity',prompt_fact_references=['p'],causal_explanation='untouched',visual_evidence='unexpected change') for a,b in zip(fs,fs[1:])]) for e in g['entities']])


def matching():
    return dict(groups=[dict(group_id=f'g{i}',a_ids=[f'shot1/e{i}'],b_ids=[f'shot3/e{i}'],identity='matched') for i in range(2)],local_origin_group_id='g0',local_reference_group_id='g1')


def fit():
    return dict(status='numeric_candidate',scale=1,rotation=[[1,0,0],[0,1,0],[0,0,1]],translation=[0,0,0])


def check(event,frames):
    return dict(event_id=event['event_id'],status='conflict',cause='inconsistency',conflict_kind='position_change' if event['kind']=='spatial' else 'unexplained_missing',prompt_verdict='does_not_explain_change',prompt_fact_references=['p'],prompt_explanation='no causal move',witnesses=[dict(shot_id=s,frame_id=f,region_xyxy=[0,0,5,5],observation='visible witness') for s,f in frames],reason='evidence',remaining_alternatives='none',**{g:True for g in GATES})


class TemporalTests(unittest.TestCase):
    def test_nonadjacent_negative_is_detected(self):
        ps=[[math.cos(t),math.sin(t),0] for t in (0,math.pi/3,2*math.pi/3)]
        g=graph(positions=[[[0,0,0]]*3,ps]);r=within_proposals(g,expectation(g))
        events=[e for e in r['events'] if e['kind']=='spatial']
        self.assertEqual(len(events),1);self.assertEqual([f['frame_id'] for f in events[0]['target_frames']],[0,2])
    def test_later_pickup_does_not_hide_prior_swap(self):
        g=graph(fids=(0,1,2,3),positions=[[[0,0,0]]*4,[[1,0,0],[-1,0,0],[-1,0,0],[5,0,0]]]);e=expectation(g)
        e['entities'][1]['intervals'][2].update(expected='reasonable_motion',basis='prompt')
        r=within_proposals(g,e);frames=[[f['frame_id'] for f in x['target_frames']] for x in r['events']]
        self.assertIn([0,1],frames);self.assertNotIn([0,3],frames)
    def test_unknown_motion_is_not_exempt(self):
        g=graph();e=expectation(g);e['entities'][0]['intervals'][0]['expected']='unknown'
        r=within_proposals(g,e);self.assertEqual(r['spatial_units'][0]['comparisons'][0]['eligibility'],'unknown')
    def test_missing_observation_and_reappearance(self):
        g=graph();g['entities'][0]['frame_evidence'][1].update(visible=False,box_xyxy=None,geometry=None)
        r=within_proposals(g,expectation(g));ev=[e for e in r['events'] if e['kind']=='presence']
        self.assertEqual(len(ev),1);self.assertEqual(ev[0]['context_frame_ids'],[0,2])
    def test_bad_depth_and_zero_vector_are_unknown(self):
        self.assertIsNone(cosine([0,0,0],[1,0,0]))
        g=graph();g['entities'][0]['frame_evidence'][0]['geometry']['center_world'][0]=float('nan')
        self.assertIsNone(within_proposals(g,expectation(g))['spatial_units'][0]['comparisons'][0]['cosine'])
    def test_endpoint_not_fused_or_representative(self):
        a=graph(positions=[[[0,0,0]]*3,[[1,0,0],[1,0,0],[-1,0,0]]]);b=graph('shot3')
        r=boundary_proposals([a,b],matching(),fit())
        self.assertEqual(r['spatial_units'][0]['cosine'],-1)
        self.assertEqual([f['frame_id'] for f in r['target_frames']],[2,0])
        self.assertEqual(len(r['presence_units']),2)  # All moving entities remain.
    def test_missing_endpoint_never_backfilled(self):
        a=graph();b=graph('shot3');b['entities'][1]['frame_evidence'][0].update(visible=False,box_xyxy=None)
        r=boundary_proposals([a,b],matching(),fit())
        self.assertIsNone(r['endpoint_observations'][1]['shot3/e1']['geometry'])
        self.assertIsNone(r['spatial_units'][0]['cosine'])
    def test_all_identity_population_required(self):
        m=matching();m['groups']=m['groups'][:1]
        with self.assertRaises(ValueError):boundary_proposals([graph(),graph('shot3')],m,fit())
    def test_multiple_events_penalize_one_unit(self):
        units=[dict(unit_id='x',event_ids=['a','b'],base_status='unknown')]
        r=aggregate(units,{'a':dict(status='conflict'),'b':dict(status='conflict')},True)
        self.assertEqual(r['summary']['confirmed_conflict_pairs'],1);self.assertEqual(r['summary']['total_pairs'],1)
    def test_nonnegative_is_normal_no_conflict_without_coverage(self):
        p=within_proposals(graph(),expectation(graph()));r=aggregate(p['spatial_units'],{},True)
        self.assertEqual(r['summary']['score'],100)
        self.assertEqual(r['units'][0]['status'],'no_conflict')
        self.assertEqual(r['summary']['unresolved_pairs'],0)
        self.assertNotIn('coverage',r['summary'])
        self.assertNotIn('identification_interval',r['summary'])
    def test_spatial_denominator_includes_all_pairs(self):
        rows=[dict(status=s) for s in ['conflict','no_conflict','unknown','exempt']]
        r=score(rows,spatial=True)
        self.assertEqual(r['total_pairs'],4)
        self.assertEqual(r['confirmed_conflict_pairs'],1)
        self.assertEqual(r['score'],75)
        self.assertEqual(r['anomaly_ratio'],.25)
        self.assertEqual(sum(r[k] for k in ['confirmed_conflict_pairs','no_conflict_pairs','unresolved_pairs','exempt_pairs']),4)
    def test_unknown_pairs_no_penalty_and_empty_has_no_score(self):
        self.assertEqual(score([dict(status='unknown')],True)['score'],100)
        self.assertIsNone(score([],True)['score'])
        self.assertIsNone(score([],True)['anomaly_ratio'])
    def test_boundary_nonnegative_and_missing_geometry_distinct(self):
        units=[dict(unit_id='a',event_ids=[],base_status='unknown',cosine=.5),
               dict(unit_id='b',event_ids=[],base_status='unknown',cosine=None)]
        r=aggregate(units,{},True)
        self.assertEqual([r['status'] for r in r['units']],['no_conflict','unknown'])
        self.assertEqual(r['summary']['total_pairs'],2)
        self.assertEqual(r['summary']['score'],100)
    def test_presence_formula_and_coverage_unchanged(self):
        r=score([dict(status=s) for s in ['compatible','conflict','unknown','exempt']])
        self.assertAlmostEqual(r['score'],100*2/3)
        self.assertEqual(r['N'],3)
        self.assertAlmostEqual(r['coverage'],2/3)

    def test_boundary_context_cannot_replace_endpoint_witness(self):
        event=dict(event_id='x',kind='presence',target_frames=[dict(shot_id='shot1',frame_id=2),dict(shot_id='shot3',frame_id=0)])
        images=[dict(shot_id=s,frame_id=f,image_size=[10,10]) for s in ('shot1','shot3') for f in (0,1,2)]
        r=validate_checks(dict(checks=[check(event,[('shot1',1),('shot3',1)])],limitations=''),dict(events=[event]),images,dict(facts=[dict(fact_id='p')]),True)
        self.assertEqual(r['x']['status'],'unknown')
        r=validate_checks(dict(checks=[check(event,[('shot1',2),('shot3',0)])],limitations=''),dict(events=[event]),images,dict(facts=[dict(fact_id='p')]),True)
        self.assertEqual(r['x']['status'],'conflict')
    def test_spatial_needs_independent_local_order(self):
        event=dict(event_id='x',kind='spatial',target_frames=[dict(shot_id='shot1',frame_id=2),dict(shot_id='shot3',frame_id=0)])
        images=[dict(shot_id=s,frame_id=f,image_size=[10,10]) for s,f in [('shot1',2),('shot3',0)]]
        raw=dict(checks=[check(event,[('shot1',2),('shot3',0)])],limitations='')
        r=validate_checks(raw,dict(events=[event]),images,dict(facts=[dict(fact_id='p')]),True,{})
        self.assertEqual(r['x']['status'],'unknown')
    def test_expectation_requires_causal_basis(self):
        g=graph();r=expectation(g);payload=dict(shot_id='shot1',entities=g['entities'],frames=[dict(frame_id=i) for i in (0,1,2)],normal_story_prompt=dict(facts=[dict(fact_id='p')]))
        validate_expectation(r,payload)
        r['entities'][0]['intervals'][0]['expected']='reasonable_motion'
        with self.assertRaises(ValueError):validate_expectation(r,payload)
    def test_singleton_gets_geometry_and_within(self):
        jobs=plan('/tmp/case',[dict(shot_id='single',scene_id='alone')],0,'GPU-test')
        names=[j['stage'] for j in jobs]
        self.assertIn('pi3x_single',names);self.assertIn('within_single',names)
        self.assertFalse(any(n.startswith('pair_') for n in names))
    def test_only_consecutive_scene_occurrences(self):
        shots=[dict(shot_id=s,scene_id=c) for s,c in [('a','room'),('b','garden'),('c','room'),('d','room')]]
        self.assertEqual([r['shot_ids'] for r in scope_for(shots)['cross_shot_pairs']],[['a','c'],['c','d']])
    def test_registration_methods_remain_separate(self):
        shots=[dict(shot_id=s) for s in ('shot1','shot2','shot3')]
        opt=plan('/tmp/case',shots,0,'GPU-test');direct=plan('/tmp/case',shots,0,'GPU-test',alignment_method='codex_direct')
        self.assertTrue(any('roma_matches' in j['stage'] for j in opt))
        self.assertFalse(any('roma_matches' in j['stage'] for j in direct))
        self.assertTrue(any('register_gs_codex.py' in ' '.join(j['command']) for j in direct))
        self.assertTrue(any(j['stage']=='within_shot2' for j in opt))
    def test_expected_static_jump_cannot_be_anchor(self):
        from gs_identity_population import validate_anchors
        nodes=[{f'{sid}/e0':dict(motion_status='static',geometry=box([0,0,0]),anchor_observed_static=False)} for sid in ('shot1','shot3')]
        m=dict(groups=[dict(group_id='g0',a_ids=['shot1/e0'],b_ids=['shot3/e0'],identity='matched',anchor_eligible=True)],structural_anchor_group_ids=['g0'])
        with self.assertRaises(AssertionError):validate_anchors(m,nodes)
    def test_boundary_conflict_requires_joint_presence(self):
        targets=[dict(shot_id='shot1',frame_id=2),dict(shot_id='shot3',frame_id=0)]
        event=dict(event_id='x',kind='spatial',target_frames=targets,endpoint_groups=['g0','g1'])
        raw=dict(checks=[check(event,[('shot1',2),('shot3',0)])],limitations='')
        images=[dict(t,image_size=[10,10]) for t in targets]
        r=validate_checks(raw,dict(events=[event]),images,dict(facts=[dict(fact_id='p')]),True,{'x':dict(opposite_supported=True)})
        self.assertEqual(r['x']['status'],'unknown')
    def test_no_scheduler_dependency_cycle(self):
        jobs=plan('/tmp/case',[dict(shot_id=s) for s in ('shot1','shot2','shot3')],0,'GPU-test')
        done=set()
        for j in jobs:
            self.assertTrue(set(j['depends'])<=done);done.add(j['stage'])


if __name__=='__main__':unittest.main()
