import os,sys,gc,time,json
from campaign import ROOT,FEAS,SHARED,read,write,load_pipe,NEGATIVE
sys.path[:0]=[str(FEAS/'holocine_deps'),str(FEAS/'deps'),str(FEAS/'repos/HoloCine'),str(SHARED)]
os.environ['HF_HUB_OFFLINE']='1';os.environ['TOKENIZERS_PARALLELISM']='false'
import torch,numpy as np
from text_context import generate_episode
import mapped_storage
q=read(ROOT/'queue.json');task=max(q['tasks'],key=lambda t:len(t['prompt']));n=task['shot_count'];reference=None;weights={};proof=[];install=mapped_storage.install
for mode in ['standard','mapped']:
 if mode=='mapped_plain':mapped_storage.install=lambda p:None
 else:mapped_storage.install=install
 pipe=load_pipe('standard' if mode=='standard' else 'mapped')
 mismatches=[]
 for name in ['text_encoder','dit','dit2','vae']:
  sd=getattr(pipe,name).state_dict()
  if mode=='standard':weights[name]=sd
  else:
   for k,v in sd.items():
    if k not in weights[name] or not torch.equal(v,weights[name][k]):mismatches.append([name,k])
 print('WEIGHT_MISMATCHES',mode,mismatches[:20],len(mismatches),flush=True)
 last={};orig=pipe.scheduler.step
 def step(*a,**k):v=orig(*a,**k);last['latents']=v.detach().cpu();return v
 pipe.scheduler.step=step
 for repeat in range(2):
  start=time.time();out=generate_episode(pipe,task['prompt'],n,num_frames=4*n+1,shot_cut_frames=[4*j+1 for j in range(1,n)],width=256,height=144,num_inference_steps=2,negative_prompt=NEGATIVE,seed=20260922,tiled=True)
  pixels=np.stack([np.asarray(im) for im in out]);latents=last['latents'];assert torch.isfinite(latents).all()
  if reference is None:reference=(latents.clone(),pixels.copy())
  d=dict(mode=mode,repeat=repeat,weight_mismatches=mismatches,seconds=time.time()-start,latent_bit_exact=torch.equal(reference[0],latents),latent_max_abs=(reference[0].float()-latents.float()).abs().max().item(),pixels_bit_exact=np.array_equal(reference[1],pixels),pixel_max_abs=int(np.abs(reference[1].astype(int)-pixels.astype(int)).max()))
  proof.append(d);write(ROOT/'staged_mmap_diagnosis.json',proof);print('COMPARISON',d,flush=True)
 del pipe,last,out;gc.collect();torch.cuda.empty_cache()
assert all(x['latent_bit_exact'] and x['pixel_max_abs']<=1 and not x['weight_mismatches'] for x in proof)
write(ROOT/'staged_mmap_equivalence.json',dict(pass_all=True,proof=proof,frames=4*n+1,size=[256,144],steps=2,finished=time.time()))
