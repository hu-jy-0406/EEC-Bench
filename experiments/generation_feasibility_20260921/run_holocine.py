"""Reproducible ROCm HoloCine probe: launch exclusively via guard_gpu.py."""
import argparse, json, os, sys, time, traceback, subprocess, fcntl, socket
from pathlib import Path
sys.stdout.reconfigure(line_buffering=True);sys.stderr.reconfigure(line_buffering=True)
R=Path(__file__).resolve().parent
sys.path[:0]=[str(R/'holocine_deps'),str(R/'deps'),str(R/'repos/HoloCine')]
os.environ['HF_HUB_OFFLINE']='1'; os.environ['TOKENIZERS_PARALLELISM']='false'
p=argparse.ArgumentParser();p.add_argument('--shots',type=int,default=4);p.add_argument('--frames',type=int,default=17);p.add_argument('--steps',type=int,default=2);p.add_argument('--width',type=int,default=256);p.add_argument('--height',type=int,default=144);p.add_argument('--fps',type=int,default=16);p.add_argument('--name',default='micro');p.add_argument('--tokens-only',action='store_true');p.add_argument('--vram-limit',type=float,default=52)
a=p.parse_args();out=R/'outputs'/'holocine'/a.name;out.mkdir(parents=True,exist_ok=True)
if a.name=='4shot_20s_50step':
 (out/'metrics.json').write_text(json.dumps(dict(status='skipped_plan_revision',reason='Replaced by 81-frame 50-step standard-sampling probe; full-length runs remain two steps',args=vars(a)),indent=2));print('SKIP_REVISED_PLAN',a.name,flush=True);sys.exit(0)
lock=(out/'.run.lock').open('w');waited_for_run=False
try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:
 waited_for_run=True;print('WAIT_EXISTING_RUN',out,flush=True);fcntl.flock(lock,fcntl.LOCK_EX)
if (out/'metrics.json').exists() and json.loads((out/'metrics.json').read_text()).get('status')=='complete' and not a.tokens_only:
 print('ALREADY_COMPLETE',out,flush=True);sys.exit(0)
if waited_for_run:raise RuntimeError('Concurrent attempt failed; a new fresh GPU guard is required before retry')
from transformers import AutoTokenizer
base=R/'models/Wan2.2-T2V-A14B'; tok=AutoTokenizer.from_pretrained(str(base/'google/umt5-xxl'),local_files_only=True)
cases=json.loads((R/'prompts/test_cases.json').read_text()); audit=[dict(shot_count=c['shot_count'],tokens=len(tok(c['holocine_prompt']).input_ids)) for c in cases]
print('TOKEN_AUDIT',audit,flush=True);(out/'token_audit.json').write_text(json.dumps(audit,indent=2));assert all(x['tokens']<=512 for x in audit)
if a.tokens_only:sys.exit(0)
c=next(c for c in cases if c['shot_count']==a.shots)
import torch
from diffsynth import save_video
from diffsynth.pipelines.wan_video_holocine import WanVideoHoloCinePipeline,ModelConfig
meta=dict(args=vars(a),hostname=socket.gethostname(),gpu_uuid=os.environ.get('ROCR_VISIBLE_DEVICES'),torch=torch.__version__,hip=torch.version.hip,device=torch.cuda.get_device_name(),episode_id=c['episode_id'],prompt=c['holocine_prompt'],start=time.time(),api_calls=0,api_cost_usd=0)
def save(): (out/'metrics.json').write_text(json.dumps(meta,indent=2))
try:
 t=time.perf_counter(); ck=R/'models/HoloCine/HoloCine_dit/full'
 pipe=WanVideoHoloCinePipeline.from_pretrained(torch_dtype=torch.bfloat16,device='cuda',model_configs=[ModelConfig(path=str(base/'models_t5_umt5-xxl-enc-bf16.pth'),offload_device='cpu'),ModelConfig(path=str(ck/'full_high_noise.safetensors'),offload_device='cpu'),ModelConfig(path=str(ck/'full_low_noise.safetensors'),offload_device='cpu'),ModelConfig(path=str(base/'Wan2.1_VAE.pth'),offload_device='cpu')],tokenizer_config=ModelConfig(path=str(base/'google/umt5-xxl')),redirect_common_files=False)
 pipe.enable_vram_management(vram_limit=a.vram_limit);torch.cuda.synchronize();meta['load_seconds']=time.perf_counter()-t;save();print('LOAD_SECONDS',meta['load_seconds'],flush=True)
 frames=4*round((a.frames-1)/4)+1;cuts=[4*round((frames*i/a.shots-1)/4)+1 for i in range(1,a.shots)];assert len(set(cuts))==a.shots-1
 meta.update(frames=frames,cuts=cuts);torch.cuda.reset_peak_memory_stats();t=time.perf_counter()
 def progress(it):
  for i,step in enumerate(it):
   torch.cuda.synchronize(); st=time.perf_counter(); yield step; torch.cuda.synchronize()
   row=dict(step=i,timestep=float(step),seconds=time.perf_counter()-st,allocated_gib=torch.cuda.memory_allocated()/2**30,peak_gib=torch.cuda.max_memory_allocated()/2**30)
   with (out/'step_times.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
   print('STEP_METRIC',json.dumps(row),flush=True)
 video=pipe(progress_bar_cmd=progress,prompt=c['holocine_prompt'],negative_prompt='过曝，静态，细节模糊不清，字幕，最差质量，低质量，畸形，多余的手指',num_frames=frames,shot_cut_frames=cuts,width=a.width,height=a.height,num_inference_steps=a.steps,tiled=True,seed=42)
 torch.cuda.synchronize();meta['generation_seconds']=time.perf_counter()-t;meta['peak_allocated_gib']=torch.cuda.max_memory_allocated()/2**30;meta['peak_reserved_gib']=torch.cuda.max_memory_reserved()/2**30
 import numpy as np
 from PIL import Image,ImageDraw
 pixel_sum=pixel_sq=0.0;pixel_count=0;lo=255;hi=0
 for frame in video:
  arr=np.asarray(frame);assert np.isfinite(arr).all()
  lo=min(lo,int(arr.min()));hi=max(hi,int(arr.max()));pixel_sum+=arr.sum(dtype=np.float64);pixel_sq+=np.square(arr.astype(np.float64)).sum();pixel_count+=arr.size
 mean=pixel_sum/pixel_count;std=max(0,pixel_sq/pixel_count-mean*mean)**0.5
 meta['output_pixel_stats']=dict(min=lo,max=hi,mean=mean,std=std,all_finite=True,scope='PIL output RGB pixels, not internal latent tensors')
 assert hi>lo,'Constant output video'
 indices=sorted(set([0,len(video)//2,len(video)-1]+[int((i+0.5)*len(video)/a.shots) for i in range(a.shots)]))
 cols=4;tw,th=312,200;sheet=Image.new('RGB',(cols*tw,((len(indices)+cols-1)//cols)*th),'white');draw=ImageDraw.Draw(sheet)
 for j,index in enumerate(indices):
  thumb=video[index].copy();thumb.thumbnail((tw,th-20));x=(j%cols)*tw;y=(j//cols)*th;sheet.paste(thumb,(x,y));draw.text((x+3,y+th-18),f'frame {index} / {index/a.fps:.2f}s',fill='black')
 sheet.save(out/'contactsheet.jpg',quality=95);meta['contactsheet_frames']=indices
 t=time.perf_counter();save_video(video,str(out/'video.mp4'),fps=a.fps,quality=5);meta['encoding_seconds']=time.perf_counter()-t;meta['output_frames']=len(video)
 import imageio_ffmpeg
 probe=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-threads','2','-i',str(out/'video.mp4'),'-f','null','-'],capture_output=True,text=True)
 if probe.returncode:raise RuntimeError('Full video decode failed: '+probe.stderr)
 decoded,seconds=imageio_ffmpeg.count_frames_and_secs(str(out/'video.mp4'));assert decoded==frames,(decoded,frames)
 meta.update(decoded_frames=decoded,container_seconds=seconds,decode_verified=True,status='complete')
except Exception:
 meta['status']='failed';meta['error']=traceback.format_exc();raise
finally:
 meta['end']=time.time();save();print('METRICS',json.dumps(meta),flush=True)
