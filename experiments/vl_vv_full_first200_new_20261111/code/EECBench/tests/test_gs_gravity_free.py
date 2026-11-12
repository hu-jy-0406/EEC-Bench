import copy,sys,unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from scipy.optimize._numdiff import approx_derivative
from scipy.spatial.transform import Rotation
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from gs_registration_so3 import objective_and_gradient,fit_all_pairs,distances
from gs_registration_3d import fit_all_pairs as fit_yaw
from gs_boundary_relative_review import support_for,finish_spatial,validate_local,LOCAL,VERIFY,GATES
from gs_efficient_transport import wire_schema
from run_gs_temporal import plan

class FreeRegistration(unittest.TestCase):
 def test_gradient(self):
  rng=np.random.default_rng(6);p=rng.normal(size=(32,3));q=rng.normal(size=(32,3))
  for w in ([.3,-.7,.6],[0.,0.,0.]):
   x=np.r_[.2,w,.5,-.3,.1]
   np.testing.assert_allclose(objective_and_gradient(x,p,q)[1],approx_derivative(lambda a:objective_and_gradient(a,p,q)[0],x).ravel(),atol=1e-6,rtol=1e-6)
 def test_full_tilt_recovery_and_yaw_limitation(self):
  q=np.random.default_rng(5).normal(size=(32,3));R=Rotation.from_euler('xyz',[.5,-.4,.7]).as_matrix();p=1.4*q@R.T+[.2,-.3,.8]
  f=fit_all_pairs(p,q)
  self.assertLess(f['objective_value'],1e-6);np.testing.assert_allclose(f['rotation'],R,atol=1e-6)
  self.assertGreater(fit_yaw(p,q,yaw_starts=4)['objective_value'],1.)
  self.assertAlmostEqual(np.linalg.det(f['rotation']),1.);self.assertIsNone(f['yaw_deg'])
 def test_exact_sum_and_outlier_kept(self):
  p=np.array([[3.,4,0],[0,0,120.]])
  self.assertEqual(objective_and_gradient(np.zeros(7),p,np.zeros_like(p))[0],125.)
  q=np.random.default_rng(8).normal(size=(16,3));p=q.copy();p[-1]+=[90.,0,0]
  f=fit_all_pairs(p,q);e=distances(np.array(f['parameters']),p,q)
  self.assertEqual(f['points_removed'],0);self.assertEqual(f['fit_rows'],16)
  self.assertAlmostEqual(e.sum(),f['objective_value']);self.assertGreater(e[-1],80.)
 def test_gauge_equivariance(self):
  rng=np.random.default_rng(12);q=rng.normal(size=(20,3));p=1.2*q@Rotation.from_rotvec([.3,.2,-.6]).as_matrix().T+[1.,2.,-.5]+rng.normal(scale=.003,size=q.shape)
  A=Rotation.from_rotvec([.7,.2,1.]).as_matrix();B=Rotation.from_rotvec([-.4,.3,.5]).as_matrix()
  a=fit_all_pairs(p,q);b=fit_all_pairs(p@A.T,q@B.T)
  self.assertAlmostEqual(a['objective_value'],b['objective_value'],places=7)
  np.testing.assert_allclose(b['rotation'],A@np.array(a['rotation'])@B.T,atol=1e-5)
 def test_invalid_and_degenerate(self):
  for q in (np.zeros((3,3)),np.array([[0,0,0],[1,0,0],[2,0,0]]),np.full((3,3),np.nan)):
   with self.assertRaises(ValueError):fit_all_pairs(q,q)

class RelativeEvidence(unittest.TestCase):
 def fixture(self):
  images=[];obs=[];groups=[]
  for n in range(1,4):groups.append(dict(group_id='g'+str(n),identity='matched',a_ids=['shot1/e'+str(n)],b_ids=['shot3/e'+str(n)]))
  event=dict(event_id='spatial_1',kind='spatial',endpoint_groups=['g1','g2'],entity_ids=['shot1/e1','shot1/e2','shot3/e1','shot3/e2'])
  for sid,target in [('shot1',1),('shot3',0)]:
   images.append([dict(shot_id=sid,frame_id=i,image_size=[100,100]) for i in (0,1)])
   ws=[dict(shot_id=sid,frame_id=i,region_xyxy=[1,1,90,90],observation='two centers and a corresponding desk corner') for i in (0,1)]
   obs.append(dict(shot_id=sid,relations=[dict(event_id='spatial_1',entity_ids=[sid+'/e1',sid+'/e2'],evidence_status='supported',support_entity_id=sid+'/e3',reference_entity_ids=[sid+'/e3'],support_verified=True,reference_verified=True,center_semantics_verified=True,relative_geometry_description='centers relative to an identified desk feature',witnesses=ws,remaining_alternatives='none')],limitations=''))
  proposals=dict(target_frames=[dict(shot_id='shot1',frame_id=1),dict(shot_id='shot3',frame_id=0)])
  matching=dict(groups=groups)
  v=dict(event_id='spatial_1',verdict='conflict',**{k:True for k in GATES},witnesses_a=obs[0]['relations'][0]['witnesses'],witnesses_b=obs[1]['relations'][0]['witnesses'],prompt_motion_review=dict(verdict='does_not_explain_change',prompt_fact_references=['f1'],specified_motion='none authorized',affected_entities=event['entity_ids'],causal_explanation_of_observed_relation_change='no applicable action'),reason='relative placement changes with corresponding support features',remaining_alternatives='none')
  stage=SimpleNamespace(story=dict(facts=[dict(fact_id='f1')]))
  return event,matching,obs,proposals,images,v,stage
 def result(self,mutate=lambda *a:None):
  event,m,obs,p,images,v,stage=self.fixture();mutate(event,m,obs,p,images,v,stage)
  support=support_for([event],m,obs,p,sum(images,[]))
  return finish_spatial(stage,dict(events=[event],raw=dict(relations=[v],limitations=''),support=support),p,images,{'g1':'compatible','g2':'compatible'})['spatial_1']
 def test_supported_and_wire_schema(self):
  self.assertEqual(self.result()['status'],'conflict');wire_schema(LOCAL);wire_schema(VERIFY)
 def test_local_unknown_cannot_be_overridden(self):
  def change(e,m,o,p,i,v,s):o[0]['relations'][0]['evidence_status']='unknown'
  self.assertEqual(self.result(change)['status'],'unknown')
 def test_no_target_no_conflict(self):
  def change(e,m,o,p,i,v,s):o[0]['relations'][0]['witnesses']=o[0]['relations'][0]['witnesses'][:1]
  self.assertEqual(self.result(change)['status'],'unknown')
 def test_no_corresponding_reference_no_conflict(self):
  def change(e,m,o,p,i,v,s):m['groups'][-1]['identity']='ambiguous'
  self.assertEqual(self.result(change)['status'],'unknown')
 def test_prompt_exemption(self):
  def change(e,m,o,p,i,v,s):v['prompt_motion_review']['verdict']='explains_change'
  self.assertEqual(self.result(change)['status'],'exempt')

class BoxerFrameTests(unittest.TestCase):
 def test_camera_frame_gauge_equivariance(self):
  from gs_boxer_camera_frame import model_to_scene,CAMERA_FROM_MODEL
  camera=np.eye(4);camera[:3,:3]=Rotation.from_rotvec([.2,-.3,.1]).as_matrix();camera[:3,3]=[1,2,3]
  gauge=np.eye(4);gauge[:3,:3]=Rotation.from_rotvec([.4,.8,-.6]).as_matrix();gauge[:3,3]=[-2,3,.4]
  np.testing.assert_allclose(model_to_scene(gauge@camera),gauge@model_to_scene(camera),atol=1e-12)
  self.assertAlmostEqual(np.linalg.det(CAMERA_FROM_MODEL),1.)
 def test_level_camera_matches_old_model_axis_convention(self):
  from gs_boxer_camera_frame import model_to_scene
  camera=np.eye(4);camera[:3,:3]=[[1,0,0],[0,0,1],[0,-1,0]]
  np.testing.assert_allclose(model_to_scene(camera),np.eye(4))

class PlanTests(unittest.TestCase):
 def test_free_pipeline_skips_calibration(self):
  shots=[dict(shot_id='shot1',scene_id='a'),dict(shot_id='shot2',scene_id='b'),dict(shot_id='shot3',scene_id='a')]
  jobs=plan(Path('/tmp/free_plan'),shots,0,'GPU-0000000000000000','gravity_free_v1','roma_fps32_free3d','full')
  self.assertNotIn('geocalib',[j['stage'] for j in jobs])
  fit=next(j for j in jobs if j['stage']=='pair_000_registration')
  self.assertEqual(fit['command'][-2:],['--rotation-model','so3'])
  names={j['stage'] for j in jobs};self.assertTrue(all(set(j['depends'])<=names for j in jobs))
 def test_mixed_mode_fails(self):
  with self.assertRaises(ValueError):plan('/tmp/free_plan',[dict(shot_id='shot1')],0,'GPU-0000000000000000','scoring_efficiency_v1','roma_fps32_free3d','spatial')

if __name__=='__main__':unittest.main()
