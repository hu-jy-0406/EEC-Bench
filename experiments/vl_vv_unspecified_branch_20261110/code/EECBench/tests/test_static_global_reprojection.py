from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import evaluate_static_global_reprojection as m


class ReprojectionTests(unittest.TestCase):
    def test_camera_translation_and_rotation(self):
        r=np.array([[0,0,1],[0,1,0],[-1,0,0]])
        camera=dict(position_world=[1,2,3],R_world_from_camera=r.tolist(),K=[[100,0,50],[0,100,50],[0,0,1]])
        box=dict(center_world=[4,2,3],size_xyz=[2,2,2],R_world_from_object=np.eye(3).tolist())
        p=m.project_box(box,camera)
        np.testing.assert_allclose(p.min(0),[0,0]);np.testing.assert_allclose(p.max(0),[100,100])

    def test_exact_box(self):
        x=m.box_metrics(np.array([[0,0],[100,100]]),[0,0,100,100],[200,200])
        self.assertEqual(x['iou'],1);self.assertEqual(x['edge_rmse_px'],0);self.assertEqual(x['center_error_px'],0)

    def test_shifted_box_errors(self):
        x=m.box_metrics(np.array([[10,0],[110,100]]),[0,0,100,100],[200,200])
        self.assertAlmostEqual(x['iou'],90/110);self.assertAlmostEqual(x['edge_rmse_px'],np.sqrt(50));self.assertEqual(x['center_error_px'],10)

    def test_frame_clipping(self):
        x=m.box_metrics(np.array([[-100,-10],[100,100]]),[0,0,100,100],[100,100])
        self.assertEqual(x['iou'],1);self.assertEqual(x['edge_rmse_px'],0)

    def test_invalid_projection_penalized(self):
        x=m.box_metrics(None,[0,0,100,100],[200,200])
        self.assertEqual(x['iou'],0);self.assertEqual(x['iou_error'],1);self.assertTrue(x['invalid_projection'])
        self.assertAlmostEqual(x['edge_rmse_px'],np.hypot(200,200))

    def test_macro_does_not_overweight_many_visible_frames(self):
        rows=[]
        for method in m.METHODS:
            for sid,eid,n,value in [('shot1','a',10,1.),('shot1','b',1,0.),('shot3','c',1,1.)]:
                for fid in range(n):
                    row=dict(method=method,shot_id=sid,entity_id=eid,frame_id=fid,invalid_projection=False)
                    row.update({key:value for key in m.METRICS});row['iou_error']=1-value;rows.append(row)
        result=m.aggregate(rows)
        for method in result['overall']:
            self.assertAlmostEqual(method['iou'],.75)
            self.assertAlmostEqual(method['all_observations_equal_mean']['iou'],11/12)


if __name__=='__main__':unittest.main()
