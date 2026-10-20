# Wan2.2 专用 prompt：400条完成

在冻结的400条原始episode上完成2,000个逐shot输入。每个原始shot文本保持逐字不变；只在末尾追加必要的前文描述。1084个shot有补充，916个shot原样保留，共1644项补充。全部最终输入均通过实际Wan UMT5 tokenizer的512硬门槛（包含特殊token），未发生截断。

## 直接使用

- 全量及顺序：`deliverables/generation_queue_400.jsonl`。
- 优先100：`deliverables/core_100.jsonl`；优先200累计集：`deliverables/priority_200.jsonl`。
- 第二阶段新增100：`deliverables/stage2_additional_100.jsonl`；最后新增200：`deliverables/stage3_remaining_200.jsonl`。
- 每个shot的最终输入字段为`wan_prompt_en`，也保存为`deliverables/prompts/<episode_id>/<shot_id>.txt`。
- `generation_prompt_en_original`和`global_prompt_original`仅用于追溯。直接把最终shot输入交给Wan，**不要再自动拼接global或其他shot**；本次512验证覆盖的就是完整`wan_prompt_en`。
- `deliverables/review.html`高亮每处补充；`context_additions`保存精确引文、目标引用和必要性说明；`token_audit.csv`提供逐shot实际长度。

## 长度与子集

| 子集 | Episode | Shot | 有补充的Shot | 平均tokens | 最长tokens | 超过512 |
|---|---:|---:|---:|---:|---:|---:|
| Core100 | 100 | 500 | 307 | 154.02 | 341 | 0 |
| Priority200（累计） | 200 | 1000 | 607 | 151.50 | 341 | 0 |
| Full400 | 400 | 2000 | 1084 | 145.07 | 364 | 0 |

保持原始episode/shot/scene编号、shot数、目标时长和优先队列顺序。Priority200包含Core100；不能将其作为Core100之后额外200条重复提交。

## 处理与质量检查

1. 只使用现有global/per-shot原文；不读取源视频、图像、源实体描述或其他非prompt事实。不引用未来shot。
2. 每4episode一批，Astra/medium产生最小补充；另一个独立上下文对全部shot复核，保留正确补充、删除冗余/无据内容，并补上遗漏。正式阶段16路并行，模型和判断标准未降级。
3. 程序逐项校验当前引用和前文引文必须精确存在、只引用同episode前文、每shot完整且有序、无未解决依赖、原文为逐字前缀；真实tokenizer同时比较无截断与生产设置下的token IDs。
4. 主代理检查前8episode全部补充，随后检查全量词汇/动作候选筛查结果和针对性原文。复核纠正了首批将short dark-haired man误读为短发的错误。两处动物颜色描述中多加的fur材质词经过定点模型复核，改为原文支持的颜色/花纹描述；原始模型响应保留在calls和correction_history中。
5. 独立的`audit_deliverables.py`重新读取实际交付文件、source/queue、每个.txt、全部引用和tokenizer输出，核对嵌套子集、hash与复核结果。`independent_validation.json`全部通过。

成功校验前有2次候选未通过机械检查，均保留并重试，没有截断或忽略错误。语义质量依据是完整独立模型复核及主代理针对性检查，不是独立人工逐条标注或形式化语义等价证明。正式entity schedule仍未编译；本次没有修改原始源数据、原始优先队列或评测器，也没有开始生成视频。

## 使用量、成本和时间

| 阶段 | 模型调用 | Input+Output tokens | 标准API等价USD |
|---|---:|---:|---:|
| 初稿（含重试） | 102 | 1,067,764 | $18.495280 |
| 独立复核（含重试） | 100 | 1,255,888 | $19.578464 |
| 定点纠正复核 | 2 | 24,401 | $0.374978 |
| 总计 | 204 | 2,348,053 | $38.448722 |

输入1,869,765 tokens，其中缓存命中462,592（属于输入子集）；输出478,288。按项目已核实的2026-09-20 Astra标准价格估算：未缓存输入$10/M、缓存输入$1/M、输出$50/M；未重复计算缓存。完整依据见pricing.json。**不是实际账单**，实际计费金额不可得。包括本次重试与定点纠正；不包括父对话和历史源数据构造。

从首个模型调用开始到本报告的处理墙钟约26.77分钟，包含首批检查、并行生成、复核与最终检查；不是视频生成耗时。复用既有206117/node306的检查空闲CPU，nice10和58–61 affinity；纯CPU/API，无GPU、无新资源分配。离线校验自身0API调用/0计费tokens/$0。

原始数据SHA256：`e124ff566333309b1c1a667408b8aaabb506f4ae9f224253f9f2d6e200c08fb9`。原始优先队列SHA256：`bb58acc3f6b6b0ff21f295ee52efd86432929c1efde4abedb7d0604d013ca314`。输出文件hash、完整token记录、模型响应和失败历史均已保存。用户本次外部文本处理授权见authorization.json。

## 本地汇总恢复记录

全部100批已保存后，主汇总读取了仍在进行的定点纠正调用，因其尚无最终seconds字段而报KeyError。待纠正结束后，对全部缓存结果重新校验并完成汇总，13.1801秒、0新增模型调用/0计费tokens/USD0。无数据丢失或重生成；见summary_recovery.json。记录的模型调用重叠峰值为16，首个至最后一个模型调用跨度1368.7706秒。最后的缓存校验使用4个线程，不代表生成阶段并发度。
