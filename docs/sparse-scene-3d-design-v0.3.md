# 稀疏三维场景表征 v0.3：坐标系、OBB、观测与约束

这次升级把三维几何状态作为主体，关系图作为它的派生结果和补充约束。目标不是换一种方式写 left/right，而是让同一套实体、坐标轴、相机和原图证据能够联合成立。采用稀疏三维布局估计，不生成点云、网格、纹理、NeRF 或完整场景表面。

## 为什么需要升级

| 版本 | 主体 | 能表达什么 | 缺口 |
|---|---|---|---|
| v0.1 | 带锚点的定性边 | 支撑、包含、足迹顺序、可见性 | 每条边可局部合理，但没有同一个三维状态保证整体自洽 |
| v0.2 | 支撑中心顺序及局部证据 | 双轴位置次序、遮挡下的有界推断 | 缺少完整高度、空间体积、统一相机模型和坐标系变换 |
| v0.3 | 坐标系中的三维实体状态 + 观测约束 | 三维相对位移、朝向、占据范围、跨视角对齐 | 几何推断质量仍需投影与独立证据检验 |

v0.1/v0.2 不应被称为已经完备的三维场景表征。用户提出的 3D bounding box + 坐标系方向是合适的升级起点，但只存一组确定的 3D 数字仍不足以处理单目歧义和缺失证据。

## 推荐结构：SparseScene3D

```text
SparseScene3D
  conventions                坐标轴、单位、矩阵方向、四元数顺序
  frames                     场景/承载物/相机坐标系及变换
  entities                   冻结 entity ID、实例匹配与粒度
    states                   按时间区间分开的三维状态
      oriented_box           位置、尺度、朝向、实体自身对称性
      grounding              支撑面和接触部位
      uncertainty            估计范围、未知维度、估计来源
  observations               每帧可见区域、可见部位、二维检测
  constraints                投影、支撑、共面、局部顺序等证据约束
  alignment_hypotheses        跨 shot 的合法变换及其证据/不确定性
  comparisons                已支持冲突、条件冲突、互补、未决
```

保持全部冻结实体。看不到底部、无法定位的实体也有节点，几何可以为空或具有多个假设，不通过删除节点掩盖问题。单个物体、集合和组件不能未经匹配就当成相同实例。

### 1. 坐标系及单位

全局场景坐标系 `W` 是任意但固定的右手坐标系。通常令 +Z 向上，用稳定建筑结构或大型固定承载物确定水平轴。正方向用物理端点/侧面标识，并保存对应图像证据，不用每帧的屏幕左/右重新定义全局方向。

单个 shot 可以先有自己的 `W_s`。它只是一个局部坐标基准，只有求出 `T_W_from_Ws` 后才成为统一全局数据。**两个 shot 都写 “world” 不表示它们的坐标已经一致。** 没有消除的 180° 朝向歧义保留为两个假设。

单目不应虚构绝对米制尺寸。可设一个稳定参照物长边为 1 单位，并声明尺度基准。不同基准之间允许正尺度的 Sim(3) 变换。所有全局 XYZ 使用同一长度单位；承载面上的归一化 UV 是另一种局部参数，必须通过承载物尺寸和姿态转换为 XYZ，不能把不同物体的 UV 直接混当世界坐标。

在当前原型中，局部 W_s 的原点是主桌面中心，桌面 z=0，桌长=1，+Z 向上，+X 沿长边，+Y 由右手规则决定。原型直接估计全部实体在 W_s 中的 OBB；更多承载物局部 frame 的层级分解是该结构的扩展，不声称已全部实现。

### 2. 三维实体状态

每个状态保存 `center_world[3]`、`size_xyz[3]`、`rotation_wxyz[4]`，三维盒子为有朝向包围盒 OBB。四元数表示盒子局部坐标到所属场景坐标的旋转。盒子是完整物体的粗包络，包括合理估计的遮挡部分；二维检测框通常只描述可见区域，两者不可直接等同。

还保存 `support_parent_id`、时间范围、图像证据及估计来源。支撑点/支撑中心与三维包围盒中心是不同的位置：比较“谁更高”可能用中心，比较“落在桌上的哪个位置”应使用接触/落位参数，不能混用。

隐藏部分允许模型基于形状与接触给出估计，但必须标注为 amodal estimate，并保留深度/高度不确定性。物体对称性也要存储，例如圆柱体的绕竖直轴朝向往往不可辨识，不把这种自由度误报成旋转冲突。

最小状态示例（结构示意，不是测例真值）：

```json
{
  "entity_id": "entity_A",
  "frame_id": "shot1_world",
  "state_id": "state_0",
  "time_scope": {"frame_ids": [0, 24]},
  "oriented_box": {
    "center_xyz": [0.2, -0.1, 0.05],
    "size_xyz": [0.08, 0.08, 0.1],
    "rotation_wxyz": [1, 0, 0, 0],
    "symmetry": "rotation_about_z"
  },
  "grounding": {"support_entity_id": "table_A"},
  "uncertainty": {
    "kind": "heuristic_interval",
    "center_halfwidth_xyz": [0.03, 0.04, 0.02],
    "calibrated_probability": false
  },
  "basis": "visual_amodal_estimate"
}
```

只留区间还不够表达所有歧义：相机、尺度和多个实体位置常有关联。完整版应保留成组的 `scene_hypothesis`，不能从不同候选相机各挑一个最合意的物体位置拼成“场景”。当前原型保留原始场景提案、平面校验候选及多个坐标系对齐分支，不声称已构造完整概率后验。

### 3. 相机与图像观测

相机内参 K 保存 fx/fy/cx/cy；外参明确为 world-to-camera：

`p_C = R_CW p_W + t_CW`, `C_W = -R_CW^T t_CW`。

相机采用 OpenCV 约定：x 向图像右，y 向图像下，z 向前。所有 R 必须满足 `R^T R = I`、`det(R)=+1`。矩阵方向和四元数顺序必须写进契约，不能靠字段名猜测。

投影采用 `u ~ K(R_CW p_W + t_CW)`。对估计盒子的八个角点、承载面角点和可见部位做投影检查。若一个估计要把相机放到桌面下方才能拟合“看见桌面上表面”的图像，说明轴符号或几何假设有问题，不能只看像素残差小就接受。

二维检测框与投影的 amodal 包络只作诊断：一个被遮挡物体的可见框完全落在更大的三维投影内是正常现象，低 IoU 不直接证明物体错；大盒子覆盖了可见框也不证明三维估计正确。

### 4. 关系是几何的派生量，同时保留独立证据

对同一参考系下的实体 i、j，可计算三维相对位移 `delta = c_i - c_j`，在指定物理轴 a 上比较 `a^T delta`。对不确定位置得到区间；区间跨过 0 表示顺序不确定。正负号属于固定物理轴，而不是图像坐标。

还可以表达相对距离、支撑位置、朝向差、某轴的分离/重叠、相对承载物的位置与高度。拓扑关系仍保留为独立证据约束：OBB 重叠不等于实体接触，包围盒包含也不总能证明真实物体包含，不能用粗盒子替代所有关系判别。

## 跨 shot 对齐和比较

1. 先对齐实体身份/粒度，再用稳定参照物估计坐标变换。给模型的对齐输入不含可移动被测物体的三维状态；图像用于核对固定建筑和承载物端点。
2. `p_A = s R_AB p_B + t_AB`，s>0，R 属于 SO(3)。+Z 向上时水平对齐通常只剩 yaw；长方形参照的 180° 歧义不能随意消除。
3. 不允许对 x/y/z 各自独立改符号造成镜像；也不允许用待检实体的移动去“改善”对齐。测试参照实体本身时，需要去掉它重新估计变换，不能让它证明自己的不变。
4. 将 B 的状态和不确定性变换到 A/W。对相对位移，平移误差会抵消；旋转/尺度误差仍要传播。不能把所有坐标误差机械相加，也不能忽略共同相机带来的相关性。
5. 在所有证据允许的对齐/状态假设下都无法满足连续性，才是支持充分的空间冲突；有些假设冲突而另一些相容，标记对齐依赖；几何投影未通过，标记几何未验证。
6. 互补视角可增加新的实体或缩小旧实体的几何范围；冲突假设并存，不能平均融合成一个两边都没出现过的位置。

存在性依旧需要观测层：将旧 OBB/诊断部位投到新视角生成搜索区域，再检查视锥、遮挡、细节及原图负证据。**粗 3D 盒子不能单独证明“理应可见”**，尤其不能用一个实心 OBB 代替真实物体的遮挡形状。原有双向存在性证据协议应保留。

## 模型与数值工具的分工

推荐模型输出物理语义、实例/部位对应、OBB 和相机的初始假设及不确定性；数值程序负责坐标约定、SO(3)/Sim(3)、投影、稀疏角点校验和一致性约束。GPT 的空间理解可以贡献有效初值，但不能以“模型应该懂”为由跳过可检验的几何条件。

| 候选 | 与本任务的关系 | 本次处理 |
|---|---|---|
| GPT 直接给 OBB + 相机 | 最快验证统一三维表征；也容易出现联合数值不自洽 | 已运行独立提案 |
| OBB + 相机 + 参考平面角点校验 | 增加可计算的几何检验，仍只处理少量参数 | 已做对照诊断，推荐作为当前基线 |
| 专门的单目 3D 检测器 | 可提供相机坐标系下的 3D 框，再进入同一结构 | 接口方向，未运行 |
| 全形状单目重建 | 输出网格/纹理等，计算与表征均超出当前需求 | 不采用 |

Cube R-CNN/Omni3D 的论文给出相机坐标系下的三维 cuboid，支持这种稀疏几何接口；其官方代码也有相机 K 与 8×3 box 顶点的评测格式：[论文](https://openaccess.thecvf.com/content/CVPR2023/papers/Brazil_Omni3D_A_Large_Benchmark_and_Model_for_3D_Object_Detection_CVPR_2023_paper.pdf)、[官方代码](https://github.com/facebookresearch/omni3d)。

VGGT 能预测相机、深度和点图，可作为专门几何前端的参考，但标准流程包含重建输出，本次没有运行：[论文](https://openaccess.thecvf.com/content/CVPR2025/html/Wang_VGGT_Visual_Geometry_Grounded_Transformer_CVPR_2025_paper.html)。SAM 3D 输出形状/纹理/布局，超出当前仅需稀疏盒子和坐标的范围：[官方说明](https://ai.meta.com/research/sam3d/)。

## 实现范围与测试入口

本次原型：`scripts/sparse_scene_3d.py`（契约/几何），`run_sparse_scene_3d.py`（两段独立提案和投影诊断），`align_sparse_scene_3d.py`（稳定参照对齐及不确定性比较）。每次调用、原始回复、来源和代码快照保留。过去 v0.1/v0.2 输出不覆盖。

```bash
python EECBench/scripts/run_sparse_scene_3d.py \
  --source-run EECBench/experiments/study_inconsistent_3/partial_scene_comparison_20260912/witness_v02 \
  --out EECBench/experiments/study_inconsistent_3/sparse_scene_3d_20260913/new_run
python EECBench/scripts/align_sparse_scene_3d.py \
  --source-run EECBench/experiments/study_inconsistent_3/sparse_scene_3d_20260913/new_run \
  --out EECBench/experiments/study_inconsistent_3/sparse_scene_3d_20260913/new_alignment
```

需要现有配置 Codex、NumPy、jsonschema，在已有低负载计算节点运行；不需要 GPU。完整概率推断、全部承载物层级 frame、专用 3D 检测器和全局非线性空间约束求解尚未实现。此原型用于选择表征和暴露数值问题，不等于已验证任意自然场景的三维准确率。


规范化数据由 `materialize_sparse_scene_3d.py` 导出为 `scene_graph.json`：按 shot 命名的世界坐标基准、相机 frame、每个实体状态的 frame 均具有唯一 ID，实体框定义在自己的状态 frame 内，并通过明确的 parent-from-frame 变换连接到 shot 世界。它保持两个 shot 的观测和身份对应，不把尚未解决的对齐候选混成一套坐标。

```bash
python EECBench/scripts/materialize_sparse_scene_3d.py RUN --alignment ALIGNMENT_RUN --out scene_graph.json
python EECBench/scripts/render_sparse_scene_3d.py RUN --alignment ALIGNMENT_RUN --out viewer.html
```

三个严格契约位于 `schemas/sparse_scene_3d_inference.v0.3.schema.json`、`sparse_scene_3d_alignment.v0.3.schema.json`、`sparse_scene_graph.v0.3.schema.json`。原始输出中的 reference.frame_id 被视为模型局部标识；规范化导出统一使用 `shot_id/world`，与观测帧编号分开，避免两个 shot 都使用“0”一类标识而发生冲突。

数值迭代还采用了旋转角度范围内投影极值的解析计算，再施加正尺度区间，替代容易过宽的半径惩罚。它能保留原本有证据的顺序符号，不通过忽略误差提高检出率。最初的粗界比较保留，当前测例报告使用 `comparison_tight_bounds.json`。当前实现仍将未知对齐视为条件假设，不能把其派生的相容/冲突解释成已完成世界配准后的真值。


## 当前测例的实际结论

本版本已在冻结的 Study 3 shot1/shot3 上完成三次独立处理和 25 项数值/契约测试。杯筒 X 轴结果为对齐依赖：0° 候选反转，180° 候选相容；稳定参照尚不能唯一确认世界配准。二维投影诊断支持参考平面拟合，但不能证明 OBB 三维准确。完整结果、旧轴隐含反射诊断及交互查看页见 [实验报告](../experiments/study_inconsistent_3/sparse_scene_3d_20260913/README.md)。
