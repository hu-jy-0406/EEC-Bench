#!/usr/bin/env python3
"""Portable, standard-library-only structural/hash verifier (not a semantic judge)."""
import argparse,hashlib,json,pathlib

def verify(root):
    read=lambda p:json.loads(p.read_text())
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    files=read(root/'files.sha256.json')
    for name,h in files.items():
        p=(root/name).resolve();assert root.resolve() in p.parents,'Unsafe relative path'
        assert p.is_file() and digest(p)==h,name
    index=read(root/'index.json')['episodes'];assert len(index)==400
    assert [r['generation_priority'] for r in index]==list(range(1,401))
    assert len({r['episode_id'] for r in index})==400
    shots=claims=ready=0
    for r in index:
        d=root/'episodes'/r['episode_id'];c=read(d/'contract.json');a=read(d/'alignment_contract.json')
        assert digest(d/'contract.json')==r['contract_sha256']
        assert digest(d/'alignment_contract.json')==r['alignment_contract_sha256']
        assert a['claims']==c['claims']
        assert read(d/'entity_schedule.json')==c['entity_schedule']
        prompt=read(d/'holocine_input.json')['prompt'];st=read(d/'structured_prompt.json')
        assert prompt=='[global caption] '+st['global_caption'].strip()+' [per shot caption] '+' [shot cut] '.join(x.strip() for x in st['shot_captions'])
        assert hashlib.sha256(prompt.encode()).hexdigest()==r['prompt_sha256']
        assert (d/'holocine_prompt.txt').read_text()==prompt+'\n'
        mapping=read(d/'shot_mapping.json');sid=[s['shot_id'] for s in c['prompt']['shots']]
        assert [x['shot_id'] for x in mapping]==st['shot_ids']==sid==a['shot_ids']
        assert [x['holo_shot_index'] for x in mapping]==list(range(r['shot_count']))
        assert [x['contract_schedule_key'] for x in mapping]==[s['schedule_key'] for s in c['prompt']['shots']]
        rv=read(d/'semantic_audit.json');known=[x['claim_id'] for x in c['claims']]
        got=rv['supported_claim_ids']+[x['claim_id'] for x in rv['unsupported_claims']]
        assert len(got)==len(set(got)) and set(got)==set(known)
        assert rv['checked_shot_ids']==sid
        if r['generation_allowed']:
            ta=read(d/'token_audit.json')
            assert r['status']=='ready' and rv['verdict']=='pass'
            assert ta['tokens']<=512 and ta['production_ids_equal_untruncated'] and ta['shot_spans_complete']
            assert not any(rv[k] for k in ['unsupported_claims','additions','source_omissions','schedule_issues','alias_issues'])
            ready+=1
        shots+=r['shot_count'];claims+=len(known)
    queue=[json.loads(s) for s in (root/'ready_queue.jsonl').read_text().splitlines() if s]
    assert queue==[r for r in index if r['generation_allowed']]
    assert shots==2000 and claims==64724
    return dict(status='pass',episodes=400,shots=shots,claims=claims,ready=ready,not_ready=400-ready,hashed_files=len(files),semantic_proof=False)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=pathlib.Path,default=pathlib.Path(__file__).resolve().parent);args=ap.parse_args();print(json.dumps(verify(args.root),indent=2))
