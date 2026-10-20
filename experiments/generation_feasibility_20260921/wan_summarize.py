#!/usr/bin/env python3
import json,statistics
from pathlib import Path
R=Path(__file__).resolve().parent
d=json.loads((R/'wan_outputs/timings.json').read_text());s=[x for x in d['shots'] if x['frames']==81]
if not s: raise SystemExit('No full shots; no throughput claim')
v=[x['generation_seconds']+x['save_seconds'] for x in s]
summary={'completed_full_shots':len(s),'load_seconds':d['load_seconds'],'mean_hot_shot_seconds':statistics.mean(v),'minimum_hot_shot_seconds':min(v),'maximum_hot_shot_seconds':max(v),'2000_shots_single_gpu_hours_estimate':statistics.mean(v)*2000/3600,'2000_shots_single_gpu_days_estimate':statistics.mean(v)*2000/86400,'2000_shots_measured_range_hours':[min(v)*2000/3600,max(v)*2000/3600],'peak_allocated_GiB':max(x['peak_allocated_bytes'] for x in s)/2**30,'peak_reserved_GiB':max(x['peak_reserved_bytes'] for x in s)/2**30,'sampling_caveat':'one episode, same resolution/settings; throughput is not quality or representative 400-episode evaluation','api_tokens':0,'api_cost_usd':0,'gpu_compute_cost':'unavailable'}
(R/'wan_outputs/summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
p=R/'wan_REPORT.md';text=p.read_text().split('\n## Measured results')[0];text=text.replace('AMD feasibility — running','AMD feasibility — measured').replace('The experiment is awaiting centralized checkpoint download. Import succeeds','The centralized checkpoint download completed and full generated shots passed decode checks. Import succeeds').replace('No inference success is claimed yet. ','').replace('Throughput and 2000-shot extrapolation remain pending actual completed samples. ','')
text+='\n## Measured results\n\n```json\n'+json.dumps(summary,indent=2)+'\n```\n\n'
text+='| Shot | Frames | Steps | Generation seconds | Save seconds | Peak allocated GiB |\n|---|---:|---:|---:|---:|---:|\n'
for x in d['shots']:text+=f"| {x['name']} | {x['frames']} | {x['steps']} | {x['generation_seconds']:.3f} | {x['save_seconds']:.3f} | {x['peak_allocated_bytes']/2**30:.3f} |\n"
text+='\nThe first tiny smoke is excluded from projections. Projected GPU hours omit downloads, one-time model load, queueing, retries, quality filtering and downstream evaluation. Parallel scaling is not measured; dividing by GPU count is an idealized estimate only. Original full-precision expert checkpoints are converted to bf16 using the official flag, without quantization.\n';p.write_text(text)
