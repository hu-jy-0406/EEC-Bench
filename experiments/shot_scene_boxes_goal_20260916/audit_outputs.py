"""Independent invariants and replay audit of actual all-entity scenes."""
import hashlib,json,sys
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;BASE=HERE.parents[1];sys.path.insert(0,str(BASE/'scripts'))
from robust_box_registration import corners,transform,PERMUTATIONS
from build_three_method_static_scenes import projection_iou
from run_isolated_shot_static_3d import owned_compute_job

def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
job=owned_compute_job();record={'status':'pass','allocation':job,'cases':[],'original_jpegs_unchanged':True,'historical_baselines_unchanged':True}
for vals in read(HERE/'baseline_corner_mse.json').values():
 for p,h in vals['sources'].items():assert sha(Path(p))==h
for method in ['pi3x','pi3x_native','da3nested','dvlt','dvlt_metric']:
 for sid,count in [('shot1',19),('shot3',22)]:
  manifest=read(HERE/'inputs'/f'{sid}.json');root=HERE/method/sid;meta=read(root/'complete.json');geom=np.load(root/'geometry.npz')
  assert meta['shot_id']==sid and meta['frame_count']==6 and meta['single_shot_input_only']
  assert len(manifest['entities'])==count
  for frame in manifest['frames']:
   assert Path(frame['path']).parent.name==sid and sha(Path(frame['path']))==frame['sha256']
  cam=geom['camera_to_scene'];local=geom['local_points'];world=geom['world_points'];q=np.array(meta['scene_rotation_from_raw']);origin=np.array(meta['scene_origin_raw']);raw=geom['raw_camera_to_world']
  np.testing.assert_allclose(np.linalg.det(cam[:,:3,:3]),1,atol=2e-5)
  reconstructed=np.einsum('nij,nhwj->nhwi',cam[:,:3,:3],local)+cam[:,None,None,:3,3]
  err=float(np.max(abs(reconstructed-world)));assert err<2e-5*max(1,float(np.max(abs(world))))
  np.testing.assert_allclose(cam[:,:3,:3],np.einsum('ij,njk->nik',q,raw[:,:3,:3]),atol=2e-5)
  np.testing.assert_allclose(cam[:,:3,3],(raw[:,:3,3]-origin)@q.T,atol=2e-5)
  variants=['boxer_depth']+(['boxer_no_depth','boxer_refined'] if method=='pi3x' else [])
  for variant in variants:
   graph=read(root/variant/'scene_graph.json');cams={c['frame_id']:c for c in graph['cameras']};assert len(graph['entities'])==count
   assert {e['entity_id'] for e in graph['entities']}=={sid+'/'+e['entity_id'] for e in manifest['entities']}
   for e in graph['entities']:
    b=e['geometry'];S=np.array(b['size_xyz']);R=np.array(b['R_world_from_object']);assert (S>0).all();np.testing.assert_allclose(R.T@R,np.eye(3),atol=2e-5);assert np.linalg.det(R)>.999
    np.testing.assert_allclose(b['corners_world'],corners(b),atol=2e-5)
    rows=e['frame_evidence'];assert {r['frame_id'] for r in rows}==set(cams)
    if e['motion_status']=='static':assert e['aggregation']['status']=='fused'
    else:
     assert e['aggregation']['status']=='representative_frame';fid=e['aggregation']['frame_id'];r=next(r for r in rows if r['frame_id']==fid)
     np.testing.assert_allclose(corners(b),corners(r['geometry']),atol=2e-5)
    ious=[projection_iou(b,cams[r['frame_id']],r['box_xyxy'],cams[r['frame_id']]['image_size']) for r in rows if r['visible'] and r['box_xyxy'] is not None]
    assert abs(np.mean(ious)-e['fused_projection_mean_iou'])<1e-9
   record['cases'].append({'method':method,'shot':sid,'variant':variant,'entity_count':count,'geometry_replay_max_error':err,'scene_graph_sha256':sha(root/variant/'scene_graph.json')})
for file in ['comparison_boxer_depth.json','comparison_boxer_no_depth.json','comparison_boxer_refined.json']:
 for key,v in read(HERE/file).items():
  paths=list(v['sources']);graphs=[read(Path(p)) for p in paths];maps=[{e['entity_id']:e for e in g['entities']} for g in graphs]
  groups=[g for g in read(BASE/'experiments/study2_static_set_consistency_20260916/run01/matching.json')['groups'] if g['identity']=='matched'];assert len(groups)==11
  target,source=[np.array([corners(m[g[side+'_ids'][0]]['geometry']) for g in groups]) for m,side in zip(maps,['a','b'])]
  pred=transform(source,(v['scale'],np.array(v['rotation']),np.array(v['translation'])));errors=((pred[:,None]-target[:,PERMUTATIONS])**2).mean((2,3)).min(1)
  assert abs(errors.mean()-v['mse_xyz'])<1e-10
  assert abs(v['normalized_mse']-v['reverse']['normalized_mse'])<1e-10
  for p,h in v['sources'].items():assert sha(Path(p))==h
record['code_hashes']={str(p):sha(p) for p in list(HERE.glob('*.py'))+[BASE/'scripts/global_corner_mse.py']}
record['limitations']=['No human/ground-truth 3D accuracy validation.','Frozen independent historical motion labels retained for controlled comparison.','Synthetic moving-camera test passes; this real pair has only small estimated within-shot camera motion.','Reprojection checks reuse input prompts.']
(HERE/'audit.json').write_text(json.dumps(record,indent=2)+'\n');print('AUDIT PASS',len(record['cases']),'case/variant outputs; originals, geometry, trajectories, reprojection, MSE, inverse replay')
