"""One-frame actual-model coordinate-gauge check, after all pipeline GPU work."""
import os,sys,json,time
from pathlib import Path
import numpy as np
root=Path(__file__).resolve().parent;B=root.parents[1];case=root/'corrected/study2/run'
sys.path[:0]=[str(B/'scripts'),str(B/'third_party/boxer')]
from gs_boxer_camera_frame import predict
from run_isolated_shot_static_3d import owned_compute_job
owned_compute_job()
import torch
from PIL import Image
from scipy.spatial.transform import Rotation
from boxernet.boxernet import BoxerNet
from loaders.base_loader import BaseLoader
from utils.tw.pose import PoseTW
assert os.environ.get('ROCR_VISIBLE_DEVICES','').startswith('GPU-') and torch.cuda.device_count()==1
torch.set_num_threads(4);torch.manual_seed(0);start=time.time();read=lambda p:json.loads(p.read_text())
source=read(case/'inputs/shot1.json');geom=read(case/'pi3x/shot1/complete.json');arr=np.load(case/'pi3x/shot1/geometry.npz');frame=source['frames'][0];camrec=geom['cameras'][0]
model=BoxerNet.load_from_checkpoint(str(B/'third_party/boxer/ckpts/boxernet_hw960in2x6d768-c88128f8.ckpt'),device='cuda');hw=int(model.hw)
cam=np.array(camrec['camera_to_scene']);K=np.array(camrec['K_original']);W,H=camrec['image_size'];image=torch.from_numpy(np.asarray(Image.open(frame['path']).convert('RGB').resize((hw,hw),Image.Resampling.BILINEAR)).copy()).permute(2,0,1).float()/255
selected=[o['box_xyxy'] for e in source['entities'] for o in e['observations'] if o['frame_id']==frame['frame_id'] and o['visible'] and o['box_xyxy'] is not None]
bbox=np.array(selected)[:,[0,2,1,3]]*np.array([hw/W,hw/W,hw/H,hw/H]);conf=arr['confidence'][0];points=arr['world_points'][0];depth=arr['depth'][0]
valid=np.isfinite(points).all(-1)&np.isfinite(conf)&(depth>0)&(conf>=np.quantile(conf[np.isfinite(conf)],.2));grid=np.zeros_like(valid);grid[::2,::2]=True;valid &= grid;cloud=points[valid]
camera=BaseLoader.pinhole_from_K(hw,hw,K[0,0]*hw/W,K[1,1]*hw/H,K[0,2]*hw/W,K[1,2]*hw/H)
def infer(R,t):
 pose=PoseTW.from_Rt(torch.tensor(R@cam[:3,:3],dtype=torch.float32),torch.tensor(R@cam[:3,3]+t,dtype=torch.float32))
 datum=dict(img0=image,cam0=camera,T_world_rig0=pose,sdp_w=torch.tensor(cloud@R.T+t,dtype=torch.float32),bb2d=torch.tensor(bbox,dtype=torch.float32))
 with torch.inference_mode():out=predict(model,datum)
 return out['obbs_pr_w'][0].bb3_center_world.detach().cpu().numpy()
a=infer(np.eye(3),np.zeros(3));results=[]
for w,t in [([.7,-.4,.9],[1.,-2.,.4]),([-1.2,.8,.3],[-.5,.2,1.])]:
 R=Rotation.from_rotvec(w).as_matrix();t=np.array(t);b=infer(R,t);error=np.linalg.norm((b-t)@R-a,axis=1)
 results.append(dict(rotation_vector=w,translation=t.tolist(),center_mean_error=float(error.mean()),center_max_error=float(error.max()),n=len(error)))
result=dict(model_frame='camera_oriented_no_gravity_v1',seconds=time.time()-start,comparisons=results,interpretation='Actual model gauge-equivalence diagnostic; not physical ground truth or gravity-informed prediction equivalence')
(root/'boxer_gauge_probe.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
