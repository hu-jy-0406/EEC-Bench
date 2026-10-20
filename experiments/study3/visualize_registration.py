"""Read-only visualization of the frozen Study3 registration; no refitting."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parent
CASE = ROOT / 'run_cpu02'
OUT = ROOT / 'registration_visualization'
OUT.mkdir(exist_ok=True)
read = lambda p: json.loads(p.read_text())
p = read(CASE / 'identity_review_payload.json')
m = read(CASE / 'matching.json')
fit = p['frozen_transform']
lookup = {e['entity_id']: e for s in p['shots'] for e in s['entities']}
groups = {g['group_id']: g for g in m['groups']}
edges = [(i,j) for i in range(8) for j in range(i+1,8) if (i^j).bit_count()==1]
colors = ['#1769ba', '#df6b17']
names = {'g02':'Mug','g03':'Lamp','g05':'Desk','g07':'Pencil cup','g09':'Window plant','g12':'Rug','g14':'Chair','g15':'Radiator','g17':'Window pot'}
plt.rcParams.update({'font.size':11, 'axes.spines.top':False,'axes.spines.right':False})
fig,axs = plt.subplots(1,2,figsize=(14,7),gridspec_kw={'width_ratios':[1.15,1]})
ax=axs[0]
for gid in names:
 g=groups[gid]; xy=[]
 for side,eid in enumerate(g['a_ids']+g['b_ids']):
  b=lookup[eid]['aligned_geometry'];c=np.array(b['center_world']);xy.append(c[:2])
  ax.scatter(*c[:2],c=colors[side],s=45,zorder=4)
  if gid in ['g03','g05','g15']:
   corners=np.array(b['corners_world'])
   for i,j in edges:ax.plot(*corners[[i,j],:2].T,color=colors[side],alpha=.45,lw=1)
   offsets={'g03':[(6,-17),(6,8)],'g05':[(8,3),(8,-20)],'g15':[(-85,12),(-85,-16)]}
   ax.annotate(f'{names[gid]} S{1 if side==0 else 3}',c[:2],xytext=offsets[gid][side],textcoords='offset points',color=colors[side],fontsize=10)
 ax.plot(*np.array(xy).T,color='#777777',ls='--',lw=1,alpha=.6)
ax.set_aspect('equal');ax.set_xlim(-1.8,2.1);ax.set_ylim(-1.65,2.45)
ax.set_xlabel('X / Shot1 model units');ax.set_ylabel('Y / Shot1 model units')
ax.set_title('Top view: final matched static entities\nBoxes shown for desk, lamp and radiator')
ax.grid(alpha=.15)
ax.legend(handles=[Line2D([0],[0],color=colors[i],marker='o',label=s) for i,s in enumerate(['Shot1','Shot3 transformed'])],loc='lower left')
dist=[]
for gid,name in names.items():
 g=groups[gid];a,b=[np.array(lookup[e]['aligned_geometry']['center_world']) for e in g['a_ids']+g['b_ids']];dist.append((gid,name,float(np.linalg.norm(a-b))))
dist.sort(key=lambda x:x[2]);ax=axs[1]
ax.barh([x[1] for x in dist],[x[2] for x in dist],color=['#dd8833' if x[0]=='g03' else '#4c7393' for x in dist])
for i,(_,_,d) in enumerate(dist):ax.text(d+.03,i,f'{d:.3f}',va='center')
ax.invert_yaxis();ax.set_xlim(0,3.3);ax.set_xlabel('3D center separation / model units (not meters)')
ax.set_title('Remaining separation after registration\nNot a motion estimate or a consistency score');ax.grid(axis='x',alpha=.15)
fig.suptitle('Study3 | Frozen Shot3 → Shot1 registration',fontsize=17)
fig.text(.5,.015,'Scale 0.8484  |  Yaw 138.85°  |  Holdout median reprojection error 120.3 px\nIdentity matches do not imply geometric agreement. Moving entities omitted from this diagnostic.',ha='center',fontsize=11)
fig.tight_layout(rect=[0,.075,1,.94]);fig.savefig(OUT/'alignment_overview.png',dpi=160);plt.close(fig)

images=read(CASE/'identity_review_images.json')
fig,axs=plt.subplots(2,2,figsize=(15,9))
for row,gid in enumerate(['g05','g15']):
 g=groups[gid]
 for side,frame in enumerate([120,0]):
  target=p['shots'][side];source=lookup[g['b_ids' if side==0 else 'a_ids'][0]]
  own=lookup[g['a_ids' if side==0 else 'b_ids'][0]]
  cam=next(c for c in target['own_scene_cameras'] if c['frame_id']==frame)
  im=next(x for x in images if x['shot_id']==target['shot_id'] and x['frame_id']==frame)
  ax=axs[row,side];ax.imshow(plt.imread(im['path']))
  corners=np.array(source['aligned_geometry']['corners_world'])
  if side==1:corners=(corners-np.array(fit['translation']))@np.array(fit['rotation'])/fit['scale']
  camera=(corners-np.array(cam['position_world']))@np.array(cam['R_world_from_camera']);uv=camera@np.array(cam['K']).T;uv=uv[:,:2]/uv[:,2:]
  for i,j in edges:
   if min(camera[i,2],camera[j,2])>1e-6:ax.plot(*uv[[i,j]].T,color='#e538cd',lw=2)
  obs=next(o for o in own['observations'] if o['frame_id']==frame)
  box=obs.get('bbox_xyxy',obs.get('box_xyxy',obs.get('bbox')))
  if box is None:raise ValueError(f'No original box in {obs.keys()}')
  x,y,x2,y2=box;ax.add_patch(Rectangle((x,y),x2-x,y2-y,fill=False,edgecolor='#25d67b',lw=2.5))
  ax.set_xlim(0,852);ax.set_ylim(480,0);ax.axis('off')
  ax.set_title(f'{names[gid]} | {target["shot_id"]}, frame {frame} ← other shot 3D box')
fig.suptitle('Registration checked against original frames',fontsize=17)
fig.legend(handles=[Line2D([0],[0],color='#25d67b',lw=3,label='Original target-frame detector box'),Line2D([0],[0],color='#e538cd',lw=3,label='Other-shot 3D box projected with frozen transform')],loc='lower center',ncol=2)
fig.tight_layout(rect=[0,.05,1,.94]);fig.subplots_adjust(hspace=.16);fig.savefig(OUT/'anchor_reprojection.png',dpi=150);plt.close(fig)
(OUT/'diagnostics.json').write_text(json.dumps({'transform':fit,'registration_quality':p['registration_quality'],'matched_static_center_distances':[dict(group=g,name=n,distance=d) for g,n,d in dist],'note':'No fit or inference rerun; transformed aggregate boxes are uncertain estimates.'},indent=2)+'\n')
print(OUT)
