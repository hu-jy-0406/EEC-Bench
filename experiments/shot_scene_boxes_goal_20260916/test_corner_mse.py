import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import global_corner_mse as gm
from robust_box_registration import SIGNS,PERMUTATIONS,transform

def sample():
 rng=np.random.default_rng(42)
 return np.array([SIGNS*rng.uniform(.1,1,3)+rng.normal(size=3)*2 for _ in range(5)])
def rz(a):
 c,s=np.cos(a),np.sin(a);return np.array([[c,-s,0],[s,c,0],[0,0,1.]])
class Tests(unittest.TestCase):
 def test_exact_similarity_arbitrary_corner_labels(self):
  x=sample();y=transform(x,(1.7,rz(.73),np.array([2.,-1.,.4])))
  y=np.array([a[PERMUTATIONS[i*3]] for i,a in enumerate(y)])
  r=gm.fit(x,y);self.assertLess(r['mse_xyz'],1e-20);self.assertAlmostEqual(r['scale'],1.7,10)
 def test_full_angle_grid_is_not_better(self):
  x=sample();y=transform(x,(.8,rz(-1.2),np.array([1.,2.,3.])))
  y[1]+=np.array([.3,-.4,.2]);r=gm.fit(x,y)
  coeff,_,_,A,B=gm.correlation_coefficients(x,y)
  grid=np.linspace(0,2*np.pi,100001)
  best=max(float(gm.correlation_at(coeff,g).max()) for g in np.array_split(grid,50))
  grid_mse=(B-best**2/A)/x.size
  self.assertLessEqual(r['mse_xyz'],grid_mse+1e-12)
 def test_units_and_reverse(self):
  x=sample();y=x.copy();y[2]+=np.array([.2,.3,.4])
  a=gm.fit(x,y);b=gm.fit(x*.001,y*1000);c=gm.fit(y,x)
  self.assertAlmostEqual(a['normalized_mse'],b['normalized_mse'],10)
  self.assertAlmostEqual(a['normalized_mse'],c['normalized_mse'],10)
 def test_invalid(self):
  with self.assertRaises(ValueError):gm.fit(np.zeros((2,8,3)),np.zeros((2,8,3)))
if __name__=='__main__':unittest.main()
