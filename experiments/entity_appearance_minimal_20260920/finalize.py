import json,hashlib,csv
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
EXP=Path(__file__).resolve().parent
read=lambda p:json.loads(Path(p).read_text())
v2=read(ROOT/'experiments/entity_appearance_compact_20260920/comparison.json')
v3=read(EXP/'comparison.json')
old=read(ROOT/'experiments/entity_appearance_separate_20260920/results.json')
current={s:read(EXP/s/'summary.json') for s in ('study2','study3')}
for p,h in read(EXP/'implementation_hashes.json').items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h
assert v3['calls']==67 and v3['entities']==71 and v3['all_appearances_pixel_audit']==474
checks={}
for study,summary in current.items():
 assert summary['calls']==(34 if study=='study2' else 33)
 for row in summary['entities']:
  prior=next(x for x in old['studies'][study]['entities'] if x['global_entity_id']==row['global_entity_id'])
  assert row['dino_score']==prior['dino_score'] and row['appearances']==prior['appearances']
  if row['codex_score'] is None:continue
  call=EXP/study/'calls'/row['global_entity_id'];override=read(call/'execution_override.json');request=read(call/'request.json')
  cmd=request['command'];assert override['actual_command']==cmd[:-1]+['-c','model_instructions_file='+json.dumps(override['model_instructions_file']),'-']
  assert hashlib.sha256(Path(override['model_instructions_file']).read_bytes()).hexdigest()==override['model_instructions_sha256']
  checks[study+'/'+row['global_entity_id']]=True
 for key in ('all_entities','multi_shot_entities','single_shot_entities'):
  assert abs(summary[key]['dino']['score']-old['studies'][study][key]['dino']['score'])<1e-12
validation_cost=v2['after']['api_equivalent_usd']+v3['after']['api_equivalent_usd']
validation_tokens=v2['after']['total_tokens']+v3['after']['total_tokens']
combined=dict(baseline=v3['before'],compact_v2=v2['after'],selected_v3=v3['after'],
              token_reduction=v3['token_reduction'],cost_reduction=v3['cost_reduction'],
              validation_calls=134,validation_tokens=validation_tokens,validation_api_equivalent_usd=validation_cost,
              studies=current,quality=dict(exact_scores=v3['equal_scores'],scored_entities=v3['scored_entities'],
              mean_absolute_score_delta=v3['score_mae'],max_absolute_score_delta=v3['max_score_delta'],human_calibrated=False),
              audit=dict(appearances=474,pixel_roundtrip=True,unchanged_dino=True,implementation_hashes=True,
                         invocation_overrides_checked=len(checks),all_evidence_schema_and_score_math=True,tests=5))
(EXP/'results.json').write_text(json.dumps(combined,ensure_ascii=False,indent=2)+'\n')
with (EXP/'score_changes.csv').open('w') as f:
 fields=['study','entity','name','old','new','delta','old_dimensions','new_dimensions','reason','limits'];w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
 for r in v3['rows']:w.writerow({k:r[k] for k in fields})
lines=['# Appearance Codex token 精简：完整 Study2/Study3 对照','',
 '用户要求大幅降低评分token。已选择 `gs_entity_appearance_minimal.py` / compact_v3 作为后续 Codex 新入口；原 v1 与中间 v2 结果保持历史。全部474个appearance、71个全局实体保留；67个可评实体每个一次调用，4个单帧实体仍null。Astra/medium未变，DINO逐实体和聚合分逐值未变，没有融合。','',
 '| 版本 | 输入token | 缓存输入子集 | 输出token | 总token | 标准API等价USD |','|---|---:|---:|---:|---:|---:|']
for label,u in [('原版v1',v3['before']),('拼图/短I-O v2',v2['after']),('加短评估基础说明 v3（选用）',v3['after'])]:
 lines.append(f'| {label} | {u["input_tokens"]:,} | {u["cached_input_tokens"]:,} | {u["output_tokens"]:,} | {u["total_tokens"]:,} | ${u["api_equivalent_usd"]:.6f} |')
lines += ['',f'最终v3相对v1：总token减少 **{v3["token_reduction"]:.2%}**，标准API等价费用减少 **{v3["cost_reduction"]:.2%}**。这是同一两study全部67个有效实体的实测总量，不是按样本外推。保留预筛的同版本成功结果，完整阶段没有重复调用这些实体。',
          f'本次优化验证额外执行v2/v3各67次，共134次、{validation_tokens:,}tokens/${validation_cost:.6f}；它与未来单次完整评测的v3费用分开计算。历史v1费用不计入这次新增验证支出。没有失败调用或自动重试。','',
          '## 如何节省','',
          '- 940张原crop/全帧附件变为77张原像素crop拼图。所有可评crop均在，未抽样/缩小；四个单帧实体虽不调用，也完成本地拼图与覆盖审计。',
          '- 原始整帧、路径、hash、检测分数保留本地，不在每个实体调用重复输入。相关正常剧情完整保留。',
          '- 输出只含逐panel可用性、四维分数/证据数组、一段短说明和限制；总分由程序按原均值公式计算。',
          '- 用官方支持的调用级 `model_instructions_file` 替换无关编码代理说明，每调用约再少4100输入token；只影响appearance调用，没有改用户配置/凭据/provider/model/reasoning/工具隔离。',
          '配置依据：[OpenAI Codex sample config](https://learn.chatgpt.com/docs/config-file/config-sample)。实际调用额外参数保存在execution_override.json，CLI公共原命令另存request.json。','',
          '## 分数影响必须单独看','',
          f'{v3["scored_entities"]}个可评实体中，{v3["equal_scores"]}个总分与v1相同；平均绝对变化{v3["score_mae"]:.4f}分，最大变化{v3["max_score_delta"]:.4f}分。不能宣称完全等价或零质量损失：缺少整帧上下文、拼图模型内缩放/注意力、简短输出和模型自身波动均可能影响判断，当前无人工真值集可分离各因素。',
          '已知台灯变色与人物裤装变化仍被识别；v3台灯颜色维度仍25，但其他结构/细节维度变为100，总分81.25而非旧62.5。这是实质判分差异，未隐藏或按更低/更高分选择结果。','',
          '| Study | 范围 | 旧Codex | 新Codex | DINO（不变） |','|---|---|---:|---:|---:|']
for study,summary in current.items():
 for key,label in [('all_entities','全部有效实体'),('multi_shot_entities','跨shot实体子集')]:
  a,b=old['studies'][study][key],summary[key];lines.append(f'| {study} | {label} | {a["codex"]["score"]:.4f} | {b["codex"]["score"]:.4f} | {b["dino"]["score"]:.6f} |')
lines+=['','所有非零变动见score_changes.csv；部分原有细节扣分消失，另一些变严格，需人工校准。植物/花盆边界的已有风险没有借压缩偷偷修规则。',
        '','## 验证与运行','',
        '5个针对性CPU测试通过：native-pixel拼图覆盖/顺序/越界排版回取，简短schema和证据编号/可用性/均值/未知检验，以及只有本次命令基础说明改变。完整bitmap审计474项，DINO完全相等，67次调用实际override/工具隔离、源hash和数学均值检查通过。现有job196093/node197，CPU/APIonly，无GPU或新资源申请。',
        '新数据不需要先跑旧Codex。先canonical prepare+DINO，再minimal prepare/score，最后summarize_entity_appearance_compact.py；协议和命令见EECBench/docs/entity-appearance-compact-v3.md。独立下游pipeline，未自动修改temporal_v2。',
        '费用按[官方Astra标准价格](https://developers.openai.com/api/docs/models/gpt-6-astra)2026-09-20核验口径：输入$10/M、缓存输入$1/M、缓存写入$12.5/M、输出$50/M；按每调用长上下文条件计算。缓存输入包含在input、reasoning包含在output，不重复计数。费用是API等价估算，不是实际账单，不含交互式对话和集群费用。',
        'source_snapshot/保留实现；comparison.json/results.json是总量和审计；study*/summary.json、REPORT.md是逐实体与分组结果；原始输出/usage/实际命令见study*/calls。']
(EXP/'REPORT.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({k:v for k,v in combined.items() if k!='studies'},ensure_ascii=False))
