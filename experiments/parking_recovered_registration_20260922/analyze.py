"""Frozen-identity diagnostics; no ground-truth error or confirmed anomaly claims."""
import sys,json,math,itertools,csv
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_gs_integrated import read,save,sha
from gs_entity_appearance_compact import cost

def transform(f,p):
 p=np.asarray(p,dtype=float)
 return p if f is None else f['scale']*p@np.asarray(f['rotation']).T+f['translation']
def run():
 allresults=[];allcalls=[]
 for name in ['parking4']:
  case=R/'shared'/name;frozen=read(case/'frozen_frontend.json')
  assert all(sha(p)==h for p,h in {**frozen['hashes'],**frozen['original_frames']}.items())
  sids=[s['shot_id'] for s in read(case/'raw_manifest.json')['shots']];nodes={e['entity_id']:e for s in sids for e in read(case/'selected'/f'{s}_scene.json')['entities']};glob=read(case/'global_initial/results.json')
  results={k:read(case/('optimization_audited' if k=='optimization' else k)/'results.json') for k in ['optimization','direct']};metric={};records=[]
  for method,res in results.items():
   by={r['shot_id']:r for r in res['shots']};pairs=[]
   for a,b in itertools.combinations(sids,2):
    if by[a]['prototype']!=by[b]['prototype']:continue
    common=[]
    for g in glob['groups']:
     ids={x.split('/')[0]:x for x in g['entity_ids']}
     if a not in ids or b not in ids:continue
     na,nb=nodes[ids[a]],nodes[ids[b]];va=next((f for f in reversed(na['frame_evidence']) if f['frame_id']==80),None);vb=next((f for f in nb['frame_evidence'] if f['frame_id']==0),None)
     if not va or not vb or not va.get('geometry') or not vb.get('geometry'):continue
     pa=transform(by[a]['fit'],va['geometry']['center_world']);pb=transform(by[b]['fit'],vb['geometry']['center_world']);d=float(np.linalg.norm(pa-pb));static=na['motion_status']==nb['motion_status']=='static'
     row=dict(method=method,shot_a=a,shot_b=b,group=g['group_id'],entity_a=ids[a],entity_b=ids[b],name_a=na['name'],name_b=nb['name'],both_static=static,center_distance=d,pa=pa.tolist(),pb=pb.tolist());records.append(row);common.append(row)
    ds=[x['center_distance'] for x in common if x['both_static']];median=float(np.median(ds)) if ds else None
    for x in common:x['re']=x['center_distance']/median if x['both_static'] and median and median>0 else None
    cos=[]
    for u,v in itertools.combinations(common,2):
     x=np.array(v['pa'])-u['pa'];y=np.array(v['pb'])-u['pb'];den=np.linalg.norm(x)*np.linalg.norm(y);c=float(np.dot(x,y)/den) if den>1e-12 else None
     cos.append(dict(groups=[u['group'],v['group']],cosine=c))
    pairs.append(dict(shot_a=a,shot_b=b,common_endpoint_entities=len(common),static_endpoint_entities=len(ds),static_median_distance=median,cosines=cos,negative_cosine_proposals=sum(c['cosine'] is not None and c['cosine']<0 for c in cos)))
   metric[method]=dict(roots=res['roots'],group_count=len(res['roots']),attached_shots=len(sids)-len(res['roots']),comparable_shot_pairs=len(pairs),possible_shot_pairs=len(sids)*(len(sids)-1)//2,seconds=res['seconds'],pairs=pairs)
  # Evaluate BOTH transforms on each optimization candidate pool, same pair and same points.
  diagnostics=[];directby={r['shot_id']:r for r in results['direct']['shots']}
  for attempt in results['optimization']['attempts']:
   if 'case' not in attempt:continue
   pair=Path(attempt['case']);p=pair/'registration/roma_geometry/correspondences.npz'
   if not p.exists():continue
   d=np.load(p)['data']
   if len(d)==0:continue
   a,b=attempt['root'],attempt['shot'];norm=float(np.sqrt(np.mean(np.sum((d[:,7:10]-d[:,7:10].mean(0))**2,axis=1))))
   for method in ['optimization','direct']:
    if method=='optimization':
     reg=pair/'registration/roma_geometry/registration.json'
     if not reg.exists():continue
     f=read(reg)['fits']['all_structures'];pred=transform(f,d[:,10:13])
    else:
     ra,rb=directby[a],directby[b]
     if ra['prototype']!=rb['prototype']:continue
     target=transform(rb['fit'],d[:,10:13]);fa=ra['fit']
     pred=target if fa is None else (target-fa['translation'])@np.asarray(fa['rotation'])/fa['scale']
    err=np.linalg.norm(pred-d[:,7:10],axis=1)
    diagnostics.append(dict(method=method,shot_a=a,shot_b=b,points=len(d),mean_distance=float(err.mean()),median_distance=float(np.median(err)),p95_distance=float(np.quantile(err,.95)),normalizer_target_cloud_rms_radius=norm,normalized_mean=float(err.mean()/norm) if norm else None,role='common anchor/RoMa candidate-pool diagnostic, NOT independent accuracy'))
  save(case/'comparison.json',dict(metrics=metric,point_diagnostics=diagnostics,entity_endpoint_records=records,identity_scope='frozen INITIAL scene-wide matches; no final aligned identity review or anomaly confirmation',coordinate_units='per prototype model units, not meters'))
  fields=['method','shot_a','shot_b','group','entity_a','entity_b','name_a','name_b','both_static','center_distance','re']
  with (case/'entity_distances.csv').open('w') as f:w=csv.DictWriter(f,fields,extrasaction='ignore');w.writeheader();w.writerows(records)
  # XY projections of identical representative 3D box corners; convex hull is not claimed rectangular.
  fig,axes=plt.subplots(1,2,figsize=(16,7));colors=plt.cm.tab10(np.linspace(0,1,len(sids)))
  from scipy.spatial import ConvexHull
  for ax,(method,res) in zip(axes,results.items()):
   roots=res['roots'];offset=0.
   for root in roots:
    extent=[];patches=[]
    for row in res['shots']:
     if row['prototype']!=root:continue
     sid=row['shot_id'];col=colors[sids.index(sid)]
     for e in nodes.values():
      if not e['entity_id'].startswith(sid+'/') or not e.get('geometry'):continue
      g=e['geometry'];corners=g.get('corners_world')
      if corners is None:continue
      xy=transform(row['fit'],corners)[:,:2];extent.extend(xy.tolist());patches.append((xy,col))
    if not extent:continue
    extent=np.array(extent);shift=np.array([offset-extent[:,0].min(),-extent[:,1].min()])
    for xy,col in patches:
     try:h=ConvexHull(xy);p=xy[h.vertices]+shift;p=np.vstack([p,p[0]]);ax.plot(p[:,0],p[:,1],color=col,alpha=.5,lw=.8)
     except Exception:pass
    ax.text(offset,float(np.ptp(extent[:,1]))+.05,root+' group');offset+=float(np.ptp(extent[:,0]))+1
   for i,sid in enumerate(sids):ax.plot([],[],color=colors[i],label=sid)
   ax.set_title(name+' / '+method);ax.set_aspect('equal');ax.grid(alpha=.2);ax.legend(fontsize=8);ax.set_xlabel('own group X; separate groups offset for display');ax.set_ylabel('own group Y')
  fig.tight_layout();fig.savefig(case/'registration_topviews.png',dpi=160);plt.close(fig)
  allresults.append(dict(name=name,metrics=metric,point_diagnostics=diagnostics,plot=str(case/'registration_topviews.png')))
  for p in list((case/'calls').glob('*/status.json'))+list((case/'entities/shots').glob('*/status.json')):
   st=read(p);u=st.get('usage',st.get('known_usage',[]));u=[u] if isinstance(u,dict) else u;u=[x for x in u if x]
   allcalls.append(dict(case=name,call=str(p),status=st['status'],seconds=st.get('seconds'),tokens=sum(x.get('input_tokens',0)+x.get('output_tokens',0) for x in u),standard_api_equivalent_usd=cost(u)))
 save(R/'comparison.json',dict(episodes=allresults,calls=allcalls,total_tokens=sum(x['tokens'] for x in allcalls),standard_api_equivalent_usd=sum(x['standard_api_equivalent_usd'] for x in allcalls),actual_bill_available=False))
def report():
 data=read(R/'comparison.json');lines=['# Parking recovered-detection registration comparison','',
 'Frozen recovered detection, fresh common geometry and motion; independent incremental optimization and pure Codex registration. Initial scene-wide identities are frozen for diagnostics. This is NOT a full consistency-scoring run or ground-truth accuracy benchmark.','',
 '| Case | Method | Coordinate groups | Attached shots | Comparable shot pairs | Method wall seconds |',
 '|---|---|---:|---:|---:|---:|']
 for e in data['episodes']:
  for method,m in e['metrics'].items():lines.append(f"| {e['name']} | {method} | {m['group_count']} | {m['attached_shots']} | {m['comparable_shot_pairs']}/{m['possible_shot_pairs']} | {m['seconds']:.2f} |")
 lines += ['', 'Numeric attachment is provisional. More connected shots does not by itself mean better registration. Optimization acceptance checks do not use a calibrated residual threshold; direct acceptance is the model’s register/abstain judgment.', '',
 '## Same-point registration diagnostics','',
 'Mean Euclidean residual divided by target point-cloud RMS radius. Same anchor/RoMa pool for both methods; FPS32 fit points come from this pool, so it is NOT independent validation. Null/missing comparisons are unavailable, not zero error.','',
 '| Case | Shot pair | Method | Point count | Normalized mean residual |','|---|---|---|---:|---:|']
 for e in data['episodes']:
  for d in e['point_diagnostics']:lines.append(f"| {e['name']} | {d['shot_a']} / {d['shot_b']} | {d['method']} | {d['points']} | {d['normalized_mean']} |")
 lines += ['', '## Usage','',f"All recorded model calls: {data['total_tokens']:,} tokens; estimated standard API equivalent USD {data['standard_api_equivalent_usd']:.6f}. Not actual billing. Includes fresh motion/initial identity and direct registration only; earlier detection/recovery cost excluded. Startup failures had no API calls. Cluster cost unavailable.",'',
 '## Visuals and detailed records','']
 for e in data['episodes']:
  c=R/'shared'/e['name'];lines += [f"### {e['name']}",'',f"![Original first frames]({R/'inputs'/e['name']/'overview.jpg'})",'',f"![Registration comparison]({e['plot']})",'',f"[Raw entity center distances and re]({c/'entity_distances.csv'}) · [All cosine proposals and point diagnostics]({c/'comparison.json'})",'']
 lines += ['Distinct coordinate groups are offset only for plotting and never compared numerically. Overlays project the same original 3D box corners onto each method’s XY plane; silhouettes need not be rectangles. Entity position differences can be real generated changes, detection noise or registration error. Negative cosines here are proposals, not confirmed spatial violations. Final aligned identity/spatial review and appearance/prompt scoring were outside this registration experiment.']
 (R/'REPORT.md').write_text('\n'.join(lines)+'\n')
if __name__=='__main__':run();report()
