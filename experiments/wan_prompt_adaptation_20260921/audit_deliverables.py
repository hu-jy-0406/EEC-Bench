#!/usr/bin/env python3
"""Independent on-disk delivery audit; no API/model inference."""
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
DEST=HERE/'deliverables'
PRIOR=ROOT/'EECBench/experiments/source_video_priority_20260921'
FEAS=ROOT/'EECBench/experiments/generation_feasibility_20260921'
def read(p):return json.loads(p.read_text())
def rows(p):return [json.loads(x) for x in p.read_text().splitlines()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(s):return hashlib.sha256(s.encode()).hexdigest()

started=time.time()
assert os.environ.get('USE_TORCH')=='0'
spec=importlib.util.spec_from_file_location('wan_tokens',FEAS/'repos/Wan2.2/wan/modules/tokenizers.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
tokenizer=mod.HuggingfaceTokenizer(str(FEAS/'models/Wan2.2-T2V-A14B/google/umt5-xxl'),seq_len=512,clean='whitespace',local_files_only=True)
manifest=read(HERE/'manifest.json')
assert sha(Path(manifest['source']))==manifest['source_sha256']
assert sha(Path(manifest['queue']))==manifest['queue_sha256']
for name,h in manifest['source_hashes'].items():assert sha(Path(name))==h
source=rows(PRIOR/'generation_queue_400.jsonl')
final=rows(DEST/'generation_queue_400.jsonl')
assert len(final)==400 and sum(len(e['shots']) for e in final)==2000
assert [e['episode_id'] for e in final]==[e['episode_id'] for e in source]
for name,expected in [('core_100',final[:100]),('priority_200',final[:200]),
    ('stage2_additional_100',final[100:200]),('stage3_remaining_200',final[200:])]:
    actual=rows(DEST/(name+'.jsonl'))
    assert actual==expected
    assert [r['episode_id'] for r in actual]==[r['episode_id'] for r in rows(PRIOR/(name+'.jsonl'))]
texts=[];originals=[];recorded=[];changed=[];evidence_count=0;largest=[]
for rank,(src,ep) in enumerate(zip(source,final),1):
    assert ep['generation_priority']==rank
    assert ep['shot_count']==src['shot_count'] and ep['target_duration_seconds']==src['target_duration_seconds']
    assert ep['global_prompt_original']==src['global_prompt']
    assert [s['shot_id'] for s in ep['shots']]==[s['shot_id'] for s in src['shots']]
    prior={'global':src['global_prompt']}
    for orig,s in zip(src['shots'],ep['shots']):
        raw=orig['generation_prompt_en'];adds=s['context_additions']
        assert s['generation_prompt_en_original']==raw
        assert s['scene_id']==orig['scene_id'] and s['target_duration_seconds']==orig['target_duration_seconds']
        wanted=raw+(' '+' '.join(a['text'] for a in adds) if adds else '')
        assert s['wan_prompt_en']==wanted and Path(s['prompt_file']).read_text()==wanted
        assert Path(s['prompt_file']).resolve()==DEST/'prompts'/ep['episode_id']/(s['shot_id']+'.txt')
        assert s['original_sha256']==digest(raw) and s['wan_sha256']==digest(wanted)
        for a in adds:
            assert a['text'].strip()==a['text'] and a['text'] and '\n' not in a['text']
            assert a['target_quote'] and a['target_quote'] in raw
            assert a['reason'].strip() and a['evidence']
            for ev in a['evidence']:
                assert ev['source_shot_id'] in prior
                assert ev['quote'] and ev['quote'] in prior[ev['source_shot_id']]
                evidence_count+=1
        prior[s['shot_id']]=raw
        texts.append(wanted);originals.append(raw);recorded.append(s['wan_tokens_including_special']);changed.append(bool(adds))
        largest.append((s['wan_tokens_including_special'],ep['episode_id'],s['shot_id']))

kwargs=dict(return_tensors=None,padding=False,add_special_tokens=True,return_attention_mask=False)
full=tokenizer(texts,truncation=False,**kwargs)
production=tokenizer(texts,**kwargs)
original_ids=tokenizer(originals,truncation=False,**kwargs)
assert full==production
lengths=list(map(len,full));original_lengths=list(map(len,original_ids))
assert lengths==recorded and max(lengths)<=512
token_csv=list(csv.DictReader((DEST/'token_audit.csv').open()))
assert len(token_csv)==len(lengths)
for line,n,n0 in zip(token_csv,lengths,original_lengths):
    assert int(line['wan_tokens'])==n and int(line['original_tokens'])==n0 and int(line['added_tokens'])==n-n0
reviewed={}
for batch in manifest['batches']:
    folder=HERE/'batches'/batch['batch_id']
    result=read(folder/'final.json')
    assert result==read(folder/'review.json')
    successful=[p for p in (folder/'calls').glob('review_*/validation.json') if read(p)['status']=='pass']
    assert successful and any(read(p.parent/'response.json')==result for p in successful)
    for e in result['episodes']:reviewed[e['episode_id']]=e
for e in final:
    for s,r in zip(e['shots'],reviewed[e['episode_id']]['shots']):
        assert s['shot_id']==r['shot_id'] and s['context_additions']==r['additions'] and not r['unresolved_dependencies']
report={'status':'pass','episodes':400,'shots':2000,'original_text_byte_preserved':True,
    'only_recorded_additions_appended':True,'all_text_files_match':True,'frozen_order_and_nested_subsets_match':True,
    'source_and_protocol_hashes_match':True,'exact_prior_evidence_references':evidence_count,
    'all_delivered_shots_match_independent_review':True,'tokens_match_actual_wan_wrapper':True,
    'production_token_ids_equal_untruncated':True,'over_512':0,'min_tokens':min(lengths),
    'max_tokens':max(lengths),'mean_tokens':statistics.mean(lengths),'changed_shots':sum(changed),
    'unchanged_shots':len(changed)-sum(changed),'longest_shots':sorted(largest,reverse=True)[:10],
    'artifact_hashes':{p.name:sha(p) for p in DEST.glob('*.jsonl')},'seconds':time.time()-started,
    'audit_api_calls':0,'audit_billable_tokens':0,'audit_api_usd':0,
    'semantic_quality_basis':'Full independent model review plus targeted primary-agent inspection; no independent human annotation.',
    'formal_entity_schedule_compiled':False}
(HERE/'independent_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
