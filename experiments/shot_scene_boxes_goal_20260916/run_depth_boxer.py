"""Predict all frozen entities with depth-conditioned Boxer in one fixed scene."""
import argparse,json,os,sys,time
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;BASE=HERE.parents[1]
sys.path[:0]=[str(HERE/'deps'),str(BASE/'scripts'),str(BASE/'third_party/boxer')]
from run_isolated_shot_static_3d import owned_compute_job
from build_three_method_static_scenes import camera_record,candidate_rows,fuse_rows,projection_iou,corners

def read(p):return json.loads(p.read_text())
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def main():
 p=argparse.ArgumentParser();p.add_argument('--method',required=True);p.add_argument('--shot',choices=['shot1','shot3'],required=True);p.add_argument('--no-depth',action='store_true');args=p.parse_args()
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
   im=Image.open(frame['path']).convert('RGB');image=torch.from_numpy(np.asarray(im.resize((hw,hw),Image.Resampling.BILINEAR)).copy()).permute(2,0,1).float()/255
   bbox=np.array([o['box_xyxy'] for e,o in selected])[:,[0,2,1,3]]*np.array([hw/W,hw/W,hw/H,hw/H])
   conf=arrays['confidence'][idx];points=arrays['world_points'][idx];depth=arrays['depth'][idx]
   valid=np.isfinite(points).all(-1)&np.isfinite(conf)&(depth>0)&(conf>=np.quantile(conf[np.isfinite(conf)],.2))
   grid=np.zeros_like(valid);grid[::2,::2]=True;valid &= grid
   cloud=points[valid].astype('float32') if not args.no_depth else np.zeros((0,3),dtype='float32')
   camera=BaseLoader.pinhole_from_K(hw,hw,K[0,0]*hw/W,K[1,1]*hw/H,K[0,2]*hw/W,K[1,2]*hw/H)
   pose=PoseTW.from_Rt(torch.tensor(cam[:3,:3],dtype=torch.float32),torch.tensor(cam[:3,3],dtype=torch.float32))
   datum={'img0':image,'cam0':camera,'T_world_rig0':pose,'sdp_w':torch.from_numpy(cloud),'bb2d':torch.tensor(bbox,dtype=torch.float32)}
   with torch.inference_mode():res=model(datum)
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
 # Hold the original independently obtained partition fixed for fair method comparison.
 labels_path=BASE/'experiments/study_inconsistent_3/shot_static_3d_isolated_20260914/run01'/args.shot/'agent_review.json'
 labels={e['entity_id']:e['status'] for e in read(labels_path)['shots'][0]['entities']}
 entities=[]
 for source_entity in source['entities']:
  e={**source_entity,'local_id':source_entity['entity_id'],'entity_id':args.shot+'/'+source_entity['entity_id']}
  rows=candidate_rows(e,frame_predictions,cameras);status=labels[e['entity_id']]
  if status=='static':box,info=fuse_rows(rows)
  else:box,info=None,None
  if box is None:
   valid=[r for r in rows if r.get('geometry')]
   if not valid:raise RuntimeError('No box for entity '+e['entity_id'])
   best=max(valid,key=lambda r:r.get('raw_quality',0))
   box=best['geometry'];info={'status':'representative_frame','frame_id':best['frame_id'],'reason':'moving_or_unknown_entity' if status!='static' else 'fusion_lacks_supported_observations'}
  ious=[projection_iou(box,cameras[r['frame_id']],r['box_xyxy'],cameras[r['frame_id']]['image_size']) for r in rows if r['visible'] and r['box_xyxy'] is not None]
  entities.append({'entity_id':e['entity_id'],'name':e['name'],'motion_status':status,'geometry':box,'aggregation':info,'frame_evidence':rows,
   'fused_projection_mean_iou':float(np.mean(ious)),'motion_label_source':'frozen_independent_shot_review_controlled_comparison_not_rejudged'})
 graph={'schema_version':'all_entity_scene_v1','method':args.method+('_boxer_no_depth' if args.no_depth else '_boxer_depth'),'shot_id':args.shot,
  'coordinate_system':{'world_frame_id':geom['scene_frame_id'],'origin':'fixed scene point-cloud median','z_axis':'up','per_frame_camera_poses':True,'scale':geom['scale']},
  'cameras':list(cameras.values()),'entities':entities,'counts':{'entities':len(entities),'boxes':len(entities),'static':sum(e['motion_status']=='static' for e in entities)},
  'limitations':['Estimated depth and camera poses, not ground truth.','Frozen independent static partition retained for controlled comparison.','Moving entity box represents one selected frame; frame_evidence preserves trajectory.','Input-conditioned reprojection is not independent 3D accuracy.']}
 assert len(entities)==len(source['entities'])
 save(out/'scene_graph.json',graph)
 save(out/'complete.json',{'status':'complete','seconds':time.time()-start,'allocation':allocation,'all_entities_covered':True,'counts':graph['counts'],'depth_input':not args.no_depth})
 print('COMPLETE',graph['method'],args.shot,graph['counts'],time.time()-start,flush=True)
if __name__=='__main__':main()
