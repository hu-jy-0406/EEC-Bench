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
- To resolve: an ablation on the current chain (discovery v5 -> review v6 ->
  scoring v5) with and without a compact DINO hint (e.g. one number per entity
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
- To resolve: re-run clustering on frozen detections, matching v2 and the
  branch chain from-registry on #032 and #002 (and a case with recurring
  background objects), compared with the existing v1 results. API calls only;
  needs a low-load node in an existing allocation and owner go-ahead.

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
    field, and entities in no presence list stay as they are.

### Q5. Apply the owner's rulings on four contract boundaries

- Decided by the owner on 2026-11-01; NOT yet applied to any contract. Apply
  later when Claude usage allows, to all 400 contracts (the cleaned 1-200 and
  the 201-400 still to be cleaned), then recompute Table 3's contract rows.
  1. Focus, softness or blur ("soft foreground", "softly focused", "soften
     the left foreground") is a requirement, recorded as camera information
     of that shot (`camera_view`).
  2. "Hold the shot / view / two-shot" is a static-camera requirement,
     recorded in that shot's `camera_movement`.
  3. Lighting stated in one shot goes to the location description or to that
     shot only, inferred from context (a lasting property of the place vs.
     a state of that moment).
  4. A street, snow or similar ground is part of the location, like floors;
     it is not a separate entity.
- Until applied, contracts keep their uneven treatment, and the cleanup
  rules (`EECBench/experiments/contract_cleanup_20261031/rules_cleanup.txt`)
  still say not to touch these four points; update those rules when the
  rulings are applied.

### Q6. V-V: attach changes to checklist items, and test the change judgment

- Current design (owner accepted 2026-11-01): checklist items are the aspects
  to compare, `checklist_audit` mainly proves coverage, and issues come from the
  judged change list. An alternative attaches changes directly to each item
  (item -> changes -> judgment -> issue); it needs schema, gate and prompt
  changes and a live check, and one change can belong to several items.
- No experiment has compared judging changes with asking directly for problems.
  Candidate ablation for RQ4.

### Q7. Verification in two calls (paper states it; pipeline not yet changed)

- Owner decision (2026-11-01): the verifier of each branch makes two model
  calls. The first keeps or splits candidates and corrects their descriptions.
  The second receives only the corrected issues and gives the verdicts. It stays
  one module, the verifier, with two calls for two tasks.
  Reason: in review v6 one output holds both the rewrite and the verdict, so
  nothing shows that the verdict rests on the rewritten text.
- Paper 3.3.3, the Figure 3 placeholder text and the call count in Section 4
  already state this. The implemented chain is still one call per branch, and
  all existing validation used it.
- Duplicates move too (owner, 2026-11-01): finding repeated reports belongs to
  verification, not scoring. The paper merges candidates that report the same
  problem in the same dimension in the first call, next to splitting, before any
  verdict (owner confirmed the timing, 2026-11-01). Scoring then has
  no duplicates: each confirmed issue deducts on its own, with no event groups and
  no maximum. The code still sets `duplicate_of` in scoring v5 (rule: same concrete
  failure of the same requirement over the same span) and needs a merge action
  in review, removal from scoring, and tests.
- To do when the owner starts this: split `prompts/vl_vv_issue_review_v6_{vl,vv}.txt`
  into two prompts with schemas and gates; fix what the second call sees
  (assumed: corrected issues, keyframes, prompt, contract, no original candidate
  text); live A/B against one call on frozen candidates. Verification goes from
  2 to 4 calls per episode (up to 6 calls with images in total). Section 4 results
  must come from the two-call chain.

### Q8. Issue entities take their label from the ledger (paper states it; pipeline not yet changed)

- Owner decision (2026-11-01): each consistency issue only lists its subject
  entities. An entity's specified or unspecified label comes from the entity
  ledger, and the count of issues involving unspecified entities follows from
  it. Issues are not classified, and neither detection nor review checks labels
  against the text.
- Paper 3.3.3 and 3.3.4 and the RQ2 table already state this. The implemented
  chain still has `entity_register` provenance in V-V detection, the provenance
  check in V-V review, and an `uncertain` upper bound in scoring v5.
- To do when the owner starts this: remove provenance from the V-V prompts,
  schemas, gates and config; read the label from the ledger in scoring; drop the
  upper-bound statistics.
- Decided (owner, 2026-11-02): an entity added by detection (`n1...`) counts as
  unspecified. Every contract entity already has a ledger record (`pb...`), also
  without any detected box, so a contract entity never needs an added key. Earlier
  runs: 7 added entities in 70 runs, 5 of 242 confirmed issues; one of them
  (#069 Wan2.1, `n2` stairs) duplicated ledger `pb0003`. Prefer specified
  entities: add this sentence to the V-V detection prompt (V-L unchanged):
  "Every contract entity has a ledger record, even when no box was detected.
  Use a contract entity's ledger ID whenever one fits, then an unspecified
  ledger entity; add a new entity (n1, n2, ...) only when no ledger record fits."
- Known effect: a wrong ledger label is no longer corrected downstream.

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

### Q11. Clearer collection rule in shot clustering (confirmed wording, not yet applied)

- Owner (2026-11-02): clearly visible objects stay separate, but a large number
  of same-kind items gathered together is one node even when every item is
  clearly visible (a basket of oranges). The current prompt also uses
  individual separability as a condition, which is wrong.
- Confirmed wording for the "Individuals and genuine collections" section of
  `skills/wedetect-shot-entities/review_prompt.txt` (replaces the "Use ONE
  collection node only when ..." bullet, including the sentences "Judge the
  visible organization and meaningful individual separability ..." and "A dense
  pile/bundle is different from a few clear individual objects."):
  - Keep clearly visible objects as separate nodes by default. Two cups on a
    table are two entities.
  - Exception: use ONE collection node for a large number of items of the same
    kind gathered together, such as a basket of oranges or a bunch of pens in a
    holder. Merge them even when every item is clearly visible, because the
    condition is the number and kind of the items, not how visible each one is.
    There is no fixed count, but a few items are not a large number. Separate
    groups stay separate: two baskets of oranges are two nodes.
- To be applied by the pipeline-sync session together with Q7 and Q8, then
  checked live with Q2.

### Q12. Several clustered entities may bind to one contract entity (decided, not yet applied)

- Problem: a contract makes a collection one entity unless the prompt describes
  its members separately, also for a few items ("Three glasses": one entity,
  "Collection of three clear glasses"; "Helpers": "A group of several men").
  Shot clustering keeps a few clearly visible items as separate nodes (Q11), and
  shot binding allows at most one local entity per contract entity per shot
  (`gs_shot_prompt_recovery.py` rejects a second binding and normalizes
  duplicates to the entity with most witness frames). The other members became
  unbound and ended up as unspecified entities, although the prompt names them.
  First 200 contracts: about 670 of 2,662 character/object entities have a
  group or plural name (name heuristic, upper bound with false positives).
- Owner decision (2026-11-02): when binding to the contract, several clustered
  entities of one shot may be bound to the same contract entity. The binding
  agent decides from the contract text; clustering and matching rules stay as
  they are. The ledger keeps them under that one specified entity in that shot.
- To be applied by the pipeline-sync session (binding prompt, schema, gates,
  normalization, ledger and everything that assumes one occurrence per shot),
  then checked live with Q2.

## Resolved

(none yet)
