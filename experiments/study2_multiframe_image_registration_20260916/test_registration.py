import unittest
import numpy as np
import register as reg
class RegistrationTest(unittest.TestCase):
 def setUp(self):
  self.old=reg.graph;self.cams={};base=np.array([[1,0,0],[0,0,1],[0,-1,0.]])
  for side in ['shot1','shot3']:
   self.cams[side]=[]
   for i in range(6):
    R=reg.rz((i-2.5)*.045)@base;t=np.array([.12*i,-6 if side=='shot1' else -7,1.5+.06*i]);K=np.array([[550.,0,426],[0,550.,240],[0,0,1.]])
    self.cams[side].append({'frame_id':i,'R_world_from_camera':R.tolist(),'position_world':t.tolist(),'K':K.tolist()})
  reg.graph=lambda s:{'cameras':self.cams[s]}
 def tearDown(self):reg.graph=self.old
 def data(self,outliers=False):
  rng=np.random.default_rng(5);d=np.zeros((180,19));x=np.r_[np.log(1.3),.71,[.4,.2,-.1]];s,R,t=reg.params(x)
  for i in range(len(d)):
   a=i%6;b=(i//6)%6;Q=rng.uniform([-2,0,.2],[2,4,2]);P=s*R@Q+t
   if outliers and i%5==0:P+=rng.uniform([.6,-1,-.2],[2,1,.4])
   u=[]
   for side,fid,p in [('shot1',a,P),('shot3',b,Q)]:
    c=self.cams[side][fid];C=np.eye(4);C[:3,:3]=c['R_world_from_camera'];C[:3,3]=c['position_world'];q=np.linalg.inv(C)@np.r_[p,1];v=np.array(c['K'])@q[:3];u.extend(v[:2]/v[2])
   d[i]=[a,b,[1,4,10,12][i%4],*u,*P,*Q,1,0,i//6,i%6,i//8,i%8]
  return d,x
 def test_symmetric_reprojection_with_moving_cameras(self):
  d,x=self.data();np.testing.assert_allclose(reg.Geometry(d).residual(x),0,atol=1e-10)
  wrong=d.copy();wrong[:,:2]=0;self.assertGreater(np.median(reg.Geometry(wrong).error(x)),5)
 def test_robust_transform_and_direction_change_retained(self):
  d,x=self.data(True);f=reg.fit(d,iterations=180);self.assertIsNotNone(f);np.testing.assert_allclose(f,x,atol=2e-5)
  s,R,t=reg.params(f);a=np.array([0.,0,0]);b=np.array([1.,0,0]);a3=(b-t)@R/s;b3=(a-t)@R/s
  v=b-a;w=s*R@(b3-a3);self.assertAlmostEqual(float(v@w/np.linalg.norm(v)/np.linalg.norm(w)),-1,10)
if __name__=='__main__':unittest.main()
