"""All-entity coverage, motion transitions, anchors and nullable geometry."""
import copy
from pathlib import Path
import sys, tempfile, unittest
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from gs_flow1_evaluator import Eval, save, read
from gs_identity_population import scene_scope, static_matching, validate_anchors
from gs_flow1_compact_payload import obb_corners, pack, unpack, equivalent
import review_aligned_entity_identities as aligned
import run_gs_integrated as integrated

class AllIdentityTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  R=[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]
  box=dict(center_world=[0.,0.,5.],size_xyz=[1.,1.,1.],R_world_from_object=R);box['corners_world']=obb_corners(box)
  from PIL import Image
  image=self.root/'frame.jpg';Image.new('RGB',(20,20)).save(image)
  frame=dict(frame_id=0,path=str(image),sha256=aligned.sha(image),timestamp_sec=0)
  for side,sid in enumerate(('shot1','shot3')):
   entities=[];source=[]
   for i,status in enumerate(('static','moving' if side==0 else 'static','unknown')):
    obs=[dict(frame_id=0,box_xyxy=[1,1,10,10],visible=True,exist=True)]
    geometry=copy.deepcopy(box) if i!=2 else None
    entities.append(dict(entity_id=f'{sid}/e{i}',name=f'entity{i}',motion_status=status,geometry=geometry,aggregation={},frame_evidence=[dict(obs[0],geometry=geometry)]))
    source.append(dict(entity_id=f'e{i}',name=f'entity{i}',observations=obs))
   save(self.root/'inputs'/f'{sid}.json',dict(shot_id=sid,frames=[frame],entities=source))
   save(self.root/'selected'/f'{sid}_scene.json',dict(shot_id=sid,method='fixture',coordinate_system={},cameras=[dict(frame_id=0,image_size=[20,20],position_world=[0,0,0],R_world_from_camera=R,K=R)],entities=entities))
  self.matching=dict(groups=[dict(group_id=f'g{i}',a_ids=[f'shot1/e{i}'],b_ids=[f'shot3/e{i}'],identity='matched',anchor_eligible=i==0,identity_evidence='fixture',anchor_reason='fixture') for i in range(3)],structural_anchor_group_ids=['g0'],local_origin_group_id='g0',local_reference_group_id='',scene_correspondence='same scene',limitations='',reference_selection_reason='fixture')
  save(self.root/'matching.json',self.matching);save(self.root/'narrative.json',dict(facts=[dict(fact_id='f1',text='same scene')]))
  save(self.root/'registration/roma_geometry/registration.json',dict(fits=dict(all_structures=dict(status='numeric_candidate',scale=1.,rotation=R,translation=[1.,0.,0.],yaw_deg=0.,train={},spatial_holdout={}))))
  with patch('gs_flow1_evaluator.io.disabled_skills_config',return_value=''):self.e=Eval(str(self.root))
 def test_matching_covers_all_entities_and_original_observations(self):
  def call(stage,prompt,payload,images,schema):
   self.assertEqual([len(g['entities']) for g in payload['graphs']],[3,3]);self.assertEqual(payload['graphs'][0]['entities'][1]['motion_status'],'moving');self.assertIsNone(payload['graphs'][0]['entities'][2]['geometry'])
   self.assertEqual(payload['graphs'][0]['entities'][2]['observations'][0]['box_xyxy'],[1,1,10,10]);equivalent(payload,unpack(pack(payload)));return copy.deepcopy(self.matching)
  self.e.call=call;self.e.match();self.assertEqual(len(read(self.root/'matching.json')['groups']),3);self.assertEqual([len(g['entities']) for g in self.e.graphs],[1,2])
 def test_missing_or_duplicate_dynamic_entity_rejected(self):
  for kind in ('missing','duplicate'):
   result=copy.deepcopy(self.matching)
   if kind=='missing':result['groups'].pop()
   else:result['groups'][0]['a_ids'].append('shot1/e1')
   self.e.call=lambda *args:result
   with self.subTest(kind=kind),self.assertRaises(AssertionError):self.e.match()
 def test_dynamic_unknown_and_geometryless_anchors_rejected(self):
  for i in (1,2):
   result=copy.deepcopy(self.matching);result['groups'][i]['anchor_eligible']=True
   with self.assertRaises(AssertionError):validate_anchors(result,self.e.identity_nodes)
  nodes=copy.deepcopy(self.e.identity_nodes);nodes[0]['shot1/e0']['geometry']=None
  with self.assertRaises(AssertionError):validate_anchors(self.matching,nodes)
 def test_mixed_motion_identity_not_recast_as_missing_static(self):
  before=copy.deepcopy(self.matching);result=static_matching(before,self.e.identity_nodes)
  self.assertEqual([g['group_id'] for g in result['groups']],['g0']);self.assertEqual(before,self.matching)
 def test_aligned_review_preserves_null_geometry_and_trajectory(self):
  payload,images=aligned.prepare(self.root);self.assertEqual([len(s['entities']) for s in payload['shots']],[3,3])
  moving=payload['shots'][0]['entities'][1];self.assertEqual(moving['motion_status'],'moving');self.assertEqual(moving['projected_center_in_other_shot'],[]);self.assertTrue(moving['frame_evidence'])
  self.assertIsNone(payload['shots'][0]['entities'][2]['aligned_geometry']);self.assertEqual(payload['shots'][1]['entities'][1]['aligned_geometry']['center_world'],[1.,0.,5.])
  result=dict(matching=copy.deepcopy(self.matching),initial_group_reviews=[dict(initial_group_id=f'g{i}',action='keep',result_group_ids=[f'g{i}'],geometry_interpretation='fixture',visual_identity_evidence='fixture',same_instance_motion_alternative='fixture',witnesses=[]) for i in range(3)],noncommon_checks=[],registration_caveats='',limitations='')
  aligned.validate(result,payload);result['matching']['groups'][1]['anchor_eligible']=True
  with self.assertRaises(AssertionError):aligned.validate(result,payload)
  result['matching']['groups'].pop()
  with self.assertRaises(AssertionError):aligned.validate(result,payload)
  equivalent(payload,unpack(pack(payload)))
 def test_focused_identity_keeps_inventory_anchor_and_split_gates(self):
  payload,_=aligned.prepare(self.root)
  result=dict(matching=copy.deepcopy(self.matching),initial_group_reviews=[dict(initial_group_id=f'g{i}',action='keep',result_group_ids=[f'g{i}'],visual_identity_evidence='fixture',witnesses=[]) for i in range(3)],registration_caveats='',limitations='')
  aligned.validate(result,payload,aligned.FOCUSED_PROTOCOL)
  bad=copy.deepcopy(result);bad['matching']['groups'].pop()
  with self.assertRaises(AssertionError):aligned.validate(bad,payload,aligned.FOCUSED_PROTOCOL)
  bad=copy.deepcopy(result);bad['initial_group_reviews'].pop()
  with self.assertRaises(AssertionError):aligned.validate(bad,payload,aligned.FOCUSED_PROTOCOL)
  bad=copy.deepcopy(result);bad['matching']['groups'][1]['anchor_eligible']=True
  with self.assertRaises(AssertionError):aligned.validate(bad,payload,aligned.FOCUSED_PROTOCOL)
  bad=copy.deepcopy(result);g=bad['matching']['groups'][1];a=copy.deepcopy(g);b=copy.deepcopy(g)
  a.update(group_id='g1a',b_ids=[],identity='unmatched');b.update(group_id='g1b',a_ids=[],identity='unmatched')
  bad['matching']['groups'][1:2]=[a,b];bad['initial_group_reviews'][1].update(action='split',result_group_ids=['g1a','g1b'])
  with self.assertRaisesRegex(AssertionError,'split lacks'):aligned.validate(bad,payload,aligned.FOCUSED_PROTOCOL)
 def test_presence_and_spatial_exclude_nonstatic_groups(self):
  def call(stage,prompt,payload,images,schema):
   self.assertEqual([g['group_id'] for g in payload['matching']['groups']],['g0'])
   return dict(checks=[dict(group_id='g0',partition='common_static',status='unknown',cause='none',conflict_kind='none',prompt_fact_references=[],witnesses=[],prompt_review_completed=False,prompt_explanation='',reason='fixture')])
  self.e.call=call;self.e.presence();result=read(self.root/'presence.json');self.assertEqual(result['summary']['N'],1);self.assertEqual(result['excluded_nonstatic_identity_group_ids'],['g1','g2'])
  self.e.spatial();self.assertEqual(read(self.root/'spatial.json')['all_pairs'],0)

class SceneScopeTests(unittest.TestCase):
 def test_legacy_pair_and_singleton(self):
  scope=integrated.supported_scene_scope([dict(shot_id=s) for s in ('shot1','shot2','shot3')]);self.assertEqual(scope['cross_shot_pairs'][0]['shot_ids'],['shot1','shot3']);self.assertEqual(scope['skipped_single_shot_scenes'][0]['shot_id'],'shot2')
 def test_singleton_and_different_scenes_skip_identity(self):
  for shots in ([dict(shot_id='shot1')],[dict(shot_id=s,scene_id=s) for s in ('shot1','shot3')]):
   scope=integrated.supported_scene_scope(shots);jobs=integrated.plan('/tmp/scope',0,'GPU-test',identity_scope=scope);self.assertEqual([j['stage'] for j in jobs],['detection_and_clustering'])
   with tempfile.TemporaryDirectory() as d:
    root=Path(d);integrated.save(root/'identity_scope.json',scope);integrated.save(root/'raw_manifest.json',dict(shots=[]))
    result=integrated.execute(root,jobs,{},'fixture',run=lambda *a,**k:SimpleNamespace(returncode=0));summary=integrated.read(root/'summary.json')
    self.assertEqual(result['status'],'success');self.assertEqual(summary['cross_shot_identity_status'],'skipped_single_shot_scenes');self.assertNotIn('presence',summary)
 def test_incomplete_metadata_and_unsupported_multishot_rejected(self):
  with self.assertRaises(ValueError):scene_scope([dict(shot_id='shot1',scene_id='room'),dict(shot_id='shot3')])
  shots=[dict(shot_id=s,scene_id='room') for s in ('shot1','shot2','shot3')];self.assertEqual(len(scene_scope(shots)['cross_shot_pairs']),3)
  with self.assertRaises(ValueError):integrated.supported_scene_scope(shots)

if __name__=='__main__':unittest.main()
