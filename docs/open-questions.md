# Open questions and planned ablations

Pending decisions and experiments for the evaluator and benchmark. Add an
entry when a question is deferred; move it to "Resolved" with the decision
and date when it is settled. Paper-writing TODOs stay in
`paper/uec-bench/notes/claims_and_todos.md`.

## Open

### Q1. DINO appearance score as a detection hint (ablation)

- Status (2026-11-01, owner): the current version does not use the DINO
  score; it is no longer in the entity ledger sent to the detection models.
  DINO is still computed and kept in `case/dino/` and
  `case/global_entities/global_entities.json`, so an ablation does not need
  a recomputation.
- Evidence so far: `EECBench/experiments/dino_issue_relation_20261101/REPORT.md`
  (offline, v1 chain, labels are pipeline verdicts). Entities in >=2 shots:
  AUC 0.628; across models for the same contract entity 0.613; within one
  video and category 0.515 (chance). Likely a between-video signal only, and
  partly circular because the v1 prompt pointed the model to DINO.
- To resolve: an ablation on the current chain (discovery v6 -> review v7 ->
  scoring v6 since 2026-11-02; the text first named v5 -> v6 -> v5) with and without a compact DINO hint (e.g. one number per entity
  and shot plus a one-sentence explanation in the detection prompts), same
  cases and repeated runs, comparing confirmed issues and recall against
  reference artifacts. Needs a switch that puts DINO back into the ledger and
  owner approval for the prompt wording.

### Q2. Live checks of the 2026-11-01 frontend changes

- Worn items as part of their wearer (clustering and V-V prompts), matching
  v2 for unspecified entities (including its appearance-plus-relations
  wording) and the simplified ledger are covered by tests only.
  The same holds for the contract-v2 evaluator (Q4) and the V-V inspection
  path with `other` (`EECBench/experiments/vl_vv_inspection_path_20261101/`).
  Also tests only: chain v6 (two verification calls, ledger labels; Q7, Q8), the
  clustering collection rule (Q11) and binding protocol v2 (Q12), all of
  2026-11-02 (`EECBench/experiments/vl_vv_pipeline_sync_20261102/`).
- To resolve: re-run clustering on frozen detections, matching v2 and the
  branch chain from-registry on #032 and #002 (and a case with recurring
  background objects), compared with the existing v1 results. API calls only;
  needs a low-load node in an existing allocation and owner go-ahead.
- Status (2026-11-05): the 40-video test (`EECBench/experiments/vl_vv_pipeline_test40_20261103/`)
  ran these frontend stages live (CPU frontend, 2026-11-03/04; 29 videos reached the ledger) and the
  chain on top of them several times; the comparison with the v1 results named above has not been made.

### Q3. Contract cleanup for priority 201-400

- The first 200 are cleaned (`EECBench/experiments/contract_cleanup_20261031/`).
  The owner wants 201-400 done later with the same process when quota allows.
  Table 3's 400-episode contract rows must be recomputed afterwards.

### Q4. Evaluator adaptation to contract v2 (required)

- Owner rule (2026-11-01): the paper text and the pipeline must both match
  the expected pipeline, and contract v2 is the expected contract.
- Done (2026-11-01): the VL/VV evaluator reads v2 by default
  (`EECBench/scripts/episode_contract.py`; case `contract.json` plus
  `prompt.json`), every shot boundary is a cut, the default chain has no
  `continue`, `shot_transitions` input or shot-map lookup, and
  `transition_from_previous` is gone from all deliverables and tools. The
  contract is the only V-L checking basis: the shot-text row is gone, the
  template has entity, relation, camera, style, transition and cross-shot rows,
  and quotes come from contract text. `shot_description.style` is in all
  contracts (54 episodes state a style), and 42 between-shot camera
  requirements moved to `cross_shot`. v1 stays readable with
  `--allow-v1-contract`; older chains refuse v2. Report:
  `EECBench/experiments/vl_vv_contract_v2_adapt_20261101/REPORT.md`.
- Remaining: a live run on the changed prompts, with Q2.
- Owner decisions on section 6 of that report (2026-11-01):
  - Unrequested prominent entities that V-L can no longer report: accepted.
  - Prompt requirements outside the contract stay unchecked: accepted.
  - `coordinate_frame` is now defined in both V-L prompts
    (`experiments/vl_vv_coordinate_frame_20261101/`).
  - Camera values that need several shots, reverse views above all, moved to
    `cross_shot`: 35 more moves, section 4 of the report. Table 3 cross-shot /
    absence is now 92 / 8 (400 episodes: 158 / 14).
  - Strip `unresolved` before sending when contracts 201-400 are used.
  - Prompts that forbid an entity stay in the per-shot `absent` list; no new
    field, and entities in no presence list stay as they are (they get ledger
    records since Q16).

### Q6. V-V: attach changes to checklist items, and test the change judgment

- Current design (owner accepted 2026-11-01): checklist items are the aspects
  to compare, `checklist_audit` mainly proves coverage, and issues come from the
  judged change list. An alternative attaches changes directly to each item
  (item -> changes -> judgment -> issue); it needs schema, gate and prompt
  changes and a live check, and one change can belong to several items.
- No experiment has compared judging changes with asking directly for problems.
  Candidate ablation for RQ4.

### Q9. Comparison of agent models (planned experiment)

- Owner request (2026-11-01): compare the models that run the agents: GPT-6 Luna,
  GPT-6 Sol and Gemini 3.8 Flash. Goes into paper Section 4, RQ4.
- The VL/VV chain calls the OpenAI API through `scripts/eec_api_codex_shim.py`
  (default `gpt-6-luna`). The only Gemini transport is `scripts/gs_gemini_backend.py`
  in the GS pipeline, with `gemini-3.5-flash`. Running Gemini 3.8 Flash needs a
  transport for this chain, including structured output and the repair loop.
- Paper 4.5 gives them their own table, separate from the pipeline ablations.
  Assistant's default, not confirmed by the owner: change detection, verification
  and scoring, and keep the same entity ledger. Availability and prices of Sol
  and Gemini 3.8 Flash have not been checked.

### Q10. Evaluator validation without complete annotation (planned experiment)

- Owner (2026-11-01): full human annotation of every problem is too expensive, so
  the precision/recall/F1 ablation table was dropped. Pipeline ablations and the
  comparison of agent models are separate tables, and tables carry no USD column.
  Evidence on what similar work reports:
  `paper/uec-bench/notes/evaluator_validation_survey_20261101.md`.
- Paper 4.5: each pipeline ablation and each agent model is measured by Spearman
  correlation with the human ratings of RQ3 on the same videos, as VideoArgus does
  for its ablations. A sampled audit (confirmed issues, rejected issues, cross-shot
  links) gives precision of confirmed issues, kappa and link accuracy. Designed by
  the assistant and not run; sample sizes are open.
- Considered and dropped the same day: issues confirmed on real source clips as a
  false-alarm bound, and defects injected into keyframes as recall. Neither has a
  precedent in multi-shot evaluation, and injection has no agreed method.

### Q19. Batch cost summaries omit the matching-v2 call (deferred)

- `experiments/vl_vv_multimodel_first200_20260926/run_batch.py` adds frontend usage from
  `entities/run.json`, `shot_prompt_recovery/calls/*/status.json` and `global_match/attempts`
  (matching v1), but not matching v2, whose usage is in `global_match_v2/audit.json`. Batch token
  and cost totals of new runs are therefore too low by the matching call. Found 2026-11-02.
- Owner (2026-11-03): do not fix for now. Fix before batch cost totals are reported.

### Q21. V-L aggregation: score by the share of failed requirements (deferred by the owner)

- Problem (2026-11-05): scoring v6 multiplies (1 - D/100) per issue, so V-L saturates near 0 once an episode has
  about 15 issues (29-video retest: 14 of 29 below 10, median 11; CineTrans mean 0.1), and longer episodes score
  lower (Spearman with requirement count -0.33).
- Owner direction (2026-11-06): score by issue proportion so scores fall in a reasonable range; choice deferred.
  Candidates computed offline (no model calls; `EECBench/experiments/vl_scoring_proportion_20261106/`):
  requirement-group pass rate (median 86, CineTrans 51.5 ... Wan2.2 90.4), requirement pass rate (median 94,
  TIFA/DSG style, keeps the absence rule per requirement), group pass rate weighted by severity (median 93).
  V-V unchanged. The scoring agent (one severity per issue) needs no change; with a pass-rate V-L score the V-L
  severity call becomes optional. Stored verdicts and severities allow rescoring offline after the full run.

## Resolved

### Q22. V-V shot-boundary path — removed 2026-11-09

- Resolved by the owner's redesign of V-V detection the same day: no inspection paths; the agent checks one checklist item per call (X4 and X9 stay checklist items). `experiments/vl_vv_checklist_traversal_20261109/REPORT.md`.

- Finding (2026-11-09, full first-200 run, 587 finished episodes, 2,355 boundaries; local result files only,
  no model calls): the boundary path (X4, X9; `boundary_checks`) is enforced only as "one entry per boundary,
  linking at least one change that compares the two shots". The cut itself (camera_position,
  required_transition, judged normal) always satisfies it: 1,940 such changes, 86% of boundaries link one
  change. Of 349 cross-shot candidate issues linked to a boundary, 336 are also linked from the continuity
  ledger; only 13 are boundary-only (11 confirmed, mostly found by O1, X4 cited twice, X9 never). No
  `spatial_continuity` issue in the whole run; `state_action_continuity` 20 (14 confirmed). Linking is the
  model's bookkeeping inside one call, so this is not an ablation.
- Owner (2026-11-09): consider deleting the path later; not now.

### Q23. V-V per-entity checks — superseded 2026-11-09

- The required continuity subjects (every recurring ledger entity, applied that morning) and the shot scan were removed with the inspection paths; each checklist item now covers the entities it concerns. Whether unspecified entities are measurable remains an empirical question (10 videos: 0-3 confirmed issues with an unspecified subject per run).

- Finding (2026-11-09, same run, local files only): the gates of V-V detection force per-entity records only for
  contract characters (shot scan, `required_shot_characters`) and contract characters and locations scheduled in
  two or more shots (continuity ledger, `required_continuity_subjects`). Objects and ledger unspecified entities
  (`ge...`) are optional ("every recurring object you compared"; shot-scan free text `other`). Multi-shot entities
  in the continuity ledger: characters 99%, locations 100%, contract objects 28%, `ge...` 2.1% (4 of 187).
  Within-shot changes per entity-shot occurrence: characters 20.9%, locations 2.7%, objects 0.9%, `ge...` 0.1%.
  `ge...` entities have 0 confirmed V-V issues; the 72 detection-added `n...` entities exist only because an issue
  named them. So the unspecified-entity statistics (Table 5) are not measurable with the current gates.
- Origin: an assistant implementation choice in checklist v2 (2026-10-04), not an owner requirement; the
  2026-10-20 design doc reported the gap, but its fix was dropped together with the per-issue B/U proposal; the
  2026-11-01 inspection path ("each recurring subject across shots") changed only the prompt wording.
- Discussed fix (not decided): required list = every ledger entity whose scheduled shots plus detected shots
  number two or more (about 8.8 subjects and 28.8 observations per episode instead of 3.6 and 14.0; roughly
  +830 output tokens per V-V detection); path 1 (per-entity shot-scan rows) separately. Open choices: shot scope
  (scheduled, detected or both), groups, path 1, in place or new version.
- Owner (2026-11-09): finish the current full run first; think about this slowly.
- Applied 2026-11-09 for path 2 (owner: "按照我之前说的修一下V-V检测，然后用一些测例作测试"): continuity list =
  every ledger entity scheduled or detected in two or more shots (`recurring_ledger_subjects`, chain v6, in place;
  `docs/vl-vv-branch-pipeline-v2.md` section 3). A/B on 40 videos (`experiments/vl_vv_unspecified_coverage_20261109/`):
  `ge...` subjects in the continuity ledger 0 -> 12 (all consistent or uncertain); confirmed V-V issues 51 -> 61;
  with an unspecified subject 1 -> 2 (both added `n...`, no `ge...`), not a measurable increase; contract-object
  issues 6 -> 16. Owner (2026-11-09): run the full set with this version anyway
  (`experiments/vl_vv_full_first200_v2_20261109/`).
- Path 1 tested 2026-11-09 (owner: "先停掉，增加路径1逐实体检查，然后抽一些案例测试…"; the second full run was drained):
  one shot-scan row per ledger entity scheduled or detected in the shot, in a staging copy, NOT applied. Same 40
  videos (`experiments/vl_vv_shot_entity_scan_20261109/REPORT.md`): all 110 `ge...` occurrences got a row, none
  unstable; confirmed V-V issues with an unspecified subject 2 (path 2) -> 2, both added `n...`, `ge...` still 0;
  rows are terse (median 4-6 characters); within-shot observed changes 98 -> 47. Unspecified issues so far come only
  from entities the detector missed. Decision on path 1 and on the full run pending.

### Q20. Requirement list compiled once per contract — implemented 2026-11-05

- Owner (2026-11-05): derive the requirement list once, decide how contract and requirements are organized and
  which stage reads which fields, then "implement it, using sonnet agent". Design
  `EECBench/docs/contract-and-requirements-design.md`: prompt.json, contract.json (authored, v2) and a compiled
  requirements.json (with prompt_registry.json and narrative.json), recorded with the contract hash; model inputs
  unchanged. Implemented by a Sonnet subagent and reviewed: 400 packages, equivalence on 603 contracts, byte-identical
  V-L payloads on the 29 frozen cases, 308 tests pass. New batch cases copy the package (missing or stale = error);
  older cases derive at run (`requirements_source: derived_at_run`). Recompile with
  `compile_episode_requirements.py --update` whenever a contract changes. Report
  `EECBench/experiments/compiled_requirements_20261105/REPORT.md`.

### Q5. Owner's rulings on four contract boundaries — applied to priority 1-200 on 2026-11-05

- Rulings (owner, 2026-11-01): focus/softness/blur is camera information (`camera_view`); "hold the shot /
  view / two-shot" is a static camera (`camera_movement`); lighting stated in one shot goes to the location
  description or to that shot by context; a street, snow or similar ground is part of the location.
- Applied 2026-11-05 (owner go-ahead) to the cleaned first 200 with Sonnet agents, independent review and
  main-session rulings on 77 disputed items; exported to `contract_cleanup_20261031/deliverables/`. Table 3
  contract rows recomputed (entities 2,935, appearance 1,550, presence 6,245, spatial 7,422); the paper
  table is not edited yet. Priority 201-400 get the rulings in their cleanup (Q3; `rules_cleanup.txt`
  updated). Report `EECBench/experiments/contract_cleanup_20261031/q5_20261105/REPORT.md`.

### Q7. Verification in two calls — implemented 2026-11-02 (tests only, no live run)

- Owner decision (2026-11-01): the verifier of each branch makes two calls; the
  first keeps or splits candidates, merges candidates that report the same problem
  in the same dimension, and corrects their descriptions; the second receives only
  the corrected issues and gives the verdicts. Scoring has no duplicates, event
  groups or maximum.
- Implemented as chain v6, the new default: review v7 (`prompts/vl_vv_issue_review_v7_{vl,vv}_{rewrite,verdict}.txt`,
  runner-assigned issue IDs traced to their source candidates) and scoring v6
  (each confirmed issue deducts on its own). Chain v5 (one call, scoring v5) stays
  selectable with `--discovery-protocol v5`. Spec `EECBench/docs/vl-vv-branch-pipeline-v2.md`;
  report `EECBench/experiments/vl_vv_pipeline_sync_20261102/REPORT.md`.
- Not done: a live A/B against one call (owner: not now); the one-call ablation was dropped (Q14).
- Amended 2026-11-05 (owner): with the answers V-L detection format, now the default, V-L candidates skip the
  first call and go straight to the verdict call (each states one failed requirement; repeats are merged by rule
  in detection). V-V and checks-format V-L keep both calls.
  `EECBench/experiments/vl_vv_direct_vl_verdict_20261105/REPORT.md`.
- Amended 2026-11-05 (owner): every verdict call's schema has one required entry per issue ID (built per call),
  so a verdict cannot be skipped; prompts and gates unchanged.
  `EECBench/experiments/vl_vv_pipeline_retest_20261105/REPORT.md`.

### Q8. Issue entities take their label from the ledger — implemented 2026-11-02 (tests only, no live run)

- Owner decisions (2026-11-01, 2026-11-02): issues only list subject entities; the
  ledger gives the label (`pb...` specified; `ge...` and detection-added `n...`
  unspecified); the V-V detection prompt gets the sentence "Every contract entity
  has a ledger record, even when no box was detected. Use a contract entity's ledger
  ID whenever one fits, then an unspecified ledger entity; add a new entity (n1, n2,
  ...) only when no ledger record fits."
- Implemented in chain v6: discovery v6 (V-V without `entity_register`, added
  entities in `added_entities`, the sentence added), review v7 without the
  provenance check, scoring v6 with `consistency_issue_statistics` per scope (count
  and share of confirmed consistency issues with an unspecified subject entity) and
  no unintentional / remainder / upper-bound outputs. Known effect: a wrong ledger
  label is no longer corrected downstream. See Q16.

### Q11. Clearer collection rule in shot clustering — applied 2026-11-02 (tests only, no live run)

- The owner's confirmed wording replaced the "Use ONE collection node only when ..."
  bullet of `skills/wedetect-shot-entities/review_prompt.txt` in place (before-copy
  and SHA-256 in the pipeline-sync report). Live check still pending with Q2.

### Q12. Several clustered entities may bind to one contract entity — applied 2026-11-02 (tests only, no live run)

- Binding protocol v2 (`prompts/gs_shot_prompt_binding_v2.txt`, VL/VV default;
  `--binding-protocol v1` and the GS pipeline keep v1): several local entities of
  one shot may bind to the same contract entity when its text describes several
  items or members; no duplicate normalization; coverage over all bound members; a
  recovered box of such an entity becomes a new local entity bound to it; the ledger
  keeps all of them under the one specified entity; DINO appearance IDs stay unique.
  Matching rules changed later the same day (Q13). Live check still pending with Q2.

### Q13. Matching: missed members of a contract entity with several members — applied 2026-11-02 (tests only, no live run)

- Problem: since Q12 a contract entity that states several items or members
  ("Three glasses") can hold several bound local entities in one shot, but matching
  v2 still allowed one occurrence per shot. A member that binding missed in a shot
  where other members were bound could only become an unspecified entity.
- Owner decision (2026-11-02): relax the rule. Matching v2 changed in place (no live
  run had used it): such a specified entity may receive missed members also from a
  shot where other members are already bound, each member keeping its own original
  boxes (no union box); every other specified entity and every unspecified entity
  keeps at most one occurrence per shot. As in binding v2, the agent judges from the
  contract text whether an entity states several members, and the gate no longer
  counts specified occurrences. Report
  `experiments/vl_vv_matching_group_members_20261102/REPORT.md`.

### Q14. A pure one-call verification ablation — dropped 2026-11-02

- Chain v5 differs from v6 in three points (entity provenance in V-V detection,
  duplicate links in scoring v5, one verification call), so it is not a pure
  "one verification call" ablation, and no v6 one-call variant was built.
- Owner decision (2026-11-02): the ablation is not essential; the "One verification
  call" row and its sentence were removed from paper 4.5 / Table 7. Chain v5 stays
  only as a historical rollback; nothing is built for this ablation.

### Q15. Grounding DINO recovery: score selection — decided 2026-11-03 (paper updated 2026-11-05)

- Paper 3.3.1 said "an agent that sees only this shot assigns each proposed box to
  the missing entity or rejects it"; the code (`gs_shot_prompt_recovery.py`, protocol
  `shot_prompt_recovery_v2_direct_grounding`) attaches the highest-score Grounding
  DINO box for each missing entity and frame without an agent.
- Known risks of the score rule: the top box of a category query may sit on another
  object (2026-09-05 query ablation: no top-1 query reliably found the target), can
  mark an entity the video never generated as observed, and is not checked against
  existing boxes. The agent review (2026-09-22 design; old prompt
  `prompts/gs_shot_prompt_recovery_review_v1.txt`, old code in
  `experiments/parking_prompt_recovery_20260922/source_snapshot/`) would add at most
  one own-shot call per shot with candidates for a missing entity.
- Owner decision (2026-11-02): defer and compare in the experiments. Owner decision
  (2026-11-03): use score selection for now. The code is unchanged; the paper
  sentence changes to the score rule (wording proposed to the owner). The 9 stale
  tests of the old agent-review interface in `tests/test_shot_prompt_recovery.py`
  were replaced by tests of score selection (11 tests, all pass). Report
  `experiments/vl_vv_recovery_score_selection_20261103/REPORT.md`.
- Paper 3.3.1 changed to the score rule on 2026-11-05 (owner approved the wording).

### Q16. Contract entities in no presence list get a ledger record — applied 2026-11-02 (tests only, no live run)

- The registry, hence the ledger, held only contract entities listed in some shot's
  presence: 5 of 2,945 entities in the cleaned first 200 contracts (13 of 6,853 in
  the 400 uncleaned v2 contracts), mostly entities that must not appear. An issue
  about one would have got an added `n...` key and counted as unspecified.
- Owner decision (2026-11-02): they are contract entities, so the ledger contains
  all contract entities, including those required not to appear.
  `episode_contract.prompt_registry` now includes every contract entity; one in no
  presence list is `not_required` in every shot (no Grounding DINO search), with the
  episode-level narrative fact `contract_entities_in_no_presence` as its evidence.
  Report `experiments/vl_vv_ledger_all_contract_entities_20261102/REPORT.md`.

### Q17. Uncertain issues deduct at a reduced factor — applied 2026-11-03 (tests only, no live run)

- Owner (2026-11-03): rejected and uncertain issues both deducting nothing made their
  distinction pointless for the score; an uncertain verdict may itself reflect a weakness
  (content too unclear to verify). Options shown: keep (A), a reduced factor (B), or
  separate causes of uncertainty (C). Owner chose B with factor 0.25.
- Scoring v6 changed in place (no live run had used it): the severity calls receive only
  confirmed and uncertain units, an uncertain unit is rated as if the problem were real and
  deducts w(severity) × 0.25; rejected units are not sent and deduct nothing. The rejected /
  uncertain distinction also stays for the audit and robustness experiments. Paper 3.3.4
  wording applied on 2026-11-05 (owner approved), with the matching sentences in 3.3 and the limitations.
  Report `experiments/vl_vv_uncertain_deduction_20261103/REPORT.md`.

### Q18. Verifier calls see only the entities their issues name — applied 2026-11-03 (tests only, no live run)

- Both review-v7 calls received the whole entity ledger (an assistant choice of 2026-11-02, not
  confirmed by the owner). Call 1 may only use entity keys of its source candidates, chain v5's
  review received only the candidates' entities, and paper 3.3.3 names the prompt, the contract
  and the keyframes as the verifier's inputs.
- Owner (2026-11-03): each call receives only the records of the entities its issues name: call 1
  those of the candidates, call 2 those of the rewritten issues (full ledger records with boxes,
  plus the named entities added by detection). The four review-v7 prompts state this in their
  input line. Report `experiments/vl_vv_verifier_issue_entities_20261103/REPORT.md`.
