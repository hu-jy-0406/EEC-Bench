"""Drain only the verified owned coordinator; preserve all running episode jobs."""
import json,os,signal,time
from pathlib import Path
import run
run.io.safe_compute()
old=3988866
cmd=Path(f'/proc/{old}/cmdline').read_bytes().replace(b'\0',b' ').decode()
assert 'episode_contracts_20260921/run.py run --skip-pilot --workers 32' in cmd
assert Path(f'/proc/{old}').stat().st_uid==os.getuid()
rows=[dict(pid=old,start_ticks=Path(f'/proc/{old}/stat').read_text().split()[21],role='old32')]
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  cmd=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode()
  if 'python EECBench/experiments/episode_contracts_20260921/reconcile_pilot.py' in cmd and p.stat().st_uid==os.getuid():rows.append(dict(pid=int(p.name),start_ticks=(p/'stat').read_text().split()[21],role='pilot_reconciliation'))
 except (FileNotFoundError,PermissionError,ProcessLookupError):pass
assert len(rows)<=2
run.dump(run.HERE/'scaling.json',dict(created=time.time(),drain_processes=rows,initial_api_slots=32-(len(rows)-1),target_api_slots=64,reason='User requested fastest bounded parallel execution preserving quality',drain_test='test_drain.py: active4 completed, queued26 cancelled,0child interruptions'))
(runtime:=run.HERE/'runtime.json').replace(run.HERE/'runtime_32.json')
os.kill(old,signal.SIGINT)
time.sleep(3)
print(json.dumps(dict(status='draining_original_only',processes=rows)))
