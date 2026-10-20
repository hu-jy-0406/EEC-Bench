"""Verify stage/call concurrency and compare measured old/new runs."""
import json,sys
from pathlib import Path
R=Path(__file__).resolve().parent;sys.path.insert(0,str(R.parents[1]/'scripts'))
import run_gs_temporal as m
old=R.parent/'study3_appearance_full_20260921/run';new=R/'run'
def intervals(rows):
 edges=[]
 for r in rows:
  if 'started' not in r:continue
  end=r.get('ended',r.get('finished',r['started']+r.get('seconds',0)))
  edges.extend([(r['started'],1),(end,-1)])
 n=peak=0
 for _,delta in sorted(edges):n+=delta;peak=max(n,peak)
 return peak

def main():
 old_s=m.read(old/'summary.json');new_s=m.read(new/'summary.json');rt=m.read(new/'pipeline_runtime.json')
 assert rt['status']==new_s['status']=='success'
 by={x['stage']:x for x in rt['stages']}
 for row in by.values():
  for dep in row['depends']:
   assert by[dep]['started']+by[dep]['seconds'] <= row['started']+.05,(dep,row['stage'])
 gpu=sorted([x for x in by.values() if x['gpu']],key=lambda x:x['started'])
 for a,b in zip(gpu,gpu[1:]):assert a['started']+a['seconds']<=b['started']+.05
 states=[m.read(new/x['call']/'status.json') for x in new_s['calls']]
 api_peak=intervals(states);assert api_peak<=8,api_peak
 actual_overlap=lambda a,b:min(a['started']+a['seconds'],b['started']+b['seconds'])-max(a['started'],b['started'])
 assert actual_overlap(by['pi3x_shot3'],by['expected_motion_shot1'])>0
 assert actual_overlap(by['appearance_dino'],by['appearance_codex'])>0
 calls={Path(x['call']).name:m.read(new/x['call']/'status.json') for x in new_s['calls']}
 assert actual_overlap(calls['boundary_review_000'],calls['boundary_local_shot1'])>0
 assert actual_overlap(calls['boundary_review_000'],calls['boundary_spatial_verify'])>0
 legacy=m.plan(old,m.read(old/'raw_manifest.json')['shots'],6,'GPU-9bd66cc06860c5b4',schedule_name='legacy')
 saved=m.read(old/'execution_plan.json')
 assert [{k:v for k,v in x.items() if k!='api_slots'} for x in legacy]==saved
 result=dict(passed=True,legacy_exact_plan_restored=True,gpu_peak=1,api_peak=api_peak,
   gpu_stage_count=len(gpu),all_dependency_barriers_passed=True,
   old=dict(seconds=old_s['elapsed_seconds'],tokens=old_s['total_tokens'],usd=old_s['standard_api_equivalent_usd']),
   new=dict(seconds=new_s['elapsed_seconds'],tokens=new_s['total_tokens'],usd=new_s['standard_api_equivalent_usd']),
   wall_reduction_percent=100*(1-new_s['elapsed_seconds']/old_s['elapsed_seconds']),
   comparisons_are_two_fresh_stochastic_runs=True,
   timings={n:dict(old_seconds=next(x['seconds'] for x in old_s['stages'] if x['stage']==n),new_seconds=by[n]['seconds'])
            for n in ('pair_000_identity_review','pair_000_boundary','appearance_codex','appearance_dino')})
 m.save(R/'scheduling_audit.json',result);print(json.dumps(result,indent=2))
if __name__=='__main__':main()
