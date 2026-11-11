import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from local_order_contract import (plan, validate_extraction, aligned_queries, compare_local, summarize,
    EXTRACT_SCHEMA, VERIFY_SCHEMA)
from partial_scene_contract import schema_validate


def graph(sid):
    frames=[dict(frame_id=f,image_size=[200,150]) for f in (0,1)]
    entities=[dict(entity_id=e,name='arbitrary_'+e,observations=[dict(frame_id=f,exist=True,visible=True,box_xyxy=[10,10,100,100]) for f in (0,1)]) for e in ('x','y','surface')]
    anchors=[dict(anchor_id=a,entity_id='surface',part='surface',axis_description='fixed physical edge '+a,resolvable=True,
        observations=[dict(frame_id=f,negative_endpoint_xy=[0,0],positive_endpoint_xy=[100,100],reason='edges') for f in (0,1)]) for a in ('u','v')]
    relations=[dict(subject_id=e,object_id='surface',predicate='supported_by',observations=[dict(value='true')]) for e in ('x','y')]
    return dict(shot_id=sid,frames=frames,entities=entities,anchors=anchors,relations=relations,
        entity_scopes=[dict(entity_id=e['entity_id'],scope='single') for e in entities])


def obs(value='less',fid=0):
    return dict(frame_id=fid,axis_verified=True,common_support=True,witness='bounded_center_from_parts',
        subject_part_xyxy=[10,10,30,30],object_part_xyxy=[25,15,40,35],
        subject_center_bounds_xyxy=[14,25,20,30],object_center_bounds_xyxy=[28,30,34,35],
        alternatives_can_reverse=False,values=[value] if value else [],reason='visible lower sides bound center order; full footprint may overlap')


def extract(g,value='less'):
    return dict(shot_id=g['shot_id'],relations=[dict(query_id=q['query_id'],observations=[obs(value,f) for f in (0,1)]) for q in plan(g)['queries']])


def fixture(a_value='less',b_value='less',reverse=False):
    a,b=graph('A'),graph('B')
    ev=[dict(frame_id=0,region_xyxy=[0,0,100,100],reason='visible')]
    alignment=dict(groups=[dict(group_id='g'+str(i),a_ids=[e],b_ids=[e],status='matched',evidence_a=ev,evidence_b=ev,reason='same') for i,e in enumerate(('x','y','surface'))],
        anchors=[dict(a_anchor=ax,b_anchor=ax,status='aligned',orientation='reversed' if reverse else 'same',evidence_a=ev,evidence_b=ev,reason='physical edges') for ax in ('u','v')])
    plans=[plan(a),plan(b)];ext=[extract(a,a_value),extract(b,b_value)]
    queries,_=aligned_queries(plans,[a,b],alignment)
    review=dict(relations=[dict(query_id=q['query_id'],correspondence_verified=True,side_a=[obs(a_value,f) for f in (0,1)],side_b=[obs(b_value,f) for f in (0,1)],reason='independent pixels') for q in queries])
    policy=dict(policy_id='test',source='fixture',default_rule='must_persist',entity_overrides=[])
    return [a,b],plans,ext,alignment,review,policy


class LocalOrderTests(unittest.TestCase):
    def test_all_axes_even_when_no_axis_relations_exist(self):
        p=plan(graph('A'));self.assertEqual([q['anchor_id'] for q in p['queries']],['u','v'])
    def test_all_pairs_are_name_independent(self):
        g=graph('A');z=copy.deepcopy(g['entities'][0]);z['entity_id']='z';z['name']='not_a_cup';g['entities'].append(z)
        g['relations'].append(dict(subject_id='z',object_id='surface',predicate='supported_by',observations=[dict(value='true')]))
        self.assertEqual(len(plan(g)['queries']),6)
    def test_missing_axis_is_rejected(self):
        g=graph('A');r=extract(g);r['relations'].pop()
        with self.assertRaises(ValueError):validate_extraction(r,plan(g),g)
    def test_partial_bases_can_support_center_order(self):
        g=graph('A');self.assertEqual(validate_extraction(extract(g),plan(g),g)['relations'][0]['observations'][0]['values'],['less'])
    def test_reversal_is_conflict(self):
        out=compare_local(*fixture('less','greater'));self.assertTrue(all(r['reason_code']=='local_order_conflict' for r in out['items']))
    def test_camera_axis_reversal_alone_not_conflict(self):
        out=compare_local(*fixture('less','greater',True));self.assertTrue(all(r['reason_code']=='shared_local_order' for r in out['items']))
    def test_physical_reversal_with_reversed_camera_axis(self):
        out=compare_local(*fixture('less','less',True));self.assertTrue(all(r['reason_code']=='local_order_conflict' for r in out['items']))
    def test_review_can_fill_extraction_unknown(self):
        f=fixture('less','greater')
        for row in f[2][1]['relations']:
            for r in row['observations']:r['values']=[]
        self.assertEqual(compare_local(*f)['items'][0]['reason_code'],'local_order_conflict')
    def test_no_fabrication_for_unknown_review(self):
        f=fixture('less','greater')
        for r in f[4]['relations']:
            for o in r['side_b']:o['values']=[]
        self.assertEqual(compare_local(*f)['items'][0]['reason_code'],'local_order_unresolved')
    def test_review_disagreement_not_silently_overwritten(self):
        f=fixture('less','greater')
        for r in f[4]['relations']:
            for o in r['side_b']:o['values']=['less']
        self.assertEqual(compare_local(*f)['items'][0]['reason_code'],'extraction_review_disagreement')
    def test_missing_grounding_or_axis_blocks_known_value(self):
        for field,value in [('subject_center_bounds_xyxy',None),('subject_part_xyxy',None),('axis_verified',False),('common_support',False),('witness','unknown')]:
            g=graph('A');e=extract(g);e['relations'][0]['observations'][0][field]=value
            with self.assertRaises(ValueError):validate_extraction(e,plan(g),g)
    def test_reverse_alternative_blocks_singleton(self):
        g=graph('A');e=extract(g);e['relations'][0]['observations'][0]['alternatives_can_reverse']=True
        with self.assertRaises(ValueError):validate_extraction(e,plan(g),g)
    def test_invisible_frame_not_filled(self):
        g=graph('A');g['entities'][0]['observations'][0]['visible']=False
        with self.assertRaises(ValueError):validate_extraction(extract(g),plan(g),g)
    def test_within_shot_reversal_retained(self):
        f=fixture()
        for r in f[2][0]['relations']:r['observations'][1]['values']=['greater']
        for r in f[4]['relations']:r['side_a'][1]['values']=['greater']
        self.assertEqual(compare_local(*f)['items'][0]['reason_code'],'within_shot_order_change')
    def test_uncertain_overlap_not_forced(self):
        self.assertEqual(summarize([dict(frame_id=0,values=['less','aligned','greater'])])[0],set())
    def test_allowed_motion_not_conflict(self):
        f=fixture('less','greater');f[-1]['default_rule']='may_change'
        self.assertEqual(compare_local(*f)['items'][0]['reason_code'],'explained_change')
    def test_unverified_correspondence_not_compared(self):
        f=fixture('less','greater');f[4]['relations'][0]['correspondence_verified']=False
        self.assertEqual(compare_local(*f)['items'][0]['reason_code'],'local_correspondence_unresolved')
    def test_policy_typo_rejected(self):
        f=fixture();f[-1]['entity_overrides']=[dict(shot_id='A',entity_id='typo',rule='must_persist',reason='bad')]
        with self.assertRaises(ValueError):compare_local(*f)
    def test_tampered_plan_rejected(self):
        f=fixture();f[1][0]['queries'].pop()
        with self.assertRaises(ValueError):compare_local(*f)
    def test_schema_exact_and_no_duplicate_frames(self):
        g=graph('A');e=extract(g);schema_validate(e,EXTRACT_SCHEMA)
        e['relations'][0]['observations'][1]['frame_id']=0
        with self.assertRaises(ValueError):validate_extraction(e,plan(g),g)

if __name__=='__main__':unittest.main()
