"""Frozen-upstream sparse RoMa, anchor corner, and hybrid registrations."""
import sys,json,time,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parents[1];sys.path.insert(0,str(BASE/'scripts'))
from gs_registration_3d import fit_all_pairs
from gs_registration_variants import select_pairs,fit_corners
from run_isolated_shot_static_3d import owned_compute_job
CASES={'study2':BASE/'experiments/study2_integrated_full_fresh_20260919/study2','study3':BASE/'experiments/study3/run_cpu02'}
read=lambda p:json.loads(p.read_text())
def save(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
 owned_compute_job()
 for name,case in CASES.items():
  out=ROOT/name;out.mkdir(parents=True,exist_ok=True);source=case/'registration/roma_geometry/correspondences.npz';d=np.load(source)['data']
  init=read(case/'matching_initial.json');graphs=[read(case/'selected'/f'{s}_scene.json') for s in ['shot1','shot3']];look=[{e['entity_id']:e for e in g['entities']} for g in graphs]
  anchors=[]
  for g in init['groups']:
   if g['group_id'] not in init['structural_anchor_group_ids']:continue
   a,b=look[0][g['a_ids'][0]],look[1][g['b_ids'][0]];assert a['motion_status']==b['motion_status']=='static'
   anchors.append(dict(group_id=g['group_id'],a_ids=g['a_ids'],b_ids=g['b_ids'],target=a['geometry']['corners_world'],source=b['geometry']['corners_world'],names=[a['name'],b['name']]))
  save(out/'anchors.json',anchors)
  provenance={str(p):sha(p) for p in [source,case/'matching_initial.json',case/'matching.json',*[case/'selected'/f'{s}_scene.json' for s in ['shot1','shot3']],*[case/'inputs'/f'{s}.json' for s in ['shot1','shot3']]]}
  save(out/'upstream_hashes.json',provenance)
  for strategy,threshold in [('top_confidence',.2),('fps',.2),('confidence_fps',.8)]:
   for count in [32,64,128]:
    method=f'm1_{strategy}_{count}';start=time.perf_counter();ix=select_pairs(d,count,'fps' if strategy=='confidence_fps' else strategy,threshold);selected=time.perf_counter();fit=fit_all_pairs(d[ix,7:10],d[ix,10:13]);end=time.perf_counter()
    rec=dict(method=method,fit=fit,selection_seconds=selected-start,optimization_seconds=end-selected,seconds=end-start,
             keypoint_pairs=len(ix),corner_pairs=0,selected_rows=ix.tolist(),confidence_threshold=threshold,
             confidence_quantiles=np.quantile(d[ix,13],[0,.25,.5,.75,1]).tolist(),group_counts={str(int(g)):int((d[ix,2]==g).sum()) for g in np.unique(d[ix,2])},
             selection_policy='confidence descending' if strategy=='top_confidence' else 'deterministic farthest-point coverage in normalized joint endpoint 6D space; seed highest confidence')
    save(out/method/'registration.json',rec);print(name,method,round(rec['seconds'],3),flush=True)
  start=time.perf_counter();fit=fit_corners(anchors);seconds=time.perf_counter()-start
  save(out/'m3_corners/registration.json',dict(method='m3_corners',fit=fit,seconds=seconds,optimization_seconds=seconds,selection_seconds=0,keypoint_pairs=0,corner_pairs=8*len(anchors)));print(name,'m3_corners',seconds,flush=True)
  count=8*len(anchors);start=time.perf_counter();ix=select_pairs(d,count,'fps',.2);selected=time.perf_counter();fit=fit_corners(anchors,d[ix,7:10],d[ix,10:13]);end=time.perf_counter()
  save(out/'m4_hybrid/registration.json',dict(method='m4_hybrid',fit=fit,seconds=end-start,optimization_seconds=end-selected,selection_seconds=selected-start,keypoint_pairs=count,corner_pairs=count,selected_rows=ix.tolist(),point_count_ratio=1.,confidence_threshold=.2));print(name,'m4_hybrid',end-start,flush=True)
  assert sha(source)==provenance[str(source)]
if __name__=='__main__':main()
