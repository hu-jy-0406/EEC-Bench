"""Audit and report this fresh run; no inference or corrections."""
import csv,json,sys,hashlib,math,shutil
from pathlib import Path
import numpy as np
H=Path(__file__).resolve().parent;B=H.parents[1];C=H/'study2';sys.path.insert(0,str(B/'scripts'))
import run_gs_integrated as flow
import run_wedetect_shot_entities as detector
read=flow.read;save=flow.save
runtime=read(C/'pipeline_runtime.json');assert runtime['status']=='success'
s=flow.summarize(C,runtime);presence=read(C/'presence.json');spatial=read(C/'spatial.json');matching=read(C/'matching.json');gm={g['group_id']:g for g in matching['groups']}
assert s['completed_through']=='spatial' and s['spatial_evaluation_run']
assert not (C/'calls/presence_2').exists()
shots=read(C/'entities/manifest.json')['shots'];dets=detector.load_detections(C/'entities/detections',shots);counts={};boxes=0
for shot in shots:
 sid=shot['shot_id'];root=C/'entities/shots'/sid;payload=detector.make_payload(shot,dets)
 assert detector.validate_result(read(root/'response.json'),payload)==read(root/'entities.json')
 es=read(root/'entities.json')['entities'];boxes+=sum(o['box_xyxy'] is not None for e in es for o in e['observations'])
 graph=read(C/'selected'/f'{sid}_scene.json');counts[sid]={k:sum(e['motion_status']==k for e in graph['entities']) for k in ['static','moving','unknown']};counts[sid]['entities']=len(es)
 for f in shot['frames']:assert flow.sha(f['path'])==f['sha256']
prov=read(C/'provenance.json');assert all(flow.sha(p)==v for p,v in prov['source_hashes'].items())
for source_path,digest in prov['source_hashes'].items():
 source_path=Path(source_path);dest=H/'code_snapshot'/source_path.relative_to(B)
 if dest.exists():assert flow.sha(dest)==digest
 else:dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source_path,dest)
nodes={sid:{e['entity_id']:e for e in read(C/'selected'/f'{sid}_scene.json')['entities']} for sid in ['shot1','shot3']}
fit=spatial['registration'];R=np.array(fit['rotation']);scale=fit['scale'];errors=[];pairs=spatial['relations'];n=len(spatial['population_group_ids']);assert len(pairs)==n*(n-1)//2
for row in pairs:
 a,b=[gm[k] for k in row['endpoint_groups']];v=[]
 for sid,side in [('shot1','a'),('shot3','b')]:v.append(np.array(nodes[sid][b[side+'_ids'][0]]['geometry']['center_world'])-np.array(nodes[sid][a[side+'_ids'][0]]['geometry']['center_world']))
 v[1]=scale*R@v[1];den=np.linalg.norm(v[0])*np.linalg.norm(v[1])
 if row['cosine'] is not None:errors.append(abs(float(v[0]@v[1]/den)-row['cosine']))
assert max(errors,default=0)<1e-10
for p in list(C.glob('calls/*/request.json'))+list(C.glob('entities/shots/*/request.json')):
 req=read(p);cmd=req['command'];assert cmd[cmd.index('--model')+1]=='gpt-6-astra'
 assert 'model_reasoning_effort="medium"' in cmd and '--ephemeral' in cmd
 assert 'web_search="disabled"' in cmd
conflicts=[]
for row in presence['groups']:
 if row['status']=='conflict':conflicts.append(dict(group_id=row['group_id'],kind=row['conflict_kind'],reason=row['reason'],identity=gm[row['group_id']]))
spatial_conflicts=[r for r in pairs if r['status']=='conflict']
audit=dict(status='passed',original_frames_unchanged=True,all_boxes_exact_detector_candidates=True,nonnull_detector_boxes=boxes,source_hashes_unchanged=True,independent_cosine_max_error=max(errors,default=0),all_unordered_pairs=True,one_B_call=True,model='gpt-6-astra',reasoning='medium',actual_calls=len(s['calls']),new_model_tokens=s['total_tokens'],inference_reuse=False)
save(H/'audit.json',audit)
result=dict(scores=dict(presence=presence['summary'],spatial=spatial['summary']),entity_counts=counts,presence_conflicts=conflicts,spatial_conflicts=spatial_conflicts,population=n,pairs=len(pairs),negative_proposals=spatial['negative_proposals'],support_pass=spatial['support_pass'],elapsed_seconds=s['elapsed_seconds'],total_tokens=s['total_tokens'],calls=len(s['calls']),input_tokens=sum(x['input_tokens'] for x in s['calls']),output_tokens=sum(x['output_tokens'] for x in s['calls']),cached_input_tokens=sum(x['cached_input_tokens'] for x in s['calls']))
save(H/'result.json',result)
with (C/'all_pairs.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=['relation_id','endpoint_groups','cosine','status','reason'],extrasaction='ignore');w.writeheader();w.writerows(pairs)
labels={'detection_and_clustering':'WeDetect＋聚类','geocalib':'GeoCalib','prepare_shot_inputs':'几何输入整理','pi3x_shot1':'Pi3X Shot1','boxer_shot1':'Boxer Shot1','pi3x_shot3':'Pi3X Shot3','boxer_shot3':'Boxer Shot3','motion_and_fusion':'独立动静划分＋融合','initial_identity':'初始身份对应 A＋A′','roma_matches':'RoMa 多帧匹配','lift_correspondences':'对应点筛选与提升','registration':'场景配准','aligned_identity_review':'配准后身份复核','presence':'单次 B 分类','spatial':'原空间关系完整评测'}
lines=['# Study2：简化前段＋原空间关系完整重跑','',f"模型：gpt-6-astra / medium。12 张原始 JPEG；从 WeDetect 起全部重新推理，没有复用先前检测、实体、几何、配准或判断结果。",'',f"最终分数：静止实体一致性 **{presence['summary']['score']:.6f}**；空间关系一致性 **{spatial['summary']['score']:.6f}**。",'',f"总墙钟 **{s['elapsed_seconds']:.3f} 秒**，**{s['total_tokens']:,} tokens**，**{len(s['calls'])} 次 Codex 调用**。输入 {result['input_tokens']:,}，输出 {result['output_tokens']:,}；缓存输入 {result['cached_input_tokens']:,} 已包含在输入中。不含本任务对话、准备/测试/报告时间。",'','|阶段|秒|Token|','|---|---:|---:|']
for row in s['stages']:
 if row['stage']=='detection_and_clustering':
  cluster=s['frontend_timing']['clustering_wall_seconds']
  lines.append(f"|WeDetect＋准备/检查|{row['seconds']-cluster:.2f}|0|")
  lines.append(f"|独立实体聚类|{cluster:.2f}|{row['total_tokens']:,}|")
 else:lines.append(f"|{labels[row['stage']]}|{row['seconds']:.2f}|{row['total_tokens']:,}|")
lines += ['', '并行的聚类、动静和局部取证按阶段墙钟统计，不把两个调用耗时相加。逐调用细节在 study2/calls.csv。', '', '## 结果与证据', '',f'单 shot 数量：`{json.dumps(counts,ensure_ascii=False)}`。',f'共同空间实体 {n}，全部无序对 {len(pairs)}，负 cosine {spatial["negative_proposals"]}，通过支撑筛选 {spatial["support_pass"]}，最终冲突 {len(spatial_conflicts)}。','', '存在性冲突：']
for c in conflicts:lines.append('- '+c['group_id']+' / '+c['kind']+'：'+'；'.join(c['reason']))
lines += ['','空间关系确认冲突：']
for r in spatial_conflicts:lines.append('- '+' ↔ '.join(r['endpoint_groups'])+f"，cosine={r['cosine']:.12f}，"+r['reason'])
lines += ['', '## 比较口径', '', '历史原版完整 fresh run 为1807.020秒、1,127,920 tokens、11次调用，存在性86.666667、空间96.428571。该历史前端还生成补框，静态实体共38个；本次使用当前候选原框前端，不能把全部结果差异归因于仅删除一次 B。不同节点/缓存/服务响应也会影响耗时。',f"本次相对该历史总 token 变化 {100*(s['total_tokens']/1127920-1):+.2f}%，总墙钟变化 {100*(s['elapsed_seconds']/1807.020-1):+.2f}%。单次实验，不代表稳定速度或整体准确率。",'', '## 审计', '', '原图哈希、原检测框来源、完整实体对总体、独立重算cosine、配置代码哈希和单次B记录均通过。详见 audit.json、result.json、study2/summary.json；原空间评测主体AST与历史版本一致，只有单次B聚合版本兼容。']
(H/'REPORT.md').write_text('\n'.join(lines)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2))
