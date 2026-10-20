"""Audit completed fresh cases and report observed outcomes, never inference inputs."""
import csv,json,sys
from pathlib import Path
import numpy as np
H=Path(__file__).resolve().parent;B=H.parents[1]
sys.path.insert(0,str(B/'scripts'))
import run_gs_integrated as flow
import run_wedetect_shot_entities as detector
read=flow.read;save=flow.save
results={}
for case in ['study0','study1']:
    C=H/case;s=read(C/'summary.json')
    assert s['status']=='success' and s['completed_through']=='spatial'
    assert s['runtime_profile']['name']=='safe_spatial_medium'
    assert not (C/'calls/presence_2').exists()
    presence=read(C/'presence.json');spatial=read(C/'spatial.json')
    matching=read(C/'matching.json');gm={g['group_id']:g for g in matching['groups']}
    shots=read(C/'entities/manifest.json')['shots']
    assert read(C/'entities/run.json')['detector_mode']=='fresh'
    dets=detector.load_detections(C/'entities/detections',shots);counts={};boxes=0
    for shot in shots:
        sid=shot['shot_id'];root=C/'entities/shots'/sid
        payload=detector.make_payload(shot,dets)
        assert detector.validate_result(read(root/'response.json'),payload)==read(root/'entities.json')
        es=read(root/'entities.json')['entities']
        boxes+=sum(o['box_xyxy'] is not None for e in es for o in e['observations'])
        graph=read(C/'selected'/f'{sid}_scene.json')
        counts[sid]={k:sum(e['motion_status']==k for e in graph['entities']) for k in ['static','moving','unknown']}
        counts[sid]['entities']=len(es)
        for f in shot['frames']:assert flow.sha(f['path'])==f['sha256']
    prov=read(C/'provenance.json')
    assert prov['inference_reuse'] is False
    assert all(flow.sha(p)==v for p,v in prov['source_hashes'].items())
    nodes={sid:{e['entity_id']:e for e in read(C/'selected'/f'{sid}_scene.json')['entities']} for sid in ['shot1','shot3']}
    fit=spatial['registration'];rotation=np.array(fit['rotation']);scale=fit['scale']
    errors=[];pairs=spatial['relations'];n=len(spatial['population_group_ids'])
    assert len(pairs)==n*(n-1)//2
    assert len({tuple(sorted(p['endpoint_groups'])) for p in pairs})==len(pairs)
    for row in pairs:
        a,b=[gm[k] for k in row['endpoint_groups']];v=[]
        for sid,side in [('shot1','a'),('shot3','b')]:
            v.append(np.array(nodes[sid][b[side+'_ids'][0]]['geometry']['center_world'])-np.array(nodes[sid][a[side+'_ids'][0]]['geometry']['center_world']))
        v[1]=scale*rotation@v[1];den=np.linalg.norm(v[0])*np.linalg.norm(v[1])
        if row['cosine'] is not None:
            assert den>0
            errors.append(abs(float(v[0]@v[1]/den)-row['cosine']))
    assert max(errors,default=0)<1e-10
    requests=list(C.glob('calls/*/request.json'))+list(C.glob('entities/shots/*/request.json'))
    for p in requests:
        cmd=read(p)['command']
        assert cmd[cmd.index('--model')+1]=='gpt-6-astra'
        assert 'model_reasoning_effort="medium"' in cmd and '--ephemeral' in cmd
        assert 'web_search="disabled"' in cmd
    conflicts=[dict(group_id=row['group_id'],kind=row['conflict_kind'],reason=row['reason'],identity=gm[row['group_id']]) for row in presence['groups'] if row['status']=='conflict']
    unknown_groups=[dict(group_id=row['group_id'],reason=row['reason'],identity=gm[row['group_id']]) for row in presence['groups'] if row['status']=='unknown']
    spatial_conflicts=[r for r in pairs if r['status']=='conflict']
    if not spatial_conflicts:assert spatial['summary']['score']==100
    audit=dict(status='passed',original_frames_unchanged=True,all_boxes_exact_detector_candidates=True,nonnull_detector_boxes=boxes,source_hashes_unchanged=True,independent_cosine_max_error=max(errors,default=0),all_unordered_pairs=True,one_B_call=True,model='gpt-6-astra',reasoning='medium',actual_calls=len(s['calls']),inference_reuse=False)
    save(C/'audit.json',audit)
    result=dict(scores=dict(presence=presence['summary'],spatial=spatial['summary']),entity_counts=counts,presence_conflicts=conflicts,unknown_groups=unknown_groups,spatial_conflicts=spatial_conflicts,population=n,pairs=len(pairs),negative_proposals=spatial['negative_proposals'],support_pass=spatial['support_pass'],elapsed_seconds=s['elapsed_seconds'],total_tokens=s['total_tokens'],calls=len(s['calls']),input_tokens=sum(x['input_tokens'] for x in s['calls']),output_tokens=sum(x['output_tokens'] for x in s['calls']),cached_input_tokens=sum(x['cached_input_tokens'] for x in s['calls']),audit=audit)
    save(C/'result.json',result);results[case]=result
    with (C/'all_pairs.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=['relation_id','endpoint_groups','cosine','status','reason'],extrasaction='ignore');writer.writeheader();writer.writerows(pairs)
save(H/'results.json',results)
labels={'detection_and_clustering':'WeDetect＋实体聚类','geocalib':'GeoCalib','prepare_shot_inputs':'几何输入整理','pi3x_shot1':'Pi3X Shot1','boxer_shot1':'Boxer Shot1','pi3x_shot3':'Pi3X Shot3','boxer_shot3':'Boxer Shot3','motion_and_fusion':'独立动静划分＋融合','initial_identity':'初始身份对应 A＋A′','roma_matches':'RoMa 多帧匹配','lift_correspondences':'对应点筛选与提升','registration':'场景配准','aligned_identity_review':'配准后身份复核','presence':'单次 B 分类','spatial':'空间关系评测'}
lines=['# Study0 / Study1：当前 pipeline 完整新评测','',
'版本 `gs-consistency-two-scores-v1`，Flow1，运行配置 `safe_spatial_medium`，所有模型调用均为 GPT-6 Astra / medium。每组仅比较 Shot1–Shot3；Shot2 情节保留在正常 narrative 中，本轮没有计算 Shot2。',
'', '每组使用 12 张原始 JPEG：Study0 852×480，Study1 854×480。没有重新保存、缩放图片，也没有复用旧检测、聚类、几何、配准或模型判断。两组单独运行、单 shot 判断相互隔离。',
'', '| Case | 静止实体一致性 | 空间关系一致性 | 墙钟秒数 | Codex tokens | 调用次数 |','|---|---:|---:|---:|---:|---:|']
for c,r in results.items():lines.append(f"| {c} | {r['scores']['presence']['score']:.2f} | {r['scores']['spatial']['score']:.2f} | {r['elapsed_seconds']:.2f} | {r['total_tokens']:,} | {r['calls']} |")
lines+=['','时间为各 case 从 WeDetect 到最终分数的实际墙钟，包含流水线内部等待；不包含排队、任务准备、报告审计和本次主对话。Token 仅统计 pipeline 调用，缓存输入是输入的子集，没有重复计数。RoMa 与动静/初始身份步骤有重叠，各阶段用时之和不等于总墙钟。', '', '## 各阶段耗时与 token','', '| 阶段 | Study0 秒 | Study0 tokens | Study1 秒 | Study1 tokens |','|---|---:|---:|---:|---:|']
stages={c:{s['stage']:s for s in read(H/c/'summary.json')['stages']} for c in results}
for key,label in labels.items():
    a,b=stages['study0'][key],stages['study1'][key]
    lines.append(f"| {label} | {a['seconds']:.2f} | {a['total_tokens']:,} | {b['seconds']:.2f} | {b['total_tokens']:,} |")
for c,r in results.items():
    lines+=['',f'## {c}：实际结果','',f"实体/动静数量：`{json.dumps(r['entity_counts'],ensure_ascii=False)}`。",'',f"存在性计数：`{json.dumps(r['scores']['presence'],ensure_ascii=False)}`。",'', '确认的存在性冲突：','']
    for x in r['presence_conflicts']:
        reason=x['reason'];reason='；'.join(reason) if isinstance(reason,list) else str(reason)
        lines.append(f"- {x['group_id']} / {x['kind']}：{reason}")
    if not r['presence_conflicts']:lines.append('- 无。')
    lines+=['', '保留为未知、不扣分的组：','']
    for x in r['unknown_groups']:
        reason=x['reason'];reason='；'.join(reason) if isinstance(reason,list) else str(reason)
        lines.append(f"- {x['group_id']}：{reason}")
    if not r['unknown_groups']:lines.append('- 无。')
    lines+=['',f"空间共同实体 {r['population']} 个，全部无序实体对 {r['pairs']} 对，负 cosine {r['negative_proposals']}，通过局部支撑筛选 {r['support_pass']}，最终确认冲突 {len(r['spatial_conflicts'])} 对。"]
    for x in r['spatial_conflicts']:lines.append(f"- {' ↔ '.join(x['endpoint_groups'])}，cosine={x['cosine']:.12f}：{x['reason']}")
    lines+=['',f"输入 {r['input_tokens']:,}；输出 {r['output_tokens']:,}；其中缓存输入 {r['cached_input_tokens']:,}。",'',f"[完整身份/存在性判断]({H/c/'presence.json'}) · [全部空间关系]({H/c/'all_pairs.csv'}) · [逐调用时间和 token]({H/c/'calls.csv'}) · [审计]({H/c/'audit.json'})"]
lines+=['','## 审计与限制','',
'两组均通过原图哈希、原始检测框及候选完整覆盖、源代码哈希、全部无序对与 cosine 独立重算、单次 B、Astra medium 和独立临时上下文检查。',
'', '身份复核提示词将原先写死的 852×480 改为读取每帧 image_size；原图和评分规则未改动。',
'', '首次作业 200015 在模型启动前因 Slurm 全局 GPU 编号与 cgroup 内可见编号不同退出；零模型调用。修复启动编号解析后使用作业 200016；每次 GPU 推理均保留原 idle/VRAM/KFD/UUID 检查。',
'', '100 分表示本流程没有确认需要扣分的冲突，不表示所有实体和空间关系都经过肯定一致的确认。此处是两个测例各一次新运行，不能据此保证其他场景或重复运行完全相同。']
(H/'REPORT.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({c:{k:r[k] for k in ['scores','entity_counts','population','pairs','negative_proposals','elapsed_seconds','total_tokens','calls']} for c,r in results.items()},ensure_ascii=False,indent=2))
