# Full400 contract rewrite into the v2 layout (2026-10-29)

Owner request: rewrite all 400 `contract.json` in the v2 layout with the agreed
entity granularity and location rules (`EECBench/docs/episode-contract-v2-format.md`).

Status (2026-10-30): complete. 400/400 finalized, audited (153 pass, 247 revised) and exported to `deliverables/`. See REPORT.md.
Evaluator adaptation not started (owner). Uneven boundary rules listed under Limitations in REPORT.md are deferred: the owner decides later, and they are skipped if time is short.

- Owner switched the producer to Claude Code subagents on Sonnet (no OpenAI API
  for the rewrite) and chose an independent audit of a seeded random sample of 40
  (`runs/audit_sample.json`, `runs/audit_workflow.js`; not yet run).
- Sonnet pilot (3 episodes, one agent): 3/3 passed check on the first run;
  166,097 subagent tokens. Run 1 (100 agents, batches of 4,
  `runs/claude_full_batches.json`): 73 agents completed, 27 stopped by the Claude
  session usage limit; 15,710,499 subagent tokens; 312 episodes finalized in total
  (incl. the 3 pilots). Unfinished drafts of 10 interrupted episodes moved to
  `runs/interrupted_run1/`. Remaining 88 in `runs/claude_full_batches_run2.json`.
- All 312 finalized contracts re-assemble identically from `final_decisions.json`;
  check runs per episode: 1 (285), 2 (25), 3 (2). Claude usage is plan usage; an
  API-equivalent cost was not computed (no verified pricing applied), so it is
  marked unavailable.
- Astra pilots (OpenAI API, kept in `pilot_history/`): see below.

- Pilot round 1 (`pilot_history/round1/`): 3/3 episodes passed all gates on the
  first attempt; camera_view values repeated entity positions that stay spatial,
  and the audit passed all three with ~100 reasoning tokens each. 6 calls,
  148,807 tokens (138,327 input, 0 cached; 10,480 output), USD 1.907270.
- Rules tightened (camera_view = camera information only; single-shot entity
  attributes go to the description; audit told not to approve by default).
- Pilot round 2 (`episodes/` of the 3 pilot episodes): 3/3 passed first
  attempt; camera values now camera-only; audits again all pass with 79-154
  reasoning tokens. 6 calls, 148,827 tokens (139,036 input incl. 4,480 cached;
  9,791 output), USD 1.839590.
- Costs are standard API equivalents at the recorded Astra rates
  (`pricing.json`: USD 10/M uncached input, 1/M cached input, 50/M output), not
  billed amounts. Per episode about USD 0.34 rewrite + 0.27 audit.

## Method

- Input per episode (`episodes/<id>/input.json`): the original global and shot
  prompts and a compact copy of the v1 contract (entities, schedule, claims
  without evidence, unscored text, unresolved notes). Source: v1 deliverables
  of `episode_contracts_20260921`. Transitions come from the source shot maps
  (`exports/storymem_hf_20260922/.../shot_mapping.json`; all 1,600 boundaries
  are cuts).
- Rewrite call (configured Astra/medium, `rules_v2.txt`, schema
  `rewrite.schema.json`): returns conversion decisions only, not the whole
  contract: the entity table with rewritten descriptions, a disposition for
  every v1 entity (kept, merged into a location, folded into an owner, merged
  into a collection), per-shot locations, camera view/movement, presence and
  absent lists, and the exceptions to the default claim mapping.
- Assembly (`rewrite.py assemble`): v1 claims are carried over unchanged
  except as decided: presence claims → presence lists; appearance claims →
  folded into descriptions unless kept per shot; spatial/motion claims → per-shot
  requirements with remapped entity IDs; multi-shot claims → `cross_shot`.
  Mechanical gates: exact quotes, every v1 entity disposed, kept names
  unchanged, character/location/object ID order, no wall/floor/ceiling entity,
  location rule shape, presence consistent with v1 presence claims, explicit
  decisions for claims that touch merged entities, every v1 claim accounted for.
  All errors go back to the model with its previous output (up to 4 attempts).
- Independent audit (fresh context, `audit_v2.txt` + the same rules): checks the
  assembled contract against the prompt and the rules and may return complete
  revised decisions, which pass the same gates (up to 3 attempts).
- Outputs per episode: `contract.json` (model-facing, no evidence),
  `contract_with_evidence.json`, `claim_accounting.json`, `review.md`,
  `final_decisions.json`, all raw calls under `calls/`.

## Additions to the owner's layout (to confirm)

- `cross_shot`: v1 has 91 multi-shot claims (e.g., "Shot4 position matches
  Shot2"); they do not fit one shot and are kept in a top-level list.
- Per-shot `absent`: v1 has 14 explicit "not visible" presence claims.
- `motion` kept per shot (not in the owner's list; no requirement dropped).

## Files

`rewrite.py` (prepare / run / usage / export), `rules_v2.txt`, `audit_v2.txt`,
`base.txt` and `pricing.json` (copied from the v1 construction),
`manifest.json` (input hashes, prompt hashes), `usage_cost.json`, `runs/`.
