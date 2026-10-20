import concurrent.futures,hashlib,json,time
from pathlib import Path
from huggingface_hub import hf_hub_download
HERE=Path(__file__).parent;ROOT=HERE.parents[1]
models=json.loads((HERE/'model_availability.json').read_text())
def fetch(item):
 name,info=item;dest=ROOT/'models'/name.replace('/','--');rows=[]
 for f in info['files']:
  if f['name'] not in ['model.safetensors','config.json','README.md','LICENSE.txt']:continue
  p=Path(hf_hub_download(name,f['name'],revision=info['sha'],local_dir=dest))
  h=hashlib.sha256()
  with p.open('rb') as stream:
   while b:=stream.read(8*1024*1024):h.update(b)
  rows.append({'path':str(p.resolve()),'size':p.stat().st_size,'sha256':h.hexdigest()})
  print(name,f['name'],'complete',flush=True)
 record={'name':name,'revision':info['sha'],'files':rows,'completed_at':time.time()}
 (HERE/(name.replace('/','--')+'_download.json')).write_text(json.dumps(record,indent=2))
 return record
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 for f in concurrent.futures.as_completed([pool.submit(fetch,x) for x in models.items()]):
  try:print('MODEL_READY',f.result()['name'],flush=True)
  except Exception as e:print(type(e).__name__,str(e),flush=True)
