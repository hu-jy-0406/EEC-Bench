"""Fit a frozen scene-to-scene transform from image correspondences only."""
import argparse,time
from scipy.optimize import least_squares
from common import *

def rz(a):c,s=np.cos(a),np.sin(a);return np.array([[c,-s,0],[s,c,0],[0,0,1.]])
def params(x):return np.exp(x[0]),rz(x[1]),x[2:5]
def ls_seed(A,B,w=None):
 w=np.ones(len(A)) if w is None else w;w=w/w.sum();ma=w@A;mb=w@B;X=A-ma;Y=B-mb
 aa=np.sum(w*(X[:,0]*Y[:,0]+X[:,1]*Y[:,1]));bb=np.sum(w*(X[:,0]*Y[:,1]-X[:,1]*Y[:,0]));angle=np.arctan2(bb,aa);R=rz(angle);den=np.sum(w*np.sum(X*X,1))
 if den<1e-10:return None
 s=np.sum(w*np.sum((X@R.T)*Y,1))/den
 if not .1<s<10:return None
 return np.r_[np.log(s),angle,mb-s*R@ma]

def balanced_weights(d):
 _,inv,counts=np.unique(d[:,[0,1,2,15,16,17,18]],axis=0,return_inverse=True,return_counts=True);w=1/counts[inv]
 for g in np.unique(d[:,2]):w[d[:,2]==g]/=w[d[:,2]==g].sum()
 return w/w.sum()

class Geometry:
 def __init__(self,d):
  self.d=d;self.P=d[:,7:10];self.Q=d[:,10:13];self.uvA=d[:,3:5];self.uvB=d[:,5:7]
  cams=[{c['frame_id']:c for c in graph(s)['cameras']} for s in ['shot1','shot3']]
  for side in range(2):
   cs=[cams[side][int(i)] for i in d[:,side]]
   setattr(self,'R'+str(side),np.array([c['R_world_from_camera'] for c in cs]));setattr(self,'t'+str(side),np.array([c['position_world'] for c in cs]));setattr(self,'K'+str(side),np.array([c['K'] for c in cs]))
 def project(self,P,side):
  c=np.einsum('ni,nij->nj',P-getattr(self,'t'+str(side)),getattr(self,'R'+str(side)));uv=np.einsum('nij,nj->ni',getattr(self,'K'+str(side)),c);uv=uv[:,:2]/np.maximum(c[:,2:],1e-4);uv[c[:,2]<=0]=1e5;return uv
 def residual(self,x):
  s,R,t=params(x);pa=s*self.Q@R.T+t;pb=(self.P-t)@R/s
  return np.c_[self.project(pa,0)-self.uvA,self.project(pb,1)-self.uvB]
 def error(self,x):return np.sqrt(np.mean(self.residual(x).reshape(-1,2,2)**2,axis=(1,2))*2)

def summary(d,error):
 if len(d)==0:return {'n':0}
 w=balanced_weights(d)
 return {'n':len(d),'median_pixels':float(np.median(error)),'mean_pixels':float(np.mean(error)),'p90_pixels':float(np.quantile(error,.9)),'inlier_5px':float(np.mean(error<=5)),'balanced_inlier_5px':float(w@(error<=5)),
  'by_group':{str(int(g)):{'n':int((d[:,2]==g).sum()),'median_px':float(np.median(error[d[:,2]==g])),'inlier_fraction_5px':float(np.mean(error[d[:,2]==g]<=5))} for g in np.unique(d[:,2])}}

def fit(d,seed=731,iterations=1200):
 if len(d)<6:return None
 rng=np.random.default_rng(seed);w=balanced_weights(d);G=Geometry(d);candidates=[]
 c=ls_seed(G.Q,G.P,w)
 if c is not None:candidates.append(c)
 for g in np.unique(d[:,2]):
  m=d[:,2]==g;c=ls_seed(G.Q[m],G.P[m])
  if c is not None:candidates.append(c)
 for _ in range(iterations):
  ix=rng.choice(len(d),3,replace=False,p=w);c=ls_seed(G.Q[ix],G.P[ix])
  if c is not None:candidates.append(c)
 def key(x):e=G.error(x);return (float(w@(e<=5)),float(-w@np.minimum(e,50)))
 scored=sorted([(key(x),x) for x in candidates],key=lambda q:q[0],reverse=True)
 if not scored:return None
 results=[]
 for _,x in scored[:8]:
  cur=x.copy()
  for repeat in range(2):
   e=G.error(cur);keep=e<=max(5,float(np.quantile(e,.15)))
   if keep.sum()<6:break
   sub=Geometry(d[keep]);weights=balanced_weights(d[keep]);weights=np.sqrt(weights*len(weights))
   def residual(v):return (sub.residual(v)*weights[:,None]).ravel()
   opt=least_squares(residual,cur,loss='soft_l1',f_scale=3,max_nfev=120,bounds=(np.r_[np.log(.1),-np.inf,[-np.inf]*3],np.r_[np.log(10),np.inf,[np.inf]*3]))
   if key(opt.x)>=key(cur):cur=opt.x
   else:break
  results.append(cur)
 results.extend(x for _,x in scored[:8]);best=max(results,key=key)
 return best

def main():
 p=argparse.ArgumentParser();p.add_argument('--method',required=True,choices=['roma','sift']);a=p.parse_args();job=owned_compute_job();start=time.time();root=RUN/(a.method+'_geometry');d=np.load(root/'correspondences.npz')['data'];train=d[:,14]==0;test=~train
 fits={};masks={'full_image':train}
 ia={v:i for i,v in enumerate(sorted(set(d[:,0])))};ib={v:i for i,v in enumerate(sorted(set(d[:,1])))}
 evenA=np.array([ia[v]%2==0 for v in d[:,0]],dtype=bool);evenB=np.array([ib[v]%2==0 for v in d[:,1]],dtype=bool)
 masks['even_frames']=train&evenA&evenB;masks['odd_frames']=train&~evenA&~evenB
 for name,mask in masks.items():
  x=fit(d[mask],iterations=1600 if name=='full_image' else 500)
  if x is None:fits[name]={'status':'insufficient_support','n':int(mask.sum())};continue
  s,R,t=params(x);e=Geometry(d).error(x);r={'status':'numeric_candidate','scale':float(s),'yaw_deg':float((np.degrees(x[1])+180)%360-180),'rotation':R.tolist(),'translation':t.tolist(),'fit_rows':int(mask.sum()),'train':summary(d[mask],e[mask]),'spatial_holdout':summary(d[test],e[test]),'all_correspondences':summary(d,e),'parameters':x.tolist()};fits[name]=r
  print(a.method,name,'yaw',r['yaw_deg'],'scale',s,'train',r['train']['median_pixels'],'holdout',r['spatial_holdout'].get('median_pixels'),'groups',r['spatial_holdout'].get('by_group'),flush=True)
 r={'method':a.method,'selection':'identity-free full-image training consensus; no identity/box mask access; constant group=1 with frame-pair/tile balancing','fits':fits,'allocation':job,'seconds':time.time()-start,'correspondences_sha256':sha(root/'correspondences.npz'),'transform_model':'one gravity-constrained positive similarity; robust symmetric per-frame reprojection refinement','support_warning':'spatial and temporal frame data are correlated; numeric inliers alone do not establish physical feature identity'};save(root/'registration.json',r)
if __name__=='__main__':main()
