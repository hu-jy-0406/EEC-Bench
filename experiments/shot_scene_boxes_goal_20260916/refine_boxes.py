"""Single-shot multi-frame reprojection refinement with a frozen 3D model prior.
No cross-shot identities, alignment scores or known anomalies are read.
Full size/orientation priors limit monocular shrinkage and depth ambiguity.
"""
import argparse,copy,json,sys,time
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation
HERE=Path(__file__).resolve().parent;BASE=HERE.parents[1];sys.path.insert(0,str(BASE/'scripts'))
from build_three_method_static_scenes import corners,projection_iou
from run_isolated_shot_static_3d import owned_compute_job

def read(p):return json.loads(p.read_text())
def refine(box,rows,cameras):
 C=np.array(box['center_world']);S=np.array(box['size_xyz']);R=np.array(box['R_world_from_object']);diag=np.linalg.norm(S)
 eligible=[r for r in rows if r.get('visible') and r.get('box_xyxy') is not None and r.get('projection_iou',0)>0]
 if not eligible:return box,{'status':'unchanged_no_eligible_observation'}
 areas=np.array([np.prod(np.array(r['box_xyxy'])[2:]-np.array(r['box_xyxy'])[:2]) for r in eligible])
 # Prefer full-looking observations within this entity's own shot. Never use cross-shot residuals.
 eligible=[r for r,a in zip(eligible,areas) if a>=.8*max(areas)]
 def unpack(x):
  g={'center_world':(C+x[:3]*diag).tolist(),'size_xyz':(S*np.exp(x[3:6])).tolist(),'R_world_from_object':(Rotation.from_euler('z',x[6]).as_matrix()@R).tolist()}
  return g
 def residual(x):
  pts=corners(unpack(x));out=[]
  for row in eligible:
   cam=cameras[row['frame_id']];q=(pts-np.array(cam['position_world']))@np.array(cam['R_world_from_camera']);uv=q@np.array(cam['K']).T;uv=uv[:,:2]/np.maximum(uv[:,2:],1e-5)
   pred=np.r_[uv.min(0),uv.max(0)];target=np.array(row['box_xyxy']);W,H=cam['image_size'];wh=np.maximum(target[2:]-target[:2],4)
   pred[[0,2]]=np.clip(pred[[0,2]],0,W);pred[[1,3]]=np.clip(pred[[1,3]],0,H)
   # A tight projected enclosure approximates the supplied complete-object 2D prompt.
   out.extend((pred-target)/np.tile(wh,2)/np.sqrt(len(eligible)))
  # Model prior: characteristic tolerance .25 diagonal position, 30% size, 20deg yaw.
  out.extend(.2*x[:3]/.25);out.extend(.2*x[3:6]/np.log(1.3));out.append(.2*x[6]/np.deg2rad(20))
  return np.array(out)
 lo=np.r_[[-.5]*3,[np.log(.6)]*3,-np.deg2rad(35)];hi=np.r_[[.5]*3,[np.log(1.6)]*3,np.deg2rad(35)]
 x0=np.zeros(7);fit=least_squares(residual,x0,bounds=(lo,hi),loss='soft_l1',f_scale=.2,max_nfev=160,xtol=1e-8,ftol=1e-8,gtol=1e-8)
 g=unpack(fit.x);g['corners_world']=corners(g).tolist()
 iou=lambda b:float(np.mean([projection_iou(b,cameras[r['frame_id']],r['box_xyxy'],cameras[r['frame_id']]['image_size']) for r in eligible]))
 before,after=iou(box),iou(g)
 if after<before:g=box
 return g,dict(status='refined' if after>=before else 'kept_prior_projection_worsened',success=bool(fit.success),nfev=fit.nfev,frame_ids=[r['frame_id'] for r in eligible],before_iou=before,after_iou=after,parameter_delta=fit.x.tolist(),cost=float(fit.cost),uses_cross_shot=False)

def main():
 p=argparse.ArgumentParser();p.add_argument('--method',default='pi3x');p.add_argument('--shot',required=True,choices=['shot1','shot3']);a=p.parse_args();job=owned_compute_job();start=time.time()
 root=HERE/a.method/a.shot;g=read(root/'boxer_depth/scene_graph.json');out=root/'boxer_refined';out.mkdir(exist_ok=True)
 if (out/'complete.json').exists():raise RuntimeError('Completed output exists')
 cameras={c['frame_id']:c for c in g['cameras']}
 for e in g['entities']:
  prior=copy.deepcopy(e['geometry'])
  if e['motion_status']=='static':e['geometry'],info=refine(prior,e['frame_evidence'],cameras)
  else:
   for row in e['frame_evidence']:
    if row.get('geometry'):row['geometry'],row['refinement']=refine(row['geometry'],[row],cameras)
   fid=e['aggregation']['frame_id'];selected=next(r for r in e['frame_evidence'] if r['frame_id']==fid);e['geometry']=selected['geometry'];info=selected.get('refinement',{})
  e['model_prior_geometry']=prior;e['refinement']=info
  e['fused_projection_mean_iou']=float(np.mean([projection_iou(e['geometry'],cameras[r['frame_id']],r['box_xyxy'],cameras[r['frame_id']]['image_size']) for r in e['frame_evidence'] if r['visible'] and r['box_xyxy'] is not None]))
  print(a.shot,e['entity_id'],info.get('before_iou'),info.get('after_iou'),flush=True)
 g['method']=a.method+'_boxer_refined';g['limitations'].append('Reprojection refinement uses same-shot 2D prompts with bounded Boxer priors; cannot establish true depth or hidden extent.')
 (out/'scene_graph.json').write_text(json.dumps(g,indent=2,allow_nan=False)+'\n')
 base=read(root/'boxer_depth/complete.json');base.update(seconds=base['seconds']+time.time()-start,refinement_seconds=time.time()-start,refinement_allocation=job)
 (out/'complete.json').write_text(json.dumps(base,indent=2)+'\n')
if __name__=='__main__':main()
