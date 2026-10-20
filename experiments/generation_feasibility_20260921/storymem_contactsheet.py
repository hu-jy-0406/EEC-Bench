import json,cv2,numpy as np
from pathlib import Path
from PIL import Image,ImageDraw
cv2.setNumThreads(1)
r=Path(__file__).resolve().parent;rows=[];stats=[]
for p in sorted((r/'outputs/storymem_official').glob('[0-9][0-9]_[0-9][0-9].mp4')):
 cap=cv2.VideoCapture(str(p));n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));fps=cap.get(cv2.CAP_PROP_FPS);frames=[]
 for i in [0,n//2,n-1]:
  cap.set(cv2.CAP_PROP_POS_FRAMES,i);ok,bgr=cap.read()
  if not ok:raise RuntimeError((p,i))
  rgb=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB);stats.append(dict(shot=p.stem,frame=i,count=n,fps=fps,width=rgb.shape[1],height=rgb.shape[0],mean=float(rgb.mean()),std=float(rgb.std()),min=int(rgb.min()),max=int(rgb.max())))
  im=Image.fromarray(rgb);im.thumbnail((416,240));canvas=Image.new('RGB',(416,265),'white');canvas.paste(im,(0,25));ImageDraw.Draw(canvas).text((4,4),f'{p.stem}: frame {i}/{n}',fill='black');frames.append(canvas)
 cap.release();row=Image.new('RGB',(1248,265),'white')
 for j,im in enumerate(frames):row.paste(im,(j*416,0))
 rows.append(row)
if rows:
 out=Image.new('RGB',(1248,265*len(rows)),'white')
 for j,row in enumerate(rows):out.paste(row,(0,j*265))
 out.save(r/'outputs/storymem_official/contactsheet.jpg')
(r/'outputs/storymem_official/video_audit.json').write_text(json.dumps(stats,indent=2))
