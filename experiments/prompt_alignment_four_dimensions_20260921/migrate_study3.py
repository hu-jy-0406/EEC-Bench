import copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'EECBench/scripts'))
import gs_prompt_alignment as a
OUT=Path(__file__).resolve().parent
OLD=ROOT/'EECBench/experiments/prompt_alignment_study3_20260921'
source_contract=OLD/'frozen_visible/contract.json'
source_results=OLD/'alignment_visible/results.json'
c=a.four_dimension_contract(a.read(source_contract))
new_contract=a.freeze(c,OUT/'frozen')
old=a.read(source_results);result=copy.deepcopy(old)
ids={q['claim_id'] for q in c['claims']}
result['checks']=[r for r in old['checks'] if r['claim_id'] in ids]
assert len(result['checks'])==len(c['claims'])==79
result['dimensions']=a.aggregate(result['checks'])
for dim in a.DIMENSIONS:assert result['dimensions'][dim]==old['dimensions'][dim]
result.update(dimension_profile=a.DIMENSION_PROFILE,contract_sha256=a.sha(new_contract),
    result_origin='offline_projection_of_complete_historical_verdicts_no_new_inference',
    source_contract=str(source_contract),source_results=str(source_results),
    source_contract_sha256=a.sha(source_contract),source_results_sha256=a.sha(source_results),
    removed_claim_ids=c['dimension_migration']['removed_claim_ids'],
    reused_historical_usage={k:old[k] for k in ('total_tokens','known_standard_api_equivalent_usd')},
    calls=[],total_tokens=0,known_standard_api_equivalent_usd=0,unavailable_call_costs=0)
result['limitations']+=' Four-dimensional output is an offline projection of existing verdicts, not a fresh call with the revised prompt.'
a.save(OUT/'alignment/results.json',result);a.write_report(OUT/'alignment',result)
a.save(OUT/'audit.json',dict(status='pass',retained_claims=79,removed_claims=4,all_retained_verdicts_unchanged=True,
    all_four_dimension_scores_unchanged=True,source_contract_sha256=a.sha(source_contract),source_results_sha256=a.sha(source_results),
    new_model_calls=0,new_tokens=0,new_api_usd=0))
print(json.dumps({k:v['score'] for k,v in result['dimensions'].items()}))
