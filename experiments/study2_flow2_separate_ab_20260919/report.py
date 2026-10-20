import json,csv,hashlib
from pathlib import Path
from collections import Counter
H=Path(__file__).resolve().parent;R=H.parent/'study2_identity_frozen_replay_20260919';OLD=H.parent/'study2_full_fresh_20260918/study2'
read=lambda p:json.loads(p.read_text())
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def metrics(p):
 s=read(p/'status.json');assert s['status']=='success' and len(s['usage'])==1;u=s['usage'][0]
 return dict(seconds=s['seconds'],input_tokens=u['input_tokens'],output_tokens=u['output_tokens'],cached_input_tokens=u.get('cached_input_tokens',0),total_tokens=u['input_tokens']+u['output_tokens'])
def compact_group(g):return dict(identity=g['identity'],members=sorted(g['a_ids']+g['b_ids']),reason=g['identity_evidence'],group_id=g['group_id'])
def pairlabel(gs,a,b):
 ga=next(g for g in gs if a in g['a_ids']);gb=next(g for g in gs if b in g['b_ids'])
 if ga is gb:return dict(matched='同一实例',ambiguous='身份未知',scope_mismatch='范围不一致').get(ga['identity'],ga['identity'])
 if ga['identity']==gb['identity']=='unmatched':return '两个不同实例'
 return ga['identity']+' / '+gb['identity']
def main():
 assert read(H/'audit.json')['passed'];run=read(H/'run.json');assert not run['errors'] and run['sources_unchanged']
 manifest=read(H/'frozen_manifest.json')
 for p,h in manifest['sources'].items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h
 match={f:read(H/f/'matching.json') for f in ['flow1','flow2']};pres={f:read(H/f/'presence.json') for f in match}
 for f in match:assert len(pres[f]['groups'])==len(match[f]['groups'])
 payload=read(H/'flow2/identity_review_payload.json');names={e['entity_id']:e['name'] for s in payload['shots'] for e in s['entities']}
 allrows=[]
 for eid,name in names.items():
  row=dict(entity_id=eid,name=name)
  for f,m in match.items():
   g=next(g for g in m['groups'] if eid in g['a_ids']+g['b_ids']);b=next(x for x in pres[f]['groups'] if x['group_id']==g['group_id']);row[f]=dict(A=compact_group(g),B=b)
  row['identity_changed']=(row['flow1']['A']['identity'],row['flow1']['A']['members'])!=(row['flow2']['A']['identity'],row['flow2']['A']['members'])
  row['B_changed']=any(row['flow1']['B'][k]!=row['flow2']['B'][k] for k in ['partition','status','cause','conflict_kind'])
  allrows.append(row)
 targets=[]
 for name,a,b in [('挂画','shot1/e1','shot3/e1'),('小木桌','shot1/e18','shot3/e8'),('桌上盆栽','shot1/e19','shot3/e11')]:
  t=dict(name=name,a_id=a,b_id=b)
  for f,m in match.items():
   relevant=[g for g in m['groups'] if a in g['a_ids'] or b in g['b_ids']];pids={g['group_id'] for g in relevant};t[f]=dict(A=pairlabel(m['groups'],a,b),B=[r for r in pres[f]['groups'] if r['group_id'] in pids])
  targets.append(t)
 calls=[]
 for f in ['flow1','flow2']:
  for stage in ['presence_1','presence_2']:calls.append(dict(flow=f,stage=stage,new_call=True,**metrics(H/f/'calls'/stage)))
 calls.append(dict(flow='flow2',stage='identity',new_call=True,**metrics(H/'flow2/calls/identity')))
 reused=dict(flow='flow1',stage='identity',new_call=False,**metrics(R/'calls/original'))
 costs={}
 for f in ['flow1','flow2']:
  a=reused if f=='flow1' else next(c for c in calls if c['stage']=='identity');bs=[c for c in calls if c['flow']==f and c['stage'].startswith('presence')];bt=read(H/f/'B_timing.json')['seconds']
  costs[f]=dict(A=a,B_tokens=sum(c['total_tokens'] for c in bs),B_wall_seconds=bt,post_registration_tokens=a['total_tokens']+sum(c['total_tokens'] for c in bs),post_registration_stage_seconds=a['seconds']+bt,A_reused=f=='flow1')
 conflicts={f:[dict(group_id=r['group_id'],entities=next(g['a_ids']+g['b_ids'] for g in match[f]['groups'] if g['group_id']==r['group_id']),kind=r['conflict_kind'],reason=r['reason']) for r in pres[f]['groups'] if r['status']=='conflict'] for f in match}
 disagreements={f:[dict(group_id=r['group_id'],raw_statuses=[v['status'] for v in r['reviews']],raw_causes=[v['cause'] for v in r['reviews']],final_status=r['status'],gates=r['evidence_gates_pass']) for r in pres[f]['groups'] if not r['independent_review_agreement'] or not all(r['evidence_gates_pass'])] for f in match}
 result=dict(targets=targets,identity_counts={f:dict(Counter(g['identity'] for g in m['groups'])) for f,m in match.items()},identity_changed_entities=[r['entity_id'] for r in allrows if r['identity_changed']],B_changed_entities=[r['entity_id'] for r in allrows if r['B_changed']],presence={f:p['summary'] for f,p in pres.items()},presence_conflicts=conflicts,B_disagreements=disagreements,calls=calls,reused_call=reused,costs=costs,new_total_tokens=sum(c['total_tokens'] for c in calls),wall_seconds=run['seconds'],all_entities=allrows,audit=read(H/'audit.json'))
 save(H/'comparison.json',result)
 with (H/'calls.csv').open('w') as out:w=csv.DictWriter(out,fieldnames=list(calls[0]));w.writeheader();w.writerows(calls+[reused])
 with (H/'all_entities.csv').open('w') as out:
  fields=['entity_id','name','identity_changed','B_changed']+[f+'_'+k for f in match for k in ['identity','members','A_reason','partition','status','cause','conflict_kind']];w=csv.DictWriter(out,fieldnames=fields);w.writeheader()
  for r in allrows:
   flat={k:r[k] for k in ['entity_id','name','identity_changed','B_changed']}
   for f in match:
    a=r[f]['A'];b=r[f]['B'];flat.update({f+'_identity':a['identity'],f+'_members':';'.join(a['members']),f+'_A_reason':a['reason'],**{f+'_'+k:b[k] for k in ['partition','status','cause','conflict_kind']}})
   w.writerow(flat)
 lines=['# 流程2：配准后独立 A，再独立 B，与流程1比较','','## 实际执行范围','',
 '- 共同基线：Study2 原完整实验的12张原始JPEG、38个静态实体、历史2D/3D框、逐帧相机、投影、配准结果及误差、故事Prompt。不是最新取消补框后的前端。',
 '- 流程1：复用刚完成的固定输入 A 复核结果，再新跑两次独立 B，并按原规则取共识。',
 '- 流程2：复用书桌/暖气片 A′与相同配准；新跑一次独立 A（含 A′复核，不做 B 类别），再新跑两次独立 B，并按原规则取共识。',
 '- B 两组均直接调用原版 Eval.presence：相同代码、提示词、图像和几何、证据门槛、冲突Prompt复核、分歧保留未知规则。区别是各自 A 生成的身份与说明。',
 '- 五次新调用，均 gpt-6-astra / medium，独立全新上下文。原版 A 复核中附带的初步 B 保留为该流程原有输出；流程2 A 严格不产生 B。',
 '- 未重新做配准前 A/A′、检测、几何或关系评分。属于配准后受控比较，不是两条流程完整从头重跑；因此不能据此声称完整端到端开销。',
 '', '## A：身份对应','', '| 实体 | 流程1 | 流程2 |','|---|---|---|']
 for t in targets:lines.append('| '+t['name']+' | '+t['flow1']['A']+' | '+t['flow2']['A']+' |')
 lines+=['',f"两流程有 {len(result['identity_changed_entities'])}/38 个实体的分组或身份状态不同（忽略组ID差异）。",'', '| 流程 | 确认匹配组 | 单侧组 | 未知组 | 范围不一致组 |','|---|---:|---:|---:|---:|']
 for f,c in result['identity_counts'].items():lines.append('| '+f+' | '+' | '.join(str(c.get(k,0)) for k in ['matched','unmatched','ambiguous','scope_mismatch'])+' |')
 lines+=['','## B：类别与存在性评分','', '| 流程 | 分数 | 共现合理 C | 冲突 K | 未知 U | 视角/运动豁免 E |','|---|---:|---:|---:|---:|---:|']
 for f,s in result['presence'].items():lines.append(f"| {f} | {s['score']:.4f} | {s['C']} | {s['K']} | {s['U']} | {s['E']} |")
 lines+=['','分数沿用原口径：100×(1−K/(C+K+U))；豁免不进分母。分母变化会改变分数，不代表缺陷增加或减少。','']
 for f,rows in conflicts.items():
  lines+=['### '+f+' 确认的存在性冲突','']
  for r in rows:lines.append('- '+', '.join(names[e] for e in r['entities'])+'：'+r['kind'])
 lines+=['','### 三组争议实体在 B 中的分类','']
 for t in targets:
  lines+=['- '+t['name']+': '+'；'.join(f+': '+', '.join(r['group_id']+'='+r['status']+'/'+r['cause'] for r in t[f]['B']) for f in match)]
 lines+=['','## 时间和 token','', '| 调用 | 本次新增 | 秒 | 输入 | 输出 | 合计 |','|---|---|---:|---:|---:|---:|']
 for c in [reused]+calls:lines.append(f"| {c['flow']}/{c['stage']} | {'是' if c['new_call'] else '否，复用上次A'} | {c['seconds']:.2f} | {c['input_tokens']:,} | {c['output_tokens']:,} | {c['total_tokens']:,} |")
 lines+=['','| 配准后 A＋B | token 合计 | A耗时＋B阶段墙钟秒 |','|---|---:|---:|']
 for f,c in costs.items():lines.append(f"| {f} | {c['post_registration_tokens']:,} | {c['post_registration_stage_seconds']:.2f} |")
 lines+=['',f"本次实际新增五次调用共 {result['new_total_tokens']:,} tokens，总墙钟 {run['seconds']:.2f} 秒。上表流程1 A成本来自上次实测，未再次消费；A＋B耗时是阶段相加用于范围一致比较，不是流程1此次重新执行的墙钟。缓存输入包含在输入token内，不另加减。",'', '## 身份判断原文','']
 for t in targets:
  lines+=['### '+t['name'],'']
  for f,m in match.items():
   g=next(g for g in m['groups'] if t['a_id'] in g['a_ids']);lines.append('- **'+f+'：** '+g['identity_evidence'])
 lines+=['','## 审计与限制','',
 '8项身份合同测试通过。两组B输入的原图、单shot图、动静态库存、故事及对齐几何逐字段相同；同组两次B输入相同；所有源文件哈希保持不变。最终匹配、逐组B原始票、共识门槛和差异详见 comparison.json；38实体逐项见 all_entities.csv；调用用量见 calls.csv。',
 '',
 '每种方法仍只有少量调用，差异不能直接推广到其他场景。流程2仅调整A/B分离，保留无初始完整配对这一特点；身份提示词和审计结构也与流程1有别。本实验未证明某一单独因素的因果作用。']
 (H/'REPORT.md').write_text('\n'.join(lines)+'\n')
 print(json.dumps({k:v for k,v in result.items() if k not in ['all_entities','targets','presence_conflicts']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
