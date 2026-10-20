# 最简身份输入：Study2/3/4 完整下游验证

结论：三组冻结上游上的最简身份输入均保留确认身份、锚点、存在性/空间关系逐实体判定及原始位移比例。Study2/3直接完成；Study4原始prompt绑定连续两次格式校验失败，在实验输出schema中明确既有约束后完成。不能称为原生产流程三组一次全部无问题。

本次只更改身份复核请求的输入范围。生产默认未切换。检测、原始图像、三维重建、whole-shot motion、配准和片内复核均复用冻结基线；跨镜头复核、外观Codex、prompt绑定与alignment新调用；全部位移重新汇总并保存原始r_e。DINO使用同一权重/处理器在已分配节点CPU重新计算，未占用GPU。

## 结果

| Study | 身份分组 | 存在性 旧→新 | 空间关系 旧→新 | 位移 片内/跨shot/全部 | 外观Codex |
|---|---|---|---|---|---|
| study2 | 一致 | 83.33 → 83.33 | 97.22 → 97.22 | 60.68 / 63.23 / 61.11 | 92.26 |
| study3 | 一致 | 92.31 → 92.31 | 97.78 → 97.78 | 62.80 / 67.15 / 63.58 | 85.78 |
| study4 | 一致 | 100.00 → 100.00 | 100.00 → 100.00 | 54.56 / 80.09 / 55.69 | 97.12 |

三组空间冲突数分别为1/36、1/45、0/3。Study4沿用原冻结集合粒度，只有3个空间实体对；不能据此宣称所有茶杯交换都得到评估。片内空间结果复用，均100，不是此次重新模型验证。存在性未知记录继续保留，不能将100解释为全部证据充分。

## 细项差异与归因

- 三组确认身份、anchor资格/选择/参考均保持；实体对应的存在性与空间最终状态保持。Study3一个不确定组的标识符变化，不改变成员和unknown状态。所有有效跨shot原始r_e、距离和实体位移分数保持。
- Study3外观总分85.7756006保持，但4个实体各有1个属性分变化，所有实体最终分仍保持；未知属性数量26→25；原始crop像素和所属实体/帧逐项核验。DINO CPU/GPU有浮点级差异，未声称逐位相同。
- Study3 prompt空间分78.5714286→80.9523810，唯一原子状态变化为shot1_lamp_on_desk：unknown→satisfied。该Shot1模型输入与旧版逐值完全相同，属于观察到的重复调用波动。
- Study3绑定中书堆ge0035从unbound→unknown(candidate notebook)。绑定模型输入与旧版完全相同；未改变冻结视觉身份，相关未知信息传入后续prompt判断。其余三个prompt维度分数保持。
- Study2/4原冻结基线没有这套完整prompt参照，因此本次由各自保存的情节文本编译54/161条要求，作为首次测试，不能报告与历史完整prompt分数等价，也不宜按不同要求集合直接比较Study间分数。Study4保留原文明确授权的杯子换位/内容变化。

## Prompt分项

| Study | Presence | Appearance | Spatial | Motion | 要求数 |
|---|---:|---:|---:|---:|---:|
| study2 | 100.00 | 100.00 | 100.00 | 100.00 | 54 |
| study3 | 100.00 | 92.86 | 80.95 | 100.00 | 79 |
| study4 | 100.00 | 100.00 | 94.74 | 100.00 | 161 |

各维度T/F/U、分层汇总和全部见证见comparison.json与各alignment/results.json；unknown不是已证实一致。Study2/4自动文本编译通过结构、引句和范围检查，但不是独立人工标注的完备性证明。

## Study4恢复记录

1. 初始文本schedule遗漏Shot2开头可见的花园门；在不使用视频判定的情况下，按原文另存修正版，增加4条相关要求，原编译输入/输出保留。
2. 初版和修正版的两次普通绑定调用均给unknown记录填写fact_ids，违反现有materialize要求。均真实失败，原响应/日志/费用保留；没有清空字段后伪装原模型通过。
3. strict_binding.py仅在实验调用的JSON schema中编码原有bound/unbound/unknown字段约束。原prompt和materialize不变，新调用通过原校验，再完整运行修正版alignment。不是额外身份复核或评分门槛调整；生产schema未修改。
4. Study4成功的边界复核、DINO和appearance调用不重复。补做因调度中止而未执行的本地位移/外观报告。初始pipeline_runtime仍保留failed，最终完成状态是有记录的checkpoint恢复。

## 时间和API用量

| Study | 首轮下游执行秒（不含编译） | 从并行启动至最终完成秒 | 本次全部tokens | 标准API等价USD |
|---|---:|---:|---:|---:|
| study2 | 367.69 | 531.45 | 880,837 | 9.775994 |
| study3 | 422.26 | 422.89 | 755,334 | 8.717356 |
| study4 | 315.15 | 1228.69 | 693,997 | 8.508154 |

三组实际并行从启动至最后成功输出：1228.69秒（20.48分钟），含首次参照编译与Study4修正/失败恢复；不含前置代码准备、资源检查和最终报告审计。所有134次API请求共2,330,168tokens，USD27.001504标准API等价估算。

费用按记录的Astra标准价：每百万未缓存输入USD10、缓存输入USD1、输出USD50，缓存为输入子集；长上下文按既有计价函数。不是实际账单，不含父对话/历史实验，集群费用未知。usage.json保留每次用量、缓存、编译和失败恢复费用。上述验证总额不是采用最简输入后每集正常运行的成本。

## 产物与边界

- runs/study{2,3,4}/comparison.json：全部细项差异；displacement/results.json与entities.csv保存未取整原始r_e。
- Study2/3完整结果：runs/study*/summary.json、appearance/report/results.json、prompt_alignment/results.json。
- Study4采用的prompt结果：study4_prompt_recovery_v2/{binding,alignment}/results.json；外观与空间仍位于runs/study4。
- frozen_upstream.json、source_snapshot、原始请求/响应、各调用status、参考编译和schema审计完整保留。
- 这是三例冻结前端的下游验证，没有重新运行检测/几何，没有独立人工正确性或新episode泛化验证。没有据分数择优挑选模型判定。

## 费用拆分

| 范围 | 请求数 | Tokens | API等价USD |
|---|---:|---:|---:|
| 其余新评分调用 | 124 | 1,966,506 | 21.659380 |
| 两次被拒绝的绑定 | 2 | 61,699 | 0.846830 |
| 参照编译 | 2 | 43,453 | 1.220690 |
| 格式约束修复后的绑定与alignment | 6 | 258,510 | 3.274604 |

总输入2,202,882（其中缓存输入154,624），输出127,286。缓存输入未重复加到总tokens。

## 各环节实测时间

并行环节的耗时不能相加解释为总墙钟时间。片内评分复用，不计新调用。Study4的首次调度因绑定错误提前结束，未开始的本地报告在恢复步骤完成。

| Study | 环节 | 秒 | 新tokens | API等价USD |
|---|---|---:|---:|---:|
| study2 | pair_000_identity_review (success) | 159.63 | 34,193 | 0.544290 |
| study2 | pair_000_boundary (success) | 196.66 | 292,108 | 3.278560 |
| study2 | global_entity_table (success) | 0.08 | 0 | 0.000000 |
| study2 | prompt_binding (success) | 99.59 | 31,686 | 0.437860 |
| study2 | appearance_prepare (success) | 5.69 | 0 | 0.000000 |
| study2 | appearance_dino (success) | 127.21 | 0 | 0.000000 |
| study2 | appearance_compact (success) | 4.41 | 0 | 0.000000 |
| study2 | appearance_codex (success) | 194.97 | 217,678 | 2.116660 |
| study2 | prompt_alignment (success) | 106.92 | 289,678 | 3.037444 |
| study2 | entity_displacement (success) | 0.10 | 0 | 0.000000 |
| study2 | appearance_report (success) | 2.76 | 0 | 0.000000 |
| study2 | prompt_binding_report (success) | 0.08 | 0 | 0.000000 |
| study3 | pair_000_identity_review (success) | 164.49 | 34,421 | 0.550370 |
| study3 | pair_000_boundary (success) | 186.91 | 290,831 | 3.258390 |
| study3 | global_entity_table (success) | 0.08 | 0 | 0.000000 |
| study3 | prompt_binding (success) | 99.94 | 32,307 | 0.445230 |
| study3 | appearance_prepare (success) | 5.86 | 0 | 0.000000 |
| study3 | appearance_dino (success) | 124.92 | 0 | 0.000000 |
| study3 | appearance_compact (success) | 4.13 | 0 | 0.000000 |
| study3 | appearance_codex (success) | 191.85 | 223,710 | 2.398836 |
| study3 | prompt_alignment (success) | 157.72 | 174,065 | 2.064530 |
| study3 | entity_displacement (success) | 0.10 | 0 | 0.000000 |
| study3 | appearance_report (success) | 3.24 | 0 | 0.000000 |
| study3 | prompt_binding_report (success) | 0.09 | 0 | 0.000000 |
| study4 | pair_000_identity_review (success) | 132.71 | 31,084 | 0.473920 |
| study4 | pair_000_boundary (success) | 146.02 | 80,392 | 0.986960 |
| study4 | global_entity_table (success) | 0.08 | 0 | 0.000000 |
| study4 | prompt_binding (failed) | 93.32 | 30,762 | 0.418980 |
| study4 | appearance_prepare (success) | 4.59 | 0 | 0.000000 |
| study4 | appearance_dino (success) | 96.79 | 0 | 0.000000 |
| study4 | appearance_compact (success) | 3.73 | 0 | 0.000000 |
| study4 | appearance_codex (success) | 174.04 | 234,353 | 2.066330 |
| study4 | recovery_binding | 87.96 | 30,898 | 0.414100 |
| study4 | recovery_alignment | 285.47 | 227,612 | 2.860504 |
| study4 | recovery_binding_report | 0.09 | 0 | 0.000000 |
