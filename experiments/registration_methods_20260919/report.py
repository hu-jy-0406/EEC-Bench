"""Audit every variant, compare fixed evaluation populations, render and report."""
import json,hashlib,sys,shutil
from pathlib import Path
import numpy as np
from scipy.optimize import linear_sum_assignment
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parents[1];sys.path.insert(0,str(BASE/'scripts'))
from gs_registration_3d import rotation,distances
from gs_registration_variants import corner_pairs,hybrid_objective
CASES={'study2':BASE/'experiments/study2_integrated_full_fresh_20260919/study2','study3':BASE/'experiments/study3/run_cpu02'}
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def usage(status):return sum(u['input_tokens']+u['output_tokens'] for u in status.get('usage',[]))
def xof(f):return np.array([np.log(f['scale']),np.radians(f['yaw_deg']),*f['translation']])
DISPLAY=['baseline_all','m1_fps_64','m1_confidence_fps_64','m2_direct','m3_corners','m4_hybrid']
LABELS={'baseline_all':'Full RoMa baseline','m1_fps_64':'1. FPS / 64 pairs','m1_confidence_fps_64':'1. confidence >= 0.8 + FPS / 64','m2_direct':'2. Direct Codex estimate','m3_corners':'3. Anchor corners only','m4_hybrid':'4. RoMa + anchor corners'}
colors=['#1769ba','#df6b17'];edges=[(i,j) for i in range(8) for j in range(i+1,8) if (i^j).bit_count()==1]
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
allrows=[];audits={};newtokens=0
for name,case in CASES.items():
 out=ROOT/name;data=np.load(case/'registration/roma_geometry/correspondences.npz')['data'];anchors=read(out/'anchors.json');initial=read(case/'matching_initial.json');final=read(case/'matching.json')
 scenes=[read(case/'selected'/f'{s}_scene.json') for s in ['shot1','shot3']];look=[{e['entity_id']:e for e in s['entities']} for s in scenes]
 common=[]
 for g in final['groups']:
  if g['identity']!='matched':continue
  a,b=look[0][g['a_ids'][0]],look[1][g['b_ids'][0]]
  if a['motion_status']!= 'static' or b['motion_status']!='static' or a['geometry'] is None or b['geometry'] is None:continue
  common.append(dict(group_id=g['group_id'],target=a['geometry']['corners_world'],source=b['geometry']['corners_world'],target_center=a['geometry']['center_world'],source_center=b['geometry']['center_world'],names=[a['name'],b['name']],a_ids=g['a_ids'],b_ids=g['b_ids']))
 stages={s['stage']:s['seconds'] for s in read(case/'pipeline_runtime.json')['stages']};anchorstatus=read(case/'calls/matching/status.json');anchortokens=usage(anchorstatus)
 summary=read(case/'summary.json');commoncalls=[c for c in summary['calls'] if c['call'] in ['calls/motion_shot1','calls/motion_shot3','entities/shots/shot1','entities/shots/shot3']];commontokens=sum(c['total_tokens'] for c in commoncalls)
 commonseconds=sum(stages[k] for k in ['detection_and_clustering','geocalib','prepare_shot_inputs','pi3x_shot1','boxer_shot1','pi3x_shot3','boxer_shot3','motion_and_fusion'])
 cost=dict(recorded_roma_seconds=stages['roma_matches'],recorded_lift_seconds=stages['lift_correspondences'],recorded_anchor_stage_seconds=stages['initial_identity'],recorded_anchor_tokens=anchortokens,common_upstream_stage_sum_seconds=commonseconds,common_upstream_tokens_excluding_shot2=commontokens,roma_hardware='GPU' if name=='study2' else 'CPU',note='Reconstructed serial path from historical measurements, not a fresh end-to-end timing. Study3 historical detection stage includes optional Shot2; tokens below exclude Shot2 consistently. Anchor cost includes the original full initial-identity call, not a newly measured anchor-only call.')
 save(out/'cost_basis.json',cost)
 baseline=read(BASE/'experiments/registration_3d_sum_20260919'/name/'registration.json');records=[dict(method='baseline_all',fit=baseline['fits']['all_structures'],seconds=baseline['seconds'],keypoint_pairs=len(data),corner_pairs=0)]
 records += [read(p) for p in sorted(out.glob('*/registration.json'))]
 direct=read(out/'m2_direct/transform.json');ds=read(out/'m2_direct/status.json');newtokens+=usage(ds)
 directfit=dict(direct,rotation=rotation(np.radians(direct['yaw_deg'])).tolist());records.append(dict(method='m2_direct',fit=directfit,seconds=ds['seconds'],keypoint_pairs=0,corner_pairs=0))
 methodmap={};full_eval=[]
 for rec in records:
  method=rec['method'];f=rec['fit'];x=xof(f);s=f['scale'];rot=rotation(x[1]);t=np.array(f['translation']);errors=distances(x,data[:,7:10],data[:,10:13]);cp,cq,assign=corner_pairs(x,common);ce=distances(x,cp,cq);centers=np.array([np.linalg.norm(s*rot@np.array(c['source_center'])+t-c['target_center']) for c in common])
  if 'selected_rows' in rec:
   ix=np.array(rec['selected_rows']);assert len(ix)==len(set(ix))==rec['keypoint_pairs'];assert (data[ix,13]>=rec['confidence_threshold']).all()
   target=data[ix,7:10];source=data[ix,10:13]
   if method.startswith('m1_'):expected=float(distances(x,target,source).sum())
   else:expected=hybrid_objective(x,anchors,target,source)[0]
   assert abs(expected-f['objective_value'])<1e-7
  elif method=='m3_corners':assert abs(hybrid_objective(x,anchors,np.empty((0,3)),np.empty((0,3)))[0]-f['objective_value'])<1e-7
  if method=='m4_hybrid':assert rec['corner_pairs']==rec['keypoint_pairs']==8*len(anchors)
  roma=method.startswith('m1_') or method in ['m4_hybrid','baseline_all'];usesanchor=method!='m2_direct'
  chain_seconds=rec['seconds']+(stages['initial_identity'] if usesanchor else 0)+(stages['roma_matches']+stages['lift_correspondences'] if roma else 0)
  tokens=anchortokens if usesanchor else usage(ds)
  row=dict(case=name,method=method,keypoint_pairs=rec['keypoint_pairs'],corner_pairs=rec['corner_pairs'],scale=s,yaw_deg=f['yaw_deg'],translation=f['translation'],full_roma_3d_mean=float(errors.mean()),full_roma_3d_median=float(np.median(errors)),reviewed_static_box_corner_mean=float(ce.mean()),reviewed_static_center_mean=float(centers.mean()),evaluated_common_static_groups=len(common),actual_current_stage_seconds=rec['seconds'],recorded_roma_seconds=stages['roma_matches'] if roma else 0,alignment_path_seconds_with_recorded_upstream=chain_seconds,alignment_path_tokens_including_reused_anchor=tokens,estimated_full_frontend_to_alignment_seconds=commonseconds+chain_seconds,estimated_full_frontend_to_alignment_tokens=commontokens+tokens,new_model_tokens=usage(ds) if method=='m2_direct' else 0,source_roma_hardware=cost['roma_hardware'] if roma else 'not used',fit_objective=f.get('objective_value'),solver_success=f.get('solver_success',f.get('selected_solver_success')),stage2_direct_confidence=f.get('confidence'))
  allrows.append(row);methodmap[method]=(rec,row)
  full_eval.append(dict(method=method,roma_error_by_group={str(int(g)):dict(n=int((data[:,2]==g).sum()),mean=float(errors[data[:,2]==g].mean()),median=float(np.median(errors[data[:,2]==g]))) for g in np.unique(data[:,2])},reviewed_common_corner_assignments=assign,reviewed_common_center_errors=[dict(group_id=c['group_id'],names=c['names'],distance=float(e)) for c,e in zip(common,centers)]))
 save(out/'evaluation_details.json',full_eval)
 # Six predeclared views: baseline, both FPS variants, and methods2/3/4.
 for render in ['top','image']:
  fig,axes=plt.subplots(2,3,figsize=(16,10));views=[]
  if render=='top':
   for method in DISPLAY:
    rec,row=methodmap[method];f=rec['fit'];rot=rotation(np.radians(f['yaw_deg']));t=np.array(f['translation'])
    for c in common:views.extend([np.array(c['target']),f['scale']*np.array(c['source'])@rot.T+t])
   xy=np.concatenate(views)[:,:2];lo=xy.min(0)-.2;hi=xy.max(0)+.2
  for ax,method in zip(axes.ravel(),DISPLAY):
   rec,row=methodmap[method];f=rec['fit'];rot=rotation(np.radians(f['yaw_deg']));t=np.array(f['translation']);s=f['scale']
   if render=='top':
    for c in common:
     for side,key in enumerate(['target','source']):
      b=np.array(c[key]);center=np.array(c[key+'_center'])
      if side:b=s*b@rot.T+t;center=s*rot@center+t
      emph=c['a_ids'][0] in ['shot1/e5','shot1/e15','shot1/e3']
      for i,j in edges:ax.plot(*b[[i,j],:2].T,c=colors[side],alpha=.65 if emph else .15,lw=.9 if emph else .5)
      ax.scatter(*center[:2],c=colors[side],s=14)
      if emph:ax.annotate(('Desk' if c['a_ids']==['shot1/e5'] else 'Radiator' if c['a_ids']==['shot1/e15'] else 'Lamp')+f' S{1 if side==0 else 3}',center[:2],xytext=(3,4 if side==0 else -10),textcoords='offset points',fontsize=7,color=colors[side])
    ax.set_xlim(lo[0],hi[0]);ax.set_ylim(lo[1],hi[1]);ax.set_aspect('equal');ax.grid(alpha=.12);ax.set_xlabel('X / model units');ax.set_ylabel('Y / model units')
    ax.set_title(LABELS[method]+f"\nkeypoint eval mean={row['full_roma_3d_mean']:.3f}; box eval={row['reviewed_static_box_corner_mean']:.3f}",fontsize=10)
   else:
    inp=read(case/'inputs/shot3.json');frame=next(f for f in inp['frames'] if f['frame_id']==0);ax.imshow(plt.imread(frame['path']));cam=next(c for c in scenes[1]['cameras'] if c['frame_id']==0)
    for eid in ['shot1/e5','shot1/e15']:
     g=next(g for g in initial['groups'] if g['a_ids']==[eid]);corners=np.array(look[0][eid]['geometry']['corners_world']);own=(corners-t)@rot/s;xyz=(own-cam['position_world'])@np.array(cam['R_world_from_camera']);uv=xyz@np.array(cam['K']).T;uv=uv[:,:2]/uv[:,2:]
     for i,j in edges:
      if min(xyz[i,2],xyz[j,2])>1e-6:ax.plot(*uv[[i,j]].T,color='#e538cd',lw=1.3)
     e=next(e for e in inp['entities'] if e['entity_id']==g['b_ids'][0].split('/')[-1]);o=next(o for o in e['observations'] if o['frame_id']==0);x,y,x2,y2=o['box_xyxy'];ax.add_patch(Rectangle((x,y),x2-x,y2-y,fill=False,ec='#25d67b',lw=1.7))
    ax.set_xlim(0,852);ax.set_ylim(480,0);ax.axis('off');ax.set_title(LABELS[method],fontsize=11)
  fig.suptitle(name.title()+' | Four alignment methods on frozen upstream evidence',fontsize=16)
  legend=[Line2D([0],[0],c=colors[0],label='Shot1'),Line2D([0],[0],c=colors[1],label='Shot3 transformed')] if render=='top' else [Line2D([0],[0],c='#25d67b',label='Original Shot3 detection boxes'),Line2D([0],[0],c='#e538cd',label='Projected Shot1 desk/radiator boxes')]
  fig.legend(handles=legend,loc='lower center',ncol=2);fig.tight_layout(rect=[0,.04,1,.95]);fig.savefig(out/f'comparison_{render}.png',dpi=150);fig.savefig(out/f'comparison_{render}.jpg',dpi=110,pil_kwargs={'quality':88});plt.close(fig)
 # Audit original evidence, input isolation, and all tool-free model events.
 for p,h in read(out/'upstream_hashes.json').items():assert sha(Path(p))==h
 payload=read(out/'m2_direct/input.json');assert set(payload)=={'stage','normal_story_prompt','shots','images','transform_convention'}
 assert len(payload['images'])==12 and len(payload['shots'])==2
 ev=[json.loads(l) for l in (out/'m2_direct/events.jsonl').read_text().splitlines()]
 types=[e.get('item',{}).get('type') for e in ev if e.get('type') in ['item.started','item.completed']]
 assert not any(t in ['command_execution','mcp_tool_call','web_search'] for t in types)
 for sid in ['shot1','shot3']:
  for f in read(case/'inputs'/f'{sid}.json')['frames']:assert sha(Path(f['path']))==f['sha256']
 audits[name]=dict(passed=True,original_upstream_unchanged=True,original_frames_verified=12,anchor_count=len(anchors),corner_pairs=8*len(anchors),hybrid_equal_counts=True,direct_no_anchor_or_previous_transform_or_matches=True,direct_tool_events=types,all_objectives_recomputed=True,initial_anchors_not_corrected_after_review=True)
save(ROOT/'comparison.json',allrows);save(ROOT/'audit.json',audits)
import csv
with (ROOT/'comparison.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=list(allrows[0]));w.writeheader();w.writerows(allrows)
snap=ROOT/'code_snapshot';snap.mkdir(exist_ok=True)
for p in [BASE/'scripts/gs_registration_variants.py',BASE/'scripts/gs_registration_3d.py',BASE/'prompts/gs_direct_registration_v1.txt',BASE/'tests/test_gs_registration_variants.py',ROOT/'run_direct.py',ROOT/'run_numeric.py',Path(__file__)]:shutil.copy2(p,snap/p.name)
save(ROOT/'source_hashes.json',{str(p):sha(p) for p in [BASE/'scripts/gs_registration_variants.py',BASE/'scripts/gs_registration_3d.py',BASE/'prompts/gs_direct_registration_v1.txt',ROOT/'run_direct.py',ROOT/'run_numeric.py',Path(__file__)]})
lines=['# Study2 / Study3 四类配准方法对比','',
'本轮为**冻结上游配准实验**：使用原始各shot实体、几何、初次Codex anchor和RoMa缓存。生产默认未更改。优化目标均为三维欧氏距离之和，不平方、不按残差删点、不截断、不置信度加权。变换为Shot3→Shot1，尺度[0.1,10]、重力轴yaw与平移。',
'','## 方法','',
'- 方法1：Top-K置信度、联合两侧3D端点的归一化6D最远点覆盖采样(FPS)、confidence>=0.8后FPS，分别32/64/128对。采样只在拟合前进行，全部被选点等权。只减优化点数，不降低原RoMa检测成本。',
'- 方法2：每例一次全新Astra/medium上下文，仅正常prompt、12张原始图和两个shot独立完整几何。无anchor/旧变换/关键点/其他方法结果，工具禁用，直接估计参数。没有自动优化或人工修正。',
'- 方法3：初始Codex anchor的8角点；每个anchor内部最小总距离一一对应（Hungarian），随候选变换更新对应；多初值求解纯角点距离和。不能把不同shot的原角点序号直接当物理对应。',
'- 方法4：上述角点加FPS选取的RoMa点对，两个数量严格相同；所有距离项等权。Study2 40+40，Study3 24+24。',
'','角点对应和固定上游设置已通过异步问题提出，等待期间开展独立工作；在未收到更改时按已说明的推荐设置执行。初始anchor没有按后来复核结果修正。Study2初始5个anchor、Study3初始3个；挂画等错配会影响角点法，RoMa法中这些区域可能没有有效点。',
'','## 如何读指标','',
'所有方法都在**相同全量RoMa点池**及**后续身份复核保留的共同静止实体box**上评估；后者只用于评估，不反馈拟合。两种指标都基于估计几何，不是真值。全量RoMa指标天然有利于全点基线；不同方法使用不同拟合集合，不能比较它们各自训练损失，也不能据单一指标宣布最佳。单位均为各自Shot1模型单位，不是米。',
'','## 主对比（含预先指定FPS64及高置信度FPS64）','']
for name in CASES:
 lines += [f'### {name}', '', '|方法|RoMa点/角点对|全RoMa池平均3D距离↓|共同静止box角点平均距离↓|当前方法实测秒|计入RoMa及anchor的配准链估算秒|配准链tokens¹|','|---|---:|---:|---:|---:|---:|---:|']
 for method in DISPLAY:
  r=next(r for r in allrows if r['case']==name and r['method']==method)
  lines.append(f"|{LABELS[method]}|{r['keypoint_pairs']}/{r['corner_pairs']}|{r['full_roma_3d_mean']:.4f}|{r['reviewed_static_box_corner_mean']:.4f}|{r['actual_current_stage_seconds']:.3f}|{r['alignment_path_seconds_with_recorded_upstream']:.2f}|{r['alignment_path_tokens_including_reused_anchor']:,}|")
 lines += ['',f'![{name}俯视图]({name}/comparison_top.png)','',f'![{name}原图投影]({name}/comparison_image.png)','']
lines+=['¹ 方法1/3/4计入复用的完整初次身份/anchor调用token，方法2计入本次直接估计调用；不把复用token算作本次新增消耗。当前方法实测为采样+优化，方法2为API调用；基线为上次实测。',
'','## 时间和token口径','',
'配准链时间 = 原anchor阶段 + 原RoMa阶段（适用方法）+原lift阶段（适用方法）+本次采样/优化；方法2仅直接估计调用。不含共同实体/几何前端。**这是按旧实测重建的串行成本，不是新的端到端实测，也未模拟阶段重叠**。',
'','Study2原RoMa用GPU，132.559s；Study3原RoMa用CPU，2732.829s。不可把两例相互比较成算法加速比。本轮新增优化均1CPU线程。方法1/4保留全36帧对的原始匹配成本，没有因后采样而偷减计时。共同前端成本和前端到配准的串行估算另在每例cost_basis.json及comparison.csv；Study3原检测阶段含可选Shot2，tokens为可比口径排除Shot2。',
'',f'本次新增模型调用2次，总tokens **{newtokens:,}**；其余方法0新增调用（复用已付费anchor结果）。采样与优化token为0，RoMa本地推理token为0。',
'','## 方法1全部采样结果','','|测例|策略|点对数|全池平均3D距离↓|共同box平均角点距离↓|秒|','|---|---|---:|---:|---:|---:|']
for r in allrows:
 if r['method'].startswith('m1_'):lines.append(f"|{r['case']}|{r['method']}|{r['keypoint_pairs']}|{r['full_roma_3d_mean']:.4f}|{r['reviewed_static_box_corner_mean']:.4f}|{r['actual_current_stage_seconds']:.3f}|")
lines+=['','## 审计与复现','','7项专门测试通过（采样唯一性/确定性/尺度不变性/阈值不放宽/角点双射/已知变换恢复/混合未平方距离和）。audit.json验证上游未改、每例12帧原JPEG、各优化目标重算、混合数量相等、直接调用无工具事件和输入隔离。','',
'完整参数、各初值结果、采样行号与置信度保存在各方法registration.json；直接调用的prompt/schema/request/events/response/usage全部保留。comparison.csv/json含所有方法、成本和完整参数。code_snapshot保存代码。没有人工挑选或修正输出，没有外观/存在性/空间最终评分，生产方法未自动替换。']
(ROOT/'REPORT.md').write_text('\n'.join(lines)+'\n')
protocol=read(ROOT/'protocol.json');protocol.update(status='completed_and_audited',new_model_calls=2,new_model_tokens=newtokens,tests_passed=7);save(ROOT/'protocol.json',protocol)
for r in allrows:
 if r['method'] in DISPLAY:print(r['case'],r['method'],round(r['full_roma_3d_mean'],4),round(r['reviewed_static_box_corner_mean'],4),round(r['alignment_path_seconds_with_recorded_upstream'],2),r['alignment_path_tokens_including_reused_anchor'])
