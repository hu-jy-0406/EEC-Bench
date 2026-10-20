"""Restored spatial review contract; synthetic calls only, no API/GPU."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import gs_boundary_spatial_review as m
from gs_temporal_core import boundary_proposals
from test_gs_temporal import graph,fit


def witness(fid):
    return dict(frame_id=fid,subject_region_xyxy=[1,1,4,4],object_region_xyxy=[1,1,4,4],
                reference_region_xyxy=[0,0,5,5],observation='body and support evidence')


class RestoredSpatialTests(unittest.TestCase):
    def setUp(self):
        positions=[[[0,0,0]]*3,[[1,0,0]]*3,[[0,3,0]]*3,[[0,4,0]]*3]
        self.graphs=[graph(s,positions=positions) for s in ('shot1','shot3')]
        self.matching=dict(groups=[dict(group_id=f'g{i}',a_ids=[f'shot1/e{i}'],b_ids=[f'shot3/e{i}'],identity='matched') for i in range(4)],
                           local_origin_group_id='g2',local_reference_group_id='g3')
        self.proposals=boundary_proposals(self.graphs,self.matching,fit())
        self.event=dict(event_id='spatial_pair_g0_g1',kind='spatial',endpoint_groups=['g0','g1'],
                        target_frames=self.proposals['target_frames'],cosine=-.3)
        self.proposals['events']=[self.event]
        self.images=[[dict(shot_id=s,frame_id=f,image_size=[10,10]) for f in (0,1,2)] for s in ('shot1','shot3')]
        self.raws=[]
        for side,sid in enumerate(('shot1','shot3')):
            relations=[]
            for axis in m.AXES:
                order=('negative' if side==0 else 'positive') if axis=='cross_anchor_up' else 'unknown'
                relations.append(dict(subject_id=sid+'/e0',object_id=sid+'/e1',origin_anchor_id=sid+'/e2',reference_anchor_id=sid+'/e3',
                                      axis=axis,order=order,reference_direction_verified=True,common_support_verified=True,
                                      center_order_supported=axis=='cross_anchor_up',geometry_error_can_reverse=axis!='cross_anchor_up',
                                      evidence=[witness(0),witness(2)],reason='horizontal body order is robust',uncertainty='height unknown'))
            self.raws.append(dict(shot_id=sid,placements=[dict(entity_id=sid+'/e'+str(i),support_entity_id=sid+'/e2',support_verified=True,
                                                            frame_ids=[0,2],reason='same support') for i in [0,1]],relations=relations,limitations='height uncertain'))
        self.verifier=dict(relations=[dict(relation_id=self.event['event_id'],verdict='conflict',
            **{k:True for k in m.VERIFY_GATES},witnesses_a=[witness(0),witness(2)],witnesses_b=[witness(0),witness(2)],
            reason='independent horizontal reversal',remaining_alternatives='height unknown',
            prompt_motion_review=dict(prompt_fact_references=['p'],specified_motion='only a book moves',affected_entities=['book'],
                                      causal_explanation_of_observed_relation_change='neither vessel moved by story',verdict='does_not_explain_change'))],limitations='')

    def evidence(self):
        return m.local_evidence([self.event],self.matching,self.raws,self.proposals,sum(self.images,[]))

    def test_horizontal_reversal_survives_unknown_vertical(self):
        support=self.evidence()[self.event['event_id']]
        self.assertTrue(support['opposite_supported'])
        self.assertFalse(support['local_axis_evidence']['vertical']['opposite_supported'])
        self.raws[0]['relations'][0]['geometry_error_can_reverse']=True
        self.assertFalse(self.evidence()[self.event['event_id']]['opposite_supported'])

    def test_canonical_sign_never_mutates_original_endpoint_prose_or_witnesses(self):
        self.event['endpoint_groups']=['g1','g0']
        original=copy.deepcopy(self.raws)
        support=self.evidence()[self.event['event_id']]
        self.assertEqual(self.raws,original)
        self.assertTrue(support['opposite_supported'])
        self.assertEqual(support['local_axis_evidence']['cross_anchor_up']['orders'],[1,-1])
        for side,sid in enumerate(('shot1','shot3')):
            row=support['observations'][side]['cross_anchor_up']
            raw=original[side]['relations'][0]
            for key in raw:self.assertEqual(row[key],raw[key])
            self.assertEqual(row['canonical_relation']['subject_id'],sid+'/e1')
            self.assertEqual(row['canonical_relation']['object_id'],sid+'/e0')
            self.assertNotEqual(row['order'],row['canonical_relation']['order'])

    def test_context_witnesses_count_but_do_not_replace_endpoint(self):
        self.assertTrue(self.evidence()[self.event['event_id']]['opposite_supported'])
        self.raws[0]['relations'][0]['evidence']=[witness(0),witness(1)]
        self.assertFalse(self.evidence()[self.event['event_id']]['opposite_supported'])

    def test_endpoint_geometry_and_all_context_preserved(self):
        before=copy.deepcopy(self.graphs)
        payloads=m.build_local_payloads(self.graphs,self.matching,self.proposals,self.images)
        self.assertEqual(self.graphs,before)
        for side,p in enumerate(payloads):
            self.assertEqual(len(p['images']),3)
            self.assertEqual(p['graph']['entities'][0]['frame_evidence'],before[side]['entities'][0]['frame_evidence'])
            self.assertEqual(p['graph']['entities'][0]['geometry']['center_world'],[0,0,0])
            self.assertTrue(all(e['entity_id'].startswith(p['graph']['shot_id']+'/') for e in p['graph']['entities']))
        self.graphs[0]['entities'][0]['frame_evidence'][-1]['visible']=False
        self.assertIsNone(m.endpoint_graphs(self.graphs,self.proposals)[0]['entities'][0]['geometry'])

    def test_original_prompt_is_verbatim_prefix(self):
        with tempfile.TemporaryDirectory() as root:
            for name in ['gs_relation_shot_v1.txt','verify_cosine.txt']:
                text=Path(m.restored_prompt(root,name)).read_text()
                self.assertEqual(text,(m.PROMPTS/name).read_text()+m.SCOPE)

    def test_old_verify_gates_and_prompt_exemption_and_joint_presence(self):
        support=self.evidence();story=dict(facts=[dict(fact_id='p')]);presence={'g0':'compatible','g1':'compatible'}
        def run():
            return m.finalize([self.event],self.verifier,support,self.proposals,sum(self.images,[]),story,presence)[self.event['event_id']]
        self.assertEqual(run()['status'],'conflict')
        presence['g0']='unknown';self.assertEqual(run()['status'],'unknown')
        presence['g0']='compatible'
        self.verifier['relations'][0]['geometry_error_excluded']=False
        self.assertEqual(run()['status'],'unknown')
        self.verifier['relations'][0]['prompt_motion_review']['verdict']='explains_change'
        self.assertEqual(run()['status'],'exempt')

    def test_missing_reference_stays_unknown(self):
        self.matching['local_origin_group_id']='absent'
        support=self.evidence()
        self.assertFalse(support[self.event['event_id']]['common_support_eligible'])
        out=m.finalize([self.event],dict(relations=[],limitations=''),support,self.proposals,sum(self.images,[]),dict(facts=[]),{})
        self.assertEqual(out[self.event['event_id']]['status'],'unknown')
        self.assertIn('review',out[self.event['event_id']])

    def test_calls_use_original_schemas_and_all_shot_images(self):
        calls=[]
        with tempfile.TemporaryDirectory() as root:
            def call(name,prompt,payload,images,schema):
                calls.append((name,prompt,payload,images,schema))
                if name.startswith('boundary_local_'):
                    side=0 if name.endswith('shot1') else 1
                    return copy.deepcopy(self.raws[side])
                return copy.deepcopy(self.verifier)
            stage=SimpleNamespace(case=Path(root),story=dict(facts=[dict(fact_id='p')]),call=call)
            out=m.review_spatial(stage,self.graphs,self.matching,self.proposals,dict(fits={'all_structures':fit()}),self.images,{'g0':'compatible','g1':'compatible'})
            self.assertEqual(out[self.event['event_id']]['status'],'conflict')
            self.assertEqual([len(c[3]) for c in calls],[3,3,6])
            self.assertEqual([Path(c[1]).name for c in calls],['gs_relation_shot_v1.txt','gs_relation_shot_v1.txt','verify_cosine.txt'])
            self.assertEqual(calls[0][4],m.SHOT_SCHEMA)
            self.assertEqual(calls[-1][4],m.VERIFY)
            self.assertTrue((Path(root)/'boundary/local_support.json').exists())

    def test_parallel_local_contexts_are_isolated_and_verify_waits_for_both(self):
        import threading
        gate=threading.Barrier(2);completed=set();lock=threading.Lock()
        with tempfile.TemporaryDirectory() as root:
            def call(name,prompt,payload,images,schema):
                if name.startswith('boundary_local_'):
                    sid=payload['graph']['shot_id'];side=0 if sid=='shot1' else 1
                    self.assertTrue(all(f['shot_id']==sid for f in images))
                    self.assertTrue(all(e['entity_id'].startswith(sid+'/') for e in payload['graph']['entities']))
                    gate.wait(timeout=3)
                    with lock:completed.add(sid)
                    return copy.deepcopy(self.raws[side])
                self.assertEqual(completed,{'shot1','shot3'})
                return copy.deepcopy(self.verifier)
            stage=SimpleNamespace(case=Path(root),story=dict(facts=[dict(fact_id='p')]),call=call,runtime={'temporal_parallel_local_spatial':True})
            out=m.review_spatial(stage,self.graphs,self.matching,self.proposals,dict(fits={'all_structures':fit()}),self.images,{'g0':'compatible','g1':'compatible'})
            self.assertEqual(out[self.event['event_id']]['status'],'conflict')

    def test_boundary_stage_routes_presence_and_spatial_separately(self):
        from unittest.mock import patch
        from run_gs_temporal_stage import Stage
        from test_gs_temporal import check
        proposals=boundary_proposals(self.graphs,self.matching,fit())
        presence_events=copy.deepcopy(proposals['events'])
        proposals['events']=presence_events+[self.event]
        proposals['spatial_units']=[dict(unit_id='pair_g0_g1',event_ids=[self.event['event_id']],base_status='unknown')]
        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            for sid,g in zip(['shot1','shot3'],self.graphs):
                path=root/'selected'/f'{sid}_scene.json';path.parent.mkdir(exist_ok=True)
                path.write_text(json.dumps(g))
            (root/'matching.json').write_text(json.dumps(self.matching))
            path=root/'registration/roma_geometry/registration.json';path.parent.mkdir(parents=True)
            path.write_text(json.dumps(dict(fits={'all_structures':fit()})))
            stage=Stage.__new__(Stage);stage.case=root;stage.story=dict(facts=[dict(fact_id='p')])
            stage.source_images=lambda sid:(None,self.images[0 if sid=='shot1' else 1])
            def presence_call(name,payload,images):
                self.assertTrue(all(e['kind']=='presence' for e in payload['events']))
                checks=[]
                for e in payload['events']:
                    r=check(e,[('shot1',2),('shot3',0)])
                    r.update(status='compatible',cause='none',conflict_kind='none')
                    checks.append(r)
                return dict(checks=checks,limitations='fixture')
            stage.review_events=presence_call
            def call(name,prompt,payload,images,schema):
                if name.startswith('boundary_local_'):
                    return copy.deepcopy(self.raws[0 if name.endswith('shot1') else 1])
                self.assertEqual(Path(prompt).name,'verify_cosine.txt')
                return copy.deepcopy(self.verifier)
            stage.call=call
            with patch('run_gs_temporal_stage.boundary_proposals',return_value=proposals):
                stage.boundary()
            result=json.loads((root/'boundary/results.json').read_text())
            self.assertEqual(result['spatial']['summary']['confirmed_conflict_pairs'],1)
            self.assertEqual(result['presence']['summary']['C'],4)
            self.assertEqual(result['target_frames'],proposals['target_frames'])
            self.assertTrue(all('review' in e for e in result['events']))


if __name__=='__main__':unittest.main()
