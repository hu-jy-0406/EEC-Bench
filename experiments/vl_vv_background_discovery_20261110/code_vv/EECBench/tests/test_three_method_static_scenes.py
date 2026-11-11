import copy
import importlib.util
from pathlib import Path
import sys
import unittest
import numpy as np

CODE=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(CODE))
import build_three_method_static_scenes as m
from render_three_method_static_scenes import camera_lines


def box(center=(0,0,3),size=(2,1,1),rotation=None):
    return dict(center_world=list(center),size_xyz=list(size),R_world_from_object=np.eye(3).tolist() if rotation is None else rotation)


def row(fid,center=(0,0,3),q=1,group=None):
    return dict(frame_id=fid,geometry=box(center),eligible=True,selected=False,weight=0.,raw_quality=q,source_group=group or str(fid))


class FusionTests(unittest.TestCase):
    def test_weighted_median(self):
        self.assertEqual(m.weighted_median([0,2],[1,1]),1)
        self.assertEqual(m.weighted_median([0,2,100],[1,1,.1]),2)

    def test_equivalent_box_rotations_preserve_geometry(self):
        ref=box();p=m.PERMUTATIONS[7];candidate=box(size=(np.abs(p).T@np.array(ref['size_xyz'])).tolist(),rotation=p.tolist())
        r,s=m.align_box(candidate,ref)
        np.testing.assert_allclose(r,np.eye(3),atol=1e-10)
        np.testing.assert_allclose(s,ref['size_xyz'])

    def test_all_24_symmetries(self):
        self.assertEqual(len(m.PERMUTATIONS),24)
        ref=box()
        expected=sorted(map(tuple,np.round(m.corners(ref),8)))
        for p in m.PERMUTATIONS:
            equivalent=box(size=(np.abs(p).T@np.array(ref['size_xyz'])).tolist(),rotation=p.tolist())
            self.assertEqual(sorted(map(tuple,np.round(m.corners(equivalent),8))),expected)

    def test_low_quality_depth_outlier_removed(self):
        rows=[row(0),row(24),row(48),row(72,center=(0,0,100),q=.05)]
        g,info=m.fuse_rows(rows)
        np.testing.assert_allclose(g['center_world'],[0,0,3])
        self.assertFalse(rows[-1]['selected']);self.assertIn(72,info['rejected_frame_ids'])

    def test_shared_state_does_not_multiply_votes(self):
        original=[row(0,group='a'),row(24,center=(2,0,3),group='b')]
        repeated=[row(0,group='a'),row(1,group='a'),row(2,group='a'),row(24,center=(2,0,3),group='b')]
        a,_=m.fuse_rows(original);b,info=m.fuse_rows(repeated)
        np.testing.assert_allclose(a['center_world'],b['center_world'])
        self.assertEqual(info['distinct_geometry_sources'],2)
        self.assertAlmostEqual(sum(r['weight'] for r in repeated if r['source_group']=='a'),.5)

    def test_null_evidence_is_not_zero_geometry(self):
        g,info=m.fuse_rows([dict(eligible=False,frame_id=0)])
        self.assertIsNone(g);self.assertEqual(info['status'],'unresolved')

    def test_tilt_is_not_flattened(self):
        theta=.3;r=[[1,0,0],[0,np.cos(theta),-np.sin(theta)],[0,np.sin(theta),np.cos(theta)]]
        a=row(0);a['geometry']=box(rotation=r);b=copy.deepcopy(a);b.update(frame_id=24,source_group='24')
        g,_=m.fuse_rows([a,b]);np.testing.assert_allclose(g['R_world_from_object'],r,atol=1e-12)
        self.assertAlmostEqual(np.linalg.det(g['R_world_from_object']),1)

    def test_camera_forward_and_up(self):
        c=m.camera_record(0,[[100,0,50],[0,100,50],[0,0,1]],np.eye(3),[1,2,3],[100,100])
        lines=camera_lines(c,2)
        np.testing.assert_allclose(lines['forward_tip'],[1,2,6.2])
        np.testing.assert_allclose(lines['up_tip'],[1,.7,3])
        self.assertTrue(all(p[2]>3 for p in lines['frustum_corners']))

    def test_projection_behind_camera_rejected(self):
        c=m.camera_record(0,[[100,0,50],[0,100,50],[0,0,1]],np.eye(3),[0,0,0],[100,100])
        self.assertEqual(m.projection_iou(box(center=(0,0,-3)),c,[0,0,100,100],[100,100]),0)

    def test_projection_consistent_box(self):
        c=m.camera_record(0,[[100,0,50],[0,100,50],[0,0,1]],np.eye(3),[0,0,0],[100,100])
        self.assertAlmostEqual(m.projection_iou(box(size=(2,2,2)),c,[0,0,100,100],[100,100]),1.)


if __name__=='__main__':unittest.main()
