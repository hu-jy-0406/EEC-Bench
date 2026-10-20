# 三种方法生成 shot-level Gs_global

[打开三行两列的离线交互网页](comparison.html)。每行先介绍一种方法，左Shot1、右Shot3；六张图都标注相机位置、视锥、朝向和上方向。可旋转、缩放、隐藏实体、悬停看数值；颜色只在同一shot的三种方法间对应。网页约5.1MB，Plotly脚本内嵌，无外部脚本依赖；旁边JSON链接需保留目录结构，单HTML图形本身可以独立打开。

## 范围与符号

沿用用户符号 G=Gm+Gs；这里以固定实体分区表示，物体间跨分区关系没有在当前OBB集合中编码。三种方法比较的是几何生成，不重复划分实体。采用已通过隔离审计的shot1/shot3分类：17/21静止实体，人物及shot1红书排除。每种方法各生成六帧Gs、再融合一个Gs_global；六张图共114个融合框。

本轮复用已有三组几何预测并实际重新执行质量加权融合，没有新模型或GPU调用。原始数据分别来自 sparse_scene_3d_20260913/run01/scene_shot*/scene.json 和 geocalib_boxer_20260913/predictions/{codex_camera,geocalib}/shot*/frame_*.json。每个产物保存来源SHA256。

## 三种具体方法

1. **Codex直接估计3D**：从多帧图像、实体/2D框估计桌面参考系、相机、任意朝向OBB和误差范围。部分状态本就覆盖多帧，逐帧展开时保留同一source_group；它不是六次独立几何预测。重复状态不会增加独立投票数。优点是语义和场景参考系表达灵活，局限是尺寸、深度和误差都是未校准的视觉假设。
2. **Codex相机参数+BoxerNet**：沿用原Codex相机内参/朝向，每帧RGB与2D框输入Boxer，获得7DoF重力对齐框和model_score；无深度输入。该历史前端设置相机平移为零，使用自身相机原点局部系，不直接沿用方法1的桌面原点或尺度。
3. **GeoCalib+BoxerNet**：六帧GeoCalib共享内参和固定机位重力共识，其余逐帧Boxer及融合规则与方法2相同。它主要检验相机估计来源的影响，仍不解决单目真实尺度、系统性深度误差或支撑接触约束。

## 取舍与融合规则

先按同一静止名单构造逐帧Gs。不可见、无几何、非有限/非正尺寸/非法旋转、没有正重投影交集的帧不参与。原始实体仍保留；若无任何支持几何则显式unresolved，不新增框。本数据六组均有完整静止框覆盖。

每帧原始权重为：

`q = IoU × sqrt(visible_2D_area / max_visible_2D_area) × boundary_factor × (0.5 + 0.5*r)`

- IoU是3D框投影包络与同一冻结2D框的裁切后重叠；由于2D框也是Boxer输入，这是拟合诊断，不是独立准确率。
- 触及图像边界的boundary_factor=0.75，否则1；面积项降低严重遮挡、只露一小部分时的权重，属于固定机位假设下的启发式。
- Boxer的r为裁切到[0,1]的model_score。Codex的r为 `1/(1 + (norm(center_halfwidth)+norm(size_halfwidth))/norm(size) + orientation_error_deg/90)`。这些原生量没有统一概率标定，不能跨方法直接比较为正确率。
- 同一几何source_group的q除以其候选帧数，共享状态总量相当于平均证据，不因展开六帧而当成六次独立预测。
- 初始加权中心中位数和MAD确定中心残差，分量尺度为`max(1.4826*MAD, 0.15*典型框对角线)`；至少三候选帧时，残差范数>4.5的帧剔除。阈值仅是本轮可复现的稳健融合策略。
- 对留下的帧重新归一化权重；中心、尺寸用加权中位数。完整枚举24种合法等价长方体轴排列，按高权重参考框对齐朝向与尺寸，再用加权旋转矩阵SVD投影到SO(3)。保留任意倾斜，不将方法1强压为yaw-only。

每个Gs_global保存全部frame_evidence、选中/剔除帧及原因、最终权重、共享来源数、MAD和融合后逐可见帧投影诊断。相机保持原方法记录，不作为物体一起平均。

虚线limited的条件是融合框投影中位IoU<0.35，或中心MAD范数/融合框对角线>0.5；这些低支持框保留展示而不隐藏方法失败。实线supported_estimate也不是经过真值确认的可信几何。未进行跨shot配准、物理接触优化或真实几何精度评估。

## 实际结果

| 方法 | Shot | 静止框 | 低支持框 | 参与实体帧 | 中心离群帧剔除 | 逐实体投影中位数再取中位数 |
|---|---|---:|---:|---:|---:|---:|
| Codex直接3D | shot1 | 17 | 5 | 96 | 0 | 0.433 |
| Codex直接3D | shot3 | 21 | 5 | 125 | 0 | 0.549 |
| Codex相机+Boxer | shot1 | 17 | 3 | 91 | 5 | 0.571 |
| Codex相机+Boxer | shot3 | 21 | 3 | 122 | 3 | 0.516 |
| GeoCalib+Boxer | shot1 | 17 | 3 | 94 | 2 | 0.608 |
| GeoCalib+Boxer | shot3 | 21 | 2 | 123 | 2 | 0.637 |

不能仅根据这一投影指标给三维准确率排名，也不能因为共享Codex状态没有抖动就认定其更准确。页面用于观察三种构造结果及方法限制。

## 验证与复现

10项行为测试通过，涵盖加权中位数、中心离群点、24种框等价变换、共享状态不重复投票、任意倾斜、空几何及相机方向/投影。`audit.json`检查六组固定静止名单、每shot六帧Gs、来源哈希、权重归一化与共享来源数、中心中位数、SO(3)/角点、相机位置/方向和图形箭头、网页六图顺序及无外部脚本依赖，全部通过。浏览器交互未实测。

在已检查低负载的现有185272/node241以单CPU执行，无新allocation/GPU/model calls。入口：

- `EECBench/scripts/build_three_method_static_scenes.py`
- `EECBench/scripts/render_three_method_static_scenes.py`
- `EECBench/scripts/audit_three_method_static_scenes.py <run目录>`

各方法/shot子目录的`Gs_frames.json`保留逐帧图和取舍，`Gs_global.json`是最终融合图；`camera_visualization.json`记录渲染使用的相机箭头和视锥坐标。


## 最终Gs_global的重投影测量

[评测报告](reprojection_evaluation/README.md) · [原图叠加查看页](reprojection_evaluation/reprojection.html)。采用同一221个实体帧样本、实体/shot等权均值，GeoCalib+Boxer整体最优；测量的是输入2D框拟合，不是独立3D准确率。
