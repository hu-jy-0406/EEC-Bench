import unittest
import sys
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import robust_box_registration as reg

class RegistrationTests(unittest.TestCase):
    def setUp(self):
        rng=np.random.default_rng(17)
        self.a=np.array([reg.corners(dict(center_world=c,size_xyz=rng.uniform(.2,1.,3),
                         R_world_from_object=Rotation.random(random_state=rng).as_matrix()))
                         for c in rng.normal(size=(10,3))*3])
        self.model=(1.12,Rotation.from_euler('xyz',[8,-17,24],degrees=True).as_matrix(),np.array([1.,-2.,.4]))
        self.b=reg.transform(self.a,self.model)
    def test_known_similarity_and_corner_symmetry(self):
        b=self.b.copy()
        for i in range(len(b)):b[i]=b[i,reg.PERMUTATIONS[(i*7)%24]]
        fit=reg.fit_boxes(self.a,b)
        self.assertLess(max(reg.box_residuals(self.a,b,fit['model'])[0]),1e-7)
        self.assertAlmostEqual(fit['model'][0],self.model[0],places=7)
        self.assertEqual(len(np.unique(reg.PERMUTATIONS,axis=0)),24)
    def test_outlier_retained_and_not_absorbed(self):
        b=self.b.copy();b[0]+=np.array([6.,0.,0.])
        robust=reg.fit_boxes(self.a,b,delta=.015)
        plain=reg.fit_boxes(self.a,b,delta=None)
        good_r=np.mean(reg.box_residuals(self.a,self.b,robust['model'])[0][1:])
        good_l=np.mean(reg.box_residuals(self.a,self.b,plain['model'])[0][1:])
        self.assertLess(good_r,good_l*.4)
        self.assertGreater(reg.box_residuals(self.a,b,robust['model'])[0][0],5.)
        self.assertEqual(len(robust['weights']),10)
    def test_reject_degenerate_centers(self):
        x=np.array([[0,0,0],[1,0,0],[2,0,0]],float)
        with self.assertRaises(ValueError):reg.weighted_similarity(x,x)
    def test_no_reflection_fit(self):
        b=self.b.copy();b[:,:,0]*=-1
        fitted=reg.weighted_similarity(self.a.mean(1),b.mean(1))
        self.assertGreater(np.linalg.det(fitted[1]),.999999)
        self.assertGreater(np.linalg.norm(reg.transform(self.a.mean(1),fitted)-b.mean(1)),.1)
    def test_inverse_and_loo(self):
        fit=reg.fit_boxes(self.a[1:],self.b[1:])
        self.assertLess(reg.box_residuals(self.a[:1],self.b[:1],fit['model'])[0][0],1e-7)
        inverse=reg.fit_boxes(self.b,self.a)['model']
        self.assertLess(np.max(np.abs(reg.transform(self.b,inverse)-self.a)),1e-7)

if __name__=='__main__':unittest.main()
