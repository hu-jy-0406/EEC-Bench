import sys,unittest,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from run_gs_temporal_stage import Stage,B
from gs_runtime_profile import profile

class TemporalTransportTests(unittest.TestCase):
 def test_experimental_route_preserves_canonical_payload_images_schema_and_base_prompt(self):
  stage=Stage.__new__(Stage);stage.runtime=profile('temporal_compact_medium');stage.args=SimpleNamespace(reasoning="medium")
  images=[dict(shot_id='shot1',frame_id=120,image_size=[100,80],path='/original.jpg',sha256='abc')]
  schema={'type':'object'};payload={'target_frames':[{'shot_id':'shot1','frame_id':120}],'geometry':None}
  with patch('gs_flow1_compact_transport.call',return_value={'ok':1}) as compact,patch('run_partial_scene_comparison.call') as canonical:
   out=stage.call('boundary_review_000','temporal_review_v2.txt',payload,images,schema)
  canonical.assert_not_called();args=compact.call_args.args
  self.assertEqual(args[1],str(B/'prompts/gs_flow1/temporal_review_v2.txt'));self.assertIs(args[3],images);self.assertIs(args[4],schema)
  self.assertEqual(args[2]['target_frames'],payload['target_frames']);self.assertIsNone(args[2]['geometry']);self.assertNotIn('images',payload)
  self.assertEqual(args[2]['images'],[dict(attachment_index=1,shot_id='shot1',frame_id=120,image_size=[100,80])]);self.assertEqual(out,{'ok':1})
 def test_current_default_stays_canonical_for_temporal(self):
  stage=Stage.__new__(Stage);stage.runtime=profile('safe_spatial_medium');stage.args=SimpleNamespace(reasoning="medium")
  with patch('gs_flow1_compact_transport.call') as compact,patch('run_partial_scene_comparison.call',return_value={}) as canonical:stage.call('within_shot1_000','temporal_review_v2.txt',{},[],{})
  compact.assert_not_called();canonical.assert_called_once()
 def test_lower_effort_never_changes_model_or_clustering(self):
  p=profile('temporal_compact_low');self.assertEqual(p['model'],'gpt-6-astra');self.assertEqual(p['reasoning'],'low');self.assertEqual(p['clustering_model'],'gpt-6-astra');self.assertEqual(p['clustering_reasoning'],'medium')
 def test_stage_overrides_do_not_leak_effort_to_presence_or_motion(self):
  stage=Stage.__new__(Stage);stage.runtime=profile('temporal_cost_v1');stage.args=SimpleNamespace(reasoning='medium',model='gpt-6-astra')
  with patch('gs_efficient_transport.call',return_value={}) as efficient,patch('run_partial_scene_comparison.call',return_value={}) as canonical:
   stage.call('boundary_local_shot1','gs_relation_shot_v1.txt',{},[],{})
   stage.call('boundary_review_000','temporal_review_v2.txt',{},[],{})
   stage.call('expected_motion_shot1','expected_motion_v2.txt',{},[],{})
  self.assertEqual(efficient.call_args.args[-1].reasoning,'low')
  self.assertTrue(all(c.args[-1].reasoning=='medium' for c in canonical.call_args_list))
  self.assertEqual(stage.args.reasoning,'medium');self.assertEqual(stage.args.model,'gpt-6-astra')
 def test_binary_profile_only_changes_motion_protocol_and_its_transport(self):
  stage=Stage.__new__(Stage);stage.runtime=profile('temporal_binary_v1');stage.args=SimpleNamespace(reasoning='medium',model='gpt-6-astra')
  self.assertEqual(stage.runtime['expected_motion_protocol'],'shot_binary_v1')
  with patch('gs_flow1_compact_transport.call',return_value={}) as compact,patch('run_partial_scene_comparison.call',return_value={}) as canonical:
   stage.call('expected_motion_shot1','shot_motion_binary_v1.txt',{},[],{})
   stage.call('within_shot1_000','temporal_review_v2.txt',{},[],{})
  compact.assert_called_once();canonical.assert_called_once()
  self.assertEqual(compact.call_args.args[-1].model,'gpt-6-astra');self.assertEqual(compact.call_args.args[-1].reasoning,'medium')
  self.assertEqual(canonical.call_args.args[1],'temporal_review_v2.txt');self.assertEqual(canonical.call_args.args[-1].reasoning,'medium')

if __name__=='__main__':unittest.main()
