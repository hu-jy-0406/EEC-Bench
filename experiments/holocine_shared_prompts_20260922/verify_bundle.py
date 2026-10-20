"""Portable readback verifier for unchanged common-model text and contracts."""
import hashlib,json,pathlib
def verify(root):
    read=lambda p:json.loads(p.read_text())
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    digest=lambda t:hashlib.sha256(t.encode()).hexdigest()
    hashes=read(root/'files.sha256.json')
    for name,value in hashes.items():
        p=(root/name).resolve();assert root.resolve() in p.parents
        assert sha(p)==value,name
    index=read(root/'index.json');rows=index['episodes'];limit=read(root/'profile.json')['text_len']
    assert len(rows)==400 and len({r['episode_id'] for r in rows})==400
    assert [r['generation_priority'] for r in rows]==list(range(1,401))
    assert max(r['tokens'] for r in rows)==limit==index['required_text_len']
    shots=claims=0
    for r in rows:
        d=root/'episodes'/r['episode_id'];st=read(d/'structured_prompt.json');p=read(d/'holocine_input.json')['prompt']
        assert p=='[global caption] '+st['global_caption']+' [per shot caption] '+' [shot cut] '.join(st['shot_captions'])
        assert (d/'holocine_prompt.txt').read_text()==p+'\n'
        assert digest(p)==r['prompt_sha256']
        c=read(d/'contract.json');a=read(d/'alignment_contract.json');mapping=read(d/'shot_mapping.json')
        assert sha(d/'contract.json')==r['contract_sha256'] and sha(d/'alignment_contract.json')==r['alignment_contract_sha256']
        assert a['claims']==c['claims'] and read(d/'entity_schedule.json')==c['entity_schedule']
        assert st['global_caption']==c['prompt']['global_prompt']
        assert st['shot_ids']==[s['shot_id'] for s in c['prompt']['shots']]==[m['shot_id'] for m in mapping]
        for txt,cs,m in zip(st['shot_captions'],c['prompt']['shots'],mapping):
            suffix=(' '+' '.join(v['text'] for v in m['context_additions'])) if m['context_additions'] else ''
            assert txt==cs['text']+suffix and digest(txt)==m['prompt_sha256']
            assert cs['schedule_key']==m['contract_schedule_key']
        t=read(d/'token_audit.json');assert t['limit']==r['required_text_len']==limit
        assert t['tokens']==r['tokens']<=limit and t['untruncated'] and t['shots']==r['shot_count']
        assert len(t['shot_caption_token_spans'])==r['shot_count'] and r['generation_allowed']
        proof=read(d/'shared_text_audit.json');assert proof['all_shot_texts_byte_equal_current_wan_storymem']
        assert proof['global_text_equal_current_source_wan_storymem_contract']
        shots+=r['shot_count'];claims+=len(c['claims'])
    assert shots==2000 and claims==64724
    queue=[json.loads(s) for s in (root/'ready_queue.jsonl').read_text().splitlines() if s]
    assert queue==rows
    return dict(status='pass',episodes=400,shots=shots,claims=claims,text_len=limit,hashed_files=len(hashes),full_video_validation=False)
if __name__=='__main__':print(json.dumps(verify(pathlib.Path(__file__).resolve().parent),indent=2))
