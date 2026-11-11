import copy,json,unittest,sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from gs_flow1_compact_payload import pack,unpack,equivalent,obb_corners
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
if __name__=='__main__':unittest.main()
