# Study0 / Study1：当前 pipeline 完整新评测

版本 `gs-consistency-two-scores-v1`，Flow1，运行配置 `safe_spatial_medium`，所有模型调用均为 GPT-6 Astra / medium。每组仅比较 Shot1–Shot3；Shot2 情节保留在正常 narrative 中，本轮没有计算 Shot2。

每组使用 12 张原始 JPEG：Study0 852×480，Study1 854×480。没有重新保存、缩放图片，也没有复用旧检测、聚类、几何、配准或模型判断。两组单独运行、单 shot 判断相互隔离。

| Case | 静止实体一致性 | 空间关系一致性 | 墙钟秒数 | Codex tokens | 调用次数 |
|---|---:|---:|---:|---:|---:|
| study0 | 100.00 | 100.00 | 880.81 | 319,720 | 7 |
| study1 | 94.44 | 100.00 | 880.86 | 326,860 | 7 |

时间为各 case 从 WeDetect 到最终分数的实际墙钟，包含流水线内部等待；不包含排队、任务准备、报告审计和本次主对话。Token 仅统计 pipeline 调用，缓存输入是输入的子集，没有重复计数。RoMa 与动静/初始身份步骤有重叠，各阶段用时之和不等于总墙钟。

## 各阶段耗时与 token

| 阶段 | Study0 秒 | Study0 tokens | Study1 秒 | Study1 tokens |
|---|---:|---:|---:|---:|
| WeDetect＋实体聚类 | 58.48 | 31,013 | 55.75 | 31,128 |
| GeoCalib | 40.49 | 0 | 39.61 | 0 |
| 几何输入整理 | 0.32 | 0 | 0.34 | 0 |
| Pi3X Shot1 | 48.86 | 0 | 41.51 | 0 |
| Boxer Shot1 | 14.13 | 0 | 13.15 | 0 |
| Pi3X Shot3 | 23.11 | 0 | 22.59 | 0 |
| Boxer Shot3 | 12.30 | 0 | 12.74 | 0 |
| 独立动静划分＋融合 | 144.60 | 75,475 | 157.84 | 77,539 |
| 初始身份对应 A＋A′ | 82.38 | 58,155 | 81.63 | 59,611 |
| RoMa 多帧匹配 | 130.12 | 0 | 129.21 | 0 |
| 对应点筛选与提升 | 5.32 | 0 | 5.74 | 0 |
| 场景配准 | 14.42 | 0 | 16.43 | 0 |
| 配准后身份复核 | 252.88 | 60,269 | 244.19 | 61,336 |
| 单次 B 分类 | 183.08 | 94,808 | 188.93 | 97,246 |
| 空间关系评测 | 0.43 | 0 | 0.42 | 0 |

## study0：实际结果

实体/动静数量：`{"shot1": {"static": 16, "moving": 2, "unknown": 0, "entities": 18}, "shot3": {"static": 17, "moving": 1, "unknown": 0, "entities": 18}}`。

存在性计数：`{"score": 100.0, "coverage": 0.8235294117647058, "N": 17, "C": 14, "K": 0, "U": 3, "E": 0, "identification_interval": [82.3529411764706, 100.0]}`。

确认的存在性冲突：

- 无。

保留为未知、不扣分的组：

- g12：保留scope_mismatch：材料均可见，但不能确认冻结对象组成严格相同；不判缺失或新增。
- g16：保留scope_mismatch；像素未显示椅毯消失，但冻结实例范围无法严格对应，不依据盒差判冲突。
- g17：单侧库存是缺项，原图直接反驳实物新增或缺失；没有视角或运动导致该差异的证据，保持unknown、cause none。

空间共同实体 14 个，全部无序实体对 91 对，负 cosine 0，通过局部支撑筛选 0，最终确认冲突 0 对。

输入 293,273；输出 26,447；其中缓存输入 0。

[完整身份/存在性判断](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/study01_safe_spatial_fresh_20260919/study0/presence.json) · [全部空间关系](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/study01_safe_spatial_fresh_20260919/study0/all_pairs.csv) · [逐调用时间和 token](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/study01_safe_spatial_fresh_20260919/study0/calls.csv) · [审计](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/study01_safe_spatial_fresh_20260919/study0/audit.json)

## study1：实际结果

实体/动静数量：`{"shot1": {"static": 18, "moving": 2, "unknown": 0, "entities": 20}, "shot3": {"static": 17, "moving": 1, "unknown": 0, "entities": 18}}`。

存在性计数：`{"score": 94.44444444444444, "coverage": 0.8888888888888888, "N": 18, "C": 15, "K": 1, "U": 2, "E": 0, "identification_interval": [83.33333333333333, 94.44444444444444]}`。

确认的存在性冲突：

- g02 / unexplained_missing：按桌沿、杯和墙面对应原灯位，冻结投影中心约为[626,180]，位于空区内。两侧各两帧原像素确认有灯与无灯，排除出画、遮挡及漏检；红本搬运动作不能解释台灯缺失。

保留为未知、不扣分的组：

- g13：保持冻结身份未定标签；两侧有白纸本不等于已确认同一本或同一叠，不能判缺失、增加或配对兼容。
- g16：保持scope_mismatch：虽可见对应绿椅及垂毯，冻结整体范围不一致，无法按同一评分实体确认；不拆分成单侧对象。

空间共同实体 15 个，全部无序实体对 105 对，负 cosine 0，通过局部支撑筛选 0，最终确认冲突 0 对。

输入 299,879；输出 26,981；其中缓存输入 14,848。

[完整身份/存在性判断](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/study01_safe_spatial_fresh_20260919/study1/presence.json) · [全部空间关系](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/study01_safe_spatial_fresh_20260919/study1/all_pairs.csv) · [逐调用时间和 token](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/study01_safe_spatial_fresh_20260919/study1/calls.csv) · [审计](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/study01_safe_spatial_fresh_20260919/study1/audit.json)

## 审计与限制

两组均通过原图哈希、原始检测框及候选完整覆盖、源代码哈希、全部无序对与 cosine 独立重算、单次 B、Astra medium 和独立临时上下文检查。

身份复核提示词将原先写死的 852×480 改为读取每帧 image_size；原图和评分规则未改动。

首次作业 200015 在模型启动前因 Slurm 全局 GPU 编号与 cgroup 内可见编号不同退出；零模型调用。修复启动编号解析后使用作业 200016；每次 GPU 推理均保留原 idle/VRAM/KFD/UUID 检查。

100 分表示本流程没有确认需要扣分的冲突，不表示所有实体和空间关系都经过肯定一致的确认。此处是两个测例各一次新运行，不能据此保证其他场景或重复运行完全相同。
