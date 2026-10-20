import json,time,cv2
from pathlib import Path
cv2.setNumThreads(1)
r=Path(__file__).resolve().parent;out=r/'outputs/storymem_official';rows=[]
for p in list(sorted(out.glob('[0-9][0-9]_[0-9][0-9].mp4')))+[out/'storymem_official.mp4']:
 st=time.monotonic();c=cv2.VideoCapture(str(p));advertised=int(c.get(cv2.CAP_PROP_FRAME_COUNT));fps=c.get(cv2.CAP_PROP_FPS);n=0;dims=set()
 while True:
  ok,f=c.read()
  if not ok:break
  n+=1;dims.add(tuple(f.shape))
 c.release();expected=324 if p.name=='storymem_official.mp4' else 81
 row=dict(file=str(p),advertised_frames=advertised,decoded_frames=n,expected_frames=expected,fps=fps,duration_seconds=n/fps if fps else None,shapes=sorted(dims),seconds=time.monotonic()-st,passed=n==advertised==expected and fps==16 and dims=={(480,832,3)})
 rows.append(row)
(out/'full_decode_audit.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows,indent=2));assert len(rows)==5 and all(x['passed'] for x in rows)
