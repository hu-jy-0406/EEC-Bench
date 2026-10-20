"""Moving-camera invariant scene fusion and genuine object motion regression."""
import sys,unittest
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;BASE=HERE.parents[1];sys.path[:0]=[str(BASE/'scripts'),str(BASE/'third_party/boxer')]
from build_three_method_static_scenes import camera_record,candidate_rows,fuse_rows,corners
from scipy.spatial.transform import Rotation
class SceneMotionTest(unittest.TestCase):
 def test_moving_camera_static_box_and_true_motion(self):
  # Synthetic world with known geometry and six genuinely distinct camera poses.
  Rbox=Rotation.from_euler('z',.4).as_matrix();size=np.array([1.2,.5,.8]);C=np.array([.3,.1,5.])
  K=np.array([[600.,0,426],[0,600,240],[0,0,1.]])
  cameras={};pred={};obs=[];raw_centers=[];world_centers=[];moving_centers=[]
  for i in range(6):
   R=Rotation.from_euler('xyz',[.025*i,.04*i,-.03*i]).as_matrix();t=np.array([.1*i,-.03*i,.02*i]);cam=camera_record(i,K,R,t,[852,480]);cameras[i]=cam
   # Observation in that frame's camera coordinates, then full pose compensation.
   c_cam=R.T@(C-t);r_cam=R.T@Rbox;raw_centers.append(c_cam)
   c_world=R@c_cam+t;r_world=R@r_cam;world_centers.append(c_world)
   local={'center_world':c_cam.tolist(),'size_xyz':size.tolist(),'R_world_from_object':r_cam.tolist()};pts=corners(local);pix=pts@K.T;pix=pix[:,:2]/pix[:,2:];bb=np.r_[pix.min(0),pix.max(0)].tolist()
   g={'center_world':c_world.tolist(),'size_xyz':size.tolist(),'R_world_from_object':r_world.tolist()};g['corners_world']=corners(g).tolist()
   pred[i]={'e1':{'geometry':g,'confidence':1.,'source_group':str(i)}};obs.append({'frame_id':i,'visible':True,'box_xyxy':bb})
   # Same camera compensation must retain real object translation.
   moving_world=C+np.array([.12*i,0,0]);moving_cam=R.T@(moving_world-t);moving_centers.append(R@moving_cam+t)
  self.assertGreater(np.linalg.norm(np.ptp(raw_centers,axis=0)),.5)
  np.testing.assert_allclose(world_centers,np.tile(C,(6,1)),atol=1e-12)
  np.testing.assert_allclose(np.diff(moving_centers,axis=0),np.tile([.12,0,0],(5,1)),atol=1e-12)
  rows=candidate_rows({'local_id':'e1','observations':obs},pred,cameras);box,info=fuse_rows(rows)
  self.assertEqual(info['status'],'fused');self.assertEqual(len(info['selected_frame_ids']),6)
  np.testing.assert_allclose(box['center_world'],C,atol=1e-12)
  self.assertTrue(all(abs(r['projection_iou']-1)<1e-10 for r in rows))
  np.testing.assert_allclose(box['corners_world'],corners({'center_world':C,'size_xyz':size,'R_world_from_object':Rbox}),atol=1e-12)
if __name__=='__main__':unittest.main()
