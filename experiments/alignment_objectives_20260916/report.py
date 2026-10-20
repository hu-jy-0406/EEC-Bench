import json, time
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from run_experiment import *

owned_compute_job()
allfits={c:read(HERE/c/'fits.json') for c in SOURCES}
allval={c:read(HERE/c/'validation.json') for c in SOURCES}
data=inputs('study2');fits=allfits['study2'];val=allval['study2']
extra=read(HERE/'study2/scale_diagnostic.json')
gauge=read(HERE/'study2/coordinate_equivalence.json')
frames=read(HERE/'study2/frame_sensitivity.json')
excl=read(HERE/'study2/focal_pair_exclusion.json')
labels={'corner_huber':'Corner Huber','center_ls':'Center least squares','center_huber':'Center Huber',
'joint_0.01':'Center + axis, lambda=.01','joint_0.03':'Center + axis, lambda=.03','joint_0.1':'Center + axis, lambda=.1',
'joint_0.3':'Center + axis, lambda=.3','axis_first':'Axis first'}
short={'corner_huber':'角点 Huber','center_ls':'中心最小二乘','center_huber':'中心 Huber','joint_0.01':'中心+方向 λ=.01',
'joint_0.03':'中心+方向 λ=.03','joint_0.1':'中心+方向 λ=.1','joint_0.3':'中心+方向 λ=.3','axis_first':'方向优先'}
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'figure.dpi':160})
fig,axes=plt.subplots(1,3,figsize=(14,4.2),layout='constrained')
colors=['#0072b2','#009e73','#d55e00']
weights=[0,.001,.01,.03,.1,.3,1.]
for case,col in zip(SOURCES,colors):
 rows=[allfits[case]['center_huber']]+[allfits[case][f'joint_{w:g}'] for w in weights[1:]]
 axes[0].plot(weights,[r['metrics']['center_rmse']*100 for r in rows],'o-',color=col,label=case)
 axes[1].plot(weights,[r['metrics']['axis_mae_deg'] for r in rows],'o-',color=col,label=case)
 names=['center_huber','joint_0.01','joint_0.03','joint_0.1','joint_0.3','axis_first']
 axes[2].plot(range(len(names)),[allval[case][n]['max_loo_yaw_deg'] for n in names],'o-',color=col,label=case)
for ax in axes[:2]:ax.set_xscale('symlog',linthresh=.001);ax.set_xlabel('Axis weight lambda');ax.grid(alpha=.18)
axes[0].set_ylabel('Center RMSE / scene baseline (%)');axes[0].set_title('Position fit');axes[0].legend()
axes[1].set_ylabel('Mean undirected long-axis error (deg)');axes[1].set_title('Box direction fit')
axes[2].set_xticks(range(6),['Center','.01','.03','.1','.3','Axis']);axes[2].set_xlabel('Objective / axis weight')
axes[2].set_ylabel('Largest leave-one-out yaw change (deg)');axes[2].set_title('Rotation stability');axes[2].grid(alpha=.18)
fig.suptitle('Frozen geometry: changing the objective does not resolve Study2 alignment')
fig.savefig(HERE/'objective_comparison.png');fig.savefig(HERE/'objective_comparison.pdf');plt.close(fig)
# Inspect all boxes for four candidate transforms, in one common horizontal frame.
exports=read(HERE/'study2/all_boxes_in_shot1_camera.json')
r1=np.array(data['graphs'][0]['cameras'][0]['R_world_from_camera'])
selected=['corner_huber','center_ls','joint_0.1','scene_coincidence']
fig,axes=plt.subplots(2,2,figsize=(10,9),layout='constrained')
from scipy.spatial import ConvexHull
allp=[]
for ax,key in zip(axes.flat,selected):
 for b in exports[key]['boxes']:
  p=np.asarray(b['corners'])@r1.T;xy=p[:,:2];h=ConvexHull(xy);v=xy[np.r_[h.vertices,h.vertices[0]]]
  col='#0072b2' if b['shot']=='shot1' else '#d55e00';style='-' if b['shot']=='shot1' else '--'
  ax.plot(v[:,0],v[:,1],color=col,linestyle=style,linewidth=.8,alpha=.7)
  allp.append(xy)
 ax.set_title(labels.get(key,'Scene-frame coincidence')+' (diagnostic)');ax.set_xlabel('Shot1 horizontal X (model units)');ax.set_ylabel('Shot1 horizontal Y (model units)')
 ax.set_aspect('equal');ax.grid(alpha=.15)
lo=np.concatenate(allp).min(0);hi=np.concatenate(allp).max(0);pad=.05*(hi-lo)
for ax in axes.flat:ax.set_xlim(lo[0]-pad[0],hi[0]+pad[0]);ax.set_ylim(lo[1]-pad[1],hi[1]+pad[1])
fig.suptitle('All 17 + 21 static boxes | Shot1 blue solid; Shot3 orange dashed\nCommon display frame is Shot1 gravity-aligned camera origin; no candidate accepted as physical pose')
fig.savefig(HERE/'study2_all_boxes_topdown.png');plt.close(fig)

lines=['# 统一坐标对齐探索：中心、框方向与坐标表示的受控对照','',
'## 结论','',
'建议采用 **固定对应 + 保持重力方向 + 中心鲁棒误差与框长边方向分开建模 + 多候选与稳定性检查**，最后把全部框导出到 Shot1 相机坐标。',
'但本次冻结 study2 几何没有得到可接受为可靠物理对齐的解。加方向项改善长边一致性，却使中心误差变大并出现 180° 分支跳变；单纯换坐标表示不改变这一问题。',
'“最优”只能在指定目标函数内讨论；本次多初值收敛检查不能证明物理正确，也不能证明全局最优。没有按杯子—笔筒是否被判异常挑选权重。','',
'## 先澄清历史流程','',
'- 原角点求解已经对每实体八角点 RMS 使用 Huber，并枚举 24 种盒角等价标记，并非纯 MSE。',
'- 相机场景局部坐标上的全框优化，与后续“各自建桌子—暖气片场景坐标再重合”是两个实验。',
'- 后续长边实验固定了场景原点与尺度，只优化共享 yaw，没有联合优化中心与方向。',
'- 本次所有变换统一为 **Shot3 → Shot1**，和旧报告 Shot1 → Shot3 的符号/尺度方向不同。重新求反向最小二乘通常也不等于旧解取逆。','',
'## 数据和方法','',
'复用原 JPEG 对应的冻结 GeoCalib+Boxer 静态图及 Codex 对应。study0/1/2 共同实体分别为 16/17/11；不重做检测、动静分类、3D 预测或身份匹配。study2 共有 17+21 个静态框，所有输出候选均包含全部 38 框。',
'每例比较 14 个主要方法，共 42 个拟合；另有固定尺度/场景参照诊断、396 次留出尝试（参考不足项保留不可求解）、108 次逐帧组合拟合、9 组阈值敏感性及 4 组额外 72 初值检查。',
'所有重计算在已有 Slurm 185272/node241 单 CPU 完成，检查负载约 .06–.11，无 GPU、新分配或模型调用。','',
'### 目标函数','',
'`L = mean_i Huber(||s Rz(theta) c_i^3 + t - c_i^1|| / D; delta=.05) + lambda * mean_j [1 - (a_j^1 dot Rz(theta) a_j^3)^2]`','',
'- D 为 Shot1 所有共同实体中心两两距离的中位数。位置项和方向项分别取均值，避免实体数量变化隐式改变权重。',
'- s>0；R 保持重力；同一个 s/R/t 用于所有 box。目标计算先做可逆中心化及尺度归一化以改善数值条件。',
'- 方向为水平长边无向轴；两边的长宽比都 ≥1.2 才参与。study2 有画框、桌子、地毯、暖气片 4 项。',
'- lambda 预先设为 0/.001/.01/.03/.1/.3/1；另测纯中心 L2、方向优先、仅原有 anchor_eligible 参照。',
'- 有界 log 归一化尺度 [-4,4] 只防止数值溢出/零尺度；边界解标注退化，不作为有效配准。',
'- 每次包含均匀 yaw 初值、中心解初值以及无向轴的两种 180° 分支。','',
'## 主要结果','',
'下表中心误差均除以同一个 case 的 D，框方向误差仅针对合格长边。留出误差指移除一个实体后预测该实体的位置；它检验对冻结几何的泛化，并非真实世界位置误差。','',
'| case | 方法 | yaw（度） | 尺度 | 中心 RMSE/D | 长边 MAE | 留出中心 RMSE/D | 最大留出 yaw 变化 |',
'|---|---|---:|---:|---:|---:|---:|---:|']
for case in SOURCES:
 for name in ['corner_huber','center_ls','center_huber','joint_0.01','joint_0.1','axis_first']:
  r=allfits[case][name];v=allval[case].get(name);m=r['metrics'];t=r['transform']
  held=f"{v['heldout_center_rmse']*100:.2f}%" if v else '未重测'
  yaw=f"{v['max_loo_yaw_deg']:.2f}°" if v else '未重测'
  lines.append(f"| {case} | {short[name]} | {t['yaw_deg']:.3f} | {t['scale']:.4f} | {m['center_rmse']*100:.2f}% | {m['axis_mae_deg']:.2f}° | {held} | {yaw} |")
lines+=['','study0/1 只是两个同视角数值控制，不是独立标定集。λ=.1 在这两个控制中降低方向误差并保持稳定；不能据此宣布通用最优权重。study2 的中心 L2 虽获得最小中心训练误差，仍高达约 54%，且尺度缩为 .481，不能被称为正确对齐。','',
'## 为什么 study2 无法通过改损失就修好？','',
'### 1. 原有三个参照中心给出相互矛盾的旋转要求','',
'| 参照中心连线 | Shot3 → Shot1 所需水平旋转 | 3D 距离尺度比 |','|---|---:|---:|']
names={'g01':'画框','g04':'桌子','g12':'暖气片'}
for r in read(HERE/'study2/center_pair_requirements.json'):
 if r['both_anchors']:
  lines.append(f"| {' → '.join(names[g] for g in r['groups'])} | {r['horizontal_required_yaw']:.3f}° | {r['distance_scale']:.3f} |")
lines+=['','这些连线不可能同时被一个保持重力的精确相似变换对齐。残差可能混合重建误差、参考物中心语义偏差和真实视频变化；没有真值时无法把它们全部归因于某一种。','',
'### 2. 长边只能确定模 180° 的方向','',
'4 个长边共同支持约 −59.748° 或 +120.252°；两者长边平均误差同为 4.079°。',
'自由中心拟合倾向选择 −59.748°，并缩小尺度。另一个分支的自由尺度趋近零边界，不能解释为成功配准。',
'为排除自由缩放的影响，又用原有参照框尺寸对角线比的中位数固定尺度 .8755；两分支中心误差仍约 95.0% 和 119.0%，问题未消失。该固定尺度也只是模型框提供的诊断先验。','',
'### 3. 结果对移除实体和选择帧高度敏感','',
'中心+方向 λ=.1 去掉一个实体时可跳变 177.11°；逐帧 6×6 组合也存在两个旋转分支。逐帧拟合只使用两侧都有效的记录，不用融合值填补缺帧。','',
'特别检查从拟合中移除杯子和笔筒（仅作分析，不用此干预选结果）：','',
'| 方法 | 全部实体 yaw | 去掉杯子/笔筒 yaw | 全量拟合下该对 cosine | 排除该对拟合后的 cosine |','|---|---:|---:|---:|---:|']
for r in excl:
 n=r['method'];lines.append(f"| {short[n]} | {fits[n]['transform']['yaw_deg']:.3f}° | {r['transform']['yaw_deg']:.3f}° | {fits[n]['metrics']['focal_pair_cosine']:.4f} | {r['metrics']['focal_pair_cosine']:.4f} |")
lines+=['','这说明对齐不稳定可以改变后续异常判断，不能直接以优化后 cosine 最高或是否检出指定案例来选配准。','',
'## 相机坐标 vs 场景坐标','',
'若 F1、F3 是各自建立场景坐标的相似变换，则场景坐标求得 T_scene 后，原坐标变换为 `T = inverse(F1) o T_scene o F3`。',
'只要仍自由优化同样的 s/yaw/t，位置误差按目标坐标单位同步归一化，换坐标只是可逆表示变化。五组实际重求解再还原的最大中心差如下：','',
'| 方法 | 最大中心差/D |','|---|---:|']
for r in gauge:lines.append(f"| {r['method']} | {r['max_normalized_prediction_difference']:.3e} |")
lines+=['','区别在于：若强制场景原点、轴、尺度直接重合，就把参考物估计当作硬约束；它不再等价于自由优化。',
'因此工程上建议直接在重力对齐的相机局部坐标求解，减少中间约束；最终可导出到实际 Shot1 OpenCV 相机坐标。设 Q1/Q3 为相机→重力坐标旋转，导出旋转为 `Q1.T @ Rz(theta) @ Q3`，平移为 `Q1.T @ t`。所有 38 框的角点换算和重力对应均已独立回放。','',
'## 推荐后续采用的方案及准入条件','',
'1. 保留已确定的跨 shot 实体对应；为配准选取空间分散、物理方向可辨的结构参照，移动/疑似冲突物体不充当自身关系的唯一对齐依据。',
'2. 使用上述中心鲁棒项 + 无向长边项，保持重力；显式保留 180° 竞争解，避免仅凭最低中心损失自动消歧。',
'3. 必须用独立的有向空间证据消歧，例如可对应的桌角/墙角、墙面布局或原图静态特征多视几何；这一像素几何消歧组件本次没有实现或验证。',
'4. 分别检查位置残差、方向残差、留出稳定性、帧间稳定性和尺度退化；没有稳定共同解则标记“对齐不可判定”。当前没有校准过的通用准入阈值，不能硬设一条并称可靠。',
'5. 对齐通过后，把所有 box 一次性变换到 Shot1 相机坐标，计算共同静态实体对 cosine 矩阵、均值和异常明细。',
'6. 对 cosine 而言，平移在差分中抵消、正尺度在归一化中抵消；旋转可靠性是核心。s/t 可用于坐标展示与其他空间指标，但不应让它们的拟合优度代替方向可靠性。','',
'当前 study2 在第 3/4 步缺乏足够证据，未选任何候选为正式对齐，也未改 Gs 存在性或空间评分。探索给出了改法的效果与失败原因，但尚不能从现有框宣布物理意义的“最优方案”。','',
'## 如果没有实体对应呢？','',
'对应未知时，需联合解决离散匹配与连续变换，重复物体、部分可见与实际布局冲突会增加歧义。本例已经有 11 对固定身份，没有必要丢掉它们重新做几何最近邻。稳健对应配准可参考 [TEASER 原论文](https://arxiv.org/abs/2001.07715)；本实验未运行 TEASER，也没有借用其理论保证。','',
'## 验证、产物与边界','',
'- 9 项数学/行为测试通过：解析梯度、已知变换、中心闭式解对照、无向轴翻转、坐标等价、局部运动抗异常、保留交换信号、固定尺度/逆变换、退化方向。',
'- 所有主要结果的中心误差/cosine 精确回放，原始图/对应哈希不变。4 个 study2 目标增加 72 yaw 初值未找到更低目标；这不是全局最优证书。',
'- 首轮留出驱动在 study0 仅两参照、移除一个后中止；修正为如实保存不可求解项后完成，不把剩余非参照留出 yaw=0 解释为参照稳定。无模型重试。',
'- `study*/fits.json`、`validation.json` 保存全部主拟合/留出；`study2/frame_sensitivity.json` 保存 108 次帧组合；`scale_diagnostic.json` 保存固定尺度与两个分支。',
'- `study2/all_boxes_in_shot1_camera.json` 保存每个候选的全部 38 个框，统一到 Shot1 实际相机坐标；每个候选明确 physical_pose_accepted=false。',
'- `objective_comparison.png/.pdf` 为目标和稳定性对照；`study2_all_boxes_topdown.png` 为四种候选全框俯视图。',
'- 未获得人工/实测真值；这些训练/留出残差都针对冻结模型几何。原视频未变化，算法分数变化不表示视频更一致。','']
(HERE/'RESULT.zh.md').write_text('\n'.join(lines))
summary=dict(recommendation='direct_camera_gravity_constrained_robust_center_plus_axial_orientation_with_ambiguity_and_stability_checks',
 study2_physical_alignment_accepted=False,max_gauge_prediction_difference=max(r['max_normalized_prediction_difference'] for r in gauge),
 tests=9,main_case_fits=42,frame_fits=108,control_joint_lambda_0_1={c:dict(fit=allfits[c]['joint_0.1']['metrics']['center_rmse'],heldout=allval[c]['joint_0.1']['heldout_center_rmse'],yaw_loo=allval[c]['joint_0.1']['max_loo_yaw_deg']) for c in SOURCES},
 focal_pair_exclusion=[dict(method=r['method'],yaw=r['transform']['yaw_deg'],cosine=r['metrics']['focal_pair_cosine']) for r in excl],
 old_scores_changed=False)
save(HERE/'summary.json',summary)
state=read(HERE/'run.json');state.update(status='completed_exploration_no_reliable_study2_pose',ended=time.time(),tests_passed=9);save(HERE/'run.json',state)
save(HERE/'report_hashes.json',{n:sha(HERE/n) for n in ['RESULT.zh.md','summary.json','objective_comparison.png','objective_comparison.pdf','study2_all_boxes_topdown.png','report.py']})
print(json.dumps(native(summary),ensure_ascii=False,indent=2),flush=True)
