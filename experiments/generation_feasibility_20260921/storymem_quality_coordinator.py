import os,time,subprocess,json
from pathlib import Path
r=Path(__file__).resolve().parent;root=r.parents[2]
while not (r/'models/Qwen2-VL-7B-Instruct/download_complete.json').exists():time.sleep(30)
env=dict(os.environ,PYTHONPATH=':'.join(str(r/p) for p in ['storymem_deps','deps','repos/StoryMem']),PYTHONNOUSERSITE='1',TOKENIZERS_PARALLELISM='false',MIOPEN_USER_DB_PATH=str(r/'outputs/storymem_miopen'),MIOPEN_CUSTOM_CACHE_DIR=str(r/'outputs/storymem_miopen'))
(r/'outputs/storymem_miopen').mkdir(exist_ok=True)
py='/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python'
with (r/'logs/storymem_quality_gpu.log').open('w') as f:
 rc=subprocess.call([py,str(root/'EECBench/experiments/study2_detection_only_fresh_20260918/guard_gpu.py'),'2','GPU-0d509b37c2cd020a',py,'-u',str(r/'preflight_storymem_quality.py')],env=env,stdout=f,stderr=subprocess.STDOUT)
print('QUALITY_SMOKE_EXIT',rc,flush=True)
if rc==0:(r/'storymem_import_ready.json').write_text(json.dumps(dict(pipeline_import=True,quality_gpu_preflight=True,time=time.time())))
raise SystemExit(rc)
