"""Inspect only this allocation; add genuinely idle allocated GPUs with CPU/RAM headroom."""
import argparse,fcntl,json,os,socket,subprocess,time,traceback
from pathlib import Path
from campaign import ROOT,PY,read,write,locked
p=argparse.ArgumentParser();p.add_argument('--indices',required=True);args=p.parse_args();indices=[int(x) for x in args.indices.split(',')]
node=socket.gethostname();job=os.environ['SLURM_JOB_ID']; EXCLUDED_HOLOCINE_NODES={'auh7-1b-gpu-208','auh7-1b-gpu-209','auh7-1b-gpu-241'}
if node in EXCLUDED_HOLOCINE_NODES:
 while not (ROOT/'STOP').exists() and not (ROOT/'complete.json').exists():
  write(ROOT/'managers'/f'{job}_{node}.json',dict(node=node,job=job,state='excluded_user_directed',reason='Reserved for another user-directed task',heartbeat=time.time(),allowed_indices=indices));time.sleep(20)
 raise SystemExit(0)
lock=ROOT/'manager_locks'/f'{job}_{node}';lock.parent.mkdir(exist_ok=True);f=lock.open('a')
try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:raise SystemExit('Manager already exists')
children={};launches={};rounds=0
while not (ROOT/'STOP').exists() and not (ROOT/'complete.json').exists():
 try:
  # Mapped transport is required before broad expansion.
  if not (ROOT/'staged_mmap_equivalence.json').exists():time.sleep(20);continue
  assert read(ROOT/'staged_mmap_equivalence.json')['pass_all']
  if not (ROOT/'staged_memory_pilot.json').exists():time.sleep(20);continue
  assert read(ROOT/'staged_memory_pilot.json')['pass_all']
  subprocess.run([PY,str(ROOT/'node_probe.py')],stdout=subprocess.DEVNULL,check=True,timeout=60)
  inv=read(ROOT/'inventory'/f'{node}.json');assert inv['job_id']==job
  state=[]
  for sf in (ROOT/'workers').glob('*.json'):
   w=read(sf)
   if w['node']!=node:continue
   proc=Path('/proc')/str(w['pid'])
   alive=proc.exists() and (proc/'cmdline').read_bytes().find(b'holocine_generation_200_20260922/campaign.py')>=0
   if alive:state.append(w)
   else:
    # Dead process proof on its original node, before reclaiming tasks.
    with locked():
     q=read(ROOT/'queue.json');changed=False
     for t in q['tasks']:
      if t['status']=='running' and t['worker']==w['worker']:
       t.setdefault('interruptions',[]).append(dict(at=time.time(),reason='worker_process_exited',worker=w['worker'],attempt=t['attempts']))
       t['status']='pending' if t['attempts']<t.get('max_attempts',2) else 'failed';changed=True
     if changed:write(ROOT/'queue.json',q)
  usedcpus={c for w in state for c in w.get('cpus',[])}
  if node.endswith('-306'):usedcpus.update(range(56,64))
  physical={}
  for c in inv['allowed_cpus']:
   t=Path(f'/sys/devices/system/cpu/cpu{c}/topology');key=((t/'physical_package_id').read_text(),(t/'core_id').read_text());physical.setdefault(key,[]).append(c)
  choices=[]
  for cs in physical.values():
   if any(c in usedcpus for c in cs):continue
   busy=max(inv['cpu_busy_percent'].get(str(c),100) for c in cs)
   if busy<=20:choices.append((busy,min(cs)))
  choices.sort();cpu=[c for _,c in choices]
  cap=int(inv['memory']['memory.max']);stats=dict(x.split() for x in inv['memory']['memory.stat'].splitlines());anon=int(stats['anon'])
  # Extra5GiB per new worker and10GiB shared/transient margin; never raise job limits.
  slots=max(0,int((cap*.9-anon-10*2**30)//(5*2**30)));idle=[]
  for card in inv['cards']:
   idx=int(card['card'][4:]);name=f'node{node.rsplit("-",1)[-1]}_gpu{idx}'
   if idx not in indices or any(w['uuid']==card['uuid'] for w in state):continue
   if card['util_max']!=0 or card['vram_used_mib']>=95 or card['kfd_processes']:continue
   if name in children and children[name].poll() is None:continue
   if launches.get(name,0)>=2:continue
   idle.append(card)
  decisions=[]
  q=read(ROOT/'queue.json')
  if not any(t['status']=='pending' for t in q['tasks']):idle=[]
  policy=read(ROOT/'resource_policy.json') if (ROOT/'resource_policy.json').exists() else {}
  node_cap=policy.get('low_memory_node_worker_cap',8) if cap<128*2**30 else 8
  launch_cards=idle[:min(slots,len(cpu)//4,max(0,node_cap-len(state)))]
  if launch_cards and not (Path('/tmp/eecbench_holocine200_bf16_shared_v3')/'verified.json').exists():
   subprocess.run(['taskset','-c',str(cpu[0]),PY,'-u',str(ROOT/'local_cache.py')],check=True)
   # Restart inspection after lengthy copying; no GPU launches on stale evidence.
   if not (ROOT/'local_cache_audits'/f'{node}.json').exists():raise RuntimeError('Missing local cache proof')
   continue
  for card in launch_cards:
   idx=int(card['card'][4:]);name=f'node{node.rsplit("-",1)[-1]}_gpu{idx}';aff=cpu[:4];cpu=cpu[4:]
   log=(ROOT/'logs'/f'{name}.log').open('a');cmd=[PY,str(ROOT/'lease_guard.py'),str(idx),card['uuid'],'taskset','-c',','.join(map(str,aff)),PY,'-u',str(ROOT/'campaign.py'),'worker','--worker',name,'--mode','mapped']
   proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL);log.close();children[name]=proc;launches[name]=launches.get(name,0)+1
   decisions.append(dict(worker=name,pid=proc.pid,cpus=aff,uuid=card['uuid'],time=time.time()));time.sleep(3)
  write(ROOT/'managers'/f'{job}_{node}.json',dict(node=node,job=job,pid=os.getpid(),heartbeat=time.time(),allowed_indices=indices,active_workers=len(state),memory_anon=anon,memory_cap=cap,last_launches=decisions,launch_counts=launches,eligible_idle=len(idle),cpu_slots=len(choices)//4,memory_slots=slots))
 except Exception:
  print(traceback.format_exc(),flush=True);write(ROOT/'managers'/f'{job}_{node}_error.json',dict(time=time.time(),error=traceback.format_exc()))
 for _ in range(12):
  if (ROOT/'STOP').exists() or (ROOT/'complete.json').exists():break
  time.sleep(10)

# Keep the Slurm step alive until its own children finish; do not orphan/cancel workers.
while any(p.poll() is None for p in children.values()):
 time.sleep(20)
