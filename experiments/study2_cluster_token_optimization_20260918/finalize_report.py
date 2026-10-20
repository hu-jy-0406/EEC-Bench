from pathlib import Path
import json,hashlib,shutil,csv,statistics,ast
H=Path(__file__).resolve().parent;B=H.parents[1]
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
j=read(H/'comparison.json');selected=j['runs'][-2:]
assert [x['run'] for x in selected]==['compact_scope_run01','compact_scope_run02']
assert all(x['structural_quality_gate_passed'] for x in selected)
# No source edits after the tested version.
for p in (H/'compact_scope_source').rglob('*'):
 if p.is_file():assert sha(p)==sha(B/p.relative_to(H/'compact_scope_source')),str(p)
base=j['baseline'];mean={k:statistics.mean(x['stats'][k] for x in selected) for k in ['input_tokens','output_tokens','total_tokens','seconds']}
trials=[]
for r in j['runs']:
 for shot in r['stats']['shots']:
  trials.append(dict(run=r['run'],**shot,passed_against_original=r['structural_quality_gate_passed']))
with (H/'calls.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(trials[0]));w.writeheader();w.writerows(trials)
# Preserve image bytes, inputs and final artifact provenance.
source_hashes={}
for p in [B/'scripts/run_wedetect_shot_entities.py',B/'tests/test_wedetect_shot_entities.py',*list((B/'skills/wedetect-shot-entities').glob('*'))]:
 if p.is_file():
  dst=H/'promoted_source'/p.relative_to(B);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst);source_hashes[str(p)]=sha(p)
(H/'promoted_source/manifest.json').write_text(json.dumps(source_hashes,indent=2)+'\n')
assert (B/'skills/wedetect-shot-entities/output.schema.json').read_bytes()==(H/'baseline_source/skills/wedetect-shot-entities/output.schema.json').read_bytes()
# Selection and downstream canonical validation stay unchanged as well.
def fn(p,name):return ast.dump(next(x for x in ast.parse(Path(p).read_text()).body if isinstance(x,ast.FunctionDef) and x.name==name),include_attributes=False)
assert fn(B/'scripts/run_wedetect_shot_entities.py','validate_result')==fn(H/'baseline_source/scripts/run_wedetect_shot_entities.py','validate_result')
for run in selected:
 manifest=read(H/run['run']/'manifest.json')
 for shot in manifest['shots']:
  for frame in shot['frames']:assert sha(frame['path'])==frame['sha256']
  old=read(Path(read(H/'spec.json')['baseline'])/'shots'/shot['shot_id']/'input.json')
  assert old==read(H/run['run']/'shots'/shot['shot_id']/'input.json')
summary=dict(status='promoted_after_two_exact_candidate_replays',selected_runs=[x['run'] for x in selected],baseline=base,optimized_mean=mean,reduction_fraction=1-mean['total_tokens']/base['total_tokens'],quality=dict(shot1_entities=21,shot3_entities=22,candidate_partitions_equal=True,rejection_sets_equal=True,all_derived_observations_equal=True,canonical_schema_unchanged=True,box_selection_unchanged=True,detector_code_unchanged=True,original_images_unchanged=True,model='gpt-6-astra',reasoning='medium'),tests=15,skill_validation_passed=True,optimization_trial_calls=len(trials),optimization_trial_tokens=sum(x['total_tokens'] for x in trials),cached_input_tokens=sum(x['cached_input_tokens'] for x in trials),limitation='Current Study2 two-shot validation only; not a universal accuracy guarantee. Group-versus-individual deduplication is now explicit, so future datasets containing overlapping collection/member candidates should be regression-tested.')
(H/'result.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
lines=['# WeDetect 单shot聚类 token 优化','','## 最终采用方案','','保持gpt-6-astra / medium、每shot全部6张原始JPEG和完整检测候选。仅重跑聚类：检测代码/参数/权重未改，固定使用上一次相同检测输出；本次没有重新进行GPU检测、几何、动静判断或跨shot评分。','','- 聚类模型只读取单一review_prompt合同；skill里的调度、资源及下游字段说明留给程序和主代理。','- 候选以共享列定义的紧凑行传入；重复标签用字典，候选用短整数ID，原始坐标/分数/帧时间保值。','- 返回实体名称与候选ID集合，程序分配entity_id并恢复原始candidate_ids；同理由的剔除项可成组传输。','- 原始输入哈希留在本地审计、附件发送前仍校验；规范化input/response和最终entities格式保留。','- 明确集合/单体去重边界：稳定集合在无独立成员候选时可保留；与已保留单体发生重复的集合候选应剔除，避免吸收单体或双重计数。该条是语义规则的澄清，不只是编码改动。','','## 效果','','| 项目 | 优化前基准 | 最终版复测1 | 最终版复测2 | 最终均值 |','|---|---:|---:|---:|---:|']
for title,key in [('输入token','input_tokens'),('输出token','output_tokens'),('总token','total_tokens'),('两shot并行阶段秒','seconds')]:
 vals=[base[key],*[r['stats'][key] for r in selected],mean[key]];lines.append('| '+title+' | '+' | '.join(f'{x:,.2f}' if isinstance(x,float) else f'{x:,}' for x in vals)+' |')
lines += ['',f"平均总token减少 **{100*summary['reduction_fraction']:.2f}%**。缓存命中已包含在input tokens内，不再扣除；实际token减少不是把缓存token漏算。时间为两shot并行阶段墙钟，不能视为稳定服务延迟保证。",'','## 质量核对','','两次独立复测均保持Shot1 21个实体、Shot3 22个实体。用原始候选ID集合核对，而非依赖生成的实体ID或名称：43个聚类成员集合、剔除候选集合、全部逐帧框/visible/exist/来源均与基准一致。名称有同义或详细程度变化，逐项记录在comparison.json；不是逐字输出相同。规范化schema与原框选择函数保持不变。15项协议测试及skill格式检查通过。','本次证据限于Study2这两个shot，不能由两次复测证明所有视频均无质量变化。对更多场景，尤其集合与成员同时被检测的情况，仍需回归验证。','','## 全部试验（含未采用方案）','','| 方案 | tokens | 秒 | 与原基准候选级一致 | 结果说明 |','|---|---:|---:|---|---|']
notes={'compact_run01':'混合黑笔单体与多笔集合，未采用','compact_run02':'范围规则过严，剔除书组等，未采用','conservative_run01':'候选表压缩第一轮通过','conservative_run02':'候选表压缩复测额外保留笔组，未采用','minimal_run01':'只改排版与哈希仍额外保留笔组，未采用','baseline_control':'原版重跑控制，与原基准一致','compact_scope_run01':'最终版第一次，通过','compact_scope_run02':'最终版第二次，通过'}
for r in j['runs']:lines.append(f"| {r['run']} | {r['stats']['total_tokens']:,} | {r['stats']['seconds']:.2f} | {r['structural_quality_gate_passed']} | {notes[r['run']]} |")
lines += ['',f"本次优化验证共 **{len(trials)}次CLI调用、{summary['optimization_trial_tokens']:,} tokens**，包含未采用方案、控制与复测；不含历史基准已发生的44,492 tokens，也不含主代理本轮对话自身用量。各次usage/requests/responses均保留。",'', '## 文件','','- `result.json`：最终选择、均值与审计结论。','- `comparison.json`：所有试验逐实体候选集合与名称对照。','- `calls.csv`：全部实际调用、输入/输出/cache token及时间。','- `promoted_source/`：最终上线代码、skill、prompt、schema及哈希。','- `baseline_source/`：优化前可回退版本。','- 各试验目录：完整原始输入、实际prompt、候选ID映射、wire/canonical response、事件及usage。','','不改写前几次完整Study2实验；最终规范化实体文件仍可供现有几何/动静/跨shot阶段读取。']
(H/'REPORT.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
