"""Finish this one experiment's report after the already-running driver exits."""
import json,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CASE=ROOT/'run01'
while True:
 state=json.loads((CASE/'pipeline_runtime.json').read_text())
 if state['status']!='running':break
 time.sleep(20)
if state['status']=='success':
 raise SystemExit(subprocess.call(['/vast/users/guangyi.chen/anaconda3/bin/python',str(ROOT/'report.py')]))
usage=[]
for p in CASE.glob('**/gemini_usage.json'):
 usage.append(dict(call=str(p.parent.relative_to(CASE)),**json.loads(p.read_text())['normalized']))
(ROOT/'failure_usage.json').write_text(json.dumps(usage,indent=2)+'\n')
with (ROOT/'REPORT.md').open('a') as f:
 f.write('\n\nRun stopped before full completion: '+str(state.get('error'))+'\nNo completed final scores are claimed. Raw responses and usage are retained.\n')
raise SystemExit(1)
