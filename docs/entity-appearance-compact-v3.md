# Appearance Codex 精简版 v3

> 最新成本取舍：当前选用 [scoring v6](entity-appearance-scoring-v6.md)，模型阶段完全复用compact-v3，仅本地严重属性封顶和RMS汇总。v4核实机制与v5改写prompt候选不再作为默认。下文保留各版本历史说明。

> 2026-09-20 后续修订：用户要求依据 Study2 误判审查优化评分，当前选用 `gs_entity_appearance_evidence.py`（[evidence v4](entity-appearance-evidence-v4.md)）。本页和 v3 入口保留为历史/回退；不再把四维均值视为当前默认 Codex 规则。

用户2026-09-20明确要求大幅降低 Codex 评分 token。当前 Codex 新入口为 `scripts/gs_entity_appearance_minimal.py`；原 `gs_entity_appearance.py` 继续负责 canonical appearance 准备与 DINO，并保留旧 Codex 路径作为 v1 对照。不改变已存在的 temporal_v2/presence/spatial 或 DINO 公式，不融合两个指标。

## 改动

1. 保留每个 global entity 的全部正检测关键帧 crop。按顺序排列在最多约1024边长的无损 PNG contact sheet 内，原 crop 像素逐点不变；较大原图允许超出这个排版目标，绝不缩小。每个 panel 标 A0、A1…，附 shot/frame/time 和目标框映射。通过 bitmap 回取检查所有 crop 像素、顺序和覆盖。
2. 不再逐 appearance 重发整个场景原图。原图、原始框、候选归属、路径、hash 与置信度保留在本地 canonical input，模型只收目标 crop、帧映射、实体名与完整正常剧情事实。减少整帧上下文属于证据范围变化，不是对 v1 全输入的无损编码；缺乏上下文必须报告 unknown，不能脑补。
3. 简短任务 prompt 保留通用物体多视角逻辑、真实部位/表面对齐、遮挡/光照/合理形变、不同表面天然不同、未知不能计100、禁止按名字过滤改变、集合实际范围、全帧/少数异常复核及原四维评分锚点。
4. 输出改为 `u`（全部panel可用性0/1/2）、`s`（原四维顺序分数）、`e`（四维证据编号列表）、一段`why`、短`limits`和明确授权变化的fact IDs。删除逐帧解释与四套重复长说明；程序验证编号/可用性，计算原非null维度均值。Canonical展开中的共享说明来自同一简短文本，不伪称模型独立解释了每一维。
5. 仅本次 CLI 调用以 `model_instructions_file` 指向 `prompts/appearance/evaluator_base_v1.txt`，将通用编码代理说明替换为简短视觉评估角色。Astra/medium、configured provider/auth、只读sandbox、禁用工具和独立上下文保持。没有改动用户配置或其他pipeline的基础说明。

官方配置依据：https://learn.chatgpt.com/docs/config-file/config-sample （model_instructions_file）。执行额外参数与文件hash保存在每次调用的 execution_override.json；request.json 是加override前的公共transport记录，execution_override中的actual_command才是实际命令。

## 新数据使用

无需先运行昂贵的旧 Codex：

```
python EECBench/scripts/gs_entity_appearance.py prepare --case CASE --out CANONICAL
# 在既有空闲GPU、经guard验证后执行DINO：
python EECBench/scripts/gs_entity_appearance.py dino --runs CANONICAL
# 以下仅CPU/API：
python EECBench/scripts/gs_entity_appearance_minimal.py prepare --source CANONICAL --out COMPACT
python EECBench/scripts/gs_entity_appearance_minimal.py score --runs COMPACT --workers 3
python EECBench/scripts/summarize_entity_appearance_compact.py --runs COMPACT
```

这些命令在适当的现有Slurm分配内执行。`score`保留成功结果以支持断点继续，不重复已成功调用；失败不会悄悄改成0。`summarize_entity_appearance_compact.py`不依赖旧Codex结果；只有benchmark `minimal.py report`需要旧Codex作比较。

DINO scores逐字复用，单帧实体仍null。每实体一次调用；全部appearance和独立身份范围不变。仍输出独立Codex/DINO逐实体与全部/跨shot/单shot均分及用量/标准API等价USD。此前 v1 的 canonical source/hash 保持原样。

## 验证和限制

两级对照分别保存：`experiments/entity_appearance_compact_20260920` 是拼图+简短I/O、原编码基础说明；`experiments/entity_appearance_minimal_20260920` 再加简短视觉角色。每一级均保留独立原始模型结果，不按更高/更低分挑结果拼接。预筛调用在同一版本全量时复用，不重复消费。

关键判断是否保留和精确分数是否相同分别报告。不同版本分数有变化，不能把bitmap无损等同于模型质量完全不变；移除场景上下文、拼图模型内部缩放/注意力以及模型自身波动都可能影响结果。DINO不受这一压缩影响。细节/形状争议和植物/花盆范围重叠仍需要人工校准；没有用已知答案修改评分规则、下调模型或降低reasoning。
