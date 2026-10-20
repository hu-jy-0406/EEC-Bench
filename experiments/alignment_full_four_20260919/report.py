#!/usr/bin/env python3
"""Read-only audit of four independent fresh evaluations; write root reports only.

Run with the standard-library Python on the selected compute node. No imports of
inference code, no model calls, and no rewriting of any case outputs.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

CASES = ('study2_fps32', 'study2_codex_direct', 'study3_fps32', 'study3_codex_direct')
DIRECT_FIELDS = {'stage', 'normal_story_prompt', 'shots', 'images', 'transform_convention'}
SHOT_FIELDS = {'shot_id', 'coordinate_system', 'cameras', 'entities'}
ENTITY_FIELDS = {'entity_id', 'name', 'motion_status', 'geometry', 'observations'}


def load(path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text())


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def save(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    temp.replace(path)


def text(value):
    if isinstance(value, list):
        return '；'.join(map(str, value))
    return str(value or '')


def safe(value):
    return text(value).replace('|', '\\|').replace('\n', ' ')


def fmt(value, places=2):
    return '—' if value is None else f'{value:,.{places}f}'


def csv_write(path, rows, columns):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def identity_key(group, nodes):
    return {side: [dict(entity_id=eid, name=nodes.get(eid, {}).get('name', eid),
                       motion_status=nodes.get(eid, {}).get('motion_status', 'unknown'))
                   for eid in group.get(side + '_ids', [])] for side in ('a', 'b')}


def group_label(identity):
    return ' ↔ '.join('/'.join(e['name'] for e in identity[side]) or '∅' for side in ('a', 'b'))


def check_sources(hashes):
    return [dict(path=str(path), expected=digest,
                 actual=sha(Path(path)) if Path(path).is_file() else None)
            for path, digest in hashes.items()]


def read_case(root, name):
    case = root / name
    study = name.split('_')[0]
    method = 'codex_direct' if name.endswith('codex_direct') else 'roma_fps32'
    runtime = load(case / 'pipeline_runtime.json', {})
    summary = load(case / 'summary.json', {})
    status = runtime.get('status', 'not_started')
    stages = runtime.get('stages', [])
    done = {s['stage'] for s in stages if s.get('status') == 'success'}
    checks, notes = {}, []
    presence = load(case / 'presence.json', {})
    spatial = load(case / 'spatial.json', {})
    matching = load(case / 'matching.json', {})
    manifest = load(case / 'raw_manifest.json', {})
    expected = load(root / (study + '_manifest.json'), {})
    nodes, population = {}, {}
    for sid in ('shot1', 'shot2', 'shot3'):
        scene = load(case / 'selected' / (sid + '_scene.json'), {})
        entities = scene.get('entities', [])
        nodes.update({e['entity_id']: e for e in entities})
        cluster = load(case / 'entities/shots' / sid / 'entities.json', {})
        population[sid] = dict(detected_entities=len(cluster['entities']) if 'entities' in cluster else None,
                               identity_entities=len(entities) if scene else None,
                               motion_counts=dict(Counter(e.get('motion_status', 'unknown') for e in entities)))
    frames = {(shot['shot_id'], f['frame_id']): f for shot in manifest.get('shots', []) for f in shot['frames']}
    original_hashes = {f'{sid}/{fid}': dict(path=f['path'], expected=f.get('sha256'),
                       actual=sha(Path(f['path'])) if Path(f['path']).is_file() else None)
                       for (sid, fid), f in frames.items()}
    checks['18_original_frames_unchanged'] = (len(frames) == 18 and all(
        f['expected'] and f['actual'] == f['expected'] for f in original_hashes.values())) if manifest else None
    expected_frames = {(s['shot_id'], f['frame_id']): f for s in expected.get('shots', []) for f in s['frames']}
    checks['root_manifest_same_bytes'] = (set(expected_frames) == set(frames) and all(
        sha(Path(f['path'])) == frames[key].get('sha256') for key, f in expected_frames.items())) if manifest and expected else None
    checks['normal_narrative_unchanged'] = (load(case/'narrative.json') == load(root/'narrative.json')) if (case/'narrative.json').exists() and (root/'narrative.json').exists() else None
    front = load(case / 'entities/run.json', {})
    front_shots = {s['shot_id']: s for s in front.get('shots', [])}
    checks['fresh_detection_and_three_clustering_calls'] = (
        front.get('detector_mode') == 'fresh' and set(front_shots) == {'shot1','shot2','shot3'} and all(
            row.get('status') == 'success' and row.get('reused_from') is None and row.get('calls', 0) >= 1
            for row in front_shots.values())) if 'detection_and_clustering' in done else None
    detector_run = load(case/'entities/detections/run.json', {})
    detector_frames = {(r['shot'], r['frame_id']): r.get('sha256') for r in detector_run.get('frames', [])}
    checks['detector_ran_on_all_18_original_frames'] = (detector_run.get('status') == 'success' and
        detector_frames == {key: f.get('sha256') for key,f in frames.items()} and len(detector_frames) == 18) if 'detection_and_clustering' in done else None
    isolation = []
    for sid in ('shot1','shot2','shot3'):
        payload = load(case/'entities/shots'/sid/'input.json')
        request = load(case/'entities/shots'/sid/'request.json')
        if payload and request:
            command = request.get('command', [])
            rows = payload.get('frames', [])
            expected_shot = {fid: f['sha256'] for (s, fid), f in frames.items() if s == sid}
            isolation.append(payload.get('shot_id') == sid and len(rows) == 6 and
                             {r['frame_id']: r.get('image_sha256') for r in rows} == expected_shot and
                             command.count('--image') == 6 and '--ephemeral' in command)
    checks['clustering_own_shot_original_frames_only'] = all(isolation) if len(isolation) == 3 else None
    provenance = load(case/'provenance.json', {})
    checks['fresh_inference_declared'] = provenance.get('inference_reuse') is False if provenance else None
    sources = check_sources(provenance.get('source_hashes', {}))
    checks['executed_sources_unchanged'] = all(row['expected'] == row['actual'] for row in sources) if sources else None
    groups = matching.get('groups', [])
    seen = [eid for g in groups for side in ('a','b') for eid in g.get(side+'_ids', [])]
    expected_ids = set(nodes)
    checks['all_entity_identity_population_conserved'] = (set(seen) == expected_ids and len(seen) == len(set(seen))) if groups and expected_ids else None
    for stage, filename in [('initial_identity','matching_initial.json'), ('aligned_identity_review','matching.json')]:
        identity = load(case/filename, {})
        ids = [eid for g in identity.get('groups', []) for side in ('a','b') for eid in g.get(side+'_ids', [])]
        checks[stage+'_includes_moving_and_unknown'] = (set(ids) == expected_ids and len(ids) == len(set(ids))) if stage in done and identity else None
    static = load(case/'matching_static.json', {})
    static_ids = {g['group_id'] for g in static.get('groups', [])}
    expected_static = {g['group_id'] for g in groups if all(nodes.get(eid,{}).get('motion_status') == 'static'
                       for side in ('a','b') for eid in g.get(side+'_ids', []))}
    checks['static_scoring_excludes_mixed_motion_groups_intact'] = static_ids == expected_static if static and groups else None
    group_map = {g['group_id']: g for g in groups}
    identities = {gid: identity_key(g, nodes) for gid,g in group_map.items()}
    calls = []
    callpaths = list((case/'entities/shots').glob('*/status.json')) + list((case/'calls').glob('*/status.json'))
    request_checks = []
    for path in sorted(callpaths):
        state = load(path, {})
        usage = state.get('usage', state.get('known_usage', []))
        if isinstance(usage, dict):
            usage = [usage]
        counts = {key: sum(int(u.get(key,0) or 0) for u in usage if u) for key in ('input_tokens','output_tokens','cached_input_tokens')}
        if not usage and state.get('status') == 'running':
            counts = {key: None for key in counts}
        duration = state.get('seconds')
        if duration is None and state.get('finished') is not None and state.get('started') is not None:
            duration = state['finished'] - state['started']
        calls.append(dict(case=name, call=str(path.parent.relative_to(case)), status=state.get('status'), seconds=duration,
                          **counts, total_tokens=(counts['input_tokens'] + counts['output_tokens']) if counts['input_tokens'] is not None else None,
                          usage_turns=len(usage)))
        request = load(path.parent/'request.json', {})
        if request:
            command = request.get('command', [])
            request_checks.append('--ephemeral' in command and '--model' in command and command[command.index('--model')+1] == 'gpt-6-astra'
                                  and 'model_reasoning_effort="medium"' in command and 'web_search="disabled"' in command)
    checks['all_saved_requests_astra_medium_ephemeral'] = all(request_checks) if request_checks else None
    registration = load(case/'registration/roma_geometry/registration.json', {})
    raw_pairs = list((case/'registration/roma').glob('*.npz'))
    # Historical matching code writes RUN/roma; RUN is case/registration.
    if method == 'codex_direct':
        direct = load(case/'calls/registration_direct/input.json')
        checks['direct_no_roma_or_lift_stages'] = not any(s['stage'] in ('roma_matches','lift_correspondences') for s in stages) if runtime else None
        checks['direct_no_raw_keypoints_or_correspondence_arrays'] = not raw_pairs and not (case/'registration/roma_geometry/correspondences.npz').exists() if runtime else None
        checks['direct_allowed_payload_fields_only'] = (set(direct) == DIRECT_FIELDS and all(set(s) == SHOT_FIELDS and all(set(e) == ENTITY_FIELDS for e in s['entities']) for s in direct['shots'])) if direct else None
        if direct:
            checks['direct_normal_prompt_and_full_own_geometry'] = direct.get('normal_story_prompt') == load(case/'narrative.json') and {s['shot_id'] for s in direct['shots']} == {'shot1','shot3'} and all(
                s['entities'] == [dict(entity_id=e['entity_id'], name=e['name'], motion_status=e['motion_status'], geometry=e['geometry'],
                                      observations={i['entity_id']: i for i in load(case/'inputs'/(s['shot_id']+'.json'))['entities']}[e['entity_id'].split('/')[-1]]['observations'])
                                  for e in load(case/'selected'/(s['shot_id']+'_scene.json'))['entities']]
                for s in direct['shots'])
        direct_request = load(case/'calls/registration_direct/request.json', {})
        if direct_request:
            attached = {(r['shot_id'],r['frame_id']): r['sha256'] for r in direct_request.get('images', [])}
            checks['direct_12_original_frame_attachments'] = attached == {key:f['sha256'] for key,f in frames.items() if key[0] in ('shot1','shot3')} and len(attached) == 12
            command = direct_request.get('command', [])
            disabled = {command[i+1] for i,v in enumerate(command[:-1]) if v == '--disable'}
            checks['direct_tools_disabled'] = {'shell_tool','unified_exec','view_image','apps','plugins','multi_agent','browser_use','code_mode'} <= disabled
        policy = registration.get('evidence_policy', {})
        checks['direct_no_matching_anchors_optimizer_or_prior_transform'] = all(policy.get(k) is False for k in ('cross_shot_matching_supplied','anchors_supplied','roma_supplied','previous_transform_supplied','numerical_optimization')) if registration else None
    else:
        sampling = registration.get('sampling', {})
        count = sampling.get('selected_count')
        checks['fps32_fixed_population'] = (sampling.get('method') == 'fps' and sampling.get('requested_count') == 32 and
             isinstance(count,int) and 3 <= count <= 32 and len(sampling.get('selected_rows', [])) == count and
             len(set(sampling.get('selected_rows', []))) == count and sampling.get('confidence_floor') == .2) if registration else None
        checks['fresh_36_roma_frame_pairs'] = len(raw_pairs) == 36 if 'roma_matches' in done else None
        fit = registration.get('fits',{}).get('all_structures',{})
        checks['exact_uniform_unsquared_objective_no_removal'] = (fit.get('objective') == 'sum_all_pair_euclidean_3d_distances_v1' and fit.get('all_selected_pairs_used') is True and fit.get('points_removed') == 0 and fit.get('point_weights') == 'uniform_1' and fit.get('distance_power') == 1 and fit.get('fit_rows') == count) if registration else None
    if registration:
        reg_sources = check_sources(registration.get('source_hashes', {}))
        checks['registration_source_hashes_unchanged'] = all(x['expected'] == x['actual'] for x in reg_sources) if reg_sources else None
        if registration.get('inference_reuse'):
            notes.append('registration.json 标注 inference_reuse=true；请区分同一 fresh run 的点表与历史推理复用。')
    checks['single_presence_call'] = presence.get('aggregation_version') == 'single_presence_witness_v1' and not (case/'calls/presence_2').exists() if presence else None
    relations = spatial.get('relations', [])
    n = len(spatial.get('population_group_ids', []))
    checks['all_unordered_spatial_pairs'] = len(relations) == n*(n-1)//2 and len({tuple(sorted(r['endpoint_groups'])) for r in relations}) == len(relations) if spatial else None
    cosine_errors = []
    for relation in relations:
        va, vb = relation.get('vector_shot1'), relation.get('vector_shot3_aligned')
        if va and vb and relation.get('cosine') is not None:
            norm = math.sqrt(sum(x*x for x in va)*sum(x*x for x in vb))
            if norm:
                cosine_errors.append(abs(sum(x*y for x,y in zip(va,vb))/norm - relation['cosine']))
    checks['stored_spatial_cosines_consistent'] = max(cosine_errors,default=0) < 1e-9 if spatial else None
    defects = {'presence': [], 'spatial': []}
    for row in presence.get('groups', []):
        if row.get('status') == 'conflict':
            gid = row['group_id']
            defects['presence'].append(dict(group_id=gid, identity=identities.get(gid, {}), kind=row.get('conflict_kind'), reason=row.get('reason'),
                                            label=group_label(identities[gid]) if gid in identities else gid))
    for row in relations:
        if row.get('status') == 'conflict':
            defects['spatial'].append(dict(relation_id=row['relation_id'], endpoint_groups=row['endpoint_groups'],
                    endpoints=[identities.get(gid,{}) for gid in row['endpoint_groups']], cosine=row.get('cosine'), reason=row.get('reason'),
                    label=' / '.join(group_label(identities[gid]) if gid in identities else gid for gid in row['endpoint_groups'])))
    complete = status == 'success' and 'presence' in done and 'spatial' in done and bool(presence) and bool(spatial)
    final_presence = presence.get('summary') if complete else None
    final_spatial = spatial.get('summary') if complete else None
    row = dict(case=name, study=study, method=method, status='completed' if complete else status,
        error=runtime.get('error'), final_scores_available=complete,
        presence_score=final_presence.get('score') if final_presence else None,
        spatial_score=final_spatial.get('score') if final_spatial else None,
        presence=final_presence, spatial=final_spatial,
        partial_presence=presence.get('summary') if not complete else None,
        partial_spatial=spatial.get('summary') if not complete else None,
        elapsed_seconds=runtime.get('seconds'), total_tokens=sum(c['total_tokens'] or 0 for c in calls),
        input_tokens=sum(c['input_tokens'] or 0 for c in calls), output_tokens=sum(c['output_tokens'] or 0 for c in calls),
        cached_input_tokens=sum(c['cached_input_tokens'] or 0 for c in calls), calls=len(calls),
        roma_seconds=next((s.get('seconds') for s in stages if s['stage']=='roma_matches'), None),
        registration_seconds=next((s.get('seconds') for s in stages if s['stage']=='registration'), None),
        direct_call_seconds=registration.get('model_seconds'), fps_selection_seconds=registration.get('selection_seconds'),
        optimization_seconds=registration.get('optimization_seconds'), population=population,
        identity_groups=dict(Counter(g.get('identity','unknown') for g in groups)),
        matched_moving_or_unknown_groups=[gid for gid,g in group_map.items() if g.get('identity') == 'matched' and any(
            nodes.get(eid,{}).get('motion_status') != 'static' for side in ('a','b') for eid in g.get(side+'_ids',[]))],
        spatial_population=n if spatial else None, spatial_pairs=len(relations) if spatial else None,
        negative_proposals=spatial.get('negative_proposals'), support_pass=spatial.get('support_pass'), defects=defects,
        anchors_initial=load(case/'matching_initial.json', {}).get('structural_anchor_group_ids'),
        transform=registration.get('fits',{}).get('all_structures'), notes=notes)
    if summary:
        checks['summary_usage_matches_actual_call_records'] = row['total_tokens'] == summary.get('total_tokens') if complete else None
    audit = dict(status='failed' if any(v is False for v in checks.values()) else ('passed' if complete and all(v is True for v in checks.values()) else 'incomplete'),
                 checks=checks, notes=notes, original_frames=original_hashes, source_hashes=sources,
                 identity_population_expected=sorted(expected_ids), identity_population_seen=sorted(seen),
                 max_stored_cosine_error=max(cosine_errors,default=None))
    return row, audit, calls, [dict(case=name, **s) for s in stages]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    root = args.root.resolve()
    results, audits, calls, stages = [], {}, [], []
    for name in CASES:
        try:
            row, audit, call_rows, stage_rows = read_case(root, name)
        except Exception as exc:
            row = dict(case=name, study=name.split('_')[0], method='codex_direct' if name.endswith('codex_direct') else 'roma_fps32',
                       status='report_error', error=repr(exc), presence_score=None, spatial_score=None, final_scores_available=False, defects={})
            audit = dict(status='failed', report_error=repr(exc))
            call_rows, stage_rows = [], []
        results.append(row); audits[name]=audit; calls.extend(call_rows); stages.extend(stage_rows)
    comparisons=[]
    for study in ('study2','study3'):
        a,b = [r for r in results if r['study']==study]
        complete = a.get('final_scores_available') and b.get('final_scores_available')
        comparisons.append(dict(study=study, both_complete=complete,
            equal_presence_score=(a['presence_score']==b['presence_score']) if complete else None,
            equal_spatial_score=(a['spatial_score']==b['spatial_score']) if complete else None,
            presence_defect_labels={r['method']: [d['label'] for d in r.get('defects',{}).get('presence',[])] for r in (a,b)},
            spatial_defect_labels={r['method']: [d['label'] for d in r.get('defects',{}).get('spatial',[])] for r in (a,b)},
            note='实体 ID、名称及冻结总体来自各自独立推理；标签需人工核对，不自动把同名视为同一实体。'))
    peer_checks={}
    for study in ('study2','study3'):
        a,b=[root/(study+'_'+method) for method in ('fps32','codex_direct')]
        ma,mb=load(a/'raw_manifest.json'),load(b/'raw_manifest.json')
        peer_checks[study+'_identical_method_inputs']=ma==mb if ma and mb else None
    a,b=load(root/'study2_manifest.json'),load(root/'study3_manifest.json')
    if a and b:
        get=lambda x,sid:[sha(Path(f['path'])) for s in x['shots'] if s['shot_id']==sid for f in s['frames']]
        peer_checks['study2_study3_shot1_shot2_same_original_bytes']=all(get(a,sid)==get(b,sid) for sid in ('shot1','shot2'))
        peer_checks['study2_study3_shot3_different']=get(a,'shot3')!=get(b,'shot3')
    overall='passed' if all(a['status']=='passed' for a in audits.values()) and all(v is True for v in peer_checks.values()) else 'incomplete'
    if any(a['status']=='failed' for a in audits.values()) or any(v is False for v in peer_checks.values()):overall='failed'
    timestamp=datetime.now(timezone.utc).isoformat()
    save(root/'comparison.json',dict(generated_at=timestamp, cases=results, method_comparisons=comparisons,
        total_reported_tokens=sum(r.get('total_tokens',0) for r in results), all_four_completed=all(r.get('final_scores_available') for r in results)))
    save(root/'audit.json',dict(status=overall, generated_at=timestamp, cases=audits, shared_input_checks=peer_checks,
                               scope='artifact/hash/structural audit; does not establish semantic correctness or ground-truth score accuracy'))
    csv_write(root/'comparison.csv',results,['case','method','status','presence_score','spatial_score','elapsed_seconds','total_tokens','input_tokens','output_tokens','cached_input_tokens','calls','roma_seconds','registration_seconds','direct_call_seconds','fps_selection_seconds','optimization_seconds','spatial_population','spatial_pairs','negative_proposals','support_pass','error'])
    csv_write(root/'calls.csv',calls,['case','call','status','seconds','input_tokens','output_tokens','cached_input_tokens','total_tokens','usage_turns'])
    csv_write(root/'stages.csv',stages,['case','stage','status','seconds','returncode','started','total_tokens'])
    lines=['# Study2 / Study3：FPS32 与纯 Codex，四次独立完整评测','',
        '从 WeDetect-Anything 起重新执行各自前端、身份匹配及后续评测。Shot1/Shot3 同场景参与评分；Shot2 单独检测与聚类。外观评分未运行。', '',
        '存在性与空间分数沿用当前静止实体评测口径；跨 shot 身份匹配包含运动、未知状态实体。失败或未完成的实验不填最终分数。', '',
        '|实验|状态|存在性|空间|墙钟秒|Token|RoMA 秒|配准阶段秒|', '|---|---|---:|---:|---:|---:|---:|---:|']
    for r in results:
        lines.append(f"|{r['case']}|{r['status']}|{fmt(r.get('presence_score'),4)}|{fmt(r.get('spatial_score'),4)}|{fmt(r.get('elapsed_seconds'))}|{fmt(r.get('total_tokens'),0)}|{fmt(r.get('roma_seconds'))}|{fmt(r.get('registration_seconds'))}|")
    lines += ['', 'Token 为四次实验实际调用的输入＋输出，缓存输入已包含在输入中。阶段存在重叠，不将阶段时间求和当作墙钟；RoMA 时间已包含在各自墙钟中。详见 calls.csv / stages.csv。',
              '各实验独立检测、聚类、动静判断和身份匹配，实体总体可能不同；结果差异不能全部归因于配准。四次单次运行也不足以估计随机性。', '']
    for r in results:
        lines += ['## '+r['case'],'']
        if r.get('error'):lines += ['失败或报告错误：`'+safe(r['error'])+'`','']
        if r.get('population'):lines += ['实体总体：`'+json.dumps(r['population'],ensure_ascii=False)+'`。',
            '完整身份组：`'+json.dumps(r['identity_groups'],ensure_ascii=False)+'`；匹配的运动/未知组：`'+json.dumps(r['matched_moving_or_unknown_groups'])+'`。','']
        for key,label in [('presence','存在性'),('spatial','空间')]:
            score=r.get(key)
            if score:lines += [label+'计数及覆盖：`'+json.dumps(score,ensure_ascii=False)+'`。','']
            defects=r.get('defects',{}).get(key,[])
            lines.append(label+'确认冲突：')
            if not defects:lines.append('- 无。' if r.get('final_scores_available') else '- 尚无最终结果。')
            for d in defects:
                cosine='；cosine='+fmt(d['cosine'],6) if 'cosine' in d else ''
                lines.append('- '+safe(d['label'])+'；'+safe(d.get('kind',''))+cosine+'；'+safe(d.get('reason')))
            lines.append('')
        audit=audits[r['case']]
        lines += ['审计状态：**'+audit['status']+'**。']
        for name,value in audit.get('checks',{}).items():
            if value is not True:lines.append('- '+name+'：'+('未完成/缺证据' if value is None else '失败'))
        lines += ['']
    lines += ['## 两种方法是否一致','']
    for row in comparisons:
        lines.append('- '+row['study']+'：'+('存在性分数'+('相同' if row['equal_presence_score'] else '不同')+'；空间分数'+('相同' if row['equal_spatial_score'] else '不同') if row['both_complete'] else '两次完整结果尚未齐备，暂不比较。'))
    lines += ['', '逐实体缺陷以各实验上方清单为准，完整身份与理由保留在 comparison.json 和原始 presence.json / spatial.json。不要仅根据分数相等断言缺陷判断一致；不同 runs 的 group_id 不可直接对应。', '',
              '总审计状态：**'+overall+'**。audit.json 记录原图、独立输入、全部实体覆盖、静止投影、方法分支与源文件哈希检查。它验证执行产物，不证明模型语义判断正确。','']
    (root/'REPORT.md').write_text('\n'.join(lines))
    print(json.dumps(dict(report=str(root/'REPORT.md'),audit=overall,cases=[dict(case=r['case'],status=r['status']) for r in results]),ensure_ascii=False))


if __name__ == '__main__':
    main()
