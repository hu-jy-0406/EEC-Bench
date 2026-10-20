# Branch-separated V-L / V-V pipeline — implementation and live validation (2026-10-09)

## Request

Decouple V-L and V-V detection, review and scoring into separate GPT calls;
give every detection and review call both definitions so that each branch
stays in its own category; give both branches the detection results as
reference and let them add missed entities; check V-L shot by shot against
the contract (template), check V-V with a strengthened checklist (camera
position, clothing, faces, actions) that filters normal changes; review each
branch separately without a partly-true verdict, with explicit criteria and
evidence, keeping the ability to split compound issues and rewriting unclear
descriptions before deciding; score V-L, V-V within and cross separately plus
a score for V-V issues involving unintentional entities, and report how many
confirmed V-V issues involve unintentional entities; keep the refine loop.

## What was built

Spec: `docs/vl-vv-branch-pipeline-v1.md` (stage I/O, prompts and
placeholders, template, checklist, schemas, gates, refine loop, scoring and
statistics, open dependencies).

| Component | Files |
| --- | --- |
| Shared definitions and boundary | `prompts/vl_vv_branch_definitions_v1.txt` |
| Config (all code lists, checklist, normal causes, review bases, provenance) | `configs/vl-vv-branch-v1.json` |
| Detection (`--branch vl\|vv`) | `scripts/run_vl_vv_branch_detection.py`, `prompts/vl_vv_issue_discovery_v5_{vl,vv}.txt` |
| Review (`--branch vl\|vv`) | `scripts/run_vl_vv_branch_review.py`, `prompts/vl_vv_issue_review_v6_{vl,vv}.txt` |
| Scoring (two severity calls + Python) | `scripts/run_vl_vv_branch_scoring.py`, `prompts/vl_vv_episode_scoring_v5_{vl,vv}.txt` |
| Shared helpers (rendering, quote check, template) | `scripts/vl_vv_branch_common.py` |
| Schemas (generated from the config) | `scripts/build_vl_vv_branch_schemas.py` → `schemas/vl-vv-issue-discovery-v5-{vl,vv}`, `vl-vv-issue-review-v6-{vl,vv}`, `vl-vv-episode-scoring-v5-{vl,vv}`, `vl-vv-branch-records-v1` |
| Refine loop | `scripts/vl_vv_repair_loop.py` (new `repair_prompt` option), `prompts/vl_vv_validation_repair_v2.txt` |
| Orchestration | `scripts/run_vl_vv_pipeline.py` (default `--discovery-protocol v5`; branch chains run concurrently), batch `experiments/vl_vv_multimodel_first200_20260926/run_batch.py` (`v5` → `v6` → `vl_vv_episode_scoring_v5`, cost accounting per branch stage) |
| Tests | `tests/test_vl_vv_branch_pipeline.py` (44 tests: config/schema/prompt consistency, every gate, scoring math and statistics, an offline five-stage run with a fake model, concurrency and failure handling, batch selection); 4 older tests now pin the v4 chain explicitly. 115 VL/VV tests pass. |

The previous chains (discovery v1–v4) are unchanged and selectable with
`--discovery-protocol v4` (etc.). Source snapshots: `source_before/` (files
modified), `source_template_v1/` (first template), `source_final/` (code of the
final validation, with SHA-256 sums).

## Development history (live runs drove three changes)

1. **Smoke run** (`runs/smoke`, #002, 9 calls, USD 0.035): all five stages ran
   end to end. Two gate problems: the first V-L response returned no template
   rows, and "one issue per violated row" was too strict for catch-all rows.
   Fixed (issue lists per row, explicit row count).
2. **First template rubber-stamped** (`runs/main_template_v1`, stopped after
   5 complete runs, 37 calls, USD 0.301). The template had one row per atomic
   claim (120–250 rows). Luna/low filled it as a form: #002 and #014 StoryMem
   all rows `satisfied`, #032 206/208 and #047 247/247 `not_verifiable`;
   observations restated the requirement ("双臂低放在沙发上" while the arms
   lie along the sofa back), 82–91% of cited frames were frame 0 in the three
   all-satisfied or near-all-satisfied runs, and the #002 fill used about 150
   reasoning tokens for 120 rows. I stopped the run and regrouped the
   template: one row per entity per shot (description + its claims as items),
   relations, shot text, transitions (#002 30 rows, #047 69); `observed`
   before `status`; judged rows cite frames from both halves of the shot; a
   not_verifiable entity row that the detector located in ≥2 frames is
   challenged once. Smoke 2 (`runs/smoke2`, 14 calls, USD 0.073): #002 rows
   now describe the frames concretely; #047 went from 0 to 9 V-L candidates.
3. **Pre-gate validation** (`runs/main_pre_element_gate`, 16/16 runs, 103
   calls, USD 0.570) showed (a) V-V boundaries were sometimes not compared
   (#047: one recorded change for 8 shots) — fixed by requiring each boundary
   check to link at least one judged change; and (b) **no entity was ever
   labeled prompt-unbound (0/35 confirmed V-V issues)** because background
   issues cited only the (always prompt-bound) place and no missed entity was
   added — fixed by requiring setting_background / background_drift issues
   (and their review units) to name a changed element other than the place.

## Final validation (`runs/main`, code in `source_final/`)

Eight clip-model videos of the 14-video reference set
(`experiments/vl_vv_v2_results_20261005/results_reference.json`): #002,
#014, #069, #047 Wan2.1; #028, #032 Wan2.2; #014, #047 StoryMem. Frozen
detection registries; 2 independent runs each; API only, on existing
allocation 261017 / node auh7-1b-gpu-250 (load ≈5/128 cores checked before
each launch; no GPU). CineTrans/HoloCine cases were excluded: their frozen
keyframes use the retired grid and need fresh detection.

### Execution

- **16/16 runs succeeded**, 116 API calls: 32 detection calls + 24 repair
  rounds, 30 review calls (no repairs; a review is skipped when its branch has
  no candidate), 30 severity calls. One not_verifiable challenge fired.
- **Wall time** per episode: mean 99.5 s, median 106.6 s, max 200.6 s
  (V-V detection 72.8 s and V-L detection 54.1 s on average, concurrently;
  reviews 13–16 s; scoring 4.3 s).
- **Tokens and cost** (16 runs): 2,456,184 uncached input + 6,132,965 cached
  input + 322,791 output tokens, **USD 0.468** standard GPT-6 Luna API
  estimate (USD 0.10/M uncached input, 0.01/M cached input, 0.50/M output;
  not a bill), i.e. USD 0.029 per episode — about 2.6× the v2 chain's
  ≈USD 0.011 per episode measured on 15 runs on 2026-10-05. V-V detection is
  the largest share (USD 0.215), then V-L detection (0.098), the two reviews
  (0.073 + 0.075) and scoring (0.008).

### Reference artifacts (assistant matching, not human annotation)

Same rule as earlier reports (`matches.json`, notes in `match_notes.json`):

| Video | Branch chain (2 runs) found / confirmed | v2 chain (3 runs) found |
| --- | --- | --- |
| #002 Wan2.1 | 6/8 / 6/8 | 10/12 |
| #014 Wan2.1 | 8/10 / 8/10 | 8/15 |
| #014 StoryMem | 0/4 / 0/4 | 0/6 |
| #028 Wan2.2 | 5/10 / 5/10 | 9/15 |
| #032 Wan2.2 | 3/8 / 2/8 | 4/12 |
| #047 Wan2.1 | 5/10 / 4/10 | 10/15 |
| #047 StoryMem | 3/6 / 2/6 | 5/9 |
| #069 Wan2.1 | 7/12 / 7/12 | 8/18 |
| **Total** | **37/68 (54%) / 34/68 (50%)** | **54/102 (53%)** |

- Recall is level with the v2 chain (54% vs 53%), within run-to-run noise;
  it is not an improvement. On the four videos with discovery v4 + review v5
  runs, the branch chain found 26/40 (65%) vs 36/60 (60%).
- Control (#014 StoryMem courtyard should stay unflagged): 0/2 flagged.
- Never found in either run: #002 A4 (arms not resting low), #014 Wan2.1 A1
  (courtyard), #014 StoryMem A1/A2, #028 A3/A5, #032 A1/A3, #047 Wan2.1
  A2/A4, #047 StoryMem A2, #069 A1/A4. Within-shot artifacts remain weak (1
  confirmed within-shot V-V issue in 16 runs).

### Review behaviour and label leakage

- 84 candidates (50 V-L, 34 V-V) → 97 units: 13 candidates split (5 V-L,
  8 V-V), 55 unit descriptions clarified before the decision.
- V-L: 45 confirmed, 10 rejected (all `requirement_satisfied` with a refuting
  frame), 0 uncertain. V-V: 34 confirmed, 8 rejected (4 `normal_change`, 3
  `not_expected_to_match`, 1 `consistent_in_frames`).
- **No unit was rejected for belonging to the other branch**
  (`visual_difference_only` 0, `text_violation_only` 0). Under the single-list
  chains about 40% of paired V-L labels were rejected, a large part of them
  for V-V-type reasons (`vl_vv_core_review_20261006`); here the V-L rejection
  rate is 10/55 (18%). The candidate sets differ, so this is not a controlled
  comparison.
- Wrong rejections still happen: #047 Wan2.1 run_b rejected the fighters'
  look swap as `not_expected_to_match` (the V-L unit for the same Shot4 look
  was confirmed); #032 run_b accepted a cat with clear black patches as "white
  cat"; #028 run_a rejected the chair type change while confirming its V-L
  counterpart.

### Unintentional entities

| | Confirmed V-V issues | Involving ≥1 unintentional entity | Proportion | Upper bound (incl. uncertain) |
| --- | --- | --- | --- | --- |
| Total | 34 | 3 | 8.8% | 8.8% |
| Within-shot | 1 | 0 | 0% | 0% |
| Cross-shot | 33 | 3 | 9.1% | 9.1% |

The three issues are background-element changes: the kitchen wall colour and
the cabinets in #032 Wan2.2 run_b, and a wood-coloured wall in #047 Wan2.1
run_a; none involves an unintentional person or prop. Before the
changed-element rule the count was 0/35 by construction. These contracts are
dense (8–20 prompt-bound entities per episode), so most recurring content is
prompt-bound; the proportion is small here and should not be generalized to
sparser prompts. `scores.v_v_unintentional.overall` was below 100 in 2/16 runs
(80.47 and 81.25); the factorization check holds in every run.

### Scores (run_a / run_b)

| Video | V-L | V-V within | V-V cross | V-V overall | V-V unintentional |
| --- | --- | --- | --- | --- | --- |
| #002 Wan2.1 | 56.25 / 42.19 | 100 / 100 | 18.75 / 15.23 | 59.38 / 57.62 | 100 / 100 |
| #014 Wan2.1 | 20.89 / 21.09 | 100 / 100 | 75.00 / 67.50 | 87.50 / 83.75 | 100 / 100 |
| #014 StoryMem | 100 / 75.00 | 100 / 100 | 100 / 100 | 100 / 100 | 100 / 100 |
| #028 Wan2.2 | 30.47 / 31.64 | 100 / 100 | 40.63 / 50.00 | 70.31 / 75.00 | 100 / 100 |
| #032 Wan2.2 | 42.19 / 42.19 | 100 / 100 | 25.00 / 30.47 | 62.50 / 65.23 | 100 / 80.47 |
| #047 StoryMem | 75.00 / 75.00 | 100 / 50.00 | 100 / 100 | 100 / 75.00 | 100 / 100 |
| #047 Wan2.1 | 14.06 / 21.09 | 100 / 100 | 15.63 / 100 | 57.81 / 100 | 81.25 / 100 |
| #069 Wan2.1 | 50.63 / 37.50 | 100 / 100 | 3.52 / 5.27 | 51.76 / 52.64 | 100 / 100 |

Run-to-run variance is large for some videos (#047 Wan2.1 V-V cross 15.63 vs
100, from the rejected swap; #047 StoryMem within 100 vs 50, the frame-0
corruption confirmed in one run only).

## Main remaining problem: shot attribution of unlabeled images (proposal, not implemented)

In #002 both runs (and both runs before the gate) put the collared shirt —
and, before the final run, the bright room — in Shot4; the frames show both
in Shot3 (verified on a contact sheet). The v1 historical run made the same
swap. In the pre-gate run_b the V-L reviewer rejected a correct Shot3 claim
because it, too, looked at Shot4's frames. Cause: `scripts/eec_api_codex_shim.py`
sends the prompt text followed by 24–48 unlabeled images; the model must count
positions to map an image to a shot. Proposal: put a short text label
(`Shot3 frame 2`) before each attached image (pixels unchanged). It changes
how evidence is presented to every stage, including the old chains, so it
needs the user's decision; it was not applied.

## Cost of this validation

279 calls in total: 9,287,634 uncached input + 12,196,288 cached input +
792,929 output tokens, **USD 1.447** standard API estimate (not a bill):
smoke 0.035, stopped first-template runs 0.301, smoke 2 0.073, pre-gate
validation 0.570, final validation 0.468 (`validation_spend.json`).

## Files

`run_jobs.py`, `launch.sh` (API-only streams in one overlapping step of an
existing allocation), `analyze.py` → `analysis.json`,
`units_for_matching.md`; `review_stats.py` → `review_stats.json`;
`matches.json`, `match_notes.json`; `validation_spend.json`;
`runs/{smoke,main_template_v1,smoke2,main_pre_element_gate,main}`.

## Follow-up audit (2026-10-09, owner questions)

`followup_audit.json`, `rejection_compare.json`:

- **Review splits:** 13/84 candidates split. 11 were genuine bundles that
  discovery should have separated (lips vs head tilt, shirt vs hair, walls vs
  staircase…). 2 fragmented one failure: the same earflap-hat requirement in
  Shot2 and Shot4 (discovery had correctly made one issue) split by shot, and
  one look swap split per character. Split siblings cannot be linked as
  duplicates, so both deducted twice.
- **Unbound entities in detected issues:** 3/84 (3.6%) detected issues, all
  V-V (3/34 = 8.8%); 0/50 V-L issues cite a detector-unbound or added entity.
  Before the changed-element rule 0/82. The 17 detector-unbound (`ge…`)
  entities in these ledgers were never cited by any issue.
- **Rejections:** V-L rejection rate 18% (10/55) vs 36% (24/67) for the v2
  chain on the same videos and 14% (5/37) for v4+v5 on four of them; my audit
  finds 0 clearly wrong, 3 debatable. V-V rejection rate 19% (8/42) vs 16%
  (10/61) and 7% (3/43); 4 clearly wrong (all "different entity" or
  "consistent" verdicts on text-established same entities: the familiar blue
  chair, the older man's hair, the fighters' look swap twice), 3 debatable.
  Reference artifacts lost at review: 3/37 (8%) vs 4/54 (7%) for v2 and 1/36
  (3%) for v4+v5.
- **Unbound share vs earlier chains** (`unbound_judgments.json`, `unbound_compare.json`):
  detected issues involving a prompt-unbound entity, by my reading under the
  branch definition: v2 chain 7/78 (9.0%), v4+v5 chain 0/80 (4 videos only),
  branch chain 3/84 (3.6%); by the detector partition alone 3/78, 0/80, 0/84.
  The drop comes mainly from the unrequested shirtless old man in #047
  Wan2.1 Shot6 (reported in 3/3 v2 runs, 0/2 branch runs).
