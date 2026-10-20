import sys,os,time,subprocess,traceback
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_gs_integrated import CPU,save,read
case=R/'runs/study4';ref=R/'references/study4_corrected';out=R/'study4_prompt_corrected';out.mkdir(exist_ok=False)
start=time.time();state=dict(status='running',started=start,stages=[],case=str(case),reference=str(ref));save(out/'runtime.json',state)
commands=[('binding',[CPU,str(B/'scripts/gs_prompt_binding.py'),'run','--case',str(case),'--registry',str(ref/'prompt_registry.json'),'--narrative',str(ref/'narrative.json'),'--out',str(out/'binding')]),('alignment',[CPU,str(B/'scripts/gs_prompt_alignment.py'),'run','--case',str(case),'--contract',str(ref/'contract.json'),'--binding',str(out/'binding/results.json'),'--out',str(out/'alignment'),'--workers','2','--input-transport','compact'])]
try:
 for name,cmd in commands:
  row=dict(stage=name,status='running',started=time.time(),command=cmd);state['stages'].append(row);save(out/'runtime.json',state)
  with (out/(name+'.log')).open('w') as log:r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
  row.update(seconds=time.time()-row['started'],returncode=r.returncode,status='success' if r.returncode==0 else 'failed');save(out/'runtime.json',state)
  if r.returncode:raise RuntimeError(name+' failed')
 state.update(status='success')
except BaseException as e:state.update(status='failed',error=repr(e),traceback=traceback.format_exc())
state.update(seconds=time.time()-start);save(out/'runtime.json',state);print(state,flush=True)
