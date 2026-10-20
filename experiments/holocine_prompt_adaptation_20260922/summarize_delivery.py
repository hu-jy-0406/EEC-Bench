#!/usr/bin/env python3
"""Write factual final report only after all 400 candidate exports exist."""
import collections,json
from run import HERE,read,dump,io,usage

io.safe_compute()
rows=read(HERE/'deliverables/index.json')['episodes']
assert len(rows)==400 and all(r['status'] in ['ready','not_ready'] for r in rows)
u=usage();groups=collections.defaultdict(collections.Counter)
for r in rows:groups[r['shot_count']][r['status']]+=1
ready=sum(r['generation_allowed'] for r in rows)
exceptions=read(HERE/'deliverables/exceptions.json')
reasons=collections.Counter(x for r in exceptions for x in r['reasons'])
table='\n'.join(f"| {n} | {sum(g.values())} | {g['ready']} | {g['not_ready']} |" for n,g in sorted(groups.items()))
cost=(f"USD {u['standard_api_equivalent_usd']:.6f}" if u['standard_api_equivalent_usd'] is not None else f"known USD {u['known_standard_api_equivalent_usd']:.6f}; {u['unknown_or_inflight']} calls have unavailable cost")
report=f'''# HoloCine 400条专属 prompt 压缩与审计

400条均已生成并审计候选：{ready}条通过全部生成门槛，{400-ready}条仍未满足全部限制。不能把整个400条包视为可直接生成队列。

| 镜头数 | Episode数 | 可生成 | 暂不可生成 |
|---|---:|---:|---:|
{table}

未通过门槛（可重叠）：`{dict(reasons)}`。超长候选保留内容，禁止直接截断。多轮压缩未达标不等于数学上证明无损压缩不可能。

## 数据与评测约束

原始400个episode、2,000个镜头、64,724项claims、镜头顺序、场景ID和entity_schedule保持不变。当前三个已批准的source修订均纳入；contract.json与alignment_contract.json和权威原件逐字节一致，源队列哈希未改变。每条候选均经过独立模型逐claim、source细节、schedule和新增信息检查；完整claim集合核对防止漏审。自然语言复核是模型验证，不是形式化等价证明或独立人工标注。

使用部署仓库的原始UMT5 tokenizer类与清洗函数，对完整原生输入重算长度，包括global/per-shot分隔符和EOS；同时比对未截断和生产token IDs以及所有镜头span。上限512。仅语义pass、长度和完整性通过、没有未解决limitations者进入ready_queue。最终选择优先全部通过，其次语义完整，再比较长度；没有修改审计结论。

## 使用

- `holocine_prompts_contracts_400.zip`：全400条及原始contracts、schedule、映射、审计与异常标记。
- `deliverables/ready_queue.jsonl`：唯一通过全部门槛的生成队列，共{ready}条。
- `deliverables/exceptions.json`：{400-ready}条阻塞原因。
- `deliverables/episodes/<id>/holocine_input.json`：原生raw Mode2的精确输入。不要追加前缀、合同或使用会添加句子的structured helper；这会改变已测长度。
- `deliverables/verify_bundle.py`：可移植文件哈希/结构/claims/schedule/队列门槛验证器；不重复调用模型或tokenizer。

保留原文明确指定的镜头时长及作用范围，不将未指定时长补成5秒；两条独立复核发现的时长作用域问题单独修正并重新复核。此任务只准备prompt，不启动视频生成，不改变任何模型、encoder上限或既有生成campaign。后续使用独立验证过的生成参数与原始alignment_contract评测。

## 运行与费用

用户明确授权400条配置服务处理，并要求并行提速。主队列从32提高至64；259条未开始任务通过原子目录占位移交，新调用另存parallel命名，旧队列不重复发送；占位记录不计API调用。已有任务不取消，修复只处理终止条目。复用allocation206117/node306 CPU60–63，nice10，GPU不可见。

累计{u['calls']}次调用，{u['total_tokens']:,} tokens；标准API等价估算{cost}，不是实际账单。输入{u['tokens']['input_tokens']:,}，其中缓存{u['tokens']['cached_input_tokens']:,}（输入子集），输出{u['tokens']['output_tokens']:,}。定价依据见pricing.json：Astra每百万未缓存输入$10、缓存输入$1、输出$50。包含pilot、失败/修复与最终候选全部调用，没有只统计选中版本。详见usage_cost.json。

独立落盘回读审计：independent_delivery_audit.json；全包校验：package_validation.json。官方格式来源：https://github.com/yihao-meng/HoloCine#prompt-format 。
'''
(HERE/'REPORT.md').write_text(report)
(HERE/'STATUS.md').write_text(f'Candidate processing/export finished: 400 episodes, {ready} ready, {400-ready} explicit exceptions. Full all400 generation-ready objective remains unmet if exceptions are nonzero. See REPORT.md and deliverables/ready_queue.jsonl.\n')
dump(HERE/'delivery_summary.json',dict(episodes=400,ready=ready,not_ready=400-ready,by_shot_count={str(k):dict(v) for k,v in groups.items()},blocking_reason_counts=dict(reasons),total_tokens=u['total_tokens'],standard_api_equivalent_usd=u['standard_api_equivalent_usd']))
print(json.dumps(read(HERE/'delivery_summary.json')))
