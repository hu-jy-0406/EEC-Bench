import hashlib,json,sys,time
from pathlib import Path
import numpy as np
HERE=Path(__file__).parent;BASE=HERE.parents[1]
sys.path.insert(0,str(BASE/'scripts'))
from global_corner_mse import fit
from robust_box_registration import corners
from run_isolated_shot_static_3d import owned_compute_job
job=owned_compute_job()
match=BASE/'experiments/study2_static_set_consistency_20260916/run01/matching.json'
groups=[g for g in json.loads(match.read_text())['groups'] if g['identity']=='matched']
source=BASE/'experiments/study_inconsistent_3/three_method_static_3d_20260914/run01'
results={}
for method in ['codex','boxer_codex_camera','boxer_geocalib']:
 paths=[source/method/s/'Gs_global.json' for s in ['shot1','shot3']]
 graphs=[json.loads(p.read_text()) for p in paths]
 maps=[{e['entity_id']:e for e in g['entities']} for g in graphs]
 a,b=[np.array([corners(m[g[side+'_ids'][0]]['geometry']) for g in groups]) for m,side in zip(maps,['a','b'])]
 start=time.time();r=fit(b,a);reverse=fit(a,b)
 assert abs(r['normalized_mse']-reverse['normalized_mse'])<1e-10
 r.update(reverse=reverse,seconds=time.time()-start,groups=[g['group_id'] for g in groups],
  sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},allocation=job,
  role='historical_fixed_camera_baseline_not_new_moving_camera_output')
 results[method]=r
 print(method,'normalizedMSE',r['normalized_mse'],'rawMSE',r['mse_xyz'],'yaw',r['yaw_deg'],'seconds',r['seconds'],flush=True)
(HERE/'baseline_corner_mse.json').write_text(json.dumps(results,indent=2))
