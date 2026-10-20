import json,hashlib,time
from pathlib import Path
import numpy as np
root=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_text())
bases=read(root/'baselines.json');out={}
for name,base in bases.items():
 case=root/'corrected'/name/'run'
 if not (case/'summary.json').exists():continue
 summary=read(case/'summary.json');r=dict(status=summary['status'],seconds=summary['elapsed_seconds'],tokens=summary['total_tokens'],usd=summary['standard_api_equivalent_usd'],calls=len(summary['calls']))
 if summary['status']!='success':out[name]=r;continue
 pair=case/'pairs/pair_000';boundary=read(pair/'boundary/results.json');reg=read(pair/'registration/roma_geometry/registration.json');fit=reg['fits']['all_structures'];matching=read(pair/'matching.json')
 names={e['entity_id']:e['name'] for p in (case/'selected').glob('*_scene.json') if '_static_' not in p.name for e in read(p)['entities']}
 assert all(s['stage']!='geocalib' for s in summary['stages'])
 assert read(case/'provenance.json')['geocalib_weights'] is None
 assert not (case/'calibration_new').exists()
 assert reg['rotation_model']=='so3' and fit['points_removed']==0 and fit['distance_power']==1
 for shot in read(case/'raw_manifest.json')['shots']:
  assert read(case/'pi3x'/shot['shot_id']/'boxer_depth/inference_complete.json')['inference_frame']=='camera_oriented_no_gravity_v1'
 R=np.array(fit['rotation']);r.update(geocalib_absent=True,rotation_determinant=float(np.linalg.det(R)),orthogonality_error=float(np.max(np.abs(R.T@R-np.eye(3)))),
  registration=dict(scale=fit['scale'],selected_pairs=reg['sampling']['selected_count'],pool_pairs=reg['sampling']['candidate_count'],selected_mean=fit['selected_distance_3d']['mean'],full_mean=fit['distance_3d']['mean'],full_median=fit['distance_3d']['median'],full_p90=fit['distance_3d']['p90'],reprojection_median_pixels=fit['all_correspondences']['median_pixels'],seconds=reg['seconds']),
  identity_counts={k:sum(g['identity']==k for g in matching['groups']) for k in sorted({g['identity'] for g in matching['groups']})},
  spatial=boundary['spatial']['summary'],presence=boundary['presence']['summary'],
  within={sid:value['spatial']['summary'] for sid,value in summary['within_shots'].items()},
  conflict_events=[dict(kind=e['kind'],event_id=e['event_id'],entity_ids=e['entity_ids'],names=[names.get(i,i) for i in e['entity_ids']],reason=e.get('review',{}).get('reason')) for e in boundary['events'] if e['status']=='conflict'],
  spatial_candidates=[dict(event_id=e['event_id'],names=[names.get(i,i) for i in e['entity_ids']],status=e['status'],cosine=e.get('cosine'),gate=e.get('gate_reason'),reason=e.get('review',{}).get('reason')) for e in boundary['events'] if e['kind']=='spatial'],
  displacement=summary['position_consistency']['episode'])
 out[name]=r
(root/'results_comparison.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(out,ensure_ascii=False,indent=2))
