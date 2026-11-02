# Full400 contracts rewritten into the v2 layout (2026-10-30)

All 400 episode contracts now exist in the owner's v2 layout
(`EECBench/docs/episode-contract-v2-format.md`), produced by Claude Code
subagents on Sonnet, independently audited by fresh Sonnet subagents and
validated mechanically. v1 contracts are unchanged; no evaluator stage reads
v2 yet.

## Deliverables (`deliverables/`)

| File | Content |
| --- | --- |
| `episodes/<id>/contract.json` | model-facing contract, no evidence (what the evaluating model will read) |
| `episodes/<id>/contract_with_evidence.json` | same content plus prompt quotes, v1 claim IDs, v1 labels and the prompt |
| `episodes/<id>/claim_accounting.json` | destination of every v1 claim |
| `episodes/<id>/review.md` | readable rendering |
| `contracts_400.jsonl`, `contracts_400_with_evidence.jsonl`, `priority_200.jsonl` | bundles in priority order |
| `index.json` | per-episode entity count, audit verdict, accounting summary |

Sizes: model-facing 8.9 MB in total (v1 contracts: 41.2 MB); with evidence 20.5 MB.

## Method

1. Input per episode: original global and shot prompts plus a compact v1 contract
   (`rewrite.py show`). Transitions come from the source shot maps (all cuts).
2. One Sonnet subagent per batch of 4 episodes (Claude Code workflow,
   `runs/`) read `rules_v2.txt`, wrote conversion decisions per episode, ran
   `rewrite.py check` (schema, exact quotes, every v1 entity disposed, kept
   names unchanged, ID order, no wall/floor/ceiling entity, location shape,
   presence consistent with v1 presence claims, explicit decisions for claims on
   merged entities, every v1 claim accounted for) until PASS, then
   `rewrite.py finalize`.
3. Audit: every episode got one fresh Sonnet subagent pass (4 episodes per
   agent, `runs/audit_workflow.js`), re-reading the prompts against the rules.
   The owner first chose a seeded sample of 40 (`runs/audit_sample.json`), then
   the remaining 360 after 26 of the 40 needed changes. Revised decisions had to
   pass the same check.

## Results (final, after audit)

- 400/400 finalized and audited; every contract re-assembles identically from its
  `final_decisions.json`, and every revised episode's final decisions equal its
  audit decisions.
- Entities: 6,853 (1,378 characters, 769 locations, 4,706 objects); median 16
  per episode. 6,790 continue v1 entities, 30 were split out of descriptions
  (handled worn/held items), 33 are newly named.
- v1 entity dispositions: kept 6,786, merged into a location 434
  (walls/floors/ceilings), folded into an owner 190 (worn/held items without
  action), merged into a collection 15.
- All 64,724 v1 claims accounted for: folded into descriptions 26,623, spatial
  14,536, presence 13,356, motion 6,877, per-shot appearance 2,681, camera view
  533, camera movement 23, cross_shot 81, absent 14; none dropped. New
  requirements: 5.

## Audit of all 400

153 pass, 247 revised (61.75%), 529 issues recorded by the auditors
(`runs/audit_all_summary.json`; 0 issues in 153 episodes, 1 in 91, 2 in 77, 3 in 48,
4+ in 31). All revisions passed check and are in the deliverables. What
actually changed, measured by diffing each episode's rewrite decisions against
its final decisions (`runs/audit_decision_diffs.json`):

| Change | Amount | Episodes |
| --- | --- | --- |
| Entity descriptions edited (missing stated attributes; unstated, shot-specific or contradictory text removed) | 244 entities | 146 |
| Camera fields edited (missing stated camera information, hold instructions, focus; entity positions removed) | 194 shots camera_view, 66 shots camera_movement | 155 |
| Worn-item layering claims moved into descriptions (no longer duplicated as per-shot spatial requirements) | 77 claims | 36 |
| Per-shot appearance kept/removed | 103 claims | 29 |
| Entity set changed | 25 added, 2 removed; 34 shots' presence lists | 20 |
| Claims moved to or from camera fields | 10 claims | 9 |
| Shot location changed | 4 shots | 3 |

Most changes are wording or small attribute corrections. Entity, presence,
duplicate-requirement and per-shot appearance changes alter what the
evaluator checks.

## Usage and cost

| Stage | Producer | Usage |
| --- | --- | --- |
| Pilot round 1 and 2 (3 episodes each, kept in `pilot_history/`) | OpenAI API, GPT-6 Astra/medium | 12 calls, 297,634 tokens (277,363 input incl. 4,480 cached; 20,271 output), USD 3.746860 standard API equivalent at the recorded rates (`pricing.json`), not a bill |
| Opus subagent pilot (stopped by the owner before its first check) | Claude Code | not recorded |
| Sonnet pilot (3 episodes) | Claude Code subagents | 166,097 subagent tokens |
| Full run 1 (100 agents; 27 stopped by the session usage limit) | Claude Code subagents | 15,710,499 subagent tokens |
| Full run 2 (22 agents, remaining 88 episodes) | Claude Code subagents | 4,436,796 subagent tokens |
| Audit, sample of 40 (10 agents) | Claude Code subagents | 2,077,067 subagent tokens |
| Audit, remaining 360, run 1 (90 agents; 44 stopped by the session usage limit, 205 episodes done) | Claude Code subagents | 11,418,465 subagent tokens |
| Audit, remaining 155, run 2 (39 agents) | Claude Code subagents | 8,171,699 subagent tokens |

Claude subagent totals: rewrite 20,313,392, audit 21,667,231, together 41,980,623 tokens. Claude subagent usage is plan usage; the workflow reports only total tokens (no
input/cached/output split) and no verified pricing was applied, so an API cost
equivalent is unavailable.

## Limitations

- Conversion and audit decisions are model judgments checked by mechanical gates,
  not human annotation. Each contract had one audit pass; audit revisions were
  not re-audited.
- The rewrite starts from the v1 claims; requirements v1 missed are only
  recovered where an agent added new entities or requirements (rare: 33 new
  entities, 5 new requirements).
- Judgment boundaries remain fuzzy and were applied inconsistently across
  agents, including auditors. Clearest case: lighting stated in one shot was
  moved into location descriptions by some agents and out of them by others.
  Others: "hold the view" as camera movement, focus/blur as camera information,
  and whether a street or snow counts as a floor.
- The evaluator (V-L template, V-V inputs) still reads v1; adapting it to v2 is
  separate work.
