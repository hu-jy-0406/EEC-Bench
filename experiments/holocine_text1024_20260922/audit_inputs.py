#!/usr/bin/env python3
"""Actual tokenizer validation for unchanged 400 prompts under explicit1024 profile."""
import collections,json,pathlib,sys,types
HERE=pathlib.Path(__file__).resolve().parent
OLD=HERE.parent/'holocine_prompt_adaptation_20260922'
sys.path.insert(0,str(OLD));import run as prior
from text_context import configure_pipeline,validate_prompt
prior.io.safe_compute();tok=prior.tokenizer()
pipe=types.SimpleNamespace(prompter=types.SimpleNamespace(text_len=512,tokenizer=tok))
configured=configure_pipeline(pipe)
manifest=prior.read(OLD/'manifest.json');assert prior.sha(prior.QUEUE)==manifest['queue_sha256']
rows=[]
for j in manifest['jobs']:
    eid=j['episode_id'];d=OLD/'episodes'/eid
    for f,k in [('contract.json','contract_sha256'),('alignment_contract.json','alignment_contract_sha256')]:
        assert prior.sha(d/f)==prior.sha(prior.CONTRACTS/eid/f)==j[k]
    c=prior.read(d/'candidate.json');r=prior.read(d/'semantic_audit.json');p=prior.read(d/'input.json')
    prior.validate_candidate(c,p);prior.validate_review(r,p);assert r['verdict']=='pass'
    a=validate_prompt(pipe,prior.render(c),j['shot_count'])
    assert a['tokens']==prior.read(d/'token_audit.json')['tokens']
    rows.append(dict(episode_id=eid,shot_count=j['shot_count'],**a))
official=HERE.parent/'holocine_contract_compression_v2_20260922/research/official_13shot_prompt.txt'
demo=validate_prompt(pipe,official.read_text(),13) if official.exists() else None
report=dict(status='pass',profile=configured,episodes=len(rows),shots=sum(r['shot_count'] for r in rows),
    token_min=min(r['tokens'] for r in rows),token_max=max(r['tokens'] for r in rows),
    former_over512=sum(r['tokens']>512 for r in rows),over1024=sum(r['tokens']>1024 for r in rows),
    original_prompts_byte_unchanged=True,contracts_byte_unchanged=True,
    all_frozen_claim_audits_pass=True,official_13shot_prompt=demo,
    full_pretrained_encoder_or_video_run=False,new_api_calls=0,new_billable_api_tokens=0,new_api_usd=0,rows=rows)
prior.dump(HERE/'input_audit.json',report)
print(json.dumps({k:v for k,v in report.items() if k!='rows'}),flush=True)
