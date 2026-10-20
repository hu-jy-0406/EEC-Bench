import hashlib,json,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CASE=ROOT/'run'
sys.path.insert(0,str(ROOT.parents[2]/'EECBench/scripts'))
import gs_entity_displacement as disp
import gs_prompt_alignment as align

def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
summary=read(CASE/'summary.json');execution=read(ROOT/'execution.json');runtime=read(CASE/'pipeline_runtime.json')
assert execution['status']==summary['status']==runtime['status']=='success'
assert all(s['status']=='success' and s['returncode']==0 for s in runtime['stages'])
manifest=read(CASE/'raw_manifest.json');frames=[f for s in manifest['shots'] for f in s['frames']]
assert len(frames)==18
for f in frames:assert sha(f['path'])==f['sha256']
provenance=read(CASE/'provenance.json')
assert provenance['inference_reuse'] is False
for p,h in provenance['source_hashes'].items():assert sha(p)==h,(p,'source changed')
contract=read(CASE/'prompt_alignment_reference/contract.json');assert len(contract['claims'])==79
assert set(q['dimension'] for q in contract['claims'])==set(align.DIMENSIONS)
assert read(CASE/'narrative.json')==contract['narrative']
assert read(CASE/'prompt_registry.json')==contract['registry']
alignment=read(CASE/'prompt_alignment/results.json')
assert len(alignment['checks'])==79 and set(alignment['dimensions'])==set(align.DIMENSIONS)
assert align.aggregate(alignment['checks'])==alignment['dimensions']
position=read(CASE/'displacement/results.json')
recomputed=disp.evaluate(CASE)
assert position==recomputed
for path,h in position['source_hashes'].items():assert sha(path)==h
assert position['total_tokens']==position['model_calls']==position['api_usd']==0
assert summary['position_consistency']['episode']==position['episode']
# Independently reconcile each serialized invocation; cached tokens are a subset.
totals=dict(input_tokens=0,cached_input_tokens=0,cache_write_input_tokens=0,output_tokens=0)
price=0;calls=[]
for call in summary['calls']:
    p=CASE/call['call']/'status.json';raw=read(p)
    us=raw.get('usage',raw.get('known_usage',[]));us=[us] if isinstance(us,dict) else us
    assert raw['status']=='success' and us,(str(p),raw['status'])
    local=0;tokens=0
    for u in us:
        i=u['input_tokens'];c=u.get('cached_input_tokens',0);w=u.get('cache_write_input_tokens',0);o=u['output_tokens']
        assert 0<=c+w<=i
        im,om=(2,1.5) if i>272000 else (1,1)
        local+=((i-c-w)*10*im+c*im+w*12.5*im+o*50*om)/1e6
        tokens+=i+o
        for k in totals:totals[k]+=u.get(k,0)
    assert tokens==call['total_tokens']
    assert abs(local-call['standard_api_equivalent_usd'])<1e-9
    price+=local;calls.append(dict(call=call['call'],requests=len(us),tokens=tokens,usd=local))
assert sum(c['tokens'] for c in calls)==summary['total_tokens']==totals['input_tokens']+totals['output_tokens']
assert abs(price-summary['standard_api_equivalent_usd'])<1e-9
assert sum(s['total_tokens'] for s in summary['stages'])==summary['total_tokens']
assert abs(sum(s['standard_api_equivalent_usd'] for s in summary['stages'])-price)<1e-9
# Check serializer / output persistence and observed scheduler resource limits.
replay_rows=read(CASE/'displacement/results.json')['records']
assert all(r['r_e'] is None or math.isfinite(r['r_e']) for r in replay_rows)
events=[]
for stage in runtime['stages']:
    for s in stage.get('attempts',[stage]):
        events.extend([(s['started'],1,s),(s['started']+s['seconds'],-1,s)])
active_gpu=active_api=peak_gpu=peak_api=0
for _,sign,s in sorted(events,key=lambda e:(e[0],e[1])):
    active_gpu+=sign*int(s['gpu']);active_api+=sign*s.get('api_slots',0)
    peak_gpu=max(peak_gpu,active_gpu);peak_api=max(peak_api,active_api)
assert peak_gpu<=1 and peak_api<=8
result=dict(status='pass',original_frame_hashes=18,source_hashes=len(provenance['source_hashes']),
    complete_successful_stages=len(runtime['stages']),model_call_directories=len(calls),recorded_requests=sum(c['requests'] for c in calls),
    token_totals=totals,total_tokens=summary['total_tokens'],standard_api_equivalent_usd=price,billed_amount_available=False,
    pipeline_elapsed_seconds=summary['elapsed_seconds'],launch_elapsed_seconds=execution['elapsed_seconds'],
    recovery=runtime.get('recovery'),
    fresh_detection_geometry_and_model_calls=True,source_and_contract_hashes_unchanged=True,
    displacement_exact_recompute=True,alignment_exact_reaggregate=True,api_peak_slots=peak_api,gpu_peak=peak_gpu,
    price_basis='Recorded Astra pricing verified 2026-09-20: USD/M uncached10/cache-read1/cache-write12.5/output50; input>272000: input-side x2/output x1.5; not billed',
    scope='18 original keyframes through final integrated evaluation, not video generation or text-reference compilation')
(ROOT/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
lines=['# Study3 final integrated fresh evaluation','',
'Fresh WeDetect/independent clustering, geometry, motion, identity/registration, relation consistency, displacement, appearance, binding and four-dimensional prompt alignment from all18 original frames. Normal narrative and registry/79claims frozen before execution. No prior detector/geometry/judgment reuse; pretrained weights and text reference reused.',
'',f'Pipeline wall time: {summary["elapsed_seconds"]:.3f}s ({summary["elapsed_seconds"]/60:.2f} min). Outer launch including immediate GPU guard/setup: {execution["elapsed_seconds"]:.3f}s.',
 f'Model calls: {len(calls)} directories / {result["recorded_requests"]} recorded requests. Total tokens: {summary["total_tokens"]:,}; standard API equivalent USD {price:.6f} (not a bill).',
 f'Input {totals["input_tokens"]:,}, including cached-read {totals["cached_input_tokens"]:,} and cache-write {totals["cache_write_input_tokens"]:,}; output {totals["output_tokens"]:,}. Cached tokens are not counted twice.',
 result['price_basis'], '',
'One initial binding response was rejected by unchanged witness validation; a same-input retry succeeded. The initial attempt is archived, both calls are included in tokens/cost, and elapsed time includes the recovery gap. Successful stages come only from this same fresh run. Binding stage seconds sum the initial stage and retry model call, excluding retry local postprocessing; see execution.json and recovery_runtime.json.', '',
'## Stage timing and usage','', '| Stage | Seconds | Tokens | API equivalent USD |','|---|---:|---:|---:|']
for s in summary['stages']:
 lines.append(f'| {s["stage"]} | {s["seconds"]:.3f} | {s["total_tokens"]} | {s["standard_api_equivalent_usd"]:.6f} |')
lines+=['','Stages overlap, so summed durations are not wall time. Position scoring is CPU-only with0newtokens/USD0API.',
 '', '## Scores', '', 'Position consistency (independent of original pair-relation score):', '',
 '| Scope | Score | Valid records |','|---|---:|---:|']
for k,v in position['episode'].items():lines.append(f'| {k} | {v["score"]} | {v["scored_records"]} |')
lines+=['', 'Original spatial-relation summaries:', '', '```json',json.dumps({"within":{k:v['spatial']['summary'] for k,v in summary['within_shots'].items()},"boundaries":{k:v['spatial']['summary'] for k,v in summary['boundaries'].items()}},ensure_ascii=False,indent=2),'```', '',
'Appearance (Codex and DINO separately):', '', '```json',json.dumps(summary['appearance'],ensure_ascii=False,indent=2),'```','',
'Prompt alignment (conditional scores, unknowns retained):','','| Dimension | Score | T/F/U |','|---|---:|---|']
for k,v in alignment['dimensions'].items():
 m=v['micro'];lines.append(f'| {k} | {v["score"]} | {m["T"]}/{m["F"]}/{m["U"]} |')
lines+=['', '## Audit and limits', '',
'All source/frame hashes, final stage success after the documented recovery, four-dimensional contract/results, independent token/cost reconciliation, exact displacement recompute and prompt-score reaggregation passed. GPU maximum1; API reservation maximum'+str(peak_api)+'.',
'Raw r_e and distances/baselines/frame evidence: run/displacement/results.json and entities.csv. All original requests/responses and per-call usage retained. This is a fresh final-version end-to-end evaluation, not an estimate from cached stages.',
'Excludes preflight resource checks, human-authored/frozen reference preparation, historical experiments, parent assistant conversation and cluster monetary cost. Fees are recorded-model standard API equivalents; actual service billing unavailable.',
'Newly sampled detector/clustering/identity/model verdicts can change population and results. Position scores remain relative geometric deviations, including detection noise; prompt unknowns are not verified successes. No tuning or verdict selection by desired study ranking.']
(ROOT/'REPORT.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
