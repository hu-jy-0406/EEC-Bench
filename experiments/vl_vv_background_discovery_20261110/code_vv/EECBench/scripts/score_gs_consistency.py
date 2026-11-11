#!/usr/bin/env python3
"""Deterministic, conflict-only score with abstention and explicit evidence coverage."""
import argparse,html,json,math
from collections import Counter
from pathlib import Path
from gs_consistency_contract import CHECK_SCHEMA,VERSION
GATES=['identity_supported','mapping_supported','visibility_supported','geometry_uncertainty_excluded','occlusion_excluded','detector_miss_excluded','alternative_mappings_excluded']

def validate_review(review,groups,images,expected_ids=None):
    import jsonschema
    jsonschema.validate(review,CHECK_SCHEMA)
    ids=[r['group_id'] for r in review['checks']]
    if len(ids)!=len(set(ids)) or set(ids)!=set(groups if expected_ids is None else expected_ids):raise ValueError('Every group must be reviewed exactly once')
    frames={(f['shot_id'],f['frame_id']):f['image_size'] for f in images}
    for r in review['checks']:
        if not set(r['anchor_group_ids'])<=set(groups):raise ValueError('Unknown anchor group')
        for w in r['visual_evidence']:
            key=(w['shot_id'],w['frame_id'])
            if key not in frames:raise ValueError('Unknown evidence frame')
            box=w['region_xyxy'];width,height=frames[key]
            if len(box)!=4 or not all(math.isfinite(v) for v in box) or not(0<=box[0]<box[2]<=width and 0<=box[1]<box[3]<=height):raise ValueError('Invalid evidence region')
            if not w['observation'].strip():raise ValueError('Empty visual evidence')

def admitted(r,g,groups,diagnostics,shots):
    v=r['verdict']
    if v=='unknown':return 'unknown','reviewer_abstained'
    if g['identity'] in ['ambiguous','scope_mismatch']:return 'unknown','unresolved_identity_or_granularity'
    counts={sid:len({w['frame_id'] for w in r['visual_evidence'] if w['shot_id']==sid}) for sid in shots}
    if not all(r[k].strip() for k in ['gs_evidence','affected_location','counterfactual_test','alternative_explanations','reason']):return 'unknown','missing_explanation'
    if v=='complement':
        if g['identity']!='unmatched' or min(counts.values())<1 or not r['identity_supported'] or not r['visibility_supported']:return 'unknown','unproved_view_exclusion'
        return v,'positive_view_exclusion'
    if v=='compatible' and g['identity']!='matched':return 'unknown','no_shared_entity'
    needed=GATES if v=='conflict' else ['identity_supported','mapping_supported','visibility_supported','alternative_mappings_excluded']
    if not all(r[k] for k in needed):return 'unknown','failed_evidence_gate'
    anchors=set(r['anchor_group_ids'])
    if g['group_id'] in anchors or any(groups[x]['identity']!='matched' for x in anchors):return 'unknown','circular_or_unmatched_anchor'
    if r['mapping_basis']=='local_visual':
        if len(anchors)<2:return 'unknown','insufficient_local_landmarks'
    elif r['mapping_basis']=='global_consensus':
        if not diagnostics['trusted'] or g['group_id'] in diagnostics['anchor_groups']:return 'unknown','untrusted_or_circular_registration'
        if not set(diagnostics['anchor_groups'])<=anchors:return 'unknown','registration_anchor_coverage'
    else:return 'unknown','no_mapping'
    if v=='compatible':
        if min(counts.values())<1:return 'unknown','no_bidirectional_witness'
    elif r['mechanism']=='presence':
        if g['identity']!='unmatched':return 'unknown','presence_requires_singleton'
        source,target=(shots[0],shots[1]) if g['a_ids'] else (shots[1],shots[0])
        if counts[source]<1 or counts[target]<2:return 'unknown','insufficient_absence_witness'
    elif r['mechanism'] in ['layout','shape']:
        if g['identity']!='matched' or min(counts.values())<2:return 'unknown','insufficient_layout_witness'
    else:return 'unknown','missing_conflict_mechanism'
    return v,'all_required_gates_passed'

def score(graphs,matching,diagnostics,reviews,images):
    from run_gs_consistency import validate_match
    validate_match(matching,graphs)
    if len(reviews) not in [2,3]:raise ValueError('Two reviews and at most one bounded recheck required')
    groups={g['group_id']:g for g in matching['groups']};shots=[g['shot_id'] for g in graphs]
    for r in reviews[:2]:validate_review(r,groups,images)
    indexes=[{r['group_id']:r for r in v['checks']} for v in reviews[:2]]
    recheck_ids=[]
    for gid,g in groups.items():
        labels=[admitted(r[gid],g,groups,diagnostics,shots)[0] for r in indexes]
        if set(labels) in [{'compatible','unknown'},{'conflict','unknown'}]:recheck_ids.append(gid)
    rechecks={}
    if len(reviews)==3:
        validate_review(reviews[2],groups,images,recheck_ids)
        rechecks={r['group_id']:r for r in reviews[2]['checks']}
    items=[];mass=Counter()
    for gid,g in groups.items():
        checks=[r[gid] for r in indexes];admissions=[admitted(r,g,groups,diagnostics,shots) for r in checks]
        labels=[r[0] for r in admissions];verdict=labels[0] if labels[0]==labels[1] else 'unknown'
        reason='two_reviews_agree' if labels[0]==labels[1] else 'review_disagreement_or_gate_failure'
        if verdict=='conflict' and checks[0]['mechanism']!=checks[1]['mechanism']:verdict='unknown';reason='conflict_mechanism_disagreement'
        if verdict in ['compatible','conflict'] and all(r['mapping_basis']=='local_visual' for r in checks):
            if len(set(checks[0]['anchor_group_ids'])&set(checks[1]['anchor_group_ids']))<2:verdict='unknown';reason='local_reference_disagreement'
        if verdict=='unknown' and gid in rechecks:
            candidate=rechecks[gid];third=admitted(candidate,g,groups,diagnostics,shots);original=[r for r,(v,_) in zip(checks,admissions) if v in ['compatible','conflict']]
            if len(original)==1 and third[0]==original[0]['verdict']:
                prior=original[0]
                mechanism_ok=third[0]!='conflict' or candidate['mechanism']==prior['mechanism']
                references_ok=not(candidate['mapping_basis']==prior['mapping_basis']=='local_visual') or len(set(candidate['anchor_group_ids'])&set(prior['anchor_group_ids']))>=2
                if mechanism_ok and references_ok:verdict=third[0];reason='bounded_witness_recheck_resolved_abstention'
            checks=checks+[candidate];admissions=admissions+[third]
        # Frozen identity universe, not O(n^2) edges. Ambiguous merged groups retain their entity mass.
        weight=max(len(g['a_ids']),len(g['b_ids']))
        mass[verdict]+=weight
        items.append(dict(group_id=gid,a_ids=g['a_ids'],b_ids=g['b_ids'],verdict=verdict,weight=weight,
            mechanism=next(r['mechanism'] for r,(v,_) in zip(checks,admissions) if v=='conflict') if verdict=='conflict' else 'none',reason=reason,
            gate_results=[dict(verdict=v,reason=r) for v,r in admissions],reviews=checks))
    c,k,u,v=[mass[x] for x in ['compatible','conflict','unknown','complement']]
    assessed=c+k;potential=c+k+u
    value=100*(1-k/potential) if assessed and potential else None
    interval=[100*c/potential,100*(c+u)/potential] if potential else None
    return dict(version=VERSION,shots=shots,score=value,score_name='Witnessed Static Consistency (WSC)',
        interpretation='Confirmed-conflict-only consistency upper bound over fixed non-complementary entity units. Unknown units receive no penalty, not proof of consistency. Read with coverage and interval; null means no adjudicable comparison.',
        conditional_assessed_score=100*c/assessed if assessed else None,recheck_candidate_ids=recheck_ids,
        coverage=assessed/potential if potential else None,identification_interval=interval,
        interval_interpretation='Logical sensitivity bounds if every unresolved unit is conflict vs compatible; NOT a statistical confidence interval.',
        weights=dict(compatible=c,conflict=k,unknown=u,complement=v),groups=items,
        formula='100 * (1 - K/(C+K+U)); coverage=(C+K)/(C+K+U). Complement V contributes to neither numerator nor denominator. Each entity unit capped at one conflict.',
        limitations=['Evidence gates rely on fresh reviews of the same model and at most one proposal-aware recheck; agreement is not statistically independent evidence or calibrated confidence.',
                    'Static partition and identity grouping are upstream assumptions. Granularity is fixed before evidence review.',
                    'Conditional scores require coverage and interval when comparing scene pairs; low coverage is not proved consistency.',
                    'Unobserved alterations cannot be detected. Raw monocular 3D disagreement alone is not penalized.'])

def report(out,result,matching):
    out=Path(out);value='不可判定' if result['score'] is None else f"{result['score']:.2f} / 100"
    cov='无比较区域' if result['coverage'] is None else f"{100*result['coverage']:.1f}%"
    names={e['entity_id']:e['name'] for name in ['graph_a.json','graph_b.json'] for e in json.loads((out/name).read_text())['entities']}
    labels={'compatible':'有证据相容','conflict':'确认冲突','complement':'视角互补','unknown':'证据不足'}
    lines=['# Gs 跨 shot 一致性评分','',f'WSC（确认冲突罚分后的上界）：**{value}**；可判定覆盖率：**{cov}**。',
        f"逻辑敏感性区间：{result['identification_interval']}（不是统计置信区间）。",'',
        '`WSC = 100 × (1 − K / (C + K + U))`；C 为有证据相容、K 为确认冲突、U 为未知实体权重。主分数是只扣确认冲突后的上界，须同时看覆盖率和区间。互补不参与分母；未知不扣分，不代表证实一致。每个实体最多计一次。',
        '', '| 实体 | 结果 | 判定原因 |','|---|---|---|']
    cards=[]
    for g in result['groups']:
        name=' / '.join(names[x] for x in g['a_ids']+g['b_ids'])
        why='；'.join(r['reason'] for r in g['reviews'])
        lines.append('| '+' | '.join([name,labels[g['verdict']],why.replace('|','/').replace('\n',' ')])+' |')
        cards.append('<details><summary>'+html.escape(name)+' — '+labels[g['verdict']]+'</summary><pre>'+html.escape(json.dumps(g,ensure_ascii=False,indent=2))+'</pre></details>')
    lines+=['','只测在固定静态场景假设下、可以被当前观测证伪的冲突。三维是候选与结构来源，原帧用于验证可见性、对应关系和几何误差替代解释。两个同模型审核意见不是独立真值，仍需在多场景正负样本上标定和验证。']
    (out/'README.md').write_text('\n'.join(lines)+'\n')
    page='<!doctype html><html lang="zh"><meta charset="utf-8"><title>Gs 一致性评分</title><style>body{font:16px system-ui;max-width:1100px;margin:32px auto;padding:20px;background:#f7f8fa;color:#182230}details{background:white;border:1px solid #ddd;padding:14px;margin:8px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}</style><h1>Gs 跨 shot 一致性</h1><p>WSC <b>'+value+'</b> · 可判定覆盖率 <b>'+cov+'</b></p><p>互补不扣分；证据不足不当作一致。每个实体最多扣一次。区间 '+html.escape(str(result['identification_interval']))+' 是未知项敏感性范围，不是置信区间。</p>'+''.join(cards)+'</html>'
    (out/'report.html').write_text(page)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args();read=lambda name:json.loads((a.run/name).read_text())
    result=score([read('graph_a.json'),read('graph_b.json')],read('matching.json'),read('geometry_diagnostics.json'),[read('witness/response.json'),read('verification/response.json')]+([read('recheck/response.json')] if (a.run/'recheck/response.json').exists() else []),read('payload.json')['images'])
    (a.run/'score.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');report(a.run,result,read('matching.json'));print(json.dumps({k:v for k,v in result.items() if k!='groups'},ensure_ascii=False))
