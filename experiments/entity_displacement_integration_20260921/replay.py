import hashlib,json,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'EECBench/scripts'))
import gs_entity_displacement as d
OUT=Path(__file__).resolve().parent
cases={'Study2':ROOT/'EECBench/experiments/within_negative_review_20260920/full/study2',
       'Study3':ROOT/'EECBench/experiments/pipeline_parallel_20260921/run',
       'Study4':ROOT/'EECBench/experiments/within_negative_review_20260920/full/study4'}
results={}
for name,case in cases.items():
    result=d.evaluate(case)
    d.write(result,OUT/name.lower())
    for path,h in result['source_hashes'].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h
    rows=[r for r in result['records'] if r['r_e'] is not None]
    score=100-math.sqrt(sum((100-100/max(1,r['r_e']))**2 for r in rows)/len(rows))
    assert abs(score-result['episode']['all']['score'])<1e-12
    results[name]=result
    print(name,json.dumps(result['episode']))
old=json.loads((ROOT/'EECBench/experiments/study4_shot1_static_displacement_20260921/results.json').read_text())
new=results['Study4']['within_shots']['shot1']['records']
for row in old['entities']:
    r=next(x for x in new if x['entity_ids']==[row['entity_id']])
    assert r['n']==row['n']
    for a,b in [('distance','mean_distance'),('max_distance','max_distance')]:
        assert (r[a] is None and row[b] is None) or abs(r[a]-row[b])<1e-12
for study in ('Study3','Study4'):
    case=cases[study]
    proposals=json.loads((case/'pairs/pair_000/boundary/proposals.json').read_text())
    for row in results[study]['boundaries']['pair_000']['records']:
        if row['distance'] is None:continue
        ids=row['pair_local_entity_ids']
        pts=[proposals['endpoint_observations'][i][ids[i]]['geometry']['center_world'] for i in range(2)]
        assert abs(math.dist(*pts)-row['distance'])<1e-12
(OUT/'audit.json').write_text(json.dumps(dict(status='pass',studies=list(results),original_sources_unchanged=True,
    study4_within_distances_match=True,study3_study4_boundary_distances_match=True,
    pooled_formula_independently_recomputed=True,model_calls=0,total_tokens=0,api_usd=0),indent=2)+'\n')
lines=['# Entity displacement integration validation','',
'Frozen Study2/3/4 frontend, motion, final identity, registration and boundary review reused. No fresh frontend/GPU/model run.',
'', '| Study | Within position score | Boundary position score | Episode position score | Scored records |','|---|---:|---:|---:|---:|']
for name,result in results.items():
    ep=result['episode']
    lines.append(f'| {name} | {ep["within"]["score"]:.6f} | {ep["cross"]["score"]:.6f} | {ep["all"]["score"]:.6f} | {ep["all"]["scored_records"]} |')
lines+=['','Per-entity round-trip precision r_e, raw means/maxima or boundary distances, medians, original/aligned centers and within-frame distance pairs are retained in study*/results.json and entities.csv.',
'Study4 Shot1 historical mean/max values and Study3/4 frozen endpoint distances reproduce to <1e-12; all source hashes unchanged; pooled RMS independently recomputed.',
'No old model calls are replayed. New module/API expense: 0 model calls, 0 tokens, USD 0.',
'Scores are relative geometric deviation, not confirmed visual errors: known outdoor-pot detection errors can score poorly. Small cross-boundary populations and median self-normalization remain limitations.',
'Production temporal_v2 spatial/full now includes the CPU stage; identity/presence early stops do not. Existing relationship/presence/appearance scoring and registration unchanged.']
(OUT/'REPORT.md').write_text('\n'.join(lines)+'\n')
