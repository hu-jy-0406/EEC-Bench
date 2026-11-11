#!/usr/bin/env python3
"""Render every frame with YOLOE left and Florence-2 right; no filtering."""
import argparse,hashlib,json
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',type=Path,required=True);a=p.parse_args()
root=a.experiment.resolve();out=root/'paired_frames';out.mkdir(exist_ok=True)
font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',17)
header=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',24)
W,H=1281,720

def render(data):
 im=Image.open(data['path']).convert('RGB').resize((W,H),Image.Resampling.LANCZOS);d=ImageDraw.Draw(im);used=[]
 for obj in data['detections']:
  label=f"{obj['id']} {obj['label']}";color=tuple(55+c%155 for c in hashlib.sha256(obj['label'].encode()).digest()[:3]);b=[v*1.5 for v in obj['box_xyxy']]
  d.rectangle(b,outline=color,width=3);tw=d.textbbox((0,0),label,font=font)[2]+8;th=23;options=[]
  for yy in [b[1]-th,b[1],b[3],b[3]-th]+list(range(0,H-th,26)):
   for xx in [b[0],b[2]-tw]:
    x=max(0,min(xx,W-tw));y=max(0,min(yy,H-th));r=(x,y,x+tw,y+th)
    overlap=sum(r[0]<q[2]+3 and r[2]+3>q[0] and r[1]<q[3]+3 and r[3]+3>q[1] for q in used)
    options.append((overlap*100000+abs(y-(b[1]-th))+abs(x-b[0])*.4,r))
  _,r=min(options,key=lambda v:v[0]);used.append(r)
  if abs(r[1]-(b[1]-th))>th*2:d.line((r[0]+tw/2,r[1]+th/2,b[0],b[1]),fill=color,width=1)
  d.rectangle(r,fill='white',outline=color,width=2);d.text((r[0]+4,r[1]+1),label,font=font,fill='black')
 return im

runs=[json.loads((root/n/'run.json').read_text()) for n in ['yoloe_03','florence_01']]
assert all(r['status']=='success' for r in runs)
assert [(f['shot'],f['frame_id'],f['sha256']) for f in runs[0]['frames']]==[(f['shot'],f['frame_id'],f['sha256']) for f in runs[1]['frames']]
records=[]
for i,f in enumerate(runs[0]['frames'],1):
 shot=f['shot'];fid=f['frame_id'];short=f'Shot{shot[-1]}';pair=Image.new('RGB',(2578,785),'#e7e9ed');draw=ImageDraw.Draw(pair);counts=[]
 for x,n,model in [(0,'yoloe_03','YOLOE'),(1297,'florence_01','Florence-2')]:
  data=json.loads((root/n/shot/f'frame_{fid:06d}'/'detections.json').read_text());assert data['sha256']==f['sha256']==hashlib.sha256(Path(f['path']).read_bytes()).hexdigest()
  counts.append(len(data['detections']));draw.text((x+14,17),f'{short} | Frame {fid} | {model} | {counts[-1]} boxes',font=header,fill='black');pair.paste(render(data),(x,65))
 name=f'{i:02d}_{short.lower()}_frame_{fid:06d}.jpg';pair.save(out/name,quality=94)
 records.append(dict(index=i,shot=short,frame_id=fid,timestamp_sec=f['timestamp_sec'],file=name,counts=counts,input_sha256=f['sha256']));print(name,flush=True)
page=['<!doctype html><meta charset="utf-8"><title>关键帧检测对照</title><style>body{font:18px sans-serif;margin:24px;background:#f4f5f7}img{width:100%}figure{margin:30px 0}figcaption{margin:8px}</style><h1>左 YOLOE，右 Florence-2</h1><p>保留全部原始检测。数字为帧内检测编号；点击图片查看全尺寸。</p>'];md=['# 关键帧检测对照\n\n每组左 YOLOE，右 Florence-2。\n']
for r in records:
 title=f"{r['shot']} · Frame {r['frame_id']} · {r['timestamp_sec']:.3f}s"
 page.append(f'<figure><figcaption>{title}</figcaption><a href="{r["file"]}"><img loading="lazy" src="{r["file"]}"></a></figure>');md.append(f'**{title}**\n\n![{title}]({r["file"]})\n')
(out/'index.html').write_text('\n'.join(page));(out/'index.md').write_text('\n'.join(md));(out/'manifest.json').write_text(json.dumps(records,indent=2))
assert len(records)==18
for r in records:
 with Image.open(out/r['file']) as im:assert im.size==(2578,785)
print('PASS: 18 pairs, all original detections retained, shared inputs verified')
