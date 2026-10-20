# Appearance Codex token 精简：完整 Study2/Study3 对照

用户要求大幅降低评分token。已选择 `gs_entity_appearance_minimal.py` / compact_v3 作为后续 Codex 新入口；原 v1 与中间 v2 结果保持历史。全部474个appearance、71个全局实体保留；67个可评实体每个一次调用，4个单帧实体仍null。Astra/medium未变，DINO逐实体和聚合分逐值未变，没有融合。

| 版本 | 输入token | 缓存输入子集 | 输出token | 总token | 标准API等价USD |
|---|---:|---:|---:|---:|---:|
| 原版v1 | 1,115,217 | 253,440 | 56,934 | 1,172,151 | $11.717910 |
| 拼图/短I-O v2 | 684,912 | 230,144 | 18,406 | 703,318 | $5.698124 |
| 加短评估基础说明 v3（选用） | 410,682 | 186,368 | 19,196 | 429,878 | $3.389308 |

最终v3相对v1：总token减少 **63.33%**，标准API等价费用减少 **71.08%**。这是同一两study全部67个有效实体的实测总量，不是按样本外推。保留预筛的同版本成功结果，完整阶段没有重复调用这些实体。
本次优化验证额外执行v2/v3各67次，共134次、1,133,196tokens/$9.087432；它与未来单次完整评测的v3费用分开计算。历史v1费用不计入这次新增验证支出。没有失败调用或自动重试。

## 如何节省

- 940张原crop/全帧附件变为77张原像素crop拼图。所有可评crop均在，未抽样/缩小；四个单帧实体虽不调用，也完成本地拼图与覆盖审计。
- 原始整帧、路径、hash、检测分数保留本地，不在每个实体调用重复输入。相关正常剧情完整保留。
- 输出只含逐panel可用性、四维分数/证据数组、一段短说明和限制；总分由程序按原均值公式计算。
- 用官方支持的调用级 `model_instructions_file` 替换无关编码代理说明，每调用约再少4100输入token；只影响appearance调用，没有改用户配置/凭据/provider/model/reasoning/工具隔离。
配置依据：[OpenAI Codex sample config](https://learn.chatgpt.com/docs/config-file/config-sample)。实际调用额外参数保存在execution_override.json，CLI公共原命令另存request.json。

## 分数影响必须单独看

67个可评实体中，62个总分与v1相同；平均绝对变化0.7774分，最大变化18.7500分。不能宣称完全等价或零质量损失：缺少整帧上下文、拼图模型内缩放/注意力、简短输出和模型自身波动均可能影响判断，当前无人工真值集可分离各因素。
已知台灯变色与人物裤装变化仍被识别；v3台灯颜色维度仍25，但其他结构/细节维度变为100，总分81.25而非旧62.5。这是实质判分差异，未隐藏或按更低/更高分选择结果。

| Study | 范围 | 旧Codex | 新Codex | DINO（不变） |
|---|---|---:|---:|---:|
| study2 | 全部有效实体 | 98.3456 | 98.1618 | 0.910026 |
| study2 | 跨shot实体子集 | 94.4444 | 93.7500 | 0.865530 |
| study3 | 全部有效实体 | 96.6540 | 97.5379 | 0.911623 |
| study3 | 跨shot实体子集 | 89.5833 | 93.1250 | 0.858438 |

所有非零变动见score_changes.csv；部分原有细节扣分消失，另一些变严格，需人工校准。植物/花盆边界的已有风险没有借压缩偷偷修规则。

## 验证与运行

5个针对性CPU测试通过：native-pixel拼图覆盖/顺序/越界排版回取，简短schema和证据编号/可用性/均值/未知检验，以及只有本次命令基础说明改变。完整bitmap审计474项，DINO完全相等，67次调用实际override/工具隔离、源hash和数学均值检查通过。现有job196093/node197，CPU/APIonly，无GPU或新资源申请。
新数据不需要先跑旧Codex。先canonical prepare+DINO，再minimal prepare/score，最后summarize_entity_appearance_compact.py；协议和命令见EECBench/docs/entity-appearance-compact-v3.md。独立下游pipeline，未自动修改temporal_v2。
费用按[官方Astra标准价格](https://developers.openai.com/api/docs/models/gpt-6-astra)2026-09-20核验口径：输入$10/M、缓存输入$1/M、缓存写入$12.5/M、输出$50/M；按每调用长上下文条件计算。缓存输入包含在input、reasoning包含在output，不重复计数。费用是API等价估算，不是实际账单，不含交互式对话和集群费用。
source_snapshot/保留实现；comparison.json/results.json是总量和审计；study*/summary.json、REPORT.md是逐实体与分组结果；原始输出/usage/实际命令见study*/calls。
