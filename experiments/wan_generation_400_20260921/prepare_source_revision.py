#!/usr/bin/env python3
"""Prepare a minimally revised input snapshot; CPU-only actual tokenizer audit."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'prompt_revision_20260922'
FEAS=ROOT.parent/'generation_feasibility_20260921'
SOURCE=ROOT.parent/'source_video_priority_20260921/generation_queue_400.jsonl'
REVISION=ROOT.parent/'episode_contracts_20260921/source_revision.json'

def digest(text):return hashlib.sha256(text.encode()).hexdigest()
def save(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')

def main():
    assert os.environ.get('USE_TORCH')=='0'
    OUT.mkdir(exist_ok=True)
    assert not (OUT/'applied.json').exists(),'Revision already applied'
    revision=json.loads(REVISION.read_text());ids=set(revision['episode_ids'])
    source={e['episode_id']:e for e in map(json.loads,SOURCE.read_text().splitlines())}
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==revision['queue_sha256']
    frozen=[json.loads(x) for x in (ROOT/'input_queue_400.jsonl').read_text().splitlines()]
    revised=copy.deepcopy(frozen);changed=[];checks=[];target=[]
    for old,ep in zip(frozen,revised):
        if ep['episode_id'] not in ids:continue
        src=source[ep['episode_id']]
        assert ep['shot_count']==src['shot_count']
        ep['global_prompt_original']=src['global_prompt']
        ep['source_revision']='source_revision_20260922'
        prior={'global':src['global_prompt']}
        changes=[]
        for shot,raw,before in zip(ep['shots'],src['shots'],old['shots']):
            assert shot['shot_id']==raw['shot_id'] and shot['scene_id']==raw['scene_id']
            base=raw['generation_prompt_en'];additions=shot['context_additions']
            for addition in additions:
                assert addition['target_quote'] in base
                for ev in addition['evidence']:
                    assert ev['source_shot_id'] in prior
                    assert ev['quote'] in prior[ev['source_shot_id']]
            text=base+(' '+' '.join(a['text'] for a in additions) if additions else '')
            assert text.startswith(base)
            shot.update(generation_prompt_en_original=base,wan_prompt_en=text,
                original_sha256=digest(base),wan_sha256=digest(text))
            dest=OUT/'prompts'/ep['episode_id']/(shot['shot_id']+'.txt')
            dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(text)
            shot['prompt_file']=str(dest.resolve())
            if text!=before['wan_prompt_en']:
                changes.append(dict(shot_id=shot['shot_id'],old=before['wan_prompt_en'],new=text))
            prior[shot['shot_id']]=base
            checks.append(shot)
        changed.append(dict(episode_id=ep['episode_id'],rank=ep['generation_priority'],
            old_global=old['global_prompt_original'],new_global=ep['global_prompt_original'],shot_changes=changes))
        target.append(ep)
    assert len(target)==3 and len(checks)==18
    assert sum(len(c['shot_changes']) for c in changed)==1
    assert sum(c['old_global']!=c['new_global'] for c in changed)==2
    spec=importlib.util.spec_from_file_location('wan_tokens',FEAS/'repos/Wan2.2/wan/modules/tokenizers.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    tok=mod.HuggingfaceTokenizer(str(FEAS/'models/Wan2.2-T2V-A14B/google/umt5-xxl'),
        seq_len=512,clean='whitespace',local_files_only=True)
    kw=dict(return_tensors=None,padding=False,add_special_tokens=True,return_attention_mask=False)
    texts=[x['wan_prompt_en'] for x in checks];full=tok(texts,truncation=False,**kw)
    assert full==tok(texts,**kw),'Production tokenizer truncates'
    raw_ids=tok([x['generation_prompt_en_original'] for x in checks],truncation=False,**kw)
    for s,ids_,original in zip(checks,full,raw_ids):
        assert len(ids_)<=512
        s['wan_tokens_including_special']=len(ids_)
        s['original_tokens_including_special']=len(original)
    snapshot=OUT/'input_queue_400.v2.jsonl'
    snapshot.write_text(''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in revised))
    (OUT/'revised_episodes.jsonl').write_text(''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in target))
    (OUT/'raw_source_3.jsonl').write_text(''.join(json.dumps(source[e['episode_id']],ensure_ascii=False)+'\n' for e in target))
    save(OUT/'changes.json',changed)
    save(OUT/'tokenizer_audit.json',dict(status='pass',episode_count=3,shot_count=18,
        min_tokens=min(map(len,full)),max_tokens=max(map(len,full)),over_limit=0,
        production_equals_untruncated=True,existing_additions_unchanged=True,
        all_prior_evidence_exact=True,api_tokens=0,api_cost_usd=0))
    request=dict(status='prepared',user_instruction='这三条后续记得按照新版prompt重新生成一下',
        created=time.time(),source_revision=revision,episode_ids=sorted(ids),
        effective_input=str(snapshot.resolve()),effective_input_sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest(),
        policy='rerun completed episode; pending episodes use revised source; preserve seeds/settings/priority/old outputs')
    save(OUT/'request.json',request)
    print(json.dumps(request,ensure_ascii=False));print((OUT/'tokenizer_audit.json').read_text())

if __name__=='__main__':main()
