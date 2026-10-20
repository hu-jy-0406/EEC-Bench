#!/usr/bin/env python3
"""Independent disk readback gates and portable HoloCine prompt package."""
import argparse,collections,csv,hashlib,json,pathlib,shutil,time,zipfile
from run import HERE,ROOT,CONTRACTS,QUEUE,io,read,dump,sha,render,token_audit,validate_candidate,validate_review,usage

def export():
    io.safe_compute();m=read(HERE/'manifest.json');assert sha(QUEUE)==m['queue_sha256']
    out=HERE/'deliverables';out.mkdir(exist_ok=True);rows=[];problems=[]
    source={e['episode_id']:e for e in map(json.loads,QUEUE.read_text().splitlines())}
    for j in m['jobs']:
        eid=j['episode_id'];d=HERE/'episodes'/eid;c=read(d/'contract.json');p=read(d/'input.json');s=source[eid]
        assert sha(d/'input.json')==j['input_sha256']
        assert sha(CONTRACTS/eid/'contract.json')==sha(d/'contract.json')==j['contract_sha256']
        assert sha(CONTRACTS/eid/'alignment_contract.json')==sha(d/'alignment_contract.json')==j['alignment_contract_sha256']
        assert c['prompt']['global_prompt']==s['global_prompt']
        assert [(x['shot_id'],x['text']) for x in c['prompt']['shots']]==[(x['shot_id'],x['generation_prompt_en']) for x in s['shots']]
        row=dict(episode_id=eid,generation_priority=j['rank'],shot_count=j['shot_count'],claim_count=j['claims'],generation_allowed=False,status='no_candidate',tokens=None)
        if not (d/'candidate.json').exists():
            rows.append(row);continue
        candidate=read(d/'candidate.json');review=read(d/'semantic_audit.json')
        validate_candidate(candidate,p);validate_review(review,p)
        ta=token_audit(render(candidate),j['shot_count']);assert ta==read(d/'token_audit.json')
        reasons=[]
        if not ta['within_limit']:reasons.append('over_512_tokens')
        if not ta['production_ids_equal_untruncated']:reasons.append('production_truncation')
        if not ta['shot_spans_complete']:reasons.append('missing_shot_span')
        if review['verdict']!='pass':reasons.append('semantic_audit_failed')
        if candidate['limitations']:reasons.append('drafter_unresolved_limitations')
        allowed=not reasons;ed=out/'episodes'/eid;ed.mkdir(parents=True,exist_ok=True)
        for name in ['contract.json','alignment_contract.json','shot_mapping.json']:shutil.copyfile(d/name,ed/name)
        dump(ed/'entity_schedule.json',c['entity_schedule']);dump(ed/'alias_map.json',candidate['aliases'])
        dump(ed/'token_audit.json',ta);dump(ed/'semantic_audit.json',review)
        native=dict(prompt=render(candidate))
        # Only prompt kwargs are delivered: no unsolicited changes to generation settings.
        dump(ed/'holocine_input.json',native);(ed/'holocine_prompt.txt').write_text(native['prompt']+'\n')
        dump(ed/'structured_prompt.json',dict(global_caption=candidate['global_caption'],shot_captions=[x['caption'] for x in candidate['shots']],shot_ids=[x['shot_id'] for x in candidate['shots']],use='Inspection only. Feed holocine_input.json in raw Mode2; the structured helper adds prose and changes measured token counts.'))
        row.update(generation_allowed=allowed,status='ready' if allowed else 'not_ready',tokens=ta['tokens'],blocking_reasons=reasons,input_path=str((ed/'holocine_input.json').relative_to(out)),contract_path=str((ed/'contract.json').relative_to(out)),alignment_contract_path=str((ed/'alignment_contract.json').relative_to(out)),prompt_sha256=hashlib.sha256(native['prompt'].encode()).hexdigest(),contract_sha256=sha(ed/'contract.json'),alignment_contract_sha256=sha(ed/'alignment_contract.json'),original_scene_ids=[x['scene_id'] for x in s['shots']],schedule_keys=[x['schedule_key'] for x in c['prompt']['shots']])
        dump(ed/'status.json',row);rows.append(row)
        if not allowed:problems.append(dict(episode_id=eid,tokens=ta['tokens'],reasons=reasons,limitations=candidate['limitations'],unsupported_claims=review['unsupported_claims'],additions=review['additions'],source_omissions=review['source_omissions'],schedule_issues=review['schedule_issues'],alias_issues=review['alias_issues']))
    dump(out/'index.json',dict(schema_version='holocine_prompt_contract_sidecar_v1',episodes=rows))
    dump(out/'exceptions.json',problems)
    for name,subset in [('full400',rows),('core100',rows[:100]),('priority200',rows[:200]),('stage2_additional100',rows[100:200]),('stage3_remaining200',rows[200:])]:
        (out/(name+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in subset))
    (out/'ready_queue.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows if r['generation_allowed']))
    u=usage();audit=dict(status='complete' if all(r['generation_allowed'] for r in rows) else 'incomplete_with_explicit_exceptions',episodes=len(rows),shots=sum(r['shot_count'] for r in rows),claims=sum(r['claim_count'] for r in rows),states=dict(collections.Counter(r['status'] for r in rows)),original_contracts_byte_preserved=True,source_revisions_and_order_preserved=True,all_candidate_claim_partitions_valid=True,tokenizer_recomputed=True,api_calls=u['calls'],total_tokens=u['total_tokens'],standard_api_equivalent_usd=u['standard_api_equivalent_usd'],actual_bill_available=False,independent_human_semantic_validation=False)
    dump(HERE/'independent_delivery_audit.json',audit)
    print(json.dumps(audit),flush=True)

if __name__=='__main__':export()
