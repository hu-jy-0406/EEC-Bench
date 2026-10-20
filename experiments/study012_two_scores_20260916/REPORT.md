# Study0 / Study1 / Study2 双分数评测

范围：各自 Shot1–Shot3，三个case独立；原始JPEG不变。复用检测、独立聚类及GeoCalib重力，其他主要阶段新运行。

| Case | 实体分 | 实体覆盖率 | 空间分 | 空间覆盖率 |
|---|---:|---:|---:|---:|
| study0 | 100.00 | 88.89% | 100.00 | 0.00% |
| study1 | 94.44 | 94.44% | 100.00 | 0.00% |
| study2 | 88.24 | 76.47% | 98.18 | 1.82% |

Study0无确认冲突；Study1台灯缺失；Study2台灯缺失、纸巾新增，以及杯子—笔筒顺序冲突（cosine=-0.543759，Prompt规定的运动不能解释该变化）。

Study0/1各120对，负cosine=0；不增加非负值复核；按新规则，没有确认空间冲突即不扣分，空间分100。未知证据状态与覆盖率继续保留。Study2共55对、31负值，只有1对通过支撑、原图及Prompt复核；其他54对未知。其98.18是只扣确认冲突的上界，覆盖率仅1.82%。全局配准仍有局部误差，不能凭此次局部冲突检出宣称整体配准可靠。

## 实际用量

| Case | 墙钟/分钟 | 活跃去重/分钟 | 阶段累计/分钟 | 输入token | 输出token | 合计token |
|---|---:|---:|---:|---:|---:|---:|
| study0 | 18.74 | 12.99 | 18.05 | 467,753 | 22,540 | 490,293 |
| study1 | 18.74 | 13.83 | 19.00 | 479,949 | 23,877 | 503,826 |
| study2 | 20.76 | 14.99 | 22.91 | 788,417 | 33,068 | 821,485 |

墙钟：首个成功新阶段开始到最终空间结果生成，含调度与修复等待；活跃：成功阶段区间并集；累计：各阶段耗时之和（重叠并行阶段会累加）。三组并行，墙钟不能相加。以上不含复用阶段的历史成本；失败GPU尝试另存日志与result.json。token来自CLI实际usage，input+output，reasoning输出为output子集，不重复相加。

## 记录

- [实际执行设置](PLAN.md)、[汇总JSON](summary.json)、[汇总程序修复记录](AGGREGATION_FIX.md)。
- study0：[实际流程与分类](study0/REPORT.md)、[全部cosine表](study0/all_pairs.csv)、[逐调用token](study0/usage.json)、[结果与耗时](study0/result.json)、[共同坐标系框](study0/aligned_entities.json)。
- study1：[实际流程与分类](study1/REPORT.md)、[全部cosine表](study1/all_pairs.csv)、[逐调用token](study1/usage.json)、[结果与耗时](study1/result.json)、[共同坐标系框](study1/aligned_entities.json)。
- study2：[实际流程与分类](study2/REPORT.md)、[全部cosine表](study2/all_pairs.csv)、[逐调用token](study2/usage.json)、[结果与耗时](study2/result.json)、[共同坐标系框](study2/aligned_entities.json)。

规则更新：空间K=0记100，既涵盖无负cosine，也涵盖存在负cosine但没有确认冲突。仅重新汇总；本次新增模型调用/token均为0，表中保留原实验用量。规则变更前结果保存在 scoring_rule_no_conflict_100/。
