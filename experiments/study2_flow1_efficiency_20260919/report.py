import json,csv,hashlib,itertools
from pathlib import Path
import numpy as np
H=Path(__file__).resolve().parent;E=H.parent;OLD=E/'study2_full_fresh_20260918/study2';REPLAY=E/'study2_identity_frozen_replay_20260919';AB=E/'study2_flow2_separate_ab_20260919/flow1'
read=lambda p:json.loads(p.read_text())
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def metric(p):
 s=read(p/'status.json');assert s['status']=='success' and len(s['usage'])==1;u=s['usage'][0]
 return dict(seconds=s['seconds'],input_tokens=u['input_tokens'],output_tokens=u['output_tokens'],cached_input_tokens=u.get('cached_input_tokens',0),total_tokens=u['input_tokens']+u['output_tokens'])
def sig(m):return sorted((g['group_id'],g['identity'],tuple(g['a_ids']),tuple(g['b_ids'])) for g in m['groups'])
def classify(m):return {e:(g['identity'],tuple(sorted(g['a_ids']+g['b_ids']))) for g in m['groups'] for e in g['a_ids']+g['b_ids']}
def spatial(m,p,root):
 groups=[g for g in m['groups'] if next(r for r in p['groups'] if r['group_id']==g['group_id'])['joint_presence_reasonable'] and g['identity']=='matched']
 nodes=[{e['entity_id']:e for e in read(root/'selected'/f'{s}_scene.json')['entities']} for s in ['shot1','shot3']];fit=read(OLD/'registration/roma_geometry/registration.json')['fits']['all_structures'];out={}
 for a,b in itertools.combinations(groups,2):
  va=np.array(nodes[0][b['a_ids'][0]]['geometry']['center_world'])-nodes[0][a['a_ids'][0]]['geometry']['center_world'];vb=np.array(nodes[1][b['b_ids'][0]]['geometry']['center_world'])-nodes[1][a['b_ids'][0]]['geometry']['center_world'];v=fit['scale']*np.array(fit['rotation'])@vb
  out['pair_'+a['group_id']+'_'+b['group_id']]=float(np.clip(va@v/(np.linalg.norm(va)*np.linalg.norm(v)),-1,1))
 return out
def main():
 baseline=dict(matching=metric(OLD/'calls/matching'),identity_review=metric(REPLAY/'calls/original'),presence_1=metric(AB/'calls/presence_1'),presence_2=metric(AB/'calls/presence_2'))
 rounds={};rows=[]
 baselineA=read(REPLAY/'calls/original/response.json')['matching'];baselineP=read(AB/'presence.json');bs=spatial(baselineA,baselineP,OLD)
 baseline_initial=read(OLD/'calls/matching/response.json')
 for name in ['compact_round01','compact_round02']:
  root=H/name;gate=read(root/'quality_gate.json');r={p.name:metric(p) for p in sorted((root/'calls').iterdir()) if (p/'status.json').exists()};A=read(root/('candidate_identity_review.json' if name.endswith('01') else 'identity_review.json'))['matching'];P=read(root/'presence.json')
  anchors=all(A[k]==baselineA[k] for k in ['structural_anchor_group_ids','local_origin_group_id','local_reference_group_id']);sp=spatial(A,P,root)
  spatial_equal=set(sp)==set(bs) and all(abs(sp[k]-bs[k])<1e-12 for k in bs)
  costs=dict(A_B_tokens=sum(r[k]['total_tokens'] for k in ['identity_review','presence_1','presence_2']),A_B_seconds=r['identity_review']['seconds']+max(r[k]['seconds'] for k in ['presence_1','presence_2']))
  rounds[name]=dict(gate=gate,anchors_equal=anchors,spatial_numeric_equal=spatial_equal,pair_count=len(sp),negative_count=sum(v<0 for v in sp.values()),calls=r,costs=costs,presence_summary=P['summary'],identity_changes=[e for e in classify(A) if classify(A)[e]!=classify(baselineA)[e]])
  for stage,m in r.items():rows.append(dict(round=name,stage=stage,**m))
  save(root/'spatial_numeric_audit.json',dict(unchanged=spatial_equal,all_pairs=sp,baseline_pairs=bs,model_spatial_calls_rerun=False))
  for p in (root/'calls').glob('*/wire_input.json'):
   w=read(p);assert w['derived_geometry']['max_corner_reconstruction_error']<=1e-9
 expectedStages=['identity_review','presence_1','presence_2'];baselineAB=sum(baseline[k]['total_tokens'] for k in expectedStages);baselineSec=baseline['identity_review']['seconds']+max(baseline[k]['seconds'] for k in ['presence_1','presence_2']);meanAB=sum(r['costs']['A_B_tokens'] for r in rounds.values())/2;meanSec=sum(r['costs']['A_B_seconds'] for r in rounds.values())/2
 initial=read(H/'compact_round01/calls/matching/response.json');initial_ok=sig(initial)==sig(baseline_initial) and all(initial[k]==baseline_initial[k] for k in ['structural_anchor_group_ids','local_origin_group_id','local_reference_group_id'])
 passed=initial_ok and all(all(r['gate'].values()) and r['anchors_equal'] and r['spatial_numeric_equal'] for r in rounds.values())
 result=dict(status='validated' if passed else 'quality_gate_failed',baseline=baseline,rounds=rounds,initial_matching_equal=initial_ok,baseline_A_B_tokens=baselineAB,optimized_mean_A_B_tokens=meanAB,token_reduction=1-meanAB/baselineAB,baseline_A_B_seconds=baselineSec,optimized_mean_A_B_seconds=meanSec,time_reduction=1-meanSec/baselineSec,new_validation_calls=len(rows),new_validation_tokens=sum(r['total_tokens'] for r in rows),promotable=passed,scope='Initial matching one replay; two A/B checks including production-entrypoint chain; same frozen geometry; numerical spatial invariance only, spatial model review unchanged and not rerun.')
 save(H/'result.json',result)
 with (H/'calls.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 lines=['# Flow1 skill 与传输效率优化','','## 固定的处理逻辑','',
 '完整初始身份对应+A′ → 原结构区域配准 → 逐组对齐后身份复核 → 两次独立存在性B → 原空间评测。模型继续gpt-6-astra/medium，原JPEG、实体清单、输出schema、Prompt因果复核、共识门槛和评分不变。流程2作为独立备选保留，不默认启用。',
 '', '## 实现','',
 '- 去除反复书写的字段名：同结构行使用列名+行值；重复子结构使用共享引用。',
 '- 保留中心、尺寸、旋转的原始精度；只有原八角点可由这三者恢复、误差≤1e-9时才使用角点派生标记，否则原样发送。实际最大误差1.3323e-15。完整原角点仍留在canonical input和数值计算中。',
 '- 原判断提示词完整保留，附加格式说明与简洁表达要求；没有删除原输出字段、证据或判断阶段。',
 '- 新skill和阶段入口集中管理传输配置。数字运算、共识和评分方法与原版AST一致。空间模型调用的传输暂不变。',
 '', '## 验证设计','',
 '首轮：压缩初始对应、A复核与两次B分别用固定历史输入对照；次轮：正式入口读取首轮压缩初始配对，重新执行压缩A复核，再让该输出直接进入两次B。两轮共7次新调用，无检测/深度/配准重跑。',
 '',f"质量门槛：{'全部通过' if passed else '未全部通过，不得整体启用'}。检查全部38实体身份/分组、参照选择、28个B组分类与分数、图像哈希、角点重建误差、全部28个空间对的cosine。空间模型取证及最终复核未重跑；其传输逻辑未改。",'', '## 每阶段实际成本','', '| 阶段 | 原版 token | 压缩轮1 token | 压缩轮2 token | 原版秒 | 轮1秒 | 轮2秒 |','|---|---:|---:|---:|---:|---:|---:|']
 for stage in ['matching']+expectedStages:
  a=rounds['compact_round01']['calls'].get(stage);c=rounds['compact_round02']['calls'].get(stage);o=baseline[stage]
  lines.append(f"| {stage} | {o['total_tokens']:,} | {a['total_tokens']:,} | "+(f"{c['total_tokens']:,}" if c else '复用轮1')+f" | {o['seconds']:.2f} | {a['seconds']:.2f} | "+(f"{c['seconds']:.2f}" if c else '—')+' |')
 lines+=['',f"A复核+B合计：原版 {baselineAB:,} tokens；两轮平均 {meanAB:,.0f}，减少 {100*result['token_reduction']:.2f}%。串行A加并行B的阶段耗时：原版 {baselineSec:.2f}s；两轮平均 {meanSec:.2f}s，减少 {100*result['time_reduction']:.2f}%。不同请求的延迟会波动，不承诺固定加速比例。",'',f"本次验证合计 {len(rows)} 个新调用、{result['new_validation_tokens']:,} tokens。该验证总成本不能混同单次pipeline成本；缓存输入包含在input_tokens中，不重复加减。",'', '## 两轮质量记录','']
 for name,r in rounds.items():lines+=['### '+name,'', '- 身份变化：'+str(r['identity_changes']),'- 参照不变：'+str(r['anchors_equal']),'- B统计：'+json.dumps(r['presence_summary'],ensure_ascii=False),'- 数值空间对：'+str(r['pair_count'])+'对，负值'+str(r['negative_count'])+'对；数值不变='+str(r['spatial_numeric_equal']),'- 门槛：'+json.dumps(r['gate'],ensure_ascii=False),'']
 lines+=['## 限制与回退','',
 '本次质量验证限于Study2的冻结输入；不是跨场景准确率保证。初始对应仅新跑一次，A/B两轮（第二轮为真实前后衔接）。保留原canonical传输，后续若完整实体/分类验证失败则回退，不能靠提高unknown或漏罚换取更低token。完整请求、canonical与wire输入、响应、事件计量、源码与基线备份均保留。']
 (H/'REPORT.md').write_text('\n'.join(lines)+'\n')
 print(json.dumps({k:v for k,v in result.items() if k not in ['rounds','baseline']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
