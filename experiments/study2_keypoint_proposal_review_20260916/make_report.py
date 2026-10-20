"""Publish actual review outputs and an original-pixel witness browser."""
import base64,collections,csv,html,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));from run_review import read,save,sha,owned_compute_job,BASE,SOURCE
owned_compute_job();out=HERE/'run01';state=read(out/'run.json');assert state['status']=='success';summary=read(out/'summary.json');rows=read(out/'results.json');manifest=read(out/'input_manifest.json');assert read(out/'audit.json')['passed']
cn={'g01':'墙上风景画','g02':'深绿色杯子','g04':'大桌子','g06':'笔筒','g07':'窗台垂吊植物','g10':'地毯','g11':'椅子','g12':'暖气片','g13':'窗台花盆','g16':'小木桌/花架','g17':'小木桌上的植物'}
reasons={'reference_entity_is_endpoint':'包含参考物端点，旧版规则不评估','no_verified_common_support_in_both_shots':'未通过两侧共同支撑筛选','negative_cosine_candidate_plus_independent_local_order_and_cross_shot_visual_evidence':'独立局部顺序与跨shot复核通过','failed_single_shot_or_cross_shot_visual_gate':'单shot或跨shot证据未通过'}
confirmed=[r for r in rows if r['status']=='conflict'];target=next(r for r in rows if set(r['endpoint_groups'])=={'g02','g06'});counts=collections.Counter(r['filter_reason'] for r in rows)
usage=collections.Counter()
for c in state['calls']:
 for u in c.get('usage',[]):
  for k,v in u.items():
   if isinstance(v,(int,float)):usage[k]+=v
summary.update(token_usage=dict(usage),total_input_output_tokens=usage['input_tokens']+usage['output_tokens'],support_filter_counts=dict(counts),target_pair_status=target['status']);save(out/'summary.json',summary)
with (out/'proposals_review.csv').open('w') as f:
 w=csv.writer(f);w.writerow(['relation_id','entity_a','entity_b','cosine','common_support_pass','verifier_verdict','final_status','reason'])
 for r in rows:w.writerow([r['relation_id'],*[cn[g] for g in r['endpoint_groups']],r['cosine'],r['common_support_eligible'],r['verification']['verdict'] if r['verification'] else 'not_reviewed',r['status'],reasons.get(r['final_reason'],r['final_reason'])])
lines=['# Study2：关键点配准负 cosine 候选，接入 v1.2 视觉复核','',f'**实际结果：31 对候选中，{len(confirmed)} 对最终确认冲突。杯子—笔筒：{target["status"]}。**','', '## 各阶段实际数量','', '| 阶段 | 数量 |','|---|---:|','| 冻结的静态交集关系总数 | 55 |','| cosine < 0 候选 | 31 |',f'| 包含桌子/暖气片参考物端点，旧规则不评估 | {counts["reference_entity_is_endpoint"]} |',f'| 未通过两侧共同支撑条件 | {counts["no_verified_common_support_in_both_shots"]} |',f'| 进入跨 shot 原帧复核 | {summary["cross_shot_reviewed"]} |',f'| 最终确认冲突 | {len(confirmed)} |',f'| 候选中保留未知 | {summary["unknown"]} |','', '**其余候选没有被证明一致或判定为误报；多数是在旧版适用范围筛选时退出。** 另外24对非负cosine没有进入本次复核，所以本实验不提供完整55对关系的准确率。','', '## 杯子—笔筒实际证据','',f'冻结的 RoMa 对齐候选 cosine={target["cosine"]:.9f}，夹角={target["angle_deg"]:.3f}°。未重新拟合旋转、尺度、平移或框。','', '| 物理局部轴（杯子中心减笔筒中心） | Shot1独立观测 | Shot3独立观测 | 证据门槛 |','|---|---|---|---|']
for axis,d in target['local_axis_evidence'].items():lines.append(f'| {axis} | {d["orders"][0]} | {d["orders"][1]} | {"两侧支持反转" if d["opposite_supported"] else "未确认反转"} |')
v=target['verification']
if v:
 lines+=['',f'跨 shot 模型结论：**{v["verdict"]}**。', '',v['reason'],'','仍存在的限制：'+v['remaining_alternatives'],'','| 复核条件 | 是否通过 |','|---|---|']
 for k in ['identity_supported','anchors_supported','common_support_verified','reference_correspondence_verified','center_semantics_verified','geometry_error_excluded','viewpoint_only_explanation_excluded']:lines.append(f'| {k} | {v[k]} |')
lines+=['', '## 本次实际执行 Pipeline','', '1. 冻结上次 RoMa v2 + Pi3X + Boxer 的31对负cosine候选及源文件哈希；排序仅按实体ID，不按目标异常或历史结论。原始55对关系、单shot场景、变换均未修改。','2. 用两个新鲜隔离的 gpt-6-astra/medium 上下文，各自只输入本shot的6张原JPEG、静态实体图、逐帧框/相机和本shot桌子—暖气片参考系。单shot prompt与冻结v1.2逐字节相同。没有输入对方shot、历史评分、已知错误或31对候选清单。','3. 分别核实9个非参考共同实体的支撑物；对有共同桌面支撑的实体对枚举3个局部轴。两边这次均只生成杯子—笔筒的3个轴观测。','4. 将这些共同支撑记录应用到全部31对负cosine候选：9对因包含参考物端点退出，21对缺少两侧共同支撑证据，1对进入跨shot复核。没有把30对退出项标为相容。','5. 一次新的跨shot gpt-6-astra/medium调用，读取全部12张原JPEG、冻结图/对应、剩余候选的原始cosine与向量、实际变换与重投影验证误差，以及两个独立shot的观测。复核身份、参考物、共同支撑、参考方向对应、中心语义、几何误差和纯视角解释，每侧至少2个不同帧见证。','6. 确认冲突要求7项跨shot条件全部通过、双方帧数合格，并且至少一个局部物理轴在两个独立观测中支持相反中心顺序，且无可反转顺序的几何替代解释。候选的负cosine本身不能直接扣分。','', '## 与原 v1.2 相同和不同的部分','', '- 相同：单shot prompt与输出schema、共同支撑和参考物端点排除规则、原7项视觉门槛、每侧至少两帧和独立局部顺序要求。','- 不同：proposal来自冻结关键点配准的cosine<0，而非旧版局部轴误差区间严格异号。跨shot prompt相应适配数值输入，并提供此次真实配准误差；没有借用历史几何区间或历史复核结论。详见 [prompt差异](verify_prompt.diff)。','- 最终用于确认的证据来自桌子—暖气片局部参照下的原图关系。这不能倒推RoMa全局变换已经正确，也不能说明单看cosine能唯一定位该异常。','- 本次是一次实际样例测试，使用同一个模型的独立上下文，不是统计独立的准确率检验。没有重新测试存在性或更改旧版总分。','', '## 调用与审计','',f'实际3次模型调用：{usage["input_tokens"]} input + {usage["output_tokens"]} output = {summary["total_input_output_tokens"]} tokens。', '', '两次单shot响应首次返回后，所用Python环境缺少jsonschema，导致本地校验报错。已保留原始失败日志和响应，通过具备依赖的CPU环境验证并恢复；没有重新模型取样。第三次调用正常完成。记录见 [validation_recovery.json](validation_recovery.json)。','', '3项复核边界测试通过：未知/几何误差/重复帧阻断、同号不成冲突、端点顺序规范化与缺失支撑。输入哈希、12张原图、两个上下文隔离、单shot prompt一致、31候选完整台账及跨shot精确覆盖审计通过。原图没有重编码。','', '## 全部31对候选台账','','| 实体对 | cosine | 处理结果 | 原因 |','|---|---:|---|---|']
for r in rows:lines.append('| '+' ↔ '.join(cn[g] for g in r['endpoint_groups'])+f' | {r["cosine"]:.4f} | {r["status"]} | '+reasons.get(r['final_reason'],r['final_reason'])+' |')
lines+=['', '## 文件','', '- [完整CSV](proposals_review.csv) / [完整JSON含所有门槛](results.json)','- [原帧与实际见证](evidence.html)','- [实际跨shot模型输出](verified_relations.json)','- [两个隔离shot输出](shot_relations.json)','- [审计](audit.json) / [数值候选](proposals.json) / [协议](../PLAN.md)']
(out/'REPORT.md').write_text('\n'.join(lines)+'\n')
# Self-contained original JPEG viewer; SVG rectangles are separate overlays, never image re-encoding.
imgs={(f['shot_id'],f['frame_id']):f for fs in manifest['images'] for f in fs};page=['<!doctype html><html lang="zh"><meta charset="utf-8"><title>Study2 proposal review evidence</title><style>body{font:16px system-ui;margin:25px auto;max-width:1200px;padding:15px;background:#f4f6f8}section{background:white;padding:20px;margin:15px 0}svg{width:100%;height:auto}p{line-height:1.7}pre{white-space:pre-wrap}</style><h1>实际复核：原始JPEG与见证区域</h1><p>绿色：第一个端点；橙色：第二个端点；蓝色虚线：参考区域。坐标来自实际模型回复。图像字节未修改；不把矩形当成真实3D中心。</p>']
for r in rows:
 if not r['verification']:continue
 v=r['verification'];page.append('<section><h2>'+html.escape(' ↔ '.join(cn[g] for g in r['endpoint_groups']))+' / '+v['verdict']+'</h2><p>'+html.escape(v['reason'])+'</p>')
 for side,sid in [('a','shot1'),('b','shot3')]:
  for w in v['witnesses_'+side]:
   f=imgs[sid,w['frame_id']];data=base64.b64encode(Path(f['path']).read_bytes()).decode();page.append(f'<h3>{sid}, frame {w["frame_id"]}</h3><svg viewBox="0 0 852 480"><image width="852" height="480" href="data:image/jpeg;base64,{data}"/>')
   for key,color in [('subject_region_xyxy','#21ed6c'),('object_region_xyxy','#ffaa24'),('reference_region_xyxy','#23cbff')]:
    x1,y1,x2,y2=w[key];dash=' stroke-dasharray="7 5"' if key.startswith('reference') else '';page.append(f'<rect x="{x1}" y="{y1}" width="{x2-x1}" height="{y2-y1}" fill="none" stroke="{color}" stroke-width="2"{dash}/>')
   page.append('</svg><p>'+html.escape(w['observation'])+'</p>')
 page.append('<p>限制：'+html.escape(v['remaining_alternatives'])+'</p></section>')
page.append('</html>');(out/'evidence.html').write_text(''.join(page))
print(json.dumps(summary,ensure_ascii=False,indent=2));print(out/'REPORT.md')
