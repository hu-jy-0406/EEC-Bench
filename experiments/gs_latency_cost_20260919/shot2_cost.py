"""Measure current compact clustering on Shot 2's original frozen detector evidence."""
import sys,time
from pathlib import Path
from types import SimpleNamespace
H=Path(__file__).resolve().parent;B=H.parents[1];sys.path.insert(0,str(B/'scripts'))
import run_wedetect_shot_entities as io
from run_isolated_shot_static_3d import owned_compute_job
owned_compute_job();source=B/'experiments/study_inconsistent_3/wedetect_shot_entities_20260912/run01';out=H/'shot2_clustering';out.mkdir(exist_ok=False)
manifest=io.read(source/'manifest.json');shot=next(s for s in manifest['shots'] if s['shot_id']=='shot2');payload=io.read(source/'shots/shot2/input.json')
for f,p in zip(shot['frames'],payload['frames']):assert io.sha(f['path'])==f['sha256']==p['image_sha256']
args=SimpleNamespace(model='gpt-6-astra',reasoning='medium',codex_bin='/vast/users/guangyi.chen/.local/bin/codex',timeout=1800,prepare_only=False,reuse_reviews=None)
t=time.time();result=io.review(shot,payload,args,out/'shot2');result.update(seconds=time.time()-t,model=args.model,reasoning=args.reasoning,frozen_detector_source=str(source/'shots/shot2/input.json'));io.dump(out/'result.json',result);print(result,flush=True)
