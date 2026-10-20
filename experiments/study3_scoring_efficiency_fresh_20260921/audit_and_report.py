"""Independent accounting and evidence audit for the fresh optimized Study3 run."""
import hashlib,json,math,sys
from pathlib import Path
R=Path(__file__).resolve().parent;C=R/'run';B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
import gs_entity_displacement as disp
import gs_prompt_alignment as alignment
from run_isolated_shot_static_3d import owned_compute_job

def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')

def main():
 owned_compute_job()
 outer=read(R/'execution.json');run=read(C/'pipeline_runtime.json');summary=read(C/'summary.json');source=read(C/'provenance.json');input_audit=read(R/'input_audit.json')
 assert outer['status']==run['status']==summary['status']=='success'
 assert all(s['status']=='success' and s['returncode']==0 for s in run['stages'])
 assert not source['inference_reuse']
 assert read(C/'runtime_profile.json')['name']=='scoring_efficiency_v1'
 assert read(C/'scheduling.json')['name']=='parallel_v2'
 for p,h in source['source_hashes'].items():
  assert sha(p)==h and input_audit['source_snapshot'][p]['sha256']==h
  assert sha(input_audit['source_snapshot'][p]['snapshot'])==h
 frames=[f for s in read(C/'raw_manifest.json')['shots'] for f in s['frames']]
 assert len(frames)==18
 for f in frames:assert sha(f['path'])==f['sha256']
 detector=read(C/'entities/run.json');assert detector['status']=='success' and detector['detector_mode']=='fresh'
 for sid in ('shot1','shot2','shot3'):
  entity=read(C/'entities/shots'/sid/'status.json');assert entity['calls']==1 and not entity['reused_from']
  assert (C/'pi3x'/sid/'complete.json').is_file()
 contract=read(C/'prompt_alignment_reference/contract.json');assert len(contract['claims'])==79 and read(C/'narrative.json')==contract['narrative']
 align=read(C/'prompt_alignment/results.json');assert len(align['checks'])==79 and set(align['dimensions'])==set(alignment.DIMENSIONS)
 assert alignment.aggregate(align['checks'])==align['dimensions']
 position=read(C/'displacement/results.json');assert position==disp.evaluate(C)
 assert position['total_tokens']==position['model_calls']==position['api_usd']==0
 assert summary['position_consistency']['episode']==position['episode']
 assert summary['appearance']['status']=='success' and summary['prompt_binding']['status']=='success'
 totals={k:0 for k in ('input_tokens','output_tokens','cached_input_tokens','cache_write_input_tokens')};price=0.;requests=0
 for call in summary['calls']:
  raw=read(C/call['call']/'status.json');assert raw['status']=='success'
  us=raw.get('usage',raw.get('known_usage',[]));us=[us] if isinstance(us,dict) else us;assert us
  tokens=0;localprice=0.
  for u in us:
   i=u['input_tokens'];c=u.get('cached_input_tokens',0);w=u.get('cache_write_input_tokens',0);o=u['output_tokens'];assert 0<=c+w<=i
   im,om=(2,1.5) if i>272000 else (1,1)
   localprice+=((i-c-w)*10*im+c*im+w*12.5*im+o*50*om)/1e6;tokens+=i+o
   for k in totals:totals[k]+=u.get(k,0)
  assert tokens==call['total_tokens'] and abs(localprice-call['standard_api_equivalent_usd'])<1e-9
  price+=localprice;requests+=len(us)
 assert totals['input_tokens']+totals['output_tokens']==summary['total_tokens']==sum(s['total_tokens'] for s in summary['stages'])
 assert abs(price-summary['standard_api_equivalent_usd'])<1e-8 and abs(price-sum(s['standard_api_equivalent_usd'] for s in summary['stages']))<1e-8
 events=[];by={s['stage']:s for s in run['stages']}
 for s in run['stages']:
  for dependency in s['depends']:assert by[dependency]['started']+by[dependency]['seconds']<=s['started']+.001
  events += [(s['started'],1,s),(s['started']+s['seconds'],-1,s)]
 gpu=api=peakgpu=peakapi=0
 for _,sign,s in sorted(events,key=lambda v:(v[0],v[1])):
  gpu+=sign*int(s['gpu']);api+=sign*s.get('api_slots',0);peakgpu=max(gpu,peakgpu);peakapi=max(api,peakapi)
 assert peakgpu<=1 and peakapi<=8
 reg=read(C/'pairs/pair_000/registration/roma_geometry/registration.json');fit=reg['fits']['all_structures']
 assert fit['all_selected_pairs_used'] and fit['points_removed']==0 and fit['distance_power']==1 and fit['fit_rows']==32
 old=read(B/'experiments/study3_final_integrated_20260921/audit.json')
 result=dict(status='pass',fresh_detection_geometry_and_model_calls=True,original_frames=len(frames),source_files=len(source['source_hashes']),
  pipeline_seconds=summary['elapsed_seconds'],outer_elapsed_seconds=outer['elapsed_seconds'],successful_stages=len(run['stages']),model_call_directories=len(summary['calls']),model_requests=requests,
  total_tokens=summary['total_tokens'],token_totals=totals,standard_api_equivalent_usd=price,api_reserved_peak=peakapi,gpu_peak=peakgpu,
  alignment_exact_reaggregate=True,displacement_exact_recompute=True,source_hashes_unchanged=True,fps32_exact_unsquared_objective_preserved=True,
  old_pipeline_seconds=old['pipeline_elapsed_seconds'],old_outer_seconds=old['launch_elapsed_seconds'],old_total_tokens=old['total_tokens'],old_api_equivalent_usd=old['standard_api_equivalent_usd'],
  elapsed_reduction_percent=100*(1-outer['elapsed_seconds']/old['launch_elapsed_seconds']),token_reduction_percent=100*(1-summary['total_tokens']/old['total_tokens']),
  note='Measured fresh run; previous baseline includes one binding retry/recovery gap. Different compute node and fresh stochastic inventories/verdicts: observed difference is not a controlled pure optimization effect.',
  price_basis='Astra standard API equivalent, not bill: USD/M input10, cached-input1, cache-write12.5, output50; input>272000 uses input-side x2/output x1.5. Cache is a subset of input.',
  exclusions='Original-video generation, frozen reference preparation, resource checks/queue, post-run audit/report, historical validation and parent conversation; cluster monetary cost unavailable.')
 save(R/'audit.json',result)
 lines=['# Study3 optimized pipeline — fresh end-to-end measurement','',
 'Default optimized runtime scoring_efficiency_v1 / parallel_v2; full temporal_v2 + appearance + binding + four-dimensional prompt alignment, RoMa FPS32 registration. Started from18 original JPEG keyframes, fresh detection/clustering/geometry/all model judgments. Original frames, frozen normal reference and pretrained weights reused; no historical inference outputs.','',
 f'Pipeline wall {summary["elapsed_seconds"]:.3f}s; outer launch including immediate GPU guard {outer["elapsed_seconds"]:.3f}s ({outer["elapsed_seconds"]/60:.2f}min).',
 f'{requests} recorded model requests / {len(summary["calls"])} call directories; {summary["total_tokens"]:,} tokens; standard API equivalent USD{price:.6f}, not actual billing.',
 f'Input{totals["input_tokens"]:,}; cached input subset{totals["cached_input_tokens"]:,}; cache-write subset{totals["cache_write_input_tokens"]:,}; output{totals["output_tokens"]:,}.',result['price_basis'],'',
 '## Full-run comparison','','| Version | Outer wall seconds | Tokens | API equivalent USD |','|---|---:|---:|---:|',
 f'| Previous complete run (recorded binding retry) | {old["launch_elapsed_seconds"]:.3f} | {old["total_tokens"]:,} | {old["standard_api_equivalent_usd"]:.6f} |',
 f'| Fresh optimized run | {outer["elapsed_seconds"]:.3f} | {summary["total_tokens"]:,} | {price:.6f} |','',result['note'],
 f'Observed outer wall reduction{result["elapsed_reduction_percent"]:.2f}%; total token reduction{result["token_reduction_percent"]:.2f}%. Old component validation expense (8calls/601721tokens/USD6.002010) is separate and not added to this production-run total.','',
 '## Measured stages','','| Stage | Seconds | Tokens | API equivalent USD |','|---|---:|---:|---:|']
 for s in summary['stages']:lines.append(f'| {s["stage"]} | {s["seconds"]:.3f} | {s["total_tokens"]:,} | {s["standard_api_equivalent_usd"]:.6f} |')
 lines+=['','Stages overlap; their summed durations are not episode wall time. All actual calls/usage are retained in run/calls.csv; cached input is not counted again as additional tokens.','',
 '## Scores and population','','```json',json.dumps(dict(global_entities=summary['global_entity_table'],position=position['episode'],
  spatial_within={k:v['spatial']['summary'] for k,v in summary['within_shots'].items()},
  boundaries={k:dict(presence=v['presence']['summary'],spatial=v['spatial']['summary']) for k,v in summary['boundaries'].items()},
  appearance=summary['appearance'],binding=summary['prompt_binding'].get('counts'),
  prompt_alignment={k:dict(score=v['score'],counts=v['micro']) for k,v in align['dimensions'].items()}),ensure_ascii=False,indent=2),'```','',
 '## Audit','',f'{len(source["source_hashes"])} source snapshots and18 image hashes match. Fresh detector provenance, all stage successes, DAG order, GPUpeak{peakgpu}/APIreservedpeak{peakapi}, independent token/cost reconciliation, exact r_e recompute, alignment aggregation and FPS32 objective all pass.',
 'Raw r_e: run/displacement/results.json and entities.csv. Canonical/model wire inputs, all model responses, unknowns and original evidence remain. Source snapshots do not depend on future workspace edits. No expected anomaly counts or desired scores were supplied.',
 result['exclusions'],'']
 (R/'REPORT.md').write_text('\n'.join(lines));print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
