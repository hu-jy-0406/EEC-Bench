import hashlib,json,sys,os
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;BASE=HERE.parents[1];OLD=Path(os.environ['CASE_ROOT']);RUN=OLD/'registration';RUN.mkdir(exist_ok=True)
sys.path.insert(0,str(BASE/'scripts'))
from run_isolated_shot_static_3d import owned_compute_job
from robust_box_registration import corners,transform
MATCH=json.loads((OLD/'anchor_matching.json').read_text()) if (OLD/'anchor_matching.json').exists() else {'groups':[],'structural_anchor_group_ids':[]}
ANCHORS={g['group_id']:(g['a_ids'][0].split('/')[-1],g['b_ids'][0].split('/')[-1]) for g in MATCH['groups'] if g['group_id'] in MATCH['structural_anchor_group_ids']}

def read(p):return json.loads(Path(p).read_text())
def save(p,x):p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def inputs(s):return read(OLD/'inputs'/f'{s}.json')
def graph(s):return read(OLD/'selected'/f'{s}_scene.json')
def structural_mask(s,fid):
 inp=inputs(s);side=0 if s=='shot1' else 1;W,H=inp['image_sizes'][0];mask=np.zeros((H,W),np.int16);chosen={ids[side]:int(g[1:]) for g,ids in ANCHORS.items()}
 rects=[]
 for e in inp['entities']:
  o=next(o for o in e['observations'] if o['frame_id']==fid)
  if not o['visible'] or o['box_xyxy'] is None:continue
  b=np.array(o['box_xyxy'],int);rects.append((e['entity_id'],b))
 # Large support surfaces first, smaller fixtures override overlap deterministically.
 for eid,b in sorted(rects,key=lambda z:-np.prod(z[1][2:]-z[1][:2])):
  if eid in chosen:
   x1,y1,x2,y2=b;mask[max(0,y1):min(H,y2),max(0,x1):min(W,x2)]=chosen[eid]
 for eid,b in rects:
  if eid not in chosen:
   x1,y1,x2,y2=b+np.array([-5,-5,5,5]);mask[max(0,y1):min(H,y2),max(0,x1):min(W,x2)]=0
 return mask

def lookup(mask,uv):
 h,w=mask.shape;v=np.floor(uv).astype(int);valid=(v[:,0]>=0)&(v[:,0]<w)&(v[:,1]>=0)&(v[:,1]<h);out=np.zeros(len(uv),np.int16);out[valid]=mask[v[valid,1],v[valid,0]];return out
