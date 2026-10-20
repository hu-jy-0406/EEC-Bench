#!/usr/bin/env python3
import hashlib,json,shutil,zipfile
from run import HERE,ROOT,io,read,dump,sha
from verify_bundle import verify

io.safe_compute();out=HERE/'deliverables';idx=read(out/'index.json')['episodes']
assert len(idx)==400 and all(r['status'] in ['ready','not_ready'] for r in idx),'Every episode must have an audited candidate before packaging'
shutil.copyfile(HERE/'verify_bundle.py',out/'verify_bundle.py')
readme='''# HoloCine-specific prompts with frozen evaluation contracts

All400episodes retain the original source selection, order, shot counts, contracts and schedules. The index distinguishes ready prompts from explicit exceptions. Only ready_queue.jsonl authorizes generation under the deployed512-token HoloCine input. Do not generate not_ready episodes by truncating their text.

For each episode:
- holocine_input.json supplies the exact native raw prompt (Mode2).
- holocine_prompt.txt is the same text plus a final newline.
- structured_prompt.json is a readable global/per-shot view ONLY. The official structured helper appends prose, changing the token count; do not feed it blindly.
- contract.json and alignment_contract.json are byte-preserved canonical evaluation standards. No claim or schedule was weakened for compression.
- entity_schedule.json is the exact original schedule export; shot_mapping.json maps native shot indices to source ShotIDs and contract schedule keys. Schedule omission means unknown/not required, not absence.
- alias_map.json links prompt aliases to canonical entities; it is provenance, not extra model conditioning.
- semantic_audit.json contains independent all-claim/source/schedule review. token_audit.json records the actual deployed tokenizer check including EOS and delimiters.
- status.json states whether generation is allowed; exceptions.json explains all blocked candidates.

Preserve original shot order and source-specified durations; do not infer an unspecified duration from other shots. Supply the separately validated generation duration/cut parameters; this package changes prompt text only and does not launch or alter video generation. Do not concatenate contracts, aliases, old prompts or extra global text into the measured input. Do not silently truncate, omit shots, change specified durations or extend the text encoder to bypass a blocked record.

Use the unchanged alignment_contract.json to evaluate videos generated from an approved prompt. Natural-language semantic review is model-based development validation, not a mathematical equivalence proof or independent human annotation.

core100 and priority200 are cumulative nested subsets; stage2_additional100 and stage3_remaining200 are incremental. None of these structural subset lists implies every member is ready: consult generation_allowed.

Run: python verify_bundle.py
This portable verifier checks file hashes, source-contract joins, canonical claims, schedule mappings, recorded review coverage, native rendering and queue gates. It does not run a new semantic model or re-tokenize. Full tokenizer recomputation was performed compute-side before export.
'''
(out/'README.md').write_text(readme)
hashes={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='files.sha256.json'}
dump(out/'files.sha256.json',hashes)
validation=verify(out)
archive=HERE/'holocine_prompts_contracts_400.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in sorted(out.rglob('*')):
        if p.is_file():z.write(p,'holocine_inputs/'+str(p.relative_to(out)))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None;count=len(z.infolist())
validation.update(archive=str(archive),archive_bytes=archive.stat().st_size,archive_sha256=sha(archive),zip_entries=count)
dump(HERE/'package_validation.json',validation);print(json.dumps(validation),flush=True)
