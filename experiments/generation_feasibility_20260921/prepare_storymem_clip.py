import os,json,torch
from pathlib import Path
os.environ['HF_HUB_DISABLE_XET']='0'
from huggingface_hub import hf_hub_download,HfApi
import clip
r=Path(__file__).resolve().parent
repo='timm/vit_base_patch32_clip_224.openai';rev=HfApi().model_info(repo).sha
p=hf_hub_download(repo,'open_clip_pytorch_model.bin',revision=rev,local_dir=str(r/'models/CLIP'))
state=torch.load(p,map_location='cpu',weights_only=True)
print('KEYS',list(state)[:10],flush=True)
model=clip.model.build_model(dict(state));print('STRICT_OPENAI_MODEL_BUILD_OK',flush=True)
out=r/'models/CLIP/ViT-B-32-openai.pt';torch.save(state,out)
(r/'models/CLIP/provenance.json').write_text(json.dumps(dict(repo=repo,revision=rev,source_file=p,output=str(out),strict_openai_model_load=True),indent=2))
