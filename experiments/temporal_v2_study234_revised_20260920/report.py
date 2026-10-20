"""Fresh revised pipeline audit; explicit anomaly fractions, no spatial coverage."""
import csv,json,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent
read=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):Path(p).write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')
def fmt(v):return '—' if v is None else f'{v:.2f}'
scores=[];events=[];stages=[];totals=[];audit={};failures=[]
for name in ('study2','study3','study4'):
 c=R/name
 if not (c/'summary.json').exists():failures.append(name+': no summary');continue
 s=read(c/'summary.json')
 if s['status']!='success':failures.append(name+': '+s['status']);continue
 assert s['protocol']=='temporal_v2' and s['alignment_method']=='roma_fps32'
 manifest=read(c/'raw_manifest.json')
 a=dict(images_unchanged=all(sha(f['path'])==f['sha256'] for shot in manifest['shots'] for f in shot['frames']),
        detector_fresh=read(c/'entities/run.json')['detector_mode']=='fresh',
        stages_success=all(z['status']=='success' for z in s['stages']),calls_success=all(z['status']=='success' for z in s['calls']))
 assert all(a.values()),a
 names={};filtered={}
 for sid in ('shot1','shot2','shot3'):
  inp=read(c/'entities/shots'/sid/'input.json');flt=inp['candidate_filter'];excluded=flt['excluded_detections']
  assert flt['policy']=='exclude_floor_coverings_v1'
  assert all(d['name'] not in flt['excluded_labels'] for f in inp['frames'] for d in f['detections'])
  assert len({d['candidate_id'] for d in excluded})==len(excluded)
  count=sum(len(read(c/'entities/detections'/sid/f"frame_{f['frame_id']:06d}/detections.json")['detections']) for f in inp['frames'])
  assert count==len(excluded)+sum(len(f['detections']) for f in inp['frames'])
  retained={d['candidate_id'] for f in inp['frames'] for d in f['detections']}
  assert all(set(e['candidate_ids'])<=retained for e in read(c/'entities/shots'/sid/'entities.json')['entities'])
  filtered[sid]=len(excluded)
  for e in read(c/'selected'/f'{sid}_scene.json')['entities']:names[e['entity_id']]=e['name']
 a['excluded_detections']=filtered
 pair=c/'pairs/pair_000';matching=read(pair/'matching.json')
 for g in matching['groups']:names[g['group_id']]=' / '.join(dict.fromkeys(names[x] for x in g['a_ids']+g['b_ids']))
 reg=read(pair/'registration/roma_geometry/registration.json');fit=reg['fits']['all_structures']
 assert fit['fit_rows']==min(32,reg['sampling']['candidate_count']) and fit['all_selected_pairs_used'] and fit['points_removed']==0
 assert fit['point_weights']=='uniform_1' and fit['distance_power']==1
 a['registration']={k:fit[k] for k in ['fit_rows','point_weights','distance_power','points_removed','scale','yaw_deg']}
 boundary=s['boundaries']['pair_000']
 assert boundary['spatial_review_protocol']=='flow1_original_prompts_endpoint_targets_all_keyframe_evidence_v1'
 for prov in (pair/'boundary/restored_prompts').glob('*.provenance.json'):
  record=read(prov);actual=prov.with_name(prov.name.replace('.provenance.json','.txt'))
  assert sha(actual)==record['full_sha256'] and sha(record['original_prompt'])==record['original_sha256']
 assert boundary['target_frames']==[dict(shot_id='shot1',frame_id=manifest['shots'][0]['frames'][-1]['frame_id']),dict(shot_id='shot3',frame_id=manifest['shots'][2]['frames'][0]['frame_id'])]
 assert set(s['within_shots'])=={'shot1','shot2','shot3'}
 for scope,d in list(s['within_shots'].items())+[('shot1_tail_to_shot3_head',boundary)]:
  p=d['presence']['summary'];z=d['spatial']['summary']
  assert z['scoring_protocol']=='confirmed_anomaly_fraction_v1' and 'coverage' not in z
  assert z['total_pairs']==len(d['spatial']['units'])
  k=sum(u['status']=='conflict' for u in d['spatial']['units']);assert k==z['confirmed_conflict_pairs']
  if z['total_pairs']:assert abs(z['score']-100*(1-k/z['total_pairs']))<1e-9
  scores.append(dict(study=name,scope=scope,presence_score=p['score'],spatial_score=z['score'],confirmed_conflict_pairs=k,total_pairs=z['total_pairs'],anomaly_ratio=z['anomaly_ratio'],presence_C=p['C'],presence_K=p['K'],presence_U=p['U'],presence_E=p['E']))
  for e in d['events']:
   review=e.get('review',{});verify=e.get('verification',{});pr=verify.get('prompt_motion_review',{})
   ids=e.get('entity_ids',e.get('endpoint_groups',[e.get('group_id','')]))
   events.append(dict(study=name,scope=scope,event_id=e['event_id'],kind=e['kind'],status=e['status'],entities=' | '.join(names.get(x,x) for x in ids),cosine=e.get('cosine'),gate=e['gate_reason'],reason=review.get('reason',verify.get('reason','')),prompt_reason=review.get('prompt_explanation',pr.get('causal_explanation_of_observed_relation_change',''))))
 for z in s['stages']:stages.append(dict(study=name,stage=z['stage'],seconds=z['seconds'],tokens=z['total_tokens']))
 assert sum(z['total_tokens'] for z in s['calls'])==s['total_tokens']
 assert sum(z['total_tokens'] for z in s['stages'])==s['total_tokens']
 a['token_balance']=True;audit[name]=a
 totals.append(dict(study=name,seconds=s['elapsed_seconds'],tokens=s['total_tokens'],calls=len(s['calls']),entity_counts=[len(read(c/'selected'/f'{sid}_scene.json')['entities']) for sid in ('shot1','shot2','shot3')]))
for filename,rows in [('scores',scores),('events',events),('stages',stages)]:
 if rows:
  with (R/(filename+'.csv')).open('w') as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
audit['source_hashes_unchanged']=all(sha(p)==h for p,h in read(R/'source_hashes.json').items())
save(R/'audit.json',audit);save(R/'comparison.json',dict(totals=totals,scores=scores,events=events,failures=failures))
md=['# Study2 / Study3 / Study4 — revised temporal_v2 fresh runs','',
'全新 WeDetect、聚类、逐帧几何、镜头内评估、身份/配准和端点评估。地毯类过滤；原版空间 prompt/逐轴复核；空间分按确认异常对数/总实体对数计算。RoMA+FPS32，Astra/medium。','',
'| 测例 | 秒 | Token | 调用 | Shot1/2/3 实体数 |','|---|---:|---:|---:|---|']
for t in totals:md.append(f"| {t['study']} | {t['seconds']:.2f} | {t['tokens']:,} | {t['calls']} | {' / '.join(map(str,t['entity_counts']))} |")
md+=['','| 测例 | 范围 | 存在性分 | 空间分 | 确认异常对 / 总对数 |','|---|---|---:|---:|---|']
for r in scores:md.append(f"| {r['study']} | {r['scope']} | {fmt(r['presence_score'])} | {fmt(r['spatial_score'])} | {r['confirmed_conflict_pairs']} / {r['total_pairs']} |")
md+=['','## 确认异常','']
for e in events:
 if e['status']=='conflict':md.append(f"- {e['study']} / {e['scope']} / {e['kind']}: {e['entities']} — {e['reason']}")
md+=['','## 执行与审计','',f'完成 {len(totals)}/3；总调用 {sum(t["calls"] for t in totals)}；总 token {sum(t["tokens"] for t in totals):,}。',
'原图哈希、过滤候选记账、等权无剔除配准、评分分母与异常数、阶段与调用 token 对账见 audit.json。每阶段耗时/token 见 stages.csv，全部事件见 events.csv。无外观评分和合成总分。']
if failures:md+=['','## 未完成',*failures]
(R/'REPORT.md').write_text('\n'.join(md)+'\n')
print(json.dumps(dict(totals=totals,failures=failures),ensure_ascii=False,indent=2))

with (R/'REPORT.md').open('a') as f: f.write('\n\n执行补充：首次节点预检发现设备被其他任务占用，未启动推理，记录见 preflight_attempt1。正式运行在已有分配200798/node209。Study3在boxer_shot2启动前因上一阶段短暂残留146MB显存被保护拦下；设备释放并复查后仅续跑未完成阶段，已完成的新推理未重复执行。首次记录见study3/guard_stop_attempt1和initial_coordinator_status.json；最终三组均成功，见status.json。Study3耗时包含保护退出及恢复间隔。\n')

with (R/'REPORT.md').open('a') as f: f.write('\n\n## API 等价费用估算（2026-09-20）\n\n按 GPT-6 Astra 标准 API 公开单价：普通输入 $10/M、缓存输入 $1/M、输出 $50/M。各请求输入均低于272K（最高223224），缓存写入为0；缓存读取按优惠价计算。服务等级与实际账单未记录，以下为标准API等价估算，不是实际扣费。\n\n| 测例 | Tokens | 估算 USD |\n|---|---:|---:|\n| study2 | 1,366,323 | $16.16 |\n| study3 | 1,359,719 | $16.35 |\n| study4 | 1,156,967 | $14.49 |\n| 合计 | 3,883,009 | $47.00 |\n\n价格来源：https://developers.openai.com/api/docs/models/gpt-6-astra 。逐项记账见 api_cost_estimate.json。仅含本次45个流水线模型调用，不含GPU计算或其他对话。\n')
