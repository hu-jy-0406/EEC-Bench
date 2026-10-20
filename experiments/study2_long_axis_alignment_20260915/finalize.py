"""Save a reviewable report and append scoped research provenance."""
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
summary=json.loads((BASE/'summary.json').read_text())
rows=json.loads((BASE/'entity_diagnostics.json').read_text())
before,after=[summary['metrics'][k] for k in ['before','after']]
table=['| 实体 | 两侧最小水平长宽比 | 旋转前夹角 | 旋转后夹角 |','|---|---:|---:|---:|']
for r in rows:
    if r['eligible']:
        table.append(f"| {r['name']} ({r['group_id']}) | {r['minimum_aspect_ratio']:.3f} | {r['absolute_angle_before_deg']:.3f}° | {r['absolute_angle_after_deg']:.3f}° |")
report=f'''# Study2：匹配框长边方向约束

## 结果

在上一轮独立建立的两个场景坐标系基础上，固定 Shot3，将 Shot1 **整体绕桌中心、沿 Z 轴旋转 −26.466072°**。从 +Z 朝原点看为顺时针。
四对有明确水平长边的框，平均轴向夹角从 {before['angle_mae_deg']:.4f}° 降到 {after['angle_mae_deg']:.4f}°，角度 RMSE 从 {before['angle_rmse_deg']:.4f}° 降到 {after['angle_rmse_deg']:.4f}°。

{chr(10).join(table)}

这支持用户提出的“还需要再旋转一些才能对齐长边”。但全部 11 对匹配框的中心 RMSE 从 {before['all_11_center_rmse']:.6f} 增至 {after['all_11_center_rmse']:.6f}，八角点 RMSE 从 {before['all_11_corner_rmse']:.6f} 增至 {after['all_11_corner_rmse']:.6f}，单位均为各自原始桌子到暖气片的水平距离。没有人工真值来证明新结果是正确场景位姿。

## 输入与约束

- Study2 指导出命名中的 study2，即旧 Study3，目录 study_inconsistent_3。仅比较 Shot1 和 Shot3。
- 使用 study2_scene_frames_20260915 的冻结结果；各 shot 先独立构造场景坐标系：桌中心为 O，Z 向上，Y 为桌子到暖气片的水平方向，水平基线归一化为 1。
- 11 对既有一对一匹配保持不变。全部 17+21 个静态框保留；静态表示该 shot 内静止，并不证明跨 shot 相同实体的姿态或位置没变。
- 只增加一个共享变量 θ。场景坐标内平移固定为 0，尺度固定为 1；每个框的尺寸和框间相对结构保持不变。Shot1 的相机位置及所有方向也随同一旋转变换。
- 无实体重新检测、重新聚类或逐实体旋转；无新的 Codex/GPU 调用。既有 Gs 分数未变更。

## 方向损失

取 OBB 两条水平边中较长一条的单位向量。竖直高度不参与偏航判断。此次输入全部为竖直 OBB；代码对倾斜框显式拒绝，不把投影对角线误当水平边。

在两侧框的水平长宽比都 ≥1.2 时才纳入方向拟合，几何规则不依赖角度是否符合预期。符合的实体是画框、桌子、地毯、暖气片；其余七对至少一侧接近正方形。全部排除原因和未拟合角度保存在 entity_diagnostics.json，不能把这些不稳定角度作为方向质量的主指标。

对每对单位长边方向 u、v，损失为 `1 − (vᵀ Rz(θ) u)²`，四对等权平均。它等于 `sin²(θ − δ)`，δ 是这对框给出的旋转角。正反方向是同一条长边，因此按 180° 周期处理；没有 θ² 的角度正则，也没有把 θ 强制趋向零。

解析解为 `θ = 0.5 atan2(Σ sin 2δ, Σ cos 2δ)`。长边本身不能解决 180° 翻转歧义，本次选择距现有场景对齐角度最近的一支 [−90°,90°)。这是一项明确的分支约定。

## 稳定性和位置代价

- 逐对留出重拟合：旋转 −23.7622° 至 −27.9564°。这是四对方向证据的敏感性检查，不能当置信区间。留出角度误差见 summary.json。
- 水平长宽比阈值 1.1/1.2 保留四对，均为 −26.4661°；1.3/1.5/2.0 保留三对，为 −27.9564°。阈值及结果全部保留。
- 暖气片 Shot1 中心从 [0,1,−0.042508] 转为 [0.445668,0.895198,−0.042508]；Shot3 为 [0,1,−0.033949]。二者中心距离从约 0.00856 增为 0.45791 个场景单位。原先“桌到暖气片方向精确重合”的定义在第二阶段变成近似关系。
- 桌中心仍精确重合，因为它是旋转中心。改善的长边方向和恶化的中心位置说明当前冻结几何的不同线索不能被这个固定原点、固定尺度的单一旋转同时满足；不能据此单独判定是实体真实移动、匹配错误还是重建误差。
- 旋转后的原始输入坐标等价 yaw 为 −120.252216°，尺度仍为 1.024121268；这是组合变换的换算，不是重新拟合相机坐标系。完整矩阵和平移见 summary.json。

## 验证与产物

已有 job185272 / auh7-1b-gpu-241 单 CPU，线程数均限制为 1。四项数学测试通过（0.024s），包括已知旋转/轴反向、轴重标号/忽略高度、退化证据拒绝、方向目标极小值。36,001 个角度采样复核解析全局极小值（模 180°）。

所有 Shot1 框、相机位置及方向的逆变换、重力、固定原点和尺度、原始坐标组合变换及输入哈希均通过审计。交互图显示全部 38 个框/456 条边；在模拟 DOM 中实际执行了调整前后切换、目标 Shot3 不变、往返、视角、图例和 320px 布局检查。未执行真实浏览器测试。

- fit_long_axes.py / test_long_axes.py：可复现拟合及测试。
- summary.json / entity_diagnostics.json：目标函数、变换、逐实体指标、留出与阈值结果。
- shot1_aligned_scene.json / shot3_aligned_scene.json：最终完整场景图；frame 字段保留初始构建元数据，Shot1 的 alignment_to_shot3_scene 显式记录后续旋转。
- overlay_before.json / overlay_after.json：完整框和相机显示数据。
- audit.json / visual_test.json / code_hashes.json：验证与输入/代码追踪。

尚未作为正式 Gs 对齐默认方法，也未运行后续一致性复核或重评分。
'''
(BASE/'RESULT.md').write_text(report)
audit=json.loads((BASE/'audit.json').read_text())
audit.update(tests_passed=4,test_seconds=.024,visual_test='visual_test.json')
(BASE/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
files=list(BASE.glob('*.py'))+list(BASE.glob('*.js'))+list(BASE.glob('*.html'))
(BASE/'code_hashes.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files},indent=2)+'\n')

heading='## 2026-09-15 — Study2 shared yaw from matched horizontal long edges'
note='''
User clarified that matching boxes' long-edge directions should agree, potentially requiring further whole-scene rotation. Added a single yaw refinement after the independent desk/radiator scene-frame construction, using frozen Study2 (oldStudy3) Shot1/Shot3 geometry and 11 correspondences. Fixed scene origin/scale, Shot3 target, gravity; no per-entity rotations. Long edges are undirected horizontal OBB axes; both aspect ratios must be >=1.2, determined without angular residuals. Four pairs eligible: painting g01, desk g04, rug g10, radiator g12; seven near-square pairs excluded with explicit records. Equal-entity mean sin²(theta−delta); no theta² regularizer. Analytic doubled-angle fit, closest-zero branch of the180-degree ambiguity.

Shared additional yaw −26.4660720775deg. Four-pair mean axial error26.48864→4.07850deg; angleRMSE26.93195→4.86643deg. All11 centerRMSE1.116871→1.344458 and cornerRMSE1.127634→1.346741 scene units worsen. Radiator center originally aligned by frame definition separates~.458units, while desk center staysfixed. Therefore this validates agreement of observed long-edge cues, not globally correct scene alignment or human truth. Existing geometry supplies conflicting position/direction evidence. Input-coordinate equivalent yaw−120.252215763deg,scale1.024121268; derived only, not a new camera fit.

Four leave-one-pair-out fits span−23.76219 to−27.95638deg (notconfidenceinterval). Aspectcutoff1.1/1.2 same4pairs/−26.4661;1.3/1.5/2.0 same3pairs/−27.9564. Four tests pass .024sec; 36,001-angle objective replay, all-box/camera inverse replay, gravity/origin/scale/composed rawtransform, frozen sourcehashes pass. Existing185272/node241 CPU only. All38boxes/456edges shown in before/after toggle with sameviewbounds; JS executed in mockDOM checks state change, Shot3 fixed, roundtrip, view/legend/320px. Realbrowsernot tested.

Artifacts:EECBench/experiments/study2_long_axis_alignment_20260915/{RESULT.md,summary.json,entity_diagnostics.json,shot1_aligned_scene.json,shot3_aligned_scene.json,overlay_before.json,overlay_after.json,audit.json,visual_test.json,code_hashes.json}. Inline:/vast/users/guangyi.chen/.codex/visualizations/2026/09/15/01a0a3ab-7a2b-73a2-b1af-77ad53986c4f/study2-long-axis-alignment.html. No model/GPU calls, no detection/matching/static-label/Gs score changes. Direction-only pilot completed; not adopted into production Gs or claimed full consistency.
'''
for name in ['research-log.md','findings.md','docs/continuity.md']:
    path=ROOT/name
    old=path.read_text()
    if heading not in old:
        path.write_text(old+'\n\n'+heading+'\n'+note)
state=ROOT/'research-state.yaml'
entry='''

study2_long_axis_yaw_refinement_20260915:
  status: completed_direction_only_pilot
  base: study2_independent_scene_frames_20260915
  report: EECBench/experiments/study2_long_axis_alignment_20260915/RESULT.md
  objective: equal_entity_mean_sin_squared_horizontal_axial_difference
  horizontal_aspect_ratio_threshold_both_shots: 1.2
  eligible_pairs: 4
  fixed_matches: 11
  additional_shared_yaw_deg: -26.466072077520877
  scene_translation: [0, 0, 0]
  scene_scale: 1
  theta_regularization: false
  per_entity_rotations: false
  eligible_axis_mae_before_after_deg: [26.488640851355633, 4.078501467376126]
  all_matched_center_rmse_before_after: [1.1168713695609533, 1.3444576590384107]
  all_matched_corner_rmse_before_after: [1.127634098382033, 1.3467406688320747]
  conclusion: long_edge_agreement_improves_but_position_alignment_worsens
  tests_passed: 4
  audit: pass
  interactive_controls_mock_dom_tested: true
  browser_execution_tested: false
  human_ground_truth_validated: false
  production_Gs_changed: false
  scores_changed: false
  model_calls: 0
  gpu_calls: 0
  visual: /vast/users/guangyi.chen/.codex/visualizations/2026/09/15/01a0a3ab-7a2b-73a2-b1af-77ad53986c4f/study2-long-axis-alignment.html
'''
if 'study2_long_axis_yaw_refinement_20260915:' not in state.read_text():
    state.write_text(state.read_text()+entry)
print(BASE/'RESULT.md')
