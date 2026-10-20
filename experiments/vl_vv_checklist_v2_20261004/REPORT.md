# VL/VV issue checklist and non-exclusive V-L/V-V labels (protocol v2) — 2026-10-04

## Request

1. Make problem finding systematic with a must-check checklist built from
   (a) problem types already detected across models and (b) problems that
   exist in generated videos but were missed, e.g. #014 Wan2.1-T2V Shot1 vs
   Shot3 background (StoryMem stays consistent) and #028 Wan2.2 the woman's
   clothing across shots. The checklist is not closed: the evaluator must still
   report any obvious or meaningful issue. V-V cross inspection must check that
   a required cut is a clear shot change and a required continue keeps
   continuity without an unintended cut.
2. Make V-L and V-V non-exclusive and define them with subcategories
   (especially V-V within and V-V cross) so issues are labeled consistently;
   e.g. #002 Wan2.1's two V-L issues are also V-V.

## Outcome

- Definitions, 10 V-L / 9 V-V-within / 10 V-V-cross subcategories, labeling
  rules, worked examples and the S1–S7 / C1–C8 / O1 checklist:
  `EECBench/docs/vl-vv-issue-taxonomy-checklist-v2.md`. Scoring v3:
  `EECBench/docs/vl-vv-episode-scoring-v3.md`.
- Implemented as the default chain discovery v2 → review v2 → scoring v3;
  `--discovery-protocol v1` restores the historical chain. 45 focused tests
  pass. No GPU work, no frontend/detection rerun; all first-200 v1 results
  are untouched.
- Live validation on 14 frozen cases (three rounds, 96 API calls, USD 0.55
  standard-API estimate): all three owner examples are now caught;
  17 of 41 audit-reported v1 misses on those cases were recovered in a single
  run; within-shot and face-identity recall remain the weakest areas.

## 1. Census of already-detected problems (v1, first-200 × 5 models)

2,410 reviewed candidates in 1,000 tasks (`analysis/map_detected_issues.py`,
`analysis/detected_issue_mapping*.json`; keyword mapping to v2 subcategories,
approximate). V-L 1,919 (1,744 confirmed), V-V within 45 (39), V-V cross 446
(395). Per-model means of V-V within were 97.26–100. Main detected types:
V-L attributes 751, presence/count 339, interaction 262, action 181, spatial
173, camera 88, setting 53, "shot still shows previous content" 41, style 31;
cross character appearance 201, object 81, identity 61, setting 59,
rendering style 30. Every class maps to a checklist item (design doc §6.1).
229 V-L rows span several shots: the v1 rule "each discrepancy in one list
only" kept many cross-shot inconsistencies out of V-V.

## 2. Audit of missed problems

Six independent Claude subagent audits viewed contact sheets and
full-resolution keyframes of 23 episodes (#002, #014, #028 plus 20 random
episodes stratified 10/6/4 by 4/6/8 shots) × 5 models = 115 videos, against
each video's v1 findings (`analysis/missed_issue_audit/`). Result: 288 missed
issues (202 high confidence; 71 major/critical), 43 already-detected V-L rows
that should also be V-V, 9 doubtful confirmed v1 issues. Code mentions: V-L
266, within 75, cross 208; 93 missed issues need both labels.

| Model | missed | with V-L code | with within code | with cross code | dual | major+ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Wan2.1 | 75 | 51 | 7 | 49 | 32 | 14 |
| CineTrans | 80 | 50 | 27 | 33 | 24 | 35 |
| Wan2.2 | 45 | 23 | 3 | 34 | 14 | 7 |
| StoryMem | 36 | 29 | 10 | 7 | 10 | 2 |
| HoloCine | 52 | 30 | 8 | 31 | 13 | 13 |

Patterns behind the checklist: required cuts never checked (CineTrans often
one static take for the whole episode, HoloCine missing cuts and shot content
in the wrong interval; 27 structural transition failures, plus 22 sub-second
late cuts that are timing offsets, by keyword split of the 49 transition items); within-shot checks almost never fired
(identity/outfit morphs, pop-in/out, flashes often at frame 0); only one
character or one shot pair compared; attributes migrating between characters,
swaps and merges; a failure flagged in one shot but not the others. Spot
checks of #002, #014, #028, #068, #069 and #180 confirmed the cited
high-impact findings. The audit is agent judgment at keyframe resolution, not
human ground truth.

## 3. Protocol changes

- **Discovery v2** (`prompts/vl_vv_issue_discovery_v2.txt`): single issue list
  with `v_l` and/or `v_v` labels; must-check checklist with one
  `checklist_audit` entry per item; mandatory open-ended sweep O1; one
  `shot_scan` entry per shot (frames 0–5 compared); `continuity_ledger` with
  per-shot signatures for every recurring character/place (prompt-bound
  subjects scheduled in ≥2 shots are mandatory); `shot_transitions` and
  `shot_sources` inputs with explicit cut/continue checks and a timing-offset
  rule for episode videos; rules for comparable-viewpoint setting comparison,
  face/hairstyle comparison, cut vs subject motion, attribute bleed, carrying
  one failure to all affected shots.
- **Review v2**: one verdict/confidence/assessment per label; the same
  setting, identity and cut rules; existing all-refutes normalization per label.
- **Scoring v3**: one severity per label; a confirmed dual-labeled issue
  deducts in V-L and in its V-V bucket; penalty rubric v2 numbers unchanged.
- Transition requirements: `case/shot_transitions.json` → source shot-map
  `cut` flags → default cut. All 1,000 first-200 flags are `true`.
- Source snapshots before editing: `source_before/` (SHA256SUMS).

## 4. Live validation

API-only stages on the frozen first-200 detection cases (read-only), run
sequentially from the login node because no allocation of this account was
running (network-bound calls; no GPU/CPU-heavy work). Driver
`run_validation.py`, summary `summarize_validation.py` →
`validation_summary.json`.

- Round 1 (6 cases): first prompt. Found #002 dual issues and the #028
  CineTrans missing cuts and merged women; exposed three prompt weaknesses:
  the reviewer excused the #014 Wan2.1 background change as "another angle",
  subject motion was called a cut (StoryMem #014), and ledger signatures were
  too generic for face/hair drift. Prompts were refined (copies of round-1
  prompts in `validation_round1/`).
- Round 2 (6 + 4 held-out): #014 Wan2.1 courtyard confirmed; StoryMem #014
  clean; held-out #180/#068/#047 transition, attribute-swap and setting
  failures caught; within-shot recall still low → added `shot_scan`.
- Round 3 (10 + 4 fresh held-out), final prompts:

| Case | v1 V-L / within / cross | v2 V-L / within / cross | issues | dual-labeled | confirmed in both | calls |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| #002 wan21 | 60.94 / 100.00 / 100.00 | 23.44 / 100.00 / 23.44 | 4 | 3 | 2 | 3 |
| #014 holocine | 56.25 / 100.00 / 100.00 | 56.25 / 100.00 / 100.00 | 3 | 0 | 0 | 3 |
| #014 storymem | 100.00 / 100.00 / 100.00 | 100.00 / 100.00 / 75.00 | 2 | 2 | 0 | 3 |
| #014 wan21 | 67.50 / 100.00 / 100.00 | 26.37 / 100.00 / 50.78 | 5 | 3 | 1 | 3 |
| #015 cinetrans | 22.78 / 100.00 / 81.25 | 14.06 / 75.00 / 37.50 | 6 | 2 | 2 | 4 |
| #028 cinetrans | 18.75 / 100.00 / 100.00 | 10.55 / 100.00 / 50.00 | 5 | 2 | 1 | 3 |
| #028 wan22 | 40.63 / 100.00 / 100.00 | 100.00 / 100.00 / 75.00 | 1 | 1 | 0 | 3 |
| #032 wan22 | 56.25 / 100.00 / 100.00 | 18.75 / 100.00 / 40.63 | 4 | 1 | 1 | 3 |
| #047 storymem | 100.00 / 100.00 / 100.00 | 52.03 / 69.38 / 100.00 | 4 | 2 | 2 | 3 |
| #047 wan21 | 50.00 / 100.00 / 100.00 | 25.00 / 100.00 / 25.00 | 3 | 2 | 1 | 4 |
| #068 holocine | 56.25 / 100.00 / 100.00 | 21.09 / 90.00 / 75.00 | 6 | 4 | 1 | 5 |
| #069 wan21 | 50.00 / 100.00 / 31.64 | 31.64 / 100.00 / 21.36 | 7 | 6 | 3 | 3 |
| #165 cinetrans | 81.25 / 100.00 / 100.00 | 37.50 / 100.00 / 75.00 | 3 | 1 | 1 | 3 |
| #180 cinetrans | 50.00 / 100.00 / 100.00 | 25.00 / 75.00 / 50.00 | 3 | 1 | 1 | 3 |

The discovery prompt's labeling examples are taken from #002, #014 and #028,
so those cases are not independent tests; #015, #032, #047, #068, #069,
#165 and #180 were not used to write examples (#047/#068/#069/#180 informed
the round-3 rule edits after round 2).

Owner examples: #014 Wan2.1 courtyard confirmed as V-V cross
`setting_background` + V-L `stated_continuity` (rounds 2, 3); #028 Wan2.2
clothing confirmed as V-V cross `character_appearance` (rounds 1–3); #002
Wan2.1 shirt and sofa dual-labeled and confirmed in rounds 1 and 3 (round 2
attributed the shirt to the wrong shot and the reviewer rejected it).

Recall against the audit (`analysis/round3_audit_recall.json`, manual
matching): 17 of 41 audit-reported v1 misses on the 14 cases were reported and
confirmed in round 3 — transitions 3/6, cross-shot 6/14, V-L 5/8, within-shot
3/13. Still missed: several face-identity changes (#069 protagonist, #047),
within-shot morphs (#069 jacket, #068 woman→man, #032 oven, #165 smeared
face), some frame-0 flashes, near-duplicate non-adjacent shots.

Precision: not measured systematically. Spot checks: the round-3 StoryMem
#014 finding (peach high neck in Shots 1/3 vs deep V-neck in Shot2) is real;
round-1 "unintended cut" in StoryMem #014 Shot4 was subject motion (false
positive, fixed by the cut-vs-motion rule); setting candidates on StoryMem
#014 were rejected by the reviewer in rounds 2 and 3.

Stability: repeated runs differ (e.g. #028 Wan2.2 V-L 90.00 / 50.63 / 100.00
across rounds with changing prompts; #068 transition failure found in round 2
but not round 3). Luna/low with up to 48 images is the main source; one run per
case is noisy.

Repair loop: 6 repair rounds over 96 calls (discovery 1 in #068 round 2, 1 in
#015, 1 in #047 Wan2.1, 2 in #068 round 3; scoring 1 in #028 Wan2.2 round 1);
all passed.

Cost (standard GPT-6 Luna API estimate, USD 0.10/M uncached input, 0.01/M
cached input as a subset of input, 0.50/M output; not a bill): round 1 19
calls 836,735 input (2,595 cached) / 24,373 output USD 0.095626; round 2 31
calls 1,746,490 (194,073) / 50,257 USD 0.182311; round 3 46 calls 2,909,149
(674,506) / 89,192 USD 0.274805; total 96 calls 5,492,374 input (871,174
cached) / 163,822 output, USD 0.552743. Against v1 evaluation stages on the
same 14 cases (41 calls, 2,074,616 input, 23,889 output, USD 0.219406), v2
costs 46 calls and USD 0.274805 (+25%), with 3.7× output tokens. The visual
audit used Claude subagents of the working session (not the project API).

## 5. Limitations and next steps

- v2 scores are not comparable with the 1,000 v1 scores; a v2 benchmark needs
  a full from-registry rerun of discovery/review/scoring (no GPU needed).
- Within-shot defects and face identity drift remain under-detected by
  Luna/low. Options to test (not adopted; model settings unchanged): medium
  reasoning for discovery, two independent discovery runs merged before
  review, or per-character crop sheets from the existing ledger boxes.
- Six keyframes per shot still miss short events.
- Audit and recall matching are agent/assistant judgments, not human labels.

## Files

- `analysis/`: census mapping script and outputs, audit JSONs/packets/sheet
  scripts, round-3 recall matching.
- `validation_round{1,2,3}/`: per-case discovery/review/scoring outputs with
  exact prompts, inputs, source hashes, usage and repair audits.
- `source_before/`: pre-change snapshots of edited runners, tests, prompts
  and the discovery skill.
