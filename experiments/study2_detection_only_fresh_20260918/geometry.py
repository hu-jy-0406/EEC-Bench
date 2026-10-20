"""One-shot-only advanced reconstruction; guarded GPU launch is external."""
import argparse,hashlib,json,math,os,subprocess,sys,time
from pathlib import Path
import numpy as np
BASE=Path(__file__).resolve().parents[2]; HERE=Path(os.environ['CASE_ROOT'])
sys.path[:0]=[str(HERE/'deps'),str(BASE/'scripts'),str(BASE/'third_party/Pi3'),str(BASE/'third_party/Depth-Anything-3/src'),str(BASE/'third_party/dvlt/src')]
from run_isolated_shot_static_3d import owned_compute_job

def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(x):return x/np.linalg.norm(x,axis=-1,keepdims=True)

def infer_pinhole(local,confidence):
 h,w=local.shape[:2];yy,xx=np.mgrid[:h,:w];valid=(local[...,2]>1e-6)&np.isfinite(local).all(-1)&(confidence>np.median(confidence))
 valid[1::2]=False;valid[:,1::2]=False
 K=np.eye(3);res=[]
 for axis,pixel in [(0,xx),(1,yy)]:
  ray=local[...,axis]/np.maximum(local[...,2],1e-8)
  A=np.stack([ray[valid],np.ones(valid.sum())],-1);y=pixel[valid]
  v=np.linalg.lstsq(A,y,rcond=None)[0];error=A@v-y
  # One robust refit, no object geometry or cross-shot result involved.
  good=np.abs(error)<=np.quantile(np.abs(error),.9)
  v=np.linalg.lstsq(A[good],y[good],rcond=None)[0]
  K[axis,axis],K[axis,2]=v;res.append(float(np.sqrt(np.mean((A@v-y)**2))))
 assert K[0,0]>0 and K[1,1]>0
 return K,res

def main():
 p=argparse.ArgumentParser();p.add_argument('--method',choices=['pi3x','pi3x_native','da3nested','dvlt'],required=True);p.add_argument('--shot',required=True);args=p.parse_args()
 if not args.shot or Path(args.shot).name!=args.shot or args.shot in ('.','..'):raise ValueError('Invalid shot ID')
 allocation=owned_compute_job();import torch
 torch.set_num_threads(4);torch.manual_seed(0)
 if not os.environ.get('ROCR_VISIBLE_DEVICES','').startswith('GPU-'):raise RuntimeError('Expected UUID guarded GPU binding')
 assert torch.cuda.is_available() and torch.cuda.device_count()==1
 out=HERE/args.method/args.shot
 if (out/'complete.json').exists():raise RuntimeError('Output already completed; do not overwrite')
 out.mkdir(parents=True,exist_ok=True)
 manifest=read(HERE/'inputs'/f'{args.shot}.json');frames=manifest['frames']
 for f in frames:
  if sha(Path(f['path']))!=f['sha256']:raise ValueError('Original JPEG hash mismatch')
 paths=[f['path'] for f in frames]
 modelid={'pi3x':'yyfz233--Pi3X','pi3x_native':'yyfz233--Pi3X','da3nested':'depth-anything--DA3NESTED-GIANT-LARGE-1.1','dvlt':'nvidia--dvlt'}[args.method]
 download=read(HERE/(modelid+'_download.json'));weights=BASE/'models'/modelid
 start=time.time();save(out/'status.json',{'status':'loading','pid':os.getpid(),'allocation':allocation,'started':start,'method':args.method,'shot':args.shot})
 print('LOAD',args.method,args.shot,flush=True)
 if args.method.startswith('pi3x'):
  from pi3.models.pi3x import Pi3X
  from PIL import Image
  model=Pi3X.from_pretrained(str(weights)).eval().to('cuda')
  model.disable_multimodal()
  W,H=Image.open(paths[0]).size;pixel_budget=W*H if args.method=='pi3x_native' else 255000;scale=math.sqrt(pixel_budget/(W*H));kw,kh=round(W*scale/14),round(H*scale/14)
  while kw*kh*196>pixel_budget:
   if kw/kh>W/H:kw-=1
   else:kh-=1
  w,h=kw*14,kh*14
  images=np.stack([np.asarray(Image.open(p).convert('RGB').resize((w,h),Image.Resampling.LANCZOS)) for p in paths])
  imgs=torch.from_numpy(images.copy()).permute(0,3,1,2).float().div(255).to('cuda')
  print('INFER',imgs.shape,flush=True)
  with torch.inference_mode(),torch.autocast('cuda',dtype=torch.bfloat16):pred=model(imgs[None],with_prior=False)
  local=pred['local_points'][0].float().cpu().numpy();c2w=pred['camera_poses'][0].float().cpu().numpy()
  conf=pred['conf'][0,...,0].float().sigmoid().cpu().numpy();depth=local[...,2]
  fitted=[infer_pinhole(l,c) for l,c in zip(local,conf)];K=np.array([k for k,r in fitted]);ray_errors=[r for k,r in fitted]
  official_world=pred['points'][0].float().cpu().numpy()
  del pred,imgs
 elif args.method=='da3nested':
  from depth_anything_3.api import DepthAnything3
  from depth_anything_3.utils.io.input_processor import InputProcessor
  class SerialInput(InputProcessor):
   def __call__(self,*a,**kw):kw.update(num_workers=1,sequential=True);return super().__call__(*a,**kw)
  model=DepthAnything3.from_pretrained(str(weights)).eval().to('cuda');model.input_processor=SerialInput()
  print('INFER DA3 ray pose, 504 long side',flush=True)
  pred=model.inference(paths,process_res=504,process_res_method='upper_bound_resize',use_ray_pose=True,ref_view_strategy='saddle_balanced',export_dir=None)
  depth=np.asarray(pred.depth);conf=np.asarray(pred.conf);K=np.asarray(pred.intrinsics);ext=np.asarray(pred.extrinsics)
  if ext.shape[-2:]==(3,4):ext=np.concatenate([ext,np.tile(np.array([[[0,0,0,1]]]),(len(ext),1,1))],1)
  c2w=np.linalg.inv(ext);n,h,w=depth.shape;yy,xx=np.mgrid[:h,:w];pix=np.stack([xx,yy,np.ones_like(xx)],-1)
  local=np.einsum('nij,hwj->nhwi',np.linalg.inv(K),pix)*depth[...,None]
  ray_errors=None;official_world=None
  del pred
 else:
  from dvlt.model.dvlt.model import DVLT
  from dvlt.util.preprocess import preprocess_images
  from accelerate import Accelerator
  from PIL import Image
  accelerator=Accelerator(mixed_precision='bf16')
  model=DVLT(**read(weights/'config.json'));model.load_pretrained(str(weights),strict=True);model.setup_test(accelerator)
  batch=preprocess_images([Image.open(p).convert('RGB') for p in paths],img_size=504,patch_size=14,device=accelerator.device)
  with torch.inference_mode(),torch.autocast('cuda',dtype=torch.bfloat16):pred=model.predict(batch,accelerator)
  cameras=pred['cameras'][0];K=cameras.get_intrinsics_matrices().float().cpu().numpy();c2w=cameras.camera_to_worlds.float().cpu().numpy()
  if c2w.shape[-2:]==(3,4):c2w=np.concatenate([c2w,np.tile(np.array([[[0,0,0,1]]]),(len(c2w),1,1))],1)
  depth=pred['depths'][0].float().cpu().numpy();conf=pred['depths_conf'][0].float().cpu().numpy().reshape(depth.shape)
  n,h,w=depth.shape;yy,xx=np.mgrid[:h,:w];pix=np.stack([xx,yy,np.ones_like(xx)],-1)
  local=np.einsum('nij,hwj->nhwi',np.linalg.inv(K),pix)*depth[...,None]
  official_world=pred['world_points'][0].float().cpu().numpy();ray_errors=None
  del pred,batch
 torch.cuda.synchronize();peak=torch.cuda.max_memory_allocated();del model;torch.cuda.empty_cache()
 assert local.shape==(*depth.shape,3) and np.isfinite(c2w).all()
 assert np.max(np.abs(np.linalg.det(c2w[:,:3,:3])-1))<1e-3
 rawworld=np.einsum('nij,nhwj->nhwi',c2w[:,:3,:3],local)+c2w[:,None,None,:3,3]
 replay=float(np.max(abs(rawworld-official_world))) if official_world is not None else None
 if replay is not None:assert replay<1e-3*max(float(np.max(abs(rawworld))),1)
 # One fixed scene basis per shot, with gravity evidence from this shot only.
 coordinate_mode=manifest.get('coordinate_mode','gravity_aligned')
 if coordinate_mode=='pi3x_native':
  if args.method!='pi3x':raise ValueError('Gravity-free mode is validated for Pi3X only')
  Q=np.eye(3)
 elif coordinate_mode=='gravity_aligned':
  calib=manifest['calibration'];ups=np.array([r['geocalib_gravity_raw'] for r in calib['records']]);world_up=norm(np.mean(np.einsum('nij,nj->ni',c2w[:,:3,:3],ups),axis=0))
  y=c2w[0,:3,2];y=norm(y-world_up*np.dot(y,world_up));x=norm(np.cross(y,world_up));Q=np.stack([x,y,world_up])
 else:raise ValueError('Unknown scene coordinate mode')
 # Origin is chosen once from scene samples, never per-frame recentered.
 samples=rawworld[:,::8,::8].reshape(-1,3);samples=samples[np.isfinite(samples).all(1)];origin=np.median(samples,axis=0)
 world=np.einsum('ij,nhwj->nhwi',Q,rawworld-origin)
 scene_c2w=c2w.copy();scene_c2w[:,:3,:3]=np.einsum('ij,njk->nik',Q,c2w[:,:3,:3]);scene_c2w[:,:3,3]=(c2w[:,:3,3]-origin)@Q.T
 np.savez_compressed(out/'geometry.npz',depth=depth.astype('float32'),confidence=conf.astype('float32'),local_points=local.astype('float32'),world_points=world.astype('float32'),intrinsics=K,raw_camera_to_world=c2w,camera_to_scene=scene_c2w)
 original_sizes=manifest['image_sizes'];cameras=[]
 for f,k,c,sz in zip(frames,K,scene_c2w,original_sizes):
  ko=k.copy()
  if args.method=='dvlt':
   resize_scale=504/max(sz);rw,rh=round(sz[0]*resize_scale),round(sz[1]*resize_scale)
   ko[0,2]+=(rw-depth.shape[2])//2;ko[1,2]+=(rh-depth.shape[1])//2
   ko[0]*=sz[0]/rw;ko[1]*=sz[1]/rh
  else:ko[0]*=sz[0]/depth.shape[2];ko[1]*=sz[1]/depth.shape[1]
  cameras.append(dict(frame_id=f['frame_id'],K_original=ko.tolist(),K_model=k.tolist(),camera_to_scene=c.tolist(),image_size=sz,model_image_size=[depth.shape[2],depth.shape[1]]))
 record=dict(status='complete',method=args.method,shot_id=args.shot,scene_frame_id=args.shot+'/'+args.method+'_scene',scene_axes=('right-handed arbitrary Pi3X axes; no physical-up estimate' if coordinate_mode=='pi3x_native' else 'right-handed Z-up fixed scene'),coordinate_mode=coordinate_mode,scene_origin_raw=origin.tolist(),scene_rotation_from_raw=Q.tolist(),
  camera_convention='OpenCV X-right Y-down Z-forward; camera_to_scene maps columns into scene',cameras=cameras,
  frame_count=len(frames),entity_count=len(manifest['entities']),inputs_sha256=sha(HERE/'inputs'/f'{args.shot}.json'),model_revision=download['revision'],
  model_file_sha256={Path(f['path']).name:f['sha256'] for f in download['files']},
  seconds=time.time()-start,peak_gpu_bytes=peak,torch_version=torch.__version__,allocation=allocation,
  camera_position_range=np.ptp(scene_c2w[:,:3,3],axis=0).tolist(),point_pose_replay_max_error=replay,ray_fit_pixel_rmse=ray_errors,
  scale=('arbitrary model scene units' if args.method=='dvlt' else 'model metric prior, not calibrated ground truth'),frame_source='original JPEGs, resized in memory only',single_shot_input_only=True)
 save(out/'complete.json',record);print('COMPLETE',args.method,args.shot,record['seconds'],record['camera_position_range'],flush=True)
if __name__=='__main__':main()
