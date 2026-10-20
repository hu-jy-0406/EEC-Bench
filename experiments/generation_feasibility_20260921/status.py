import json,time
from pathlib import Path
R=Path(__file__).resolve().parent
print('UTC',time.strftime('%Y-%m-%d %H:%M:%S',time.gmtime()))
for name in ['Wan2.2-T2V-A14B','HoloCine','Wan2.2-I2V-A14B','StoryMem','HPSv3','Qwen2-VL-7B-Instruct']:
 d=R/'models'/name
 fs=[]
 if d.exists():
  # Only our bounded download directories; never traverse shared symlinks.
  import os
  for base,dirs,files in os.walk(d,followlinks=False):
   for f in files:
    p=Path(base)/f
    if not p.is_symlink():fs.append(p)
 print(name,round(sum(p.stat().st_size for p in fs)/1e9,3),'GB', 'complete' if (d/'download_complete.json').exists() else 'pending')
for p in sorted((R/'logs').glob('*')):
 if p.is_file():
  with p.open('rb') as f:
   f.seek(max(0,p.stat().st_size-650));text=f.read().decode(errors='replace')
  print('\nLOG',p.name,text[-500:])
