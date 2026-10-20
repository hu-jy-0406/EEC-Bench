# Study2 检测候选聚类版：全新前端与前版对照

两组均使用同12张原始JPEG，模型gpt-6-astra / medium。基准为study2_anchor_joint_fresh_20260918的前端；新运行从WeDetect开始，检测、聚类、GeoCalib、Pi3X、Boxer和独立动静判断均重新推理。仅复用原始输入、代码/环境、预训练权重与下载元数据。

## 结果

| Shot | 旧实体/静态/运动/未知 | 新实体/静态/运动/未知 | 候选成员完全相同的聚类 | 旧非空框 | 新非空框 |
|---|---|---|---:|---:|---:|
| shot1 | 19/17/2/0 | 21/19/2/0 | 19 | 102 | 99 |
| shot3 | 22/21/1/0 | 22/21/1/0 | 22 | 130 | 129 |

WeDetect的12帧候选数量、标签和坐标均与基准一致（置信分数允许微小数值差异）。原有41个实体的候选归属集合与动静标签全部一致；Shot1额外保留书架上层和下层两个书组，均为static。它们的候选在旧聚类中被剔除，属于候选保留口径差异，而非检测新增或框恢复。
Shot1非空框从102变为99，是删除15个恢复框、同时新增两个书组的12个原始检测观测的净结果。Shot3从130变为129，对应删除一处花盆恢复框。所有228个非空框均逐值等于原始候选坐标。
Shot1黑色笔、小木桌、桌上植物虽各仅保留一个检测帧，动静模型仍结合其他原图中的可辨部分判静止；这些视觉观察未被写回为补框。

## 实际阶段耗时与tokens

| 环节 | 旧秒 | 新秒 | 旧tokens | 新tokens |
|---|---:|---:|---:|---:|
| WeDetect-Anything | 31.30 | 32.68 | 0 | 0 |
| Codex 独立聚类 | 178.53 | 43.80 | 53,289 | 44,492 |
| GeoCalib | 42.18 | 78.04 | 0 | 0 |
| Pi3X Shot1 | 51.83 | 56.64 | 0 | 0 |
| Boxer Shot1 | 15.14 | 22.05 | 0 | 0 |
| Pi3X Shot3 | 25.13 | 32.19 | 0 | 0 |
| Boxer Shot3 | 13.56 | 20.38 | 0 | 0 |
| Codex 独立动静判断＋静态图融合 | 159.19 | 157.22 | 81,783 | 84,128 |
| 前端总计（含新运行排错等待） | 517.18 | 639.55 | 135,072 | 128,620 |

Token减少4.78%；端到端墙钟变化+23.66%。旧input/output=114603/20469，新input/output=116188/12432。缓存input已含在input内：旧0、新0；reasoning子项不重复加总。
两shot聚类并行、两shot动静判断并行，阶段耗时按墙钟计一次，token按调用求和。GPU阶段含安全检查、加载与推理；总墙钟还包含阶段交接和输入整理。仅比较相同前端范围，不含跨shot身份、配准或一致性评分，也不含本次准备/报告耗时。一次运行的耗时包含服务及机器负载波动，不是稳定加速比。

## 每次Codex调用

| 调用 | 秒 | input | output | total |
|---|---:|---:|---:|---:|
| clustering shot1 | 43.79 | 20,313 | 1,262 | 21,575 |
| motion shot1 | 155.02 | 34,648 | 4,957 | 39,605 |
| clustering shot3 | 43.79 | 21,708 | 1,209 | 22,917 |
| motion shot3 | 156.59 | 39,519 | 5,004 | 44,523 |

## 执行中断记录

GeoCalib首次启动缺少预训练权重链接，在模型推理前退出；失败耗时27.20s。修复及重新调度等待196.37s。成功阶段累计415.93s。全部保留在端到端总时间中；阶段表GeoCalib包含失败与成功两次启动。未重复检测或已完成Codex调用，未复用上次实验的推理结果。

## 实体聚类与动静标签逐项对照

用同帧原始候选ID集合建立新旧对应，而非假设实体ID或名称保持不变。exact=false的项目需看候选归属改变，不能直接按名称认定同一聚类。

| Shot | 旧实体 | 新实体 | 候选集合完全相同 | 旧标签 | 新标签 | 旧观测帧 | 新观测帧 |
|---|---|---|---|---|---|---|
| shot1 | e1 Framed landscape painting on wall | e1 Framed landscape painting on wall | True | static | static | [0, 24, 48, 72, 120] | [0, 24, 48, 72, 120] |
| shot1 | e2 Dark green mug | e2 Dark green mug | True | static | static | [0, 24, 48, 72, 120] | [0, 24, 48, 72, 120] |
| shot1 | e3 Black desk lamp | e3 Black desk lamp | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 48, 72, 96, 120] |
| shot1 | e4 Woman wearing gray sweater and dark trousers | e4 Woman wearing a gray sweater and dark trousers | True | moving | moving | [0, 24, 48, 72, 96] | [0, 24, 48, 72, 96] |
| shot1 | e5 Large wooden desk | e5 Large wooden desk | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 48, 72, 96, 120] |
| shot1 | e6 Small framed picture on bookcase | e6 Small framed picture on bookcase | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 48, 72, 96, 120] |
| shot1 | e7 Light-colored pencil cup | e7 Light-colored pencil holder | True | static | static | [0, 24, 48, 72, 120] | [0, 24, 48, 72, 120] |
| shot1 | None None | e8 Row of books on lower bookshelf | False | None | static | None | [0, 24, 48, 72, 96, 120] |
| shot1 | e8 Trailing plant by window | e9 Trailing plant on windowsill | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 48, 72, 96, 120] |
| shot1 | e9 Dark green bookcase with lower cabinet | e10 Dark bookcase with lower cabinet | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 48, 72, 120] |
| shot1 | e10 Trailing plant on bookcase shelf | e11 Trailing plant on bookshelf | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 48, 72, 96, 120] |
| shot1 | e11 Patterned rug beneath desk | e12 Patterned rug beneath desk | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 48, 72, 96, 120] |
| shot1 | e12 Red hardcover book | e13 Red hardcover book carried by woman | True | moving | moving | [0, 24, 48, 72, 96] | [0, 24, 48, 72] |
| shot1 | e13 Wooden slat-back chair | e14 Wooden slat-back chair | True | static | static | [0, 24, 48, 96, 120] | [0, 24, 48, 96, 120] |
| shot1 | e14 Radiator below window | e15 Radiator beneath window | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 48, 96, 120] |
| shot1 | None None | e16 Books on top bookshelf | False | None | static | None | [0, 24, 48, 72, 96, 120] |
| shot1 | e15 Terracotta pot on windowsill | e17 Terracotta plant pot on windowsill | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 48, 72, 96, 120] |
| shot1 | e16 Small pale vessel on bookcase shelf | e18 Small light-colored pot on bookshelf | True | static | static | [0, 24, 48, 72, 96, 120] | [24, 48, 72] |
| shot1 | e17 Black writing instrument in pencil cup | e19 Black pen in pencil holder | True | static | static | [0, 24, 48, 72, 120] | [72] |
| shot1 | e18 Small wooden side table against wall | e20 Small wooden side table | True | static | static | [0, 24, 72, 96, 120] | [120] |
| shot1 | e19 Trailing plant on small side table | e21 Trailing plant on side table | True | static | static | [96, 120] | [120] |
| shot3 | e1 Framed landscape painting | e1 Framed landscape painting | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 48, 72, 96, 120] |
| shot3 | e2 Dark green mug | e2 Dark green mug | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 48, 72, 96, 120] |
| shot3 | e3 Larger framed picture in hallway | e3 Larger framed picture in hallway | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 48, 72, 96, 120] |
| shot3 | e4 Framed botanical print beside window | e4 Framed botanical print beside window | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 48, 72, 96, 120] |
| shot3 | e5 Small narrow framed hallway picture | e5 Narrow framed picture in hallway | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 48, 72, 96, 120] |
| shot3 | e6 Wooden dining chair | e6 Wooden dining chair | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 48, 72, 96, 120] |
| shot3 | e7 Large wooden dining table | e7 Large wooden dining table | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 48, 72, 96, 120] |
| shot3 | e8 Small wooden console table | e8 Wooden console table against back wall | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 48, 72, 96, 120] |
| shot3 | e9 White pencil cup | e9 White pencil cup | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 48, 72, 96, 120] |
| shot3 | e10 Trailing plant on windowsill | e10 Trailing plant on windowsill | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 48, 72, 96, 120] |
| shot3 | e11 Trailing plant on console table | e11 Trailing plant on console table | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 48, 72, 96, 120] |
| shot3 | e12 Small dark hallway cabinet | e12 Small dark wooden hallway cabinet | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 48, 72, 96, 120] |
| shot3 | e13 Plant at far left edge | e13 Partially visible plant at left edge | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 48, 72, 96, 120] |
| shot3 | e14 Tissue packet with protruding tissue | e14 Tissue packet with protruding tissue | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 48, 72, 96, 120] |
| shot3 | e15 Large patterned rug beneath dining table | e15 Patterned rug beneath dining table | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 48, 72, 96, 120] |
| shot3 | e16 Stack of books on console | e16 Stack of books on console table | True | static | static | [0, 24, 72, 96, 120] | [0, 24, 72, 96, 120] |
| shot3 | e17 Plant pot on windowsill | e17 Plant pot on windowsill | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 48, 72, 96, 120] |
| shot3 | e18 White radiator below window | e18 White radiator beneath window | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 48, 72, 96, 120] |
| shot3 | e19 Writing utensils in pencil cup | e19 Writing utensils in pencil cup | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 48, 72, 96, 120] |
| shot3 | e20 Hallway runner rug | e20 Patterned hallway rug | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 48, 72, 96, 120] |
| shot3 | e21 Plant pot on console table | e21 Plant pot on console table | True | static | static | [0, 24, 48, 72, 96, 120] | [0, 24, 72, 96, 120] |
| shot3 | e22 Woman wearing gray sweater and dark trousers | e22 Woman in gray sweater and dark trousers | True | moving | moving | [24, 48, 72, 96, 120] | [24, 48, 72, 96, 120] |

## 执行规则与验证

- WeDetect检测全部12帧；每shot使用独立的新Codex上下文，输入只包含该shot原帧及候选。
- Codex只输出entity_id/name/candidate_ids与剔除候选；不生成逐帧框或exist/visible。
- 程序按最高置信度选择同帧原候选框，分数相同按candidate_id排序；保留所有来源。无候选不补框，exist为未知，visible表示是否有保留检测观测。
- GeoCalib + 单shot Pi3X + 深度条件Boxer全部重跑；逐帧几何进入各自隔离的动静判断，静态实体再融合。
- 已验证每个最终非空2D框逐值等于其选中的原始候选；空框没有跨帧补齐。
- 已验证原始JPEG哈希、旧产物哈希、代码快照、4次调用模型和推理模式、上下文隔离及token对账。
- 此次未运行跨shot评分；动静判断差异与几何、证据帧变化应一起评估，不能由省token直接推断准确率提升。
