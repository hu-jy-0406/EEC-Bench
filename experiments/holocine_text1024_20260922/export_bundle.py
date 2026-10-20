#!/usr/bin/env python3
"""Export unchanged, fully audited prompts with explicit1024 runtime requirement."""
import hashlib,json,pathlib,shutil,sys,zipfile
HERE=pathlib.Path(__file__).resolve().parent
OLD=HERE.parent/'holocine_prompt_adaptation_20260922'
sys.path.insert(0,str(OLD));import run as prior
prior.io.safe_compute();audit=prior.read(HERE/'input_audit.json');assert audit['status']=='pass' and audit['over1024']==0
dynamic=prior.read(HERE/'dynamic_context_validation.json');assert dynamic['status']=='pass'
out=HERE/'deliverables';shutil.copytree(OLD/'deliverables',out,dirs_exist_ok=True)
byid={r['episode_id']:r for r in audit['rows']}
idx=prior.read(out/'index.json');rows=idx['episodes']
shutil.copyfile(out/'exceptions.json',out/'historical_512_exceptions.json')
for r in rows:
    eid=r['episode_id'];d=out/'episodes'/eid;a=byid[eid]
    native=prior.read(d/'holocine_input.json')['prompt']
    assert hashlib.sha256(native.encode()).hexdigest()==r['prompt_sha256']
    assert prior.read(d/'semantic_audit.json')['verdict']=='pass'
    r.update(historical_status_512=r['status'],generation_allowed=True,status='ready',blocking_reasons=[],required_text_len=1024,runtime_profile='eec_holocine_text1024_v1',full_pretrained_video_validation=False)
    t=prior.read(d/'token_audit.json');t.update(limit=1024,within_limit=True,production_ids_equal_untruncated=True,shot_spans_complete=True,shot_caption_token_spans=a['shot_caption_token_spans'],recomputed_for_profile='eec_holocine_text1024_v1')
    prior.dump(d/'token_audit.json',t);prior.dump(d/'status.json',r)
idx.update(schema_version='holocine_prompt_contract_sidecar_text1024_v1',required_text_len=1024)
prior.dump(out/'index.json',idx);prior.dump(out/'exceptions.json',[])
for name,subset in [('full400',rows),('core100',rows[:100]),('priority200',rows[:200]),('stage2_additional100',rows[100:200]),('stage3_remaining200',rows[200:]),('ready_queue',rows)]:
    (out/(name+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in subset))
for name in ['profile.json','text_context.py','dynamic_context_validation.json']:
    shutil.copyfile(HERE/name,out/name)
verifier=(OLD/'verify_bundle.py').read_text().replace("ta['tokens']<=512", "ta['tokens']<=1024 and ta['limit']==1024 and r['required_text_len']==1024")
(out/'verify_bundle.py').write_text(verifier)
(out/'README.md').write_text('''# HoloCine 400 prompts: explicit1024 text profile

All400 prompts and original evaluation contracts are unchanged from the full-source-and-contract-audited delivery. All fit1024;159 exceed the upstream default512. This package requires eec_holocine_text1024_v1 for EVERY episode, including previously short prompts. Do not feed its queue into an unmodified512-configured pipeline.

After loading the official pipeline, use text_context.configure_pipeline(pipe) to set BOTH pipe.prompter.text_len and pipe.prompter.tokenizer.seq_len to1024. The public checkout itself is unchanged. Prefer text_context.generate_episode(pipe, prompt, expected_shots, **original_generation_kwargs), which applies this profile and rejects truncation/shot-count mismatches before diffusion. Supply the original separately validated frame counts, shot_cut_frames, sampling, resolution and seeds. No video generation is launched by this package.

Use exact raw Mode2 text from episodes/<id>/holocine_input.json. Contracts, alignment contracts, schedules, entity aliases and shot mappings remain unchanged. The old512 exceptions are retained in historical_512_exceptions.json; they are resolved only by the explicit configuration change, not by deleting information or changing semantic audit verdicts.

Validation covers the actual tokenizer for all400, native shot spans, and actual official T5/CrossAttention/mask code using small CPU models at1024 sequence length. It is NOT a full pretrained text-encoder/14B video inference or a quality comparison.1024 is an explicit benchmark configuration change, not a claimed official setting. Keep this distinction in experiment reports; increased memory/runtime and long-context quality still need generation-side validation.

Run python verify_bundle.py to verify recorded file hashes, contracts, schedules, claim coverage, prompt rendering and1024 queue gates. This portable verifier does not rerun tokenizer/model inference.
''')
hashes={str(p.relative_to(out)):prior.sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='files.sha256.json'}
prior.dump(out/'files.sha256.json',hashes)
ns={'__name__':'portable_verifier'};exec(compile(verifier,str(out/'verify_bundle.py'),'exec'),ns)
validation=ns['verify'](out)
archive=HERE/'holocine_prompts_contracts_400_text1024.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in sorted(out.rglob('*')):
        if p.is_file():z.write(p,'holocine_inputs/'+str(p.relative_to(out)))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
validation.update(profile='eec_holocine_text1024_v1',archive=str(archive),archive_bytes=archive.stat().st_size,archive_sha256=prior.sha(archive),new_api_calls=0,new_billable_api_tokens=0,new_api_usd=0,full_video_validation=False)
prior.dump(HERE/'package_validation.json',validation);print(json.dumps(validation),flush=True)
