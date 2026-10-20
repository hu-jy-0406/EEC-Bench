"""Compare frozen old registrations with the all-pair 3D-distance reruns."""
import hashlib,json,shutil,sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

ROOT=Path(__file__).resolve().parent;BASE=ROOT.parents[1]
sys.path.insert(0,str(BASE/'scripts'))
from gs_registration_3d import distances
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
colors=['#1769ba','#df6b17']
edges=[(i,j) for i in range(8) for j in range(i+1,8) if (i^j).bit_count()==1]
plt.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(2,2,figsize=(13,11))
figim,axim=plt.subplots(2,2,figsize=(15,9))
rows=[];audit={}
for row,name in enumerate(['study2','study3']):
 out=ROOT/name;result=read(out/'registration.json');case=Path(result['source_case'])
 new=result['fits']['all_structures'];old=read(case/'registration/roma_geometry/registration.json')['fits']['all_structures']
 pointpath=case/'registration/roma_geometry/correspondences.npz';data=np.load(pointpath)['data'];p=data[:,7:10];q=data[:,10:13]
 assert sha(pointpath)==result['correspondences_sha256']
 assert new['fit_rows']==len(data) and new['points_removed']==0
 assert np.isclose(distances(np.array(new['parameters']),p,q).sum(),new['objective_value'],rtol=1e-12)
 assert sha(Path(result['previous_registration']['path']))==result['previous_registration']['sha256']
 selected=[read(case/'selected'/f'{sid}_scene.json') for sid in ['shot1','shot3']]
 entities=[{e['entity_id']:e for e in g['entities']} for g in selected]
 initial=read(case/'matching_initial.json');desk=next(g for g in initial['groups'] if g['a_ids']==['shot1/e5']);rad=next(g for g in initial['groups'] if g['a_ids']==['shot1/e15'])
 # Identical axes within each old/new comparison. All selected points plotted.
 transformed=[]
 for fit in [old,new]:transformed.append(fit['scale']*q@np.array(fit['rotation']).T+fit['translation'])
 extents=[p,*transformed]
 for fit in [old,new]:
  for g in [desk,rad]:
   extents.append(np.array(entities[0][g['a_ids'][0]]['geometry']['corners_world']))
   c=np.array(entities[1][g['b_ids'][0]]['geometry']['corners_world'])
   extents.append(fit['scale']*c@np.array(fit['rotation']).T+fit['translation'])
 xy=np.concatenate(extents)[:,:2];low=xy.min(0)-.25;high=xy.max(0)+.25
 for col,(fit,z) in enumerate(zip([old,new],transformed)):
  ax=axes[row,col];ax.scatter(*p[:,:2].T,c=colors[0],s=3,alpha=.35,rasterized=True);ax.scatter(*z[:,:2].T,c=colors[1],s=3,alpha=.35,rasterized=True)
  for g,label in [(desk,'Desk'),(rad,'Radiator')]:
   for side,key in enumerate(['a_ids','b_ids']):
    geom=entities[side][g[key][0]]['geometry'];c=np.array(geom['corners_world']);center=np.array(geom['center_world'])
    if side:c=fit['scale']*c@np.array(fit['rotation']).T+fit['translation'];center=fit['scale']*np.array(fit['rotation'])@center+fit['translation']
    for i,j in edges:ax.plot(*c[[i,j],:2].T,color=colors[side],lw=.9,alpha=.7)
    ax.annotate(label+f' S{1 if side==0 else 3}',center[:2],xytext=(4,5 if side==0 else -13),textcoords='offset points',fontsize=9,color=colors[side])
  cost=float(np.linalg.norm(z-p,axis=1).sum())
  ax.set_title(f'{name.title()} | {"Previous" if col==0 else "3D distance sum"}\nN={len(p)} | sum={cost:.2f} | mean={cost/len(p):.3f}')
  ax.set_xlim(low[0],high[0]);ax.set_ylim(low[1],high[1]);ax.set_aspect('equal');ax.grid(alpha=.15);ax.set_xlabel('X / Shot1 model units');ax.set_ylabel('Y / Shot1 model units')
  # Reproject Shot1 desk/radiator boxes into the same Shot3 original frame.
  inp=read(case/'inputs/shot3.json');frame=next(f for f in inp['frames'] if f['frame_id']==0)
  camera=next(c for c in selected[1]['cameras'] if c['frame_id']==0);im=axim[row,col];im.imshow(plt.imread(frame['path']))
  for g in [desk,rad]:
   geom=entities[0][g['a_ids'][0]]['geometry'];c=np.array(geom['corners_world'])
   own=(c-np.array(fit['translation']))@np.array(fit['rotation'])/fit['scale']
   xyz=(own-np.array(camera['position_world']))@np.array(camera['R_world_from_camera']);uv=xyz@np.array(camera['K']).T;uv=uv[:,:2]/uv[:,2:]
   for i,j in edges:
    if min(xyz[i,2],xyz[j,2])>1e-6:im.plot(*uv[[i,j]].T,color='#e538cd',lw=1.8)
   ent=next(e for e in inp['entities'] if e['entity_id']==g['b_ids'][0].split('/')[-1]);obs=next(o for o in ent['observations'] if o['frame_id']==0);x,y,x2,y2=obs['box_xyxy'];im.add_patch(Rectangle((x,y),x2-x,y2-y,fill=False,ec='#25d67b',lw=2))
  im.set_xlim(0,852);im.set_ylim(480,0);im.axis('off');im.set_title(f'{name.title()} Shot3 frame 0 | {"Previous" if col==0 else "3D distance sum"}')
 before=result['previous_registration']['distance_3d'];after=new['distance_3d'];gain=100*(1-after['sum']/before['sum'])
 rows.append(dict(case=name,n=len(data),old_sum=before['sum'],new_sum=after['sum'],reduction_percent=gain,old_mean=before['mean'],new_mean=after['mean'],old_scale=old['scale'],new_scale=new['scale'],old_yaw=old['yaw_deg'],new_yaw=new['yaw_deg'],groups_before=before['by_group'],groups_after=after['by_group'],solver_success=new['selected_solver_success'],start_count=len(new['attempts']),start_objective_spread=float(np.ptp([a['final_sum'] for a in new['attempts']])),seconds=result['seconds']))
 files=[pointpath,case/'registration/roma_geometry/registration.json',case/'matching_initial.json']+[case/'selected'/f'{s}_scene.json' for s in ['shot1','shot3']]+[case/'inputs'/f'{s}.json' for s in ['shot1','shot3']]
 provenance={str(f):sha(f) for f in files}
 for sid in ['shot1','shot3']:
  for frame in read(case/'inputs'/f'{sid}.json')['frames']:
   assert sha(Path(frame['path']))==frame['sha256'];provenance[frame['path']]=frame['sha256']
 (out/'input_provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
 shutil.copy2(pointpath,out/'correspondences.npz')
 audit[name]=dict(passed=True,all_rows_used=len(data),legacy_partition_also_fitted=int((data[:,14]!=0).sum()),points_removed=0,original_registration_unchanged=True,original_correspondences_unchanged=True,original_frames_verified=12,objective_recomputed=True,selected_solver_success=new['selected_solver_success'],scale_at_bound=new['scale_at_bound'])

fig.suptitle('Same selected 3D pairs | Previous registration vs exact distance-sum objective',fontsize=16)
fig.legend(handles=[Line2D([0],[0],color=colors[0],marker='o',label='Shot1 selected points / boxes'),Line2D([0],[0],color=colors[1],marker='o',label='Shot3 transformed selected points / boxes')],loc='lower center',ncol=2)
fig.tight_layout(rect=[0,.045,1,.95]);fig.savefig(ROOT/'point_alignment_before_after.png',dpi=150);plt.close(fig)
figim.suptitle('Original-frame diagnostic | Same Shot1 boxes projected into Shot3',fontsize=16)
figim.legend(handles=[Line2D([0],[0],color='#25d67b',lw=3,label='Original Shot3 detector boxes'),Line2D([0],[0],color='#e538cd',lw=3,label='Projected Shot1 3D boxes (desk + radiator)')],loc='lower center',ncol=2)
figim.tight_layout(rect=[0,.055,1,.95]);figim.subplots_adjust(hspace=.14);figim.savefig(ROOT/'reprojection_before_after.png',dpi=150);plt.close(figim)
(ROOT/'comparison.json').write_text(json.dumps(rows,indent=2)+'\n');(ROOT/'audit.json').write_text(json.dumps(audit,indent=2)+'\n')
snap=ROOT/'code_snapshot';snap.mkdir(exist_ok=True)
for f in [BASE/'scripts/gs_registration_3d.py',BASE/'scripts/register_gs_3d.py',BASE/'scripts/run_gs_integrated.py',BASE/'tests/test_gs_registration_3d.py',BASE/'experiments/study2_full_fresh_20260918/register.py',Path(__file__)]:shutil.copy2(f,snap/f.name)
lines=['# Study2 / Study3：全三维点对距离总和配准','',
'目标：`min sum_i ||s Rz(theta) Q_i+t-P_i||_2`。所有选定点等权、距离不平方、不删点、不截断、不按实体重新加权。Shot3→Shot1，保留原先的正尺度[0.1,10]、绕竖直轴旋转和平移模型。',
'','两次均重用本例保存的RoMa筛选后3D对应点，只重跑配准。所有旧train/holdout行均参加拟合；本轮没有独立留出验证。未重跑检测/几何/身份或评分；旧配准和旧身份结果保持原样，不能声称后续身份复核已使用新变换。',
'','## 同一点集上的目标值对比','',
'|测例|点对数|旧距离总和|新距离总和|降低|旧平均距离|新平均距离|','|---|---:|---:|---:|---:|---:|---:|']
for r in rows:lines.append(f"|{r['case']}|{r['n']}|{r['old_sum']:.6f}|{r['new_sum']:.6f}|{r['reduction_percent']:.2f}%|{r['old_mean']:.6f}|{r['new_mean']:.6f}|")
lines+=['','单位为各自Shot1模型坐标单位，不是标定米。不同测例点数及重建不同，不能直接用总和跨测例排名。','',
'## 变换与逐结构结果','']
for r in rows:
 lines += [f"### {r['case']}",f"尺度 {r['old_scale']:.6f} → {r['new_scale']:.6f}；yaw {r['old_yaw']:.4f}° → {r['new_yaw']:.4f}°。CPU数值阶段 {r['seconds']:.3f}s。",'','|结构组|点数|旧平均3D距离|新平均3D距离|','|---|---:|---:|---:|']
 for g,before in r['groups_before'].items():lines.append(f"|g{int(g):02d}|{before['n']}|{before['mean']:.6f}|{r['groups_after'][g]['mean']:.6f}|")
 lines+=['',f"{r['start_count']}个初值均使用完整点集和同一目标；终值跨度 {r['start_objective_spread']:.3g}。选中优化成功：{r['solver_success']}。多初值一致不是全局最优证明。",'']
lines+=['## 可视化','','![点云前后对比](point_alignment_before_after.png)','','![原图投影前后对比](reprojection_before_after.png)','',
'俯视图显示全部选定点及桌子/暖气片3D盒；每个测例前后同坐标范围。原图绿色为原始检测框、紫色为Shot1桌子/暖气片聚合3D盒投影；框自身有重建误差，该图不是优化目标。较小总距离不等于每个结构都改善，也不代表物理几何或身份完全正确。',
'','审计：`audit.json`、每例`input_provenance.json`、`correspondences.npz`、`registration.json`；精确结果：`comparison.json`。实现及绘图快照：`code_snapshot/`。当前整合pipeline默认入口已改为`register_gs_3d.py`，历史`register.py`仅保留复现及重投影诊断函数。']
(ROOT/'REPORT.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(rows,indent=2))
