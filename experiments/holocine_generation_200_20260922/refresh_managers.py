# Refresh only this campaign's pre-validation idle managers after a path-check fix.
import os,signal,subprocess
from campaign import ROOT
assert not (ROOT/'mapped_validation.json').exists()
for line in subprocess.check_output(['ps','-u',str(os.getuid()),'-o','pid=,args='],text=True).splitlines():
 pid,_,cmd=line.strip().partition(' ')
 if str(ROOT/'node_manager.py') in cmd and '--indices' in cmd and 'srun ' not in cmd:
  args=open('/proc/'+pid+'/cmdline','rb').read().split(b'\0')
  if str(ROOT/'node_manager.py').encode() in args:os.kill(int(pid),signal.SIGTERM);print('refreshed_manager',pid)
