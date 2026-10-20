import argparse,os,sys,time,itertools
from pathlib import Path
import numpy as np
from common import *
p=argparse.ArgumentParser();p.add_argument('--method',choices=['roma','sift'],default='roma');p.add_argument('--part',type=int,default=0);p.add_argument('--parts',type=int,default=1);a=p.parse_args();job=owned_compute_job()
import cv2
cv2.setNumThreads(1)
A,B=inputs('shot1'),inputs('shot3');frames=[A['frames'],B['frames']];out=RUN/a.method;out.mkdir(exist_ok=True)
for f in frames[0]+frames[1]:assert sha(f['path'])==f['sha256']
if a.method=='roma':
 import torch
 import torch.nn.functional as F
 assert os.environ.get('ROCR_VISIBLE_DEVICES','').startswith('GPU-') and torch.cuda.device_count()==1
 torch.set_num_threads(4);torch.set_float32_matmul_precision('highest');torch.manual_seed(31)
 torch.hub.set_dir(str(BASE/'experiments/study2_multiframe_image_registration_20260916/torch_cache/hub'));sys.path.insert(0,str(BASE/'third_party/RoMaV2/src'))
 from romav2 import RoMaV2
 model=RoMaV2();model.apply_setting('precise')
else:
 model=cv2.SIFT_create(nfeatures=6000,contrastThreshold=.02);cache={}
 for side,(s,fs) in enumerate(zip(['shot1','shot3'],frames)):
  for f in fs:
   im=cv2.imread(f['path'],0);mask=(structural_mask(s,f['frame_id'])>0).astype('uint8')*255;k,d=model.detectAndCompute(im,mask);cache[side,f['frame_id']]=(k,d)
for index,(fa,fb) in enumerate(itertools.product(*frames)):
 if index%a.parts!=a.part:continue
 ia,ib=fa['frame_id'],fb['frame_id'];dest=out/f'{ia:03d}_{ib:03d}.npz'
 if dest.exists():continue
 start=time.time()
 if a.method=='roma':
  torch.manual_seed(31+index)
  with torch.inference_mode():
   pred=model.match(fa['path'],fb['path']);m,c,_,_=model.sample(pred,5000)
   wa,ha=A['image_sizes'][0];wb,hb=B['image_sizes'][0]
   uvA,uvB=model.to_pixel_coordinates(m,ha,wa,hb,wb)
   ab=F.grid_sample(pred['warp_AB'].permute(0,3,1,2),m[:,:2][None,None],align_corners=False)[0,:,0].T
   ba=F.grid_sample(pred['warp_BA'].permute(0,3,1,2),m[:,2:][None,None],align_corners=False)[0,:,0].T
   ratioA=torch.tensor([wa/2,ha/2],device=m.device);ratioB=torch.tensor([wb/2,hb/2],device=m.device);cycle=torch.maximum(torch.linalg.norm((ab-m[:,2:])*ratioB,dim=1),torch.linalg.norm((ba-m[:,:2])*ratioA,dim=1))
   uvA,uvB,conf,cycle=[x.float().cpu().numpy() for x in [uvA,uvB,c,cycle]]
   del pred,m,c
 else:
  k1,d1=cache[0,ia];k2,d2=cache[1,ib];match=[]
  if d1 is not None and d2 is not None:
   bf=cv2.BFMatcher();forward=bf.knnMatch(d1,d2,k=2);back=bf.knnMatch(d2,d1,k=2);rev={m.queryIdx:m.trainIdx for m,n in back if m.distance<.8*n.distance}
   match=[m for m,n in forward if m.distance<.8*n.distance and rev.get(m.trainIdx)==m.queryIdx]
  uvA=np.array([k1[m.queryIdx].pt for m in match],np.float32).reshape(-1,2);uvB=np.array([k2[m.trainIdx].pt for m in match],np.float32).reshape(-1,2);conf=np.ones(len(match),np.float32);cycle=np.zeros(len(match),np.float32)
 np.savez_compressed(dest,uvA=uvA,uvB=uvB,confidence=conf,cycle_pixels=cycle,frame_a=ia,frame_b=ib)
 rec={'index':index,'frame_a':ia,'frame_b':ib,'matches':len(uvA),'seconds':time.time()-start,'allocation':job,'method':a.method,'input_hashes':[fa['sha256'],fb['sha256']]};save(dest.with_suffix('.json'),rec);print(rec,flush=True)
print('MATCH PART COMPLETE',a.method,a.part,flush=True)
