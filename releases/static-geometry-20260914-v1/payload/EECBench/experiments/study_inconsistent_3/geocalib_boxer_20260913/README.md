# GeoCalib + BoxerNet：Study 3 shot1/shot3 实际对照

## 结论

已实际运行官方 GeoCalib 与 BoxerNet，使用冻结的 WeDetect 聚类实体和逐帧二维 grounding。GeoCalib + Boxer 的裁切后投影中位 IoU 从原 Codex SparseScene3D 的 **0.433/0.522 提高到 0.609/0.667**（shot1/shot3）。41 个实体节点全部保留；236 个可见实体帧均有三维框，其余 10 个不可见实体帧明确保留空几何。

这是二维提示条件下的投影拟合改善，**不是独立三维准确率提升的证明**。Boxer 本身接收被比较的二维框；没有三维真值、真实内参或真实深度。本轮没有重新检测、聚类、跨 shot 配准或判定异常。

## 查看产物

- [原图投影对照页](projection_viewer.html)：选择 shot、帧、实体和相机来源。绿色是 grounding 框，橙色是原 Codex OBB 投影包络，紫色是 Boxer 框及真实三维边线的投影。
- [可旋转三维查看页](scene_viewer.html)：每个 shot 独立显示，选择帧；两个 shot 尚未世界配准。
- [完整实体场景图](boxer_scene_graph.json)：19+22 实体、原候选 IDs、原始逐帧观测、逐帧三维预测及不可见状态。
- [逐实体比较](comparison.json)、[标定几何复核](geometry_review.json)、[参数扰动结果](sensitivity.json)。
- [独立审计](audit.json)、[版本和哈希](provenance.json)、[测试日志](tests.log)。

两个 HTML 页面均可下载后在本地浏览器离线打开。已生成，未进行浏览器自动化运行测试。

## 输入与实验分组

原始测例为 Study 3，portable export 中称 study2。冻结输入：`../wedetect_shot_entities_20260912/run01`。两 shot 各六帧 0/24/48/72/96/120，原图 852×480，图像哈希逐一匹配。所有可见二维框保持原实体聚类结果；不可见帧不强行预测画外框。

| 组别 | 相机与重力 | 三维框 | 深度输入 |
|---|---|---|---|
| 历史基线 | 原 Codex | 原 Codex SparseScene3D | 无 |
| 相机控制组 | 原 Codex | BoxerNet | 无 |
| 主实验 | GeoCalib | BoxerNet | 无 |

GeoCalib 对每个 shot 的六帧联合估计共享内参；根据固定机位假设，对六个上方向做单位向量均值，作为本 shot 一致的姿态基准。保留各帧原始预测与不确定性输出，不将其视为已校准的真实误差范围。未使用待检异常标签。

Boxer 使用官方 960×960 输入适配方式，同时缩放内参和框，原 XYXY 转换为官方 XXYY；按官方 `no_sdp` 路径提供空深度点集。所有输出都保留，没有按模型分数筛掉困难实体。

## 相机与几何复核

| 项目 | Shot1 | Shot3 |
|---|---:|---:|
| 原 Codex 焦距 fx，px | 958 | 1273 |
| GeoCalib 共享 fx，px | 969.13 | 1042.13 |
| 与原估计的上方向夹角 | 2.83° | 3.39° |
| shot 内上方向相对共识的最大偏差 | 0.51° | 0.30° |

主点沿用 GeoCalib 模型的居中假设，原图对应约 (426,240)。相机 OpenCV 轴为 X右、Y下、Z前；GeoCalib 零倾角的原始向量为 (0,-1,0)，在此约定下作为物理上方向；物理向下取其反号。Boxer 的世界 Z 向上，通过合法旋转明确转换，未直接混用两个库的同名 gravity 字段。

Root Codex 查看了两张原始 frame0，记录每张四条可见竖直边的近似端点。竖直线方向误差支持 GeoCalib 作为可用候选，但这些点不是人工标定真值。旧桌面角点在 GeoCalib 内参下的两个方向非正交误差约为 shot1 0.59°、shot3 7.74°；其平面法向与估计上方向分别相差约 2.70°、5.56°。这说明 shot3 的建筑线索与现有桌角假设仍有分歧。保留 GeoCalib 原值，不用实体框的 IoU 调参选择标定。

## 全部可见实体帧的重投影对照

投影八角点，取二维包络，裁切到原图边界，与相同 grounding 框计算 IoU。相同 shot 三组使用完全相同的实体帧集合。

| Shot | 方法 | 中位 IoU | 平均 IoU | IoU≥0.5 | IoU≥0.75 |
|---|---|---:|---:|---:|---:|
| shot1，106 项 | 原 Codex | 0.433 | 0.466 | 37/106 | 18/106 |
| shot1 | 原 Codex 相机 + Boxer | 0.577 | 0.574 | 70/106 | 20/106 |
| shot1 | GeoCalib + Boxer | **0.609** | **0.581** | **70/106** | **24/106** |
| shot3，130 项 | 原 Codex | 0.522 | 0.526 | 76/130 | 12/130 |
| shot3 | 原 Codex 相机 + Boxer | 0.528 | 0.561 | 73/130 | 16/130 |
| shot3 | GeoCalib + Boxer | **0.667** | **0.619** | **100/130** | **31/130** |

主实验投影面积/grounding面积中位数从 1.95/1.71 倍降低到 1.39/1.46 倍。重复静态帧不是独立统计样本；IoU改善不能直接推广到其他场景。

### 关键实体

| 实体 | 原 Codex 中位 IoU | GeoCalib + Boxer |
|---|---:|---:|
| shot1 杯子 | 0.433 | 0.528 |
| shot1 笔筒 | 0.263 | 0.419 |
| shot1 台灯 | 0.673 | 0.802 |
| shot1 小桌/花架 | 0.176 | 0.323 |
| shot1 小桌盆栽 | 0.015 | 0.249 |
| shot3 杯子 | 0.586 | 0.635 |
| shot3 笔筒 | 0.671 | **0.612，下降** |
| shot3 纸巾包 | 0.593 | 0.676 |

Shot1 笔筒的投影面积仍约为 grounding 的 2.39 倍。整体改善不表示细小、遮挡或细长实体均已准确。

## 标定敏感性

在两张 frame0 上分别做焦距 ±10%、上方向绕相机 X 轴 ±3° 的四种扰动，不改 grounding，也不根据结果选择参数。杯筒预测深度变化约 9%–14%，二维 IoU 仍可能相近或更高。例如 shot3 笔筒在上方向 +3° 条件下深度增加约 14.2%，IoU 仍约 0.643。这直接说明二维重投影不足以唯一确定三维深度。扰动范围是诊断设置，不是置信区间。

## 模型范围与未完成事项

- Boxer 官方当前头部预测重力对齐的 7DoF 框（中心、尺寸、yaw），不是任意 pitch/roll 或关节形变。代码默认最小边长为 0.05 模型长度单位；很薄或很细的实体有表达限制。
- 无深度时的尺度来自模型先验。场景 JSON 使用相机原点的 shot 局部 Z-up 系，不与原桌长=1世界系混合，也不宣称两 shot 已对齐。
- 三维 OBB 是完整物体范围假设，grounding 描述可见部分；遮挡/截断时不能强制二者完全贴合。
- 本轮仅替换并验证几何前端，没有重新宣布台灯、纸巾或杯筒的跨 shot 冲突。
- 后续优先验证支撑接触和局部深度，并处理 shot3 的建筑竖直方向与桌面透视分歧。不能通过跨 shot 强制物体同位置来抹掉异常。

## 来源、资源与验证

官方源码未修改：

- [GeoCalib](https://github.com/cvg/GeoCalib)，commit `97b8968e7798a66bf04fcf791fb535624241bda7`。
- [Boxer](https://github.com/facebookresearch/boxer)，commit `1f86542dc342a4b1d474c87c97c5d1d6566d9148`。

项目内隔离 venv 复用 ROCm PyTorch 2.7.1。模型权重、源码、输入及适配代码 SHA256 记录在 provenance.json。GeoCalib 使用官方 pinhole 权重；Boxer 主 checkpoint 320/320 张量全部加载；DINOv3 权重来自官方 Boxer 发布目录。

使用已有 Slurm 分配182691/node210 的物理GPU4，UUID `GPU-c41711cdb16de32f`。每次 GPU 启动前检查利用率、显存和每个 KFD 进程的物理 GPU 映射；其他任务保持在0–3。结束后GPU4恢复0%利用率与约13MB基线显存。没有新资源申请。

实际处理：GeoCalib 两次六帧批量标定；Boxer 主对照24次单帧推理，加敏感性8次，共32次，632个框预测（472主对照+160扰动）。无新增配置 Codex CLI 模型调用；几何视觉复核由当前任务的 Codex 直接完成。

10 项新增坐标/指标测试通过；472 个主对照预测通过正尺寸、SO(3)、角点/中心/尺寸一致性、世界到相机转换、原像素投影复算、全实体帧覆盖及原图哈希审计。HTML 已生成，浏览器运行未自动测试。

## 复现

入口位于 `EECBench/scripts/run_geocalib_boxer.py`；依次使用 `--stage calibrate`、`--stage boxer`。运行 GPU 阶段前必须重新选择空闲 GPU，并使用 `guard_geocalib_boxer_gpu.py` 的物理索引+UUID保护。随后在计算节点CPU运行 `evaluate_geocalib_boxer.py` 和 `audit_geocalib_boxer.py`。敏感性使用 `--limit-frames 1 --variants geocalib_focal_low geocalib_focal_high geocalib_pitch_low geocalib_pitch_high`。完整运行命令和失败/成功日志均保留。本轮原始 SparseScene3D 结果未覆盖。
