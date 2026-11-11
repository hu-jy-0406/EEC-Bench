import copy,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_wedetect_shot_entities as io
import gs_shot_prompt_recovery as r

# Recovery attaches the highest-score Grounding DINO box per missing prompt entity and frame, without an agent
# review (owner, 2026-11-03, open-questions Q15). The agent-review tests of 2026-09-22 were replaced.
class Recovery(unittest.TestCase):
 def setUp(self):
  self.p=dict(shot_id='S',frames=[dict(frame_id=i,image_size=[100,100],detections=([dict(candidate_id='f0:d1',name='cup',box_xyxy=[1,1,10,10],score=.5)] if i==0 else [])) for i in (0,1)],candidate_filter={})
  self.raw=dict(shot_id='S',entities=[dict(entity_id='e1',name='cup',candidate_ids=['f0:d1'])],rejected_detections=[])
  self.old=io.validate_result(self.raw,self.p)
  self.b=dict(bindings=[dict(entity_id='e1',status='bound',prompt_entity_id='cup',candidate_prompt_entity_ids=[],witness_frame_ids=[0],reason='visible')],queries=[dict(prompt_entity_id=p,detection_query=p+'.') for p in ['cup','pillar']])
  self.own=dict(entities=self.old['entities'],prompt_entities=[dict(prompt_entity_id=p,name=p,expectation='required') for p in ['cup','pillar']])
  self.cov=r.coverage(self.own,self.b,[dict(frame_id=i) for i in (0,1)])
  self.n=[dict(frame_id=1,detections=[dict(candidate_id='f1:gd1',name='cup',prompt_entity_id='cup',box_xyxy=[2,2,11,11],score=.8),dict(candidate_id='f1:gd2',name='cup',prompt_entity_id='cup',box_xyxy=[50,50,60,60],score=.3)]),dict(frame_id=0,detections=[dict(candidate_id='f0:gd1',name='pillar',prompt_entity_id='pillar',box_xyxy=[30,1,40,90],score=.9)])]
 def grounding(self):
  return r.materialize_grounding(self.old,self.p,self.own,self.n,self.b,self.cov)
 def test_reverse_coverage_and_partial(self):
  self.assertEqual(self.cov[0]['missing_detection_frame_ids'],[1]);self.assertEqual(self.cov[1]['missing_detection_frame_ids'],[0,1])
  self.assertEqual([c['status'] for c in self.cov],['partial','uncovered'])
 def test_no_required_no_search(self):
  self.own['prompt_entities'][1]['expectation']='not_required';self.assertEqual(r.coverage(self.own,self.b,[dict(frame_id=0)])[1]['missing_detection_frame_ids'],[])
 def test_highest_score_box_fills_gaps_with_exact_boxes(self):
  x,_,canonical,b=self.grounding()
  self.assertEqual(x['entities'][0]['observations'][0]['box_xyxy'],[1,1,10,10]);self.assertEqual(x['entities'][0]['observations'][1]['box_xyxy'],[2,2,11,11])
  self.assertIn('f1:gd2',[d['candidate_id'] for d in canonical['rejected_detections']])
  self.assertEqual(x['entities'][1]['name'],'pillar');self.assertEqual(x['entities'][1]['observations'][0]['box_xyxy'],[30,1,40,90]);self.assertIsNone(x['entities'][1]['observations'][1]['box_xyxy'])
  self.assertEqual(b['bindings'][-1],dict(entity_id=x['entities'][1]['entity_id'],status='bound',prompt_entity_id='pillar',candidate_prompt_entity_ids=[],witness_frame_ids=[0],reason='Directly recovered by the prompt-targeted Grounding DINO query.'))
 def test_candidate_for_a_covered_frame_never_replaces_a_box(self):
  self.n.append(dict(frame_id=0,detections=[dict(candidate_id='f0:gd2',name='cup',prompt_entity_id='cup',box_xyxy=[70,70,80,80],score=.99)]))
  x,_,canonical,_=self.grounding()
  self.assertEqual(x['entities'][0]['observations'][0]['box_xyxy'],[1,1,10,10]);self.assertIn('f0:gd2',[d['candidate_id'] for d in canonical['rejected_detections']])
 def test_candidate_of_another_prompt_entity_is_not_used(self):
  self.n[0]['detections']=[dict(candidate_id='f1:gd1',name='cup',prompt_entity_id='lamp',box_xyxy=[2,2,11,11],score=.8)]
  x,_,canonical,_=self.grounding()
  self.assertIsNone(x['entities'][0]['observations'][1]['box_xyxy']);self.assertIn('f1:gd1',[d['candidate_id'] for d in canonical['rejected_detections']])
 def test_group_entity_recovered_boxes_form_a_new_local_entity(self):
  p=dict(shot_id='S',frames=[dict(frame_id=0,image_size=[100,100],detections=[dict(candidate_id='f0:d1',name='glass',box_xyxy=[1,1,10,10],score=.5),dict(candidate_id='f0:d2',name='glass',box_xyxy=[20,1,30,10],score=.5)]),dict(frame_id=1,image_size=[100,100],detections=[])],candidate_filter={})
  old=io.validate_result(dict(shot_id='S',entities=[dict(entity_id='e1',name='glass',candidate_ids=['f0:d1']),dict(entity_id='e2',name='glass',candidate_ids=['f0:d2'])],rejected_detections=[]),p)
  b=dict(bindings=[dict(entity_id=e,status='bound',prompt_entity_id='glasses',candidate_prompt_entity_ids=[],witness_frame_ids=[0],reason='visible') for e in ('e1','e2')],queries=[dict(prompt_entity_id='glasses',detection_query='glass.')])
  own=dict(entities=old['entities'],prompt_entities=[dict(prompt_entity_id='glasses',name='Three glasses',expectation='required')])
  cov=r.coverage(own,b,[dict(frame_id=i) for i in (0,1)]);self.assertEqual(cov[0]['missing_detection_frame_ids'],[1])
  n=[dict(frame_id=1,detections=[dict(candidate_id='f1:gd1',name='glass',prompt_entity_id='glasses',box_xyxy=[2,2,11,11],score=.7)])]
  x,_,_,final=r.materialize_grounding(old,p,own,n,b,cov)
  self.assertEqual([o['box_xyxy'] for o in x['entities'][0]['observations']],[[1,1,10,10],None]);self.assertEqual([o['box_xyxy'] for o in x['entities'][1]['observations']],[[20,1,30,10],None])
  self.assertEqual([o['box_xyxy'] for o in x['entities'][2]['observations']],[None,[2,2,11,11]])
  self.assertEqual([(row['entity_id'],row['prompt_entity_id']) for row in final['bindings']],[('e1','glasses'),('e2','glasses'),('e3','glasses')])
  r.validate_binding(final,dict(own,entities=x['entities']),'v2')
 def test_bound_requires_actual_witness(self):
  self.b['bindings'][0]['witness_frame_ids']=[1]
  with self.assertRaises(ValueError):r.validate_binding(self.b,self.own)
 def test_incomplete_recovery_blocks_downstream(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);io.dump(p/'shot_prompt_recovery/run.json',dict(status='failed'))
   with self.assertRaises(ValueError):r.active_entities_root(p)
 def test_rollback_root(self):
  with tempfile.TemporaryDirectory() as tmp:self.assertEqual(r.active_entities_root(Path(tmp)),Path(tmp)/'entities')
 def test_pipeline_dependency_and_rollback(self):
  from run_gs_temporal import plan
  shots=[dict(shot_id='shot1',scene_id='a'),dict(shot_id='shot3',scene_id='a')]
  jobs=plan(Path('/tmp/test'),shots,0,'GPU-0000000000000000',stop_after='identity',prompt_binding=True)
  by={j['stage']:j for j in jobs};self.assertIn('shot_prompt_recovery',by);self.assertIn('shot_prompt_recovery',by['geocalib']['depends']);self.assertIn('detection_and_clustering',by['shot_prompt_recovery']['depends'])
  old=plan(Path('/tmp/test'),shots,0,'GPU-0000000000000000',stop_after='identity',prompt_binding=True,prompt_recovery='off');self.assertNotIn('shot_prompt_recovery',[j['stage'] for j in old])
 def test_unanimous_global_binding_reuse_no_identity_merge(self):
  from gs_prompt_binding import reuse_shot_bindings
  with tempfile.TemporaryDirectory() as tmp:
   case=Path(tmp);root=case/'shot_prompt_recovery'
   reg=dict(shot_ids=['S'],entities=[dict(prompt_entity_id='cup',evidence=[dict(fact_id='f')])])
   io.dump(root/'results.json',dict(status='success'));io.dump(root/'prompt_registry.json',reg);io.dump(root/'shots/S/binding_final.json',self.b)
   visual=dict(entities=[dict(global_entity_id='g1',appearances=[dict(shot_id='S',local_entity_id='e1')])])
   rows,_=reuse_shot_bindings(case,reg,visual);self.assertEqual(rows[0]['prompt_entity_id'],'cup');self.assertEqual(rows[0]['global_entity_id'],'g1')
   self.b['bindings'][0].update(status='unknown',prompt_entity_id=None,witness_frame_ids=[]);io.dump(root/'shots/S/binding_final.json',self.b)
   self.assertEqual(reuse_shot_bindings(case,reg,visual)[0],[])
if __name__=='__main__':unittest.main()
