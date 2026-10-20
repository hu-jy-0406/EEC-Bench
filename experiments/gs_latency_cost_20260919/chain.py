"""Fresh sequential model stages over explicitly frozen detector/3D/keypoint evidence."""
import argparse,copy,json,shutil,sys,time,hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
H=Path(__file__).resolve().parent;B=H.parents[1];sys.path.insert(0,str(B/'scripts'))
import transport as efficient
import gs_flow1_evaluator as flow
import run_partial_scene_comparison as canonical
import run_gs_motion_fusion as motion
from run_isolated_shot_static_3d import owned_compute_job
C=B/'experiments/study2_integrated_full_fresh_20260919/study2'
def read(p):return json.loads(p.read_text())
def sig(m):return sorted((tuple(g['a_ids']),tuple(g['b_ids']),g['identity'],g['anchor_eligible']) for g in m['groups'])
def signatures(case):
 m=read(case/'matching.json');gs={g['group_id']:(tuple(g['a_ids']),tuple(g['b_ids'])) for g in m['groups']}
 p=read(case/'presence.json');sp=read(case/'spatial.json')
 return dict(identity=sig(m),presence=sorted((gs[r['group_id']],r['status'],r['cause'],r['conflict_kind'],r['joint_presence_reasonable']) for r in p['groups']),spatial=sorted((tuple(sorted(gs[k] for k in r['endpoint_groups'])),r['status'],r['reason']) for r in sp['relations']),presence_score=p['summary'],spatial_score=sp['summary'],negative_count=sp['negative_proposals'],support_pass=sp['support_pass'])
def main():
 p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--model',default='gpt-5.6-luna');p.add_argument('--reasoning',default='low');a=p.parse_args();allocation=owned_compute_job();out=H/a.name;out.mkdir(exist_ok=False)
 # Frozen numerical inference is shared read-only; no old model verdicts are input.
 for name in ['inputs','pi3x']:(out/name).symlink_to(C/name,target_is_directory=True)
 shutil.copy2(C/'narrative.json',out/'narrative.json');(out/'registration/roma_geometry').mkdir(parents=True)
 shutil.copy2(C/'registration/roma_geometry/registration.json',out/'registration/roma_geometry/registration.json')
 provenance=dict(frozen_evidence_source=str(C),reused=['WeDetect candidates and validated clustering','GeoCalib','Pi3X','Boxer','RoMa points and registration (subject to exact anchor membership check)'],fresh=['isolated motion','initial identity','aligned identity','single B','local witnesses','Prompt verification'],model=a.model,reasoning=a.reasoning,allocation=allocation)
 flow.save(out/'provenance.json',provenance)
 def routed(stage,prompt,payload,images,schema,args):
  args.model=a.model;args.reasoning=a.reasoning
  return efficient.call(stage,canonical.PROMPTS/prompt,payload,images,schema,args)
 canonical.call=routed;start=time.time();stages=[]
 def stage(name,fn):
  t=time.time();print('START',name,flush=True);fn();stages.append(dict(stage=name,seconds=time.time()-t));flow.save(out/'timing.json',dict(seconds=time.time()-start,stages=stages));print('END',name,stages[-1]['seconds'],flush=True)
 def motions():
  with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda s:motion.run(str(out),s),['shot1','shot3']))
 stage('motion_and_fusion',motions)
 for sid in ['shot1','shot3']:
  new=read(out/'selected'/f'{sid}_scene.json');old=read(C/'selected'/f'{sid}_scene.json')
  assert [(e['entity_id'],e['motion_status'],e['geometry']) for e in new['entities']]==[(e['entity_id'],e['motion_status'],e['geometry']) for e in old['entities']], 'Frozen registration prerequisites changed: recompute numerical stages before continuing'
 e=flow.Eval(str(out));stage('initial_identity',e.match)
 new=read(out/'matching.json');old=read(C/'matching_initial.json')
 for key in ['structural_anchor_group_ids','local_origin_group_id','local_reference_group_id']:assert new[key]==old[key], 'Changed anchor selection requires fresh registration'
 ng={g['group_id']:g for g in new['groups']};og={g['group_id']:g for g in old['groups']}
 for gid in old['structural_anchor_group_ids']:
  for key in ['a_ids','b_ids','identity','anchor_eligible']:assert ng[gid][key]==og[gid][key], 'Changed anchor identity requires fresh registration'
 stage('aligned_identity_review',e.review_identity);stage('presence',e.presence);stage('spatial',e.spatial)
 quality={k:signatures(out)[k]==signatures(C)[k] for k in signatures(C)}
 flow.save(out/'quality.json',dict(comparison=quality,actual=signatures(out),baseline=signatures(C)))
 print('QUALITY',quality,flush=True)
if __name__=='__main__':main()
