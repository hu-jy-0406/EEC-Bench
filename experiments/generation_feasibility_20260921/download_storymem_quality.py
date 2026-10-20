import os,json,time
from pathlib import Path
os.environ['HF_HUB_DISABLE_XET']='0';os.environ['HF_HUB_DOWNLOAD_TIMEOUT']='120'
from huggingface_hub import snapshot_download,HfApi
root=Path(__file__).resolve().parent
for repo,name,patterns in [('MizzenAI/HPSv3','HPSv3',['HPSv3.safetensors']),('Qwen/Qwen2-VL-7B-Instruct','Qwen2-VL-7B-Instruct',['*.json','*.safetensors','*.txt','*.jinja'])]:
 rev=HfApi().model_info(repo).sha;dest=root/'models'/name
 print('START',repo,rev,time.time(),flush=True)
 snapshot_download(repo,revision=rev,allow_patterns=patterns,local_dir=str(dest),max_workers=2)
 (dest/'download_complete.json').write_text(json.dumps(dict(repo=repo,revision=rev,time=time.time())))
 print('DONE',repo,time.time(),flush=True)
