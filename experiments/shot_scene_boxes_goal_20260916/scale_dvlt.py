"""Give relative-scale DVLT one same-shot DA3 metric scale before Boxer."""
import argparse,json,sys,time
from pathlib import Path
import cv2,numpy as np
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parents[1]/'scripts'))
from run_isolated_shot_static_3d import owned_compute_job
p=argparse.ArgumentParser();p.add_argument('--shot',required=True,choices=['shot1','shot3']);a=p.parse_args();job=owned_compute_job()
source=HERE/'dvlt'/a.shot;dest=HERE/'dvlt_metric'/a.shot;dest.mkdir(parents=True,exist_ok=True)
if (dest/'complete.json').exists():raise RuntimeError('Already completed')
meta=json.loads((source/'complete.json').read_text());ref=json.loads((HERE/'da3nested'/a.shot/'complete.json').read_text())
start=time.time();src=dict(np.load(source/'geometry.npz'));target=np.load(HERE/'da3nested'/a.shot/'geometry.npz');ratios=[];per=[]
for i,c in enumerate(meta['cameras']):
 W,H=c['image_size'];rescale=504/max(W,H);rw,rh=round(W*rescale),round(H*rescale);h,w=src['depth'][i].shape;top,left=(rh-h)//2,(rw-w)//2
 z=cv2.resize(target['depth'][i],(rw,rh),interpolation=cv2.INTER_LINEAR)[top:top+h,left:left+w]
 q=cv2.resize(target['confidence'][i],(rw,rh),interpolation=cv2.INTER_LINEAR)[top:top+h,left:left+w]
 d=src['depth'][i];conf=src['confidence'][i];valid=np.isfinite(z)&np.isfinite(d)&(z>0)&(d>0)&(q>=np.median(q))&(conf>=np.median(conf))
 r=z[valid]/d[valid];ratios.append(r);per.append(float(np.median(r)))
scale=float(np.median(np.concatenate(ratios)))
for key in ['depth','local_points','world_points']:src[key]=src[key]*scale
for key in ['camera_to_scene','raw_camera_to_world']:src[key]=src[key].copy();src[key][:,:3,3]*=scale
np.savez_compressed(dest/'geometry.npz',**src)
meta.update(method='dvlt_metric',scene_frame_id=a.shot+'/dvlt_metric_scene',scale='DVLT relative reconstruction with one same-shot DA3nested metric-depth median scale; not GT',metric_scale_factor=scale,per_frame_ratio_diagnostics=per,metric_reference=str(HERE/'da3nested'/a.shot/'complete.json'),seconds=meta['seconds']+ref['seconds']+time.time()-start,scale_calibration_allocation=job)
meta['scene_origin_raw']=(np.array(meta['scene_origin_raw'])*scale).tolist();meta['camera_position_range']=(np.array(meta['camera_position_range'])*scale).tolist()
for c in meta['cameras']:
 t=np.array(c['camera_to_scene']);t[:3,3]*=scale;c['camera_to_scene']=t.tolist()
(dest/'complete.json').write_text(json.dumps(meta,indent=2)+'\n');print(a.shot,'same-shot scale',scale,'perframe',per)
