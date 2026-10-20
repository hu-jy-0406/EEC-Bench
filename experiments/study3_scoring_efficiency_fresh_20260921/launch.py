import json,os,subprocess,time
from pathlib import Path
root=Path(__file__).resolve().parent
workspace=root.parents[2]
os.chdir(workspace)
python='/vast/users/guangyi.chen/anaconda3/bin/python'
command=[python,'EECBench/experiments/study2_detection_only_fresh_20260918/guard_gpu.py','2','GPU-aabcddaa244a3d6e',python,'EECBench/scripts/run_gs_integrated.py',
 '--manifest',str(root/'raw_manifest.json'),'--narrative',str(root/'narrative.json'),'--output',str(root/'run'),
 '--alignment-method','roma_fps32','--consistency-protocol','temporal_v2','--runtime-profile','scoring_efficiency_v1',
 '--schedule-profile','parallel_v2','--stop-after','full','--gpu','2','--gpu-uuid','GPU-aabcddaa244a3d6e',
 '--prompt-alignment-contract','EECBench/experiments/prompt_alignment_four_dimensions_20260921/frozen/contract.json']
state=dict(status='running',started=time.time(),pid=os.getpid(),allocation=os.environ.get('SLURM_JOB_ID'),command=command)
def save():
 tmp=root/'execution.json.tmp';tmp.write_text(json.dumps(state,indent=2)+'\n');tmp.replace(root/'execution.json')
save()
try:
 with (root/'console.log').open('w') as log:
  r=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
 state.update(returncode=r.returncode,status='success' if r.returncode==0 else 'failed')
finally:
 state.update(finished=time.time(),elapsed_seconds=time.time()-state['started']);save()
raise SystemExit(state['returncode'])
