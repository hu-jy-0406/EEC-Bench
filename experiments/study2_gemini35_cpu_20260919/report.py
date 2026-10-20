"""Audit completed Gemini CPU results and compare with the historical Astra run."""
import csv
import itertools
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parent
B = ROOT.parents[1]
CASE = ROOT / 'run01'
BASELINE = B / 'experiments/study2_integrated_full_fresh_20260919/study2'
sys.path.insert(0, str(B / 'scripts'))
import run_gs_integrated as pipeline
import run_wedetect_shot_entities as detector

read, save = pipeline.read, pipeline.save


def main():
    runtime = read(CASE / 'pipeline_runtime.json')
    assert runtime['status'] == 'success', 'Full run has not succeeded'
    summary = pipeline.summarize(CASE, runtime)
    presence, spatial, matching = [read(CASE / name) for name in
        ['presence.json', 'spatial.json', 'matching.json']]
    groups = {group['group_id']: group for group in matching['groups']}
    shots = read(CASE / 'entities/manifest.json')['shots']
    detections = detector.load_detections(CASE / 'entities/detections', shots)
    counts, cluster_comparison = {}, {}
    box_count = 0
    for shot in shots:
        sid = shot['shot_id']
        folder = CASE / 'entities/shots' / sid
        payload = detector.make_payload(shot, detections)
        entities = read(folder / 'entities.json')
        assert detector.validate_result(read(folder / 'response.json'), payload) == entities
        counts[sid] = dict(entities=len(entities['entities']))
        box_count += sum(row['box_xyxy'] is not None for e in entities['entities'] for row in e['observations'])
        for frame in shot['frames']:
            assert pipeline.sha(frame['path']) == frame['sha256']
        graph_path = CASE / 'selected' / (sid + '_scene.json')
        if graph_path.exists():
            graph = read(graph_path)
            counts[sid].update({label: sum(e['motion_status'] == label for e in graph['entities'])
                for label in ['static', 'moving', 'unknown']})
        old_path = BASELINE / 'entities/shots' / sid / 'entities.json'
        if old_path.exists():
            old = read(old_path)
            cluster_comparison[sid] = dict(
                gemini_names=[e['name'] for e in entities['entities']],
                astra_names=[e['name'] for e in old['entities']])
    indexed = {shot['shot_id']: shot for shot in shots}
    expected_raw = []
    for index, (a, b) in enumerate(itertools.product(indexed['shot1']['frames'], indexed['shot3']['frames'])):
        name = f"{a['frame_id']:03d}_{b['frame_id']:03d}"
        expected_raw.append(name + '.npz')
        meta = read(CASE / 'registration/roma' / (name + '.json'))
        assert meta['index'] == index and meta['matches'] == 5000
        assert meta['input_hashes'] == [a['sha256'], b['sha256']]
        with np.load(CASE / 'registration/roma' / (name + '.npz')) as data:
            assert data['uvA'].shape == data['uvB'].shape == (5000, 2)
    assert {p.name for p in (CASE / 'registration/roma').glob('*.npz')} == set(expected_raw)
    checkpoint_path = ROOT / 'same_run_pair_checkpoint.json'
    if checkpoint_path.exists():
        for path, digest in read(checkpoint_path)['hashes'].items():
            assert pipeline.sha(path) == digest, 'Completed same-run pair was modified'
    provenance = read(CASE / 'provenance.json')
    source_changes = []
    for path, digest in provenance['source_hashes'].items():
        snapshot = CASE / 'code_snapshot' / Path(path).relative_to(B)
        assert pipeline.sha(snapshot) == digest
        if pipeline.sha(path) != digest:
            source_changes.append(path)
    assert not source_changes, source_changes
    nodes = {sid: {e['entity_id']: e for e in read(CASE / 'selected' / (sid + '_scene.json'))['entities']}
             for sid in ['shot1', 'shot3']}
    for sid, side in [('shot1', 'a'), ('shot3', 'b')]:
        ids = [eid for group in groups.values() for eid in group[side + '_ids']]
        assert len(ids) == len(set(ids)) and set(ids) == set(nodes[sid])
    static_groups = read(CASE / 'matching_static.json')['groups']
    for group in static_groups:
        assert all(nodes[sid][eid]['motion_status'] == 'static'
            for sid, side in [('shot1', 'a'), ('shot3', 'b')] for eid in group[side + '_ids'])
    population = spatial['population_group_ids']
    expected_pairs = {frozenset(pair) for pair in itertools.combinations(population, 2)}
    pairs = spatial['relations']
    assert len(pairs) == len(expected_pairs)
    assert {frozenset(row['endpoint_groups']) for row in pairs} == expected_pairs
    fit = spatial['registration']
    errors = []
    for row in pairs:
        if row['cosine'] is None:
            continue
        a, b = [groups[key] for key in row['endpoint_groups']]
        vectors = [np.array(nodes[sid][b[side + '_ids'][0]]['geometry']['center_world']) -
                   np.array(nodes[sid][a[side + '_ids'][0]]['geometry']['center_world'])
                   for sid, side in [('shot1', 'a'), ('shot3', 'b')]]
        vectors[1] = fit['scale'] * np.array(fit['rotation']) @ vectors[1]
        cosine = float(vectors[0] @ vectors[1] / (np.linalg.norm(vectors[0]) * np.linalg.norm(vectors[1])))
        errors.append(abs(cosine - row['cosine']))
    assert max(errors, default=0) < 1e-10
    requests = list(CASE.glob('calls/*/request.json')) + list(CASE.glob('entities/shots/*/request.json'))
    for path in requests:
        request = read(path)
        assert request['provider'] == 'google-gemini-openai-compatible'
        assert request['model'] == 'gemini-3.5-flash' and request['reasoning'] == 'medium'
        assert request['stateless'] and not request['tools_enabled'] and 'command' not in request
        raw = read(path.parent / 'gemini_response.json')
        assert raw['model'] == 'gemini-3.5-flash' and raw['choices'][0]['finish_reason'] == 'stop'
        assert request['prompt_sha256'] == pipeline.sha(path.parent / 'prompt.txt')
        assert len(request['attachments']) in [6, 12, 13]
        attached_hashes = [image['sha256'] for image in request['attachments']]
        if 'images' in request:
            assert attached_hashes == [image['sha256'] for image in request['images']]
        name = path.parent.name
        local_sid = name if name in indexed else name.removeprefix('motion_').removeprefix('observe_')
        if local_sid in indexed:
            assert attached_hashes == [frame['sha256'] for frame in indexed[local_sid]['frames']]

    assert presence['aggregation_version'] == 'single_presence_witness_v1'
    assert not (CASE / 'calls/presence_2').exists()
    api_usage = [read(path) for path in CASE.glob('**/gemini_usage.json')]
    totals = {key: sum(u['normalized'][key] for u in api_usage)
              for key in ['input_tokens', 'output_tokens', 'cached_input_tokens']}
    total_tokens = totals['input_tokens'] + totals['output_tokens']
    assert total_tokens == summary['total_tokens']
    def group_name(gid):
        group = groups[gid]
        return ' / '.join(nodes[sid][eid]['name'] for sid, side in [('shot1', 'a'), ('shot3', 'b')]
                          for eid in group[side + '_ids'])
    conflicts = [dict(group_id=row['group_id'], name=group_name(row['group_id']),
        kind=row['conflict_kind'], reason=row['reason']) for row in presence['groups'] if row['status'] == 'conflict']
    relation_conflicts = [dict(relation_id=row['relation_id'], cosine=row['cosine'],
        names=[group_name(gid) for gid in row['endpoint_groups']]) for row in pairs if row['status'] == 'conflict']
    price = ((totals['input_tokens'] - totals['cached_input_tokens']) * 1.5 +
             totals['cached_input_tokens'] * .15 + totals['output_tokens'] * 9) / 1e6
    model_stage_wall = summary['frontend_timing']['clustering_wall_seconds'] + sum(row['seconds'] for row in summary['stages'] if row['stage'] in {'motion_and_fusion', 'initial_identity', 'aligned_identity_review', 'presence', 'spatial'})
    result = dict(status='completed_and_audited', model='gemini-3.5-flash', reasoning='medium',
        device='cpu', scores=dict(presence=presence['summary'], spatial=spatial['summary']),
        entity_counts=counts, presence_conflicts=conflicts, spatial_conflicts=relation_conflicts,
        common_spatial_entities=len(population), all_pairs=len(pairs),
        negative_proposals=spatial['negative_proposals'], support_pass=spatial['support_pass'],
        wall_seconds=summary['elapsed_seconds'], model_related_stage_wall_seconds=model_stage_wall, model_calls=len(requests), total_tokens=total_tokens,
        **totals, standard_api_price_estimate_usd=price, price_source='https://ai.google.dev/gemini-api/docs/pricing',
        comparison_limit='Historical Astra run used GPU geometry and static-only identity; not a controlled model-only ablation')
    audit = dict(status='passed', original_images_unchanged=18, exact_candidate_boxes=box_count,
        source_snapshots_and_live_sources_unchanged=True, all_entity_identity_inventory_complete=True,
        static_scoring_projection_preserved=True, all_unordered_pairs_complete=True, all_36_raw_frame_pairs=True, same_run_checkpoint_hashes_unchanged=True,
        independent_cosine_max_error=max(errors, default=0), original_single_B=True,
        all_calls_gemini_stateless_medium=True, per_shot_attachment_isolation=True, codex_executions=0, usage_reconciled=True)
    save(ROOT / 'audit.json', audit)
    save(ROOT / 'result.json', result)
    save(ROOT / 'cluster_comparison.json', cluster_comparison)
    checkpoint = read(ROOT / 'same_run_pair_checkpoint.json') if (ROOT / 'same_run_pair_checkpoint.json').exists() else None
    baseline = read(BASELINE / 'summary.json')
    lines = ['# Study2：Gemini 3.5 Flash 完整 CPU pipeline', '',
        '当前 Flow1＋全部实体身份匹配＋单次 B＋完整空间评估。18 张原始 JPEG，全部从 WeDetect 重跑；Shot2 仅检测聚类。', '',
        '|指标|本次 Gemini / CPU|历史 Astra / GPU|', '|---|---:|---:|',
        f"|存在性分数|{presence['summary']['score']}|{baseline['presence']['score']}|",
        f"|空间分数|{spatial['summary']['score']}|{baseline['spatial']['score']}|",
        f"|完整墙钟秒|{summary['elapsed_seconds']:.2f}|{baseline['elapsed_seconds']:.2f}|",
        f"|模型 tokens（含推理）|{total_tokens:,}|{baseline['total_tokens']:,}|", '',
        f"模型相关阶段墙钟合计 {model_stage_wall:.2f} 秒（含轻量输入/融合及重试处理等待，组内并发不重复累加）；CPU几何与调度等待另计。",
        f"本次 {len(requests)} 次 Gemini 调用，输入 {totals['input_tokens']:,}，输出含推理 {totals['output_tokens']:,}。",
        f"按官方标准价估算 ${price:.4f}，并非账户实际账单；不含独立 API 探针、开发和审计。",
        '[官方价格](https://ai.google.dev/gemini-api/docs/pricing)：输入 $1.50/M、输出含推理 $9/M、缓存输入 $0.15/M。', '',
        '## 检测到的缺陷', '']
    lines += [f"- 存在性：{row['name']}；{row['kind']}。" for row in conflicts]
    lines += [f"- 空间：{' ↔ '.join(row['names'])}；cosine={row['cosine']:.12f}。" for row in relation_conflicts]
    if not conflicts and not relation_conflicts:
        lines.append('- 未确认冲突。高分不能解释为所有实体和空间关系均已验证一致。')
    lines += ['', '## 覆盖与比较边界', '', f'实体数和动静划分：`{json.dumps(counts, ensure_ascii=False)}`。',
        f"存在性 C/K/U/E：{[presence['summary'][k] for k in ['C','K','U','E']]}。",
        f"空间：{len(population)} 个共同静态实体，{len(pairs)} 对，{spatial['negative_proposals']} 个负 cosine，{spatial['support_pass']} 对通过支撑门槛。",
        '历史 Astra 结果确认台灯消失、纸巾新增和杯子—笔筒关系冲突。对比需看这些缺陷及 unknown，不能仅比较分数高低。',
        '历史完整结果使用 GPU 混合精度、旧静态身份总体、仅 Shot1/Shot3；本次为 CPU FP32、全实体身份总体并增加 Shot2 聚类。不是纯模型替换的受控消融，不能据此断言速度或准确率优劣。',
        'medium 是各服务自己的推理设置，不表示两者投入相同计算量。单案例单次结果，尚无人工准确率标注。', '',
        '## 阶段耗时与 tokens', '', '|阶段|秒|tokens|', '|---|---:|---:|']
    lines += [f"|{row['stage']}|{row['seconds']:.2f}|{row['total_tokens']:,}|" for row in summary['stages']]
    lines += ['', '审计通过：原图、原候选框、源代码快照、全实体匹配守恒、静态评分投影、全部无序对和独立 cosine 重算、单 B、全部 Gemini 调用及 token 对账。',
        '详见 `audit.json`、`result.json`、`run01/calls.csv`、`run01/stages.csv` 及逐调用原始 Gemini 响应。']
    if (CASE / 'calls/identity_review_attempt1').exists():
        lines += ['', '模型重试：第一次配准后身份复核只输出4/29个初始组审查项，原完整性校验拒绝该结果；失败响应和用量完整保留。随后仅作一次全请求哈希相同的独立重试。总调用数、tokens、费用和墙钟均包含第一次失败与重试处理等待，未放宽原校验或人工补写判断。']
    if (ROOT / 'frontend_comparison.json').exists():
        lines += ['', '前端精确对比：与历史 Astra 相比，候选 ID、原框、类别和原图完全一致，置信度最大浮点差为5.31e-6。Shot1保留20个完全相同候选聚类，但拒绝黑笔；Shot3保留19个完全相同聚类，拒绝两个花盆，并删除地毯重复候选。详见 frontend_comparison.json；这些是模型差异，未人工改写。']
    if checkpoint is not None:
        lines += ['', 'CPU 调度说明：开始使用四线程串行 RoMa，随后显式保留本次已完成的 ' + str(len(checkpoint['files'])) + ' 对结果，改用两个独立 worker 各四线程完成剩余图像对。仍为全部 36 对、原 precise 设置和原逐对种子；不复用历史推理。', '总墙钟和 RoMa 阶段耗时包含串行尝试、中断及切换开销；GPU始终隐藏，worker合计RSS限制24GiB。中间四worker尝试因RSS峰值超过限制被保护程序终止，完整失败日志保留；没有模型判断重试。']
    (ROOT / 'REPORT.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
