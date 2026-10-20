#!/usr/bin/env python3
import json,sys,hashlib
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'runtime/EECBench/scripts'))
from run_isolated_shot_static_3d import owned_compute_job
from audit_isolated_shot_static_3d import run as audit_static
from gs_spatial_relations import DEFAULT_POLICY
import build_three_method_static_scenes as fusion
read=lambda p:json.loads(p.read_text())
owned_compute_job()
rows=[];calls=[];fusion_checks=[]
def compare_fusion(a,b):
    errors=[]
    def check(x,y):
        if isinstance(x,dict):
            assert x.keys()==y.keys()
            for k in x:check(x[k],y[k])
        elif isinstance(x,list):
            assert len(x)==len(y)
            for v,w in zip(x,y):check(v,w)
        elif isinstance(x,float) and isinstance(y,(float,int)):
            error=abs(x-y);assert error<=1e-10;errors.append(error)
        else:assert x==y
    check(a,b)
    return max(errors,default=0)

for case in ['study0','study1']:
    d=ROOT/case
    audit_static(d/'static')
    fusion.LABELS=d/'static';fusion.BOXER=d/'geometry'
    for sid in ['shot1','shot3']:
        rebuilt,_=fusion.build('boxer_geocalib',sid);saved=read(d/'fusion'/sid/'Gs_global.json')
        rebuilt.pop('provenance');saved.pop('provenance');error=compare_fusion(rebuilt,saved)
        fusion_checks.append(dict(case=case,shot=sid,max_absolute_float_difference=error,float_tolerance=1e-10,discrete_fields_exact=True))
    s=read(d/'gs_v12/score.json')
    assert read(d/'gs_v11/audit.json')['passed'] and read(d/'gs_v12/audit.json')['passed']
    graphs=[read(d/'fusion'/sid/'Gs_global.json') for sid in ['shot1','shot3']]
    names={e['entity_id']:e['name'] for g in graphs for e in g['entities']}
    conflicts=[dict(group_id=g['group_id'],names=[names[e] for e in g['a_ids']+g['b_ids']],mechanism=g['mechanism'],reason=g['reason']) for g in s['groups'] if g['verdict']=='conflict']
    diagnostics=read(d/'gs_v11/geometry_diagnostics.json')
    review_counts={stage:dict(Counter(c['verdict'] for c in read(d/'gs_v11'/stage/'response.json')['checks'])) for stage in ['witness','verification']}
    rows.append(dict(case=case,registration_trusted=diagnostics['trusted'],registration_anchor_count=len(diagnostics['anchor_groups']),raw_review_verdict_counts=review_counts,**{k:s[k] for k in ['score','coverage','identification_interval','weights','confirmed_relation_count','previous_score']},static_counts=[len(g['entities']) for g in graphs],conflicts=conflicts,camera_assessments=[read(d/'static'/sid/'agent_review.json')['shots'][0]['camera_assessment'] for sid in ['shot1','shot3']]))
    for p in d.glob('**/status.json'):
        if (p.parent/'events.jsonl').exists():
            r=read(p)
            if r.get('status')=='success':calls.append(dict(case=case,stage=str(p.parent.relative_to(d)),usage=r.get('usage')))
for path,r in read(ROOT/'runtime_sources.json').items():assert hashlib.sha256((ROOT/'runtime/EECBench'/path).read_bytes()).hexdigest()==r['sha256']
(ROOT/'fusion_replay_audit.json').write_text(json.dumps(fusion_checks,indent=2)+'\n')
summary=dict(fusion_replay=fusion_checks,method='Gs consistency v1.2',comparison='within each case shot1 vs shot3',policy=DEFAULT_POLICY,results=rows,calls=calls,limits=['Confirmed-conflict-only upper bound, not established consistency percentage.','One scene pair per case; same-model visual judgments and heuristic geometry remain uncalibrated.','No full global 3D registration; local relation coverage depends on common anchors and support evidence.'])
(ROOT/'comparison.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
fmt=lambda x:'null' if x is None else f'{x:.2f}'
lines=['# Study0 / Study1：Shot1–Shot3 静态一致性对比','','两例均使用冻结 Gs consistency v1.2、GeoCalib＋Boxer 和相同参数，仅比较各自 Shot1 与 Shot3。预期的一致／不一致标签未传入模型。','','| 测例 | 得分上界 | 覆盖率 | 相容 C | 冲突 K | 未知 U | 互补 V | 未知区间 |','|---|---:|---:|---:|---:|---:|---:|---|']
for r in rows:
    w=r['weights'];iv=r['identification_interval'];lines.append(f"| {r['case']} | {fmt(r['score'])} | {100*r['coverage']:.1f}% | {w['compatible']} | {w['conflict']} | {w['unknown']} | {w['complement']} | {iv} |")
lines+=['','分数为 100×(1−K/(C+K+U))。互补不参与分母，未知不扣分；因此高分不等于已确认全部一致。每个实体组最多计一次冲突。','']
for r in rows:
    lines += [f"## {r['case']}",'',f"两 shot 静态实体数：{r['static_counts']}；确认空间冲突关系：{r['confirmed_relation_count']}。",'']
    lines += [f"- {c['group_id']}：{' / '.join(c['names'])}；{c['mechanism']}，{c['reason']}。" for c in r['conflicts']] or ['- 没有通过完整证据条件的确认冲突；请结合未知数量解读。']
    lines += ['',f"[证据网页]({r['case']}/gs_v12/evidence.html) · [原始分数]({r['case']}/gs_v12/score.json) · [审计]({r['case']}/gs_v12/audit.json)",'']
lines += ['## 如何解读这次比较','','study1 检出了台灯存在性冲突；study0 没有任何通过完整证据门槛的相容或冲突项，主分数为 null（不是 0 分，也不是 100 分）。因此本次不能计算两例有效的得分差或进行正负测例排序。','','study0 第一轮原始判断为 2 相容、16 未知，第二轮为 18 未知；最终 18 个实体组全部未知。其可用配准参考实体仅 2 个，未形成可信全局配准；复核对完整物理位置、尺度和遮挡解释保持保守。v1.2 的局部关系扩展只增加确认冲突，不会把无冲突候选转换成相容，所以未恢复评分覆盖。未针对预期标签调整阈值或重试判断。','']
lines += ['## 范围和复现','','- study0 = 原 experiments/study；study1 = 原 experiments/study_inconsistent_2。','- study0 重新检测及聚类；study1 复用已完成的当前协议实体输入。两者均新跑几何、独立静态判断和评分。','- 仅使用账户已有 Slurm 分配的 CPU，不使用 GPU。','- 所有静态判断独立单 shot，存在性与关系取证保持冻结版本流程。','- 几何回放、隔离审计、评分回放及运行源码哈希均通过。','- 默认中心扰动比例 0.25、轴容差 ±15°、区间分离裕量 0.005；完整敏感性结果各在 gs_v12/sensitivity.json。','- 无独立人工真值校准；没有完成全场景 3D 配准。证据 HTML 生成后未验证浏览器交互。','- run_cases.py 是输入路径和测例适配器；runtime_sources.json 记录未修改的冻结算法及提示词来源；DEPENDENCIES.md 记录启动问题。']
(ROOT/'RESULT.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(rows,ensure_ascii=False,indent=2))
