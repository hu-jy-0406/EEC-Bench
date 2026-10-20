"""Independent on-disk delivery/provenance/accounting check (CPU only)."""
import collections,hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'EECBench/scripts'))
import gs_prompt_alignment as alignment
import run_wedetect_shot_entities as io

def load(p):return json.loads(p.read_text())
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 io.safe_compute();m=load(HERE/'manifest.json');dest=HERE/'deliverables';idx=load(dest/'index.json')
 source=Path(m['source']);queue=Path(m['queue']);assert digest(source)==m['source_sha256'];assert digest(queue)==m['queue_sha256']
 originals=[json.loads(x) for x in queue.read_text().splitlines()];assert len(idx)==len(originals)==400
 counts=collections.Counter();htmlrows=[];delivery_hashes={}
 for row,original in zip(idx,originals):
  eid=original['episode_id'];assert row['episode_id']==eid
  p=dest/row['contract'];c=load(p);a=load(dest/row['alignment_contract'])
  assert c['episode_id']==eid and digest(p)==row['sha256']
  assert c['prompt']['global_prompt']==original['global_prompt']
  assert [s['shot_id'] for s in c['prompt']['shots']]==[s['shot_id'] for s in original['shots']]
  assert [s['text'] for s in c['prompt']['shots']]==[s['generation_prompt_en'] for s in original['shots']]
  keys=[s['schedule_key'] for s in c['prompt']['shots']];assert list(c['entity_schedule'])==keys
  assert 'scene_id' not in c and not any('scene_id' in s for s in c['prompt']['shots'])
  assert isinstance(c['unresolved'],list);assert a['claims']==c['claims'];alignment.validate_contract(a)
  entities=c['entity_descriptions'];names={e['name']:eid for eid,e in entities.items()};assert len(names)==len(entities)
  assert {e['prompt_entity_id'] for e in a['registry']['entities']}==set(entities)
  for e in a['registry']['entities']:
   src=entities[e['prompt_entity_id']]
   assert all(e[k]==src[k] for k in ['name','description','evidence'])
   group={'Character':'characters','Location':'places','Object':'objects'}[e['prompt_entity_id'].split()[0]]
   for sched,shot in zip(e['schedule'],c['prompt']['shots']):
    assert sched['shot_id']==shot['shot_id']
    assert (sched['expectation']=='required')==(e['name'] in c['entity_schedule'][shot['schedule_key']][group])
  fs={x['fact_id']:x['text'] for x in a['narrative']['facts']}
  assert fs=={'global':original['global_prompt'],**{s['shot_id']:s['generation_prompt_en'] for s in original['shots']}}
  checks=load(HERE/'episodes'/eid/'review.json');assert checks['verdict'] in ['pass','revised','unresolved'];assert checks['unresolved']==c['unresolved']
  # Actual successful call output must match saved accepted review, not a synthetic audit flag.
  calls=HERE/'episodes'/eid/'calls';found=False
  current_input=load(HERE/'episodes'/eid/'input.json');accepted_draft=load(HERE/'episodes'/eid/'draft.json')
  for rp in calls.glob('review_*/response.json'):
   if load(rp)!=checks:continue
   review_input=load(rp.parent/'input.json')
   if {k:review_input[k] for k in current_input}!=current_input or review_input['proposal']!=accepted_draft:continue
   status=load(rp.parent/'status.json')
   if status['status']=='success' and load(rp.parent/'validation.json')['status']=='pass':found=True
  assert found
  counts.update(ambiguity_notes=len(c['unresolved']),episodes=1,shots=len(keys),entities=len(entities),claims=len(c['claims']),source_units=len(c['coverage']),review_revised=load(HERE/'episodes'/eid/'final.json')!=accepted_draft)
  counts.update({dim:sum(q['dimension']==dim for q in c['claims']) for dim in alignment.DIMENSIONS})
  delivery_hashes[str(p.relative_to(dest))]=digest(p)
 for name,selected in [('contracts_400.jsonl',originals),('core_100.jsonl',originals[:100]),('priority_200.jsonl',originals[:200]),('stage2_additional_100.jsonl',originals[100:200]),('stage3_remaining_200.jsonl',originals[200:])]:
  rows=[json.loads(x) for x in (dest/name).read_text().splitlines()]
  assert [r['episode_id'] for r in rows]==[r['episode_id'] for r in selected]
  for c in rows:assert c==load(dest/'episodes'/c['episode_id']/'contract.json')
  delivery_hashes[name]=digest(dest/name)
 # Reconcile every completed and failed attempt, including mechanical rejections.
 total=collections.Counter();known_cost=0.;unknown=[];call_count=0;prices=load(HERE/'pricing.json');spans=[]
 for p in (HERE/'episodes').glob('*/calls/*/status.json'):
  s=load(p);call_count+=1;assert s['status']!='running';assert s['model']=='gpt-6-astra' and s['reasoning']=='medium'
  request=load(p.parent/'request.json');cmd=request['command'];assert '--image' not in cmd
  assert 'model_reasoning_effort="medium"' in cmd
  assert request['prompt_sha256']==digest(p.parent/'prompt.txt')
  payload=load(p.parent/'input.json');assert set(payload)<={'episode_id','global_prompt','shots','source_units','proposal'}
  assert all(set(x)=={'shot_id','prompt'} for x in payload['shots'])
  spans.extend([(s['started'],1),(s['started']+s['seconds'],-1)])
  usages=s.get('usage',s.get('known_usage',[]));usages=[usages] if isinstance(usages,dict) else usages
  if not usages and (p.parent/'events.jsonl').exists():
   usages=[ev['usage'] for line in (p.parent/'events.jsonl').read_text().splitlines() if (ev:=json.loads(line)).get('type')=='turn.completed' and ev.get('usage')]
  if not usages:unknown.append(str(p))
  for u in usages:
   i,cache,o=[u.get(k,0) for k in ('input_tokens','cached_input_tokens','output_tokens')]
   if not 0<=cache<=i<=prices['max_input_tokens'] or u.get('cache_write_input_tokens',0):unknown.append(str(p))
   total.update(input_tokens=i,cached_input_tokens=cache,output_tokens=o)
   known_cost+=((i-cache)*prices['input_usd_per_million']+cache*prices['cached_input_usd_per_million']+o*prices['output_usd_per_million'])/1e6
 recorded=load(HERE/'usage_cost.json');assert recorded['calls']==call_count and recorded['usage']==dict(total)
 assert abs(recorded['known_subtotal_usd']-known_cost)<1e-7
 overlap=peak=0
 for t,n in sorted(spans):overlap+=n;peak=max(peak,overlap)
 result=dict(status='pass',counts=dict(counts),checks=['400 unique source-matched episodes','2000 byte-exact original prompts','EntityBench inventory/schedule references','no extra scene_id','all claims identical to evaluator adapters','all canonical validators pass','actual independent review responses verified','all subset order/content exact','no generated/source-video inputs in model requests','source and queue hashes match current authorized versions','all calls including failures accounted once'],model_calls=call_count,total_tokens=total['input_tokens']+total['output_tokens'],standard_api_equivalent_usd=known_cost if not unknown else None,actual_billed_api_usd=None,max_call_overlap=peak,unknown_cost_records=unknown,independent_human_semantic_validation=False)
 io.dump(HERE/'independent_validation.json',result);io.dump(dest/'sha256.json',delivery_hashes)
 print(json.dumps(result))
if __name__=='__main__':main()
