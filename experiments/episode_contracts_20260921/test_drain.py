import concurrent.futures,json,os,signal,subprocess,sys,tempfile,time
from pathlib import Path
if len(sys.argv)>1:
 path=Path(sys.argv[1])
 def job(i):
  with path.open('a') as f:f.write(json.dumps(['start',i])+'\n')
  time.sleep(1)
  with path.open('a') as f:f.write(json.dumps(['end',i])+'\n')
 try:
  with concurrent.futures.ThreadPoolExecutor(max_workers=4) as p:list(p.map(job,range(30)))
 except KeyboardInterrupt:pass
else:
 with tempfile.TemporaryDirectory() as td:
  path=Path(td)/'events'
  p=subprocess.Popen([sys.executable,__file__,str(path)])
  while not path.exists() or len(path.read_text().splitlines())<4:time.sleep(.01)
  p.send_signal(signal.SIGINT);p.wait(timeout=10)
  events=[json.loads(s) for s in path.read_text().splitlines()]
  starts=[i for t,i in events if t=='start'];ends=[i for t,i in events if t=='end']
  assert len(starts)==4 and sorted(starts)==sorted(ends)
  print(json.dumps(dict(status='pass',running_jobs_finished=4,queued_jobs_cancelled=26,child_jobs_interrupted=0)))
