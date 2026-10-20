"""Resume the studied per-shot pipeline, rechecking GPU immediately per stage.
Run within an existing owned allocation; requires a physical index AND its UUID.
Each invocation processes exactly one frozen shot. Comparison is a separate call.
"""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;BASE=HERE.parents[1];sys.path.insert(0,str(BASE/'scripts'))
from run_isolated_shot_static_3d import owned_compute_job
p=argparse.ArgumentParser();p.add_argument('--shot',required=True,choices=['shot1','shot3']);p.add_argument('--method',default='pi3x',choices=['pi3x','pi3x_native','da3nested','dvlt']);p.add_argument('--gpu-index',required=True,type=int);p.add_argument('--gpu-uuid',required=True);p.add_argument('--refine',action='store_true');a=p.parse_args()
owned_compute_job()
if not a.gpu_uuid.startswith('GPU-'):raise ValueError('Use checked ROCr GPU UUID')
root=HERE/a.method/a.shot;guard=[sys.executable,str(BASE/'scripts/guard_geocalib_boxer_gpu.py'),str(a.gpu_index),a.gpu_uuid,sys.executable]
for script,done in [('run_geometry.py',root/'complete.json'),('run_depth_boxer.py',root/'boxer_depth/complete.json')]:
 if done.exists():
  metadata=json.loads(done.read_text());assert metadata['status']=='complete'
  if script=='run_geometry.py':assert metadata['inputs_sha256']==hashlib.sha256((HERE/'inputs'/f'{a.shot}.json').read_bytes()).hexdigest()
  print('REUSE completed stage',done,flush=True)
 else:subprocess.run(guard+[str(HERE/script),'--method',a.method,'--shot',a.shot],check=True)
if a.refine and not (root/'boxer_refined/complete.json').exists():subprocess.run([sys.executable,str(HERE/'refine_boxes.py'),'--method',a.method,'--shot',a.shot],check=True)
print('SHOT COMPLETE',a.method,a.shot,'comparison remains separate')
