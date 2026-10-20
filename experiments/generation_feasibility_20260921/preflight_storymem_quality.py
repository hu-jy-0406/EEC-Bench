import os,time,json
from pathlib import Path
from PIL import Image
r=Path(__file__).resolve().parent
from hpsv3 import HPSv3RewardInferencer
st=time.monotonic()
m=HPSv3RewardInferencer(config_path=str(r/'prompts/storymem_hps.yaml'),checkpoint_path=str(r/'models/HPSv3/HPSv3.safetensors'),device='cuda')
print('HPS_INIT',time.monotonic()-st,flush=True)
a=m.reward(image_paths=[Image.new('RGB',(224,224),(127,127,127))],prompts=[''])
print('HPS_REWARD',a,flush=True)
import torch
assert torch.isfinite(a).all() if isinstance(a,torch.Tensor) else all(torch.isfinite(x).all() for x in a)
print('HPS_GPU_SMOKE_OK',time.monotonic()-st,flush=True)
(r/'storymem_quality_preflight.json').write_text(json.dumps(dict(seconds=time.monotonic()-st,result='finite',scope='synthetic image smoke, not pipeline video generation')))
