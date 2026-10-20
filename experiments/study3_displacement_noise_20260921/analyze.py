"""Read-only frozen-registration diagnostics. No fitting or inference."""
from pathlib import Path
import sys,json,csv,hashlib,itertools
import numpy as np
from scipy.optimize import lsq_linear
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from gs_temporal_core import transform_geometry
OUT=Path(__file__).resolve().parent
CASE=ROOT/'experiments/pipeline_parallel_20260921/run';PAIR=CASE/'pairs/pair_000'
sources={}
def read(p):
 sources[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();return json.loads(p.read_text())
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def stats(vals):
 v=np.asarray(vals,float)
 return dict(n=len(v),median=float(np.median(v)),p95=float(np.percentile(v,95)),max=float(v.max())) if len(v) else dict(n=0,median=None,p95=None,max=None)
def gap(a,b):
 # Minimize ||ca+Ra*u - cb-Rb*v|| over the two solid OBBs; convex bounded least squares.
 A=np.column_stack([a['R_world_from_object'],-np.asarray(b['R_world_from_object'])]);d=np.asarray(b['center_world'])-a['center_world']
 h=np.r_[a['size_xyz'],b['size_xyz']]/2
 z=lsq_linear(A,d,bounds=(-h,h),tol=1e-12,max_iter=1000)
 assert z.success
 return float(np.linalg.norm(A@z.x-d))
box=dict(center_world=[0,0,0],size_xyz=[2,2,2],R_world_from_object=np.eye(3).tolist())
assert gap(box,box)<1e-9
assert abs(gap(box,dict(box,center_world=[5,0,0]))-3)<1e-8
reg=read(PAIR/'registration/roma_geometry/registration.json');fit=reg['fits']['all_structures']
match=read(PAIR/'matching.json');initial=read(PAIR/'matching_initial.json')
graphs=[read(CASE/'selected'/f'{s}_scene.json') for s in ('shot1','shot3')]
proposals=read(PAIR/'boundary/proposals.json')
global_entities=read(CASE/'global_entities/global_entities.json')
locals_to_global={(a['shot_id'],a['local_entity_id']):e['global_entity_id'] for e in global_entities['entities'] for a in e['appearances']}
nodes=[{e['entity_id']:e for e in g['entities']} for g in graphs]
rows=[];allframes=[]
for group in match['groups']:
 if group['identity']!='matched':continue
 eid=[group[k][0] for k in ('a_ids','b_ids')];ents=[nodes[i][eid[i]] for i in range(2)]
 series=[];geom=[];jitter=[]
 for side,e in enumerate(ents):
  series.append([]);geom.append({})
  for f in e['frame_evidence']:
   if not f['visible'] or f['box_xyxy'] is None or not f.get('geometry'):continue
   g=f['geometry'] if side==0 else transform_geometry(f['geometry'],fit)
   geom[side][f['frame_id']]=g;series[side].append(np.asarray(g['center_world']))
   allframes.append(dict(group_id=group['group_id'],shot_id=graphs[side]['shot_id'],frame_id=f['frame_id'],center=g['center_world'],size=g['size_xyz'],projection_iou=f.get('projection_iou'),visible_extent_ratio=f.get('visible_extent_ratio')))
  ds=[np.linalg.norm(a-b) for a,b in itertools.combinations(series[side],2)]
  jitter.append(stats(ds))
 gid=group['group_id'];row=dict(group_id=gid,name=ents[0]['name'],entity_ids=eid,global_entity_id=locals_to_global.get(('shot1',eid[0].split('/')[-1])),
  anchor_initial=bool(next(g for g in initial['groups'] if g['group_id']==gid).get('anchor_eligible')),
  anchor_after_review=group.get('anchor_eligible'),motion_labels=[e['motion_status'] for e in ents],within_shot_all_pair_displacement=jitter)
 a,b=geom[0].get(120),geom[1].get(0)
 if a and b:
  for side,g in enumerate((a,b)):
   old=proposals['endpoint_observations'][side][eid[side]]['geometry']
   assert np.max(np.abs(np.asarray(old['center_world'])-g['center_world']))<1e-10
  delta=np.asarray(b['center_world'])-a['center_world'];dist=float(np.linalg.norm(delta));noise=max(j['p95'] or 0 for j in jitter)
  row.update(center_shot1=a['center_world'],center_shot3_aligned=b['center_world'],delta_xyz=delta.tolist(),center_distance=dist,
   horizontal_distance=float(np.linalg.norm(delta[:2])),vertical_delta=float(delta[2]),solid_obb_gap=gap(a,b),
   size_shot1=a['size_xyz'],size_shot3_aligned=b['size_xyz'],diagonal_shot1=float(np.linalg.norm(a['size_xyz'])),diagonal_shot3=float(np.linalg.norm(b['size_xyz'])),
   displacement_over_mean_box_diagonal=dist/float((np.linalg.norm(a['size_xyz'])+np.linalg.norm(b['size_xyz']))/2),
   within_p95_max=noise,displacement_over_within_p95=dist/noise if noise else None,
   cross_all_frame_center_distances=stats([np.linalg.norm(x-y) for x in series[0] for y in series[1]]))
 else:row.update(center_distance=None,reason='Missing target-frame observation; no substitution')
 rows.append(row)
# Translation-invariant relative displacement to each post-review anchor, diagnostic only.
by={r['group_id']:r for r in rows}
for r in rows:
 if r['center_distance'] is None:continue
 r['relative_displacement_to_anchors']={g:float(np.linalg.norm(np.asarray(r['delta_xyz'])-by[g]['delta_xyz'])) for g in ('g05','g14') if g!=r['group_id']}
# Read fitting pool only to summarize fixed-transform residuals, never refit/remove/reweight.
npz=PAIR/'registration/roma_geometry/correspondences.npz';sources[str(npz)]=hashlib.sha256(npz.read_bytes()).hexdigest()
with np.load(npz) as data:npz_keys={k:list(data[k].shape) for k in data.files}
result=dict(source_case=str(CASE),target_frames=['shot1/120','shot3/0'],units='Shot1 model coordinate units, not calibrated meters',
 registration=dict(scale=fit['scale'],rotation=fit['rotation'],translation=fit['translation'],full_pool_residual=fit['distance_3d'],selected_residual=fit['selected_distance_3d'],independent_holdout=False),
 entities=rows,frame_centers=allframes,correspondence_array_shapes=npz_keys,source_hashes=sources,
 limitations=['Within-shot spread mixes reconstruction jitter, occlusion, box/part changes and any actual drift; not pure measurement noise.',
 'Across-shot stable-reference residuals are not independently annotated negatives; fit anchors are in-sample.',
 'No calibrated metric scale, no independent significance test, no threshold adopted. Solid-OBB gap zero means overlap, not no displacement.',
 'Frame-pair distances are dependent observations; P95 is descriptive, not a confidence bound.'])
for p,h in sources.items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h
save(OUT/'results.json',result)
fields=['group_id','name','center_distance','horizontal_distance','vertical_delta','solid_obb_gap','within_p95_max','displacement_over_within_p95','anchor_initial','anchor_after_review']
with (OUT/'entities.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
for r in rows:
 print(r['group_id'],r['name'], 'missing' if r['center_distance'] is None else 'd=%.4f gap=%.4f jitter95=%.4f ratio=%.2f delta=%s'%(r['center_distance'],r['solid_obb_gap'],r['within_p95_max'],r['displacement_over_within_p95'],np.round(r['delta_xyz'],4)))
print('npz',npz_keys)
# Standalone diagnostic figure; descriptive spreads, no significance cutoff.
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
valid=[r for r in rows if r['center_distance'] is not None];y=np.arange(len(valid))
fig,ax=plt.subplots(figsize=(10,6),layout='constrained')
ax.barh(y-.18,[r['center_distance'] for r in valid],.34,label='Boundary center displacement')
ax.barh(y+.18,[r['within_p95_max'] for r in valid],.34,label='Larger within-shot pair-distance P95 (proxy)')
ax.set_yticks(y,[r['name'] for r in valid]);ax.invert_yaxis();ax.set_xlabel('Shot1 model units (not calibrated meters)');ax.legend(loc='lower right');ax.set_title('Study3: displacement versus within-shot geometry spread')
fig.savefig(OUT/'displacement_vs_spread.png',dpi=160);fig.savefig(OUT/'displacement_vs_spread.pdf');plt.close(fig)
