import copy,json
from pathlib import Path
import run
old=run.read(run.ROOT/'EECBench/experiments/prompt_alignment_four_dimensions_20260921/frozen/contract.json')
src=dict(episode_id='study3_validation',global_prompt=old['narrative']['facts'][0]['text'],shots=[dict(shot_id=f['fact_id'],prompt=f['text']) for f in old['narrative']['facts'][1:]])
src['source_units']=run.units(run.facts(src))
mapping={e['prompt_entity_id']:('Character 1' if e['prompt_entity_id']=='woman' else 'Object '+str(i)) for i,e in enumerate(old['registry']['entities'])}
entities=[dict(label=mapping[e['prompt_entity_id']],name=e['name'],description=e['description'],evidence=[dict(fact_id='global' if x['fact_id']=='setting' else x['fact_id'],quote=x['quote']) for x in e['evidence']]) for e in old['registry']['entities']]
schedule=[]
for sid in old['shot_ids']:
 row=dict(shot_id=sid,characters=[],places=[],objects=[])
 for e in old['registry']['entities']:
  if next(s for s in e['schedule'] if s['shot_id']==sid)['expectation']=='required':row['characters' if e['prompt_entity_id']=='woman' else 'objects'].append(e['name'])
 schedule.append(row)
claims=copy.deepcopy(old['claims'])
for c in claims:
 c['entity_ids']=[mapping[e] for e in c['entity_ids']]
 for ev in c['evidence']:
  if ev['fact_id']=='setting':ev['fact_id']='global'
coverage=[]
for u in src['source_units']:
 refs=[c['claim_id'] for c in claims if any(ev['fact_id']==u['fact_id'] and ev['quote'] in u['text'] for ev in c['evidence'])]
 coverage.append(dict(unit_id=u['unit_id'],claim_ids=refs,unscored=[] if refs else [dict(quote=u['text'],reason='Fixture mapping only; not a new semantic annotation')]))
# Some original exact evidence spans sentence boundaries: assign to first fact unit.
seen={x for r in coverage for x in r['claim_ids']}
for c in claims:
 if c['claim_id'] not in seen:
  next(r for r,u in zip(coverage,src['source_units']) if u['fact_id']==c['evidence'][0]['fact_id'])['claim_ids'].append(c['claim_id'])
data=dict(entities=entities,schedule=schedule,claims=claims,coverage=coverage,unresolved=[])
run.validate(data,src)
patch=dict(verdict='pass',issues=[],delete_entities=[],upsert_entities=[],replacement_schedule=[],delete_claims=[],upsert_claims=[],replacement_coverage=[],unresolved=[])
assert run.apply_review(data,patch)==data
checks=['Study3 79-claim canonical adaptation','empty patch exact preservation']
def bad(name,fn):
 d=copy.deepcopy(data);fn(d)
 try:run.validate(d,src)
 except (ValueError,KeyError,StopIteration):checks.append(name)
 else:raise AssertionError(name)
bad('foreign schedule entity',lambda d:d['schedule'][0]['objects'].append('invented'))
bad('missing shot',lambda d:d['schedule'].pop())
bad('duplicate name',lambda d:d['entities'][1].update(name=d['entities'][0]['name']))
bad('nonexact evidence',lambda d:d['entities'][0]['evidence'][0].update(quote='invented text'))
bad('uncovered claim',lambda d:[r['claim_ids'].remove(d['claims'][0]['claim_id']) for r in d['coverage'] if d['claims'][0]['claim_id'] in r['claim_ids']])
bad('foreign claim ref',lambda d:d['coverage'][0]['claim_ids'].append('invented'))
bad('wrong exclusion evidence',lambda d:d['coverage'][0]['unscored'].append(dict(quote='invented exclusion',reason='fake')))
bad('dangling dependency',lambda d:d['claims'][-1]['depends_on'].append('invented'))
bad('cyclic dependency',lambda d:d['claims'][-1]['depends_on'].append(d['claims'][-1]['claim_id']))
run.dump(run.HERE/'preflight.json',dict(status='pass',checks=checks,count=len(checks),model_calls=0,tokens=0,api_usd=0))
print(json.dumps(dict(status='pass',checks=len(checks))))
