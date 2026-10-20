import unittest
import numpy as np
from scene_frame import frame_from_points,to_scene,from_scene
class SceneFrameTests(unittest.TestCase):
    def test_origin_axes_and_unit(self):
        o=np.array([3.,-2.,.7]);r=np.array([1.,1.,1.1]);f=frame_from_points(o,r)
        np.testing.assert_allclose(to_scene(o,f),[0,0,0],atol=1e-12)
        np.testing.assert_allclose(to_scene(r,f)[:2],[0,1],atol=1e-12)
        basis=np.array(f['axes_in_input_columns_xyz']);np.testing.assert_allclose(basis.T@basis,np.eye(3),atol=1e-12)
        self.assertAlmostEqual(np.linalg.det(basis),1.)
    def test_invariant_to_independent_camera_frame_similarity(self):
        rng=np.random.default_rng(7);pts=rng.normal(size=(32,3));o=pts[0];r=pts[1];f=frame_from_points(o,r)
        a=1.4;theta=1.23;c,s=np.cos(theta),np.sin(theta);R=np.array([[c,-s,0],[s,c,0],[0,0,1.]])
        T=lambda p:a*np.asarray(p)@R.T+np.array([2.,-5.,.3])
        g=frame_from_points(T(o),T(r))
        np.testing.assert_allclose(to_scene(T(pts),g),to_scene(pts,f),atol=1e-12)
        np.testing.assert_allclose(from_scene(to_scene(pts,f),f),pts,atol=1e-12)
    def test_reject_vertical_reference_pair(self):
        with self.assertRaises(ValueError):frame_from_points([0,0,0],[0,0,1])
if __name__=='__main__':unittest.main()
