import cv2
from common import *
owned_compute_job();cv2.setNumThreads(1);start=time.time()
frames={};cams={};arrays={};sources={};dest=RUN/'roma_geometry';dest.mkdir(parents=True,exist_ok=True)
for sid in ['shot1','shot3']:
 ip=OLD/'inputs'/f'{sid}.json';sp=OLD/'selected'/f'{sid}_scene.json';gp=OLD/'pi3x'/sid/'geometry.npz'
 inp=read(ip);scene=read(sp)
 snapshot={'shot_id':sid,'coordinate_system':scene['coordinate_system'],'cameras':scene['cameras'],'frames':inp['frames'],'image_sizes':inp['image_sizes']}
 save(RUN/'camera_inputs'/f'{sid}.json',snapshot)
 frames[sid]=snapshot;cams[sid]={c['frame_id']:c for c in snapshot['cameras']};arrays[sid]=dict(np.load(gp));sources.update({str(p):sha(p) for p in [ip,sp,gp]})
 for f in inp['frames']:assert sha(f['path'])==f['sha256'];sources[f['path']]=f['sha256']
index={s:{f['frame_id']:i for i,f in enumerate(frames[s]['frames'])} for s in frames}
def lift(s,fid,uv):
 z=arrays[s];i=index[s][fid];h,w=z['depth'][i].shape;W,H=frames[s]['image_sizes'][i]
 x=(uv[:,0]*w/W).astype('float32');y=(uv[:,1]*h/H).astype('float32')
 local=cv2.remap(z['local_points'][i],x[:,None],y[:,None],cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)[:,0]
 conf=cv2.remap(z['confidence'][i],x[:,None],y[:,None],cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)[:,0]
 cam=cams[s][fid];world=local@np.array(cam['R_world_from_camera']).T+np.array(cam['position_world'])
 valid=np.isfinite(world).all(1)&(local[:,2]>1e-5)&(conf>=np.quantile(z['confidence'][i],.1))
 return world,valid
rows=[];diagnostics=[]
files=sorted((OLD/'registration/roma').glob('*.npz'));assert len(files)==36
for f in files:
 r=np.load(f);ia,ib=int(r['frame_a']),int(r['frame_b']);A,B=r['uvA'],r['uvB'];good=(r['confidence']>=.2)&(r['cycle_pixels']<=3)
 keep=np.where(good)[0];a,b=A[keep],B[keep];P,va=lift('shot1',ia,a);Q,vb=lift('shot3',ib,b);v=va&vb
 for i in np.where(v)[0]:
  u1,u3=a[i],b[i];ta=(int(u1[0]//48),int(u1[1]//48));tb=(int(u3[0]//48),int(u3[1]//48));test=((ta[0]*17+ta[1]*31)%5==0 or (tb[0]*17+tb[1]*31)%5==0)
  rows.append([ia,ib,1,*u1,*u3,*P[i],*Q[i],float(r['confidence'][keep[i]]),int(test),*ta,*tb])
 diagnostics.append(dict(frame_a=ia,frame_b=ib,raw=len(A),confidence_and_cycle=len(keep),lifted=int(v.sum())));sources[str(f)]=sha(f)
 print(ia,ib,'lifted',int(v.sum()),flush=True)
d=np.array(rows,dtype=float).reshape(-1,19);np.savez_compressed(dest/'correspondences.npz',data=d)
save(dest/'schema.json',dict(rows=len(d),raw_points=sum(x['raw'] for x in diagnostics),train=int((d[:,14]==0).sum()),holdout=int((d[:,14]==1).sum()),group_column='constant 1; not an entity id',filters='confidence>=0.2, bidirectional match consistency<=3px, own-shot depth confidence>=10th percentile; NO entity masks or cross-shot identities',spatial_holdout='same fixed 48px tile predicate as baseline',raw_match_files={str(f):sha(f) for f in files}))
save(dest/'pair_diagnostics.json',diagnostics);save(RUN/'preparation_audit.json',dict(sources=sources,cross_shot_identity_read=False,entity_masks_used=False,source_raw_matcher='RoMaV2 precise; full-image model.match/sample; 5000 points per frame pair',reused_raw_pairs=36,new_model_calls=0,seconds=time.time()-start,allocation=os.environ['SLURM_JOB_ID']))
print('LIFT COMPLETE',len(d),flush=True)
