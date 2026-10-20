import re,json,ast,time
from pathlib import Path
r=Path(__file__).resolve().parent
first=(r/'logs/storymem_first_terminal.log').read_text()
mp=r/'logs/storymem_memory_terminal.log';memory=mp.read_text() if mp.exists() else ''
rows={i:dict(shot=i,frames=81,width=832,height=480,seed=20260920+i,cpu_binding=[0,1,64,65] if i==1 else [24,25,26,27]) for i in range(1,5)}
init={}
for stage,log in [('t2v',first),('m2v',memory)]:
 m=re.search(r'TIMING '+stage+r'_init_seconds=([0-9.]+)',log)
 if m:init[stage]=float(m[1])
m=re.search(r'TIMING t2v_generate_seconds=([0-9.]+)',first)
if m:rows[1]['generate_seconds']=float(m[1]);rows[1]['input_memory_count']=0
for sec,scene,shot,count in re.findall(r'TIMING m2v_generate_seconds=([0-9.]+) scene=(\d+) shot=(\d+) memory_count=(\d+)',memory):rows[int(shot)].update(generate_seconds=float(sec),input_memory_count=int(count))
for typ in ['encode','keyframe_selection']:
 for sec,shot in re.findall(r'TIMING '+typ+r'_seconds=([0-9.]+) path=.*?/01_(\d+)\.mp4',memory):rows[int(shot)][typ+'_seconds']=float(sec)
p=r/'storymem_first_keyframe_recovery.json'
if p.exists():rows[1]['keyframe_selection_seconds']=json.loads(p.read_text())['seconds'];rows[1]['keyframe_selection_cpu_binding']='original contended binding; separate recovery after loader repair'
for p in (r/'outputs/storymem_official').glob('01_??.mp4'):rows[int(p.stem[-2:])]['video']=str(p)
for shot,shape,finite,minimum,maximum,std in re.findall(r'VIDEO_STATS path=.*?/01_(\d+)\.mp4 shape=(\([^\n]+?\)) finite=(True|False) min=([-0-9.]+) max=([-0-9.]+) std=([-0-9.]+)', first+'\n'+memory):
 rows[int(shot)]['tensor_stats']=dict(shape=list(ast.literal_eval(shape)),finite=finite=='True',min=float(minimum),max=float(maximum),std=float(std))
for i,row in rows.items():row['retained_memory_files']=[str(p) for p in sorted((r/'outputs/storymem_official').glob(f'01_{i:02d}_keyframe*.jpg'))]
status={}
for x in ['first','memory']:
 p=r/f'storymem_{x}_status.json'
 if p.exists():status[x]=json.loads(p.read_text())
out=dict(updated=time.time(),status='complete' if status.get('memory',{}).get('returncode')==0 else 'partial',init_seconds=init,shots=list(rows.values()),phase_status=status,api_calls=0,api_tokens=0,api_cost_usd=0,cluster_cost='unavailable; local compute is not free',notes=['First-shot encode duration unavailable; instrumented directly for memory phase.','First original phase failed after successful video generation; keyframe-only recovery succeeded.','First keyframe selection used contended CPU binding; subsequent phase uses dedicated CPUs24–27.','Only actual observed memory counts are measured; cap10 performance is not inferred as validated.'])
out['official_model_load_projection_400episodes'] = dict(t2v_loads=400,m2v_loads=400,model_load_hours=400*sum(init.values())/3600,scope='official per-episode two-invocation lifecycle; excludes interpreter/guard startup; no persistent-worker optimization assumed')
p=r/'storymem_first_quality_replay.json'
if p.exists():out['corrected_cpu_first_quality_timing_validation']=json.loads(p.read_text())
gens=[row['generate_seconds'] for i,row in rows.items() if i>1 and 'generate_seconds' in row]
if gens:
 out['generation_only_projection_400episodes']=dict(first_shots=400,memory_shots=1600,observed_memory_shots=len(gens),input_memory_counts=[row['input_memory_count'] for i,row in rows.items() if i>1 and 'generate_seconds' in row],gpu_hours_mean=(400*rows[1]['generate_seconds']+1600*sum(gens)/len(gens))/3600,gpu_hours_observed_min=(400*rows[1]['generate_seconds']+1600*min(gens))/3600,gpu_hours_observed_max=(400*rows[1]['generate_seconds']+1600*max(gens))/3600,scope='measured-low-memory generation proxy only; excludes load, encode, HPS/CLIP and unmeasured higher-memory costs; min/max are scenarios, not confidence bounds')
p=r/'storymem_capacity_projection.json'
if p.exists():out['capacity10_diagnostic_projection']=json.loads(p.read_text())
if gens:
 quality=[row['keyframe_selection_seconds'] for i,row in rows.items() if i>1 and 'keyframe_selection_seconds' in row]
 encode=[row['encode_seconds'] for i,row in rows.items() if i>1 and 'encode_seconds' in row]
 if quality and encode:
  q1=out.get('corrected_cpu_first_quality_timing_validation',{}).get('seconds')
  if q1 is not None:
   q=sum(quality)/len(quality);e=sum(encode)/len(encode)
   overhead=(400*sum(init.values())+400*q1+1600*(q+e))/3600
   genproj=out['generation_only_projection_400episodes']
   out['composition_projection_400episodes']=dict(episodes=400,shots=2000,first_shots=400,memory_shots=1600,observed_memory_encode_mean_seconds=e,missing_first_encode_proxy_additional_hours=400*e/3600,assumed_first_quality_seconds=q1,observed_memory_quality_mean_seconds=q,load_encode_quality_hours=overhead,low_memory_mean_hours=genproj['gpu_hours_mean']+overhead,low_memory_observed_min_scenario_hours=genproj['gpu_hours_observed_min']+overhead,low_memory_observed_max_scenario_hours=genproj['gpu_hours_observed_max']+overhead,cap10_compute_shape_scenario_hours=(400*rows[1]['generate_seconds']+1600*out['capacity10_diagnostic_projection']['projected_generation_seconds'])/3600+overhead,scope='single-device sequential composition estimate, not measured batch walltime; first encode omitted because unmeasured, its optional mean-encode proxy is separately reported; excludes interpreter/guard/concat/manual/recovery overhead; cap10 extrapolated from 2 steps with 13/27 expert weighting, not upper bound')
p=r/'storymem_concat_recovery.json'
if p.exists():out['concat_recovery']=json.loads(p.read_text())
p=r/'outputs/storymem_official/full_decode_audit.json'
if p.exists():
 out['full_decode_audit']=json.loads(p.read_text())
 if len(out['full_decode_audit'])==5 and all(x['passed'] for x in out['full_decode_audit']) and out.get('concat_recovery',{}).get('returncode')==0 and all('generate_seconds' in row and 'keyframe_selection_seconds' in row for row in rows.values()):out['status']='complete_with_recorded_first_quality_and_concat_recoveries'
(r/'storymem_metrics.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
