"""Offline report from complete immutable judgments; no inference or score editing."""
from pathlib import Path
import json
R=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_text())
r=read(R/'alignment_visible/results.json');audit=read(R/'alignment_visible/audit.json');state=read(R/'alignment_visible/status.json')
b=read(R/'binding/results.json');dev=read(R/'alignment/results.json')
assert audit['status']==state['status'].replace('success','passed')=='passed'
rows=[('绑定（复用同一 registry）',b['total_tokens'],b['standard_api_equivalent_usd']),
      ('选定版本完整评分',r['total_tokens'],r['known_standard_api_equivalent_usd']),
      ('首轮语义开发试验（额外费用）',dev['total_tokens'],dev['known_standard_api_equivalent_usd'])]
lines=['# Study3：正常情节参照与 Prompt Alignment B','',
'状态：完成新评分组件验证。复用 `pipeline_parallel_20260921/run` 的18张原始关键帧、检测/几何/最终身份；不是新全流程 GPU 运行，也不是独立人类标注校准。',
'', '## 正常参照与冻结要求','',
'先创建 `reference/story_prompt_zh.md`，随后实现评分。正常情节保留女子拿红本离开书房、放到走廊玄关桌、空手返回；台灯应为黑色，水杯/笔筒及台灯保持原场景位置。删除原生成指令中的故意制造连续性错误要求，未向 judge 提供原注入指令或历史异常/分数。多出的未指定物体不自动违反本参照。',
'', '选定合同：`frozen_visible/contract.json`；9个prompt实体，83条原子要求：18presence、28appearance、17spatial、16motion、4temporal。全部在评分前冻结；文本编译脚本不读取生成视频。最初 `frozen/`、`alignment/` 将普通外观错误地扩为离画后的全程验证；统一修正28条appearance的时间量词为when_visible，其余要求、原文和registry完全相同。两轮响应/费用完整保留，最终结果全部来自选定版本的6次新评分调用，没有择优混合。',
'',f'重新绑定36个视觉记录：{b["counts"]["bound"]} bound / {b["counts"]["unbound"]} unbound / {b["counts"]["unknown"]} unknown。同一prompt角色可对应不同场景的多个global记录，未据此合并物理身份。两个背景窄木桌实例对应不明，保留unknown。',
'', '## 选定结果','',
'主分按实体/关系和镜头范围分层等权；是已判定要求上的条件符合率。T/F/U为逐条符合/违反/未知数。区间按同样层级计算未知值边界，非统计置信区间；不产生融合总分。',
'', '| 维度 | 条件分 | T/F/U | 未知取值区间 |','|---|---:|---|---|']
labels=dict(presence='存在',appearance='外观',spatial='空间',motion='运动/动作',temporal='时序/持续')
for k,d in r['dimensions'].items():
 score='null' if d['score'] is None else f'{d["score"]:.2f}'
 interval='null' if d['identification_interval'] is None else '–'.join(f'{v:.2f}' for v in d['identification_interval'])
 m=d['micro'];lines.append(f'| {labels[k]} | {score} | {m["T"]}/{m["F"]}/{m["U"]} | {interval} |')
lines+=['','## 明确违反的要求（模型判定，非人工真值）','']
for x in r['checks']:
 if x['status']=='violated':lines.append(f'- `{x["claim_id"]}`：{x["expected"]}。判定依据：{x["reason"]}')
lines+=['','## 开发试验与选定版本的波动','', '空间条件分由首轮80.95变为选定95.24。台灯位置两轮均判违反；水杯、笔筒位置从首轮违反变为选定符合。空间要求和图像未改变，但调用提示增加了外观观察域定义，且为全新模型调用；不能将分数提升当作质量提升或声称空间异常召回得到验证。保留逐条两轮差异，不混合择优 verdict。当前跨镜头没有接入注册转换用于数值判定，视觉视角推断仍需独立校准。', '', '## 未知要求','']
for x in r['checks']:
 if x['status']=='unknown':lines.append(f'- `{x["claim_id"]}`：{x["reason"]}')
lines+=['','## 验证及局限','',
'39项单元/回归测试通过（17新alignment、11binding、7appearance集成、4并行调度）；两种注册方法×四种停止阶段均保留原阶段计划；不启用新参数时与已保存生产计划精确一致。新增参数的CLI plan-only通过。确定性最终审计检查83要求精确覆盖、原帧/来源hash、单镜头证据隔离、无旧分数/运动判定输入、完整原始响应到汇总一致、费用不重复计入。',
'',
'每个scope一次fresh Astra/medium调用，3个单镜头+3个跨镜头范围。使用所有相关原图与原始2D/逐帧3D/cameras；没有另加裁剪图、密集轨迹或二审。跨镜头没有注册转换输入，禁止直接比较独立世界坐标，位置判定依赖视觉锚点/视角推断，需后续人类校准。单张图无法确认胡桃木种类、稀疏关键帧可能无法确证释放先后；出画后的物理持存不能凭情节推断为满足。原一致性/appearance/DINO结果均未改写。',
'',f'选定评分组件墙钟 {state["seconds"]:.2f}s；绑定 {b["seconds"]:.2f}s。不是完整流水线耗时。',
'', '## 用量与费用','', '| 阶段 | Tokens | USD标准API等价 |','|---|---:|---:|']
for name,t,c in rows:lines.append(f'| {name} | {t:,} | {c:.6f} |')
selected_tokens=sum(x[1] for x in rows[:2]);selected_cost=sum(x[2] for x in rows[:2])
lines +=[f'| 绑定+选定评分 | {selected_tokens:,} | {selected_cost:.6f} |',f'| 本次全部开发和验证 | {sum(x[1] for x in rows):,} | {sum(x[2] for x in rows):.6f} |','',r['cost_basis'],'缓存输入属于总输入子集，未重复计数；reasoning计入output，不重复加。人工文本编译/代码测试/离线审计0次额外API；未执行自动文本编译模型调用。未含历史前端/identity/appearance费用或本对话费用。','',
'逐项证据：`alignment_visible/report.md`；机器结果：`alignment_visible/results.json`；审计：`alignment_visible/audit.json`；源码快照：`source_snapshot_visible/`；实现文档：`../../docs/prompt-alignment-b-v1.md`。']
(R/'REPORT.md').write_text('\n'.join(lines)+'\n')
usage=[]
for stage,folder in [('binding','binding'),('selected','alignment_visible'),('development','alignment')]:
 for path in sorted((R/folder/'calls').glob('*/status.json')):
  s=read(path)
  for u in s.get('usage',[]):usage.append(dict(stage=stage,call=path.parent.name,**u))
(R/'usage_reconciled.json').write_text(json.dumps(dict(rows=usage,selected_tokens=selected_tokens,selected_standard_api_equivalent_usd=selected_cost,
 total_tokens=sum(x[1] for x in rows),total_standard_api_equivalent_usd=sum(x[2] for x in rows),billed_amount_available=False),indent=2)+'\n')
print(R/'REPORT.md')
