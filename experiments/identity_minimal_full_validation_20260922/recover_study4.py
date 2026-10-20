"""Complete independent local reports after a rejected prompt call; no repeated VLM work."""
import sys,time,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_gs_integrated import CPU,read,save
case=R/'runs/study4';out=R/'study4_prompt_corrected';start=time.time()
state=dict(status='running',started=start,stages=[],reason='Initial binding invalid; independent successful work retained. Corrected-reference branch uses fresh validated calls.')
save(R/'study4_recovery.json',state)
while read(R/'study4_status.json')['status']=='running':time.sleep(5)
original=read(case/'pipeline_runtime.json');by={x['stage']:x for x in original['stages']}
for name in ['pair_000_identity_review','pair_000_boundary','appearance_codex','appearance_dino']:
 assert by[name]['status']=='success',(name,by[name])
cmds=[('entity_displacement',[CPU,str(B/'scripts/gs_entity_displacement.py'),'--case',str(case)]),('appearance_report',[CPU,str(B/'scripts/gs_entity_appearance_scoring.py'),'report','--runs',str(case/'appearance/compact'),'--out',str(case/'appearance/report')])]
for name,cmd in cmds:
 t=time.time()
 with (case/(name+'_recovery.log')).open('w') as log:r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
 state['stages'].append(dict(stage=name,status='success' if r.returncode==0 else 'failed',seconds=time.time()-t,command=cmd,returncode=r.returncode));save(R/'study4_recovery.json',state)
 if r.returncode:state.update(status='failed');save(R/'study4_recovery.json',state);sys.exit(1)
while read(out/'runtime.json')['status']=='running':time.sleep(5)
if read(out/'runtime.json')['status']!='success':
 state.update(status='blocked_on_corrected_prompt',seconds=time.time()-start);save(R/'study4_recovery.json',state);sys.exit(1)
cmd=[CPU,str(B/'scripts/gs_prompt_binding.py'),'report','--binding',str(out/'binding/results.json'),'--appearance-csv',str(case/'appearance/report/entities.csv'),'--out',str(out/'binding/appearance_groups.json')]
with (out/'binding_report.log').open('w') as log:r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
assert r.returncode==0
state.update(status='success',seconds=time.time()-start,selected_binding=str(out/'binding/results.json'),selected_alignment=str(out/'alignment/results.json'),initial_pipeline_status=original['status'],resumed_from_fresh_checkpoints=True,new_model_calls_in_this_recovery_script=0)
save(R/'study4_recovery.json',state);print(state,flush=True)
