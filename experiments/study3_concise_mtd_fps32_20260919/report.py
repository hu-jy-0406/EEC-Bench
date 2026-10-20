"""Read-only per-stage audit and standard API-equivalent cost report."""
import json,csv,importlib.util,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent;B=ROOT.parents[1];CASE=ROOT/'run'
spec=importlib.util.spec_from_file_location('baseline_audit',B/'experiments/alignment_full_four_20260919/report.py');auditmod=importlib.util.module_from_spec(spec);spec.loader.exec_module(auditmod)
def load(p):return json.loads(p.read_text())
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def writecsv(p,rows):
 with p.open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
 result,audit,calls,stages=auditmod.read_case(ROOT,'run')
 assert result['final_scores_available'],'Only report final after completed pipeline'
 prices=load(ROOT/'pricing.json');total_cost=0
 for call in calls:
  status=load(CASE/call['call']/'status.json');usages=status.get('usage',status.get('known_usage',[]))
  if isinstance(usages,dict):usages=[usages]
  cost=0;long=0;writes=0;missing_writes=0
  for u in usages:
   i=u.get('input_tokens',0);o=u.get('output_tokens',0);c=u.get('cached_input_tokens',0)
   w=u.get('cache_write_input_tokens',0);writes+=w;missing_writes+=int('cache_write_input_tokens' not in u)
   assert 0<=c+w<=i
   islong=i>272000;long+=int(islong)
   cost+=((i-c-w)*10*(2 if islong else 1)+c*(2 if islong else 1)+w*12.5*(2 if islong else 1)+o*50*(1.5 if islong else 1))/1e6
  call.update(standard_api_equivalent_usd=cost,long_context_turns=long,cache_write_input_tokens=writes,missing_cache_write_usage_turns=missing_writes)
  total_cost+=cost
 summary=load(CASE/'summary.json');front=load(CASE/'entities/run.json')
 prefixes={'detection_and_clustering':['entities/shots/'],'motion_and_fusion':['calls/motion_'],'initial_identity':['calls/matching'],'registration':['calls/registration_direct'],'aligned_identity_review':['calls/identity_review'],'presence':['calls/presence_1'],'spatial':['calls/observe_','calls/verify_relations']}
 labels={'detection_and_clustering':'WeDetect检测＋各shot独立聚类','geocalib':'GeoCalib标定','prepare_shot_inputs':'准备几何输入','pi3x_shot1':'Shot1 Pi3X重建','boxer_shot1':'Shot1 3D实体框','pi3x_shot3':'Shot3 Pi3X重建','boxer_shot3':'Shot3 3D实体框','motion_and_fusion':'独立动静判断＋场景融合','initial_identity':'全实体初始身份匹配＋anchor选择','roma_matches':'RoMA原始匹配（36帧对）','lift_correspondences':'anchor筛选＋提升3D点对','registration':'FPS32＋配准优化','aligned_identity_review':'配准后全实体身份复核','presence':'实体存在性判断','spatial':'空间关系计算＋复核'}
 rows=[]
 for s in stages:
  selected=[c for c in calls if any(c['call'].startswith(pre) for pre in prefixes.get(s['stage'],[]))]
  row=dict(stage=s['stage'],label=labels.get(s['stage'],s['stage']),seconds=s['seconds'],input_tokens=sum(c['input_tokens'] for c in selected),cached_input_tokens=sum(c['cached_input_tokens'] for c in selected),output_tokens=sum(c['output_tokens'] for c in selected),total_tokens=sum(c['total_tokens'] for c in selected),standard_api_equivalent_usd=sum(c['standard_api_equivalent_usd'] for c in selected));rows.append(row)
 assert sum(r['total_tokens'] for r in rows)==result['total_tokens']
 assert abs(sum(r['standard_api_equivalent_usd'] for r in rows)-total_cost)<1e-9
 audit['checks']['cost_stage_totals_equal_call_totals']=True
 prov=load(ROOT/'input_provenance.json')
 audit['checks']['source_videos_and_prompts_unchanged']=all(hashlib.sha256(Path(p['path']).read_bytes()).hexdigest()==p['sha256'] for p in prov['videos']+prov['prompts'])
 if not audit['checks']['source_videos_and_prompts_unchanged']:audit['status']='failed'
 result.update(standard_api_equivalent_usd=total_cost,pricing=prices,stage_costs=rows,frontend_timing=summary['frontend_timing'],input_preparation_seconds=prov['preparation_seconds'])
 save(ROOT/'results.json',result);save(ROOT/'audit.json',audit);writecsv(ROOT/'calls_with_cost.csv',calls);writecsv(ROOT/'stages_with_cost.csv',rows)
 def fmt(x):return '—' if x is None else f'{x:.4f}'
 lines=['# study3-concise-mtd-local：固定 FPS32 完整评测','',f"状态：{result['status']}；审计：{audit['status']}。配准 roma_fps32，运行配置 safe_spatial_medium，模型 gpt-6-astra / medium。",'',f"存在性 **{fmt(result['presence_score'])}**；空间一致性 **{fmt(result['spatial_score'])}**。",f"Pipeline 墙钟 **{result['elapsed_seconds']:.2f} 秒**，总 token **{result['total_tokens']:,}**，标准 API 等价费用 **${total_cost:.6f}**。",'', '## 逐阶段','', '|阶段|秒|输入token（含缓存）|其中缓存|输出token|总token|API等价美元|','|---|---:|---:|---:|---:|---:|---:|']
 for r in rows:lines.append(f"|{r['label']}|{r['seconds']:.2f}|{r['input_tokens']:,}|{r['cached_input_tokens']:,}|{r['output_tokens']:,}|{r['total_tokens']:,}|${r['standard_api_equivalent_usd']:.6f}|")
 lines+=['', 'RoMA 与动静/初始身份阶段部分重叠，逐阶段秒数之和不是墙钟。检测与聚类阶段内部也有并行。输入抽帧单独耗时 '+f"{prov['preparation_seconds']:.2f} 秒。",'', '## 细分','',f"检测/准备：{summary['frontend_timing'].get('detection_and_preparation_seconds',0):.2f} 秒；独立聚类墙钟：{summary['frontend_timing'].get('clustering_wall_seconds',0):.2f} 秒。",f"FPS选择：{result['fps_selection_seconds']:.6f} 秒；优化求解：{result['optimization_seconds']:.6f} 秒（配准阶段还包含加载、诊断和写出）。",'', '|调用|秒|输入|缓存输入|输出|总token|美元|','|---|---:|---:|---:|---:|---:|---:|']
 for c in calls:lines.append(f"|{c['call']}|{c['seconds']:.2f}|{c['input_tokens']:,}|{c['cached_input_tokens']:,}|{c['output_tokens']:,}|{c['total_tokens']:,}|${c['standard_api_equivalent_usd']:.6f}|")
 lines+=['','## 实体与判定','', '实体数/动静：`'+json.dumps(result['population'],ensure_ascii=False)+'`。','身份组：`'+json.dumps(result['identity_groups'],ensure_ascii=False)+'`。']
 for key,label in [('presence','存在性'),('spatial','空间')]:
  lines+=['',label+'计数：`'+json.dumps(result[key],ensure_ascii=False)+'`。',label+'确认冲突：']
  if not result['defects'][key]:lines.append('- 无。')
  for d in result['defects'][key]:lines.append('- '+d['label']+'：'+str(d.get('reason','')))
 lines+=['','## 输入与费用口径','', '输入为目录中三个实际视频，各取六帧覆盖首尾、保留852×480分辨率（JPEG95）；不使用生成参考PNG。Shot1/3客厅比较，Shot2花园仅检测聚类。全部推理新跑；原始视频和prompt、源码哈希已记录。','', '正常故事证据包含未经改写的global_prompt.md与各shot/prompt.txt。它明确要求镜头外交换杯子位置、改变短杯内容；不能把这些prompt允许的变化自动作为冲突。Appearance和独立prompt一致性分数未计算。动静身份组仍参与全实体匹配，但当前存在性/空间评分仅使用静止投影。','', '单价按[OpenAI官方Astra文档](https://developers.openai.com/api/docs/models/gpt-6-astra)（2026-09-19核对）：每百万token标准输入$10、缓存输入$1、输出$50；单请求输入>272K时分别$20/$2/$75。按逐次usage计算，缓存输入包含在输入内不重复计数。缓存写入按报告的cache_write_input_tokens以输入单价1.25倍计算，包含在总输入内；缺失字段按0计并在calls表记录。本表按实际报告usage折算标准API等价费用，不是实际CLI账单，不含GPU/CPU资源费或本任务主助手的对话token。','', '高分不等于所有实体/关系已确认一致：保留C/K/U/E与coverage，unknown不扣分且进入分母。审计验证文件、原图、阶段隔离、总体守恒和数值一致性，不是人工真值准确率认证。']
 (ROOT/'REPORT.md').write_text('\n'.join(lines)+'\n')
 print(json.dumps({k:result[k] for k in ['presence_score','spatial_score','elapsed_seconds','total_tokens','standard_api_equivalent_usd']},indent=2));print('audit',audit['status'])
if __name__=='__main__':main()
