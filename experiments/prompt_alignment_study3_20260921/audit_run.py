"""CPU-only deterministic audit; no model calls or second semantic review."""
import json,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'scripts'))
import gs_prompt_alignment as a
folder=Path(sys.argv[1]).resolve();r=a.read(folder/'results.json');c=a.read(folder/'contract.json')
a.validate_contract(c)
assert [x['claim_id'] for x in r['checks']]==[q['claim_id'] for q in c['claims']]
assert a.aggregate(r['checks'])==r['dimensions']
assert a.read(folder/'status.json')['status']=='success'
assert a.usage_summary(folder)['total_tokens']==r['total_tokens']
assert abs(a.usage_summary(folder)['known_standard_api_equivalent_usd']-r['known_standard_api_equivalent_usd'])<1e-9
sources=a.read(folder/'source_hashes.json')
for p,h in sources.items():assert a.sha(p)==h,p
rows=[]
for call in sorted((folder/'calls').iterdir()):
 payload=a.read(call/'input.json');request=a.read(call/'request.json');raw=a.read(call/'response.json')
 actual=a.review_batch(raw,payload['claims'],request['images'])
 assert all(x in r['checks'] for x in actual)
 scope={s for q in payload['claims'] for s in q['shot_ids']}
 assert {x['shot_id'] for x in payload['image_order']}==scope
 assert {x['shot_id'] for x in request['images']}==scope
 assert all(g['shot_id'] in scope for g in payload['graphs'])
 text=json.dumps(payload)
 for word in ['motion_status','motion_evidence','anchor_observed_static','observed_motion_status','conflict_pairs']:
  assert '"'+word+'"' not in text,word
 rows.append(dict(call=call.name,scope=sorted(scope),claims=len(actual),images=len(request['images']),usage=a.read(call/'status.json')['usage']))
a.save(folder/'audit.json',dict(status='passed',sources=len(sources),calls=rows,claim_population=len(r['checks']),
    dimensions_recomputed=True,original_frame_hashes=True,scope_isolation=True,prior_score_leakage=False,
    token_cost_reconciliation=True,physical_cross_scene_identity_merge=False))
print(json.dumps(dict(status='passed',claims=len(r['checks']),calls=len(rows),dimensions={k:dict(score=v['score'],interval=v['identification_interval'],**{x:v['micro'][x] for x in ['T','F','U']}) for k,v in r['dimensions'].items()},tokens=r['total_tokens'],usd=r['known_standard_api_equivalent_usd']),ensure_ascii=False))
