"""Aggregate actual probes, distinguish linear-step projection from measured runs."""
import json
from pathlib import Path
R=Path(__file__).resolve().parent
rows=[]
for shots,seconds,count in [(4,20,240),(6,30,120),(8,40,40)]:
 d=R/'outputs/holocine'/f'{shots}shot_{seconds}s_2step'
 if not (d/'metrics.json').exists():continue
 m=json.loads((d/'metrics.json').read_text())
 if m.get('status')!='complete':continue
 steps=[json.loads(x) for x in (d/'step_times.jsonl').read_text().splitlines()]
 # Only successful runs are expected for these directories; fail on mixed attempts.
 assert len(steps)==2 and [s['step'] for s in steps]==[0,1]
 mean=sum(s['seconds'] for s in steps)/2
 wall=m['end']-m['start'];estimated=m['generation_seconds']+48*mean
 estimated_with_load_encode=estimated+m['load_seconds']+m['encoding_seconds']
 rows.append(dict(shots=shots,target_seconds=seconds,episodes=count,frames=m['frames'],measured_steps=2,measured_model_load_seconds=m['load_seconds'],measured_generation_seconds=m['generation_seconds'],measured_recorded_wall_seconds=wall,step_seconds=[s['seconds'] for s in steps],step_mean_seconds=mean,peak_allocated_gib=m['peak_allocated_gib'],peak_reserved_gib=m['peak_reserved_gib'],estimated_50step_generation_encoding_seconds=estimated+m['encoding_seconds'],estimated_50step_generation_encoding_hours=(estimated+m['encoding_seconds'])/3600,weighted_generation_encoding_gpu_hours=count*(estimated+m['encoding_seconds'])/3600,estimated_50step_generation_seconds=estimated,estimated_50step_generation_hours=estimated/3600,estimated_50step_with_load_encode_seconds=estimated_with_load_encode,weighted_generation_gpu_hours=count*estimated/3600,video=str(d/'video.mp4'),contactsheet=str(d/'contactsheet.jpg')))
s=R/'outputs/holocine/4shot_5s_50step/metrics.json';short=json.loads(s.read_text()) if s.exists() else None
summary=dict(rows=rows,all_requested_durations_complete=len(rows)==3,total_400_generation_encoding_gpu_hours=sum(r['weighted_generation_encoding_gpu_hours'] for r in rows) if len(rows)==3 else None,total_400_generation_gpu_hours=sum(r['weighted_generation_gpu_hours'] for r in rows) if len(rows)==3 else None,standard_sampling_short_probe=short,estimate_formula='measured two-step generation_seconds + 48 * mean of two synchronized denoising-step times; excludes model loading, encoding and validation' ,limits=['50-step 20/30/40-second runs were not executed; engineering projections are not precise bounds.', 'Two-step probes have one high-noise and one low-noise step, whereas the 50-step schedule has 21 high and 29 low; the low probe step includes an expert switch, and simple averaging repeats startup/switch cost. CFG positive/negative passes are already included and must not be doubled.', '16 fps is benchmark adaptation; the official HoloCine example saves at 15 fps.','Short 81-frame 50-step sample preserves four shots but compresses the requested episode duration.','One prompt per length; not a quality or throughput benchmark.','Recorded wall starts after Python imports; excludes download, queue, guard and initial import time.','Peak memory is measured for the executed settings, not a guaranteed upper bound for all prompts or 50-step long videos.','Existing allocations and GPUs were shared without overlapping resident processes.'],api_calls=0,api_cost_usd=0)
(R/'holocine_summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps({k:v for k,v in summary.items() if k!='standard_sampling_short_probe'},indent=2))
