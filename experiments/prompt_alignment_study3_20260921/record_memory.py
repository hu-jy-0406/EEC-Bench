from pathlib import Path
import json
R=Path(__file__).resolve().parent
W=R.parents[2]
read=lambda p:json.loads(p.read_text())
r=read(R/'alignment_visible/results.json');u=read(R/'usage_reconciled.json');audit=read(R/'alignment_visible/audit.json')
assert audit['status']=='passed'
key='prompt_alignment_b_v1_20260921'
base='EECBench/experiments/prompt_alignment_study3_20260921'
info=dict(status='implemented_study3_frozen_frontend_component_validated',specification='EECBench/docs/prompt-alignment-b-v1.md',
 report=base+'/REPORT.md',normal_reference=base+'/reference/story_prompt_zh.md',selected_contract=base+'/frozen_visible/contract.json',selected_results=base+'/alignment_visible/results.json',
 runner='EECBench/scripts/gs_prompt_alignment.py',integration='optional --prompt-alignment-contract; full temporal_v2 after binding',
 prompt_entities=9,claims=83,binding=dict(bound=11,unbound=23,unknown=2),
 scores={k:v['score'] for k,v in r['dimensions'].items()},unknown_counts={k:v['micro']['U'] for k,v in r['dimensions'].items()},
 tests=39,all_prior_stages_unchanged=True,source_frame_scope_cost_audits='passed',
 final_binding_and_scoring_calls=7,final_tokens=u['selected_tokens'],final_standard_api_equivalent_usd=u['selected_standard_api_equivalent_usd'],
 development_calls=6,development_tokens=330959,development_standard_api_equivalent_usd=3.651374,
 combined_tokens=u['total_tokens'],combined_standard_api_equivalent_usd=u['total_standard_api_equivalent_usd'],
 normal_reference_precedes_implementation=True,appearance_observation_domain='when_visible',
 full_gpu_run=False,human_calibrated=False,automatic_text_compiler_paid_test=False,spatial_judgment_variation='mug/holder cross-shot violations in first trial became satisfied; no recall/quality claim',active_task_inference_processes=False)
p=W/'research-state.yaml';content=p.read_text()
if key+':' not in content:
 with p.open('a') as f:
  f.write('\n\n'+key+':\n')
  for k,v in info.items():f.write('  '+k+': '+json.dumps(v,ensure_ascii=False)+'\n')
heading='## 2026-09-21 — Normal Study3 reference and prompt alignment B implemented'
text=(heading+'\n\nUser selected only B and required a normal narrative before pipeline work because original generation instructions inject inconsistencies. Wrote story_prompt_zh.md first, then added gs_prompt_alignment.py and optional --prompt-alignment-contract to temporal_v2; freeze reference/registry/schedule/atomic claims before frontend, bind after global registry, independent alignment at full. Existing narrative/registration/identity/temporal/appearance/DINO gates remain unchanged. No A/C or second verifier.\n\n'
+'Study3 text-authored9prompt entities/83claims; new binding36visual records=11bound/23unbound/2unknown. First development trial overextended ordinary appearance into offscreen throughout verification; preserved6calls/'+str(330959)+'tokens/USD3.651374. Corrected all28appearance claims to when_visible; other55claims,normaltext,registry unchanged. Final6fresh calls cover all scopes; binding reused exact registry, no chosen verdict mixing. Three single-shot calls remain isolated, cross-shot calls separate; all originalframes/raw2D/defining3D/cameras, no prior motion/scores. Cross-shot geometry not numerically registered in this branch; use visual landmarks/unknown.\n\n'
+'Five independent hierarchical conditional scores with T/F/U and unknown-value bounds, no overall/fusion; unknown not success. Scores '+json.dumps(info['scores'])+'; unknowns '+json.dumps(info['unknown_counts'])+'.39tests and source/frame/population/scope/cost audits passed, no-contract saved production plan exact; two methods x four stop options retain original stages. Final binding+scoring '+str(u['selected_tokens'])+'tokens/USD'+f'{u["selected_standard_api_equivalent_usd"]:.6f}'+', all development '+str(u['total_tokens'])+'tokens/USD'+f'{u["total_standard_api_equivalent_usd"]:.6f}'+' standard API equivalent, not bill. Frozen frontend reused, no full GPU rerun or human calibration. Automatic text compiler interface exists but paid Study3 compiler not run; Study3 claims human text-authored. Report '+base+'/REPORT.md, spec EECBench/docs/prompt-alignment-b-v1.md. Cross-shot mug/holder verdicts changed from violated in development to satisfied in selected run; changed conditional spatial score is not a quality improvement claim. All own inference ended.\n')
for file in ['findings.md','research-log.md','docs/continuity.md']:
 p=W/file
 if heading not in p.read_text():
  with p.open('a') as f:f.write('\n\n'+text)
heading='## Prompt alignment B — explicit user selection (2026-09-21)'
p=W/'AGENTS.md'
if heading not in p.read_text():
 with p.open('a') as f:f.write('\n\n'+heading+'\n\n'
 '- User selected scheme B only: normal evaluation narrative → frozen atomic requirements → scoped pixel/evidence verification → code aggregation. Do not mix deliberate generation-error instructions into the normal reference. Study3 reference was written before implementation.\n'
 '- Use `EECBench/scripts/gs_prompt_alignment.py` and `EECBench/docs/prompt-alignment-b-v1.md`. Integrated opt-in: `--prompt-alignment-contract`, temporal_v2/full, after reference-specific prompt binding. Preserve existing narrative, registration choice, old consistency/appearance prompts, scores and identity population. No A/C, fusion, second verifier or automatic cross-scene identity merging.\n'
 '- Ordinary appearance uses `when_visible`; offscreen/occlusion alone does not invalidate supported visible attributes. Explicit throughout/offscreen persistence keeps its own semantics and can remain unknown. Preserve every frozen claim, including unbound/missing observations and specified static requirements; no negative-cosine or observed-moving-only selection.\n'
 '- Five separate hierarchical conditional T/F/U scores and unknown-value intervals (not confidence intervals); unknown is not success. Dependencies block unsupported attributes without multiplying absence penalties. All original relevant frames/raw boxes/defining geometry, own-shot isolation, cross-shot scopes separate; no prior anomaly or motion verdicts as visual proof. Current cross-shot alignment has no registered numeric geometry comparison.\n'
 '- Selected Study3 contract/results: `EECBench/experiments/prompt_alignment_study3_20260921/frozen_visible/contract.json` and `alignment_visible/`; initial `frozen/`/`alignment/` are preserved development history. Report both development and selected expenses. Frozen frontend component validation, not fresh full GPU evaluation or human calibration. Automatic compiler interface exists; Study3 used text-authored claims.\n')
print('Appended project memory')
