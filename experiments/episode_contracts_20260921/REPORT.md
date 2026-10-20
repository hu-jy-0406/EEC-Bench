# Full400 episode schedule + claims

Completed 400 episodes / 2000 shots from the current authoritative shared global and per-shot prompts in the priority queue, including user-authorized source corrections.

- Primary files: `deliverables/episodes/<episode_id>/contract.json`.
- Main fields: `entity_descriptions`, `entity_schedule`, `claims`; no duplicate scene_id.
- Totals: 7425 entity records, 64724 claims (presence: 13370 / appearance: 28906 / spatial: 15570 / motion: 6878).
- Evaluator-compatible derivatives: `alignment_contract.json` beside each primary contract. All pass the existing validator; all claims are identical to the primary files.
- Index and browsing: `deliverables/index.json`, `deliverables/review.html`, per-episode `review.md`.
- Queue exports: contracts_400.jsonl, core_100.jsonl, priority_200.jsonl, stage2_additional_100.jsonl, stage3_remaining_200.jsonl. Original IDs and nested subset order preserved.

## Validation

All400 received independent fresh-context text audit after compilation. Audit revised 379 episodes. 9594 source sentence units retain coverage references and explicit unscored fragments. Source/queue hashes, all original prompt strings, quote references, schedule/entity/claim IDs, dependencies, deterministic adapter equivalence, actual review responses and subset contents pass the independent on-disk audit.

Use `source_revision.json` to match the current source version to generation inputs and contracts. The three affected model-specific prompt adaptations require refresh before generation against this version.

The current shared prompts are the semantic source. No source-video observations, images, prior visual detector inventories, generated outputs or Wan-specific additions enter compilation. The Wan adaptations retain additional model-specific text outside these shared original-prompt contracts. No video evaluation was rerun.

63 source-ambiguity notes are preserved in `deliverables/ambiguities.json` and the corresponding contracts, not forced into fabricated certainty. These require case-specific interpretation or unknown handling during evaluation. Schedule omission is not prohibition. Same registered places express intended location recurrence; shared incidental location visibility alone is not proof of a common camera scene.

This is full model-based semantic review plus structural/provenance verification, not a formal proof of natural-language equivalence or independent human annotation. Pure filmmaking/style/audio/timing and independent temporal-order/offscreen-persistence requirements remain explicitly unscored under the existing four-dimensional protocol. Their current source text is retained verbatim.

## Usage and runtime

All attempts including mechanical rejections/recovery: 848 calls; 21,231,651 recorded tokens = 13,241,202 input (including 2,748,160 cached subset) + 7,990,449 output. Known standard API equivalent subtotal USD 507.201030; full amount unavailable because 2 attempts have no complete usable usage record. Reported token totals include recorded usage only. These estimates are not actual bills. Recorded verified 2026-09-20 Astra pricing: USD/M uncached10, cached-read1, output50 within the recorded standard context limit; no cache double counting. Actual billed amount unavailable.

First-to-last model interval 6841.448s, including pilot and recovery; maximum recorded call concurrency 65. This is contract-construction time, not video generation/evaluation runtime. CPU/API only on existing206117/node306 with low-priority bounded CPU affinity and GPUs hidden; no new allocation. Parent conversation and cluster price excluded.

Initial pilot local validator incorrectly rejected a response solely for honest source-ambiguity notes. The local acceptance rule was corrected to retain ambiguity rather than forcing unsupported certainty; original responses and additional attempts remain fully charged. No production evaluator prompt, evidence gate, scoring or historical result changed.

Full accounting: usage_cost.json. Independent audit: independent_validation.json. Protocol: METHOD.md. See STATUS.md for terminal process confirmation.
