# Appearance budget v5

> 最新成本取舍：当前选用 [scoring v6](entity-appearance-scoring-v6.md)，模型阶段完全复用compact-v3，仅本地严重属性封顶和RMS汇总。v4核实机制与v5改写prompt候选不再作为默认。下文保留各版本历史说明。

用户明确要求 trade-off 成本、允许改评分规则、不要新增核实机制。本版恢复 compact v3 的短输出，只改评分措辞与本地数学；移除 v4 的证据门槛、属性状态数组、事件表、事件严重度/解释输出及对应语义检查。不增加第二遍检查、复核模型或调用次数。

## 固定规则

- 输入不变：每个冻结实体的全部 appearance crop、原生像素拼图、完整正常叙事和原来的 wire 元数据。独立 Codex gpt-6-astra / medium，每实体一次调用；DINO 单独报告并复用原分数。
- 原 v3 六字段 `u/s/e/why/limits/expected_changes`，保持四个属性分和短共享说明，不要求新字段。代码只保留 v3 的结构/索引/至少两个可用见证/fact-ID 校验，没有 v4 核实机制。
- 分档按整个实体受影响程度统一解释：100 可比部分无明确矛盾；90 轻微局部细节；75 清晰但局限于组件/区域的变化；25 主要辨识属性或主体表面的重大改变；0 广泛根本不一致；null 证据不足。90 替代旧50档不是历史分数数值映射，必须按新语义重新判断。
- 继续用简短措辞说明正常视角/遮挡/清晰度差异和 unknown，不让小特征改变自动变成主体级错误；不输出检查清单或变化事件。
- 实体分 `min(nonnull s)`，全部null时null。同一变化在多个属性重复反映不会累加处罚。不能假定四个评分是独立概率。
- Episode 主分 `100-sqrt(mean((100-C)^2))`，普通实体均分辅助；DINO均分不变。两种汇总均由本地代码计算，无模型token成本。保留未知属性数、可评分数量以及单shot/multi-shot实体子集；部分属性未知时100只代表可评估部分。

## 运行

在检查后的现有 Slurm allocation 内 CPU-only 执行，不申请新GPU。

```bash
python EECBench/scripts/gs_entity_appearance_budget.py prepare --source COMPACT_V3_OR_CANONICAL --out NEW_RUN
python EECBench/scripts/gs_entity_appearance_budget.py score --runs NEW_RUN --workers 3
python EECBench/scripts/gs_entity_appearance_budget.py report --runs NEW_RUN --out RESULTS_JSON
```

不需先运行旧VLM；canonical来源先完成appearance准备和DINO即可。旧v3/v4脚本、prompt及结果保持原样。报告/用量/比较在 `experiments/entity_appearance_budget_20260920/REPORT.md`。

## 成本与边界

Prompt 2277 bytes，低于v3的2528和v4的4619 bytes；这些是文本字节，不是模型token。字段集合与v3一致，实际模型token、缓存命中及输出/推理用量需以实测为准。减少字段不保证每次都降低计费；报告分别列input/cache/output与标准API等价成本。

相较v4牺牲逐事件可解释性、显式核实门槛和对应程序约束；不能声称误报控制完全等效。此轮Study2/3是开发样本，不能用分差证明人类一致性。模型设置、原始证据与调用次数固定，禁止为得到预期分数而重跑、拼接结果或改变公式。
