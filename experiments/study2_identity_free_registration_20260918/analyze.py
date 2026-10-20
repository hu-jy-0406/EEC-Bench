"""Post-fit evaluation only: identities/boxes never feed the registration solver."""
import os,json,hashlib,copy,csv,itertools,time
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR','/tmp/eec-identityfree-mpl')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import plotly.graph_objects as go
H=Path(__file__).resolve().parent;B=H.parents[1];OLD=B/'experiments/study012_two_scores_20260916/study2';RUN=H/'run01'
def read(p):return json.loads(p.read_text())
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
newpath=RUN/'roma_geometry/registration.json';newhash=sha(newpath);new=read(newpath)['fits']['full_image'];old=read(OLD/'registration/roma_geometry/registration.json')['fits']['all_structures'];fits={'old':old,'identity_free':new}
cams={s:{c['frame_id']:c for c in read(RUN/'camera_inputs'/f'{s}.json')['cameras']} for s in ['shot1','shot3']}
def error(d,f):
 s=f['scale'];R=np.array(f['rotation']);t=np.array(f['translation']);P,Q=d[:,7:10],d[:,10:13]
 out=[]
 for side,points in [(0,s*Q@R.T+t),(1,(P-t)@R/s)]:
  cs=[cams[['shot1','shot3'][side]][int(fid)] for fid in d[:,side]];rots=np.array([c['R_world_from_camera'] for c in cs]);pos=np.array([c['position_world'] for c in cs]);K=np.array([c['K'] for c in cs])
  local=np.einsum('ni,nij->nj',points-pos,rots);uv=np.einsum('nij,nj->ni',K,local);uv=uv[:,:2]/np.maximum(local[:,2:],1e-4);uv[local[:,2]<=0]=1e5;out.append(uv-d[:,3+2*side:5+2*side])
 return np.sqrt(np.mean(np.stack(out,1)**2,axis=(1,2))*2)
def stats(e):return dict(n=len(e),median_pixels=float(np.median(e)),p90_pixels=float(np.quantile(e,.9)),inlier_5px=float(np.mean(e<=5)))
d=np.load(RUN/'roma_geometry/correspondences.npz')['data'];od=np.load(OLD/'registration/roma_geometry/correspondences.npz')['data'];m=d[:,14]==1;om=od[:,14]==1
errors={k:error(d,f) for k,f in fits.items()};oe={k:error(od,f) for k,f in fits.items()}
metrics={k:dict(full_image_holdout=stats(errors[k][m]),original_structure_holdout=stats(oe[k][om]),original_structure_groups={str(int(g)):stats(oe[k][om&(od[:,2]==g)]) for g in np.unique(od[om,2])}) for k in fits}
assert np.isclose(metrics['identity_free']['full_image_holdout']['median_pixels'],new['spatial_holdout']['median_pixels'])
# Freeze transformed boxes after transform selection; these are output diagnostics only.
scenes={s:read(OLD/'selected'/f'{s}_scene.json') for s in ['shot1','shot3']}
S=np.array(list(itertools.product([-1,1],repeat=3)));edges=[(i,j) for i in range(8) for j in range(i+1,8) if bin(i^j).count('1')==1]
def corners(g):return (S*np.array(g['size_xyz'])/2)@np.array(g['R_world_from_object']).T+np.array(g['center_world'])
aligned={}
for k,f in fits.items():
 aligned[k]={}
 for sid,scene in scenes.items():
  es=[]
  for e in scene['entities']:
   ee={a:copy.deepcopy(e[a]) for a in ['entity_id','name','motion_status','geometry']};g=ee['geometry']
   if sid=='shot3':
    s=f['scale'];R=np.array(f['rotation']);t=np.array(f['translation']);g['center_world']=(s*R@np.array(g['center_world'])+t).tolist();g['size_xyz']=(s*np.array(g['size_xyz'])).tolist();g['R_world_from_object']=(R@np.array(g['R_world_from_object'])).tolist()
   g['corners_world']=corners(g).tolist();es.append(ee)
  aligned[k][sid]=es
save(RUN/'aligned_entities.json',dict(frame='fixed Shot1 scene, Z-up',transform=new,shots=[dict(shot_id=s,entities=e) for s,e in aligned['identity_free'].items()],identity_used_for_transform=False))
groups=read(OLD/'matching.json')['groups'];groups={g['group_id']:g for g in groups};indexes={k:{e['entity_id']:e for es in sh.values() for e in es} for k,sh in aligned.items()}
rows=[]
for r in read(OLD/'all_pair_cosines.json'):
 out={'relation_id':r['relation_id'],'endpoint_groups':r['endpoint_groups'],'identity_warning':'g16 rejected by user; g17 and g01 require identity recheck' if set(r['endpoint_groups'])&{'g16','g17','g01'} else ''}
 for k in fits:
  vec=[]
  for sid,side in [('shot1','a'),('shot3','b')]:
   a,b=[np.array(indexes[k][groups[g][side+'_ids'][0]]['geometry']['center_world']) for g in r['endpoint_groups']];vec.append(b-a)
  co=float(vec[0]@vec[1]/np.prod([np.linalg.norm(v) for v in vec]));out[k+'_cosine']=co
  if k=='old':assert np.isclose(co,r['cosine'])
 rows.append(out)
with (RUN/'pair_cosines_comparison.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
center_errors={}
for gid in ['g01','g02','g04','g06','g07','g10','g11','g12','g16','g17']:
 a,b=groups[gid]['a_ids'][0],groups[gid]['b_ids'][0];center_errors[gid]={'entity':indexes['old'][a]['name']}
 for k in fits:center_errors[gid][k]=float(np.linalg.norm(np.array(indexes[k][a]['geometry']['center_world'])-np.array(indexes[k][b]['geometry']['center_world'])))
res=dict(old_transform={k:old[k] for k in ['scale','yaw_deg','translation','rotation']},new_transform={k:new[k] for k in ['scale','yaw_deg','translation','rotation']},same_population_metrics=metrics,center_displacements=center_errors,negative_counts={k:sum(r[k+'_cosine']<0 for r in rows) for k in fits},pair_cosines=rows,caution='Full-image heldout matches are not verified physical correspondences. Identity warnings remain; no new consistency score.',new_model_calls=0)
save(RUN/'comparison.json',res)
# Equal-coordinate-scale overlays, all static entities. Focus labels are post-fit only.
colors={'shot1':'#1769ba','shot3':'#df6b17'};focus={'shot1/e5':'Desk','shot3/e7':'Desk','shot1/e14':'Radiator','shot3/e18':'Radiator','shot1/e11':'Rug','shot3/e15':'Rug'}
allpoints=np.concatenate([corners(e['geometry']) for k in fits for es in aligned[k].values() for e in es if e['motion_status']=='static']);lo=allpoints.min(0);hi=allpoints.max(0);pad=(hi-lo)*.05;lo-=pad;hi+=pad
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10})
fig=plt.figure(figsize=(16,12));gs=fig.add_gridspec(2,2,left=.04,right=.97,bottom=.06,top=.89,wspace=.15,hspace=.12)
for col,k in enumerate(fits):
 for row in range(2):
  ax=fig.add_subplot(gs[row,col],projection='3d' if row==0 else None)
  for sid,es in aligned[k].items():
   for e in es:
    if e['motion_status']!='static':continue
    c=corners(e['geometry']);target=e['entity_id'] in focus
    for i,j in edges:
     p=c[[i,j]];ax.plot(*(p.T if row==0 else p[:,:2].T),c=colors[sid],lw=1.7 if target else .6,alpha=.95 if target else .18)
    if target and focus[e['entity_id']]!='Rug':
     p=np.array(e['geometry']['center_world']);label='S'+sid[-1]+' '+focus[e['entity_id']]
     if row==0:ax.text(*(p+[0,0,.18 if sid=='shot1' else -.2]),label,c=colors[sid],fontsize=9)
     else:ax.annotate(label,p[:2],xytext=(8,10 if sid=='shot1' else -18),textcoords='offset points',c=colors[sid],fontsize=9,bbox=dict(fc='white',ec='none',alpha=.7))
  ax.set_xlim(lo[0],hi[0]);ax.set_ylim(lo[1],hi[1]);ax.set_xlabel('X');ax.set_ylabel('Y');ax.grid(alpha=.15)
  if row==0:ax.set_zlim(lo[2],hi[2]);ax.set_zlabel('Z (up)');ax.set_box_aspect(hi-lo);ax.view_init(elev=30,azim=-60);ax.set_proj_type('ortho');ax.set_title(('Original: identity-filtered' if k=='old' else 'New: identity-free full image')+f'\nyaw={fits[k]["yaw_deg"]:.2f}°, scale={fits[k]["scale"]:.4f}',fontsize=14,weight='bold')
  else:ax.set_aspect('equal');ax.set_title('Top view (XY)',fontsize=11)
fig.suptitle('Study2 | same boxes, different registration inputs',fontsize=20,weight='bold',y=.98)
fig.legend(handles=[Line2D([0],[0],color=c,lw=3,label=s.replace('shot','Shot ')) for s,c in colors.items()],loc='upper center',bbox_to_anchor=(.5,.958),ncol=2,frameon=False)
fig.text(.5,.015,'Fixed Shot1 scene, identical axis ranges. All 38 static boxes shown; desk, rug and radiator highlighted. Model units, not calibrated metres.',ha='center',fontsize=11)
fig.savefig(RUN/'overlay_comparison.png',dpi=150);fig.savefig(RUN/'overlay_comparison.jpg',dpi=110,pil_kwargs={'quality':90});plt.close(fig)
# New alignment standalone interactive scene with identities only as hover labels.
tr=[]
for sid,es in aligned['identity_free'].items():
 for e in es:
  if e['motion_status']!='static':continue
  c=corners(e['geometry']);xyz=[[],[],[]]
  for i,j in edges:
   for dim in range(3):xyz[dim].extend([c[i,dim],c[j,dim],None])
  name=sid+' '+e['entity_id']+': '+e['name'];tr.append(go.Scatter3d(x=xyz[0],y=xyz[1],z=xyz[2],mode='lines',line=dict(color=colors[sid],width=4 if e['entity_id'] in focus else 2),opacity=1 if e['entity_id'] in focus else .45,name=name,hovertemplate=name+'<extra></extra>',showlegend=False))
fig=go.Figure(tr);fig.update_layout(title='Study2 · 不使用跨shot身份的配准结果｜蓝色Shot1，橙色Shot3',scene=dict(aspectmode='data',xaxis_title='X',yaxis_title='Y',zaxis_title='Z（向上）'),height=900);fig.write_html(RUN/'interactive.html',include_plotlyjs=True)
# Raw image-space support scatter, both fits on exactly the same matches.
fig,axes=plt.subplots(2,2,figsize=(15,9));frames=[(s,fid) for s,fid in [('shot1',120),('shot3',0)]]
for col,(sid,fid) in enumerate(frames):
 fp=next(f['path'] for f in read(RUN/'camera_inputs'/f'{sid}.json')['frames'] if f['frame_id']==fid);im=plt.imread(fp)
 for row,k in enumerate(fits):
  ax=axes[row,col];ax.imshow(im);ix=np.where((d[:,0]==120)&(d[:,1]==0))[0];ok=errors[k][ix]<=5;uv=d[ix,3:5] if sid=='shot1' else d[ix,5:7]
  ax.scatter(*uv[~ok].T,s=5,c='#df6b17',alpha=.4);ax.scatter(*uv[ok].T,s=10,c='#17b882',alpha=.8);ax.axis('off');ax.set_title(k+' | '+sid+f' | inliers {int(ok.sum())}/{len(ok)}')
fig.suptitle('Same frame-pair RoMa correspondences: green <=5px, orange >5px',fontsize=16);fig.tight_layout();fig.savefig(RUN/'match_support.jpg',dpi=120,pil_kwargs={'quality':90});plt.close(fig)
assert sha(newpath)==newhash
prep=read(RUN/'preparation_audit.json');unchanged=all(sha(Path(p))==v for p,v in prep['sources'].items());assert unchanged
save(RUN/'final_audit.json',dict(passed=True,sources_unchanged=unchanged,new_fit_frozen_during_analysis=True,old_pair_cosines_replayed=True,same_population_errors_replayed=True,all_static_boxes=38,new_model_calls=0,registration_identity_independent=True,postfit_only_identity_diagnostics=True,code_hashes={str(p):sha(p) for p in H.glob('*.py')}))
print(json.dumps({k:res[k] for k in ['old_transform','new_transform','same_population_metrics','center_displacements','negative_counts']},indent=2),flush=True)
