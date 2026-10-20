import os,time,logging,json
from pathlib import Path
r=Path(__file__).resolve().parent
os.environ['STORYMEM_CLIP_CHECKPOINT']=str(r/'models/CLIP/ViT-B-32-openai.pt')
logging.basicConfig(level=logging.INFO)
import torch,cv2
from extract_keyframes import get_frame_sim_clip
print('CPU_PROBE',os.sched_getaffinity(0),torch.get_num_threads(),flush=True)
cap=cv2.VideoCapture(str(r/'outputs/storymem_official/01_01.mp4'));frames=[]
for i in [0,40]:
 cap.set(cv2.CAP_PROP_POS_FRAMES,i);ok,a=cap.read();assert ok;frames.append(torch.from_numpy(cv2.cvtColor(a,cv2.COLOR_BGR2RGB)).permute(2,0,1))
st=time.monotonic();sim=get_frame_sim_clip(*frames);dt=time.monotonic()-st
print('CLIP_CPU_RESULT',sim,dt,flush=True)
(r/'storymem_clip_cpu_probe.json').write_text(json.dumps(dict(similarity=sim,seconds=dt,cpus=sorted(os.sched_getaffinity(0)),threads=torch.get_num_threads(),scope='CPU diagnostic on two generated frames; no memory bank change')))
