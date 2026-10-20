# Branch-separated V-L / V-V pipeline (discovery v5 → review v6 → scoring v5)

Status: implemented 2026-10-09 at the user's direction; default chain of
`scripts/run_vl_vv_pipeline.py` and selectable in the batch controller
(`--discovery-protocol v5`). The single-issue-list chains (discovery v1–v4)
remain selectable and unchanged. Validation: see
`experiments/vl_vv_branch_split_20261009/REPORT.md`.

## 1. Why

Findings from the previous chains (reports `vl_vv_partial_review_20261006`,
`vl_vv_core_review_20261006`, `vl_vv_entity_scope_20261006`):

- Valid issues were rejected when their description was unclear. The
  partly-true review (v3) did not fix this: its effect was within run-to-run
  noise, it lowered the severity of some confirmed issues, and its main effect
  was to split compound issues. It was removed.
- Many wrong rejections came from mixing the V-L and V-V questions in one
  issue list: a reviewer judged a V-L label by visual sameness ("another shot
  matches") or a V-V difference as a text question.

The new chain therefore separates the two questions completely: separate
detection calls, separate review calls and separate scores, with shared
definitions so that each call knows exactly what belongs to the other one. A
reviewer can still split a compound issue, and it rewrites an unclear
description before deciding instead of rejecting it. There is no partly-true
verdict.

## 2. Stages, inputs, outputs and call relationships

```
case (frozen detection registry)
 ├── vl_detection  (1 call + repairs)  → vl_review  (1 call + repairs, none if no candidates) ─┐
 └── vv_detection  (1 call + repairs)  → vv_review  (1 call + repairs, none if no candidates) ─┴→ episode_scoring
                                                                    (V-L call + V-V call in parallel, then Python)
```

The two branch chains run concurrently (`run_vl_vv_pipeline.py` runs each
branch's stages in order in its own thread); `episode_scoring` starts after
both reviews. A branch failure lets the other branch finish, then fails the
run; scoring does not run.

| Stage | Script | Inputs | Output (`OUTPUT/<stage>/result.json`) | Feeds |
| --- | --- | --- | --- | --- |
| 1. Detection registry | `run_vl_vv_detection.py` (unchanged) | prepared case, keyframes | `case/episode_entities.json` (prompt_bound `pb…` / prompt_unbound `ge…` entities with per-shot boxes) | both branches as reference information |
| 2a. V-L detection | `run_vl_vv_branch_detection.py --branch vl` | original prompt, full contract, shot transitions and sources, **contract-checking template** (built by the runner), detector ledger, all keyframes | `checks` (one per template row), `issues` (canonical, `L1…`), `entities` (ledger + added `n…`), `model_output`, counts, usage | 3a |
| 2b. V-V detection | `run_vl_vv_branch_detection.py --branch vv` | all keyframes, detector ledger, prompt and contract **as context only**, shot transitions and sources, required continuity subjects, required characters per shot, **V-V checklist** | `issues` (canonical, `V1…`), `entities` (entity register with provenance), `model_output` (audit, shot scan, continuity ledger, boundary checks, observed changes) | 3b |
| 3a. V-L review | `run_vl_vv_branch_review.py --branch vl` | V-L candidates with the template rows they cite, prompt, contract, transitions, entity index, all keyframes | `units` (canonical reviewed units), candidates, counts | 4 |
| 3b. V-V review | `run_vl_vv_branch_review.py --branch vv` | V-V candidates with their observed changes, entity index with proposed provenance, prompt/contract as context, checklist, all keyframes | `units` with verified entity provenance | 4 |
| 4. Scoring | `run_vl_vv_branch_scoring.py` | the two review results (no images) | V-L, V-V within/cross/overall, unintentional subset scores, V-V issue statistics, ledgers, usage | batch summaries |

Every stage writes `input.json`, `prompt_rendered.txt` (the exact prompt
text), `source_hashes.json`, `run.json` (status, seconds, token cost) and its
call folders (`call`, `call_repair_NN`, `call_repair_audit.json`). Model
pinning is unchanged: GPT-6 Luna, reasoning low, through
`scripts/openai_api_env.sh`.

## 3. Definitions shared by every branch call

File: `prompts/vl_vv_branch_definitions_v1.txt`, included verbatim (as
`{{VL_VV_DEFINITIONS}}`) in all four detection and review prompts. It gives
both definitions, their subcategories and a boundary table of what each
branch reports. The other branch's definition is there only so that the call
can leave those findings out.

- **V-L (video vs language)**: a visible observation contradicts an explicit
  requirement of the text (global prompt, shot prompt, contract entity
  descriptions / schedule / claims, required transitions). The violated words
  can be quoted literally. Entity descriptions are episode-wide (rule of
  2026-10-06); the wording is the requirement, not how another shot happened
  to depict it; explicit continuity words ("the same sofa", "remains",
  "back in") make sameness itself the requirement. The last point restores
  the continuity exception that the second in-place sentence of review v5
  had suppressed.
- **V-V (video vs video)**: a visible observation is incompatible with other
  visual evidence of the same episode without a visible or text-supported
  cause; within one shot or across shots (including transition realization).
- Boundary table (excerpt): a described attribute wrong in every shot → V-L
  only; an undescribed attribute changing between shots → V-V only; a
  described attribute changing between shots → V-L reports the violating
  shots, V-V reports the change; a shot that satisfies the words but differs
  from another shot → V-V only; a missing required cut → V-L
  `shot_structure` and V-V `transition_realization`.

Subcategories: the ten V-L subcategories, the nine within-shot and ten
cross-shot V-V subcategories of protocol v2 are kept. One within-shot V-V
subcategory is **added**: `action_discontinuity` (a pose, position or action
jumps, reverses or restarts between frames without continuous motion), so
that the strengthened action check has a home. All codes live in
`configs/vl-vv-branch-v1.json`.

### Unintentional entities

- **Prompt-bound** entity: the text refers to it (a contract entity, a prompt
  phrase naming it or the role it plays), or it is an intrinsic part (face,
  hair, body, worn clothing, accessories) of such an entity.
- **Prompt-unbound** entity: no global prompt, shot prompt or contract text
  refers to it and it is not part of a referenced entity.
- **Unintentional entity** = a visible entity whose final text provenance is
  prompt-unbound: the generator introduced it. A prompt-bound entity is never
  unintentional, even when it is rendered wrongly (that is a V-L question).
- **Uncertain** provenance: the text could refer to it but is too vague (for
  example "people in the background" for one specific bystander). Kept as a
  separate label and reported as an upper bound, never forced into either
  side.
- Relation to the detector partition: the ledger's `prompt_bound` (`pb…`)
  entities were bound to a contract entity during detection and are treated
  as prompt-bound (the V-V calls may mark one uncertain, never unbound). The
  ledger's `prompt_unbound` (`ge…`) entities are candidates only: glasses or
  a watch the ledger split from a described character are `part_of_entity`
  and prompt-bound. Places: a scheduled place is prompt-bound; its separate
  structures, furniture and signage are prompt-bound only if the text states
  them. Entities the detector missed are added by the V-V detection agent
  (`n1, n2, …`) and labeled by the same test.
- Where the labels come from: the existing pipeline only had the ledger
  partition, which cannot decide this (it misses background elements and
  splits worn items). The new labeling step is in V-V detection
  (`entity_register`: provenance + basis), verified by the V-V reviewer for
  every entity of every unit, with deterministic gates (section 7). A
  setting_background or background_drift issue must name the changed
  structures or elements (a wall covering, a sign, a piece of furniture) as
  subject entities, adding them when the ledger lacks them; the place itself
  may only be an extra subject or context. Without this rule the agent cited
  only the (always prompt-bound) place, so unstated background elements were
  never labeled.
- "An issue involves an unintentional entity" when one of its **subject**
  entities (the entity whose identity, appearance, state, presence or
  position is inconsistent, or one side of an inconsistent relation) is
  unintentional. Context entities that only help to locate the problem do
  not count.

## 4. Prompts and placeholders

All prompts are complete texts in `prompts/`. Two kinds of placeholders:

- **Static** `{{NAME}}` placeholders are filled by
  `vl_vv_branch_common.render_prompt` from repository files before the call;
  the rendered text is saved as `prompt_rendered.txt` in the stage folder and
  can be printed with `--print-prompt`:
  `{{VL_VV_DEFINITIONS}}` (definitions file, itself containing
  `{{VL_SUBCATEGORIES}}`, `{{VV_WITHIN_SUBCATEGORIES}}`,
  `{{VV_CROSS_SUBCATEGORIES}}`), `{{VV_CHECKLIST}}`, `{{VV_NORMAL_CAUSES}}`
  (all from `configs/vl-vv-branch-v1.json`). An unknown or unrendered
  placeholder is an error.
- **Dynamic** episode inputs are never pasted into the prompt text. Each
  prompt has a "Dynamic inputs" section naming them as `INPUT.<field>`; the
  transport appends `INPUT:` followed by the stage's `input.json`, and attaches
  the keyframes in `INPUT.image_order` order.

| Call | Prompt | Output schema | Dynamic inputs |
| --- | --- | --- | --- |
| V-L detection | `vl_vv_issue_discovery_v5_vl.txt` | `vl-vv-issue-discovery-v5-vl.schema.json` | `original_prompt`, `contract_json`, `shot_transitions`, `shot_sources`, `contract_check_template`, `detector_ledger`, `image_order` + images |
| V-V detection | `vl_vv_issue_discovery_v5_vv.txt` | `vl-vv-issue-discovery-v5-vv.schema.json` | `image_order` + images, `detector_ledger`, `original_prompt`, `contract_json`, `shot_transitions`, `shot_sources`, `required_continuity_subjects`, `required_shot_characters` |
| V-L review | `vl_vv_issue_review_v6_vl.txt` | `vl-vv-issue-review-v6-vl.schema.json` | `candidate_issues` (with cited `template_rows`), `original_prompt`, `contract_json`, `shot_transitions`, `shot_sources`, `entity_index`, `image_order` + images |
| V-V review | `vl_vv_issue_review_v6_vv.txt` | `vl-vv-issue-review-v6-vv.schema.json` | `candidate_issues` (with `changes`), `entity_index` (with proposed provenance), `original_prompt`, `contract_json`, `shot_transitions`, `shot_sources`, `image_order` + images |
| V-L severities | `vl_vv_episode_scoring_v5_vl.txt` | `vl-vv-episode-scoring-v5-vl.schema.json` | `units` (V-L reviewed units, no images) |
| V-V severities | `vl_vv_episode_scoring_v5_vv.txt` | `vl-vv-episode-scoring-v5-vv.schema.json` | `units` (V-V reviewed units, no images) |
| Repair turns | `vl_vv_validation_repair_v2.txt` | the stage's schema | `validation_errors`, `previous_output` |

## 5. Contract-checking template (V-L)

Built deterministically by `vl_vv_branch_common.contract_template` from the
contract and passed as `INPUT.contract_check_template`; saved in the V-L
detection result. Rows are **clause groups**, per shot in manifest order;
each row lists its requirement **items**:

| Row kind | Row ID | Items | One per |
| --- | --- | --- | --- |
| `entity` | `EN:<label>@<shot>` | `description` (the episode-wide entity description, when the entity is scheduled in the shot) + each single-entity claim of the shot about it (`item_id` = claim ID, with dimension, expected, quantifier, contract quotes, `depends_on`) | contract entity scheduled in, or claimed for, the shot |
| `relations` | `RL:<shot>` | the shot's claims that relate two or more entities | shot with such claims |
| `shot_text` | `SP:<shot>` | `text` (the shot prompt, standing for every other explicit requirement of the shot and of the global prompt) | shot |
| `transition` | `TR:<from>-><to>` | `transition` (quoted as `ShotA->ShotB: cut`) | boundary, attached to the later shot |

All contract claims appear as items (a test checks this). #002 has 30 rows
(120 items), #047 69 rows (247 items).

The model fills one `checks` entry per row, in this field order:
`observed` (first, what the six frames actually show for the row, in
concrete visible values; restating the requirement is explicitly wrong),
`status` (`satisfied`, `violated`, `not_verifiable`, `not_applicable`),
`violated_items` (the contradicted item IDs; non-empty exactly when
violated; if a presence item is violated only it is listed, so one absence
is reported once), `frame_refs` (a judged row cites a frame from each half of
the shot; a transition row a frame of each boundary shot; not_verifiable the
frames inspected), `issue_ids` (the issues reporting the row; a transition
row has exactly one, other rows may host several independent failures).

Design history (kept in `experiments/vl_vv_branch_split_20261009`): the
first template had one row per atomic claim and description (120–250 rows).
In live runs Luna/low filled it as a form: every row satisfied, or every row
not_verifiable, with observations that restated the requirement and cited
frame 0. Grouping by entity, putting `observed` before `status`, requiring
frames from both halves of the shot, and challenging once a not_verifiable
entity row that the detector located in two or more frames of the shot
replaced it.

Each **V-L issue** is one failed requirement; the same failure in several
shots is one issue with one occurrence per shot: `subcategory`,
`requirement_quotes` (`{source, shot_id, quote}`, literal), `expected`,
`occurrences` (`shot_id`, violated `row_ids`, `frame_refs`, `observed`,
`mismatch`), `entity_keys`, `summary`, `confidence`. This records the shot,
contract clause, expected content, observed content and mismatch for every
issue.

## 6. V-V checklist and template

Checklist items (rendered from the config into the V-V detection and review
prompts; the validator requires exactly one `checklist_audit` entry each):

| Item | Scope | Check (abridged) |
| --- | --- | --- |
| W1 | within | **Camera position and movement**: shot scale, angle, camera position per frame; classify none / smooth / reframe / jump; a jump is an unintended cut unless requested |
| W2 | within | **Clothing, hair, accessories** of every visible character, frame by frame |
| W3 | within | **Face and identity**: face shape, apparent age, skin tone, features; expression and head turns are normal |
| W4 | within | **Actions, poses, bodies**: continuous evolution (no teleport, pose swap, reversal, restart), intact bodies |
| W5 | within | Objects, held items, contacts |
| W6 | within | Presence and count |
| W7 | within | Background, lighting, rendering (incl. frame 0 flash) |
| X1 | cross | **Camera positions across shots**: a new camera position at a cut is normal; comparable positions must show the same background/layout; the layout must be explainable by the camera change |
| X2 | cross | **Faces and identity** of every recurring character, all of its shots |
| X3 | cross | **Clothing, hair, accessories** of recurring characters; attribute migration |
| X4 | cross | **Actions and poses across boundaries and returns**; no reset or repeat without elapsed time |
| X5–X9 | cross | Objects; settings and background elements (changed elements named as entities); lighting/style; instances; spatial layout |
| X10 | cross | Transition realization at every boundary |
| O1 | episode | Open-ended sweep |

Template the V-V agent fills before writing issues:

- `shot_scan` (one per shot): `camera` {`setup` per frame, `movement`, note};
  `characters` (every visible character and every scheduled prompt-bound
  character): `face`, `hair_clothing`, `action`, `stable`; `other`;
  `change_ids`.
- `continuity_ledger`: per recurring character / place / object, one
  signature per scheduled or visible shot (places include the camera
  position they are seen from), assessment, linked changes.
- `boundary_checks`: one per boundary: required transition, last frame,
  first frame, realized / not_realized / uncertain, continuity.
- `observed_changes`: **every** change noticed, with a **normality test**:
  `normal` (with a cause: camera_motion, viewpoint_change, described_action
  with a literal quote, visible_action, occlusion_or_framing,
  lighting_cause, time_skip, different_entity, required_transition,
  cut_timing_offset, image_quality), `abnormal` (no normal cause, the frames
  show the difference) or `uncertain` (cannot tell whether it changed).
  **Only abnormal changes become issues**; this is the false-positive filter.
- `entity_register`: provenance of every entity used by an issue and every
  added entity (section 3).
- `issues`: each groups abnormal changes of one physical discrepancy, with
  `entities` (`entity_key`, role `subject` / `context`), `key_evidence` on
  both sides, `checklist_items`, `confidence`.

## 7. Shared structured records and validation gates

`schemas/vl-vv-branch-records-v1.schema.json` defines the canonical records
every stage hands on:

- **issue**: `issue_id`, `branch` (`v_l` / `v_v`), `scope` (`v_l`,
  `within_shot`, `cross_shot`), `subcategory`, `description`, `shot_ids`,
  `entity_refs` (`entity_key`, `role`), `key_evidence`, `confidence`,
  `v_l_detail` (requirement quotes, expected, occurrences, template rows) or
  `v_v_detail` (changes, checklist items);
- **entity**: key, ledger ID or null, source (`detection_ledger`,
  `added_by_vl_detection`, `added_by_vv_detection`), name, description,
  ledger partition, contract label, provenance and basis;
- **unit** (reviewed): `unit_id`, `parent_issue_id`, branch, scope,
  subcategory, revised `description` and `original_description`,
  `revision`, `split`, `shot_ids`, `verdict`, `basis`, `confidence`,
  `evidence`, `assessment`, `entity_refs` with final provenance, and
  `v_l_detail` (requirement quote, whether it was verified literally,
  applicability) or `v_v_detail` (comparison, normal cause).

All model schemas are generated from the config by
`scripts/build_vl_vv_branch_schemas.py` (a test fails if they drift).
Semantic gates (all go back to the model through the repair loop):

| Stage | Gates |
| --- | --- |
| V-L detection | one check per template row; `violated_items` ⊆ the row's items and non-empty exactly when violated; a violated presence item is the only violated item of its row; judged rows cite frames from both halves of the shot (transition rows: both boundary shots), not_verifiable rows cite inspected frames; a not_verifiable entity row whose entity the detector located in ≥2 frames of the shot is challenged once; violated ↔ linked issues whose occurrences list the row (transition rows: exactly one issue); occurrence rows belong to the occurrence's shot; transition rows → `shot_structure`; **every requirement quote is literal** (normalized substring of the named source; an ellipsis may join exact fragments; wrong source → hint); entity keys known; entity-free issues only for setting/camera/style/shot-structure; added entities used and placed in frames |
| V-V detection | every checklist item once, X10 not N/A for multi-shot, cited items not N/A; one shot scan per shot with every scheduled prompt-bound character; a camera jump or an unstable character links a change; every within-shot change listed in its shot scan; continuity ledger covers every required subject and scheduled shot, inconsistent ⇔ an abnormal change linked; one boundary check per boundary in order, each linking ≥1 judged change that compares the two shots, not_realized → transition_realization issue; changes: scope/shots/frames on both sides, normal ⇒ cause (+ literal quote for described_action) and no issue, abnormal ⇒ issue, uncertain ⇒ no issue; issues: subcategory fits scope, only abnormal changes, change scope and shots match, witnesses from two shots for cross-shot, a subject entity unless the subcategory is whole-frame, setting_background / background_drift issues name a changed element other than the place, every issue entity has a register row; register: provenance/basis pairs from the config, contract labels exist and match the ledger binding, prompt quotes literal, `part_of` names a prompt-bound entity, ledger `pb…` never prompt_unbound, added entities have frames and are used |
| Reviews | every candidate once; keep → one unit with the candidate's ID, split → ≥2 units `<id>.1…` in order with a reason; unit shots inside the candidate's; clarified ⇒ revision note; basis fits verdict; **confirmed ⇒ a supporting frame from the unit's shots**; V-L: confirmed / satisfied / not-applicable / visual-difference ⇒ literal requirement quote, requirement_satisfied ⇒ a refuting frame; V-V: scope kept, subcategory fits, within-shot cites only its shot, confirmed ⇒ normal_cause none and evidence from two shots for cross-shot, normal_change ⇒ a cause, consistent_in_frames ⇒ a refuting frame, entities only the candidate's, a subject unless whole-frame, a setting/background unit keeps a changed element of its candidate as subject, one provenance per entity across units, ledger `pb…` never prompt_unbound |
| Severities | one assessment per unit; confirmed ⇒ severity; rejected/uncertain ⇒ none, no duplicate; duplicates point to an earlier confirmed unit of the same scope, never self, never a split sibling, no chains |

## 8. Review: labels and criteria

Before deciding, the reviewer chooses **keep** (one problem) or **split**
(two or more independent problems that can be true or false separately:
different requirements, entities, attributes or shot pairs). It writes a
clear, complete `description` of each unit, correcting unclear or partly
inaccurate wording (`revision: clarified` + note), without weakening the core
problem, then judges the unit as described.

| Verdict | V-L criteria (basis) | V-V criteria (basis) |
| --- | --- | --- |
| confirmed | `requirement_violated`: literal quote exists; it applies to the unit's shots (own text, global prompt, or an episode-wide description without a different description in the shot); a **supporting** frame shows the contradiction | `inconsistency_confirmed`: the observations should match (same entity/place/moment, or one take); no normal cause (`normal_cause: none`, note says what was checked); evidence on both sides with ≥1 **supporting** frame |
| rejected | `requirement_absent` (the text does not say it), `requirement_not_applicable` (does not apply to these shots), `requirement_satisfied` (a **refuting** frame shows compliance), `visual_difference_only` (only differs from another shot: a V-V question) | `consistent_in_frames` (a **refuting** frame), `normal_change` (name the cause), `not_expected_to_match`, `text_violation_only` (consistent video, only contradicts text: a V-L question) |
| uncertain | `not_verifiable`: name the missing evidence | `not_verifiable`: name the missing evidence |

A real core problem is never rejected because of a wrong secondary detail;
the detail is corrected in the description. There is no partly-true verdict.
A finding in the wrong branch is rejected with the boundary basis
(`visual_difference_only` / `text_violation_only`) and is not transferred, so
the branches stay independent; the other branch's own detection is
responsible for it. The basis counts measure such leakage.

## 9. Refine (validation-repair) loop

The existing `vl_vv_repair_loop.call_with_repair` is used by all six calls.

- **Trigger**: any JSON-schema violation or any semantic gate of section 7
  on a model response (including every repair response).
- **Correction step**: all problems (schema + semantic, not only the first)
  and the complete previous output are sent back in the same conversation
  (`previous_response_id`) with `prompts/vl_vv_validation_repair_v2.txt`;
  the model returns one complete corrected output in the same schema. If the
  stored conversation is unavailable, the full task (prompt + repair
  instructions + input + images) is resent. Repair v2 differs from v1 only in
  allowing the identifiers the task lets the model create (issue, change and
  split unit IDs, added entity keys) and in asking for literal quotes.
- **What reruns**: only the failing call of that stage. Upstream outputs are
  immutable (source hashes are checked after every stage); downstream stages
  start only after the stage's output passed every gate.
- **Termination**: the output passes all gates (accepted), or 8 repair rounds
  fail → the stage fails with its remaining errors, the branch stops, the
  other branch finishes, the pipeline run fails without scoring. Recovery
  uses a fresh output directory (or the stage CLI into a fresh folder);
  nothing is overwritten. Every round's errors and usage are kept in
  `call_repair_audit.json`; all rounds count in the cost.
- Existing deterministic normalizations of older stages are not applied in
  this chain (there are none in v5/v6); nothing is repaired in code.

## 10. Scoring and entity statistics

Penalty rubric v2, unchanged: base deductions minor/moderate/major/critical =
10/25/50/80, multiplied by reviewer confidence (high 1, medium 0.75, low
0.5). Confirmed units linked by `duplicate_of` form one **event**
(= one independent issue) that deducts its maximum; split units are separate
events. A bucket scores `S = 100 · Π (1 − D_e/100)`, rounded half up to two
decimals. Rejected and uncertain units deduct nothing.

| Score | Events |
| --- | --- |
| `scores.v_l` | V-L events (existing framework) |
| `scores.v_v.within_shot`, `.cross_shot` | V-V events of that scope; `.overall` = their mean (existing rule) |
| `scores.v_v_unintentional.{within_shot, cross_shot, overall}` | only V-V events with **definite** unintentional involvement (a subject entity with final provenance prompt_unbound; an event is involved if any of its units is) |
| `scores.v_v_remainder.{…}` | the other V-V events |
| `scores.v_v_unintentional_or_uncertain.{…}` | events with definite or uncertain-only involvement (upper bound) |

Relationship: every V-V event is in exactly one of the unintentional and
remainder subsets, so for each scope
`v_v = v_v_unintentional × v_v_remainder / 100` exactly before rounding
(`factorization_check` records both sides). The unintentional score is the
part of the V-V score lost to inconsistencies of content the prompt never
asked for; it is ≥ the V-V score. A subset with no confirmed events scores
100, which is not proof of consistency: read it with the counts.

`v_v_issue_statistics` (total, `within_shot`, `cross_shot`):
`confirmed_issues` (independent confirmed V-V issues), `involving_unintentional`
(issues with ≥1 unintentional subject entity, each counted once however many
it has), `proportion` (= involving / confirmed; null when there is no
confirmed issue), `involving_unintentional_or_uncertain` and
`proportion_upper_bound`, `confirmed_units`, plus the list of unintentional
entities involved. Batch summaries (`run_batch.py score_record`) carry the
subset scores and these statistics.

## 11. Running

```bash
# Dry run (login node is fine): validates the case and prints the five stages
python EECBench/scripts/run_vl_vv_pipeline.py --case CASE --output FRESH_DIR --mode from-registry --dry-run

# Real run, inside an existing allocation (API only; no GPU for from-registry)
EECBench/scripts/openai_api_env.sh python EECBench/scripts/run_vl_vv_pipeline.py --case CASE --output FRESH_DIR --mode from-registry

# Inspect the exact rendered prompt of one call (no API call)
python EECBench/scripts/run_vl_vv_branch_detection.py --branch vv --print-prompt

# Regenerate the schemas after editing configs/vl-vv-branch-v1.json
python EECBench/scripts/build_vl_vv_branch_schemas.py
```

Stage CLIs can also be run alone: `run_vl_vv_branch_detection.py --branch
vl|vv --case CASE --output DIR`, `run_vl_vv_branch_review.py --branch vl|vv
--case CASE --detection DIR/result.json --output DIR2`,
`run_vl_vv_branch_scoring.py --vl-review … --vv-review … --output DIR3`.
Batch: `experiments/vl_vv_multimodel_first200_20260926/run_batch.py
--discovery-protocol v5` for a new `--exp-dir` (an existing directory keeps
its recorded chain). Old chains: `--discovery-protocol v4` (or v1–v3) in both
runners.

## 12. Open dependencies and information gaps

- **No human labels.** Neither the provenance labels nor the confirmed
  issues are calibrated against human annotation; the penalty weights are
  conventions. The unintentional proportion is a model-judged statistic with
  an uncertain-provenance bound.
- **Added entities have no boxes.** Entities the detector missed are located
  only by frame references; they are not added to the detector ledger, and
  appearance (DINO) evidence does not exist for them.
- **Unintentional support is not audited.** The statistics count confirmed
  issues; the chain does not inventory every unintentional entity in the
  video, so it cannot report a break rate per unintentional entity (see the
  hierarchical scoring design, which proposes such an audit).
- **Contracts without claims** fall back to entity-description, shot-text and
  transition rows; all first-200 contracts carry claims.
- **Episode-video cases** (CineTrans, HoloCine) need fresh detection on the
  recorded-cut keyframes before this chain can run on them.
- **Cost.** Four image-bearing calls per episode instead of two (detection and
  review per branch); see the validation report for measured usage.
