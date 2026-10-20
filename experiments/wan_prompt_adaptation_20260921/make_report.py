#!/usr/bin/env python3
"""Generate final documentation only after delivery and independent audit pass."""
import collections
import json
from pathlib import Path
import statistics
import time

HERE=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_text())
audit=read(HERE/'audit.json');check=read(HERE/'independent_validation.json');usage=read(HERE/'usage_cost.json')
assert check['status']=='pass' and audit['episodes']==400 and audit['shots']==2000
assert usage['unavailable_or_inflight_costs']==0
rows=[json.loads(s) for s in (HERE/'deliverables/generation_queue_400.jsonl').read_text().splitlines()]
table=[]
for name,n in [('Core100',100),('Priority200（累计）',200),('Full400',400)]:
    ss=[s for e in rows[:n] for s in e['shots']]
    table.append(f"| {name} | {n} | {len(ss)} | {sum(bool(s['context_additions']) for s in ss)} | {statistics.mean(s['wan_tokens_including_special'] for s in ss):.2f} | {max(s['wan_tokens_including_special'] for s in ss)} | 0 |")
groups=collections.defaultdict(lambda:dict(calls=0,tokens=0,usd=0.))
starts=[];ends=[];bad=[]
for row in usage['rows']:
    p=Path(row['path']);status=read(p);starts.append(status['started']);ends.append(status['started']+status['seconds'])
    name='定点纠正复核' if 'primary_source_check' in str(p) else ('初稿（含重试）' if p.parent.name.startswith('draft') else '独立复核（含重试）')
    group=groups[name];group['calls']+=1;group['usd']+=row['standard_api_equivalent_usd']
    group['tokens']+=sum(u.get('input_tokens',0)+u.get('output_tokens',0) for u in row['usage'])
    v=p.parent/'validation.json'
    if v.exists() and read(v)['status']!='pass':bad.append(str(v.relative_to(HERE)))
costrows=[f"| {k} | {v['calls']} | {v['tokens']:,} | ${v['usd']:.6f} |" for k,v in groups.items()]
wall=time.time()-min(starts)
report=f'''# Wan2.2 专用 prompt：400条完成

在冻结的400条原始episode上完成2,000个逐shot输入。每个原始shot文本保持逐字不变；只在末尾追加必要的前文描述。{audit['changed_shots']}个shot有补充，{audit['unchanged_shots']}个shot原样保留，共{audit['additions']}项补充。全部最终输入均通过实际Wan UMT5 tokenizer的512硬门槛（包含特殊token），未发生截断。

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
{chr(10).join(table)}

保持原始episode/shot/scene编号、shot数、目标时长和优先队列顺序。Priority200包含Core100；不能将其作为Core100之后额外200条重复提交。

## 处理与质量检查

1. 只使用现有global/per-shot原文；不读取源视频、图像、源实体描述或其他非prompt事实。不引用未来shot。
2. 每4episode一批，Astra/medium产生最小补充；另一个独立上下文对全部shot复核，保留正确补充、删除冗余/无据内容，并补上遗漏。正式阶段16路并行，模型和判断标准未降级。
3. 程序逐项校验当前引用和前文引文必须精确存在、只引用同episode前文、每shot完整且有序、无未解决依赖、原文为逐字前缀；真实tokenizer同时比较无截断与生产设置下的token IDs。
4. 主代理检查前8episode全部补充，随后检查全量词汇/动作候选筛查结果和针对性原文。复核纠正了首批将short dark-haired man误读为短发的错误。两处动物颜色描述中多加的fur材质词经过定点模型复核，改为原文支持的颜色/花纹描述；原始模型响应保留在calls和correction_history中。
5. 独立的`audit_deliverables.py`重新读取实际交付文件、source/queue、每个.txt、全部引用和tokenizer输出，核对嵌套子集、hash与复核结果。`independent_validation.json`全部通过。

成功校验前有{len(bad)}次候选未通过机械检查，均保留并重试，没有截断或忽略错误。语义质量依据是完整独立模型复核及主代理针对性检查，不是独立人工逐条标注或形式化语义等价证明。正式entity schedule仍未编译；本次没有修改原始源数据、原始优先队列或评测器，也没有开始生成视频。

## 使用量、成本和时间

| 阶段 | 模型调用 | Input+Output tokens | 标准API等价USD |
|---|---:|---:|---:|
{chr(10).join(costrows)}
| 总计 | {usage['calls']} | {usage['total_tokens']:,} | ${usage['standard_api_equivalent_usd']:.6f} |

输入{usage['usage']['input_tokens']:,} tokens，其中缓存命中{usage['usage']['cached_input_tokens']:,}（属于输入子集）；输出{usage['usage']['output_tokens']:,}。按项目已核实的2026-09-20 Astra标准价格估算：未缓存输入$10/M、缓存输入$1/M、输出$50/M；未重复计算缓存。完整依据见pricing.json。**不是实际账单**，实际计费金额不可得。包括本次重试与定点纠正；不包括父对话和历史源数据构造。

从首个模型调用开始到本报告的处理墙钟约{wall/60:.2f}分钟，包含首批检查、并行生成、复核与最终检查；不是视频生成耗时。复用既有206117/node306的检查空闲CPU，nice10和58–61 affinity；纯CPU/API，无GPU、无新资源分配。离线校验自身0API调用/0计费tokens/$0。

原始数据SHA256：`{audit['source_sha256']}`。原始优先队列SHA256：`{audit['priority_queue_sha256']}`。输出文件hash、完整token记录、模型响应和失败历史均已保存。用户本次外部文本处理授权见authorization.json。
'''
(HERE/'REPORT.md').write_text(report)
(HERE/'STATUS.md').write_text('# 已完成\n\n400episode/2000shot已生成并复核，交付文件及独立检查通过。详见[REPORT.md](REPORT.md)。本次外部处理授权已获用户确认，历史审批拒绝已解决。\n')
runtime=read(HERE/'runtime.json');runtime.update(status='complete',finished=time.time(),whole_task_seconds_since_first_model_call=wall,active_task_processes=False)
(HERE/'runtime.json').write_text(json.dumps(runtime,ensure_ascii=False,indent=2)+'\n')
(HERE/'completion.json').write_text(json.dumps({'completed':True,'episodes':400,'shots':2000,'changed_shots':audit['changed_shots'],
    'unchanged_shots':audit['unchanged_shots'],'max_tokens':audit['wan_tokens_max'],'model_calls':usage['calls'],
    'total_tokens':usage['total_tokens'],'standard_api_equivalent_usd':usage['standard_api_equivalent_usd'],
    'whole_task_seconds_since_first_model_call':wall,'failed_validation_attempts':bad,'stage_usage':dict(groups)},ensure_ascii=False,indent=2)+'\n')
print(json.dumps(read(HERE/'completion.json'),ensure_ascii=False,indent=2))
