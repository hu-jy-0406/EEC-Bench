"""Shareable plot of exactly the exported common camera-frame geometry."""
import itertools,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Line3DCollection
from matplotlib.lines import Line2D
HERE=Path(__file__).parent/'run01'
d=json.loads((HERE/'aligned_boxes.json').read_text());boxes=d['boxes']
fig=plt.figure(figsize=(11,9));ax=fig.add_subplot(111,projection='3d')
colors={'shot1':'#1674b5','shot3':'#d66a21'}
for b in boxes:
 c=np.array(b['corners']);pairs=[(i,j) for i,j in itertools.combinations(range(8),2) if i^j in [1,2,4]]
 focal=b['group'] in ['g02','g06']
 ax.add_collection3d(Line3DCollection([[c[i],c[j]] for i,j in pairs],colors=colors[b['shot']],linewidths=2.4 if focal else 1,alpha=1 if focal else .4,linestyles='solid' if b['shot']=='shot1' else 'dashed'))
for shot in ['shot1','shot3']:
 a,b=[next(x for x in boxes if x['shot']==shot and x['group']==g) for g in ['g02','g06']]
 p=np.array(a['center']);v=np.array(b['center'])-p
 ax.quiver(*p,*v,color=colors[shot],arrow_length_ratio=.15,linewidth=2)
pts=np.array([p for b in boxes for p in b['corners']]);lo=pts.min(0);hi=pts.max(0);pad=(hi-lo)*.06
ax.set_xlim(lo[0]-pad[0],hi[0]+pad[0]);ax.set_ylim(hi[1]+pad[1],lo[1]-pad[1]);ax.set_zlim(lo[2]-pad[2],hi[2]+pad[2]);ax.set_box_aspect(hi-lo)
ax.view_init(elev=18,azim=-65,vertical_axis='y')
ax.set_xlabel('X right');ax.set_ylabel('Y down');ax.set_zlabel('Z forward')
ax.set_title('Study2 | All 38 static boxes in Shot1 camera coordinates\nCup to pencil holder: cosine 0.9449 | angle 19.1 deg',pad=18)
ax.legend(handles=[Line2D([0],[0],color=colors['shot1'],label='Shot1: 17 boxes'),Line2D([0],[0],color=colors['shot3'],ls='--',label='Shot3: 21 boxes')],loc='upper right')
fig.text(.5,.03,'Native reconstruction units | Thick boxes/arrows: cup and pencil holder',ha='center')
fig.savefig(HERE/'aligned_boxes.png',dpi=170,bbox_inches='tight');fig.savefig(HERE/'aligned_boxes.pdf',bbox_inches='tight');plt.close(fig)
print('Saved static PNG/PDF')
