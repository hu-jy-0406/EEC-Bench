import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from sparse_scene_3d import (camera_matrix,quat_matrix,sim3,project,reference_corners,camera_from_plane,relative_order,
    compare_order_hypotheses,transformed_relative,box_corners,envelope_iou)


def camera():return dict(fx=800,fy=800,cx=426,cy=240,position_world=[-1.5,-1,.9],look_at_world=[0,0,0],up_hint_world=[0,0,1])
def box(c,err=0):return dict(center_world=list(c),size_xyz=[.1,.1,.1],rotation_wxyz=[1,0,0,0],center_halfwidth_xyz=[err]*3,size_halfwidth_xyz=[0]*3,orientation_error_deg=0,symmetry='none')
def transform(q=None):return dict(rotation_wxyz=q or [1,0,0,0],translation_xyz=[3,4,5],scale=1,rotation_error_deg=0,translation_halfwidth_xyz=[0,0,0],scale_halfwidth=0)

class SparseGeometryTests(unittest.TestCase):
    def test_camera_is_proper_rotation(self):
        r,t=camera_matrix(camera());np.testing.assert_allclose(r.T@r,np.eye(3),atol=1e-12);self.assertAlmostEqual(np.linalg.det(r),1)
    def test_look_at_projects_to_principal_point(self):
        uv,z=project([[0,0,0]],camera());np.testing.assert_allclose(uv[0],[426,240]);self.assertGreater(z[0],0)
    def test_camera_collinear_up_rejected(self):
        c=camera();c['look_at_world']=[-1.5,-1,3]
        with self.assertRaises(ValueError):camera_matrix(c)
    def test_mirror_alignment_rejected(self):
        with self.assertRaises(ValueError):sim3([[1,2,3]],np.diag([-1,1,1]),[0,0,0],1)
    def test_negative_scale_rejected(self):
        with self.assertRaises(ValueError):sim3([[1,2,3]],np.eye(3),[0,0,0],-1)
    def test_sim3_roundtrip(self):
        r=quat_matrix([.9238795,0,0,.3826834]);x=np.array([[1,2,3],[-3,4,.2]]);t=np.array([3,-2,1]);y=sim3(x,r,t,2)
        np.testing.assert_allclose((y-t)@r/2,x,atol=1e-10)
    def test_viewpoint_change_does_not_change_world_relation(self):
        a,b=box([.2,.1,.3]),box([-.1,.5,.4]);r=quat_matrix([.70710678,0,0,.70710678]);axis=np.array([1,0,0])
        out=relative_order(a,b,axis)
        aa,bb=box(sim3([a['center_world']],r,[4,5,6],2)[0]),box(sim3([b['center_world']],r,[4,5,6],2)[0])
        self.assertEqual(out['allowed_orders'],relative_order(aa,bb,r@axis)['allowed_orders'])
    def test_exact_plane_calibration(self):
        c=camera();p=reference_corners(.55);uv,_=project(p,c);r,t=camera_from_plane(c,p,uv);got,_=project(p,c,(r,t))
        np.testing.assert_allclose(got,uv,atol=1e-8);self.assertGreater((-r.T@t)[2],0)
    def test_mirrored_corner_labels_produce_below_plane_camera(self):
        c=camera();p=reference_corners(.55);uv,_=project(p,c);r,t=camera_from_plane(c,p,uv[[1,0,3,2]])
        self.assertLess((-r.T@t)[2],0)
    def test_boxes_are_three_dimensional(self):
        pts=box_corners(box([0,0,.05]));np.testing.assert_allclose(pts.min(axis=0),[-.05,-.05,0]);np.testing.assert_allclose(pts.max(axis=0),[.05,.05,.1])
    def test_height_reversal_detected(self):
        a,b=box([0,0,.2]),box([0,0,.5]);out=compare_order_hypotheses(a,b,b,a,[0,0,1],[transform()]);self.assertEqual(out['status'],'conflict')
    def test_camera_yaw_is_not_an_object_reversal(self):
        a,b=box([.2,0,0]),box([-.2,0,0]);out=compare_order_hypotheses(a,b,b,a,[1,0,0],[transform([0,0,0,1])]);self.assertEqual(out['status'],'compatible')
    def test_alignment_ambiguity_not_forced(self):
        a,b=box([.2,0,0]),box([-.2,0,0]);out=compare_order_hypotheses(a,b,a,b,[1,0,0],[transform(),transform([0,0,0,1])]);self.assertEqual(out['status'],'alignment_dependent')
    def test_wide_uncertainty_not_conflict(self):
        a,b=box([.2,0,0],.3),box([-.2,0,0],.3);out=compare_order_hypotheses(a,b,b,a,[1,0,0],[transform()]);self.assertEqual(out['status'],'position_uncertain')
    def test_failed_projection_blocks_claim(self):
        a,b=box([.2,0,0]),box([-.2,0,0]);self.assertEqual(compare_order_hypotheses(a,b,b,a,[1,0,0],[transform()],False)['status'],'geometry_unverified')
    def test_translation_error_cancels_for_relative_order(self):
        a,b=box([.2,0,0]),box([-.2,0,0]);h=transform();before=transformed_relative(a,b,h,[1,0,0]);h['translation_halfwidth_xyz']=[100,100,100]
        self.assertEqual(before,transformed_relative(a,b,h,[1,0,0]))
    def test_rotation_uncertainty_is_propagated(self):
        a,b=box([.2,0,0]),box([-.2,0,0]);h=transform();h['rotation_error_deg']=180
        self.assertEqual(set(transformed_relative(a,b,h,[1,0,0])['allowed_orders']),{'less','aligned','greater'})
    def test_visible_box_not_amodal_box(self):
        iou,coverage=envelope_iou([0,0,100,100],[20,20,40,40]);self.assertEqual(coverage,1);self.assertLess(iou,.1)

    def test_positive_scale_uncertainty_cannot_reverse_order(self):
        a,b=box([.2,0,0]),box([0,0,0]);h=transform();h['scale_halfwidth']=.99
        self.assertEqual(transformed_relative(a,b,h,[1,0,0])['allowed_orders'],['greater'])
    def test_angular_bounds_match_rotation_endpoints(self):
        a,b=box([1,0,0]),box([0,0,0]);h=transform();h['rotation_error_deg']=30
        lo,hi=transformed_relative(a,b,h,[1,0,0])['delta_interval']
        self.assertAlmostEqual(lo,np.cos(np.pi/6));self.assertAlmostEqual(hi,1)
    def test_alignment_cannot_drop_self_referenced_alternative(self):
        from align_sparse_scene_3d import independent_hypotheses
        candidates=[dict(anchor_group_ids=['g1']),dict(anchor_group_ids=['g2'])]
        self.assertEqual(independent_hypotheses(candidates,['g1']),[])
    def test_pair_requires_same_camera_hypothesis(self):
        from align_sparse_scene_3d import qualified_options
        cam=dict(frame_id=0,observed_corners=4,camera_above_surface=True,raw_corner_rmse_px=0,plane_corner_rmse_px=0,plane_camera_center=[0,0,1])
        quality=dict(cameras=[cam],projected_boxes=[dict(entity_id='a',frame_id=0,camera_variant='raw',all_corners_in_front=True,visible_box_coverage=1),dict(entity_id='b',frame_id=0,camera_variant='plane_calibrated',all_corners_in_front=True,visible_box_coverage=1)])
        self.assertFalse(qualified_options('a',quality)&qualified_options('b',quality))

    def test_coordinate_frame_id_collisions_rejected(self):
        from materialize_sparse_scene_3d import validate_frames
        f=dict(frame_id='world',parent_frame_id=None,pose_parent_from_frame=None)
        with self.assertRaises(ValueError):validate_frames(dict(frames=[f,f],entities=[]))
    def test_coordinate_frame_cycles_rejected(self):
        from materialize_sparse_scene_3d import validate_frames
        frames=[dict(frame_id=a,parent_frame_id=b,pose_parent_from_frame=None) for a,b in [('a','b'),('b','a')]]
        with self.assertRaises(ValueError):validate_frames(dict(frames=frames,entities=[]))
    def test_coordinate_frame_reflection_rejected(self):
        from materialize_sparse_scene_3d import validate_frames
        frames=[dict(frame_id='a',parent_frame_id=None,pose_parent_from_frame=dict(rotation=np.diag([-1,1,1]).tolist(),translation=[0,0,0],scale=1))]
        with self.assertRaises(ValueError):validate_frames(dict(frames=frames,entities=[]))

if __name__=='__main__':unittest.main()
