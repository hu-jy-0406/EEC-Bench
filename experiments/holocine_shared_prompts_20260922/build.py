#!/usr/bin/env python3
"""Use exact current Wan/StoryMem shared uncompressed text; derive Holo text budget."""
import collections,hashlib,json,pathlib,shutil,sys,time
HERE=pathlib.Path(__file__).resolve().parent
EXP=HERE.parent
OLD=EXP/'holocine_prompt_adaptation_20260922'
sys.path.insert(0,str(OLD));import run as old
read,dump,sha=old.read,old.dump,old.sha
STORY=EXP/'storymem_prompt_adaptation_20260922/deliverables'
WAN=EXP/'wan_generation_400_20260921/prompt_revision_20260922/input_queue_400.v2.jsonl'
text_sha=lambda t:hashlib.sha256(t.encode()).hexdigest()

def main():
    allocation=old.io.safe_compute();start=time.time();t=old.tokenizer()
    wan=[json.loads(s) for s in WAN.read_text().splitlines() if s];si=read(STORY/'index.json')['episodes']
    raw=[json.loads(s) for s in old.QUEUE.read_text().splitlines() if s]
    assert len(wan)==len(si)==len(raw)==400
    assert [x['episode_id'] for x in wan]==[x['episode_id'] for x in si]==[x['episode_id'] for x in raw]
    out=HERE/'deliverables';out.mkdir(parents=True,exist_ok=True);rows=[];proofs=[]
    for w,s,src in zip(wan,si,raw):
        eid=w['episode_id'];script=read(STORY/s['story_script_path']);c=read(old.CONTRACTS/eid/'contract.json')
        assert script['story_overview']==w['global_prompt_original']==src['global_prompt']==c['prompt']['global_prompt']
        texts=[text for scene in script['scenes'] for text in scene['video_prompts']]
        assert texts==[shot['wan_prompt_en'] for shot in w['shots']]
        assert len(texts)==w['shot_count']==len(c['prompt']['shots'])
        assert [v['shot_id'] for v in w['shots']]==[v['shot_id'] for v in s['shots']]==[v['shot_id'] for v in c['prompt']['shots']]
        d=out/'episodes'/eid;d.mkdir(parents=True,exist_ok=True);mapping=[]
        for i,(ws,ss,cs,rs,txt) in enumerate(zip(w['shots'],s['shots'],c['prompt']['shots'],src['shots'],texts)):
            assert ws['generation_prompt_en_original']==cs['text']==rs['generation_prompt_en']
            suffix=(' '+' '.join(a['text'] for a in ws['context_additions'])) if ws['context_additions'] else ''
            assert txt==cs['text']+suffix and text_sha(txt)==ss['prompt_sha256']
            assert ws['scene_id']==ss['source_scene_id']==rs['scene_id']
            assert ss['contract_schedule_key']==cs['schedule_key']
            mapping.append(dict(shot_id=ws['shot_id'],holo_shot_index=i,source_scene_id=ws['scene_id'],contract_schedule_key=cs['schedule_key'],prompt_sha256=text_sha(txt),storymem_scene_num=ss['storymem_scene_num'],storymem_shot_num=ss['storymem_shot_num'],target_duration_seconds=ws['target_duration_seconds'],context_additions=ws['context_additions']))
        prompt='[global caption] '+script['story_overview']+' [per shot caption] '+' [shot cut] '.join(texts)
        encoded=t(prompt,truncation=False,return_tensors=None,padding=False,add_special_tokens=True)
        count=len(encoded['input_ids'][0])
        dump(d/'holocine_input.json',dict(prompt=prompt));(d/'holocine_prompt.txt').write_text(prompt+'\n')
        dump(d/'structured_prompt.json',dict(global_caption=script['story_overview'],shot_captions=texts,shot_ids=[m['shot_id'] for m in mapping],use='Exact shared text; feed raw native prompt, not structured helper that appends prose.'))
        for f in ['contract.json','alignment_contract.json']:
            shutil.copyfile(old.CONTRACTS/eid/f,d/f)
        assert read(d/'alignment_contract.json')['claims']==c['claims']
        dump(d/'entity_schedule.json',c['entity_schedule']);dump(d/'shot_mapping.json',mapping)
        proof=dict(episode_id=eid,global_text_equal_current_source_wan_storymem_contract=True,all_shot_texts_byte_equal_current_wan_storymem=True,all_original_contract_shot_bodies_exact_prefix=True,only_existing_audited_context_additions_retained=True,new_rewrite_or_semantic_model_call=False,contract_sha256=sha(d/'contract.json'),alignment_contract_sha256=sha(d/'alignment_contract.json'),story_script_sha256=sha(STORY/s['story_script_path']))
        dump(d/'shared_text_audit.json',proof);proofs.append(proof)
        rows.append(dict(episode_id=eid,generation_priority=w['generation_priority'],shot_count=len(texts),claim_count=len(c['claims']),tokens=count,prompt_sha256=text_sha(prompt),input_path=str((d/'holocine_input.json').relative_to(out)),contract_path=str((d/'contract.json').relative_to(out)),alignment_contract_path=str((d/'alignment_contract.json').relative_to(out)),contract_sha256=proof['contract_sha256'],alignment_contract_sha256=proof['alignment_contract_sha256']))
    maximum=max(r['tokens'] for r in rows)
    profile=dict(profile='eec_holocine_shared_uncompressed_v1',text_len=maximum,tokenizer_seq_len=maximum,basis='Exact maximum of400 complete native prompts with current Wan/StoryMem shared global+shot text, markers and EOS.',all400_same_profile=True,upstream_default=512,weights_changed=False,shot_settings_changed=False,officially_quality_validated=False,user_request='用压缩之前的prompt，和Wan2.2与StoryMem保持一致；直接根据这个上限来')
    dump(HERE/'profile.json',profile);dump(out/'profile.json',profile)
    adapter=(EXP/'holocine_text1024_20260922/text_context.py').read_text().replace('DEFAULT_TEXT_LEN = 1024',f'DEFAULT_TEXT_LEN = {maximum}').replace('eec_holocine_text1024_v1','eec_holocine_shared_uncompressed_v1')
    (HERE/'text_context.py').write_text(adapter);(out/'text_context.py').write_text(adapter)
    ns={'__name__':'profile_adapter'};exec(compile(adapter,str(HERE/'text_context.py'),'exec'),ns)
    import types
    pipe=types.SimpleNamespace(prompter=types.SimpleNamespace(text_len=512,tokenizer=t));ns['configure_pipeline'](pipe)
    for r in rows:
        d=out/'episodes'/r['episode_id'];a=ns['validate_prompt'](pipe,read(d/'holocine_input.json')['prompt'],r['shot_count'])
        assert a['tokens']==r['tokens'] and a['limit']==maximum
        dump(d/'token_audit.json',a)
        r.update(generation_allowed=True,status='ready_input_validated',required_text_len=maximum,runtime_profile=profile['profile'],full_pretrained_video_validation=False)
        dump(d/'status.json',r)
    dump(out/'index.json',dict(schema_version='holocine_shared_uncompressed_v1',required_text_len=maximum,episodes=rows))
    for name,subset in [('full400',rows),('core100',rows[:100]),('priority200',rows[:200]),('stage2_additional100',rows[100:200]),('stage3_remaining200',rows[200:]),('ready_queue',rows)]:
        (out/(name+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in subset))
    byshot={str(n):dict(count=sum(r['shot_count']==n for r in rows),minimum=min(r['tokens'] for r in rows if r['shot_count']==n),maximum=max(r['tokens'] for r in rows if r['shot_count']==n)) for n in (4,6,8)}
    audit=dict(status='pass',episodes=len(rows),shots=sum(r['shot_count'] for r in rows),claims=sum(r['claim_count'] for r in rows),maximum_tokens=maximum,minimum_tokens=min(r['tokens'] for r in rows),longest_episode_ids=[r['episode_id'] for r in rows if r['tokens']==maximum],by_shot_count=byshot,source_wan_queue_sha256=sha(WAN),source_storymem_index_sha256=sha(STORY/'index.json'),source_raw_queue_sha256=sha(old.QUEUE),all2000shot_texts_byte_equal_wan_and_storymem=True,all400globals_equal=True,contracts_and_schedules_unchanged=True,no_truncation=True,all_shot_spans_complete=True,new_api_calls=0,new_billable_api_tokens=0,new_api_usd=0,allocation=allocation,seconds=time.time()-start,full_pretrained_video_validation=False)
    dump(HERE/'input_audit.json',audit);print(json.dumps(audit),flush=True)
if __name__=='__main__':main()
