#!/usr/bin/env python3
"""Local-only contract tests and full prepared-input integrity check. No API calls."""
import copy
import importlib.util
import json
from pathlib import Path
import time

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('wan_adapter',HERE/'run.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.io.safe_compute()
started=time.time();manifest=m.verify_sources()
queue=[json.loads(x) for x in m.QUEUE.read_text().splitlines()]
prepared=[e for b in manifest['batches'] for e in m.read(HERE/'batches'/b['batch_id']/'input.json')['episodes']]
assert [r['episode_id'] for r in queue]==[r['episode_id'] for r in prepared]
assert len(prepared)==400 and sum(len(r['shots']) for r in prepared)==2000
for orig,wire in zip(queue,prepared):
    assert wire['global_prompt']==orig['global_prompt']
    assert wire['shots']==[{k:s[k] for k in ('shot_id','scene_id','generation_prompt_en')} for s in orig['shots']]
    assert set(wire)=={'episode_id','global_prompt','shots'}
    assert all(set(s)=={'shot_id','scene_id','generation_prompt_en'} for s in wire['shots'])

payload={'episodes':prepared[:1]}
empty={'episodes':[{'episode_id':e['episode_id'],'shots':[{'shot_id':s['shot_id'],'additions':[],
    'unresolved_dependencies':[]} for s in e['shots']]} for e in payload['episodes']]}
m.validate(empty,payload)
source=payload['episodes'][0]['shots'][1]['generation_prompt_en']
addition={'text':'The Suited man has wavy brown hair and wears a dark suit, a pale pink striped shirt, a red tie and matching pocket square.',
          'target_quote':'the Suited man standing behind the desk',
          'evidence':[{'source_shot_id':'Shot2','quote':source.split('.')[0]+'.'}],
          'reason':'Mechanical test fixture: resolve the previously defined suited man.'}
valid=copy.deepcopy(empty);valid['episodes'][0]['shots'][2]['additions']=[addition]
m.validate(valid,payload)
raw=payload['episodes'][0]['shots'][2]['generation_prompt_en']
assert m.materialize(raw,[addition])==raw+' '+addition['text']
assert m.materialize(raw,[])==raw

checks=[]
def reject(name,mutate):
    bad=copy.deepcopy(valid);mutate(bad)
    try: m.validate(bad,payload)
    except (ValueError,AssertionError): checks.append(name);return
    raise AssertionError('Did not reject '+name)
def a(r): return r['episodes'][0]['shots'][2]['additions'][0]
reject('future_source',lambda r:a(r)['evidence'][0].update(source_shot_id='Shot4'))
reject('invented_source_quote',lambda r:a(r)['evidence'][0].update(quote='unmentioned green necktie'))
reject('invented_target',lambda r:a(r).update(target_quote='an unmentioned stranger'))
reject('wrong_episode',lambda r:r['episodes'][0].update(episode_id='other_episode'))
reject('missing_shot',lambda r:r['episodes'][0]['shots'].pop())
reject('duplicate_append',lambda r:r['episodes'][0]['shots'][2]['additions'].append(copy.deepcopy(a(r))))
reject('unresolved_dependency',lambda r:r['episodes'][0]['shots'][2]['unresolved_dependencies'].append('Unknown person'))
reject('token_overflow',lambda r:a(r).update(text='Additional contextual text. '*600+'End.'))

for batch in manifest['batches']:
    p=m.read(HERE/'batches'/batch['batch_id']/'input.json')
    unchanged={'episodes':[{'episode_id':e['episode_id'],'shots':[{'shot_id':s['shot_id'],'additions':[],
        'unresolved_dependencies':[]} for s in e['shots']]} for e in p['episodes']]}
    m.validate(unchanged,p)
result={'status':'pass','prepared_episodes':400,'prepared_shots':2000,'ordered_source_text_exact':True,
        'no_source_images_or_nonprompt_fact_metadata':True,'valid_append_and_noop_pass':True,
        'rejected_invalid_fixtures':checks,'all_originals_pass_actual_tokenizer':True,
        'api_calls':0,'billable_tokens':0,'api_usd':0,'seconds':time.time()-started,
        'semantic_adaptation_completed':False}
m.dump(HERE/'preflight.json',result)
print(json.dumps(result,indent=2))
