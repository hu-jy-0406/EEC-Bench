import os,json,hashlib
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR','/tmp/eec-identityreview-fig')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
H=Path(__file__).resolve().parent;O=H/'study2';r=json.loads((O/'identity_review.json').read_text());groups=r['matching']['groups'];emap={eid:g['group_id'] for g in groups for eid in g['a_ids']+g['b_ids']}
fig,axes=plt.subplots(1,2,figsize=(16,5.7));selected={'shot1':[(120,['e1','e18','e19'])],'shot3':[(0,['e1','e8','e11'])]}
for ax,sid in zip(axes,['shot1','shot3']):
 d=json.loads((O/'inputs'/f'{sid}.json').read_text());fid,ids=selected[sid][0];f=next(x for x in d['frames'] if x['frame_id']==fid);assert hashlib.sha256(Path(f['path']).read_bytes()).hexdigest()==f['sha256'];ax.imshow(plt.imread(f['path']));ax.axis('off');ax.set_title(sid.replace('shot','Shot ')+f' / frame {fid}',fontsize=14,weight='bold')
 for eid,label,c in zip(ids,['Painting','Side table','Plant'],['#1769ba','#b342ad','#167442']):
  e=next(e for e in d['entities'] if e['entity_id']==eid);b=next(o['box_xyxy'] for o in e['observations'] if o['frame_id']==fid);x,y,x2,y2=b;ax.add_patch(Rectangle((x,y),x2-x,y2-y,fill=False,ec=c,lw=2));gid=emap[sid+'/'+eid]
  ax.annotate(label+' / '+gid,(x,y),xytext=(0,11 if label=='Plant' else -23 if label=='Side table' else -10),textcoords='offset points',fontsize=10,color='white',bbox=dict(fc=c,ec='none',pad=2),annotation_clip=False)
fig.suptitle('Study2 | three former matches split into six single-shot identities',fontsize=17,weight='bold',y=.985);fig.text(.5,.045,'_a and _b are different instances after review. Viewpoint explanations are checked separately downstream.',ha='center',fontsize=11);fig.subplots_adjust(left=.015,right=.985,top=.88,bottom=.10,wspace=.04);fig.savefig(O/'identity_changes.png',dpi=140);fig.savefig(O/'identity_changes.jpg',dpi=110,pil_kwargs={'quality':90});print('Identity evidence figure saved.')
