import json,csv
from pathlib import Path
R=Path(__file__).resolve().parent;BASE=R.parent/'temporal_v2_study234_revised_20260920'
read=lambda p:json.loads(Path(p).read_text())
MODES=['boundary_compact_medium','shots_compact_medium','spatial_compact_low','spatial_efficient_low','within_compact_medium_fixed']
def usage(path):
 d=read(path);us=d.get('usage',d.get('known_usage',[]));us=[us] if isinstance(us,dict) else us
 v=dict(input=0,output=0,cached=0,tokens=0,usd=0.,seconds=d.get('seconds',0),status=d['status'])
 for u in us:
  i=u['input_tokens'];o=u['output_tokens'];c=u.get('cached_input_tokens',0);w=u.get('cache_write_input_tokens',0);large=i>272000
  v['input']+=i;v['output']+=o;v['cached']+=c;v['tokens']+=i+o
  v['usd']+=((i-c-w)*10+c+w*12.5)*(2 if large else 1)/1e6+o*50*(1.5 if large else 1)/1e6
 return v
def sumusage(paths):
 rows=[usage(p) for p in paths];return {k:sum(r[k] for r in rows) for k in ['input','output','cached','tokens','usd','seconds']}
prod=[];validation=[]
for n in ['study2','study3','study4']:
 base=read(BASE/n/'summary.json');old=sumusage([BASE/n/c['call']/'status.json' for c in base['calls']]);p=BASE/n/'pairs/pair_000/calls'
 prior=[p/name/'status.json' for name in ['boundary_local_shot1','boundary_local_shot3','boundary_spatial_verify']];oldspace=sumusage(prior)
 p=R/'spatial_efficient_low'/n/'calls';newspace=sumusage(list(p.glob('*/status.json')))
 projected={k:old[k]-oldspace[k]+newspace[k] for k in ['input','output','cached','tokens','usd']}
 parallel=max(usage(p/'boundary_local_shot1/status.json')['seconds'],usage(p/'boundary_local_shot3/status.json')['seconds'])+usage(p/'boundary_spatial_verify/status.json')['seconds']
 prod.append(dict(study=n,baseline=old,baseline_spatial=oldspace,selected_spatial=newspace,estimated_pipeline=projected,baseline_pipeline_seconds=base['elapsed_seconds'],estimated_spatial_parallel_seconds=parallel,estimated_pipeline_seconds=base['elapsed_seconds']-oldspace['seconds']+parallel))
for mode in MODES:
 for n in ['study2','study3','study4']:
  paths=list((R/mode/n/'calls').glob('*/status.json'));u=sumusage(paths)
  validation.append(dict(mode=mode,study=n,calls=len(paths),complete=all(usage(p)['status']=='success' for p in paths),**u))
assert all(x['status']=='success' for x in read(R/'selected_validation.json'))
result=dict(scope='Controlled frozen-upstream component validation, not a fresh GPU end-to-end run. Unchanged stages retain baseline measurements; new full-pipeline cost/latency are composition estimates.',currency='USD',pricing=dict(model='gpt-6-astra',uncached_per_million=10,cached_per_million=1,output_per_million=50,source='https://developers.openai.com/api/docs/models/gpt-6-astra',actual_billing=False),production=prod,validation=validation)
(R/'cost_quality_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
with (R/'cost_comparison.csv').open('w') as f:
 w=csv.writer(f);w.writerow(['study','baseline_tokens','estimated_tokens','baseline_usd','estimated_usd','baseline_seconds','estimated_seconds'])
 for p in prod:w.writerow([p['study'],p['baseline']['tokens'],p['estimated_pipeline']['tokens'],p['baseline']['usd'],p['estimated_pipeline']['usd'],p['baseline_pipeline_seconds'],p['estimated_pipeline_seconds']])
a=sum(p['baseline']['usd'] for p in prod);b=sum(p['estimated_pipeline']['usd'] for p in prod);ta=sum(p['baseline']['tokens'] for p in prod);tb=sum(p['estimated_pipeline']['tokens'] for p in prod)
md=['# Study2/3/4：质量约束下的成本优化','',
'采用 `temporal_cost_v1`：GPT-6 Astra保持不变；仅边界空间取证/终审使用无损压缩输入、短字段和共享见证输出、low推理。两个单镜头取证并行，最终复核等待两侧。运动预期、镜头内评估、身份匹配/复核、边界存在性和检测聚类均保留原实现及medium。','',
'## 成本（标准API等价估算，不是账单）','',
'| 测例 | 原tokens | 优化后估算tokens | 原USD | 优化后估算USD | 降费 |','|---|---:|---:|---:|---:|---:|']
for p in prod:
 x=p['baseline'];y=p['estimated_pipeline'];md.append(f"| {p['study']} | {x['tokens']:,} | {y['tokens']:,} | ${x['usd']:.2f} | ${y['usd']:.2f} | {(1-y['usd']/x['usd'])*100:.1f}% |")
md += [f'| 合计 | {ta:,} | {tb:,} | ${a:.2f} | ${b:.2f} | {(1-b/a)*100:.1f}% |','',
'输入$10/M、缓存输入$1/M、输出$50/M；逐请求按272K长上下文阈值检查。使用日志实际缓存命中；未来命中可能变化。只含模型API等价费用，不含本对话或GPU计算。价格来源：https://developers.openai.com/api/docs/models/gpt-6-astra 。','',
'## 质量与验证范围','',
'三个案例的完整边界事件状态、全部实体/实体对聚合状态、分母和分数均与基线一致。Study2/3绿杯–笔筒冲突保留，Study2灯缺失及纸巾新增、Study3纸巾新增保留，Study4剧情允许换杯仍豁免。原运动标签、原完整身份对应和九个镜头内结果均未改变。','',
'验收不只比较总分：selected_validation.json、各selected_replay/*/composition_audit.json核对实际规范输入、全部原图hash、原决策prompt前缀、规范输出schema、全部事件和评分单位。数值注册、尾首帧目标、所有上下文帧、独立见证/因果/逐轴门槛保留。几何原始定义数值不取整；重复子树/表格无损，派生角点误差<=1e-9。','',
'本轮是冻结上游检测/几何/身份后的真实模型组件对照，并以原未修改阶段组合验证；没有重新跑GPU前端，也没有把组合估计写成新端到端实测。并行调度已做隔离/等待回归测试；下表并行时间是根据已测独立调用推算。','',
'| 测例 | 原空间阶段秒 | 新空间阶段串行实测秒 | 新空间阶段并行估算秒 | 原整条分钟 | 新整条估算分钟 |','|---|---:|---:|---:|---:|---:|']
for p in prod:md.append(f"| {p['study']} | {p['baseline_spatial']['seconds']:.1f} | {p['selected_spatial']['seconds']:.1f} | {p['estimated_spatial_parallel_seconds']:.1f} | {p['baseline_pipeline_seconds']/60:.2f} | {p['estimated_pipeline_seconds']/60:.2f} |")
md += ['','## 未采用方案','',
'- 全时序输入压缩：运动预期存在实质变化，例如Study2Shot1红本首区间reasonable_motion→static；虽然总分相同，评分资格发生变化，拒绝。',
'- 边界存在性压缩：Study2 g10、Study3 g17/g27由unknown变exempt，存在性分母和分数变化，拒绝。',
'- 固定原运动标签后的镜头内压缩：Study3及Study4仍有unknown→exempt变化，拒绝。',
'- 空间compact/medium、compact/low、efficient/low均在三组保留全部空间状态；选费用合计最低的efficient/low。未测试/未使用GPT-5.6。','',
'## 优化验证开销（一次性，不能混入单次生产费用）','',
'| 方案 | 调用 | tokens | 估算USD |','|---|---:|---:|---:|']
for mode in MODES:
 vs=[v for v in validation if v['mode']==mode];md.append(f"| {mode} | {sum(v['calls'] for v in vs)} | {sum(v['tokens'] for v in vs):,} | ${sum(v['usd'] for v in vs):.2f} |")
md.append(f"| 合计 | {sum(v['calls'] for v in validation)} | {sum(v['tokens'] for v in validation):,} | ${sum(v['usd'] for v in validation):.2f} |")
if not all(v['complete'] for v in validation):md.append('\n仍有候选调用未完成，验证总成本暂不完整；已选组件与组合验收已完成。')
(R/'REPORT.md').write_text('\n'.join(md)+'\n');print(json.dumps(dict(old_usd=a,new_estimated_usd=b,old_tokens=ta,new_estimated_tokens=tb,validation_usd=sum(v['usd'] for v in validation),all_validation_calls_complete=all(v['complete'] for v in validation)),indent=2))

with (R/'REPORT.md').open('a') as f:f.write('\n\n工程验证：时序/传输27项、边界空间9项、集成9项，共45项通过；三个manifest的真实CLI plan-only验证通过。当前工作区已有global_entity_table导出，计划核对使用当前回退配置而不是历史22阶段假设，确认本轮未增删阶段或依赖。选定源代码快照和hash见selected_code_snapshot/、selected_source_hashes.json。\n')
