import copy
import importlib.util
from pathlib import Path
import unittest
import numpy as np

spec=importlib.util.spec_from_file_location('static3d',Path(__file__).resolve().parents[1]/'scripts/run_shot_static_3d.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def state(i,center=(0,0,0),size=(4,2,1),yaw=0):
    r=[[np.cos(yaw),-np.sin(yaw),0],[np.sin(yaw),np.cos(yaw),0],[0,0,1]]
    return dict(frame_id=i,geometry=dict(center_world=list(center),size_xyz=list(size),R_world_from_object=r))

class Static3DTests(unittest.TestCase):
    def test_robust_multiframe_not_reference(self):
        g,a=m.fuse([state(0,(100,0,0)),state(24,(2,0,0)),state(48,(4,0,0))])
        self.assertEqual(g['center_world'],[4,0,0]);self.assertEqual(a['source_count'],3)
    def test_even_median_uses_multiple_frames(self):
        g,_=m.fuse([state(0,(2,0,0)),state(24,(4,0,0))]);self.assertEqual(g['center_world'],[3,0,0])
    def test_equivalent_xy_swap_and_pi(self):
        g,a=m.fuse([state(0),state(24,size=(2,4,1),yaw=np.pi/2),state(48,yaw=np.pi)])
        np.testing.assert_allclose(g['size_xyz'],[4,2,1]);np.testing.assert_allclose(g['R_world_from_object'],np.eye(3),atol=1e-8)
    def test_circular_wrap(self):
        g,_=m.fuse([state(0,yaw=.01),state(24,yaw=np.pi-.01)]);r=np.array(g['R_world_from_object']);self.assertGreater(abs(r[0,0]),.99)
    def test_transformed_corners(self):
        r=np.array([[0,-1,0],[1,0,0],[0,0,1]]);pts=m.corners([1,2,3],[4,2,6],r)
        self.assertEqual(len(pts),8);np.testing.assert_allclose(np.ptp(pts,axis=0),[2,4,6]);np.testing.assert_allclose(pts.mean(axis=0),[1,2,3])
    def test_null_is_omitted_not_zero(self):
        g,a=m.fuse([dict(frame_id=0,geometry=None),state(24,(5,6,7))]);self.assertEqual(g['center_world'],[5,6,7]);self.assertEqual(a['source_frame_ids'],[24])
    def test_static_only_and_coverage(self):
        import json
        src=json.loads(m.SOURCE.read_text());rev=json.loads((m.OUT/'agent_review.json').read_text());g=m.build(src,rev)
        self.assertEqual(sum(len(s['entities']) for s in rev['shots']),41)
        ids={e['entity_id'] for s in g['shots'] for e in s['entities']}
        expected={e['entity_id'] for s in rev['shots'] for e in s['entities'] if e['status']=='static'}
        self.assertEqual(ids,expected);self.assertEqual(len(g['shots']),2)
        bad=copy.deepcopy(rev);bad['shots'][0]['entities'].pop()
        with self.assertRaises(ValueError):m.build(src,bad)
    def test_single_frame_is_not_shot_fusion(self):
        import json
        src=json.loads(m.SOURCE.read_text());rev=json.loads((m.OUT/'agent_review.json').read_text())
        entity=src['shots'][0]['entities'][0]
        kept=False
        for row in entity['states']:
            if row['geometry'] is not None and not kept:
                kept=True
            else:
                row['geometry']=None
        with self.assertRaises(ValueError):m.build(src,rev)
    def test_movement_veto(self):
        import json
        src=json.loads(m.SOURCE.read_text());rev=json.loads((m.OUT/'agent_review.json').read_text())
        rev['shots'][0]['entities'][0]['motion_intervals']=[[24,48]]
        with self.assertRaises(ValueError):m.build(src,rev)

if __name__=='__main__':unittest.main()
