"""Incremental direct-to-prototype FPS32. Numeric attachment is provisional."""
import sys,os,time,json,subprocess,math
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_gs_integrated import read,save,S,REG,CPU,GEOM,FRONT
from run_gs_temporal_stage import prepare_pair

def projected_matching(case,root,sid,glob):
 groups=[];anchors=[]
 for gg in glob['groups']:
  a=[x for x in gg['entity_ids'] if x.startswith(root+'/')];b=[x for x in gg['entity_ids'] if x.startswith(sid+'/')]
  if not a and not b:continue
  gid=f'g{len(groups)+1:02d}';eligible=bool(a and b and any({p['shot_a'],p['shot_b']}=={root,sid} for p in gg['anchor_pairs']))
  groups.append(dict(group_id=gid,a_ids=['shot1/'+x.split('/')[-1] for x in a],b_ids=['shot3/'+x.split('/')[-1] for x in b],identity='matched' if a and b else 'unmatched',anchor_eligible=eligible,identity_evidence=gg['identity_evidence'],anchor_reason=next((p['reason'] for p in gg['anchor_pairs'] if {p['shot_a'],p['shot_b']}=={root,sid}),''),global_group_id=gg['group_id']))
  if eligible:anchors.append(gid)
 return dict(groups=groups,structural_anchor_group_ids=anchors,local_origin_group_id='',local_reference_group_id='',scene_correspondence='scene-wide initial identity projected to requested pair',limitations='Initial identity, not final aligned review. Missing projection is unknown; unresolved associations preserved in global input.')

def feasible(case,root,sid,m):
 nodes={s:{e['entity_id']:e for e in read(case/'selected'/f'{s}_scene.json')['entities']} for s in [root,sid]}
 for g in m['groups']:
  if not g['anchor_eligible']:continue
  ok=True
  for side,s in [('a',root),('b',sid)]:
   e=nodes[s][s+'/'+g[side+'_ids'][0].split('/')[-1]]
   ok &= e['motion_status']=='static' and bool(e['geometry']) and any(r.get('geometry') and r.get('box_xyxy') is not None for r in e['frame_evidence'])
  if ok:return True
 return False

def run(case,gpu,uuid):
 glob=read(case/'global_initial/results.json');sids=[s['shot_id'] for s in read(case/'raw_manifest.json')['shots']];roots=[sids[0]];rows=[dict(shot_id=sids[0],prototype=sids[0],status='root',fit=None)];attempts=[];start=time.time()
 def command(cmd,pair,label):
  t=time.time();env=os.environ.copy();env.update(CASE_ROOT=str(pair),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='4',PYTHONPATH=str(B/'experiments/shot_scene_boxes_goal_20260916/deps'))
  for k,n in [('MIOPEN_USER_DB_PATH','miopen_db'),('MIOPEN_CUSTOM_CACHE_DIR','miopen_cache'),('MPLCONFIGDIR','matplotlib')]:env[k]=str(case/'runtime_cache'/n)
  with (pair/(label+'.log')).open('w') as f:p=subprocess.run(list(map(str,cmd)),env=env,stdout=f,stderr=subprocess.STDOUT)
  return dict(stage=label,seconds=time.time()-t,returncode=p.returncode)
 for sid in sids[1:]:
  attached=False
  for root in roots:
   m=projected_matching(case,root,sid,glob);a=dict(root=root,shot=sid,anchors=m['structural_anchor_group_ids'],stages=[]);attempts.append(a)
   if not feasible(case,root,sid,m):a['status']='skip_no_usable_static_anchor';continue
   pid=root+'_'+sid;prepare_pair(case,pid,[root,sid]);pair=case/'pairs'/pid;save(pair/'matching.json',m);a['case']=str(pair)
   stages=[('roma',[CPU,FRONT/'guard_gpu.py',gpu,uuid,GEOM,REG/'run_matching.py','--method','roma']),('lift',[GEOM,REG/'prepare_correspondences.py','--method','roma']),('fit',[GEOM,S/'register_gs_3d.py','--method','roma','--sampling','fps','--sample-count','32'])]
   for label,cmd in stages:
    r=command(cmd,pair,label);a['stages'].append(r)
    if r['returncode']:break
   if r['returncode']:
    a['status']='failed_'+label
    # Insufficient valid correspondence is an experimental geometric failure; other errors abort.
    if label=='fit' and 'Fewer than three valid pairs' in (pair/'fit.log').read_text():continue
    raise RuntimeError((pair,label))
   fit=read(pair/'registration/roma_geometry/registration.json')['fits']['all_structures'];d=np.load(pair/'registration/roma_geometry/correspondences.npz')['data']
   finite=all(math.isfinite(v) for v in [fit['scale'],*fit['translation'],*np.array(fit['rotation']).ravel()]);ranks=[int(np.linalg.matrix_rank(d[:,k:k+3]-d[:,k:k+3].mean(0))) for k in (7,10)];a['geometry_ranks']=ranks
   if not finite or min(ranks)<2 or not fit['selected_solver_success']:
    a['status']='rejected_degenerate_or_solver_failed';continue
   a['status']='numeric_candidate';rows.append(dict(shot_id=sid,prototype=root,status='numeric_candidate',fit=fit,pair_case=str(pair)));attached=True;break
  if not attached:roots.append(sid);rows.append(dict(shot_id=sid,prototype=sid,status='root_unregistered',fit=None))
  save(case/'optimization/results.json',dict(method='roma_fps32_incremental',status='running',roots=roots,shots=rows,attempts=attempts,seconds=time.time()-start))
 result=dict(method='roma_fps32_incremental',status='success',roots=roots,shots=rows,attempts=attempts,seconds=time.time()-start,acceptance='usable original anchor, >=3 valid pairs, noncollinear point clouds, converged finite solver. PROVISIONAL numeric attachment; no calibrated reliability threshold or quality certification.')
 save(case/'optimization/results.json',result);return result
if __name__=='__main__':run(Path(sys.argv[1]).resolve(),int(sys.argv[2]),sys.argv[3])
