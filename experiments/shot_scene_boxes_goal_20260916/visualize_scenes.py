"""Standalone diagnostic plots from actual output geometry (no new inference)."""
import argparse,itertools,json,sys
from pathlib import Path
import numpy as np
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image
HERE=Path(__file__).resolve().parent;BASE=HERE.parents[1];sys.path.insert(0,str(BASE/'scripts'))
from robust_box_registration import corners,transform
from run_isolated_shot_static_3d import owned_compute_job

def read(p):return json.loads(p.read_text())
def main():
 p=argparse.ArgumentParser();p.add_argument('--method',default='pi3x');p.add_argument('--variant',default='boxer_depth');a=p.parse_args();owned_compute_job()
 out=HERE/a.method/'visuals';out.mkdir(exist_ok=True)
 signs=np.array(list(itertools.product([-1,1],repeat=3)));edges=[(i,j) for i in range(8) for j in range(i+1,8) if np.sum(signs[i]!=signs[j])==1]
 graphs=[read(HERE/a.method/s/a.variant/'scene_graph.json') for s in ['shot1','shot3']]
 rows=read(HERE/f'comparison_{a.variant}.json');fit=rows[a.method+'_'+a.variant]
 R=np.array(fit['rotation']);t=np.array(fit['translation']);scale=fit['scale']
 colors=['#2368b5','#d67523'];allpoints=[]
 fig=plt.figure(figsize=(15,11));axs=[fig.add_subplot(221,projection='3d'),fig.add_subplot(222),fig.add_subplot(223),fig.add_subplot(224)]
 for sid,(g,color) in enumerate(zip(graphs,colors)):
  for e in g['entities']:
   pts=corners(e['geometry']);pts=transform(pts,(scale,R,t)) if sid else pts;allpoints.append(pts)
   for i,j in edges:
    q=pts[[i,j]];axs[0].plot(*q.T,color=color,alpha=.65,lw=.75,ls='-' if not sid else '--')
    for ax,(x,y) in zip(axs[1:],[(0,1),(0,2),(1,2)]):ax.plot(q[:,x],q[:,y],color=color,alpha=.55,lw=.7)
   c=pts.mean(0);label=e['entity_id'].replace('shot','S')
   for ax,(x,y) in zip(axs[1:],[(0,1),(0,2),(1,2)]):ax.text(c[x],c[y],label,fontsize=6,color=color)
  cams=np.array([c['position_world'] for c in g['cameras']]);cams=transform(cams,(scale,R,t)) if sid else cams
  axs[0].plot(*cams.T,color=color,marker='^',markersize=5)
 allpoints=np.concatenate(allpoints);lo=allpoints.min(0);hi=allpoints.max(0);axs[0].set_box_aspect(hi-lo)
 for ax,(x,y),name in zip(axs[1:],[(0,1),(0,2),(1,2)],['Top XY','Front XZ','Side YZ']):ax.set_aspect('equal');ax.set_title(name);ax.set_xlabel('XYZ'[x]);ax.set_ylabel('XYZ'[y]);ax.grid(alpha=.2)
 axs[0].set(xlabel='X',ylabel='Y',zlabel='Z',title='All 41 boxes; fixed Shot1 scene frame')
 fig.suptitle(f'{a.method} / {a.variant}: blue Shot1, orange Shot3\n11 static correspondences, plain corner-MSE fit; normalized MSE={fit["normalized_mse"]:.6f}; estimated alignment',fontsize=12)
 fig.tight_layout();fig.savefig(out/f'{a.variant}_aligned.png',dpi=170);fig.savefig(out/f'{a.variant}_aligned.pdf');fig.savefig(out/f'{a.variant}_aligned_preview.jpg',dpi=90);plt.close(fig)
 for s,g in zip(['shot1','shot3'],graphs):
  source=read(HERE/'inputs'/f'{s}.json');fig,axs=plt.subplots(2,3,figsize=(20,8));lookup={e['entity_id']:e for e in source['entities']}
  for ax,frame,cam in zip(axs.flat,source['frames'],g['cameras']):
   ax.imshow(Image.open(frame['path']));K=np.array(cam['K']);Rc=np.array(cam['R_world_from_camera']);pos=np.array(cam['position_world'])
   for e in g['entities']:
    obs=next(f for f in e['frame_evidence'] if f['frame_id']==frame['frame_id'])
    if not obs['visible'] or 'geometry' not in obs:continue
    box=e['geometry'] if e['motion_status']=='static' else obs['geometry'];q=(corners(box)-pos)@Rc
    if (q[:,2]<=0).any():continue
    uv=q@K.T;uv=uv[:,:2]/uv[:,2:]
    color='#00e5ff' if e['motion_status']=='static' else '#ffca28'
    for i,j in edges:ax.plot(uv[[i,j],0],uv[[i,j],1],color=color,lw=.55,alpha=.8)
    c=uv.mean(0);ax.text(*c,e['entity_id'].split('/')[-1],fontsize=7,color='black',bbox={'facecolor':'white','alpha':.65,'pad':.5,'edgecolor':'none'})
   W,H=cam['image_size'];ax.set_xlim(0,W);ax.set_ylim(H,0);ax.set_title(f'{s} frame {frame["frame_id"]}');ax.axis('off')
  fig.suptitle(f'{a.method}: cyan = fixed static box; yellow = moving entity frame box. Predictions projected to unchanged original JPEGs.')
  fig.tight_layout();fig.savefig(out/f'{a.variant}_{s}_projections.png',dpi=150);fig.savefig(out/f'{a.variant}_{s}_projections_preview.jpg',dpi=90);plt.close(fig)
 print(out)
if __name__=='__main__':main()
