import unittest
import sys
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from scipy.spatial.transform import Rotation
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import gravity_box_registration as reg

class GravityRegistrationTests(unittest.TestCase):
    def setUp(self):
        rng=np.random.default_rng(41)
        self.a=np.array([reg.corners(dict(center_world=c,size_xyz=rng.uniform(.2,1.,3),
                     R_world_from_object=Rotation.random(random_state=rng).as_matrix()))
                     for c in rng.normal(size=(10,3))*np.array([3.,3.,1.])])
        self.model=(1.17,Rotation.from_euler('z',137,degrees=True).as_matrix(),np.array([.8,-1.2,.4]))
        self.b=reg.transform(self.a,self.model)
    def test_known_yaw_scale_translation_and_corner_relabeling(self):
        b=self.b.copy()
        for i in range(len(b)):b[i]=b[i,reg.PERMUTATIONS[(i*7)%24]]
        fit=reg.fit_boxes(self.a,b)
        self.assertLess(max(reg.box_residuals(self.a,b,fit['model'])[0]),1e-7)
        np.testing.assert_allclose(fit['model'][1][:,2],[0,0,1],atol=1e-14)
        self.assertAlmostEqual(fit['model'][0],1.17,places=7)
        inverse=reg.fit_boxes(self.b,self.a)['model']
        np.testing.assert_allclose(reg.transform(self.b,inverse),self.a,atol=1e-7)
        heldout=reg.fit_boxes(self.a[1:],self.b[1:])['model']
        self.assertLess(reg.box_residuals(self.a[:1],self.b[:1],heldout)[0][0],1e-7)
    def test_weighted_update_against_independent_five_parameter_optimizer(self):
        rng=np.random.default_rng(4);x=rng.normal(size=(30,3));y=reg.transform(x,self.model)+rng.normal(size=x.shape)*.13
        w=rng.uniform(.1,1.,len(x));fit=reg.weighted_similarity(x,y,w)
        def objective(v):
            candidate=(np.exp(v[0]),Rotation.from_euler('z',v[1]).as_matrix(),v[2:])
            return np.sum(w[:,None]*(reg.transform(x,candidate)-y)**2)/w.sum()
        independent=minimize(objective,[.1,2.2,.7,-1.,.3],method='BFGS',options={'gtol':1e-9})
        actual=np.sum(w[:,None]*(reg.transform(x,fit)-y)**2)/w.sum()
        self.assertAlmostEqual(actual,float(independent.fun),places=10)
    def test_upside_down_solution_is_excluded(self):
        flipped=reg.transform(self.a,(1.,Rotation.from_euler('x',180,degrees=True).as_matrix(),np.array([1.,0.,.3])))
        m=reg.fit_boxes(self.a,flipped)['model']
        np.testing.assert_allclose(m[1]@[0,0,1],[0,0,1],atol=1e-14)
        self.assertGreater(np.mean(reg.box_residuals(self.a,flipped,m)[0]),.5)
        self.assertGreater(np.linalg.det(m[1]),.999999)
    def test_robust_outlier_remains_without_dragging_scene(self):
        b=self.b.copy();b[0]+=[6.,0,0]
        robust=reg.fit_boxes(self.a,b,delta=.015)['model'];plain=reg.fit_boxes(self.a,b,delta=None)['model']
        good_r=np.mean(reg.box_residuals(self.a,self.b,robust)[0][1:])
        good_l=np.mean(reg.box_residuals(self.a,self.b,plain)[0][1:])
        self.assertLess(good_r,good_l*.4)
        self.assertGreater(reg.box_residuals(self.a,b,robust)[0][0],5.)
    def test_undetermined_yaw_and_invalid_weights_are_rejected(self):
        vertical=np.array([[0,0,0],[0,0,1],[0,0,2.]])
        with self.assertRaises(ValueError):reg.weighted_similarity(vertical,vertical)
        with self.assertRaises(ValueError):reg.weighted_similarity(self.a.mean(1),self.b.mean(1),np.full(10,np.nan))

if __name__=='__main__':unittest.main()
