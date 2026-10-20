#!/usr/bin/env python3
import argparse,json,time,os,sys,subprocess,hashlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--smoke-only',action='store_true');p.add_argument('--shots',type=int,default=4);a=p.parse_args()
R=Path(__file__).resolve().parent
sys.path[:0]=[str(R/'wan_deps'),str(R/'deps'),str(R/'repos/Wan2.2')]
import torch
from wan import WanT2V
from wan.configs import WAN_CONFIGS
from wan.utils.utils import save_video
out=R/'wan_outputs';out.mkdir(exist_ok=True)
cfg=WAN_CONFIGS['t2v-A14B']; ckpt=R/'models/Wan2.2-T2V-A14B'
case=json.loads((R/'prompts/test_cases.json').read_text())[0]
report={'episode_id':case['episode_id'],'repo_commit':subprocess.check_output(['git','-C',str(R/'repos/Wan2.2'),'rev-parse','HEAD'],text=True).strip(),'checkpoint':str(ckpt),'torch':torch.__version__,'hip':torch.version.hip,'device':torch.cuda.get_device_name(),'size':[832,480],'frame_num':81,'fps':16,'steps':40,'solver':'unipc','shift':cfg.sample_shift,'guide_scale':cfg.sample_guide_scale,'seed_base':20260921,'offload_model':True,'t5_cpu':False,'convert_model_dtype':True,'shots':[]}
def persist(): (out/'timings.json').write_text(json.dumps(report,indent=2))
t=time.perf_counter();model=WanT2V(cfg,str(ckpt),device_id=0,t5_cpu=False,init_on_cpu=True,convert_model_dtype=True);torch.cuda.synchronize();report['load_seconds']=time.perf_counter()-t;persist();print('LOAD_SECONDS',report['load_seconds'],flush=True)
plans=[('smoke',0,5,2)]+([] if a.smoke_only else [(f'shot{i+1}',i,81,40) for i in range(min(a.shots,len(case['per_shot_prompts'])))])
for name,i,frames,steps in plans:
 prompt=case['per_shot_prompts'][i]
 if not isinstance(prompt,str): prompt=prompt.get('prompt',prompt.get('text'))
 torch.cuda.reset_peak_memory_stats();torch.cuda.synchronize();t=time.perf_counter()
 video=model.generate(prompt,size=(832,480),frame_num=frames,shift=cfg.sample_shift,sampling_steps=steps,guide_scale=cfg.sample_guide_scale,seed=20260921+i,offload_model=True)
 torch.cuda.synchronize();dt=time.perf_counter()-t;peak=torch.cuda.max_memory_allocated();reserved=torch.cuda.max_memory_reserved();t=time.perf_counter()
 assert torch.isfinite(video).all().item(), 'Nonfinite generated tensor'
 tensor_stats={'min':video.min().item(),'max':video.max().item(),'std':video.float().std().item()}
 torch.cuda.synchronize();tensor_validation_seconds=time.perf_counter()-t;t=time.perf_counter();path=out/f'{name}.mp4'
 save_video(tensor=video[None],save_file=str(path),fps=16,nrow=1,normalize=True,value_range=(-1,1));save=time.perf_counter()-t
 import imageio.v2 as imageio
 t=time.perf_counter();reader=imageio.get_reader(str(path)); decoded=0;selected=[]
 for frame in reader:
  assert frame.shape[:2]==(480,832),frame.shape
  if decoded in {0,frames//2,frames-1}: selected.append(frame.copy())
  decoded+=1
 reader.close();assert decoded==frames,(decoded,frames)
 from PIL import Image,ImageDraw
 sheet=Image.new('RGB',(832*len(selected),510),'white')
 for j,frame in enumerate(selected):
  sheet.paste(Image.fromarray(frame),(j*832,30));ImageDraw.Draw(sheet).text((j*832+10,8),['first','middle','last'][j],fill='black')
 sheet.save(out/f'{name}_contact.jpg');decode_validation_seconds=time.perf_counter()-t
 record={'name':name,'prompt':prompt,'frames':frames,'steps':steps,'generation_seconds':dt,'save_seconds':save,'peak_allocated_bytes':peak,'peak_reserved_bytes':reserved,'output':str(path),'shape':list(video.shape),'tensor_stats':tensor_stats,'tensor_validation_seconds':tensor_validation_seconds,'decode_validation_seconds':decode_validation_seconds,'decoded_frames':decoded,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()};report['shots'].append(record);persist();print('SHOT_DONE',json.dumps(record),flush=True);del video
 if name=='shot2' and max(x['generation_seconds'] for x in report['shots'] if x['frames']==81)>1200:
  report['bounded_stop_reason']='two full shots complete; measured generation exceeds 20 minutes per shot';break
report['complete']=True;persist()
