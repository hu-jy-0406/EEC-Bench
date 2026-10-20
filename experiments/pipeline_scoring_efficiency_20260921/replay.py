"""Fresh API component comparison on frozen Study3 frontend, not end-to-end."""
import copy,json,os,shutil,subprocess,sys,time,traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parent;B=ROOT.parents[1];sys.path.insert(0,str(B/'scripts'))
import run_gs_temporal_stage as stage
import gs_prompt_alignment as alignment
from gs_temporal_review import validate_checks
from gs_temporal_core import aggregate
from gs_entity_appearance_compact import cost
from run_isolated_shot_static_3d import owned_compute_job
BASE=B/'experiments/study3_final_integrated_20260921/run';PAIR=BASE/'pairs/pair_000'
read,save=stage.read,stage.save

def identity():
    out=ROOT/'identity';out.mkdir()
    for name in ('inputs','selected'):
        shutil.copytree(PAIR/name,out/name)
    for name in ('narrative.json','registration/roma_geometry/registration.json','matching_initial.json'):
        p=out/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(PAIR/name,p)
    shutil.copy2(out/'matching_initial.json',out/'matching.json')
    command=[sys.executable,str(B/'scripts/run_gs_flow1_stage.py'),str(out),'review_identity','--runtime-profile','scoring_efficiency_v1']
    with (out/'console.log').open('w') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    old=read(PAIR/'matching.json');new=read(out/'matching.json')
    def population(m):return sorted([(tuple(g['a_ids']),tuple(g['b_ids']),g['identity']) for g in m['groups']])
    oldp,newp=population(old),population(new)
    return dict(population_equal=oldp==newp,old_only=[r for r in oldp if r not in newp],new_only=[r for r in newp if r not in oldp],
                anchors_equal=old['structural_anchor_group_ids']==new['structural_anchor_group_ids'],old_groups=len(oldp),new_groups=len(newp))

def presence():
    out=ROOT/'presence';out.mkdir();shutil.copy2(PAIR/'narrative.json',out/'narrative.json')
    s=stage.Stage(out,'scoring_efficiency_v1');payload=read(PAIR/'calls/boundary_review_000/input.json')
    images=sum([stage.Stage(PAIR,'temporal_spatial_v1').source_images(sid)[1] for sid in ('shot1','shot3')],[])
    raw=s.review_events('boundary_review',payload,images)
    proposals=read(PAIR/'boundary/proposals.json');proposals['events']=[e for e in proposals['events'] if e['kind']=='presence']
    checks=validate_checks(raw,proposals,images,s.story,boundary=True,presence_only_schema=True)
    oldchecks={e['event_id']:e for e in read(PAIR/'boundary/results.json')['events'] if e['kind']=='presence'}
    result=dict(summary=aggregate(proposals['presence_units'],checks),checks=checks,
        differences=[dict(event_id=k,old=oldchecks[k]['status'],new=v['status'],old_reason=oldchecks[k]['review']['reason'],new_reason=v['review']['reason']) for k,v in checks.items() if oldchecks[k]['status']!=v['status']],
        old_conflicts=sorted(k for k,v in oldchecks.items() if v['status']=='conflict'),new_conflicts=sorted(k for k,v in checks.items() if v['status']=='conflict'))
    save(out/'results.json',result);return {k:v for k,v in result.items() if k!='checks'}

def prompt_alignment():
    out=ROOT/'alignment';result=alignment.run(BASE,BASE/'prompt_alignment_reference/contract.json',BASE/'prompt_binding/results.json',out,workers=2,input_transport='compact')
    old=read(BASE/'prompt_alignment/results.json');oldrows={r['claim_id']:r for r in old['checks']}
    return dict(dimensions={k:dict(old=old['dimensions'][k]['score'],new=v['score'],old_counts=old['dimensions'][k]['micro'],new_counts=v['micro']) for k,v in result['dimensions'].items()},
        differences=[dict(claim_id=r['claim_id'],old=oldrows[r['claim_id']]['status'],new=r['status'],old_reason=oldrows[r['claim_id']]['reason'],new_reason=r['reason']) for r in result['checks'] if r['status']!=oldrows[r['claim_id']]['status']])

def main():
    owned_compute_job();started=time.time();state=dict(status='running',started=started,pid=os.getpid(),allocation=os.environ['SLURM_JOB_ID'],frozen_frontend_reuse=True,components={})
    save(ROOT/'replay_status.json',state)
    def run(name,fn):
        start=time.time()
        try:
            result=fn();return dict(status='success',seconds=time.time()-start,result=result)
        except BaseException as exc:return dict(status='failed',seconds=time.time()-start,error=repr(exc),traceback=traceback.format_exc())
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={k:pool.submit(run,k,fn) for k,fn in [('identity',identity),('presence',presence),('alignment',prompt_alignment)]}
        for name,f in futures.items():state['components'][name]=f.result();save(ROOT/'replay_status.json',state)
    calls=[]
    for component in ('identity','presence','alignment'):
        for path in sorted((ROOT/component/'calls').glob('*/status.json')):
            s=read(path);us=s.get('usage',s.get('known_usage',[]));us=[us] if isinstance(us,dict) else us
            calls.append(dict(component=component,call=path.parent.name,status=s['status'],seconds=s['seconds'],usage=us,
                tokens=sum(u.get('input_tokens',0)+u.get('output_tokens',0) for u in us),standard_api_equivalent_usd=cost(us)))
    state.update(status='success' if all(v['status']=='success' for v in state['components'].values()) else 'failed',seconds=time.time()-started,calls=calls,
        total_tokens=sum(c['tokens'] for c in calls),standard_api_equivalent_usd=sum(c['standard_api_equivalent_usd'] for c in calls),not_a_bill=True)
    save(ROOT/'replay_status.json',state);print(json.dumps(state,ensure_ascii=False,indent=2))
    if state['status']!='success':raise SystemExit(1)
if __name__=='__main__':main()
