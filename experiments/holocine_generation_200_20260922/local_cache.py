"""One verified local copy per node; never share writable ROCm host pages across nodes."""
import fcntl,hashlib,os,shutil,socket,time
from pathlib import Path
from campaign import ROOT,read,write
CACHE=Path('/tmp/eecbench_holocine200_bf16_shared_v3')
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024**2),b''):h.update(b)
 return h.hexdigest()
def prepare():
 CACHE.mkdir(exist_ok=True)
 with (CACHE/'prepare.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  proof=read(ROOT/'mapped_weights/complete.json');assert proof['all_tensors_equal_official_bf16']
  sizes={str(i):row['destination_bytes'] for i,row in enumerate(proof['proof'])}
  marker=CACHE/'verified.json'
  if marker.exists():
   audit=read(marker)
   assert audit['source_proof']==proof
   assert all((CACHE/f'{i}.safetensors').stat().st_size==n for i,n in sizes.items())
   return CACHE
  free=shutil.disk_usage(CACHE).free
  remote_low=free<=sum(sizes.values())+20*2**30
  required=sum(sizes.values())-(sizes['2'] if remote_low else 0)
  assert free>required+8*2**30,'Insufficient local storage even with node-private low expert'
  fallback=ROOT/'node_private_weights'/socket.gethostname()
  if remote_low:fallback.mkdir(parents=True,exist_ok=True)
  rows=[]
  for i,n in sizes.items():
   source=ROOT/'mapped_weights'/f'{i}.safetensors';dest=(fallback if remote_low and i=='2' else CACHE)/f'{i}.safetensors';partial=dest.with_suffix('.partial')
   start=time.time();h=hashlib.sha256()
   with source.open('rb') as inp,partial.open('wb') as out:
    for b in iter(lambda:inp.read(8*1024**2),b''):h.update(b);out.write(b)
    out.flush();os.fsync(out.fileno())
   assert partial.stat().st_size==n
   actual=digest(partial);assert actual==h.hexdigest()
   os.replace(partial,dest)
   if dest.parent!=CACHE:(CACHE/dest.name).symlink_to(dest)
   rows.append(dict(file=dest.name,bytes=n,sha256=actual,seconds=time.time()-start))
   with source.open('rb') as old:os.posix_fadvise(old.fileno(),0,0,os.POSIX_FADV_DONTNEED)
   print('LOCAL_CACHE_VERIFIED',i,rows[-1],flush=True)
  audit=dict(node=socket.gethostname(),source_proof=proof,files=rows,created=time.time(),path=str(CACHE),node_private_low_expert=remote_low)
  write(marker,audit);write(ROOT/'local_cache_audits'/f'{socket.gethostname()}.json',audit)
 return CACHE
if __name__=='__main__':print(prepare(),flush=True)
