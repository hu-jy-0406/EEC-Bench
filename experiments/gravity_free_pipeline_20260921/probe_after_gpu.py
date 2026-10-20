import json,os,sys,time
from pathlib import Path
root=Path(__file__).resolve().parent;B=root.parents[1];case=root/'corrected/study4/run';deadline=time.time()+7200
while time.time()<deadline:
 try:
  state=json.loads((case/'pipeline_runtime.json').read_text());plan=json.loads((case/'execution_plan.json').read_text())
  if state['status']=='failed':raise RuntimeError('Study4 failed; do not launch probe automatically')
  if {x['stage'] for x in plan if x['gpu']} <= {x['stage'] for x in state['stages'] if x['status']=='success'}:break
 except (FileNotFoundError,json.JSONDecodeError):pass
 time.sleep(3)
else:raise TimeoutError('GPU stages not finished')
os.environ['PYTHONPATH']=str(B/'experiments/shot_scene_boxes_goal_20260916/deps')
cmd=[sys.executable,str(B/'experiments/study2_detection_only_fresh_20260918/guard_gpu.py'),'0','GPU-bb018c40b923a974',str(B/'experiments/study_inconsistent_3/geocalib_boxer_20260913/venv/bin/python'),str(root/'gauge_probe.py')]
os.execv(cmd[0],cmd)
