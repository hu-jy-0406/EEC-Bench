import json,subprocess,sys,time
from pathlib import Path
root=Path(__file__).resolve().parent;workspace=root.parents[2];children=[]
def wait_gpu_done(name):
 start=time.time()
 while time.time()-start<7200:
  case=root/name/'run'
  try:
   state=json.loads((case/'pipeline_runtime.json').read_text());plan=json.loads((case/'execution_plan.json').read_text())
   if isinstance(plan,dict):plan=plan['stages']
   if state['status']=='failed':raise RuntimeError(name+' failed; preserve outputs and diagnose before proceeding')
   done={r['stage'] for r in state['stages'] if r['status']=='success'}
   gpu={r['stage'] for r in plan if r['gpu']}
   if gpu and gpu<=done:return
  except (FileNotFoundError,json.JSONDecodeError):pass
  time.sleep(2)
 raise TimeoutError(name+' GPU stages timed out')
for previous,name in [('study2','study3'),('study3','study4')]:
 wait_gpu_done(previous)
 cmd=[sys.executable,str(workspace/'EECBench/scripts/run_gs_integrated.py'),'--manifest',str(root/name/'raw_manifest.json'),'--narrative',str(root/name/'narrative.json'),'--output',str(root/name/'run'),'--alignment-method','roma_fps32_free3d','--runtime-profile','gravity_free_v1','--stop-after','spatial','--gpu','0','--gpu-uuid','GPU-bb018c40b923a974','--geocalib-weights','/tmp/geocalib-deliberately-unavailable.tar']
 log=(root/name/'launch.log').open('w');proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT);children.append((name,proc,log));print('LAUNCH',name,proc.pid,time.time(),flush=True)
for name,proc,log in children:
 code=proc.wait();log.close();print('EXIT',name,code,time.time(),flush=True)
 if code:sys.exit(code)
