"""Read completed fresh temporal runs, preserve scores and expose uncertainty."""
import csv,json,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent
B=R.parents[1]
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):Path(p).write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')
def fmt(v):return '—' if v is None else f'{v:.2f}'
rows=[];events=[];stages=[];totals=[];audit={};entity_rows=[]
for name in ('study2','study3','study4'):
 c=R/name; s=read(c/'summary.json');assert s['status']=='success',name
 assert s['protocol']=='temporal_v2' and s['alignment_method']=='roma_fps32'
 assert set(s['within_shots'])=={'shot1','shot2','shot3'}
 assert len(s['boundaries'])==1
 manifest=read(c/'raw_manifest.json')
 audit[name]={'images_unchanged':all(sha(f['path'])==f['sha256'] for shot in manifest['shots'] for f in shot['frames']),
              'detector_mode':read(c/'entities/run.json')['detector_mode'],
              'all_stages_success':all(z['status']=='success' for z in s['stages']),
              'all_calls_success':all(z['status']=='success' for z in s['calls'])}
 assert all(audit[name][k] for k in ('images_unchanged','all_stages_success','all_calls_success'))
 assert audit[name]['detector_mode']=='fresh'
 names={}
 for sid in ('shot1','shot2','shot3'):
  g=read(c/'selected'/f'{sid}_scene.json')
  for e in g['entities']:
   names[e['entity_id']]=e['name']
   entity_rows.append(dict(study=name,shot=sid,entity_id=e['entity_id'],name=e['name'],expected=e['expected_motion_status'],observed=e['observed_motion_status'],anchor_candidate=e['anchor_observed_static']))
 pair=c/'pairs/pair_000';matching=read(pair/'matching.json')
 reg=read(pair/'registration/roma_geometry/registration.json');fit=reg['fits']['all_structures']
 assert fit['fit_rows']==32 and fit['all_selected_pairs_used'] and fit['points_removed']==0
 assert fit['point_weights']=='uniform_1' and fit['distance_power']==1
 audit[name]['registration']={k:fit[k] for k in ('fit_rows','all_selected_pairs_used','points_removed','point_weights','distance_power')}
 audit[name]['registration'].update(selection_seconds=reg['selection_seconds'],optimization_seconds=reg['optimization_seconds'])
 for g in matching['groups']:
  names[g['group_id']]=' / '.join(dict.fromkeys(names[x] for x in g['a_ids']+g['b_ids']))
 sections=list(s['within_shots'].items())+[(k,v) for k,v in s['boundaries'].items()]
 for scope,d in sections:
  label=scope if scope.startswith('shot') else 'shot1_tail_to_shot3_head'
  for metric in ('presence','spatial'):
   z=d[metric]['summary'];rows.append(dict(study=name,scope=label,metric=metric,**{k:z[k] for k in ('score','coverage','C','K','U','E','N')}))
  for e in d['events']:
   ids=e.get('entity_ids',e.get('endpoint_groups',[e.get('group_id','')]))
   review=e['review']
   events.append(dict(study=name,scope=label,event_id=e['event_id'],kind=e['kind'],status=e['status'],entities=' | '.join(names.get(x,x) for x in ids),target_frames=json.dumps(e['target_frames']),cosine=e.get('cosine'),cause=review['cause'],gate=e['gate_reason'],explanation=review.get('explanation',review.get('reason','')),prompt_explanation=review['prompt_explanation']))
 boundary=s['boundaries']['pair_000']
 assert boundary['target_frames']==[dict(shot_id='shot1',frame_id=manifest['shots'][0]['frames'][-1]['frame_id']),dict(shot_id='shot3',frame_id=manifest['shots'][2]['frames'][0]['frame_id'])]
 for row in s['stages']:stages.append(dict(study=name,stage=row['stage'],seconds=row['seconds'],tokens=row['total_tokens']))
 totals.append(dict(study=name,seconds=s['elapsed_seconds'],tokens=s['total_tokens'],calls=len(s['calls']),entities=[len(read(c/'selected'/f'{sid}_scene.json')['entities']) for sid in ('shot1','shot2','shot3')]))
for filename,data in [('scores',rows),('events',events),('stages',stages),('entities',entity_rows)]:
 with (R/(filename+'.csv')).open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
save(R/'audit.json',audit);save(R/'comparison.json',dict(totals=totals,scores=rows,events=events))
md=['# Study2 / Study3 / Study4 — temporal_v2 完整实验','',
'三个测例均从新的 WeDetect 检测开始，独立完成全部三个 shot 的推理；使用 roma_fps32 优化配准。仅复用原始输入关键帧、正常叙事 prompt 和预训练权重，不复用历史检测、几何、身份或配准结果。',
'','Study4 对应原始目录 `experiments/study3-concise-mtd-local/`。每个 shot 内比较全部关键帧组合；跨 shot 只评估同场景 shot1 尾帧和 shot3 首帧。Shot2 是独立场景，仍做 shot 内评估。',
'','| 测例 | 完整耗时（秒） | Token | API 调用 | 各 shot 实体数 |','|---|---:|---:|---:|---|']
for t in totals:md.append(f"| {t['study']} | {t['seconds']:.2f} | {t['tokens']:,} | {t['calls']} | {' / '.join(map(str,t['entities']))} |")
md+=['','耗时包含 WeDetect、RoMA、几何和 API；单测例内部有阶段重叠，三个测例并行，不能用阶段耗时之和替代端到端耗时。Token 为输入（含缓存）加输出，详见每个测例的 calls.csv。',
'','| 测例 | 范围 | 存在性 | 空间 | 存在性 C/K/U/E | 空间 C/K/U/E |','|---|---|---:|---:|---|---|']
for i in range(0,len(rows),2):
 p,q=rows[i:i+2];counts=lambda z:'/'.join(str(z[k]) for k in ('C','K','U','E'))
 md.append(f"| {p['study']} | {p['scope']} | {fmt(p['score'])} | {fmt(q['score'])} | {counts(p)} | {counts(q)} |")
md+=['','C=确认兼容，K=确认冲突，U=不确定，E=合理运动/遮挡等豁免。沿用原评分公式；空间 100 分可能伴随低覆盖率，不代表所有关系均已确认一致。不存在虚构的跨范围总分。',
'','## 确认冲突','']
conflicts=[e for e in events if e['status']=='conflict']
if not conflicts:md.append('本次未确认冲突；仍需结合不确定项和覆盖率解释。')
for e in conflicts:md.append(f"- {e['study']} / {e['scope']} / {e['kind']}: {e['entities']}; {e['target_frames']}; {e['prompt_explanation']}")
md+=['','## 每阶段耗时与 token','', '| 测例 | 阶段 | 秒 | Token |','|---|---|---:|---:|']
for z in stages:md.append(f"| {z['study']} | {z['stage']} | {z['seconds']:.2f} | {z['tokens']:,} |")
md+=['','逐事件记录见 events.csv，含确认冲突、不确定、兼容和豁免；完整 witnesses 和判断理由保存在各测例 within/*/results.json 与 pairs/pair_000/boundary/results.json。','']
(R/'REPORT.md').write_text('\n'.join(md))
print(json.dumps(totals,indent=2))
