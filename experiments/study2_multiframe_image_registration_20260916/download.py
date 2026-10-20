import hashlib,json,socket,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;BASE=HERE.parents[1];sys.path.insert(0,str(BASE/'scripts'))
from run_isolated_shot_static_3d import owned_compute_job
job=owned_compute_job();socket.setdefaulttimeout(120)
import torch
p=HERE/'torch_cache/hub/checkpoints/romav2.0.1.pt';p.parent.mkdir(parents=True,exist_ok=True)
u='https://github.com/Parskatt/RoMaV2/releases/download/v2.0.1/romav2.0.1.pt'
if not p.exists():torch.hub.download_url_to_file(u,str(p),progress=False)
h=hashlib.sha256()
with p.open('rb') as f:
 while b:=f.read(8*1024*1024):h.update(b)
r={'url':u,'path':str(p),'sha256':h.hexdigest(),'size':p.stat().st_size,'allocation':job};(HERE/'weights.json').write_text(json.dumps(r,indent=2)+'\n');print(r,flush=True)
