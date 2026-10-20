"""Materialize exactly the original CPU BF16 casts as file-backed safetensors."""
import os,json,time,gc,sys
from pathlib import Path
R=Path(__file__).resolve().parent;F=R.parent/'generation_feasibility_20260921'
sys.path[:0]=[str(F/'holocine_deps'),str(F/'deps')]
import torch
from safetensors import safe_open
from safetensors.torch import save_file
from campaign import write
D=R/'mapped_weights';D.mkdir(exist_ok=True);base=F/'models/Wan2.2-T2V-A14B';ck=F/'models/HoloCine/HoloCine_dit/full'
paths=[base/'models_t5_umt5-xxl-enc-bf16.pth',ck/'full_high_noise.safetensors',ck/'full_low_noise.safetensors',base/'Wan2.1_VAE.pth'];proof=[]
for i,p in enumerate(paths):
 dest=D/f'{i}.safetensors';t=time.time()
 if p.suffix=='.safetensors':
  with safe_open(str(p),framework='pt',device='cpu') as f:sd={k:f.get_tensor(k).to(torch.bfloat16).contiguous() for k in f.keys()}
 else:
  raw=torch.load(p,map_location='cpu',weights_only=True);sd={k:v.to(torch.bfloat16).contiguous() for k,v in raw.items()};del raw
 temp=dest.with_suffix('.partial');save_file(sd,str(temp));os.replace(temp,dest)
 with safe_open(str(dest),framework='pt',device='cpu') as f:
  assert set(f.keys())==set(sd)
  for k,v in sd.items():assert torch.equal(v,f.get_tensor(k)),(p,k)
 proof.append(dict(source=str(p),destination=str(dest),source_size=p.stat().st_size,tensors=len(sd),destination_bytes=dest.stat().st_size,all_tensors_equal=True,seconds=time.time()-t));write(D/'progress.json',proof);print(proof[-1],flush=True);del sd;gc.collect()
write(D/'complete.json',dict(all_tensors_equal_official_bf16=True,proof=proof,finished=time.time(),quantization=False))
