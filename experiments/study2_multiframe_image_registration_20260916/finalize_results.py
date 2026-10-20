"""Freeze image-only primary fit, then evaluate frozen static relations and export all boxes."""
import copy,csv,itertools,subprocess
from common import *
from common import lookup as pixel_lookup
from register import Geometry
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
owned_compute_job();out=RUN/'results';out.mkdir(exist_ok=True)
regs={m:read(RUN/(m+'_geometry')/'registration.json') for m in ['roma','sift']}
fit=regs['roma']['fits']['all_structures'];s=fit['scale'];R=np.array(fit['rotation']);t=np.array(fit['translation'])
# Primary choice fixed in PLAN.md and registration.py, before downstream relation evaluation.
selection={'method':'RoMa v2 multiframe image correspondences; fixed per-shot Pi3X scene geometry','primary_fit':fit,'status':'alignment_unreliable_no_confirmed_spatial_penalty','selected_by':'predeclared all_structures train-only consensus, never relation score','uses_known_anomaly_as_target':False,'frozen_registration_sha256':sha(RUN/'roma_geometry/registration.json'),'coordinate_frame':'fixed Shot1 scene (not a fixed camera for all frames)'}
save(out/'selection.json',selection)
matchpath=BASE/'experiments/study2_static_set_consistency_20260916/run01/matching.json';matching=read(matchpath)
Gs={k:graph(k) for k in ['shot1','shot3']};ents={e['entity_id']:e for g in Gs.values() for e in g['entities']}
groups=[g for g in matching['groups'] if g['identity']=='matched' and len(g['a_ids'])==1 and len(g['b_ids'])==1 and ents[g['a_ids'][0]]['motion_status']=='static' and ents[g['b_ids'][0]]['motion_status']=='static'];groups.sort(key=lambda g:g['group_id']);assert len(groups)==11
lookup={g['group_id']:g for g in groups}
cn={'g01':'墙上风景画','g02':'深绿色杯子','g04':'大桌子','g06':'笔筒','g07':'窗台垂吊植物','g10':'地毯','g11':'椅子','g12':'暖气片','g13':'窗台花盆','g16':'小木桌/花架','g17':'小木桌上的植物'}

def box_to_common(b,shot):
 b=copy.deepcopy(b)
 if shot=='shot3':
  b['center_world']=(s*R@np.array(b['center_world'])+t).tolist();b['R_world_from_object']=(R@np.array(b['R_world_from_object'])).tolist();b['size_xyz']=(s*np.array(b['size_xyz'])).tolist()
 b['corners_world']=corners(b).tolist();return b
bundle={'coordinate_frame':'fixed_shot1_scene','status':'diagnostic_only_alignment_unreliable','transform_shot3_to_shot1':{'scale':s,'rotation':R.tolist(),'translation':t.tolist()},'entities':[],'cameras':{},'comparison_scope':'11 matched static entities; all 55 unordered relations','motion_representation':'best-visible representative plus own-frame estimated trajectory','geometry_is_ground_truth':False}
for shot,g in Gs.items():
 source={shot+'/'+e['entity_id']:e for e in inputs(shot)['entities']}
 for e in g['entities']:
  obs={o['frame_id']:o for o in source[e['entity_id']]['observations']};v={'shot_id':shot,'entity_id':e['entity_id'],'name':e['name'],'motion_status':e['motion_status'],'geometry':box_to_common(e['geometry'],shot),'representative_frame_id':e['aggregation'].get('frame_id'),'estimated_observation_trajectory':[]}
  for row in e['frame_evidence']:
   o=obs[row['frame_id']];v['estimated_observation_trajectory'].append({'frame_id':row['frame_id'],'exist':o['exist'],'visible':o['visible'],'geometry':box_to_common(row['geometry'],shot) if row.get('geometry') else None})
  bundle['entities'].append(v)
 cams=copy.deepcopy(g['cameras'])
 if shot=='shot3':
  for c in cams:
   c['position_world']=(s*R@np.array(c['position_world'])+t).tolist();c['R_world_from_camera']=(R@np.array(c['R_world_from_camera'])).tolist()
   for key in ['forward_world','up_world']:c[key]=(R@np.array(c[key])).tolist()
 bundle['cameras'][shot]=cams
assert len(bundle['entities'])==41
save(out/'all_entities_in_shot1_scene.json',bundle)
variants={'old_box_MSE':read(OLD/'selected/selection.json')['fit']}
for method,reg in regs.items():
 for name,f in reg['fits'].items():
  if f['status']=='numeric_candidate':variants[method+'_'+name]=f

def center(g,side):return np.array(ents[g[('a_ids','b_ids')[side]][0]]['geometry']['center_world'])
rows=[]
for ga,gb in itertools.combinations(groups,2):
 va=center(gb,0)-center(ga,0);vb=center(gb,1)-center(ga,1);cos={}
 for name,f in variants.items():
  v=np.array(f['rotation'])@vb;cos[name]=float(np.clip(va@v/(np.linalg.norm(va)*np.linalg.norm(v)),-1,1))
 row={'group_a':ga['group_id'],'group_b':gb['group_id'],'name_a':cn[ga['group_id']],'name_b':cn[gb['group_id']],'vector_shot1':va.tolist(),'vector_shot3_aligned':(s*R@vb).tolist(),'cosine':cos['roma_all_structures'],'angle_deg':float(np.degrees(np.arccos(cos['roma_all_structures']))),'variants':cos,'scoring_status':'unknown_alignment_unreliable'};rows.append(row)
rows.sort(key=lambda r:r['cosine'])
for i,r in enumerate(rows):r['rank_lowest_first']=i+1
assert len(rows)==55
save(out/'relations.json',rows)
fields=['rank_lowest_first','group_a','group_b','name_a','name_b','cosine','angle_deg','old_box_MSE_cosine','sift_cosine','scoring_status']
with (out/'relations.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
 for r in rows:w.writerow({k:r[k] for k in fields if k in r}|{'old_box_MSE_cosine':r['variants']['old_box_MSE'],'sift_cosine':r['variants']['sift_all_structures']})
target=next(r for r in rows if {r['group_a'],r['group_b']}=={'g02','g06'})
# Explicit user-facing arrow is holder -> mug in both shots.
va=center(lookup['g02'],0)-center(lookup['g06'],0);vb=s*R@(center(lookup['g02'],1)-center(lookup['g06'],1))
stat={'mean_cosine':float(np.mean([r['cosine'] for r in rows])),'negative_relations':sum(r['cosine']<0 for r in rows),'below_minus_0_5':sum(r['cosine']<-.5 for r in rows),'total_relations':55,'holder_to_mug':{'shot1_vector':va.tolist(),'shot3_aligned_vector':vb.tolist(),**target},'spatial_penalty':None,'reason':'image-derived alignment fails spatial holdout; raw cosines are diagnostic only, neither verified conflicts nor consistency passes'}
save(out/'summary.json',stat)

# Full two-color geometry and relation diagnostics.
signs=np.array(list(itertools.product([-1,1],repeat=3)));edges=[(i,j) for i in range(8) for j in range(i+1,8) if np.sum(signs[i]!=signs[j])==1];colors={'shot1':'#2368b5','shot3':'#e07820'}
fig=plt.figure(figsize=(15,11));axs=[fig.add_subplot(221,projection='3d'),fig.add_subplot(222),fig.add_subplot(223),fig.add_subplot(224)];allpts=[]
for e in bundle['entities']:
 c=colors[e['shot_id']];pts=np.array(e['geometry']['corners_world']);allpts.append(pts);highlight=e['entity_id'] in ['shot1/e2','shot1/e7','shot3/e2','shot3/e9']
 for i,j in edges:
  q=pts[[i,j]];axs[0].plot(*q.T,color=c,lw=1.6 if highlight else .7,alpha=.9 if highlight else .42);axs[1].plot(q[:,0],q[:,1],color=c,lw=1.6 if highlight else .65,alpha=.9 if highlight else .45)
 if highlight:
  p=np.array(e['geometry']['center_world']);label=e['entity_id'].replace('shot','S');axs[0].text(*p,label,color=c,fontsize=8);axs[1].text(*p[:2],label,color=c,fontsize=8)
P=np.concatenate(allpts);axs[0].set_box_aspect(np.ptp(P,axis=0));axs[0].set(xlabel='X',ylabel='Y',zlabel='Z',title='All 41 boxes; bold = mug / holder');axs[1].set_aspect('equal');axs[1].set(xlabel='X',ylabel='Y',title='Top view: same fixed Shot1 scene');axs[1].grid(alpha=.2)
for shot,v in [('shot1',va),('shot3',vb)]:
 u=v/np.linalg.norm(v);axs[2].quiver(0,0,u[0],u[1],angles='xy',scale_units='xy',scale=1,color=colors[shot],width=.012,label=shot);axs[2].text(u[0],u[1],shot,color=colors[shot])
axs[2].set(xlim=(-1.15,1.15),ylim=(-1.15,1.15),xlabel='X component',ylabel='Y component',title=f'Holder -> mug, 3D unit vectors (XY view)\ncos={target["cosine"]:.3f}, angle={target["angle_deg"]:.1f} deg');axs[2].set_aspect('equal');axs[2].grid(alpha=.2)
vals=[r['cosine'] for r in rows];axs[3].hist(vals,bins=np.linspace(-1,1,17),color='#8ea6be',edgecolor='white');axs[3].axvline(target['cosine'],c='#b21c38',lw=2,label=f'Holder / mug: rank {target["rank_lowest_first"]}/55');axs[3].set(xlabel='Relation cosine',ylabel='Number of pairs',title=f'All 55 common-static pairs; {stat["negative_relations"]} negative');axs[3].legend()
fig.legend(handles=[Line2D([0],[0],color=colors[s],lw=2,label=s) for s in colors],loc='upper right');fig.suptitle(f'Image-driven multiframe alignment: yaw {fit["yaw_deg"]:.2f} deg, scale {s:.3f}\nDIAGNOSTIC ONLY: spatial holdout median {fit["spatial_holdout"]["median_pixels"]:.1f} px; global alignment unreliable',fontsize=13);fig.tight_layout(rect=(0,0,1,.93));fig.savefig(out/'overview.png',dpi=170);fig.savefig(out/'overview.jpg',dpi=90);fig.savefig(out/'overview.pdf');plt.close(fig)
# Matrix includes every pair, preserves group identity.
M=np.eye(11);ids=[g['group_id'] for g in groups]
for r in rows:i,j=ids.index(r['group_a']),ids.index(r['group_b']);M[i,j]=M[j,i]=r['cosine']
fig,ax=plt.subplots(figsize=(10,9));im=ax.imshow(M,vmin=-1,vmax=1,cmap='RdBu');ax.set_xticks(range(11),ids);ax.set_yticks(range(11),ids)
for i in range(11):
 for j in range(11):ax.text(j,i,f'{M[i,j]:.2f}',ha='center',va='center',fontsize=8,color='white' if abs(M[i,j])>.65 else 'black')
fig.colorbar(im,ax=ax,label='3D direction cosine');ax.set_title('All common-static relation cosines\nUnreliable alignment: values are diagnostic, not confirmed penalties');fig.tight_layout();fig.savefig(out/'relation_matrix.png',dpi=150);plt.close(fig)

# Traceability and independent replay checks.
framehash=[]
for shot in Gs:
 for f in inputs(shot)['frames']:
  h=sha(f['path']);expected=f.get('sha256',f.get('image_sha256'));assert expected is None or h==expected;framehash.append({'shot':shot,'frame_id':f['frame_id'],'path':f['path'],'sha256':h,'expected_sha256':expected})
newlookup={e['entity_id']:e for e in bundle['entities']}
for r in rows:
 a,b=lookup[r['group_a']],lookup[r['group_b']];vs=[]
 for key in ['a_ids','b_ids']:vs.append(np.array(newlookup[b[key][0]]['geometry']['center_world'])-np.array(newlookup[a[key][0]]['geometry']['center_world']))
 replay=vs[0]@vs[1]/np.prod([np.linalg.norm(v) for v in vs]);assert abs(replay-r['cosine'])<1e-12
assert np.linalg.norm(R.T@R-np.eye(3))<1e-10 and np.linalg.det(R)>0 and s>0
for shot in Gs:
 for e in Gs[shot]['entities']:
  if shot=='shot3':assert np.max(np.abs((np.array(newlookup[e['entity_id']]['geometry']['center_world'])-t)@R/s-np.array(e['geometry']['center_world'])))<1e-10
mask_audit={}
for method in regs:
 d=np.load(RUN/(method+'_geometry')/'correspondences.npz')['data'];bad=0
 for ia,ib in set(map(tuple,d[:,:2])):
  sub=d[(d[:,0]==ia)&(d[:,1]==ib)];bad+=int(np.sum(pixel_lookup(structural_mask('shot1',int(ia)),sub[:,3:5])!=sub[:,2]));bad+=int(np.sum(pixel_lookup(structural_mask('shot3',int(ib)),sub[:,5:7])!=sub[:,2]))
 # Explicitly recompute the fixed holdout predicate from both original pixel grids.
 h=(((d[:,15]*17+d[:,16]*31)%5==0)|((d[:,17]*17+d[:,18]*31)%5==0));assert np.array_equal(h,d[:,14].astype(bool))
 assert bad==0
 raw=list((RUN/method).glob('*.npz'));assert len(raw)==36
 mask_audit[method]={'raw_pair_files':len(raw),'raw_pairs':sum(len(np.load(p)['uvA']) for p in raw),'retained':len(d),'holdout_rule_replay':True,'both_endpoint_structure_masks_replayed':True,'excluded_entity_pixel_violations':bad}
audit={'original_jpegs':framehash,'original_frame_reencoding':False,'source_graphs':{str(OLD/'selected'/f'{k}_scene.json'):sha(OLD/'selected'/f'{k}_scene.json') for k in Gs},'source_matching_sha256':sha(matchpath),'matcher_commit':subprocess.check_output(['git','-C',str(BASE/'third_party/RoMaV2'),'rev-parse','HEAD'],text=True).strip(),'matcher_weights':read(HERE/'weights.json'),'pair_counts':mask_audit,'entities_exported':41,'static_matches':11,'relations_replayed':55,'transform_inverse_checked':True,'self_reprojection':read(RUN/'self_reprojection.json'),'unit_tests':'test_registration.py: per-frame moving-camera composition and corrupted-match robust recovery; 2 passed (tests.log)','caveat':'Some pixels in one endpoint non-heldout tiles can occur in both sets; a pair is held out if either endpoint is in a reserved tile. Video frames remain correlated.'}
audit['experiment_code_sha256']={str(p):sha(p) for p in sorted(HERE.glob('*.py'))}
for shot,g in Gs.items():
 source=OLD/'pi3x'/shot/'boxer_depth/scene_graph.json';assert g==read(source)
 audit['source_graphs'][str(source)]=sha(source)
save(out/'audit.json',audit)
lines=['# Study2：多关键帧原图配准实验','', '**结论：这次方法尚未得到可信的全局对齐。不能据此确认空间冲突或给出有效扣分。**','',f'主结果为 RoMa v2，Shot3 场景变换到固定 Shot1 场景：yaw={fit["yaw_deg"]:.3f}°，scale={s:.6f}，translation={t.tolist()}。平移/尺度单位沿用模型场景，未标定为米。','',f'笔筒→深绿色杯子（g06→g02）的 cosine 为 **{target["cosine"]:.6f}**，夹角 **{target["angle_deg"]:.2f}°**，在55对关系中从低到高排 **{target["rank_lowest_first"]}**。共有 **{stat["negative_relations"]}/55** 对为负，均值 **{stat["mean_cosine"]:.6f}**。这些是未通过对齐验证的诊断值；均值不是有效的一致性分数。','', '## 实际执行流程','', '1. 冻结两个 shot 的原始 JPEG，各6帧（0、24、48、72、96、120；852×480），不重新编码。不重跑实体发现、动静态分类或 Boxer。保留原有 Pi3X 每帧相机位姿、深度、19/22个实体框以及11对静态对应。','2. 预先限定风景画、桌面、地毯、暖气片四个结构区域作为候选参照。遮去其他可见实体矩形并外扩5px，杯子、笔筒、人物不进入拟合。地毯在原匹配记录中并非可靠anchor；本次仅作结构候选，实际RoMa训练中也没有地毯点。矩形只是候选区域，不能保证框内每个像素属于该结构。','3. 官方 RoMa v2 v2.0.1 在全部6×6=36帧对上运行，每对保存5000个原始对应，共180000。另跑互相匹配的SIFT，作为独立对照。输入哈希、权重哈希、提交版本及计算节点记录见audit和原始结果。','4. 过滤条件：两端同一结构区域、置信度≥0.2、双向匹配循环误差≤3px、每帧深度为正且Pi3X置信度不在最低10%。RoMa保留3074对，训练1698、空间留出1376；SIFT保留171对，训练115、留出56。RoMa训练只覆盖桌面和暖气片，风景画没有保留点，地毯7点均属留出。','5. 每个像素由**所在关键帧**的局部3D点与camera-to-scene转换到该shot固定场景，未假设所有关键帧相机不动。自身重投影中位误差约0.3–0.4px。','6. 用训练匹配拟合一个正尺度、只绕重力轴旋转的Sim(3)：三点RANSAC候选、结构/空间格子加权投票、双向逐帧重投影soft-L1细化。优化变量为scale、yaw、三维translation；主结果按训练5px内点支持度选取。没有用实体框MSE、关系cosine或预期异常挑选变换。该数值求解未作全局最优证明。','7. 48px格子预留验证，另检查单结构/移除结构、奇偶关键帧子集以及SIFT。相邻视频帧相关，增加帧数不等于增加独立视差证据。','8. 冻结主变换后，将全部41个框、每帧轨迹及相机统一到Shot1固定场景。只对11对共同静止实体计算C(11,2)=55个关系，v1=c_b1−c_a1，v3=sR(c_b3−c_a3)，cos=v1·v3/(||v1||||v3||)。平移在差分中抵消，正尺度在cosine中抵消，但旋转和框中心误差仍影响结果。','', '## 为什么没有通过全局对齐验证','', '| 留出区域 | RoMa对应数 | 双向重投影误差中位数(px) | ≤5px比例 |','|---|---:|---:|---:|']
for gid,v in fit['spatial_holdout']['by_group'].items():lines.append(f'| {cn["g"+gid.zfill(2)]} | {v["n"]} | {v["median_px"]:.2f} | {v["inlier_fraction_5px"]:.1%} |')
lines+=['',f'整体留出中位误差为{fit["spatial_holdout"]["median_pixels"]:.2f}px；暖气片占留出点多数，整体值会掩盖桌面约116px的失败。SIFT主解yaw={variants["sift_all_structures"]["yaw_deg"]:.2f}°，留出中位误差{variants["sift_all_structures"]["spatial_holdout"]["median_pixels"]:.2f}px。两种图像方法没有形成统一几何解释。','', '原图对应点可见重复的暖气片条纹和缺少唯一标记的桌面纹理；循环一致性及较低局部残差不等于正确物理对应。当前结果无法严格区分错误对应、深度/相机误差、实际生成场景变化及优化局限各自占比，更不能把配准失败直接解释为实体空间冲突。','', '## 同一目标关系在不同解下的变化','', '| 方法/参照 | yaw(°) | 笔筒→杯子cosine |','|---|---:|---:|']
for name in ['old_box_MSE','roma_all_structures','roma_only_g04','roma_only_g12','roma_even_frames','roma_odd_frames','sift_all_structures','sift_only_g01']:
 if name in variants:lines.append(f'| {name} | {variants[name]["yaw_deg"]:.2f} | {target["variants"][name]:.6f} |')
lines+=['','## 可视化与完整输出','','![统一场景框与关系诊断](overview.png)','','- [全部55对CSV](relations.csv)；[向量及所有候选变换结果JSON](relations.json)','- [全部41个框、逐帧轨迹及相机JSON](all_entities_in_shot1_scene.json)','- [11×11关系矩阵](relation_matrix.png)；[高分辨率统一框图](overview.png)','- [主变换及验证状态](selection.json)；[输入/输出审计](audit.json)','- [第一帧原图对应点](../roma_geometry/visuals/matches_0_0.jpg)','', '## 全部关系（按主解cosine从低到高）','','所有条目的有效评分状态均为 `unknown_alignment_unreliable`。','', '| 排名 | 关系 | RoMa cosine | 夹角(°) | 旧框MSE cosine | SIFT cosine |','|---:|---|---:|---:|---:|---:|']
for r in rows:lines.append(f'| {r["rank_lowest_first"]} | {r["group_a"]} {r["name_a"]} ↔ {r["group_b"]} {r["name_b"]} | {r["cosine"]:.4f} | {r["angle_deg"]:.2f} | {r["variants"]["old_box_MSE"]:.4f} | {r["variants"]["sift_all_structures"]:.4f} |')
diag=read(RUN/'support_diagnostics.json');free=diag['roma']['free_rotation_sim3']['None']
lines+=['','## 失败后的补充诊断（未用于选择主变换）','',f'额外运行自由3D旋转Sim(3)探索，RoMa所得解偏离重力轴{free["up_axis_tilt_deg"]:.2f}°，留出整体中位误差{free["spatial_holdout"]["median_pixels"]:.2f}px，但桌面仍为{free["spatial_holdout"]["by_group"]["4"]["median_px"]:.2f}px。该诊断还改变了采样/加权方式，不是严格单变量消融；它没有恢复可靠全局对齐，也不能据此断言重力误差无关。','', '另在每个帧对、每个结构区域用训练点拟合局部2D单应性并检验留出点。它们不是一个共同3D坐标系，也未用于空间关系评分。完整结果：[support_diagnostics.json](../support_diagnostics.json)。','']
lines+=['','## 边界与下一步','','本次只评估空间关系对齐，不重算存在性扣分；不覆盖历史评测。保留独立shot建图与逐帧相机设定。下一步应先验证跨shot结构点是否是真实对应，再检验这些点能否支持统一几何；若仍缺少可信几何，应只输出可验证的局部关系或未知，不能靠最大化全体关系一致性来调旋转。','', '方法来源：[官方RoMa v2](https://github.com/Parskatt/RoMaV2)。原始数据和脚本均保留在上级实验目录。']
(out/'REPORT.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(stat,ensure_ascii=False,indent=2));print('RESULTS',out)
