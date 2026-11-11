# Per-shot score formula, offline rescoring of the first-200 rerun (2026-11-09)

## Owner request

2026-11-09 (Dubai evening): the current score range is low; adjust the scoring formula so the range is roughly
level with the earliest run, keep the formula simple and reasonable without an obvious tuned hyperparameter,
combine severity and confidence of confirmed issues, take uncertain issues into account appropriately
(an uncertain verdict itself carries confidence information), and rescore this run's results with it.

## Why the scores dropped

The earliest first-200 run (`vl_vv_multimodel_first200_run02` + `_b`, chain v1, scoring v2) used the same
weights and the same product rule `100 x prod(1 - D/100)` as scoring v6. The difference is the number of issues
found: confirmed issues per video were V-L 1.1-2.9 and cross-shot 0.04-0.86 then, V-L 3.5-36.1 and cross-shot
0.5-4.4 now (`vl_vv_full_first200_v3_20261109`). The product saturates with many issues:

- 268 of 1,000 videos have V-L below 1 under v6 (CineTrans mean 1.58), so further issues no longer change
  the score and the low end cannot be told apart.
- Longer episodes have more chances for issues and are penalized for length: v6 UEC means 57.65 / 51.43 /
  44.67 for 4 / 6 / 8 shots (the earliest run 83.38 / 80.72 / 79.66).

## Formula (assistant choice; owner made it the default, 2026-11-09)

Per issue, unchanged from scoring v6: `D = w(severity) x c`

- `w` = 10 / 25 / 50 / 80 for minor / moderate / major / critical (penalty rubric v2, used since the earliest run);
- `c` is one confidence ladder over the verifier's output: 1 / 0.75 / 0.5 for a confirmed issue with confidence
  high / medium / low, 0.25 for an uncertain issue (the rung below a low-confidence confirmation), 0 for rejected.
  The verifier's confidence inside an uncertain verdict is not used, as in v6.

Per dimension (V-L, V-V within-shot, V-V cross-shot), with `S` = number of shots of the episode:

    s = 100 x exp(-sum(D) / (100 x S))

UEC = mean of the three dimensions, V-V = mean of within and cross, as in v6. A dimension without deducting issues
scores 100.

Reading: `sum(D) / S` is the expected deduction per shot; one full deduction (100 points) per shot gives 100/e,
about 37. For small deductions `prod(1 - D/100)` of v6 is about `exp(-sum(D)/100)`, so the change is to divide
the summed deduction by the number of shots; there is no new constant. A single confirmed moderate issue
(D = 25) gives 93.94 / 95.92 / 96.92 in a 4 / 6 / 8-shot episode (v6: 75 in any episode).

Choice basis: per-shot normalization removes the length penalty. Among parameter-free per-shot forms checked
(`candidates.py`: per-shot geometric mean of the v6 product, per-shot exponential, per-shot hyperbolic
`100/(1+x)`), the exponential is the simplest to write (one sum) and its per-video distribution is closest to the
earliest run's. All three give the same model order. The earliest range was a selection criterion at the
owner's request; the model order was not.

## Result (1,000 videos, zero model calls)

| model | V-L | within | cross | V-V | UEC | v6 UEC | earliest UEC |
|---|---|---|---|---|---|---|---|
| StoryMem | 82.48 | 96.99 | 94.19 | 95.59 | 91.22 | 68.27 | 89.41 |
| HoloCine | 68.04 | 97.45 | 97.21 | 97.33 | 87.57 | 66.80 | 85.86 |
| Wan2.2 | 83.09 | 97.64 | 77.78 | 87.71 | 86.17 | 54.02 | 83.42 |
| Wan2.1 | 61.44 | 96.72 | 73.49 | 85.10 | 77.22 | 40.15 | 76.48 |
| CineTrans-DiT | 21.95 | 93.82 | 87.05 | 90.43 | 67.61 | 43.18 | 75.87 |
| all | 63.40 | 96.52 | 85.94 | 91.23 | 81.96 | 54.49 | 82.21 |

The earliest run has no UEC field; its UEC here is the mean of its three dimensions.

Per-video UEC percentiles (p5 / p25 / p50 / p75 / p95): new 61.18 / 73.18 / 84.24 / 91.05 / 97.98; earliest
62.63 / 75.00 / 83.33 / 91.67 / 100.00; v6 25.37 / 39.07 / 53.28 / 68.75 / 91.67. UEC by shots: 81.96 / 82.10 /
81.51 for 4 / 6 / 8 shots. V-L below 1: 5 videos (v6: 268).

Order by UEC: StoryMem > HoloCine > Wan2.2 > Wan2.1 > CineTrans, the earliest run's order (v6 had CineTrans above
Wan2.1). Adjacent differences, paired bootstrap over the 200 episodes (95%): StoryMem - HoloCine 3.65 [2.39, 4.91];
HoloCine - Wan2.2 1.40 [-0.00, 2.82] (not separable); Wan2.2 - Wan2.1 8.96 [7.77, 10.10]; Wan2.1 - CineTrans 9.61
[8.31, 10.94]. The CineTrans / Wan2.1 swap comes from saturation: under v6 CineTrans V-L was near 0 whatever its
issue count (36.1 confirmed V-L issues per video against 9.3 for Wan2.1), so only cross-shot differences counted.
The intervals cover episode sampling only; each video was evaluated once.

## Limits

- Offline reaggregation of the v6 per-issue deductions (recomputed from severity and confidence and checked
  against each `adjusted_deduction`); no severity or verification call was repeated.
- Not human-calibrated. The score level is set to be comparable with the earliest run, not validated as absolute
  quality.
- The rerun's stored `episode_scoring/result.json` files still hold the product scores; use `rescored.jsonl`.

## Files

`collect.py` (units of the rerun -> `units.jsonl`), `candidates.py` (forms compared), `rescore.py` (this rule ->
`rescored.jsonl` per video with new and v6 scores, `summary.json`).

## Applied as the pipeline default (owner: "设为默认并改论文", 2026-11-09 ~23:05 Dubai)

- Scoring v6 changed in place (as for Q17): `run_vl_vv_branch_scoring.py` reads S from the case's
  `raw_manifest.json` (added to the hashed sources), `per_shot_score()` computes `100 x exp(-sum(D) / (100 x S))`
  in Decimal, and results record `scoring_rule.aggregation = per_shot_exp`, `scoring_rule.shots` and the new
  `bucket_rule`. Severity prompts, schemas, calls, per-issue deductions and statistics are unchanged; chain v5 keeps
  its product. Config `configs/vl-vv-branch-v2.json` gains the text field `scoring.dimension_rule`.
- Tests: v6 scoring expectations updated, one new test (`test_dimension_score_is_per_shot`); VL/VV set 333 passed
  (`tests_after.txt`, compute node of allocation 356507).
- `check_pipeline.py`: the live pipeline code recomputed all 1,000 rerun videos from their stored reviews and
  severity assessments; scores equal `rescored.jsonl` on every video, deductions and unspecified-subject statistics
  equal the stored results (0 mismatches).
- Pre-change copies `source_before/` (SHA256SUMS), after `SHA256SUMS_after`. Docs: spec section 1 and 5,
  AGENTS.md, research-log.
