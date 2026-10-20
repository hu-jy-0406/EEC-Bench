import sys,time,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_gs_integrated import read,save,CPU
out=R/'study4_prompt_recovery_v2';out.mkdir(exist_ok=False);case=R/'runs/study4';ref=R/'references/study4_corrected'
start=time.time();state=dict(status='running',started=start,stages=[]);save(out/'runtime.json',state)
commands=[('binding',[CPU,str(R/'strict_binding.py')]),('alignment',[CPU,str(B/'scripts/gs_prompt_alignment.py'),'run','--case',str(case),'--contract',str(ref/'contract.json'),'--binding',str(out/'binding/results.json'),'--out',str(out/'alignment'),'--workers','2','--input-transport','compact']),('binding_report',[CPU,str(B/'scripts/gs_prompt_binding.py'),'report','--binding',str(out/'binding/results.json'),'--appearance-csv',str(case/'appearance/report/entities.csv'),'--out',str(out/'binding/appearance_groups.json')])]
for name,cmd in commands:
 t=time.time();row=dict(stage=name,status='running',started=t,command=cmd);state['stages'].append(row);save(out/'runtime.json',state)
 with (out/(name+'.log')).open('w') as log:r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
 row.update(status='success' if r.returncode==0 else 'failed',seconds=time.time()-t,returncode=r.returncode);save(out/'runtime.json',state)
 if r.returncode:break
state.update(status='success' if all(x['status']=='success' for x in state['stages']) else 'failed',seconds=time.time()-start);save(out/'runtime.json',state);print(state,flush=True)
