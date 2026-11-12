"""Evidence transport and scheduler invariants, without model or GPU work."""
import copy,json,sys,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
B=Path(__file__).resolve().parents[1];sys.path.insert(0,str(B/'scripts'))
import gs_efficient_transport as transport
import run_gs_integrated as run
import gs_witness_codec as witness
from prepare_gs_integrated import inputs
from gs_runtime_profile import profile
from review_aligned_entity_identities import SCHEMA

class EfficientTests(unittest.TestCase):
 def test_aliases_roundtrip_complete_real_response(self):
  source=B/'experiments/study2_integrated_full_fresh_20260919/study2/calls/identity_review/response.json'
  value=json.loads(source.read_text())
  def encode(v,s):
   if s.get('type')=='object':return {transport.ALIASES.get(k,k):encode(v[k],p) for k,p in s['properties'].items()}
   if s.get('type')=='array':return [encode(x,s['items']) for x in v]
   return v
  transport.schema_validate(encode(value,SCHEMA),transport.wire_schema(SCHEMA))
  self.assertEqual(transport.decode(encode(value,SCHEMA),SCHEMA),value)
 def test_witness_bank_restores_real_identity_evidence_exactly(self):
  root=B/'experiments/study2_integrated_full_fresh_20260919/study2'
  value=json.loads((root/'calls/identity_review/response.json').read_text());images=json.loads((root/'identity_review_images.json').read_text());bank=[];ids={}
  def encode(v,s):
   if witness.is_witness(s):
    key=json.dumps(v,sort_keys=True)
    if key not in ids:
     ids[key]=len(bank);i=next(i+1 for i,f in enumerate(images) if f['shot_id']==v['shot_id'] and f['frame_id']==v['frame_id']);bank.append(dict(i=i,b=v['region_xyxy'],o=v['observation']))
    return ids[key]
   if s.get('type')=='object':return {k:encode(v[k],p) for k,p in s['properties'].items()}
   if s.get('type')=='array':return [encode(x,s['items']) for x in v]
   return v
  encoded=encode(value,SCHEMA);encoded['witness_bank']=bank;schema,active=witness.schema_with_bank(SCHEMA,images)
  self.assertTrue(active);transport.schema_validate(encoded,schema);self.assertEqual(witness.expand(encoded,SCHEMA,images),value)
  with_unused=copy.deepcopy(encoded);with_unused['witness_bank'].append(copy.deepcopy(bank[0]));self.assertEqual(witness.expand(with_unused,SCHEMA,images),value)
  encoded['initial_group_reviews'][0]['witnesses'][0]=len(bank)
  with self.assertRaises(AssertionError):witness.expand(encoded,SCHEMA,images)
 def test_alias_collision_rejected(self):
  with self.assertRaises(AssertionError):transport.wire_schema({'type':'object','properties':{'entity_id':{'type':'string'},'id':{'type':'string'}}})
 def test_profile_preserves_frontend_and_routes_cross_shot(self):
  p=profile('efficient_astra_low');self.assertEqual(p['clustering_reasoning'],'medium');self.assertEqual(p['reasoning'],'low')
  jobs=run.plan('/tmp/example',0,'GPU-id',profile_name=p['name'])
  self.assertIn('medium',jobs[0]['command'])
  for j in jobs:
   if j['stage'] in ['motion_and_fusion','initial_identity','aligned_identity_review','presence','spatial']:self.assertIn(p['name'],j['command'])
 def test_overlap_waits_for_both_dependencies_and_never_overlaps_gpus(self):
  roma_started=threading.Event();identity_finished=threading.Event();roma_finished=threading.Event();gpu_lock=threading.Lock()
  names=['boxer_shot3','motion_and_fusion','initial_identity','roma_matches','lift_correspondences','registration'];jobs=[dict(stage=n,command=[n]) for n in names]
  def fake(cmd,**kwargs):
   n=cmd[0]
   if n in ['boxer_shot3','roma_matches']:self.assertTrue(gpu_lock.acquire(blocking=False))
   if n=='motion_and_fusion':self.assertTrue(roma_started.wait(2))
   if n=='initial_identity':identity_finished.set()
   if n=='roma_matches':roma_started.set();self.assertTrue(identity_finished.wait(2));roma_finished.set()
   if n=='lift_correspondences':self.assertTrue(roma_finished.is_set() and identity_finished.is_set())
   if n in ['boxer_shot3','roma_matches']:gpu_lock.release()
   return SimpleNamespace(returncode=0)
  with tempfile.TemporaryDirectory() as d:
   runtime={'stages':[]};run.execute_parallel_stages(Path(d),jobs,{},fake,runtime);self.assertEqual({r['stage'] for r in runtime['stages']},set(names));self.assertTrue(all(r['status']=='success' for r in runtime['stages']))
 def test_overlap_failure_does_not_launch_downstream(self):
  names=['boxer_shot3','motion_and_fusion','initial_identity','roma_matches','lift_correspondences'];called=[]
  def fake(cmd,**kwargs):called.append(cmd[0]);return SimpleNamespace(returncode=3 if cmd[0]=='motion_and_fusion' else 0)
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(RuntimeError):run.execute_parallel_stages(Path(d),[dict(stage=n,command=[n]) for n in names],{},fake,{'stages':[]})
  self.assertNotIn('initial_identity',called);self.assertNotIn('lift_correspondences',called)
 def test_auxiliary_shot2_never_requests_geometry(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);run.save(root/'entities/manifest.json',{'shots':[{'shot_id':'shot2','frames':[{'path':'intentionally missing'}]}]})
   inputs(root);self.assertFalse((root/'inputs/shot2.json').exists())
if __name__=='__main__':unittest.main()
