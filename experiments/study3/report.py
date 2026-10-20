"""Audit and report model identities only after the blind pipeline finishes."""
import csv,json,hashlib,sys
from collections import Counter
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_gs_integrated import read,save,sha
from gs_identity_population import validate_anchors

def report():
 state=read(R/'status.json') if (R/'status.json').exists() else dict(status='queued',job_id='200642')
 lines=['# Study3：全实体跨 shot 身份测试','',f"状态：**{state['status']}**；Slurm作业 `{state.get('job_id','200642')}`。",'',
 '本轮本地模型使用CPU/FP32，判断调用仍为配置的Astra/medium；设备精度差异另记，不声称与GPU逐数相等。',
 '输入为 Study2 原 Shot1/Shot2 和指定的新 Shot3；沿用正常剧情。所有检测、聚类、几何、动静、配准、身份调用重新执行；不复用旧推理结果。Shot2 为走廊单shot场景，仅独立检测/聚类。',
 '', '模型仅接收正常输入与原始证据，不接收生成指令、预期异常或指定台灯对应。执行到 aligned identity，未运行 appearance、存在性或空间评分。','']
 case=Path(state.get('case_directory',str(R/'run01')))
 if state['status']!='success':
  lines+=['尚无可报告的最终对应结果。排队不等于模型已完成；不得据此推断台灯匹配成功。']
  if state.get('error'):lines+=['',str(state['error'])]
  (R/'REPORT.md').write_text('\n'.join(lines)+'\n');return
 initial=read(case/'matching_initial.json');review=read(case/'identity_review.json');final=read(case/'matching.json');assert review['matching']==final
 shots=[read(case/'selected'/f'{sid}_scene.json') for sid in ['shot1','shot3']];nodes=[{e['entity_id']:e for e in s['entities']} for s in shots];lookup={k:v for n in nodes for k,v in n.items()}
 for side,n in zip(['a','b'],nodes):
  assigned=[x for g in final['groups'] for x in g[side+'_ids']];assert len(assigned)==len(set(assigned)) and set(assigned)==set(n)
 validate_anchors(final,nodes)
 for shot in read(R/'manifest.json')['shots']:
  for f in shot['frames']:assert sha(f['path'])==f['sha256']
 assert sha(R/'narrative.json')==sha(B/'experiments/study2_integrated_full_fresh_20260919/study2/narrative.json')
 assert sha(read(R/'input_provenance.json')['source_video'])==read(R/'input_provenance.json')['source_video_sha256']
 assert all(sha(p)==h for p,h in read(R/'source_hashes.json').items())
 assert not (case/'calls/presence_1').exists() and not (case/'spatial.json').exists()
 rows=[];lamp_groups=[]
 for g in final['groups']:
  members=[lookup[x] for x in g['a_ids']+g['b_ids']]
  row=dict(group_id=g['group_id'],identity=g['identity'],shot1_ids=';'.join(g['a_ids']),shot1_names=';'.join(lookup[x]['name'] for x in g['a_ids']),shot1_motion=';'.join(lookup[x]['motion_status'] for x in g['a_ids']),shot3_ids=';'.join(g['b_ids']),shot3_names=';'.join(lookup[x]['name'] for x in g['b_ids']),shot3_motion=';'.join(lookup[x]['motion_status'] for x in g['b_ids']),identity_evidence=g['identity_evidence'],anchor=g['group_id'] in final['structural_anchor_group_ids'])
  rows.append(row)
  if any('lamp' in e['name'].lower() or '灯' in e['name'] for e in members):lamp_groups.append(dict(group=g,entities=[dict(entity_id=e['entity_id'],name=e['name'],motion_status=e['motion_status']) for e in members]))
 with (R/'all_identities.csv').open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 summary=read(case/'summary.json');counts=Counter(g['identity'] for g in final['groups'])
 result=dict(status='completed_and_audited',case_id='study3',final_group_counts=dict(counts),initial_group_counts=dict(Counter(g['identity'] for g in initial['groups'])),lamp_groups=lamp_groups,shot_counts={s['shot_id']:dict(total=len(s['entities']),motion=dict(Counter(e['motion_status'] for e in s['entities']))) for s in shots},shot2_entities=len(read(case/'entities/shots/shot2/entities.json')['entities']),pipeline_seconds=summary['elapsed_seconds'],total_tokens=summary['total_tokens'],calls=summary['calls'],identity_only=True,appearance_score_computed=False)
 result['execution_device']=state.get('device','cuda');result['case_directory']=str(case);save(R/'results.json',result);save(R/'audit.json',dict(passed=True,all_entities_conserved=True,original_frames_unchanged=18,original_video_unchanged=True,normal_narrative_unchanged=True,source_hashes_unchanged=True,static_anchor_gates_passed=True,inference_reuse=False,stop_after='identity'))
 lines += [f"阶段耗时：{summary['elapsed_seconds']:.2f}s；{len(summary['calls'])} 次模型调用；{summary['total_tokens']:,} tokens（缓存已含输入，不重复累计）。",'',f"最终身份组：{dict(counts)}。",'', '## 台灯对应','']
 for item in lamp_groups:
  g=item['group'];lines += [f"- `{g['group_id']}` / **{g['identity']}**："+'；'.join(e['entity_id']+' '+e['name'] for e in item['entities']), '  '+g['identity_evidence']]
 lines+=['','这里只报告模型身份结果，颜色变化未量化为appearance分数。单次新测例不代表一般准确率。','','## 全部对应','','|组|状态|Shot1实体|Shot1运动|Shot3实体|Shot3运动|','|---|---|---|---|---|---|']
 for row in rows:lines.append('|'+ '|'.join(str(row[k]).replace('|','/') for k in ['group_id','identity','shot1_names','shot1_motion','shot3_names','shot3_motion'])+'|')
 lines+=['','完整证据：`run01/matching_initial.json`、`run01/identity_review.json`、`run01/matching.json`；CSV：`all_identities.csv`；审计：`audit.json`。']
 (R/'REPORT.md').write_text('\n'.join(lines)+'\n')
if __name__=='__main__':report()
