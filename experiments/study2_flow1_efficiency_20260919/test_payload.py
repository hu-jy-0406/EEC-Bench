import copy,json,unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from compact_payload import pack,unpack,equivalent,obb_corners
H=Path(__file__).resolve().parent;E=H.parent
class Codec(unittest.TestCase):
 def test_mixed_values(self):
  x={'numbers':[None,True,False,0,1,1.0,-0.0,1e-20],'rows':[{'a':i,'中文':'原帧'} for i in range(8)]};self.assertEqual(x,unpack(pack(x)))
 def test_empty_uneven_rows(self):
  x=[{},[],[{'a':1},{'b':2}],{'v':[],'w':None}];self.assertEqual(x,unpack(pack(x)))
 def test_duplicate_subtrees(self):
  x={'a':[{'id':i,'description':'x'*500} for i in range(4)]};x['b']=copy.deepcopy(x['a']);w=pack(x);self.assertTrue(w['shared']);self.assertEqual(x,unpack(w))
 def test_corner_derivation(self):
  g={'center_world':[1.0,2.0,3.0],'size_xyz':[2.0,4.0,6.0],'R_world_from_object':[[0.,-1.,0.],[1.,0.,0.],[0.,0.,1.]]};g['corners_world']=obb_corners(g);w=pack(g);self.assertEqual(w['derived_geometry']['derived_boxes'],1);equivalent(g,unpack(w))
 def test_nonredundant_corners_retained(self):
  g={'center_world':[0.,0.,0.],'size_xyz':[1.,1.,1.],'R_world_from_object':[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]};g['corners_world']=obb_corners(g);g['corners_world'][0][0]+=0.01;w=pack(g);self.assertEqual(w['derived_geometry']['derived_boxes'],0);self.assertEqual(g,unpack(w))
 def test_precise_centers_not_changed(self):
  x={'center_world':[0.0000000000023456789,1.123456789012345,-1e-16]};self.assertEqual(x,unpack(pack(x)))
 def test_reject_invalid_reference(self):
  with self.assertRaises(KeyError):unpack({'encoding':'lossless_tables_refs_v1','shared':{},'data':{'$ref':'missing'}})
 def test_reject_cycle(self):
  with self.assertRaises(AssertionError):unpack({'encoding':'lossless_tables_refs_v1','shared':{'x':{'$ref':'x'}},'data':{'$ref':'x'}})
 def test_historical_roundtrips_and_parallel(self):
  paths=[E/'study2_full_fresh_20260918/study2/calls/matching/input.json',E/'study2_identity_frozen_replay_20260919/calls/original/input.json',E/'study2_flow2_separate_ab_20260919/flow1/calls/presence_1/input.json'];values=[json.loads(p.read_text()) for p in paths]
  with ThreadPoolExecutor(max_workers=3) as p:packed=list(p.map(pack,values))
  for a,b in zip(values,packed):equivalent(a,unpack(b));self.assertLessEqual(b['derived_geometry']['max_corner_reconstruction_error'],1e-9)
if __name__=='__main__':unittest.main()
