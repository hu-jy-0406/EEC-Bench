import copy,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_wedetect_shot_entities as io
import gs_shot_prompt_recovery as r

class Recovery(unittest.TestCase):
 def setUp(self):
  self.p=dict(shot_id='S',frames=[dict(frame_id=i,image_size=[100,100],detections=([dict(candidate_id='f0:d1',name='cup',box_xyxy=[1,1,10,10],score=.5)] if i==0 else [])) for i in (0,1)],candidate_filter={})
  self.raw=dict(shot_id='S',entities=[dict(entity_id='e1',name='cup',candidate_ids=['f0:d1'])],rejected_detections=[])
  self.old=io.validate_result(self.raw,self.p)
  self.b=dict(bindings=[dict(entity_id='e1',status='bound',prompt_entity_id='cup',candidate_prompt_entity_ids=[],witness_frame_ids=[0],reason='visible')],queries=[dict(prompt_entity_id=p,detection_query=p+'.') for p in ['cup','pillar']])
  self.own=dict(entities=self.old['entities'],prompt_entities=[dict(prompt_entity_id=p,expectation='required') for p in ['cup','pillar']])
  self.cov=r.coverage(self.own,self.b,[dict(frame_id=i) for i in (0,1)])
  self.n=[dict(frame_id=1,detections=[dict(candidate_id='f1:gd1',name='cup',box_xyxy=[2,2,11,11],score=.8)]),dict(frame_id=0,detections=[dict(candidate_id='f0:gd1',name='pillar',box_xyxy=[30,1,40,90],score=.9)])]
  self.review=dict(new_entities=[dict(new_id='n1',name='pillar',prompt_entity_id='pillar')],decisions=[dict(candidate_id='f1:gd1',status='assigned',target_kind='existing',target_id='e1',reason='cup'),dict(candidate_id='f0:gd1',status='assigned',target_kind='new',target_id='n1',reason='pillar')])
 def test_reverse_coverage_and_partial(self):
  self.assertEqual(self.cov[0]['missing_detection_frame_ids'],[1]);self.assertEqual(self.cov[1]['missing_detection_frame_ids'],[0,1]);self.assertIsNone(self.cov[1]['physical_absence'])
 def test_no_required_no_search(self):
  self.own['prompt_entities'][1]['expectation']='not_required';self.assertEqual(r.coverage(self.own,self.b,[dict(frame_id=0)])[1]['missing_detection_frame_ids'],[])
 def test_exact_boxes_new_and_old(self):
  x,p,raw,b=r.materialize_review(self.review,self.old,self.p,self.n,self.b,self.cov)
  self.assertEqual(x['entities'][0]['observations'][0]['box_xyxy'],[1,1,10,10]);self.assertEqual(x['entities'][0]['observations'][1]['box_xyxy'],[2,2,11,11]);self.assertEqual(x['entities'][1]['observations'][0]['box_xyxy'],[30,1,40,90]);self.assertIsNone(x['entities'][1]['observations'][1]['box_xyxy']);self.assertEqual(b['bindings'][-1]['prompt_entity_id'],'pillar')
 def test_replace_existing_forbidden(self):
  self.n[0]['frame_id']=0
  with self.assertRaisesRegex(ValueError,'replace'):r.materialize_review(self.review,self.old,self.p,self.n,self.b,self.cov)
 def test_no_invented_candidate(self):
  self.review['decisions'][0]['candidate_id']='invented'
  with self.assertRaisesRegex(ValueError,'accounted'):r.materialize_review(self.review,self.old,self.p,self.n,self.b,self.cov)
 def test_no_duplicate_ownership(self):
  self.review['decisions'].append(self.review['decisions'][0])
  with self.assertRaises(ValueError):r.materialize_review(self.review,self.old,self.p,self.n,self.b,self.cov)
 def test_no_empty_new_entity(self):
  self.review['decisions'][1].update(status='rejected',target_kind='none',target_id=None)
  with self.assertRaisesRegex(ValueError,'Empty new'):r.materialize_review(self.review,self.old,self.p,self.n,self.b,self.cov)
 def test_bound_requires_actual_witness(self):
  self.b['bindings'][0]['witness_frame_ids']=[1]
  with self.assertRaises(ValueError):r.validate_binding(self.b,self.own)
 def test_no_new_duplicate_prompt_instance(self):
  self.review['new_entities'][0]['prompt_entity_id']='cup'
  with self.assertRaises(ValueError):r.materialize_review(self.review,self.old,self.p,self.n,self.b,self.cov)
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
 def test_schema_blocks_unknown_existing_assignment(self):
  import jsonschema
  self.b['bindings'][0].update(status='unknown',prompt_entity_id=None,witness_frame_ids=[],candidate_prompt_entity_ids=['cup'])
  schema=r.review_schema(self.old,self.n,self.b,self.cov)
  with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(self.review,schema)
 def test_schema_blocks_existing_covered_frame(self):
  import jsonschema
  self.n[0]['frame_id']=0
  schema=r.review_schema(self.old,self.n,self.b,self.cov)
  with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(self.review,schema)
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
