"""Predict all frozen entities with depth-conditioned Boxer in one fixed scene."""
import argparse,json,os,sys,time
from pathlib import Path
import numpy as np
BASE=Path(__file__).resolve().parents[2]; HERE=Path(os.environ['CASE_ROOT'])
sys.path[:0]=[str(HERE/'deps'),str(BASE/'scripts'),str(BASE/'third_party/boxer')]
from run_isolated_shot_static_3d import owned_compute_job
from build_three_method_static_scenes import camera_record,candidate_rows,fuse_rows,projection_iou,corners

def read(p):return json.loads(p.read_text())
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def main():
 p=argparse.ArgumentParser();p.add_argument('--method',required=True);p.add_argument('--shot',required=True);p.add_argument('--no-depth',action='store_true');args=p.parse_args()
 if not args.shot or Path(args.shot).name!=args.shot or args.shot in ('.','..'):raise ValueError('Invalid shot ID')
 allocation=owned_compute_job();import torch
 from PIL import Image
 from boxernet.boxernet import BoxerNet
 from loaders.base_loader import BaseLoader
 from utils.tw.pose import PoseTW
 torch.set_num_threads(4);torch.manual_seed(0)
 assert os.environ.get('ROCR_VISIBLE_DEVICES','').startswith('GPU-') and torch.cuda.is_available()
 root=HERE/args.method/args.shot;source=read(HERE/'inputs'/f'{args.shot}.json');geom=read(root/'complete.json');arrays=np.load(root/'geometry.npz')
 out=root/('boxer_no_depth' if args.no_depth else 'boxer_depth')
 if (out/'complete.json').exists():raise RuntimeError('Already completed')
 out.mkdir(parents=True,exist_ok=True);start=time.time()
 model=BoxerNet.load_from_checkpoint(str(BASE/'third_party/boxer/ckpts/boxernet_hw960in2x6d768-c88128f8.ckpt'),device='cuda');hw=int(model.hw)
 cameras={};frame_predictions={}
 for idx,(frame,camrec) in enumerate(zip(source['frames'],geom['cameras'])):
  fid=frame['frame_id'];cam=np.array(camrec['camera_to_scene']);K=np.array(camrec['K_original']);W,H=camrec['image_size']
  cameras[fid]=camera_record(fid,K,cam[:3,:3],cam[:3,3],[W,H]);dest=out/f'frame_{fid:06d}.json'
  if dest.exists():predictions=read(dest)['entities']
  else:
   selected=[]
   for e in source['entities']:
    o=next(o for o in e['observations'] if o['frame_id']==fid)
    if o['visible'] and o['box_xyxy'] is not None:selected.append((e,o))
   if not selected:
    save(dest,{'shot_id':args.shot,'frame_id':fid,'depth_points':0,'camera':cameras[fid],'entities':[],'geometry_skipped':'no retained detections'})
    frame_predictions[fid]={}
    continue
   im=Image.open(frame['path']).convert('RGB');image=torch.from_numpy(np.asarray(im.resize((hw,hw),Image.Resampling.BILINEAR)).copy()).permute(2,0,1).float()/255
   bbox=np.array([o['box_xyxy'] for e,o in selected])[:,[0,2,1,3]]*np.array([hw/W,hw/W,hw/H,hw/H])
   conf=arrays['confidence'][idx];points=arrays['world_points'][idx];depth=arrays['depth'][idx]
   valid=np.isfinite(points).all(-1)&np.isfinite(conf)&(depth>0)&(conf>=np.quantile(conf[np.isfinite(conf)],.2))
   grid=np.zeros_like(valid);grid[::2,::2]=True;valid &= grid
   cloud=points[valid].astype('float32') if not args.no_depth else np.zeros((0,3),dtype='float32')
   camera=BaseLoader.pinhole_from_K(hw,hw,K[0,0]*hw/W,K[1,1]*hw/H,K[0,2]*hw/W,K[1,2]*hw/H)
   pose=PoseTW.from_Rt(torch.tensor(cam[:3,:3],dtype=torch.float32),torch.tensor(cam[:3,3],dtype=torch.float32))
   datum={'img0':image,'cam0':camera,'T_world_rig0':pose,'sdp_w':torch.from_numpy(cloud),'bb2d':torch.tensor(bbox,dtype=torch.float32)}
   with torch.inference_mode():
    if geom.get('coordinate_mode')=='pi3x_native':
     from gs_boxer_camera_frame import predict
     res=predict(model,datum)
    else:res=model(datum)
   obb=res['obbs_pr_w'][0];cs=obb.bb3_center_world.detach().cpu().numpy();ss=obb.bb3_diagonal.detach().cpu().numpy();rs=obb.T_world_object.R.detach().cpu().numpy();probs=obb.prob.detach().cpu().numpy()
   assert len(cs)==len(selected)
   predictions=[]
   for i,(e,o) in enumerate(selected):
    box={'center_world':cs[i].tolist(),'size_xyz':ss[i].tolist(),'R_world_from_object':rs[i].tolist()};box['corners_world']=corners(box).tolist()
    predictions.append({'entity_id':e['entity_id'],'name':e['name'],'geometry':box,'confidence':float(np.asarray(probs[i]).reshape(-1)[0]),'box_xyxy':o['box_xyxy']})
   save(dest,{'shot_id':args.shot,'frame_id':fid,'depth_points':len(cloud),'camera':cameras[fid],'entities':predictions})
   print('BOXER',args.method,args.shot,fid,len(predictions),'points',len(cloud),flush=True)
  frame_predictions[fid]={e['entity_id']:dict(geometry=e['geometry'],confidence=e['confidence'],source_group=f'{args.shot}/{e["entity_id"]}/frame{fid}',source_path=str(dest)) for e in predictions}
 del model;torch.cuda.empty_cache()
 save(out/'inference_complete.json',{'status':'complete','seconds':time.time()-start,'allocation':allocation,'inference_frame':('camera_oriented_no_gravity_v1' if geom.get('coordinate_mode')=='pi3x_native' else 'gravity_aligned_world_z')})
if __name__=='__main__':main()
