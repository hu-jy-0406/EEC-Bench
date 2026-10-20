import os,json,time,sys
from pathlib import Path
os.environ['HF_HUB_DISABLE_XET']='0'
os.environ['HF_HUB_DOWNLOAD_TIMEOUT']='120'
from huggingface_hub import snapshot_download
root=Path(__file__).resolve().parent
shared=Path('/vast/users/guangyi.chen/causal_group/jinyuan.hu/shotpilot/models/Wan2.1-T2V-1.3B')
specs=[('Wan-AI/Wan2.2-T2V-A14B','c8c270b13ee05bfa474194ac9fb07a5868a97cea',['high_noise_model/*','low_noise_model/*','configuration.json']),('hlwang06/HoloCine','08ee5131abc3eb290c1f1fa93ba79a18fa63c289',['HoloCine_dit/full/*']),('Wan-AI/Wan2.2-I2V-A14B','206a9ee1b7bfaaf8f7e4d81335650533490646a3',['high_noise_model/*','low_noise_model/*','configuration.json']),('Kevin-thu/StoryMem','6dc32f376da3a4552b871ae85b03221ba50dd1f6',['Wan2.2-MI2V-A14B/*','config.json'])]
if len(sys.argv)>1: specs=[specs[int(sys.argv[1])]]
for repo,rev,patterns in specs:
 dest=root/'models'/repo.split('/')[-1];dest.mkdir(parents=True,exist_ok=True)
 if repo.startswith('Wan-AI'):
  for name in ['google','Wan2.1_VAE.pth','models_t5_umt5-xxl-enc-bf16.pth']:
   if not (dest/name).exists():(dest/name).symlink_to(shared/name)
 print('START',repo,time.time(),flush=True)
 snapshot_download(repo,revision=rev,allow_patterns=patterns,local_dir=str(dest),max_workers=2)
 (dest/'download_complete.json').write_text(json.dumps(dict(repo=repo,revision=rev,patterns=patterns,time=time.time())))
 print('DONE',repo,time.time(),flush=True)
