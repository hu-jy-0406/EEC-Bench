"""Audit and summarize the two fresh judgments without another model call."""
import json,csv,hashlib
from pathlib import Path
from collections import Counter
H=Path(__file__).resolve().parent; E=H.parent
read=lambda p:json.loads(p.read_text())
save=lambda p,x:p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
PATHS={
 'old_historical':E/'study2_full_fresh_20260918/study2/calls/identity_review',
 'old_replay':H/'calls/original',
 'joint_historical':E/'study2_anchor_joint_fresh_20260918/study2/calls/joint_identity_presence',
 'joint_replay':H/'calls/joint'}
LABELS={'old_historical':'原版上次','old_replay':'原版本次','joint_historical':'新版上次（几何不同）','joint_replay':'新版本次（统一几何）'}
TARGETS=[('挂画','shot1/e1','shot3/e1'),('小木桌','shot1/e18','shot3/e8'),('桌上盆栽','shot1/e19','shot3/e11')]
def groupkey(g):return (g['identity'],tuple(sorted(g['a_ids'])),tuple(sorted(g['b_ids'])))
def pair_status(groups,a,b):
 ga=next(g for g in groups if a in g['a_ids']+g['b_ids']);gb=next(g for g in groups if b in g['a_ids']+g['b_ids'])
 if ga is gb:return {'matched':'同一实例','ambiguous':'身份未知','scope_mismatch':'实体范围不一致'}.get(ga['identity'],ga['identity'])
 if ga['identity']==gb['identity']=='unmatched':return '拆为两个实例'
 return f"分组不同（{ga['identity']}/{gb['identity']}）"
def main():
 results={k:read(p/'response.json') for k,p in PATHS.items()}
 groups={k:r['matching']['groups'] for k,r in results.items()}
 inputs={k:read(H/'calls'/k/'input.json') for k in ['original','joint']}
 manifest=read(H/'frozen_manifest.json');run=read(H/'run.json')
 assert not run['errors'] and run['sources_unchanged']
 for p,h in manifest['sources'].items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h
 for key in ['shots','frozen_transform','registration_quality','normal_story_prompt','images']:
  assert inputs['original'][key]==inputs['joint'][key],key
 for stage in ['original','joint']:assert read(H/f'{stage}_validation.json')['passed']
 calls=[]
 for stage in ['original','joint']:
  st=read(H/'calls'/stage/'status.json');assert st['status']=='success'
  usage=st['usage'];assert len(usage)==1
  u=usage[0];calls.append(dict(stage=stage,seconds=st['seconds'],model=st['model'],reasoning=st['reasoning'],input_tokens=u['input_tokens'],output_tokens=u['output_tokens'],cached_input_tokens=u.get('cached_input_tokens',0),total_tokens=u['input_tokens']+u['output_tokens']))
 with (H/'calls.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=list(calls[0]));w.writeheader();w.writerows(calls)
 names={e['entity_id']:e['name'] for s in inputs['original']['shots'] for e in s['entities']}
 rows=[]
 for eid,name in names.items():
  row={'entity_id':eid,'name':name}
  for k,gs in groups.items():
   g=next(g for g in gs if eid in g['a_ids']+g['b_ids']);row[k]=dict(group_id=g['group_id'],identity=g['identity'],members=g['a_ids']+g['b_ids'],reason=g['identity_evidence'])
  rows.append(row)
 changes={}
 for key,l,r in [('old_repeat','old_historical','old_replay'),('joint_repeat_changed_geometry','joint_historical','joint_replay'),('protocols_same_geometry','old_replay','joint_replay')]:
  changes[key]=[x['entity_id'] for x in rows if (x[l]['identity'],set(x[l]['members']))!=(x[r]['identity'],set(x[r]['members']))]
 targets=[dict(name=n,a_id=a,b_id=b,verdicts={k:pair_status(gs,a,b) for k,gs in groups.items()}) for n,a,b in TARGETS]
 counts={k:dict(Counter(g['identity'] for g in gs)) for k,gs in groups.items()}
 presence=read(H/'joint_normalized_presence.json')
 summary=dict(targets=targets,counts=counts,changed_entities=changes,calls=calls,total_tokens=sum(c['total_tokens'] for c in calls),wall_seconds=run['wall_seconds'],all_entities=rows,joint_presence_counts=dict(Counter(r['status'] for r in presence)),joint_presence_conflicts=[r for r in presence if r['status']=='conflict'],audit=dict(same_geometry=True,same_original_frames=True,same_story=True,same_registration=True,source_hashes_unchanged=True,contract_validations_passed=True,all_38_static_entities_accounted_once=True),scope='One new call per protocol; no new detection/geometry/alignment/downstream spatial evaluation; protocol package comparison, not task-merger-only ablation.')
 save(H/'comparison.json',summary)
 with (H/'all_entities.csv').open('w') as f:
  fields=['entity_id','name']+[k+'_'+s for k in PATHS for s in ['identity','members','reason']];w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
  for row in rows:
   flat={k:row[k] for k in ['entity_id','name']}
   for k in PATHS:
    for s in ['identity','members','reason']:flat[k+'_'+s]=';'.join(row[k][s]) if s=='members' else row[k][s]
   w.writerow(flat)
 lines=['# Study2：固定几何的身份判断复测（2026-09-19）','','## 控制条件','',
 '两组共用原完整版的12张原始JPEG、38个静态实体及2D/3D框、逐帧相机、对齐坐标、投影、配准误差和故事Prompt。原版输入/提示词与其历史调用逐字节一致。两组均为新的独立 gpt-6-astra / medium CLI上下文，各调用一次；未向任何模型提供历史最终判定或目标异常。',
 '',
 '保留两种协议各自原有任务与信息呈现：原版接收初始完整配对、逐对数值诊断和配对连线图；新版仅接收原有书桌/暖气片锚点，联合做身份和存在性判断，附全量运动清单。新版锚点假设复用此前锚点阶段，坐标和全部框改用本次统一基线；诊断图据同一基线重画。未重新选择锚点或拟合变换。',
 '',
 '注意：基线为历史完整实验，包含当时生成的框；这里不混入后来取消补框、token优化后的前端。保留旧数据仅用于隔离实验变量。',
 '', '## 重点身份结果','', '| 实体 | '+' | '.join(LABELS.values())+' |','|---|'+'---|'*4]
 for t in targets:lines.append('| '+t['name']+' | '+' | '.join(t['verdicts'][k] for k in PATHS)+' |')
 lines+=['','## 全量结果','', '| 版本 | 确认匹配组 | 单侧组 | 身份未知组 | 范围不一致组 |','|---|---:|---:|---:|---:|']
 for k,c in counts.items():lines.append('| '+LABELS[k]+' | '+' | '.join(str(c.get(s,0)) for s in ['matched','unmatched','ambiguous','scope_mismatch'])+' |')
 lines+=['',f"同一几何下两种协议有 {len(changes['protocols_same_geometry'])}/38 个实体的分组或身份状态不同；原版重复调用较上次有 {len(changes['old_repeat'])}/38 个实体变化。按实体成员与身份比较，忽略组ID变化。",'', '## 本次耗时与 token','', '| 调用 | 秒 | 输入 token | 输出 token | 总 token | 缓存输入（已含输入） |','|---|---:|---:|---:|---:|---:|']
 for c in calls:lines.append('| '+('原版逐组复核' if c['stage']=='original' else '新版联合判断')+' | '+f"{c['seconds']:.2f} | {c['input_tokens']:,} | {c['output_tokens']:,} | {c['total_tokens']:,} | {c['cached_input_tokens']:,} |")
 lines += ['',f"合计 {summary['total_tokens']:,} tokens；两个调用并行，含准备和验证的总墙钟时间 {run['wall_seconds']:.2f} 秒。未将并行耗时相加，也未把缓存token重复扣除。",'', '## 判断原文','']
 for name,a,b in TARGETS:
  lines+=['### '+name,'']
  for k in ['old_replay','joint_replay']:
   g=next(g for g in groups[k] if a in g['a_ids']);lines+=['- **'+LABELS[k]+'：** '+g['identity_evidence']]
 lines+=['','## 附件与结论范围','',
 '全部38实体逐项对照：`all_entities.csv` / `comparison.json`。原始请求、输入、模型响应、事件token和耗时保存在 `calls/`；输入哈希及控制条件见 `frozen_manifest.json`；两组原有合同验证器均通过。',
 '',
 '本次未重跑原版后续两次存在性判断，也未计算关系分数。新版调用自然包含存在性输出，保存供核查，但不能与未执行的原版完整评分作对等分数比较。',
 '',
 '每种协议只新增一次调用；此实验排除两组上游几何差异，但提示词、先前身份假设、逐组诊断、图示和任务合并同时不同。不能将差异单独归因于任务合并，也不能据一次复测证明稳定性。']
 (H/'REPORT.md').write_text('\n'.join(lines)+'\n')
 print(json.dumps({k:v for k,v in summary.items() if k not in ['all_entities','joint_presence_conflicts']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
