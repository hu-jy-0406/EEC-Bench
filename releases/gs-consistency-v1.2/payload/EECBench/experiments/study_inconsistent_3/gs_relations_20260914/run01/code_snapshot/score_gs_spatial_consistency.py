"""Combine independently verified spatial contradictions with a frozen presence score."""
import copy,html,json,math
from collections import Counter
from pathlib import Path
from gs_relation_contract import VERIFY_SCHEMA
VERIFY_GATES=['identity_supported','anchors_supported','common_support_verified','reference_correspondence_verified','center_semantics_verified','geometry_error_excluded','viewpoint_only_explanation_excluded']

def validate_witnesses(rows,shot_id,images):
    frame_map={f['frame_id']:f['image_size'] for f in images if f['shot_id']==shot_id}
    for w in rows:
        if w['frame_id'] not in frame_map:raise ValueError('Unknown witness frame')
        width,height=frame_map[w['frame_id']]
        for k in ['subject_region_xyxy','object_region_xyxy','reference_region_xyxy']:
            b=w[k]
            if len(b)!=4 or not all(math.isfinite(x) for x in b) or not(0<=b[0]<b[2]<=width and 0<=b[1]<b[3]<=height):raise ValueError('Invalid witness region')
    return len({w['frame_id'] for w in rows})>=2

def combine(base,relations,verified,images):
    import jsonschema
    jsonschema.validate(verified,VERIFY_SCHEMA)
    expected={r['relation_id'] for r in relations if r['candidate_conflict']};ids=[r['relation_id'] for r in verified['relations']]
    if len(ids)!=len(set(ids)) or set(ids)!=expected:raise ValueError('Verifier must cover exact candidate set')
    verify_index={v['relation_id']:v for v in verified['relations']};group_index={g['group_id']:g for g in base['groups']};involved=set();results=[]
    for r in relations:
        endpoints=r['endpoint_groups'];anchors=r['anchor_groups'];j=r['axis_index'];reason='numeric_intervals_do_not_prove_reversal';status='unknown'
        if len(set(endpoints))!=2 or set(endpoints)&set(anchors):raise ValueError('Self-referential spatial query')
        if not set(endpoints+anchors)<=set(group_index):raise ValueError('Unknown group')
        if any(len(group_index[g]['a_ids'])!=1 or len(group_index[g]['b_ids'])!=1 for g in endpoints+anchors):raise ValueError('Spatial query must have one-to-one entities')
        obs=r['shot_observations'];geometric=r['candidate_conflict'];v=verify_index.get(r['relation_id'])
        extraction_ok=[];orders=[]
        for sid,o,m in zip(base['shots'],obs,r['measurements']):
            enough=validate_witnesses(o['evidence'],sid,images)
            order={'negative':-1,'positive':1,'unknown':0}[o['order']];orders.append(order)
            extraction_ok.append(enough and o['reference_direction_verified'] and o['common_support_verified'] and o['center_order_supported'] and not o['geometry_error_can_reverse'] and m['status']=='measured' and order==m['robust_signs'][j] and order!=0)
        if geometric:
            witnesses_ok=all(validate_witnesses(v['witnesses_'+s],sid,images) for s,sid in zip(['a','b'],base['shots']))
            if all(extraction_ok) and orders[0]*orders[1]==-1 and v['verdict']=='conflict' and witnesses_ok and all(v[k] for k in VERIFY_GATES):
                status='conflict';reason='numeric_reversal_plus_two_isolated_shot_witnesses_and_cross_shot_verification';involved.update(endpoints)
            else:reason='failed_single_shot_or_cross_shot_evidence_gate'
        results.append(dict(relation_id=r['relation_id'],endpoint_groups=endpoints,anchor_groups=anchors,axis=r['axis'],status=status,reason=reason,
            nominal=[m['nominal'][j] if m['status']=='measured' else None for m in r['measurements']],
            sensitivity_intervals=[m['sensitivity_intervals'][j] if m['status']=='measured' else None for m in r['measurements']],single_shot_gate_passed=extraction_ok,verification=v))
    groups=copy.deepcopy(base['groups']);prior_conflicts={g['group_id'] for g in groups if g['verdict']=='conflict'}
    for g in groups:
        g['base_verdict']=g['verdict']
        if g['group_id'] in involved:
            if g['verdict']=='complement':raise ValueError('Complement cannot be endpoint of a shared witnessed relation')
            g['verdict']='conflict';g['mechanism']='spatial_relation';g['reason']='participates_in_confirmed_spatial_relation_conflict'
            g['spatial_relation_ids']=[r['relation_id'] for r in results if r['status']=='conflict' and g['group_id'] in r['endpoint_groups']]
    mass=Counter()
    for g in groups:mass[g['verdict']]+=g['weight']
    c,k,u,v=[mass[x] for x in ['compatible','conflict','unknown','complement']];n=c+k+u
    return dict(version='gs-consistency-v1.2',shots=base['shots'],score=100*(1-k/n) if n and c+k else None,
        previous_score=base['score'],coverage=(c+k)/n if n else None,identification_interval=[100*c/n,100*(c+u)/n] if n else None,
        weights=dict(compatible=c,conflict=k,unknown=u,complement=v),groups=groups,spatial_relations=results,
        confirmed_relation_count=sum(r['status']=='conflict' for r in results),new_penalized_groups=sorted(involved-prior_conflicts),
        penalty_semantics='Entity participation in confirmed contradictions, union of prior and relation endpoint groups, capped once per entity. A reversed pair contributes its two endpoint units; this does NOT prove both objects moved or an exact position swap.',
        formula='100*(1 - confirmed_conflict_participating_entity_weight / non_complementary_entity_weight)',
        limitations=['This is an upper-bound score with unknown items unpenalized; read coverage and interval.',
            'Local anchor-and-up relation comparison is not whole-scene registration.',
            'Center/axis stress bounds are heuristic; visual grounding and anchor correspondence still use Codex.',
            'Only relations with verified common support and sufficient geometric evidence can add penalties. Other spatial relations remain unassessed.',
            'Entity participation measures affected structure, not which entity caused the error. No held-out human accuracy calibration.'])

def render(out,result,graphs,relations):
    out=Path(out);names={e['entity_id']:e['name'] for g in graphs for e in g['entities']};groups={g['group_id']:g for g in result['groups']}
    label=lambda gid:' / '.join(names[x] for x in groups[gid]['a_ids']+groups[gid]['b_ids'])
    lines=['# Gs 存在性与空间关系评分 v1.2','',f"主分数（上界）：**{result['score']:.2f} / 100**；原分数 {result['previous_score']:.2f}；覆盖率 **{100*result['coverage']:.1f}%**。",'',
        '在固定 Gs 上新增共同支撑面内的有向中心关系；参考轴由两个已对应参考物与物理向上方向计算。局部方向不依赖相机原点、尺度或朝向，但仍需验证参考物与几何误差。',
        '', '| 关系 | 轴 | 两 shot 数值 | 压力区间 | 结果 |','|---|---|---|---|---|']
    for r in result['spatial_relations']:
        lines.append('| '+' | '.join([' ↔ '.join(label(g) for g in r['endpoint_groups']),r['axis'],str(r['nominal']),str(r['sensitivity_intervals']),r['status']])+' |')
    lines+=['','已确认冲突关系涉及的两个实体分别计1，但每个实体全局最多计一次；这表示参与不相容关系，不证明两者都移动或恰好交换了原位置。原存在性结论保持，互补仍不扣分。',
        '', '数值压力测试：采用每个物体水平框对角线25%的中心偏移半径、参考方向±15°，并组合全部选中帧的物体/参考估计；区间不是统计置信区间。两侧相反符号且区间间距>参考基线0.5%才产生几何候选，随后必须通过两个独立单shot观测及跨shot原帧复核。',
        '', '本次没有重生成三维框、没有修改冻结存在性分数，没有声称整间房屋已完成配准。适用范围是有可靠共同支撑和参考方向的局部关系；其他空间关系继续保留未知。']
    (out/'README.md').write_text('\n'.join(lines)+'\n')
    page='<!doctype html><html lang="zh"><meta charset="utf-8"><title>Gs 空间关系评分</title><style>body{max-width:1150px;margin:30px auto;padding:20px;font:16px system-ui;background:#f6f8fb}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}details{background:white;padding:15px;margin:12px 0}</style><h1>Gs 存在性与空间关系评分</h1><p>上界 '+str(round(result['score'],2))+' / 100 · 原分数 '+str(round(result['previous_score'],2))+' · 覆盖率 '+str(round(100*result['coverage'],1))+'%</p><p>每个参与确认冲突的实体最多扣一次。关系反转不等于证明两件物体都移动。完整数值、误差范围与原帧见旁边 JSON 文件。</p>'
    for r in result['spatial_relations']:
        page+='<details open><summary>'+html.escape(' ↔ '.join(label(g) for g in r['endpoint_groups'])+' / '+r['axis']+' / '+r['status'])+'</summary><pre>'+html.escape(json.dumps(r,ensure_ascii=False,indent=2))+'</pre></details>'
    (out/'report.html').write_text(page+'</html>')
