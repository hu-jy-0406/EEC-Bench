import os,time,json,copy,traceback,hashlib,logging
from pathlib import Path
import cv2,numpy as np,torch
import wan
from wan.configs import WAN_CONFIGS,MAX_AREA_CONFIGS
from wan.utils.utils import save_video
r=Path(__file__).resolve().parent;out=r/'outputs/storymem_capacity10_probe';out.mkdir(exist_ok=True)
logging.basicConfig(level=logging.INFO,format='[%(asctime)s] %(levelname)s: %(message)s')
cv2.setNumThreads(1)
cap=cv2.VideoCapture(str(r/'outputs/storymem_official/01_01.mp4'));n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));indices=np.linspace(0,n-1,10).round().astype(int).tolist();files=[]
for i in indices:
 cap.set(cv2.CAP_PROP_POS_FRAMES,i);ok,frame=cap.read();assert ok;p=out/f'memory_frame_{i:03d}.png';assert cv2.imwrite(str(p),frame);files.append(str(p))
cap.release();hashes=[hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files];assert len(set(hashes))==10
cfg=copy.deepcopy(WAN_CONFIGS['m2v-A14B'])
for level in ['low','high']:
 lora=cfg[f'{level}_noise_lora'];lora.weight=str(r/f'models/StoryMem/Wan2.2-MI2V-A14B/backbone_{level}_noise.safetensors');lora.r=lora.lora_alpha=128
record=dict(kind='explicit selector-bypass capacity diagnostic; not official selected memory or 40-step quality',source_video=str(r/'outputs/storymem_official/01_01.mp4'),frame_indices=indices,memory_files=files,sha256=hashes,steps=2,frames=81,size=[832,480],seed=20260923,cpus=sorted(os.sched_getaffinity(0)),stages=[])
def save(): (out/'metrics.json').write_text(json.dumps(record,indent=2))
start=time.monotonic();model=None
try:
 st=time.monotonic();model=wan.WanM2V(config=cfg,checkpoint_dir=str(r/'models/Wan2.2-I2V-A14B'),device_id=0,rank=0,t5_cpu=False,convert_model_dtype=True)
 record['init_seconds']=time.monotonic()-st;print('CAPACITY_INIT',record['init_seconds'],flush=True)
 def instrument(obj,name,label):
  original=getattr(obj,name)
  def measured(*args,**kwargs):
   torch.cuda.synchronize();st=time.monotonic();result=original(*args,**kwargs);torch.cuda.synchronize();dt=time.monotonic()-st
   row=dict(stage=label,seconds=dt);record['stages'].append(row);print('CAPACITY_STAGE',row,flush=True);return result
  setattr(obj,name,measured)
 instrument(model,'_prepare_model_for_timestep','expert_prepare')
 instrument(model.high_noise_model,'forward','high_noise_forward')
 instrument(model.low_noise_model,'forward','low_noise_forward')
 instrument(model.vae,'encode','vae_encode')
 instrument(model.vae,'decode','vae_decode')
 prompt=json.loads((r/'prompts/test_cases.json').read_text())[0]['per_shot_prompts'][2]
 torch.cuda.reset_peak_memory_stats();st=time.monotonic()
 video=model.generate(prompt,files,max_area=MAX_AREA_CONFIGS['832*480'],frame_num=81,shift=cfg.sample_shift,sample_solver='unipc',sampling_steps=2,guide_scale=3.5,seed=20260923,offload_model=True)
 torch.cuda.synchronize();record.update(generate_seconds=time.monotonic()-st,peak_allocated_bytes=torch.cuda.max_memory_allocated(),peak_reserved_bytes=torch.cuda.max_memory_reserved(),shape=list(video.shape),finite=bool(torch.isfinite(video).all()),min=float(video.min()),max=float(video.max()),std=float(video.std()))
 save_video(tensor=video[None],save_file=str(out/'video_2step.mp4'),fps=cfg.sample_fps,nrow=1,normalize=True,value_range=(-1,1))
 record['status']='success';record['total_seconds']=time.monotonic()-start;save();print('CAPACITY_SUCCESS',json.dumps(record),flush=True)
except Exception as e:
 record.update(status='failed',error=repr(e),traceback=traceback.format_exc(),total_seconds=time.monotonic()-start)
 if torch.cuda.is_initialized():record.update(peak_allocated_bytes=torch.cuda.max_memory_allocated(),peak_reserved_bytes=torch.cuda.max_memory_reserved())
 save();raise
