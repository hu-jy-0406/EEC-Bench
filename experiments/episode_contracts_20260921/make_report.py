import collections,html,json,time
from pathlib import Path
import run
run.io.safe_compute()
audit=run.read(run.HERE/'independent_validation.json');assert audit['status']=='pass'
u=run.read(run.HERE/'usage_cost.json');assert all(r['status']!='running' for r in u['rows'])
if u['standard_api_equivalent_usd'] is None:
 cost_text=f"Known standard API equivalent subtotal USD {u['known_subtotal_usd']:.6f}; full amount unavailable because {u['unavailable_or_inflight_costs']} attempts have no complete usable usage record. Reported token totals include recorded usage only."
else:
 cost_text=f"Standard API equivalent USD {u['standard_api_equivalent_usd']:.6f}."
idx=run.read(run.HERE/'deliverables/index.json');assert len(idx)==400
out=run.HERE/'deliverables';amb=[];problems=[];blocks=[]
for row in idx:
 c=run.read(out/row['contract']);eid=c['episode_id']
 for note in c['unresolved']:amb.append(dict(episode_id=eid,note=note))
 p=out/row['contract'];md=['# '+eid,'','Source: current authoritative shared episode prompts.','', '## Schedule','', '| Shot | Characters | Places | Objects |','|---|---|---|---|']
 for s in c['prompt']['shots']:
  v=c['entity_schedule'][s['schedule_key']];md.append('| '+s['shot_id']+' | '+' | '.join(', '.join(v[k]).replace('|',' / ') for k in ('characters','places','objects'))+' |')
 md+=['','## Entities','']
 for label,e in c['entity_descriptions'].items():md.append('- **'+label+' / '+e['name']+'**: '+e['description'])
 md+=['','## Original prompts','','### Global','',c['prompt']['global_prompt']]
 for s in c['prompt']['shots']:md+=['','### '+s['shot_id'],'',s['text']]
 md+=['','## Claims','']
 for dim in run.align.DIMENSIONS:
  md+=['','### '+dim,'']
  for q in c['claims']:
   if q['dimension']==dim:md.append('- `'+q['claim_id']+'` ['+', '.join(q['shot_ids'])+'] '+q['expected']+' ('+', '.join(q['entity_ids'])+'; '+q['quantifier']+'; '+q['coordinate_frame']+')')
 if c['unresolved']:md+=['','## Source ambiguity notes','']+['- '+x for x in c['unresolved']]
 (p.parent/'review.md').write_text('\n'.join(md)+'\n')
 blocks.append('<tr><td>'+str(row['priority_index']+1)+'</td><td><a href="'+html.escape(row['contract'])+'">'+html.escape(eid)+'</a></td><td>'+str(row['shots'])+'</td><td>'+str(row['entities'])+'</td><td>'+str(row['claims'])+'</td><td>'+str(len(c['unresolved']))+'</td><td><a href="episodes/'+html.escape(eid)+'/review.md">Read</a></td></tr>')
run.dump(out/'ambiguities.json',amb)
(out/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>Episode contracts</title><style>body{font:15px system-ui;margin:30px}td,th{padding:7px;border-bottom:1px solid #ddd;text-align:left}input{padding:9px;width:420px}table{border-collapse:collapse}</style><h1>400 episode contracts</h1><p>Original prompts; EntityBench inventories/schedules; four-dimensional claims. Review is model-based, not human ground truth.</p><input id="q" placeholder="Filter episode ID" oninput="document.querySelectorAll(\'tbody tr\').forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(this.value.toLowerCase()))"><table><thead><tr><th>#</th><th>Episode</th><th>Shots</th><th>Entities</th><th>Claims</th><th>Ambiguities</th><th>Readable</th></tr></thead><tbody>'+''.join(blocks)+'</tbody></table>')
counts=audit['counts'];dims=' / '.join(f'{k}: {counts[k]}' for k in run.align.DIMENSIONS)
spans=[(r['started'],r['started']+r['seconds']) for r in u['rows'] if r.get('seconds') is not None]
span=max(e for s,e in spans)-min(s for s,e in spans)
report=f'''# Full400 episode schedule + claims

Completed {counts['episodes']} episodes / {counts['shots']} shots from the current authoritative shared global and per-shot prompts in the priority queue, including user-authorized source corrections.

- Primary files: `deliverables/episodes/<episode_id>/contract.json`.
- Main fields: `entity_descriptions`, `entity_schedule`, `claims`; no duplicate scene_id.
- Totals: {counts['entities']} entity records, {counts['claims']} claims ({dims}).
- Evaluator-compatible derivatives: `alignment_contract.json` beside each primary contract. All pass the existing validator; all claims are identical to the primary files.
- Index and browsing: `deliverables/index.json`, `deliverables/review.html`, per-episode `review.md`.
- Queue exports: contracts_400.jsonl, core_100.jsonl, priority_200.jsonl, stage2_additional_100.jsonl, stage3_remaining_200.jsonl. Original IDs and nested subset order preserved.

## Validation

All400 received independent fresh-context text audit after compilation. Audit revised {counts['review_revised']} episodes. {counts['source_units']} source sentence units retain coverage references and explicit unscored fragments. Source/queue hashes, all original prompt strings, quote references, schedule/entity/claim IDs, dependencies, deterministic adapter equivalence, actual review responses and subset contents pass the independent on-disk audit.

Use `source_revision.json` to match the current source version to generation inputs and contracts. The three affected model-specific prompt adaptations require refresh before generation against this version.

The current shared prompts are the semantic source. No source-video observations, images, prior visual detector inventories, generated outputs or Wan-specific additions enter compilation. The Wan adaptations retain additional model-specific text outside these shared original-prompt contracts. No video evaluation was rerun.

{len(amb)} source-ambiguity notes are preserved in `deliverables/ambiguities.json` and the corresponding contracts, not forced into fabricated certainty. These require case-specific interpretation or unknown handling during evaluation. Schedule omission is not prohibition. Same registered places express intended location recurrence; shared incidental location visibility alone is not proof of a common camera scene.

This is full model-based semantic review plus structural/provenance verification, not a formal proof of natural-language equivalence or independent human annotation. Pure filmmaking/style/audio/timing and independent temporal-order/offscreen-persistence requirements remain explicitly unscored under the existing four-dimensional protocol. Their current source text is retained verbatim.

## Usage and runtime

All attempts including mechanical rejections/recovery: {u['calls']} calls; {u['total_tokens']:,} recorded tokens = {u['usage']['input_tokens']:,} input (including {u['usage']['cached_input_tokens']:,} cached subset) + {u['usage']['output_tokens']:,} output. {cost_text} These estimates are not actual bills. Recorded verified 2026-09-20 Astra pricing: USD/M uncached10, cached-read1, output50 within the recorded standard context limit; no cache double counting. Actual billed amount unavailable.

First-to-last model interval {span:.3f}s, including pilot and recovery; maximum recorded call concurrency {audit['max_call_overlap']}. This is contract-construction time, not video generation/evaluation runtime. CPU/API only on existing206117/node306 with low-priority bounded CPU affinity and GPUs hidden; no new allocation. Parent conversation and cluster price excluded.

Initial pilot local validator incorrectly rejected a response solely for honest source-ambiguity notes. The local acceptance rule was corrected to retain ambiguity rather than forcing unsupported certainty; original responses and additional attempts remain fully charged. No production evaluator prompt, evidence gate, scoring or historical result changed.

Full accounting: usage_cost.json. Independent audit: independent_validation.json. Protocol: METHOD.md. See STATUS.md for terminal process confirmation.
'''
(run.HERE/'REPORT.md').write_text(report)
run.dump(run.HERE/'completion.json',dict(status='complete',completed=time.time(),episodes=400,shots=2000,claims=counts['claims'],entities=counts['entities'],ambiguity_notes=len(amb),model_calls=u['calls'],tokens=u['total_tokens'],standard_api_equivalent_usd=u['standard_api_equivalent_usd'],known_subtotal_usd=u['known_subtotal_usd'],unavailable_cost_records=u['unavailable_or_inflight_costs'],model_interval_seconds=span,independent_audit='pass'))
print(json.dumps(run.read(run.HERE/'completion.json')))
