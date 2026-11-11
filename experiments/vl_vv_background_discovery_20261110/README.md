# Background-object discovery test (2026-11-10)

Times are Dubai time.

## Owner request

After the missed-issue diagnosis (`../vl_vv_full_first200_v3_20261109/miss_diagnosis/README.md`: most audited
problems of unprompted objects are lost because WeDetect never boxes small background objects, and lower detector
thresholds recover only 2-3 of 9), the owner proposed a dedicated model call for background object discovery in the
entity-discovery stage (also usable as an ablation) and agreed to validate in order ("按照你说的顺序验证"):
1. discovery only on the 20 audited videos: how many of the 19 audited objects does a per-shot call list, and can
   Grounding DINO box them by name (no pipeline change);
2. if good, integrate and compare on these 20 videos, then decide on the full set.

## Step 1 design

- `prompt_discovery_v0.txt` (new, test only): one isolated call per shot; input = that shot's labelled keyframes, its
  prompt text and its own final local entity list; output = objects visible but not registered (name, detector
  query, description, location, frames, whether the shot text names it). Exclusions follow the current entity rules
  (walls/floors/ceilings/ground and the place, worn items not handled, body parts, parts of registered objects).
- `run_discovery.py`: GPT-6 Luna, reasoning low, API transport, 8 parallel calls; no repair loop (a call that fails
  schema validation is reported as failed).
- Grounding DINO (`scripts/gs_grounding_recovery.py`, unchanged, box 0.30 / text 0.25) on the frames each object is
  listed in, then a check of the boxes on the audited objects.

## Step 1 results (2026-11-10 00:52-01:06)

Discovery (`run_discovery.py` -> `runs/`, `summarize_discovery.py` -> `discovery_summary.json`): 100/100 shots, no
failure, mean 4.9 s per call; 112 objects (1.12 per shot), 92 marked not named by the shot text. Usage 100 calls,
356,568 input tokens (0 cached), 24,649 output, USD 0.047981 (GPT-6 Luna standard estimate: 0.10/M uncached input,
0.01/M cached, 0.50/M output; not a bill), plus the smoke call included in these numbers.

Recall on the audit (`../vl_vv_full_first200_v3_20261109/miss_diagnosis`): of the 9 real small objects WeDetect never
boxed, discovery lists 5: light switch (#025), sill plants (#036 Shot4), notice sheet (#047 Shot2), rear-wall shelves
(#047 Shot5; banners not listed), baton (#120). Missed: canopy (#036), side table and towel (#126, nothing listed in
that video), cloth in the paw (#127). Out of scope: the second drone (detected, rejected by clustering) and the TV-wall
screen images (part of a registered entity).

Grounding DINO (unchanged `scripts/gs_grounding_recovery.py`, box 0.30 / text 0.25, allocation 356508 GPU 0
GPU-42c44f03a31e14fb idle in two probes 30 s apart and again just before launch; 298 frames, 564 frame-query pairs,
132.9 s; `evaluate_grounding.py` -> `grounding_summary.json`): 110 of 112 objects get at least one box (101 in every
listed frame), 1.81 boxes per listed frame.
- The five audit objects (`grounding_check/priority_*`): correct tight box for the switch, sill plants and baton; a
  whole-frame box for the notice sheet; shelves boxed in only 2 of 6 frames.
- Random 12 other objects (`sample_check.py`, `grounding_check/sample_*.png`): all 12 are real visible things
  (one may duplicate a registered towel); boxes: 4 correct, 5 with the right box among wrong ones (whole-frame boxes or
  other buildings often score higher), 2 wrong object, 1 unclear.
- Reading: discovery finds about half of the missed small objects at very low cost; Grounding DINO usually has a box
  on the object but often also on other things, so "highest score" selection would be wrong about half the time.
  Integration needs a box-choice step (for example the discovery model picking among drawn candidate boxes).

## Owner decisions for the overnight iteration (2026-11-10 01:26)

- "好的，加一个选框步骤。这一步发现的entity occurence也参与聚类吧": chosen Grounding DINO boxes of discovered objects
  join the WeDetect candidates as input to shot clustering (an explicit extension of the WeDetect-only candidate
  rule, for this test).
- "感觉就按照这个思路调下去就行，我得回去睡觉了…之后就交给你来迭代了", then (answers to four questions): OpenAI API
  budget for the night at most USD 10 (GPT-6 Luna standard estimate), no full 1,000-video rerun; all changes only in
  experiment folders with a frozen code copy (no live pipeline, AGENTS.md or paper change, no commit; the owner
  decides in the morning); also test a V-V-side checklist item for background objects (frontend discovery alone and
  together with the V-V item); recommend adoption only if, on the 20 videos, confirmed issues involving unspecified
  entities at least double and grow by 5 or more, at least 70% of the new ones are real on my check, specified issues
  do not drop noticeably, and the extra cost stays within about USD 10 per 1,000 videos.

## Step 2a: box choice (00:5x-01:2x)

`prompt_boxchoice_v0.txt`, `run_boxchoice.py` (keyframes with candidates drawn and labelled <object>-<n>; one isolated
GPT-6 Luna low call per shot; checked choices, one retry on errors). 52 shots, 110 objects, 536 object-frames: 336
boxes chosen, 200 "none"; 1 retry, no remaining error. 53 calls, 165,591 input tokens (0 cached), 29,140 output,
USD 0.031129 (standard estimate). Smoke check (#047 Shot6): whole-frame boxes avoided; two discovered objects got the
same plate box (a duplicate that clustering can merge).

## Step 2b: arms on the 20 audited videos (design)

- Frozen code: `code/EECBench` = live configs, prompts, schemas, scripts, skills and tests at 01:26 (`SHA256SUMS_code_frozen`,
  symlinks to the live experiments, eval, models, third_party, data, exports); `code_vv/EECBench` = the same plus two
  V-V checklist items in `configs/vl-vv-branch-v2.json` (W8 "Background objects inside the shot", X10 "Background
  objects of a shared view"; schemas regenerated with its own `build_vl_vv_branch_schemas.py`; 19 item calls instead of 17).
- `build_aug_detections.py` -> `aug_detections/<task>`: the original WeDetect detections plus the 336 chosen Grounding
  DINO boxes (new ids, label = discovered name, provenance fields); originals unchanged; the clustering loader accepts them.
- `run_arms.py`: A = original detections, B = augmented detections; both from fresh shot clustering through scoring
  (detect stage on GPUs of 356508, one worker per GPU); C = B's case with the code_vv V-V stages; D = A's case with the
  code_vv V-V stages. `compare_arms.py` -> `arms_summary.json`.

## Step 2b results, round 1 (01:29-02:18)

All 80 arm runs succeeded (A, B: 01:29-02:10 on 356508 GPUs 0-3, about 3 min per video; C, D: 02:11-02:18).
`compare_arms.py` -> `arms_summary.json` (20 videos each):

| arm | confirmed V-V | with unspecified subject | specified only | ledger ge (in 2+ shots) | USD (standard estimate) |
|---|---|---|---|---|---|
| A fresh baseline | 58 | 0 | 58 | 33 (5) | 1.235586 |
| B + background discovery | 60 | 0 | 60 | 70 (7) | 1.254663 |
| C = B + W8/X10 | 74 | 4 | 70 | 70 (7) | 0.863293 (V-V stages only) |
| D = A + W8/X10 | 69 | 3 | 66 | 33 (5) | 0.872932 (V-V stages only) |

- Discovery alone puts the objects into the ledger (ge 33 -> 70) but the V-V detector still reports none of them.
- W8/X10 add a few: C confirms 2 audit findings (#036 sill plants, #055 furnishings behind the woman) plus #167
  window and #078 roof vent; D confirms the same 2 audit findings and a #036 toy popping in and out.
- Bottleneck is detection, not verification: unspecified candidates C 7 (4 confirmed, 3 rejected), D 4 (3 confirmed).
  W8 produced 5 and X10 8 issues in all 20 videos, mostly about specified entities; the ledger already tells the
  detector that, for example, the #025 wall switch has boxes only in Shot2, but X10 did not check the Shot4 return view.
- Criteria not met (needs at least +5 over A). Round 2: code_vv2 rewrites W8/X10 to use the ledger as a checklist
  (entities boxed in only some keyframes / recorded in only some shots, then the same for unledgered background objects);
  arms C2 (on B) and D2 (on A).

## Round 2 (02:25-02:32): ledger-driven W8/X10

| arm | confirmed V-V | with unspecified subject | USD (V-V stages only) |
|---|---|---|---|
| C2 = B + W8/X10 v2 | 80 | 2 (#055 furnishings, #078 roof vent) | 0.429185 |
| D2 = A + W8/X10 v2 | 72 | 0 | 0.415762 |

Asking the per-item calls to walk the ledger did not help (C 4 -> C2 2, D 3 -> D2 0; the same prompt family gives 4 or 2,
so run-to-run variation is large). One call that looks at every keyframe of the episode does not compare small objects
one by one at reasoning low, while the per-shot discovery call sees them well.

## Round 3 (02:4x-): object continuity check (OCC)

`prompt_occ_v0.txt`, `run_occ.py`: per video one isolated call over all keyframes plus one reference crop per object
entity (ledger pb entities whose contract label is object and every ge entity, labels treated alike), checking each
object inside its shots and in other shots of the same view; problems are checked (ids, frames, scope; one retry),
mapped to V-V subcategories, appended as candidates to the host arm's own V-V detection (entity records added from the
ledger with their labels), then V-V review and scoring (code_vv). Arms E (host B) and F (host A). Smoke (#025, E): 2
candidates (door opening by itself in Shot3: confirmed; ornament appearing on a shelf: rejected); no wall-switch
problem; one call 13,569 input / 386 output tokens.

## Round 3 results and overall conclusion (02:5x)

| arm | what | confirmed V-V | with unspecified subject | new-call USD |
|---|---|---|---|---|
| A | fresh baseline | 58 | 0 | 1.235586 |
| B | + frontend discovery (ledger ge 33 -> 70) | 60 | 0 | 1.254663 |
| C | B + W8/X10 | 74 | 4 | 0.863293 |
| D | A + W8/X10 | 69 | 3 | 0.872932 |
| C2 | B + ledger-driven W8/X10 | 80 | 2 | 0.429185 |
| D2 | A + ledger-driven W8/X10 | 72 | 0 | 0.415762 |
| E | B + object continuity check (low) | 78 | 0 | 0.237048 |
| F | A + object continuity check (low) | 68 | 0 | 0.217027 |
| E2 | B + object continuity check (medium) | 76 | 1 | 0.262223 |

(C-F and C2, D2, E2 rerun only the V-V stages on the host arm's case; A/B include the whole pipeline.)

- Object continuity check: of 76 (E) / 81 (F) / 86 (E2) reported problems only 2 / 0 / 2 concern unspecified
  entities; the rest are specified objects, of which the verifier rejects about 80% (E: 11 confirmed, 62 rejected).
  At medium it finds the audit's clear #078 TV cabinet change (verdict uncertain) and a #003 teapot missing in Shot6
  (confirmed).
- No variant meets the owner's bar (+5 and at least double over A): the best (C) has 4, of which 2 match audit
  findings (#036 sill plants, #055 furnishings).
- Total overnight usage (`usage_total.json`): 3,664 calls, 93,763,005 input tokens (51,529,939 cached), 2,256,448
  output, USD 5.86683 (GPT-6 Luna standard estimate; not a bill) of the USD 10 budget. GPUs: 356508 GPUs 0-3,
  01:29-02:10 (each probed idle twice before use); at 02:5x they were in use by another user's job started about 02:19,
  after ours; no process of this experiment remains.
- Reading: frontend discovery works as a mechanism (cheap, boxes checked by the box choice, ledger more complete) but
  does not raise confirmed issues of unprompted objects; every V-V-side variant adds at most a few, while specified
  objects keep most of the reported and confirmed problems. With GPT-6 Luna as evaluator, consistency issues of
  unprompted objects stay rare; the Claude audit's subtler findings (17 of 19 "likely") are mostly not reproduced.
  Whether those audit findings are real needs a human check. Nothing was adopted; live pipeline unchanged.
