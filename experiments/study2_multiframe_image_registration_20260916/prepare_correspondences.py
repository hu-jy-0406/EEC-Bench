import argparse
import cv2
from common import *
p=argparse.ArgumentParser();p.add_argument('--method',choices=['sift','roma'],required=True);a=p.parse_args();owned_compute_job();cv2.setNumThreads(1)
source=RUN/a.method;dest=RUN/(a.method+'_geometry');dest.mkdir(exist_ok=True)
arrays={s:dict(np.load(OLD/'pi3x'/s/'geometry.npz')) for s in ['shot1','shot3']};cameras={s:{c['frame_id']:c for c in graph(s)['cameras']} for s in arrays};index={s:{f['frame_id']:i for i,f in enumerate(inputs(s)['frames'])} for s in arrays}

def lift(s,fid,uv):
 z=arrays[s];i=index[s][fid];h,w=z['depth'][i].shape
 x=(uv[:,0]*w/852).astype('float32');y=(uv[:,1]*h/480).astype('float32')
 local=cv2.remap(z['local_points'][i],x[:,None],y[:,None],cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)[:,0]
 conf=cv2.remap(z['confidence'][i],x[:,None],y[:,None],cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)[:,0]
 cam=cameras[s][fid];R=np.array(cam['R_world_from_camera']);t=np.array(cam['position_world']);world=local@R.T+t
 valid=np.isfinite(world).all(1)&(local[:,2]>1e-5)&(conf>=np.quantile(z['confidence'][i],.1))
 return world,valid
rows=[];diagnostics=[]
for f in sorted(source.glob('*.npz')):
 r=np.load(f);ia,ib=int(r['frame_a']),int(r['frame_b']);uvA,uvB=r['uvA'],r['uvB'];n=len(uvA)
 ga=lookup(structural_mask('shot1',ia),uvA);gb=lookup(structural_mask('shot3',ib),uvB)
 good=(ga>0)&(ga==gb)&(r['confidence']>=.2)&(r['cycle_pixels']<=3)
 keep=np.where(good)[0];d={'frame_a':ia,'frame_b':ib,'raw':n,'same_structural_region':int(((ga>0)&(ga==gb)).sum()),'confidence_and_cycle':len(keep),'groups':{str(g):int(((ga==g)&good).sum()) for g in [1,4,10,12]}}
 if len(keep):
  A,B=uvA[keep],uvB[keep];PA,va=lift('shot1',ia,A);PB,vb=lift('shot3',ib,B);v=va&vb
  for i in np.where(v)[0]:
   u1,u3=A[i],B[i];g=int(ga[keep[i]]);ta=(int(u1[0]//48),int(u1[1]//48));tb=(int(u3[0]//48),int(u3[1]//48));test=((ta[0]*17+ta[1]*31)%5==0 or (tb[0]*17+tb[1]*31)%5==0)
   rows.append([ia,ib,g,*u1,*u3,*PA[i],*PB[i],float(r['confidence'][keep[i]]),int(test),ta[0],ta[1],tb[0],tb[1]])
  d['lifted']=int(v.sum())
 else:d['lifted']=0
 diagnostics.append(d)
data=np.array(rows,dtype=float).reshape(-1,19)
np.savez_compressed(dest/'correspondences.npz',data=data)
save(dest/'schema.json',{'columns':['frame_a','frame_b','group','u_a','v_a','u_b','v_b','X_a','Y_a','Z_a','X_b','Y_b','Z_b','confidence','holdout','tile_ax','tile_ay','tile_bx','tile_by'],'rows':len(data),'pairs':len(diagnostics),'train':int((data[:,14]==0).sum()),'holdout':int((data[:,14]==1).sum()),'groups':{str(g):int((data[:,2]==g).sum()) for g in [1,4,10,12]},'filters':'same structural group, confidence>=.2, bidirectional cycle<=3px, own-shot geometry confidence>=10th percentile','raw_match_files':{str(p):sha(p) for p in source.glob('*.npz')}})
save(dest/'pair_diagnostics.json',diagnostics);print(read(dest/'schema.json')|{'raw_match_files':'omitted'},flush=True)
