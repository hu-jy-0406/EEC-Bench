"""Audit this stopped model-replacement experiment; never fabricate final scores."""
import collections,csv,itertools,json,sys
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parent;B=R.parents[1];C=R/'run01';sys.path.insert(0,str(B/'scripts'))
from run_gs_integrated import read,save,sha,summarize
import run_wedetect_shot_entities as detector
from review_aligned_entity_identities import SCHEMA,validate
import jsonschema
runtime=read(C/'pipeline_runtime.json');assert runtime['status']=='failed'
# Distinguish a successful transport/JSON response from a failed semantic stage.
d=C/'calls/identity_review';status=read(d/'status.json');status.update(transport_status='success',status='failed',semantic_validation='incomplete_initial_group_reviews_20_of_29');save(d/'status.json',status)
summary=summarize(C,runtime)
shots=read(C/'entities/manifest.json')['shots'];indexed={s['shot_id']:s for s in shots};dets=detector.load_detections(C/'entities/detections',shots);counts={};boxes=0
for shot in shots:
 sid=shot['shot_id'];folder=C/'entities/shots'/sid;entities=read(folder/'entities.json')
 assert detector.validate_result(read(folder/'response.json'),detector.make_payload(shot,dets))==entities
 boxes+=sum(o['box_xyxy'] is not None for e in entities['entities'] for o in e['observations'])
 counts[sid]={'entities':len(entities['entities'])}
 for frame in shot['frames']:assert sha(frame['path'])==frame['sha256']
 if sid in ['shot1','shot3']:
  graph=read(C/'selected'/f'{sid}_scene.json');counts[sid].update({k:sum(e['motion_status']==k for e in graph['entities']) for k in ['static','moving','unknown']})
expected=[]
for index,(a,b) in enumerate(itertools.product(indexed['shot1']['frames'],indexed['shot3']['frames'])):
 name=f"{a['frame_id']:03d}_{b['frame_id']:03d}";expected.append(name+'.npz');m=read(C/'registration/roma'/(name+'.json'))
 assert m['index']==index and m['matches']==5000 and m['input_hashes']==[a['sha256'],b['sha256']]
 with np.load(C/'registration/roma'/(name+'.npz')) as z:assert z['uvA'].shape==z['uvB'].shape==(5000,2)
assert {p.name for p in (C/'registration/roma').glob('*.npz')}==set(expected)
for p,h in read(R/'same_run_pair_checkpoint.json')['hashes'].items():assert sha(p)==h
for p,h in read(C/'provenance.json')['source_hashes'].items():
 assert sha(p)==h,(p,'live source changed')
 assert sha(C/'code_snapshot'/Path(p).relative_to(B))==h
attempts=[]
for name in ['identity_review_attempt1','identity_review']:
 folder=C/'calls'/name;response=read(folder/'response.json');payload=read(folder/'input.json');jsonschema.validate(response,SCHEMA)
 old={g['group_id'] for g in payload['initial_matching']['groups']};reviews=response['initial_group_reviews'];ids=[r['initial_group_id'] for r in reviews]
 for side,shot in zip(['a','b'],payload['shots']):
  assigned=[e for g in response['matching']['groups'] for e in g[side+'_ids']]
  assert len(assigned)==len(set(assigned)) and set(assigned)=={e['entity_id'] for e in shot['entities']}
 try:validate(response,payload)
 except AssertionError:pass
 else:raise AssertionError('Expected the original semantic validator to reject this attempt')
 singles={g['group_id'] for g in response['matching']['groups'] if g['identity']=='unmatched'};checked={r['group_id'] for r in response['noncommon_checks']}
 attempts.append(dict(call=name,required_initial_groups=len(old),reviewed_initial_groups=len(ids),missing_initial_groups=sorted(old-set(ids)),required_noncommon_groups=len(singles),reviewed_noncommon_groups=len(checked),missing_noncommon_groups=sorted(singles-checked),final_groups=len(response['matching']['groups']),actions={r['initial_group_id']:r['action'] for r in reviews},all_40_entities_preserved=True))
requests=list(C.glob('calls/*/request.json'))+list(C.glob('entities/shots/*/request.json'))
for path in requests:
 req=read(path);assert req['provider']=='google-gemini-openai-compatible' and req['model']=='gemini-3.5-flash' and req['reasoning']=='medium' and req['stateless'] and not req['tools_enabled'] and 'command' not in req
 assert req['prompt_sha256']==sha(path.parent/'prompt.txt')
 hashes=[x['sha256'] for x in req['attachments']]
 if 'images' in req:assert hashes==[x['sha256'] for x in req['images']]
 name=path.parent.name;sid=name.removeprefix('motion_')
 if sid in indexed:assert hashes==[x['sha256'] for x in indexed[sid]['frames']]
 raw=read(path.parent/'gemini_response.json');assert raw['model']=='gemini-3.5-flash' and raw['choices'][0]['finish_reason']=='stop'
a=read(C/'calls/identity_review_attempt1/request.json');b=read(C/'calls/identity_review/request.json');assert a['request_body_sha256']==b['request_body_sha256']
usage=[read(p) for p in C.glob('**/gemini_usage.json')];totals={k:sum(u['normalized'][k] for u in usage) for k in ['input_tokens','output_tokens','cached_input_tokens']};total=totals['input_tokens']+totals['output_tokens'];assert total==summary['total_tokens']
price=((totals['input_tokens']-totals['cached_input_tokens'])*1.5+totals['cached_input_tokens']*.15+totals['output_tokens']*9)/1e6
assert not (C/'presence.json').exists() and not (C/'spatial.json').exists()
result=dict(status='stopped_on_model_semantic_validation_failure',model='gemini-3.5-flash',reasoning='medium',device='cpu',model_calls=len(requests),api_and_json_successes=len(requests),semantic_identity_failures=2,attempts=attempts,entity_counts=counts,wall_seconds=runtime['seconds'],total_tokens=total,**totals,standard_api_price_estimate_usd=price,presence_score=None,spatial_score=None,last_completed_stage='registration',inference_reuse=False,all_36_raw_pairs_completed=True,score_comparison_with_astra_not_available=True)
save(R/'result.json',result)
save(R/'audit.json',dict(status='passed_for_stopped_run_not_successful_evaluation',all_original_images_unchanged=18,exact_candidate_boxes=boxes,all_36_pairs_complete=True,same_run_checkpoints_unchanged=True,source_snapshots_and_live_sources_unchanged=True,all_calls_gemini_stateless_medium=True,per_shot_image_isolation=True,identical_request_retry_hash=True,original_semantic_validator_reproduced_both_failures=True,all_usage_reconciled=True,no_downstream_scores_fabricated=True,codex_executions=0))
lines=['# Study2：Gemini 3.5 Flash 完整 CPU pipeline 测试','', '**结论：API 可用，新分支已创建并实跑；本次在配准后身份复核被原协议校验截停，没有有效的最终存在性/空间分数。**','',
'## 实际完成与失败','', '18 张原始 JPEG 从 WeDetect 重新运行：三镜头独立聚类、Shot1/Shot3 GeoCalib、Pi3X、Boxer、隔离动静判断、全实体初始身份匹配、全部36对RoMa匹配和数值配准均完成。Shot2只检测聚类。所有模型调用均为Gemini3.5Flash/medium，未执行Codex CLI。','',
'|配准后身份复核|初始组复核覆盖|非共同组检查覆盖|原完整性校验|','|---|---:|---:|---|']
for a in attempts:lines.append(f"|{a['call']}|{a['reviewed_initial_groups']}/{a['required_initial_groups']}|{a['reviewed_noncommon_groups']}/{a['required_noncommon_groups']}|失败|")
lines += ['', '两次API响应均完成且JSON schema有效，40个实体均保留；缺失的是协议强制要求的逐组审查证据。第二次为完全相同请求的独立重试，完整请求哈希相同。没有补写遗漏项、修改框或放宽评分门槛。',
'身份决定也不稳定：第一次把挂画、小桌、桌上植物三组拆分，第二次全部保留匹配。这些均为未通过完整审查的原始响应，不能当作最终身份结论。','',
'## 用量与耗时','',f"共{len(requests)}次Gemini调用（包含失败复核及一次重试），输入{totals['input_tokens']:,}、输出含推理{totals['output_tokens']:,}，合计 **{total:,} tokens**。缓存输入{totals['cached_input_tokens']:,}已包含在输入中。",
f"按[官方标准API价格](https://ai.google.dev/gemini-api/docs/pricing)估算 **${price:.4f}**，不是账户实际账单；不含独立连接探针、开发和审计。价格：未缓存输入$1.50/M、缓存输入$0.15/M、输出含推理$9/M。",
f"本次运行实际墙钟 **{runtime['seconds']:.2f}秒（{runtime['seconds']/60:.2f}分钟）**，包含CPU重调度、四worker内存保护停止、模型失败及人工处理/重试间隔，不能作为理想生产延迟。",'',
'开始四线程串行RoMa，保留本次已完成6对后尝试四个worker；合计RSS达到32.44GiB时触发24GiB保护并停止。随后两个worker各四线程完成剩余30对，峰值20.07GiB。全部使用已分配节点306的CPU；未申请或使用GPU。原36对、每对5000点、precise设置和逐对种子均保留；无历史推理复用。','',
'## 与历史Astra结果的关系','', '本次聚类Shot1/2/3实体数20/7/20，Shot1/3静态数18/19。候选ID、框、类别、原图与历史Astra完全相同，置信度只有最大5.31e-6浮点差异。Gemini拒绝Shot1黑笔和Shot3两个花盆；Shot1仍把花盆单列，出现跨镜头粒度差异。详细候选集合比较见frontend_comparison.json。',
'历史Astra完整运行存在性86.6667、空间96.4286，确认台灯消失、纸巾新增和杯子—笔筒关系冲突；本次没有完成B和空间阶段，不能比较这些缺陷的召回率或最终分数。历史还使用GPU几何及旧静态身份总体，不能视为纯模型受控消融。','',
'**目前不宜直接替换默认Astra判断器。** 后续可单独测试：将已有逐组完整性要求进一步编码为Gemini结构化输出约束；该适配尚未实施，也未据此重跑本次测试。原pipeline及默认配置保持不变。','',
'## 产物与审计','', '入口：EECBench/scripts/run_gs_integrated_gemini.py；CPU入口：EECBench/scripts/run_gs_integrated_gemini_cpu.py；使用说明：EECBench/docs/gs-integrated-gemini.md。',
'12项适配器与原集成测试通过。停跑审计通过18原图、原候选框、36图像对、同次检查点、源码快照、单镜头图像隔离、全部Gemini请求、相同请求重试和完整token对账；原语义校验的两次失败已独立复现。',
'详见result.json、audit.json、run01/calls.csv、run01/stages.csv及calls/identity_review_attempt1、calls/identity_review原始响应。', '', '|阶段|状态|秒|tokens|','|---|---|---:|---:|']
for row in summary['stages']:lines.append(f"|{row['stage']}|{row['status']}|{row.get('seconds',0):.2f}|{row.get('total_tokens',0):,}|")
(R/'REPORT.md').write_text('\n'.join(lines)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2))
