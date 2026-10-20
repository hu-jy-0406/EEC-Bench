"""Create the human-readable comparison from frozen audited JSON outputs."""
import json,math,hashlib,shutil
from pathlib import Path
BASE=Path(__file__).resolve().parent
PRIOR=BASE.parent/'study12_box_registration_20260915'
def read(p):return json.loads(p.read_text())
def vec(values):return '('+', '.join(f'{x:+.6f}' for x in values)+')'
def norm(values):return math.sqrt(sum(x*x for x in values))
rows=[]
for case in ['study1','study2']:
 p=BASE/case;s=read(p/'summary.json');f=read(p/'fits.json');h=read(p/'historical_anchor_comparison.json');audit=read(p/'audit.json');sens=read(p/'sensitivity.json');loo=read(p/'leave_one_out.json');free=read(PRIOR/case/'summary.json')
 t=s['robust_transform'];L=s['baseline']
 rows.append(dict(case=case,matched=s['matched_entities'],baseline=L,gravity_transform=t,translation_norm=norm(t['translation_b']),
     rmse_free=free['methods']['box_huber']['normalized_corner_rmse'],rmse_gravity=s['methods']['box_huber']['normalized_corner_rmse'],
     loo_rmse_free=free['loo_corner_rmse']/L,loo_rmse_gravity=s['loo_corner_rmse']/L,
     historical=h['retained_transforms_evaluated'],historical_trusted=h['trusted'],historical_anchor_groups=h['anchor_groups']))
 text=f'''# {case} Shot1→Shot3：硬重力约束配准

## 设置与结论

硬约束 R·(0,0,1)=(0,0,1)，仅优化绕Z轴的有符号偏航角θ、统一尺度s>0、三维平移t，共5个参数。双方输入图的Z轴已定义为向上；该实验把此方向当作精确约束，未估计重力误差。

原始图、身份匹配与输入框和上次自由旋转实验逐项相同；各case独立处理。每个实体八角点RMS，24种等价角点编号，实体Huber δ=.05；全部明确匹配实体共同拟合。仍为8个主起点、4个留出起点，原有参数敏感性及合成移动检查保留。没有新检测、提帧、模型调用或Gs评分。

{('得到与无约束结果接近的稳定数值候选。台灯仍为未匹配项，不参与配准。' if case=='study1' else '排除了上下翻转，但未得到低残差且对留出稳定的对齐；不得直接作为可靠全局变换采纳。')}

## 变换

- s={t['scale']:.9f}，θ={t['yaw_deg']:+.9f}°（绕+Z，正值按右手规则）。
- t={vec(t['translation_b'])}，范数={norm(t['translation_b']):.9f}。
- R={t['R_b_from_a']}。
- L={L:.9f}，取目标图匹配实体中心两两距离的中位数；长度为模型坐标单位，非实测米。

| 方法 | 全部角点RMSE/L | 留出RMSE/L |
|---|---:|---:|
| 无约束三维旋转（上次） | {100*free['methods']['box_huber']['normalized_corner_rmse']:.3f}% | {100*free['loo_corner_rmse']/L:.3f}% |
| 重力约束（本次） | {100*s['methods']['box_huber']['normalized_corner_rmse']:.3f}% | {100*s['loo_corner_rmse']/L:.3f}% |

以上是归一化几何误差，不是一致性得分。Huber目标和未加权RMSE不同，约束后未加权RMSE的微小下降不意味着约束优化降低了无约束最优Huber目标。变换也不是实测相机运动。

留出拟合尺度范围{s['loo_scale_range']}，旋转最大偏差{s['loo_rotation_deviation_max_deg']:.3f}°，其余实体中心预测最大变化{100*s['loo_other_prediction_shift_max']:.3f}%L；反向独立拟合往返最大误差{100*sens['reverse_roundtrip_max_corner_error_normalized']:.3f}%L。

## 每次留出一个实体

| 实体 | 全体拟合误差/L | 留出误差/L | Huber权重 |
|---|---:|---:|---:|
'''
 for r in loo:text+=f"| {r['group_id']} {r['name']} | {100*r['fitted']/L:.2f}% | {100*r['heldout_normalized_corner_rmse']:.2f}% | {r['full_fit_weight']:.3f} |\n"
 text+='\n## 与历史锚点流程对比\n\n'
 text+=f"历史Codex输出实体对应和anchor_eligible，数值代码gs_consistency_geometry.fit_similarity拟合中心的全局Sim(3)。历史合格锚点{h['anchor_groups']}，生成{h['hypotheses_generated']}个候选，trusted={h['trusted']}。匹配和复核输出契约都没有R、t、s字段。\n"
 if h['retained_transforms_evaluated']:
  old=h['retained_transforms_evaluated'][0];ot=old['transform'];diff=old['gravity_vs_old']
  text+=f"\n实际旧候选：s={ot['scale']:.9f}，旋转{ot['rotation_angle_deg']:.6f}°，t={vec(ot['translation_b'])}。将该已有变换直接应用到本次相同17组框，以同一个L重算，RMSE/L={100*old['metrics_same_boxes_same_baseline']['normalized_corner_rmse']:.3f}%，本次={100*s['methods']['box_huber']['normalized_corner_rmse']:.3f}%。仅看非锚点14组，则旧方法{100*old['nonanchor_normalized_corner_rmse']:.3f}%、新方法{100*old['gravity_fit_nonanchor_normalized_corner_rmse']:.3f}%；新方法这些组参与了拟合，此项不是独立测试。新旧旋转相差{diff['rotation_difference_deg']:.3f}°，平移参数差范数{diff['translation_difference']:.6f}，中心预测RMS差{100*diff['center_prediction_difference_rmse_normalized']:.3f}%L。\n\n旧候选的锚点中心误差为1.064%，用了不同分母和仅3个中心，不可与全部框角点误差直接比较。旧流程要求至少4个合格锚点；此例只有3个，所以没有获准作为global_consensus。\n"
 else:
  text+='\n旧流程至少需要3个锚点生成候选，此例只有桌子g04和暖气片g12两个，所以retained_hypotheses=[]。不存在可供数值差值比较的历史全局矩阵。之后local_visual通过小区域和对应地标做视觉判断，未输出全局变换。Gs v1.2又由数值代码用桌子→暖气片方向和up构造局部坐标轴比较相对位移；这也不是拟合所有实体的全局sR+t。\n'
 text+='\n## 参数敏感性\n\n| δ | s | θ | RMSE/L |\n|---|---:|---:|---:|\n'
 for delta in ['0.025','0.05','0.1']:
  v=sens[delta];text+=f"| {delta} | {v['transform']['scale']:.6f} | {v['transform']['yaw_deg']:+.3f}° | {100*v['metrics']['normalized_corner_rmse']:.3f}% |\n"
 text+=f"\n5项新增数学测试通过。两例共28次留出误差、各1次独立重拟合、全部方法角点重算、源哈希、硬重力约束及旧锚点诊断精确回放通过。另加24个均匀偏航起点未发现更低目标；独立5参数BFGS额外改善{audit['independent_BFGS_gain']:.3g}，中心差分梯度范数{audit['gradient_norm']:.3g}，BFGS状态success={audit['independent_BFGS_success']}（{audit['independent_BFGS_message']}）。这不是全局最优证明或物理一致性认证。\n"
 text+='\n使用已有Slurm185272/node241单CPU，无GPU/新资源申请。交互图数据已核对，未执行浏览器测试。\n\n[交互式对齐图](alignment.html) · [完整变换](fits.json) · [留出结果](leave_one_out.json) · [历史对比](historical_anchor_comparison.json) · [审计](audit.json)\n'
 (p/'RESULT.md').write_text(text)
(BASE/'comparison.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
text='''# 重力约束优化与此前Codex锚点流程对照

## 结论

Study1仍得到稳定的小旋转变换；Study2虽然不再上下翻转，但误差和留出敏感性很大，尚不能采纳为可靠全局对齐。

以前确实有数值求解坐标变换的阶段：Codex先输出实体对应与锚点资格，随后代码从锚点三维中心求解s、R、t。Codex的local_visual复核没有输出数值矩阵。Study1留下1个未通过旧可信门槛的候选，Study2没有生成全局候选。

## 本次重力约束

硬约束R·up=up，双方up=(0,0,1)。仅允许绕Z轴旋转，仍可统一缩放和三维平移。其余输入、角点损失、Huber δ=.05、8个主起点与4个留出起点沿用上一实验。Study1=study_inconsistent_2；Study2=旧Study3=study_inconsistent_3。只比较每例Shot1→Shot3，没有重做视频/检测/匹配。

| 测例 | s | 绕Z旋转θ | 平移t | 平移范数 |
|---|---:|---:|---|---:|
'''
for r in rows:
 t=r['gravity_transform'];text+=f"| {r['case']} | {t['scale']:.6f} | {t['yaw_deg']:+.3f}° | {vec(t['translation_b'])} | {r['translation_norm']:.6f} |\n"
text+='\n长度为模型坐标单位，不是实测米。θ为有符号偏航角，和上一实验任意三维旋转的总角度含义不同。\n\n| 测例 | 无约束误差/L | 重力约束误差/L | 无约束留出误差/L | 重力约束留出误差/L |\n|---|---:|---:|---:|---:|\n'
for r in rows:text+=f"| {r['case']} | {100*r['rmse_free']:.2f}% | {100*r['rmse_gravity']:.2f}% | {100*r['loo_rmse_free']:.2f}% | {100*r['loo_rmse_gravity']:.2f}% |\n"
text+='''
误差为所有匹配框八角点RMSE除以本例场景基准L，不是Gs一致性得分。留出误差指逐一排除被测实体后重新拟合，再测该实体。

Study1留出拟合旋转最大变化0.211°，其他实体中心预测最大变化0.951%L；反向往返误差0.437%L。Study2对应为25.620°、55.836%L、31.142%L。重力约束只排除了不合理翻转，没有解决当前Study2图中的整体几何/匹配矛盾；残差混合单目重建误差、潜在匹配问题和真实场景变化，不能全判作视频不一致。

## 旧锚点流程究竟做了什么

1. Codex识别跨shot对应实体，给出anchor_eligible和理由。
2. 数值代码使用三维锚点中心，枚举三点组合并求proper Sim(3)，随后评估锚点残差。至少3个锚点才能生成候选，至少4个且误差通过门槛才标trusted。
3. 无可信全局变换时，Codex可用local_visual做局部参考区域的空间复核。其输出包含参考实体、文字推理及画面证据，没有全局R、t、s。

| 测例 | 合格锚点 | 生成候选 | 当时是否trusted |
|---|---|---:|---|
| study1 | 小桌g05、书桌g09、窗户g17 | 1 | 否，仅3个锚点 |
| study2 | 桌子g04、暖气片g12 | 0 | 否，不足3个锚点 |

此外，Gs v1.2的局部相对位置模块确实计算了“两个锚点方向+up”的坐标基，但由代码完成，用于比较局部相对位移；当时没有宣称全场景配准或输出可对照的全局变换。

## Study1：与旧流程已有候选直接比较

两种变换直接施加到同样的17组框，统一使用L=2.150267945。旧候选的3锚点中心误差1.064%采用不同分母，不能混入这张表。

| 方法 | s | 旋转角 | 平移t | 同组框RMSE/L |
|---|---:|---:|---|---:|
'''
r=rows[0];old=r['historical'][0];ot=old['transform'];gt=r['gravity_transform']
text+=f"| 旧Codex选锚点＋数值中心拟合 | {ot['scale']:.6f} | {ot['rotation_angle_deg']:.3f}° | {vec(ot['translation_b'])} | {100*old['metrics_same_boxes_same_baseline']['normalized_corner_rmse']:.2f}% |\n"
text+=f"| 全匹配框＋重力约束优化 | {gt['scale']:.6f} | {gt['rotation_angle_deg']:.3f}° | {vec(gt['translation_b'])} | {100*r['rmse_gravity']:.2f}% |\n"
text+='''
二者旋转相差2.349°，平移参数差范数0.118442模型单位，实体中心预测RMS差为2.054%L。新方法在这些输入框上的拟合误差较低；这不是独立标注的物理精度比较。台灯缺失仍在未匹配组中，不会被低配准误差消除。

Study2不存在历史全局矩阵，因此不能给出“优化变换减去Codex变换”的数值。没有新造一个变换并冒充历史Codex输出。

## 验证与查看

5项新增数学测试通过；两例数值/来源审计、28次留出残差重算及旧锚点诊断精确回放通过。每例另用24个均匀偏航起点检查，未找到更低目标。独立优化和有限差分支持局部驻点，但不证明全局最优。Study1独立BFGS因precision loss未报告success，已保留原状态；其有限差分梯度为1.48e-9，未发现进一步目标改善。

全部使用已有Slurm185272/node241的CPU，无GPU/新分配/模型调用。原始图、匹配与Gs分数不变；没有执行下游视觉复核。

- [Study1详细结果与历史对比](study1/RESULT.md) · [3D对齐图](study1/alignment.html)
- [Study2详细结果](study2/RESULT.md) · [3D对齐图](study2/alignment.html)
- [比较数据](comparison.json) · [新测试](tests.json) · [审计脚本](audit.py)
'''
(BASE/'RESULT.md').write_text(text)
# Preserve the reporting code alongside the numerical closure.
snapshot=BASE/'code_snapshot'/Path(__file__).name;shutil.copy2(Path(__file__),snapshot)
manifest=read(BASE/'code_hashes.json')
manifest=[m for m in manifest if Path(m['path']).name!=Path(__file__).name]
manifest.append(dict(path=str(Path(__file__).resolve()),sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),snapshot=str(snapshot)))
(BASE/'code_hashes.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Wrote audited comparison and two case reports')
