"""Release only this campaign's unused source file cache after node-local copy."""
import os,socket
from campaign import ROOT
for i in range(4):
 with (ROOT/'mapped_weights'/f'{i}.safetensors').open('rb') as f:os.posix_fadvise(f.fileno(),0,0,os.POSIX_FADV_DONTNEED)
print(socket.gethostname(),'unused campaign source-cache release hint issued',flush=True)
