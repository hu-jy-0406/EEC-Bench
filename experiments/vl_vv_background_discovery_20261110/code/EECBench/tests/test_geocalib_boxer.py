"""Coordinate and evaluation regressions for the model adapter."""
import sys, unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from run_geocalib_boxer import world_from_camera
from evaluate_geocalib_boxer import box_metrics,vertical_residual

class AdapterTests(unittest.TestCase):
    def test_level_camera_gravity_sign(self):
        R=world_from_camera([0,-1,0])
        np.testing.assert_allclose(R@[0,-1,0],[0,0,1],atol=1e-9)
        np.testing.assert_allclose(R@[0,1,0],[0,0,-1],atol=1e-9)
    def test_tilted_camera_is_proper(self):
        up=np.array([.1,-.95,-.2]);up/=np.linalg.norm(up);R=world_from_camera(up)
        np.testing.assert_allclose(R@up,[0,0,1],atol=1e-9)
        self.assertAlmostEqual(np.linalg.det(R),1.)
    def test_vertical_looking_camera(self):
        R=world_from_camera([0,0,1]);np.testing.assert_allclose(R@R.T,np.eye(3),atol=1e-9)
    def test_reject_zero_gravity(self):
        with self.assertRaises(ValueError):world_from_camera([0,0,0])
    def test_known_world_camera_roundtrip(self):
        R=world_from_camera([.03,-.98,-.2]);p=np.array([[1,2,3],[-1,2,5.]])
        np.testing.assert_allclose((p@R.T)@R,p,atol=1e-9)
    def test_perfect_clipped_projection(self):
        m=box_metrics([-100,-100,1000,1000],[0,0,852,480]);self.assertEqual(m['iou'],1.)
    def test_coverage_not_iou(self):
        m=box_metrics([0,0,20,20],[5,5,15,15]);self.assertEqual(m['coverage'],1.);self.assertEqual(m['iou'],.25)
    def test_no_intersection(self):
        self.assertEqual(box_metrics([0,0,10,10],[20,20,30,30])['iou'],0.)
    def test_vertical_direction_at_infinity(self):
        K=np.array([[1000,0,426],[0,1000,240],[0,0,1]])
        self.assertAlmostEqual(vertical_residual(K,np.array([0,-1,0]),[[300,50],[300,400]]),0.)
    def test_joint_image_and_intrinsics_scaling(self):
        K=np.array([[969.,0,426],[0,969,240],[0,0,1]]);p=np.array([.3,.1,2.]);A=np.diag([960/852,960/480,1]);a=K@p;b=A@K@p
        np.testing.assert_allclose((b/b[2])[:2],(A@(a/a[2]))[:2])
if __name__=='__main__':unittest.main()
