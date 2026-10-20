# Review v3 (true / partly true / false): implementation and validation — 2026-10-06

## Request

The user asked to change the review rule: the reviewer classifies each issue as
true, partly true or false. For a partly true issue it confirms the true part
instead of rejecting the whole claim, so that part counts in the score. The
motivating case is #068 HoloCine I5: the man really vanishes from the elevator
in Shot6, but review v2 rejected the whole claim because its second half
("the woman returns") was false.

## Implementation

The spec is in `docs/vl-vv-issue-review-v3.md`. The new chain is discovery v2 →
review v3 → scoring v4, and it is now the default.

- **Older chains kept:**
  - `--review-protocol v2` keeps review v2 → scoring v3.
  - `--discovery-protocol v1` keeps the historical chain.
- **Flag coverage:** the flags work in `run_vl_vv_pipeline.py`,
  `run_vl_vv_issue_review.py` and the batch controller.
- **Batch directories:** each records its review protocol. Directories created
  before v3 resume with review v2.
- **New and changed files:**
  - `prompts/vl_vv_issue_review_v3.txt` and `schemas/vl-vv-issue-review-v3.schema.json`.
  - `prompts/vl_vv_episode_scoring_v4.txt` and `schemas/vl-vv-episode-scoring-v4.schema.json`.
  - `review_errors_v3`, plus a scored-verdict parameter on the scoring-v3
    functions (v3 output is unchanged).
- **Tests:** `tests/test_vl_vv_partial_review.py` (14 tests). All 72 VL/VV
  tests pass.
- **Snapshots:** pre-change copies are in `source_before/` (SHA256SUMS).

## Validation design

- **Cases:** 24 clip-model runs, i.e. 8 videos (Wan2.1, Wan2.2, StoryMem) ×
  runs a–c from `vl_vv_old_vs_new_20261005` and `vl_vv_v2_results_20261005`.
  This gives 128 labels.
- **Why only clip models:** episode videos (HoloCine, CineTrans), including
  #068, were excluded. Their cases use the retired nominal-grid keyframes.
- **Same candidates for every review:** each run's frozen
  `issue_discovery/result.json` was reviewed three times:
  - `v2_orig`: the original review v2 + scoring v3;
  - `v2_repeat`: a fresh repeat of review v2 + scoring v3 (`runs_v2_repeat/`),
    which measures the reviewer's own run-to-run variance;
  - `v3`: review v3 + scoring v4 (`runs/`).
- **Scripts:** `run_rereview.py`, `launch.sh`, `launch_v2_repeat.sh`, `compare.py`.
- **Results file:** `comparison.json`.
- **Annotations:** A* (verified artifact) and C* (control) come from the two
  earlier experiments. They are assistant judgment, not human labels.

## Results

### Reviewer variance is the same size as the protocol change

Whether a label deducts changed for:

- 17/128 labels between `v2_orig` and `v2_repeat`;
- 19/128 between `v2_orig` and `v3`;
- 18/128 between `v2_repeat` and `v3`.

### Verdicts

| | confirmed | partly confirmed | rejected | uncertain |
| --- | --- | --- | --- | --- |
| v2_orig | 91 | – | 34 | 3 |
| v2_repeat | 98 | – | 29 | 1 |
| v3 | 65 | 27 | 36 | 0 |

### Where the 27 partly true verdicts came from

- **23 were labels `v2_orig` had confirmed.** Their true part is now scored on
  its own:
  - 8 dropped a severity tier (7 major→moderate, 1 moderate→minor);
  - 2 rose a tier;
  - 13 kept their tier.
- **4 were labels `v2_orig` had rejected or marked uncertain.** These are the
  intended effect, and each now deducts for its true part:
  - #014 Wan2.1 run_c I1 V-L: the scarf hides the required peach collar;
  - #069 Wan2.1 run_a I2 V-L: the short figure's required brown trousers turn
    dark in Shot4;
  - #069 Wan2.1 run_c I2 V-L: Shot3's gun is a slim rifle with a yellow strap,
    not the required large angular gun;
  - #069 Wan2.1 run_b I6 V-V: the corridor background differs between Shot1 and
    Shot3.

### Severity drops that removed real content

Some severity drops narrowed claims whose dropped part is in fact a verified
artifact:

- **#002 Wan2.1 face change (A3), runs a and b:** the reviewer treated the face
  change as "cannot be established". Face identity was already a known weak
  spot.
- **#014 Wan2.1 run_a courtyard:** the reviewer narrowed the claim to Shot1 vs
  Shot2 and left out Shot3. Shot1 vs Shot3 is the user's own example.

The current rule lets `unsupported_part` include parts that are merely
unestablished, not only parts that are refuted.

### Verified-artifact and control labels that deduct

| | Artifact labels (of 92) | Control labels (of 6) |
| --- | --- | --- |
| v2_orig | 76 | 0 |
| v2_repeat | 78 | 2 |
| v3 | 70 | 0 |

- **v3 misses (vs both v2 runs):** 7 artifact labels that both v2 runs
  deducted were rejected by v3.
  - All 7 are V-L labels. In every case the issue's V-V label still deducts
    in v3.
  - The v3 reasons say the prompt text does not explicitly require the
    attribute. Examples: Shot3's text only says "blue-gray shirt"; it does not
    fix a chair size.
  - One of them is the #014 Wan2.1 run_b courtyard ("retain continuity"). The
    setting rule, unchanged from v2, says such text does require a compatible
    background.
- **v3 gains (vs both v2 runs):** v3 deducted 3 labels that neither v2 run did.
- **Odd-one-out losses:** v3 is the single disagreeing review for 7 losses (all
  V-L), versus 7 for `v2_orig` (4 V-L) and 3 for `v2_repeat`. With one run per
  protocol this is suggestive, not established.

### Mean bucket scores over the 24 runs

| | V-L | V-V within | V-V cross |
| --- | --- | --- | --- |
| v2_orig | 59.72 | 94.79 | 52.18 |
| v2_repeat | 56.63 | 96.88 | 53.74 |
| v3 | 63.26 | 93.75 | 52.49 |

### Repair rounds

One of the 24 v3 reviews needed one repair round. All 24 scorings passed on the
first call.

## Cost

Review + scoring over 24 runs, using the GPT-6 Luna standard API estimate:
USD 0.10/M uncached input, 0.01/M cached input, 0.50/M output. These are
estimates, not billed amounts.

| | Uncached input | Cached input | Output | USD | USD per video |
| --- | --- | --- | --- | --- | --- |
| v2_orig | 953,560 | 3,584 | 41,256 | 0.116020 | 0.00483 |
| v2_repeat | 951,558 | 0 | 39,354 | 0.114833 | 0.00478 |
| v3 | 978,028 | 49,403 | 49,063 | 0.122828 | 0.00512 |

- Review v3 + scoring v4 cost about 6% more than v2 + v3, mostly from longer
  output.
- This experiment spent USD 0.237661: the v3 batch plus the v2 repeat.
  Discovery was reused and not rerun.

Compute: CPU and API only, in existing allocation 236651 / node270 (checked
load 0.08). No GPU was used and no new allocation was requested.

## Not done / open choices

- **#068 HoloCine I5 not retested.** Its case uses the retired keyframes. A
  retest needs a fresh case from the recorded-cut keyframes (detection on GPU),
  and discovery may not reproduce I5.
- **Possible tightening of partial verdicts (not applied, needs a user
  decision):** require the unsupported part to be refuted by frames or text,
  not merely unestablished. This would stop partial verdicts from lowering the
  severity of real face or background changes the reviewer cannot judge.
- **V-L strictness:** v3 rejected 7 V-L labels that both v2 runs deducted. It
  is not clear whether this comes from the v3 prompt or from reviewer variance.
  Separating the two needs repeated v3 runs.
