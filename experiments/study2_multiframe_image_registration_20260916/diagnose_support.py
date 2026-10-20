"""Post-fit diagnostics; never replace primary transform using relation outcomes."""
import cv2
from common import *
from register import Geometry,summary
from scipy.spatial.transform import Rotation
from scipy.optimize import least_squares
owned_compute_job();cv2.setNumThreads(1)

def simfit(Q,P):
 q,p=Q.mean(0),P.mean(0);X,Y=Q-q,P-p;U,S,Vt=np.linalg.svd(Y.T@X);D=np.eye(3);D[-1,-1]=np.linalg.det(U@Vt);R=U@D@Vt;s=np.sum(S*np.diag(D))/np.sum(X*X)
 if not .1<s<10:return None
 return np.r_[np.log(s),Rotation.from_matrix(R).as_rotvec(),p-s*R@q]
def error(x,G,flat=False):
 s=np.exp(x[0]);R=Rotation.from_rotvec(x[1:4]).as_matrix();t=x[4:7];pa=s*G.Q@R.T+t;pb=(G.P-t)@R/s;r=np.c_[G.project(pa,0)-G.uvA,G.project(pb,1)-G.uvB]
 return r.ravel() if flat else np.sqrt(np.sum(r*r,axis=1)/2)

results={}
for method in ['roma','sift']:
 d=np.load(RUN/(method+'_geometry')/'correspondences.npz')['data'];h=[]
 for ia,ib,g in sorted(set(map(tuple,d[:,0:3]))):
  sub=d[(d[:,0]==ia)&(d[:,1]==ib)&(d[:,2]==g)];tr=sub[sub[:,14]==0];te=sub[sub[:,14]==1]
  if len(tr)<6 or len(te)<2:continue
  H,mask=cv2.findHomography(tr[:,3:5],tr[:,5:7],cv2.RANSAC,3,maxIters=5000,confidence=.999)
  if H is None:continue
  pred=cv2.perspectiveTransform(te[:,3:5].astype('float64').reshape(-1,1,2),H)[:,0];e=np.linalg.norm(pred-te[:,5:7],axis=1)
  h.append({'frame_a':int(ia),'frame_b':int(ib),'group':int(g),'train_n':len(tr),'holdout_n':len(te),'holdout_median_2D_px':float(np.median(e)),'holdout_inlier_5px':float(np.mean(e<=5))})
 results[method]={'local_planar_homography':h,'free_rotation_sim3':{}}
 for group in ([None,4,12] if method=='roma' else [None]):
  tr=d[(d[:,14]==0)&((d[:,2]==group) if group else True)];G=Geometry(tr);rng=np.random.default_rng(734);candidates=[]
  x=simfit(G.Q,G.P)
  if x is not None:candidates.append(x)
  for _ in range(500):
   ix=rng.choice(len(tr),3,replace=False);x=simfit(G.Q[ix],G.P[ix])
   if x is not None:candidates.append(x)
  def key(x):e=error(x,G);return (np.mean(e<=5),-np.mean(np.minimum(e,50)))
  bests=sorted(candidates,key=key,reverse=True)[:4];refined=[]
  for x in bests:
   e=error(x,G);keep=e<=max(5,np.quantile(e,.15));sub=Geometry(tr[keep]);opt=least_squares(lambda v:error(v,sub,True),x,loss='soft_l1',f_scale=3,max_nfev=100,bounds=(np.r_[np.log(.1),[-np.inf]*6],np.r_[np.log(10),[np.inf]*6]));refined.append(opt.x)
  x=max(bests+refined,key=key);R=Rotation.from_rotvec(x[1:4]).as_matrix();e=error(x,Geometry(d));v={'scale':float(np.exp(x[0])),'rotation':R.tolist(),'translation':x[4:].tolist(),'up_axis_tilt_deg':float(np.degrees(np.arccos(np.clip(R[2,2],-1,1)))),'train':summary(tr,error(x,G)),'spatial_holdout':summary(d[d[:,14]==1],e[d[:,14]==1])};results[method]['free_rotation_sim3'][str(group)]=v;print(method,group,'tilt',v['up_axis_tilt_deg'],'heldout',v['spatial_holdout'],flush=True)
results['interpretation']='Exploratory diagnostics after primary failure. Homographies are per-region/per-frame, not one global 3D alignment. Free Sim3 abandons required shared gravity, so is not the selected scoring transform. Numerical consensus does not verify physical feature identities.'
save(RUN/'support_diagnostics.json',results)
