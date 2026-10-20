#!/usr/bin/env python3
"""Fail closed idle-GPU guard; bind by UUID, never ROCr physical ordinal."""
import json,os,re,subprocess,sys,time,tempfile
from pathlib import Path
idx=int(sys.argv[1]);uuid=sys.argv[2];cmd=sys.argv[3:]
def run(args):return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT)
text=run(['rocm-smi','-d',str(idx),'--showuse','--showmeminfo','vram','--showuniqueid'])
print(text,flush=True)
use=re.search(r'GPU\['+str(idx)+r'\].*GPU use \(%\):\s*(\d+)',text)
mem=re.search(r'VRAM Total Used Memory \(B\):\s*(\d+)',text)
actual=re.search(r'GPU\['+str(idx)+r'\].*Unique ID:\s*0x([0-9a-fA-F]+)',text)
shared=os.environ.get('EECBENCH_ALLOW_SHARED_GPU')=='1'
if not(use and mem and actual and re.fullmatch(r'GPU-[0-9a-fA-F]{16}',uuid) and int(use[1])==0 and int(actual[1],16)==int(uuid[4:],16) and (shared or int(mem[1])<100_000_000)):raise SystemExit('GPU not idle or UUID mismatch')
pids=run(['rocm-smi','--showpids']);print(pids,flush=True)
for pid in re.findall(r'^\s*(\d+)\s+',pids,re.M):
 mapping=run(['rocm-smi','--showpidgpus',pid]);print(mapping,flush=True)
 m=re.search(r'DRM device\(s\):\s*\n([0-9 ]+)',mapping)
 if not m:
  if re.search(r'is using 0 DRM device',mapping):continue
  refreshed=run(['rocm-smi','--showpids'])
  if pid not in re.findall(r'^\s*(\d+)\s+',refreshed,re.M):
   print('Process exited during inspection; absent from fresh KFD snapshot',pid,flush=True);continue
  raise SystemExit('Cannot verify process GPU mapping')
 if idx in [int(x) for x in m[1].split()] and not shared:raise SystemExit('Resident GPU process')
os.environ['ROCR_VISIBLE_DEVICES']=uuid
for k in ['HIP_VISIBLE_DEVICES','CUDA_VISIBLE_DEVICES']:os.environ.pop(k,None)
# Per-invocation MIOpen cache prevents an unrelated resident workload from
# locking the shared default /tmp database on a deliberately shared GPU.
miopen=Path(tempfile.mkdtemp(prefix='eec-miopen-'))
os.environ['MIOPEN_USER_DB_PATH']=str(miopen/'user-db')
os.environ['MIOPEN_CUSTOM_CACHE_DIR']=str(miopen/'cache')
Path(os.environ['MIOPEN_USER_DB_PATH']).mkdir(parents=True,exist_ok=True)
Path(os.environ['MIOPEN_CUSTOM_CACHE_DIR']).mkdir(parents=True,exist_ok=True)
os.environ['OMP_NUM_THREADS']='4';os.environ['MKL_NUM_THREADS']='4'
print('GUARD PASS',time.time(),'physical',idx,'UUID',uuid,flush=True)
os.execvp(cmd[0],cmd)
