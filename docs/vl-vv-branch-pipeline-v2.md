# Branch-separated V-L / V-V pipeline, chain v6 (discovery v6 → review v7 → scoring v6)

Status: implemented 2026-11-02 at the owner's direction (open-questions Q7, Q8;
frontend Q11, Q12); default chain of `scripts/run_vl_vv_pipeline.py`
(`--discovery-protocol v6`) and of a new batch directory
(`run_batch.py --discovery-protocol v6`). Tests and dry runs only: no live run
has used these prompts yet. Report:
`experiments/vl_vv_pipeline_sync_20261102/REPORT.md`.

The previous branch chain v5 (discovery v5 → review v6 → scoring v5,
`docs/vl-vv-branch-pipeline-v1.md`) stays selectable with
`--discovery-protocol v5` and is unchanged: its prompts, schemas, config v1
and records v1 are byte-identical, and its stage code paths are the same.
Everything that `vl-vv-branch-pipeline-v1.md` says about the stages, the
shared definitions, the contract-checking template, the V-V checklist and
inspection path, the validation-repair loop and image labels also holds for
chain v6, except for the points below.

## 1. What changed and why

| Point | Chain v5 | Chain v6 | Owner decision |
| --- | --- | --- | --- |
| Verification | one review v6 call per branch: keep/split, rewrite and verdict in one output | two calls per branch: call 1 keeps, splits or **merges** the candidates and rewrites them (no verdicts); call 2 sees only the rewritten issues and gives the verdicts. V-L candidates of the answers formats (default since 2026-11-05) skip call 1 and go straight to the verdict call | Q7 (2026-11-01); owner 2026-11-05 |
| Duplicates | scoring v5 links duplicates (`duplicate_of`), an event group deducts its maximum | merged in verification call 1; scoring has no duplicate links, groups or maximum; each confirmed issue deducts on its own | Q7 (2026-11-01) |
| Uncertain issues | deduct nothing; every unit is sent to the severity call (`none` for rejected and uncertain) | deduct w(severity) × 0.25, rated as if real; rejected units are not sent and deduct nothing | owner, 2026-11-03 |
| Dimension score | 100 × Π (1 − D/100) over events | 100 × exp(−ΣD / (100 S)), S = number of shots (per-shot rule; the product until 2026-11-09) | owner, 2026-11-09 |
| Issue entities | V-V detection registers provenance (`entity_register`), the V-V reviewer verifies it, scoring reports an unintentional subset, a remainder and an `uncertain` upper bound | V-V issues only list subject and context entities; a subject's specified / unspecified label comes from the entity ledger; scoring counts confirmed consistency issues with an unspecified subject entity | Q8 (2026-11-01, 2026-11-02) |

The paper (Section 3.3.3 and 3.3.4) describes chain v6.

## 2. Files

| Call | Prompt | Output schema |
| --- | --- | --- |
| V-L detection | `prompts/vl_vv_issue_discovery_v6_vl.txt` (v5 V-L plus the absent-item rule of 2026-11-02) | `schemas/vl-vv-issue-discovery-v6-vl.schema.json` |
| V-V detection, one call per checklist item (default since 2026-11-09) | `prompts/vl_vv_issue_discovery_v6_vv_item.txt` (+ the item in a trailing message) | `schemas/vl-vv-issue-discovery-v6-vv-item.schema.json` |
| V-V detection, one call for the whole checklist (`--vv-mode one_call`) | `prompts/vl_vv_issue_discovery_v6_vv.txt` | `schemas/vl-vv-issue-discovery-v6-vv.schema.json` |
| V-L verification, call 1 | `prompts/vl_vv_issue_review_v7_vl_rewrite.txt` | `schemas/vl-vv-issue-review-v7-vl-rewrite.schema.json` |
| V-L verification, call 2 | `prompts/vl_vv_issue_review_v7_vl_verdict.txt` | `schemas/vl-vv-issue-review-v7-vl-verdict.schema.json` |
| V-L verification, verdict only (answers formats, default) | `prompts/vl_vv_issue_review_v7_vl_verdict_direct.txt` (the call-2 prompt with only the call-1 wording changed) | `schemas/vl-vv-issue-review-v7-vl-verdict.schema.json` |
| V-V verification, call 1 | `prompts/vl_vv_issue_review_v7_vv_rewrite.txt` | `schemas/vl-vv-issue-review-v7-vv-rewrite.schema.json` |
| V-V verification, call 2 | `prompts/vl_vv_issue_review_v7_vv_verdict.txt` | `schemas/vl-vv-issue-review-v7-vv-verdict.schema.json` |
| V-L severities | `prompts/vl_vv_episode_scoring_v6_vl.txt` | `schemas/vl-vv-episode-scoring-v6-vl.schema.json` |
| V-V severities | `prompts/vl_vv_episode_scoring_v6_vv.txt` | `schemas/vl-vv-episode-scoring-v6-vv.schema.json` |
| Repair turns | `prompts/vl_vv_validation_repair_v2.txt` (shared, unchanged) | the call's schema |

Config: `configs/vl-vv-branch-v2.json` = config v1 without `provenance`, plus
`rewrite.actions` (keep / split / merge) and the scoring issue rule and
ledger-label rule. Canonical records: `schemas/vl-vv-branch-records-v2.schema.json`
(entities carry `label` instead of provenance fields; units trace their
`source_candidate_ids`). Shared definitions: `prompts/vl_vv_branch_definitions_v1.txt`
(unchanged). All schemas come from `scripts/build_vl_vv_branch_schemas.py`
(both chains; a test fails if a committed schema drifts).

Code: the same stage runners serve both chains through `--chain v5|v6`
(default v6): `run_vl_vv_branch_detection.py`, `run_vl_vv_branch_review.py`
(`run_v6` for chain v5, `run_v7` for chain v6), `run_vl_vv_branch_scoring.py`
(`run_v5`, `run_v6`); chain specs in `vl_vv_branch_common.CHAINS`.

## 3. Discovery v6

V-L: unchanged (same gates, same template; same prompt text except one rule added on 2026-11-02 at the owner's direction: an absent item is satisfied when no frame shows the entity and violated when any frame shows it, never not_verifiable for that reason; `experiments/vl_vv_absent_item_rule_20261102/REPORT.md`). Changed on 2026-11-05 at the owner's direction (all chain v6 V-L formats; chain v5 unchanged): an absence no longer counts once. When a presence item is violated, every other requirement of the shot that needs the entity to be seen (appearance, position, relation, action) is violated too and reported on its own; one that holds without the entity is satisfied; the entity description applies only where the entity appears and is not reported. The gate now rejects a listed description (checks) or, in the answers formats, a not_verifiable dependent or a violated description; `experiments/vl_vv_absence_counts_each_20261105/REPORT.md`.

V-L issue links by requirement ID (owner, 2026-11-04; changed in place): every template item has a requirement ID that is unique in the template (the contract's own IDs; `S<n>-des-<entity>`, `S<n>-cam-view`, `S<n>-cam-move`, `S<n>-sty` and `S<n>-cut` for the description, camera, style and cut items of the n-th shot). Each issue occurrence names the requirement IDs it reports (`requirement_ids`); the check rows no longer list `issue_ids`, and the runner derives the requirement-to-issue mapping. Gates on the derived mapping: a reported requirement must be in its row's `violated_items` and belong to the occurrence's shot; every violated requirement is reported by at least one issue; a requirement is reported by exactly one issue except an entity description or a camera item (config `multi_issue_item_kinds`), whose independent attribute failures are separate issues; a cut requirement is `shot_structure`. Before, rows and issues were linked both ways and about 90% of the V-L detection repair errors in the 40-video test were disagreements between the two copies (`experiments/vl_vv_pipeline_test40_20261103/README.md`). Records keep `occurrences[].row_ids` (derived) and add `v_l_detail.requirement_ids`, so review v7 receives the same candidate fields. Chain v5 (config v1) is unchanged. Report: `experiments/vl_vv_requirement_issue_links_20261104/REPORT.md`.

Requirement list (2026-11-05): compiled once per contract (`scripts/compile_episode_requirements.py`, package `experiments/compiled_requirements_20261105/compiled/<episode>/`, copied into each case as `requirements.json`); V-L detection loads it (`episode_requirements.load_for_case`, ledger IDs joined at run time) and records `requirements_source`; a case without it derives the same list at run. Model inputs are unchanged.

V-L detection format "answers" (owner direction, 2026-11-04; **default V-L format of chain v6 since 2026-11-05**, owner: `run_vl_vv_branch_detection.py`, `run_vl_vv_pipeline.py` and new batch directories use it unless `--vl-format checks` or `answers_no_contract` is given; batch directories record `vl_format`, and a chain v6 directory created before keeps checks; v2 contracts only): the agent answers every requirement of the template, one answer per requirement ID, in a schema built for the call (every ID required). An answer has `observed`, `verdict` (satisfied / violated / not_verifiable; not_applicable for a description) and, when violated, its problem (`shown`, `frame_refs`, `subcategory`, `confidence`; descriptions and camera items a list of problems, one per failed attribute, with literal `violated_words`). The runner makes one candidate per problem (statement `要求“<words>”，画面：<shown>`; the same failed description attribute in several shots becomes one candidate), so no issue-requirement mapping is written by the model; candidate records are unchanged for review v7, which accepts the protocol `vl_vv_issue_discovery_v6_vl_answers`. Code `scripts/vl_vv_requirement_answers.py`, prompt `prompts/vl_vv_issue_discovery_v6_vl_answers.txt`. Debug runs on 9 videos: `experiments/vl_vv_requirement_answers_20261104/REPORT.md`. Format `answers_no_contract` (owner direction, 2026-11-04; opt-in with `--vl-format answers_no_contract`, same scope) is the same call without `INPUT.contract_json`: the requirement list and entity table carry everything that is checked; prompt `prompts/vl_vv_issue_discovery_v6_vl_answers_no_contract.txt` (protocol of the same name, accepted by review v7) differs only by the removed input and three wording adaptations that pointed at the contract. The reviewer still receives the contract.

V-V (changed in place on 2026-11-09 at the owner's direction; applied 15:31 Dubai; the path-based description
that stood here, with its continuity-subject change of the same morning, is in git history and
`experiments/vl_vv_unspecified_coverage_20261109/REPORT.md`):

- No inspection paths. The agent goes through the checklist (W1-W7, X1-X9, O1) one item at a time: for each item it
  finds the entities the item concerns in the entity ledger and keyframes, compares them as the item says, and
  reports every change no normal cause explains as an issue under that item, with every entity involved (subject /
  context). Output per item: `item`, `status` (checked / not_applicable), `note`, `issues`. Removed: shot scan,
  continuity ledger, boundary checks, observed changes, checklist audit and the inputs
  `required_continuity_subjects` / `required_shot_characters` (open-questions Q22 and Q23 resolved by removal).
- Mode `per_item` (default): one call per item. Every call of a video sends the same prompt, input, schema and
  keyframes and names its item in a trailing user message (O1 also lists the other items as context). W1 runs
  alone, then up to 8 calls in parallel (`--vv-item-workers`). The runner renumbers the issues (V1... in checklist
  order) and added entities (n1...), checks the assembled checklist with the one-call gate and records
  `vv_detection_mode`, `item_calls` and `prompt_cache_key`; repeats across items go to the verifier's merge. Mode
  `one_call`: the whole checklist in one call, with `earlier_issue_ids` instead of repeated reports.
- Prompt caching: GPT-6 Luna caches an exact repeat of a request and an identical leading developer message, not a
  shared part of a user message followed by a different message, not keyframes and not previous_response_id
  continuations; a developer message cannot hold images (diagnostics in
  `experiments/vl_vv_checklist_traversal_20261109/diag_cache/`). Item calls therefore send the prompt text and INPUT
  as a developer message, the labelled keyframes as the user message and the item last (shim `--prompt-role
  developer`, `--trailing-text-file`, `--prompt-cache-key`); about half of the detection input is cached.
- Gates per issue as before: scope follows the item (W within_shot, X cross_shot, O1 either), known shots, frames
  and entity keys, a subject unless the subcategory may have none, evidence from both sides of a cross-shot issue,
  `other` only under O1.
- Walls, floors, ceilings and the ground are part of their place (owner, 2026-11-09, in place): a change to them
  is reported with the place's ledger ID, which may be the only subject of a setting/background issue; they are
  never added as entities (`experiments/vl_vv_walls_part_of_place_20261109/REPORT.md`).
- `added_entities` and the ledger label rule are unchanged: entities the detector missed get `n1`, `n2`, ... with
  name, description and frame_refs; canonical entities (records v2) carry `label` (`pb...` specified; `ge...` and
  added `n...` unspecified). The worn-items rule and the owner's ledger sentence stay in the prompt.
- 10-video comparison and costs: `experiments/vl_vv_checklist_traversal_20261109/REPORT.md`.

## 4. Review v7: one verifier per branch, two calls

```
candidates ──► call 1 (rewrite) ──► rewritten issues (runner-assigned IDs) ──► call 2 (verdict) ──► units
answers-format V-L candidates ──► direct issues (same IDs, unchanged) ──► verdict call ──► units
```

**V-L without call 1 (owner, 2026-11-05).** When the V-L detection result has an
answers protocol (`answers`, the default, or `answers_no_contract`), the review
makes only the verdict call: each candidate already states one failed
requirement and repeats were merged by rule in detection, so the runner turns
every candidate into one issue unchanged (`direct_issues`: same ID, description,
shots, its one requirement quote, template rows, the frames of its occurrences,
its entities; `rewrite_actions` empty, `revision` unchanged), checks it with the
call-1 structural gates (a failure is a runner error, not a repair round) and
saves `direct_issues.json`. The verdict call uses
`prompts/vl_vv_issue_review_v7_vl_verdict_direct.txt` (same schema and
protocol; it says the issues are the detection agent's candidates). The result
and `run.json` record `review_calls: ["verdict"]`; `model_output.rewrite` is
null. Checks-format V-L and all V-V keep both calls. Basis: in the answers-format
debug runs call 1 split 2 of about 2,100 V-L candidates and left 92% of the
descriptions as rewordings, while costing 55% of the V-L review
(`experiments/vl_vv_direct_vl_verdict_20261105/REPORT.md`).
The one call-1 gate that the composition of answers-format candidates does not
already guarantee, that a subcategory concerning an entity needs one, runs in
answers-format detection instead (2026-11-05, found by the 29-video retest): a
problem of a requirement that names no ledger entity (camera, style, entity-free
rows) must take an entity-optional subcategory, and the detection repair loop
sends it back by requirement ID
(`experiments/vl_vv_pipeline_retest_20261105/REPORT.md`).

Both calls receive the keyframes (labelled), the original prompt (context), the
model-facing contract, the shot sources and the shared definitions, plus the
entity records of only the entities their issues name (owner, 2026-11-03,
`experiments/vl_vv_verifier_issue_entities_20261103/`): `detector_ledger` keeps
the ledger's two lists with each named entity's full record (name, description,
per-shot occurrences and boxes), and `added_entities` the named `n...` entities.
Call 1 uses the entities of the candidates, call 2 those of the rewritten issues
(call 1 may only use entity keys of its sources). Each call has its own repair
loop (`call_rewrite*`, `call_verdict*` folders); the stage's `run.json` counts
both. No candidates: no call.

**Call 1 (rewrite).** One `candidate_actions` entry per candidate: `keep` (one
problem, the only source of one issue), `split` (independent problems, source of
two or more issues), `merge` (the same problem as other candidates: the same
concrete failure of the same requirement over the same span, in the same
dimension; one issue lists all of them as sources). A part of a split candidate
may be merged. V-L call 1 keeps or splits only (owner, 2026-11-05: config
`rewrite.v_l_actions`; a V-L issue has exactly one source): V-L candidates that
report the same failure of the same requirement (same requirements, an entity
description counting as one requirement in every shot, same quoted words, same
subcategory) are merged by rule in the detection runner (`rule_merge_vl`,
recorded as `rule_merges`); V-V call 1 keeps merge
(`experiments/vl_vv_vl_rule_merge_20261105/REPORT.md`). Then `issues`, each with `source_candidate_ids`, a clear
complete description (corrected details, `revision` / `revision_note`, never
weakening the core problem), and:

- V-L: subcategory, shot_ids, `requirement_quote` (literal contract text or a
  transition item), `template_row_ids` (rows of its sources), frame_refs,
  entity_keys (keys of its sources);
- V-V: scope (kept from the sources), subcategory of that scope, shot_ids,
  frame_refs (both sides for cross_shot), entities (keys of its sources, role
  subject / context).

No verdict, basis or confidence. Gates: every candidate has one action and is
the source of at least one issue; each action matches the issues it feeds;
merged sources share a dimension (V-L, V-V within_shot, V-V cross_shot);
source IDs known and distinct; shots, rows and entities inside the sources;
literal quotes; rows concern the issue's shots; V-V structural rules (one shot
within_shot, two or more cross_shot with frames from two shots, a subject unless
the subcategory is whole-frame, a setting/background issue keeps a changed
element as subject); clarified ⇒ note.

**Issue IDs** are assigned by the runner from the sources, in candidate order:
one source used once keeps its ID (`V3`); several sources are joined (`V1+V4`);
the same sources behind several issues are numbered (`V2.1`, `V2.2`). The
rewritten issues are saved in `rewritten_issues.json` with their sources,
original descriptions and actions.

**Call 2 (verdict).** Input `issues`: only the rewritten issues (ID,
subcategory, description, shots, frame refs, entities; V-L also the quote and
the contract-check rows it concerns), no candidate text and no source IDs.
One verdict per issue: `confirmed` / `rejected` / `uncertain`, a basis from the
fixed list (unchanged), confidence high / medium / low, evidence, assessment;
V-L adds `requirement_applies`, V-V adds `comparison`, `normal_cause`,
`normal_cause_note`. The v6 verdict criteria and gates apply unchanged where
they still apply (basis fits verdict; confirmed ⇒ a supporting frame in the
issue's shots; V-L requirement_satisfied ⇒ a refuting frame; V-V confirmed ⇒
normal_cause none and both sides for cross_shot; normal_change ⇒ a cause;
consistent_in_frames ⇒ a refuting frame; within_shot cites only its shot). A
finding of the other branch is rejected (`visual_difference_only` /
`text_violation_only`). The provenance check of v6 is gone.

Output form of every verdict call (owner, 2026-11-05; both branches, the
direct V-L verdict call included): the runner builds the call's schema
(`run_vl_vv_branch_review.verdict_schema`, saved as
`verdict_output.schema.json`) from the branch's verdict schema file, with
`verdicts` an object that has one required entry per issue ID, in input
order, each the verdict row without `issue_id`. The model therefore cannot
skip, repeat or invent an issue (before, one call answered 86 of 96 issues
and needed a repair round). The runner turns the response back into the
verdict list (`listed_verdicts`), on which the gates above and the units run
unchanged; `model_output.verdict` holds that list. Prompts are unchanged.
Results and `run.json` record `verdict_output_form: keyed_by_issue_id`.
Report `experiments/vl_vv_pipeline_retest_20261105/REPORT.md`.

## 5. Scoring v6

Two text-only severity calls (V-L units, V-V units), as in v5, without
`duplicate_of`. They receive only the confirmed and uncertain units; an
uncertain unit is rated as if the problem were real (owner, 2026-11-03,
`experiments/vl_vv_uncertain_deduction_20261103/`). Python: each confirmed unit
deducts `D = w(severity) × γ(confidence)` with w = 10 / 25 / 50 / 80 (minor,
moderate, major, critical) and γ = 1 / 0.75 / 0.5 (verifier confidence high,
medium, low); each uncertain unit deducts `D = w(severity) × 0.25` (config
`scoring.uncertain_factor`; the verifier's confidence in an uncertain verdict is
not used); rejected units get no severity call and deduct nothing. A dimension
scores `s = 100 × exp(−ΣD / (100 S))` over its confirmed and uncertain units
(V-L, V-V within_shot, V-V cross_shot), `S` = number of shots of the case
manifest (`raw_manifest.json`, hashed with the sources), rounded half up to two
decimals (per-shot rule, owner 2026-11-09; results scored before used
`100 × Π (1 − D/100)`, which saturates when many issues are found and penalizes
longer episodes; `scoring_rule.aggregation = per_shot_exp` and
`scoring_rule.shots` mark the new results; report
`experiments/vl_vv_score_formula_20261109/REPORT.md`); `uec` = mean
of the three (before rounding); `v_v.overall` = mean of within and cross (kept).
`counts` gives per dimension `confirmed`, `uncertain`, `rejected`,
`confirmed_issues` (= confirmed) and `deducting_issues` (confirmed + uncertain);
each `unit_scores` row has `factor` and `factor_basis`.

`consistency_issue_statistics` (within_shot, cross_shot, total):
`confirmed_issues`, `with_unspecified_subject` (confirmed V-V issues with at
least one subject entity labelled unspecified, each issue counted once;
uncertain issues are not counted),
`share` (null without confirmed issues), the unit IDs, and the unspecified
subject entities involved. Context entities do not count. The unit ledger
(`unit_scores`) records each unit's deduction, subject entities with labels and
`involves_unspecified_entity` (on confirmed and uncertain V-V units), so the prompt-centric rescoring of paper Table 5
(drop the issues with an unspecified subject and recompute) can be computed from
it offline. There are no `v_v_unintentional`, `v_v_remainder` or upper-bound
outputs.

## 6. Frontend changes of the same day

- **Clustering (Q11):** the collection bullet of
  `skills/wedetect-shot-entities/review_prompt.txt` was replaced in place by the
  owner's wording (a large number of same-kind items gathered together is one
  node even when every item is visible; a few items stay separate).
- **Binding (Q12):** `prompts/gs_shot_prompt_binding_v2.txt` lets several local
  entities of one shot bind to one contract entity when its name or description
  states several items or members ("Three glasses", "a group of several men").
  `gs_shot_prompt_recovery.py --binding-protocol v2` (VL/VV default through
  `run_vl_vv_detection.py --binding-protocol v2`; the GS pipeline and the
  recovery CLI keep v1) has no duplicate normalization or duplicate gate;
  coverage uses the frames of all bound members; a recovered Grounding DINO box
  of a contract entity with several bound members becomes one new local entity
  bound to it, so no member's track receives another member's box. The ledger
  keeps every bound local entity as an occurrence of the one specified entity
  (several occurrences per shot possible); `global_entities.json` deduplicates
  `observed_shot_ids`; DINO appearance IDs name the local entity when an entity
  has several in one shot. Matching v2 prompt and gates are unchanged (see the
  report's open questions).

## 7. Running

```bash
# Dry run (login node is fine)
python EECBench/scripts/run_vl_vv_pipeline.py --case CASE --output FRESH_DIR --mode from-registry --dry-run
# Retained chain v5
python EECBench/scripts/run_vl_vv_pipeline.py --case CASE --output FRESH_DIR --mode from-registry --dry-run --discovery-protocol v5
# Rendered prompts of both verification calls of a branch
python EECBench/scripts/run_vl_vv_branch_review.py --branch vv --chain v6 --print-prompt
```

Batch: `run_batch.py --discovery-protocol v6` for a new `--exp-dir` (review v7,
scoring v6); an existing directory keeps its recorded chain.

## 8. Cost

Verification goes from one to two image-bearing calls per branch: four
verification calls per episode instead of two (six image-bearing calls in
total with detection). Not measured yet.

## 9. Pipeline C, the unspecified plug-in and the entity scope (2026-11-11)

Owner (2026-11-10): "新流程把C设为默认，然后把这个unspecify专属分支作为plug in"; merged review kept ("保持合并复核").
Validated on all 1,000 first-200 videos (`experiments/vl_vv_full_first200_c_20261110/README.md`, code commit 6f530ee);
the live port reproduces that run's grounding requests, augmented detections, plug-in suspects and merged V-V
candidates from its recorded model outputs (`tests/test_vl_vv_pipeline_c.py`).

- **Background frontend** (`scripts/vl_vv_background_frontend.py`; default on for discovery v6 in full mode,
  `--background-frontend off` restores the previous frontend). Stages: `detect` (first pass: WeDetect, shot
  clustering, binding and recovery) -> `bg_discover` (one GPT-6 Luna low call per shot,
  `prompts/vl_vv_background_discovery_v0.txt`: visible objects not in the first pass's entities) -> `bg_ground`
  (Grounding DINO on the listed frames, box 0.30 / text 0.25, GPU pinned by UUID or CPU) -> `bg_choose` (one Luna
  low call per shot, `prompts/vl_vv_background_boxchoice_v0.txt`, picks a drawn candidate or none per frame, one
  retry) -> `bg_augment` (original WeDetect detections plus the chosen boxes; the first pass moves to
  `background_frontend/pass1/`) -> `redetect` (`run_vl_vv_detection.py detect --detections`: clustering of the
  augmented detections without WeDetect, then binding and recovery) -> `match` and the DINO stages as before.
- **V-V checklist** adds W8 (background objects inside the shot) and X10 (background objects of a shared view): 19
  per-item calls (`configs/vl-vv-branch-v2.json`; schemas regenerated).
- **Unspecified plug-in** (`scripts/run_vl_vv_unspecified_plugin.py`; default on for discovery v6 since 2026-11-12,
  `--unspecified-plugin off` = the ablation without it):
  stage `vv_plugin` between `vv_detection` and `vv_review`. U1 one call per shot (Luna medium,
  `prompts/vl_vv_unspecified_plugin_u1_v1.txt`), U2 by rule (objects against the other shots of the same contract
  place, at most 3; within-shot changes or gaps; at most 15 suspects), U3 one call per suspect (Luna high,
  `prompts/vl_vv_unspecified_plugin_u3_v2.txt`, needs an anchor). Real findings are appended to the V-V candidates
  (checklist item O1, numbering continued) and the V-V review judges the merged list. In the full run the plug-in
  added about USD 0.018 per video and 167 confirmed units over 1,000 videos (standard-price estimate).
- **Both versions of one video** (owner, 2026-11-11, "复用V-L打分"): to report new and new + plug-in together, run the
  pipeline with the plug-in off, then the plug-in, one V-V review of the merged candidates and
  `run_vl_vv_branch_scoring.py --vl-scoring-from <the base episode_scoring>`: the plug-in version reuses the base
  version's V-L severity response (no second V-L severity call; byte-identical V-L review, rendered V-L prompt and V-L
  scorer input required; the reused response is re-validated), so both versions report the same V-L score.
- **Batch controller**: a new discovery v6 `--exp-dir` records `background_frontend: true` and `unspecified_plugin`
  (default true since 2026-11-12, `--unspecified-plugin off` for the ablation); an existing directory keeps what it
  recorded (none recorded = off).
- **Entity scope** (owner, 2026-11-11, "所有类别都加吧，同步改contract"): worn or carried items and walls, floors,
  ceilings, the ground, floor coverings and plants are entities of their own in shot clustering, matching v2, V-V
  detection and review call 1, the background discovery prompt and plug-in U1; the floor-covering exclusion before
  clustering is off (`EECBENCH_EXCLUDE_FLOOR_COVERINGS=1` only to reproduce historical results). Chain v5 prompts
  are unchanged. Contracts follow the same scope (`docs/episode-contract-v2-format.md`). Before-copies and hashes:
  `experiments/vl_vv_entity_scope_20261111/`.

## 10. Default pipeline: new entity rule + new + plug-in (2026-11-12)

Owner (2026-11-12): "把新实体规则+新+插件作为默认流程吧 … new版本就作为去掉插件的ablation". The default chain v6
pipeline is the entity scope of section 9 with pipeline C's background frontend and the unspecified plug-in on:
detection, `vv_detection` -> `vv_plugin` -> one V-V review of the merged candidates -> scoring (its own V-L severity
call). `--unspecified-plugin off` (pipeline and batch controller) runs the ablation "new" (no plug-in). Basis: the
full first-200 run of both versions, `experiments/vl_vv_full_first200_new_20261111/` (README, `summary.json`,
`unspecified_entity_metrics.json`, `cost_four_versions.json`). In that run the plug-in version reused the base
version's V-L severities (section 9, "Both versions of one video"); the integrated default makes its own V-L severity
call, so its V-L score can differ slightly from the base run's.
