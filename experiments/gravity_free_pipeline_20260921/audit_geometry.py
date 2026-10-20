import json,sys
from pathlib import Path
import numpy as np
root=Path(__file__).resolve().parent;bases=json.loads((root/'baselines.json').read_text());report={}
def read(p):return json.loads(p.read_text())
for study,base in bases.items():
 new=root/'corrected'/study/'run';old=Path(base);rows={}
 for shot in read(new/'raw_manifest.json')['shots']:
  sid=shot['shot_id'];a=read(old/'pi3x'/sid/'complete.json');b=read(new/'pi3x'/sid/'complete.json')
  assert b['coordinate_mode']=='pi3x_native';np.testing.assert_array_equal(b['scene_rotation_from_raw'],np.eye(3))
  assert read(new/'inputs'/f'{sid}.json')['calibration'] is None
  with np.load(old/'pi3x'/sid/'geometry.npz') as x,np.load(new/'pi3x'/sid/'geometry.npz') as y:
   diffs={k:float(np.max(np.abs(x[k]-y[k]))) for k in ['raw_camera_to_world','intrinsics','depth']}
  Q=np.array(a['scene_rotation_from_raw']);shift=np.array(b['scene_origin_raw'])-a['scene_origin_raw'];center_errors=[];details=[];box_counts=[0,0]
  for frame in shot['frames']:
   name=f"frame_{frame['frame_id']:06d}.json"
   aa=read(old/'pi3x'/sid/'boxer_depth'/name)['entities'];bb=read(new/'pi3x'/sid/'boxer_depth'/name)['entities'];lookup={tuple(e['box_xyxy']):e for e in aa};box_counts[0]+=len(aa);box_counts[1]+=len(bb)
   for e in bb:
    prior=lookup.get(tuple(e['box_xyxy']))
    if prior is not None:
     p=np.array(prior['geometry']['center_world']);q=(np.array(e['geometry']['center_world'])+shift)@Q.T
     center_errors.append(float(np.linalg.norm(p-q)));details.append(dict(frame_id=frame['frame_id'],name=e['name'],distance=center_errors[-1]))
  rows[sid]=dict(native_geometry_verified=True,raw_geometry_max_absolute_difference=diffs,box_counts_old_new=box_counts,
   same_2d_box_comparisons=len(center_errors),center_gauge_difference_mean=float(np.mean(center_errors)) if center_errors else None,
   center_gauge_difference_max=max(center_errors,default=None),largest_center_differences=sorted(details,key=lambda r:r['distance'],reverse=True)[:5])
 report[study]=rows
(root/'geometry_audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
