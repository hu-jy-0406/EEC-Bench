import argparse
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import ConnectionPatch
from PIL import Image
from common import *
p=argparse.ArgumentParser();p.add_argument('--method',default='roma');a=p.parse_args();owned_compute_job();root=RUN/(a.method+'_geometry');d=np.load(root/'correspondences.npz')['data'];out=root/'visuals';out.mkdir(exist_ok=True)
files={s:{f['frame_id']:f['path'] for f in inputs(s)['frames']} for s in ['shot1','shot3']};colors={1:'#e8bd00',4:'#00ccff',10:'#b578ff',12:'#ff8329'}
for fa,fb in [(0,0),(0,120),(72,48),(120,120)]:
 rows=d[(d[:,0]==fa)&(d[:,1]==fb)];fig,ax=plt.subplots(1,2,figsize=(14.2,4.5));seen=set();selected=[]
 for r in rows[np.argsort(-rows[:,13])]:
  key=(int(r[2]),int(r[3]//64),int(r[4]//64))
  if key not in seen:seen.add(key);selected.append(r)
  if len(selected)>=18:break
 for side,(s,fid) in enumerate([('shot1',fa),('shot3',fb)]):ax[side].imshow(Image.open(files[s][fid]));ax[side].set_xlim(0,852);ax[side].set_ylim(480,0);ax[side].axis('off');ax[side].set_title(s+' frame '+str(fid))
 for i,r in enumerate(selected):
  u=r[3:5];v=r[5:7];c=colors[int(r[2])]
  fig.add_artist(ConnectionPatch(u,v,'data','data',axesA=ax[0],axesB=ax[1],color=c,lw=.65,alpha=.55))
  for j,q in enumerate([u,v]):ax[j].plot(*q,'o',color=c,ms=3);ax[j].text(*q,str(i),color='black',fontsize=7,bbox={'facecolor':'white','alpha':.8,'pad':.3,'edgecolor':'none'})
 fig.suptitle(a.method+f' filtered correspondences (not ground truth), {len(rows)} retained; cyan table, orange radiator, yellow painting, purple rug',fontsize=10);fig.tight_layout();fig.savefig(out/f'matches_{fa}_{fb}.jpg',dpi=110);plt.close(fig)
print(out)
