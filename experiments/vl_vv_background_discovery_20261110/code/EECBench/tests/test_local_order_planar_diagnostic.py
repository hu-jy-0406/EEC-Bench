import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from check_local_order_planar_diagnostic import homography,project_bounds

class PlanarDiagnosticTests(unittest.TestCase):
    def test_negative_homogeneous_scale_is_same_mapping(self):
        h=np.eye(3);box=[10,20,30,40]
        for a,b in zip(project_bounds(h,box),project_bounds(-h,box)):np.testing.assert_allclose(a,b)
    def test_horizon_crossing_rejected(self):
        h=np.array([[1,0,0],[0,1,0],[1,0,-20]],float)
        with self.assertRaises(ValueError):project_bounds(h,[10,20,30,40])
    def test_camera_reflection_preserves_physical_coordinates(self):
        h=homography([(100,0),(0,0),(0,100),(100,100)])
        lo,hi=project_bounds(h,[65,20,75,30])
        np.testing.assert_allclose(lo,[.25,.2]);np.testing.assert_allclose(hi,[.35,.3])

if __name__=='__main__':unittest.main()
