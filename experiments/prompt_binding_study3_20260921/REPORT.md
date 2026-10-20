# Study3 Prompt-bound / Prompt-unbound 实体划分

2026-09-21，新增环节已实现并完成 Study3 冻结上游测试。主流程传入 `--prompt-registry` 后，在最终跨镜头身份审核及 `global_entities` 导出之后做对应，完整流程追加分类外观报告。没有提供 registry 时明确不运行分类，不把所有实体默认为 unbound。

## 输入与结果

当前 Study3 评测输入未提供 registry/schedule；依据其 **正常评测情节** 手工生成并冻结 [prompt_registry.json](prompt_registry.json)，不把异常注入生成指令作为输入。清单在读取此次视觉实体表之前写入。它是本次回溯测试的情节推导 fixture，不宣称是视频生成前预注册的 EntityBench 原始标注。

| Prompt 实体 | 要求出现的镜头 | 对应视觉记录 |
|---|---|---|
| pe01 女子 | Shot1/2/3 | ge0004（Shot1/3）、ge0021（Shot2） |
| pe02 红色笔记本 | Shot1/2 | ge0012（Shot1）、ge0025（Shot2） |
| pe03 书房胡桃木桌 | Shot1/3 | ge0005 |
| pe04 原木椅 | Shot1/3 | ge0013 |
| pe05 走廊窄玄关桌 | Shot2 | ge0024 |

未要求的镜头标为 `not_required`，不代表实体物理不存在。`required` 指镜头中某时应出现，不要求每个关键帧可见。衣物作为女子属性，书房作为场景，不另建 prompt 实例。

36 个冻结全局视觉记录：**bound 7、unbound 29、unknown 0**。5 个 prompt 实体均有对应；全部 10 个 required 实体-镜头条目有正观察对应。仍不据此输出 schedule 合规分或推断关键帧间的缺失。完整逐实体理由见 [bindings.md](binding/bindings.md)，双向对应和 15 个 schedule 条目见 [results.json](binding/results.json)。

女子、红本跨场景分别有两个视觉记录，对应同一个 prompt ID，但没有新建视觉身份边或合并跨场景实体。原 side-table plant ambiguous 关联保持原样。杯、灯、笔筒、纸巾包等属于本次正常情节 registry 之外，因此 unbound；这不表示完整异常生成指令从未提过它们。分类始终相对于所提供的固定 registry。

## 已有外观分数分组

复用最新 `pipeline_parallel_20260921/run` 已有 v6 Codex 和独立 DINO 结果，零新增外观调用。保持按视觉实体记录等权、Codex RMS deficits 及 DINO 均值；不按 prompt ID 重新合并或加权。

| 类别 | 记录数 | 可评分 / null | Codex RMS 分数 | Codex 普通均值 | DINO 均值 |
|---|---:|---:|---:|---:|---:|
| bound | 7 | 7 / 0 | 87.278744 | 93.75 | 0.827630 |
| unbound | 29 | 27 / 2 | 84.701193 | 95.987654 | 0.936161 |
| unknown | 0 | 0 / 0 | null | null | null |

这是按归属划分的条件外观统计，**不是完整 SB/SU**。原始存在性、空间评分及分母没有变；没有新增 schedule 缺失、Prompt 属性符合度或混合实体对归属规则。

## 验证与费用

- 一次新的独立 GPT-6 Astra/medium 调用，18 张原始关键帧、36 个视觉记录、全部原始 2D 观察坐标；未重跑 WeDetect、几何、身份、DINO 或外观模型。不是新完整端到端运行。
- 调用耗时 99.05 秒（不含节点检查、开发、审计），input 28,582、cached input 0、output 2,738，共 **31,320 tokens / USD 0.422720 标准 API 等价估算**，非实际账单。沿用项目 2026-09-21 已核实定价：每百万 uncached/cache-read/cache-write/output 为 USD 10/1/12.5/50，cached input 为 input 子集不重复计费；本次无长上下文倍率或缓存写入。价格来源记录见上一完整运行 `study3_appearance_full_20260921/pricing.json`。
- 初次本地后处理过窄地要求 fact ID 必须列在所匹配实体条目下，拒绝了女子引用其他 registry 条目中“拿起/放下笔记本”的真实事实。修正为允许所有已提供且原文验证通过的 registry fact ID；未知 fact ID 仍拒绝。保留唯一原始响应和调用时代码快照，仅重新本地校验；没有改写任何分类、重试或选择模型回复。上述费用包含这次开发调用，无额外收费纠错调用。
- 22 项聚焦测试通过（11 新分类/引用/缺失保留/重复对应/费用测试、7 原外观集成、4 原并发调度）。实际 integrated CLI plan-only 验证新依赖；不传 registry 的 plan 与先前保存的完整计划逐项一致。
- [audit.json](audit.json) 验证原始图片、坐标、全部实体覆盖、原始响应和源文件哈希、费用计数、分组人口、未改变的旧执行计划。[replay_audit.json](replay_audit.json) 验证修正后的完整新增入口在完全相同输入/图片/模型响应上成功结束；回放费用为 0 calls / 0 tokens / USD 0，引用历史调用数字不重复计入。
- 使用现有 allocation196093/node197，单 CPU/nice19，无新增 GPU allocation；SSH 主机 key 不符时改用既有 Slurm allocation，没有绕过主机校验。全部本次推理结束。

这是一个冻结输入的开发验证，未做人类独立标注校准；unknown 为零仅是本例结果，不能证明其他情节的对应均无歧义。

实现与命令：[prompt-binding-v1.md](../../docs/prompt-binding-v1.md)。
