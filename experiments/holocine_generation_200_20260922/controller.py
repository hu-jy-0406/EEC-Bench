"""Follow existing/new RUNNING allocations, never submit a GPU allocation."""
import importlib.util,json,os,re,subprocess,time,traceback,fcntl
from pathlib import Path
from campaign import ROOT,PY,read,write,locked
path='/vast/users/guangyi.chen/causal_group/jinyuan.hu/check_guangyi_gpus.py'
import sys
spec=importlib.util.spec_from_file_location('cluster_probe',path);probe=importlib.util.module_from_spec(spec);sys.modules['cluster_probe']=probe;spec.loader.exec_module(probe)
f=(ROOT/'controller.lock').open('a');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
children={};last_launch={}
def expand_indices(s):
 out=[]
 for part in s.split(','):
  if '-' in part:a,b=map(int,part.split('-'));out.extend(range(a,b+1))
  else:out.append(int(part))
 return out
while not (ROOT/'STOP_CONTROLLER').exists() and not (ROOT/'complete.json').exists():
 try:
  jobs=probe.discover('guangyi.chen');decisions=[]
  for j in jobs:
   if j.state!='RUNNING':continue
   detail=subprocess.check_output(['scontrol','show','job','-o',j.job_id],text=True);fields=dict(x.split('=',1) for x in detail.split() if '=' in x)
   # Don't race an independently scheduled generation campaign's startup.
   if 'storymem_generation_' in fields.get('Command','') or 'storymem_generation_' in j.workdir:
    decisions.append(dict(job=j.job_id,skip='StoryMem dedicated scheduled campaign'));continue
   cores=int(fields['NumCPUs'])//int(fields['NumNodes'])
   if cores<4:continue
   for node in j.nodes:
    indices=j.gpu_indices.get(node)
    if indices is None:
     if j.gpu_count.get(node)==8:indices='0-7'
     else:decisions.append(dict(job=j.job_id,node=node,skip='GPU index ownership unavailable'));continue
    key=j.job_id+'_'+node
    if key in children and children[key].poll() is None:continue
    m=ROOT/'managers'/f'{key}.json'
    if m.exists() and time.time()-read(m)['heartbeat']<240:continue
    if time.time()-last_launch.get(key,0)<300:continue
    clean={k:v for k,v in os.environ.items() if not k.startswith(('SLURM_','SRUN_'))}
    cmd=['srun','--jobid='+j.job_id,'--overlap','-N1','-n1','-w',node,'-c',str(cores),'--cpu-bind=none',PY,'-u',str(ROOT/'node_manager.py'),'--indices',','.join(map(str,expand_indices(indices)))]
    log=(ROOT/'logs'/f'manager_{key}.log').open('a');proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,env=clean);log.close();children[key]=proc;last_launch[key]=time.time();decisions.append(dict(job=j.job_id,node=node,pid=proc.pid,indices=indices))
  # Terminal allocations guarantee their steps ended. Preserve failures/attempts.
  q=read(ROOT/'queue.json');activejobs={j.job_id for j in jobs}
  stale={}
  for t in q['tasks']:
   if t['status']!='running':continue
   sf=ROOT/'workers'/f'{t["worker"]}.json'
   if not sf.exists():continue
   try:
    w=read(sf);job=w['job']
   except OSError:
    continue
   if job in activejobs or job in stale:continue
   x=subprocess.run(['scontrol','show','job','-o',job],capture_output=True,text=True);mm=re.search(r'JobState=(\S+)',x.stdout)
   if mm and mm[1] in ['COMPLETED','CANCELLED','TIMEOUT','FAILED','NODE_FAIL','OUT_OF_MEMORY']:stale[job]=mm[1]
  if stale:
   with locked():
    q=read(ROOT/'queue.json')
    for t in q['tasks']:
     if t['status']!='running':continue
     w=read(ROOT/'workers'/f'{t["worker"]}.json')
     if w['job'] in stale:t.setdefault('interruptions',[]).append(dict(at=time.time(),reason='allocation_'+stale[w['job']],worker=t['worker']));t['status']='pending';t['max_attempts']=t.get('max_attempts',2)+1
    write(ROOT/'queue.json',q)
  write(ROOT/'controller_status.json',dict(pid=os.getpid(),node=os.uname().nodename,heartbeat=time.time(),jobs=[j.job_id for j in jobs],last_decisions=decisions,terminal_requeues=stale))
 except Exception:print(traceback.format_exc(),flush=True)
 for _ in range(12):
  if (ROOT/'STOP_CONTROLLER').exists() or (ROOT/'complete.json').exists():break
  time.sleep(10)

# Keep the Slurm step alive until its own children finish; do not orphan/cancel workers.
while any(p.poll() is None for p in children.values()):
 time.sleep(20)
