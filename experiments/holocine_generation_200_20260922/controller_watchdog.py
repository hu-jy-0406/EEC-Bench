"""Lightweight login-node supervisor; all model/probe/copy work stays in existing compute allocations."""
import fcntl,os,subprocess,time
from campaign import ROOT,PY,read,write
with (ROOT/'watchdog.lock').open('a') as own:
 try:fcntl.flock(own,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:raise SystemExit('watchdog already running')
 child=None
 while not (ROOT/'STOP_CONTROLLER').exists() and not (ROOT/'complete.json').exists():
  status=read(ROOT/'controller_status.json') if (ROOT/'controller_status.json').exists() else {}
  write(ROOT/'watchdog_status.json',dict(pid=os.getpid(),heartbeat=time.time(),controller_heartbeat=status.get('heartbeat'),host=os.uname().nodename))
  if time.time()-status.get('heartbeat',0)>300 and (child is None or child.poll() is not None):
   # Child controller takes the global nonblocking flock. Never start a second owner.
   with (ROOT/'logs/controller_watchdog.log').open('a') as log:
    child=subprocess.Popen([PY,'-u',str(ROOT/'controller.py')],stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
  time.sleep(30)
 if child is not None:child.wait()
