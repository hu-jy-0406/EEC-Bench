import argparse,json,statistics,csv
from pathlib import Path
R=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_text())
LABELS={'lean_center_min':'中心尺寸+逐帧中心（无重复摘要）','full':'完整输入对照','no_native':'删原坐标几何/相机','no_frame3d':'删逐帧3D','no_projection':'删跨视角投影','no_plot':'删辅助图','lean':'组合精简：中心尺寸+不确定性+配对摘要','visual':'去全部3D/保留2D框','visual_no_boxes':'去全部3D及2D框','lean_no_story':'组合精简再删情节','lean_no_prior':'组合精简再删初始解释','lean_pair_summary':'不确定性+配对摘要','lean_no_uncertainty':'中心尺寸+配对摘要','lean_no_pairdiag':'中心尺寸+不确定性','lean_centers':'组合精简+逐帧中心轨迹','lean_trajectories':'组合精简+逐帧中心与尺寸','lean_distance_only':'仅配对距离摘要','lean_geometry_only':'仅对齐中心与尺寸','lean_uncertainty_only':'仅不确定性摘要','lean_geometry_no_prior':'中心尺寸版再删初始解释'}

def main():
 a=argparse.ArgumentParser();a.add_argument('--variant',required=True);args=a.parse_args();variant=args.variant
 ds=[read(p) for p in sorted((R/'runs').glob('*/*/*/result.json'))];selected=[d for d in ds if d['variant']==variant]
 evidence=read(R/'evidence_audit.json');numeric=read(R/'downstream_audit.json')
 key=lambda d:(d['study'],d['variant'],d['repeat'])
 ev={key(x):x for x in evidence};nu={key(x):x for x in numeric}
 assert len(selected)==9 and all(d['status']=='success' for d in selected)
 assert all(d['exact_links'] and d['exact_anchors'] for d in selected)
 assert all(d['differences']['anchor_eligible']['equal'] for d in selected)
 assert all(not ev[key(d)]['both_shot_witness_violations'] and ev[key(d)]['all_witness_frames_attached'] and ev[key(d)]['original_image_bytes_preserved'] for d in selected)
 assert all(nu[key(d)]['spatial_equal'] and nu[key(d)]['distances_equal'] for d in selected)
 def stats(xs):
  us=[u for x in xs for u in x['usage']]
  return dict(calls=len(xs),mean_tokens=statistics.mean(x['total_tokens'] for x in xs),mean_input=statistics.mean(sum(u['input_tokens'] for u in x['usage']) for x in xs),mean_output=statistics.mean(sum(u['output_tokens'] for u in x['usage']) for x in xs),mean_seconds=statistics.mean(x['call_seconds'] for x in xs),median_seconds=statistics.median(x['call_seconds'] for x in xs),mean_usd=statistics.mean(x['standard_api_equivalent_usd'] for x in xs),mean_no_cache_usd=statistics.mean(sum((u['input_tokens']*10+u['output_tokens']*50)/1e6 for u in x['usage']) for x in xs))
 baseline_envelope={s:{json.dumps(d['differences']['population']['new'],sort_keys=True) for d in ds if d['study']==s and d['variant']=='full' and d['status']=='success'} for s in ['study2','study3','study4']}
 assert all(json.dumps(d['differences']['population']['new'],sort_keys=True) in baseline_envelope[d['study']] for d in selected), 'New identity partition outside full-control variation'
 comparison={s:dict(full=stats([x for x in ds if x['study']==s and x['variant']=='full']),selected=stats([x for x in selected if x['study']==s])) for s in ['study2','study3','study4']}
 result=dict(variant=variant,profile=LABELS[variant],selected_runs=len(selected),exact_partitions=sum(d['exact_population'] for d in selected),confirmed_link_preservation=all(d['exact_links'] for d in selected),anchors_preserved=True,all_partitions_within_observed_full_control_variation=True,comparison=comparison,all_trials=len(ds),validation_tokens=sum(d['total_tokens'] for d in ds),validation_api_equivalent_usd=sum(d['standard_api_equivalent_usd'] for d in ds),model='gpt-6-astra',reasoning='medium',production_default_changed=False,scope='Frozen-input identity component only; all original keyframes. No fresh downstream model calls, no independent ground truth or end-to-end speed claim.')
 (R/'selection.json').write_text(json.dumps(result,indent=2)+'\n')
 lines=['# 配准后身份复核：输入消融实验','',f'推荐候选：**{LABELS[variant]}**（`{variant}`）。完整结论见下列质量边界；不声称模型输出绝对确定，不修改生产默认。','',
 '## 实验范围','',
 '- 固定 Study2/3/4 的旧版 GeoCalib 检测、聚类、初始匹配和配准；仅重新调用身份复核。保持 Astra/medium、原始图片、完整实体范围、focused 身份输出和原校验规则。',
 '- 每组均提供 Shot1/Shot3 各6张原始帧，图片字节与分辨率完全不变。原始 canonical 输入、配准和评分几何未修改。没有重跑 GPU 前端，也没有把这些调用当作完整 pipeline 时长。',
 '- 先做输入块单项删除，再做组合与更小边界探测；完整输入重复对照。最终候选每组3次。选择查看全部试验，未删除失败/不一致结果。',
 '- 完整输入在 Study2/3 重复时也出现同一植物关联的 ambiguous/unmatched 波动；因此单项删减差异不能自动解释为因果性退化。没有人工身份真值，历史模型结果只作回归参照。','',
 '## 全部消融','',
 '| 方案 | 次数 | 通过协议校验 | 完整身份分组一致 | 确认匹配一致 | 锚点/参考一致 | 平均tokens | 平均API等价USD | 平均调用秒数 |',
 '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
 for v in LABELS:
  xs=[d for d in ds if d['variant']==v]
  if not xs:continue
  ok=[d for d in xs if d['status']=='success'];n=len(xs)
  lines.append(f'| {LABELS[v]} | {n} | {len(ok)}/{n} | {sum(d["exact_population"] for d in ok)}/{n} | {sum(d["exact_links"] for d in ok)}/{n} | {sum(d["exact_anchors"] for d in ok)}/{n} | {statistics.mean(d["total_tokens"] for d in xs):,.0f} | {statistics.mean(d["standard_api_equivalent_usd"] for d in xs):.6f} | {statistics.mean(d["call_seconds"] for d in xs):.2f} |')
 lines+=['','该表不同方案的测例/重复数不完全相同，跨行均值不能直接当作配对性能对比。逐次结果见 calls.csv；下表按同一测例对比。','',
 '## 推荐候选的重复验证','',f'- 9/9次保留全部确认匹配、锚点资格、锚点选择和参考实体；完整身份分组 {result["exact_partitions"]}/9 次与历史参照一致。',
 '- 9/9次完整分组均落在对应测例完整输入对照实际出现过的分组集合内。这个有限样本检查不能证明分布相同、统计非劣或普遍正确。',
 '- 9/9次原帧见证合法，确认匹配/拆分具备双侧见证；没有新增/丢失实体、运动重分类、坐标修改或图片降质。',
 '- 已重新计算冻结精确端点的全部 cosine 和中心距离：评测对及数值均一致。这个检查不是重新运行后续 VLM 评分；不能据此宣称所有后续模型判定/得分完全相同。','',
 '| 测例 | 完整输入重复数 | tokens：完整→精简均值 | API等价USD：完整→精简均值 | 秒数：完整→精简均值 |','|---|---:|---:|---:|---:|']
 for s,c in comparison.items():
  a,b=c['full'],c['selected'];lines.append(f'| {s} | {a["calls"]} | {a["mean_tokens"]:,.0f} → {b["mean_tokens"]:,.0f} | {a["mean_usd"]:.6f} → {b["mean_usd"]:.6f} | {a["mean_seconds"]:.2f} → {b["mean_seconds"]:.2f} |')
 lines+=['','模型输出工作量/网络/API等待未消除；输入token大幅下降不意味着时长同比下降。不同调用存在缓存与服务延迟波动，费用另保留无缓存等价值，时间仅为本实验观察，非稳定加速保证。','',
 '## 所有差异与失败','']
 for d in ds:
  tag=f'{d["study"]}/{d["variant"]}/r{d["repeat"]}'
  if d['status']!='success':lines.append(f'- `{tag}`：失败 `{d.get("error")}`；原响应与traceback保存。未修补成通过结果，费用计入。');continue
  for k,v in d['differences'].items():
   if v['equal']:continue
   lines.append(f'- `{tag}` {k}: 原有 `{[x for x in v["old"] if x not in v["new"]]}`；新有 `{[x for x in v["new"] if x not in v["old"]]}`。')
 lines+=['','## 费用与可复现性','',f'本任务全部 {len(ds)} 次请求（含失败、对照和重复）：**{result["validation_tokens"]:,} tokens / USD {result["validation_api_equivalent_usd"]:.6f} 标准 API 等价估算**，不是实际账单。',
 '费率按项目记录的 Astra USD/百万tokens：未缓存输入10、缓存输入1、输出50；缓存为输入子集，未重复计数。本实验请求低于272k输入门槛。实际 usage 保存于每次 calls/identity_review/status.json；生产候选成本与本次研发验证总费用分开。',
 '- `calls.csv`：全部请求的tokens、缓存、输出、耗时及费用。',
 '- `evidence_audit.json`：原帧字节和双侧见证检查。',
 '- `downstream_audit.json`：冻结几何下逐实体对/位移/存在性人口检查。',
 '- `runs/`：每个方案和重复的 canonical/ablation/wire 输入、prompt、图片列表、原始响应、校验、用量及差异。',
 '- `candidate_inputs/`：可审阅、可复用的三组中心/尺寸版输入（若推荐不同档，以对应runs实际输入为准）。',
 '- `PLAN.md`、各批次计划/状态、`source_snapshot/`：实验设计和版本记录。','']
 report='\n'.join(lines)+'\n'
 rationale=R/'selection_rationale.md'
 if rationale.exists():report=report.replace('## 全部消融',rationale.read_text().strip()+'\n\n## 全部消融')
 report=report.replace('- `downstream_audit.json`：冻结几何下逐实体对/位移/存在性人口检查。','- `downstream_audit.json`：冻结几何下逐实体对/位移/存在性人口检查。\n- `selected_numeric_audit.json`、最终9次`numeric_replay.json`：原始cosine、中心距离、r_e及实体分数保存并核验一致。')
 (R/'REPORT.md').write_text(report);print(json.dumps(result,indent=2))
if __name__=='__main__':main()
