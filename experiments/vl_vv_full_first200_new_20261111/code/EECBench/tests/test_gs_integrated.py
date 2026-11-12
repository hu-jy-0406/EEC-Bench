import json
from pathlib import Path
import sys,tempfile,unittest
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_gs_integrated as flow
from prepare_gs_integrated import inputs

class IntegrationTests(unittest.TestCase):
 def test_order_and_current_entrypoints(self):
  jobs=flow.plan('/tmp/fresh-case',3,'GPU-test');names=[j['stage'] for j in jobs]
  self.assertLess(names.index('motion_and_fusion'),names.index('initial_identity'))
  self.assertLess(names.index('initial_identity'),names.index('registration'))
  self.assertLess(names.index('registration'),names.index('aligned_identity_review'))
  self.assertEqual(names[-2:],['presence','spatial'])
  self.assertEqual(flow.plan('/tmp/fresh-case',3,'GPU-test','presence')[-1]['stage'],'presence')
  for job in jobs:
   self.assertNotIn('evaluate.py',' '.join(job['command']))
   self.assertNotIn('--detections',job['command'])
  self.assertIn('run_wedetect_shot_entities.py',' '.join(jobs[0]['command']))
  self.assertIn('run_gs_flow1_stage.py',' '.join(jobs[-1]['command']))
  self.assertIn('register_gs_3d.py',' '.join(next(j for j in jobs if j['stage']=='registration')['command']))
 def test_direct_alignment_skips_roma_and_lifting_but_keeps_scoring(self):
  jobs=flow.plan('/tmp/direct-case',0,'GPU-test',alignment_method='codex_direct');names=[j['stage'] for j in jobs]
  self.assertNotIn('roma_matches',names);self.assertNotIn('lift_correspondences',names)
  self.assertEqual(names[-2:],['presence','spatial'])
  command=next(j['command'] for j in jobs if j['stage']=='registration')
  self.assertIn('register_gs_codex.py',' '.join(command))
  self.assertLess(names.index('initial_identity'),names.index('registration'))
  self.assertLess(names.index('registration'),names.index('aligned_identity_review'))
 def test_identity_only_stops_before_scoring(self):
  jobs=flow.plan('/tmp/identity-case',0,'GPU-test','identity')
  self.assertEqual(jobs[-1]['stage'],'aligned_identity_review')
  self.assertNotIn('presence',[j['stage'] for j in jobs]);self.assertNotIn('spatial',[j['stage'] for j in jobs])
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);flow.save(root/'raw_manifest.json',dict(shots=[]))
   def run(cmd,**kw):
    flow.save(root/'identity_review.json',dict(matching={'groups':[]}))
    for sid in ['shot1','shot3']:flow.save(root/'selected'/f'{sid}_scene.json',dict(counts={'static':1}))
    return SimpleNamespace(returncode=0)
   result=flow.execute(root,[dict(stage='aligned_identity_review',command=['fake'])],{},'test',run)
   summary=flow.read(root/'summary.json');self.assertEqual(result['status'],'success');self.assertNotIn('presence',summary);self.assertFalse(summary['presence_evaluation_run'])
 def test_gpu_stages_guarded(self):
  for job in flow.plan('/tmp/case',3,'GPU-test'):
   if job['stage'] in ['detection_and_clustering','geocalib','pi3x_shot1','pi3x_shot3','boxer_shot1','boxer_shot3','roma_matches']:
    self.assertEqual(Path(job['command'][1]).name,'guard_gpu.py');self.assertEqual(job['command'][2:4],['3','GPU-test'])
 def test_failure_stops_before_downstream(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);calls=[]
   def run(cmd,**kw):calls.append(cmd);return SimpleNamespace(returncode=2)
   with self.assertRaises(RuntimeError):flow.execute(root,[dict(stage='first',command=['fail']),dict(stage='second',command=['never'])],{},'test',run)
   self.assertEqual(calls,[['fail']]);self.assertEqual(flow.read(root/'summary.json')['status'],'failed')
 def test_usage_counts_clustering_and_cache_once(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);usage=[dict(input_tokens=100,cached_input_tokens=60,output_tokens=10)]
   for name in ['entities/shots/shot1','calls/motion_shot1','calls/presence_1']:
    flow.save(root/name/'status.json',dict(status='success',usage=usage,seconds=2))
   runtime=dict(status='failed',seconds=5,stages=[dict(stage='detection_and_clustering'),dict(stage='motion_and_fusion'),dict(stage='presence')])
   r=flow.summarize(root,runtime);self.assertEqual(len(r['calls']),3);self.assertEqual(r['total_tokens'],330)
   self.assertEqual([s['total_tokens'] for s in r['stages']],[110,110,110])
 def test_bridge_preserves_missing_boxes_and_candidate_provenance(self):
  from PIL import Image
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);im=root/'frame.jpg';Image.new('RGB',(20,10)).save(im)
   frame=dict(frame_id=0,path=str(im),sha256=flow.sha(im),timestamp_sec=0)
   entities=[dict(entity_id='e1',name='table',observations=[dict(frame_id=0,box_xyxy=None,visible=False,exist=None,candidate_ids=[])])]
   flow.save(root/'entities/manifest.json',dict(shots=[dict(shot_id='shot1',frames=[frame])]))
   flow.save(root/'entities/shots/shot1/entities.json',dict(entities=entities));flow.save(root/'calibration_new/calibration/shot1.json',{})
   inputs(root);out=flow.read(root/'inputs/shot1.json');self.assertEqual(out['entities'],entities);self.assertEqual(out['frames'],[frame]);self.assertEqual(out['image_sizes'],[[20,10]])
   im.write_bytes(b'changed')
   with self.assertRaises(ValueError):inputs(root)
 def test_existing_case_refused_before_loading(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(FileExistsError):flow.prepare(Path(d),None,None,None,None)
 def test_successful_orchestration_finishes_at_single_presence(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);flow.save(root/'raw_manifest.json',dict(shots=[]))
   def run(cmd,**kw):
    flow.save(root/'presence.json',dict(aggregation_version='single_presence_witness_v1',summary={'K':0}))
    for sid in ['shot1','shot3']:flow.save(root/'selected'/f'{sid}_scene.json',dict(counts={'static':1}))
    return SimpleNamespace(returncode=0)
   result=flow.execute(root,[dict(stage='presence',command=['fake'])],{},'test',run)
   self.assertEqual(result['status'],'success');self.assertFalse(flow.read(root/'summary.json')['spatial_evaluation_run'])
if __name__=='__main__':unittest.main()
