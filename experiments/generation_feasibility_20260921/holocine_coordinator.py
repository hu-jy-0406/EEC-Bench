import argparse,json,os,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parent;W=R.parents[2]
p=argparse.ArgumentParser();p.add_argument('--gpu-index',required=True);p.add_argument('--gpu-uuid',required=True);a=p.parse_args()
py='/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python'
guard=W/'EECBench/experiments/study2_detection_only_fresh_20260918/guard_gpu.py'
status=R/'logs/holocine_coordinator.json'
def record(**kw):status.write_text(json.dumps(dict(time=time.time(),**kw),indent=2))
record(status='waiting_weights',pid=os.getpid())
while not (R/'models/HoloCine/download_complete.json').exists():time.sleep(10)
for name,shots,frames,steps,width,height in [('micro',4,17,2,256,144),('4shot_20s_2step',4,321,2,832,480),('6shot_30s_2step',6,481,2,832,480),('8shot_40s_2step',8,641,2,832,480)]:
 metrics=R/'outputs/holocine'/name/'metrics.json'
 if metrics.exists() and json.loads(metrics.read_text()).get('status')=='complete':continue
 cmd=[py,str(guard),a.gpu_index,a.gpu_uuid,py,str(R/'run_holocine.py'),'--name',name,'--shots',str(shots),'--frames',str(frames),'--steps',str(steps),'--width',str(width),'--height',str(height)]
 record(status='running',pid=os.getpid(),name=name,command=cmd)
 print('LAUNCH',name,time.time(),flush=True)
 with (R/'logs'/('holocine_'+name+'.log')).open('a') as f:result=subprocess.run(cmd,cwd=W,stdout=f,stderr=subprocess.STDOUT)
 print('EXIT',name,result.returncode,time.time(),flush=True)
 if result.returncode:record(status='failed',name=name,returncode=result.returncode);raise SystemExit(result.returncode)
record(status='complete')
