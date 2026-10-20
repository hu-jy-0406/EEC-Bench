# Appearance evidence v4

> 最新成本取舍：当前选用 [scoring v6](entity-appearance-scoring-v6.md)，模型阶段完全复用compact-v3，仅本地严重属性封顶和RMS汇总。v4核实机制与v5改写prompt候选不再作为默认。下文保留各版本历史说明。

2026-09-20 用户要求根据 Study2 扣分审查优化机制。本版替代“属性平均”；不采用机械最低属性分。独立入口 `scripts/gs_entity_appearance_evidence.py`，不修改历史 v1/v3 runner、输入或分数。验证结果见 `experiments/entity_appearance_evidence_20260920/REPORT.md`。

## 判定与评分

- 每个实体全部已有 appearance crop 同一次独立 Codex 调用，gpt-6-astra / medium、原图像 transport、完整正常叙事、原冻结身份与范围保留。VLM 不接收历史分数、Study2/3 预期标签或 DINO。
- 四个属性改成 consistent / changed / unknown。consistent 必须有足够可比证据；多 shot 实体不能仅凭各 shot 内稳定推断跨 shot 一致。全部 unknown 返回 null；部分 unknown 明示其数量和局限，分数仅针对可评估部分。
- 每个独立变化事件记录两组原始 appearance 见证、对应部位和四个门槛：物理对应成立、该变化的可见性/分辨率充分、有依据的视角/光照/遮挡/模糊解释已排除、变化属于实体自身范围。四项都通过才允许 confirmed 和严重度；否则保留 uncertain，相关属性不得被冒充为 consistent。门槛的语义正确性仍由 VLM 判断，代码只能验证结构与逻辑，不能证明视觉判断正确。
- bbox/像素宽高比不是固有比例变化证据；没有物理枝叶对应不能断言同一枝叶改变；模糊造成纹理消失不是材质变化；植物和独立花盆等不得跨范围重复扣分。明显变化也不能靠想象光照或视角解释豁免。
- 严重度以整个实体为尺度：1 轻微局部细节（扣10），2 清晰但局限于组件/区域的变化（扣25），3 主要辨识属性或主体表面重大改变（扣75），4 整体广泛不相容（扣100）。区域大小和语义重要性共同判断，不用固定像素比例；置信度不能混进严重度。
- 同一个变化跨多属性、多个关键帧只记一个事件。实体分 `C=100-max(confirmed_event_penalties)`；没有 confirmed 且至少一维可评估则100，否则null。max 同时避免重复事件叠加，但会舍弃多个独立小错误的累积影响；它刻画最严重已确认外观问题，不是所有错误总量。
- Episode Codex 主分 `100-sqrt(mean((100-C)^2))`，有效实体等权；同时保存实体算术均分、可评估实体数、未知属性数、存疑事件和单/multi-shot实体子集。multi-shot 子集仍是这些实体的全部 appearance，不是纯跨镜头 pair 分数。部分可评估100不表示全部属性已证实一致。
- DINO 原分数和公式逐字复用，继续单独报告，不融合。不改变 presence/spatial/motion/registration。

## 使用

在已检查的现有 Slurm allocation 内 CPU-only 执行；不需要新 GPU。

```bash
python EECBench/scripts/gs_entity_appearance_evidence.py prepare --source COMPACT_V3_OR_CANONICAL --out NEW_RUN
python EECBench/scripts/gs_entity_appearance_evidence.py score --runs NEW_RUN --workers 3
python EECBench/scripts/gs_entity_appearance_evidence.py report --runs NEW_RUN --out RESULTS_JSON
```

source 可为已有 compact v3（复用原生像素拼图）或完成 prepare/DINO 的 canonical 数据（重新无损排版）；均不要求先运行旧 VLM。输出独立目录，失败不自动重试或静默计零，保留原始响应、请求、模型设置、用量与标准 API 等价成本。旧 v3 仍可独立回退。

## 依据与验证边界

借鉴 EntityBench 分属性可审计判断、VIEScore 严重缺陷不能被其他高分抵消、VideoScore 明确严重程度与人工校准原则。事件分档和 RMS 缺陷聚合是本项目规则，不是这些论文的原公式。此轮设计受 Study2/3 观察启发，同样本复测属于开发集诊断，不能作为独立泛化或人类一致性验证；不以达到预定分差、Study2 必须100或某实体必须扣分作为通过标准。不调参追求结果，不删除真实附带生成漂移。仍需独立人工标注样本验证误报/漏报、多视角鲁棒性与严重度排序。

## 本轮完成结果

本版已作为后续独立 appearance 评分入口选用，旧 v3 保留回退。Study2/3 新主分95.7125/86.2380，普通实体均分99.2647/96.9697；DINO0.910026/0.911623不变。Study2只确认人物裤装局部变化；Study3额外确认台灯主体黑→乳白色，实体25。20项测试、71实体/474appearances完整审计通过。67新调用461305tokens，标准API等价$4.413690；比精简v3的429878tokens增加约7.3%，仍为每实体一次调用。没有独立人工校准。三份响应的冗余证据引用展开问题已统一本地修复，未重跑模型；详见报告。
