import unittest,sys,itertools
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from gs_registration_variants import select_pairs,corner_pairs,fit_corners,hybrid_objective
from gs_registration_3d import rotation

class VariantTests(unittest.TestCase):
 def data(self):
  d=np.zeros((200,19));rng=np.random.default_rng(7);d[:,7:13]=rng.normal(size=(200,6));d[:,13]=np.linspace(.2,1,200);return d
 def test_topk_and_threshold(self):
  d=self.data();ix=select_pairs(d,32,'top_confidence',.8);self.assertEqual(len(set(ix)),32);self.assertTrue((d[ix,13]>=.8).all());self.assertEqual(ix[0],199)
 def test_fps_unique_and_deterministic(self):
  d=self.data();a=select_pairs(d,64);np.testing.assert_array_equal(a,select_pairs(d,64));self.assertEqual(len(set(a)),64)
 def test_fps_invariant_to_shot_units(self):
  d=self.data();a=select_pairs(d,32);d[:,7:10]*=10;d[:,10:13]*=.3;np.testing.assert_array_equal(a,select_pairs(d,32))
 def test_no_silent_threshold_relaxation(self):
  with self.assertRaises(ValueError):select_pairs(self.data(),128,min_confidence=.9)
 def boxes(self):
  raw=np.array(list(itertools.product([-1.,1.],repeat=3)));items=[]
  for i,center in enumerate([[0,0,0],[3,0,1],[0,4,2]]):
   q=raw*np.array([.5,.3,.2])+center;p=1.2*q@rotation(.8).T+[.2,-.5,.1]
   items.append(dict(group_id=str(i),source=q[::-1].tolist(),target=p.tolist()))
  return items
 def test_corner_bijection_handles_index_permutation(self):
  boxes=self.boxes();x=np.array([np.log(1.2),.8,.2,-.5,.1]);p,q,assign=corner_pairs(x,boxes)
  self.assertEqual(len(p),24);self.assertTrue(all(len(set(a['source_indices']))==8 for a in assign))
  self.assertLess(hybrid_objective(x,boxes,np.empty((0,3)),np.empty((0,3)))[0],1e-10)
 def test_corner_only_recovers_known_transform(self):
  fit=fit_corners(self.boxes(),yaw_starts=12);self.assertLess(fit['objective_value'],1e-5)
 def test_hybrid_is_exact_unsquared_sum(self):
  boxes=self.boxes();x=np.array([np.log(1.2),.8,.2,-.5,.1]);q=np.zeros((1,3));p=np.array([[3.2,3.5,.1]])
  self.assertAlmostEqual(hybrid_objective(x,boxes,p,q)[0],5.,places=10)
if __name__=='__main__':unittest.main()
