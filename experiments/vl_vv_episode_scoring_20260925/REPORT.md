# VL/VV episode scoring on ten shared episodes

Status: `success` (30/30). Same ten episodes for all three models.

Scores are 0–100 and conditioned on confirmed reviewed issues. Model means are equal-episode averages; no human calibration is claimed.

## Model means

| Model | V-L | V-V within | V-V cross | V-V overall | All-100 counts V-L / within / cross | Luna calls | Tokens | API estimate USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| wan22 | 84.87 | 100.00 | 85.00 | 92.50 | 2 / 10 / 3 | 10 | 25264 | 0.003205 |
| storymem | 92.50 | 98.50 | 100.00 | 99.25 | 6 / 9 / 10 | 10 | 18256 | 0.002178 |
| holocine | 84.95 | 98.50 | 100.00 | 99.25 | 3 / 9 / 10 | 10 | 20682 | 0.002593 |

Total scoring calls: 30; tokens: 64202; standard API estimate: USD 0.007977.
Batch elapsed: 27.74 seconds with at most four concurrent API calls; per-call time is in each `run.json`.

The estimate uses USD 0.10/M uncached input, 0.01/M cached input, and 0.50/M output. It is not an actual bill. A prior schema-rejected smoke call produced no usage; one successful smoke call is separate from these batch totals.

## Per-episode scores

| Model | Episode | V-L | Within | Cross | V-V overall | Confirmed / rejected / uncertain | Unique scored events | USD estimate |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| wan22 | `74Od5-Fmf60_s00006_n4_clean_v2` | 85.00 | 100.00 | 100.00 | 100.00 | 1 / 0 / 0 | 1 | 0.000063 |
| wan22 | `74S1Iw0gJrA_s00006_n4_clean_v2` | 72.25 | 100.00 | 100.00 | 100.00 | 2 / 0 / 0 | 2 | 0.000397 |
| wan22 | `kTAOppBVgsU_s00001_n6_clean_v2` | 85.00 | 100.00 | 85.00 | 92.50 | 2 / 0 / 0 | 2 | 0.000318 |
| wan22 | `7M9pU29bOeY_s00004_n4_clean_v2` | 75.44 | 100.00 | 70.00 | 85.00 | 3 / 0 / 1 | 3 | 0.000500 |
| wan22 | `2hEV6a24yXc_s00017_n8_clean_v3_alt8` | 85.00 | 100.00 | 70.00 | 85.00 | 2 / 0 / 0 | 2 | 0.000349 |
| wan22 | `6kwhPKkHFpA_s00007_n4_clean_v2` | 72.25 | 100.00 | 100.00 | 100.00 | 2 / 0 / 0 | 2 | 0.000371 |
| wan22 | `v9I0QHOiU0Y_s00050_n4_clean_v2` | 100.00 | 100.00 | 85.00 | 92.50 | 1 / 0 / 0 | 1 | 0.000236 |
| wan22 | `KFuxHDKp2oc_s00012_n6_clean_v2` | 88.75 | 100.00 | 85.00 | 92.50 | 2 / 0 / 0 | 2 | 0.000357 |
| wan22 | `tIB4z4uMeNs_s00023_n4_clean_v2` | 100.00 | 100.00 | 85.00 | 92.50 | 1 / 0 / 0 | 1 | 0.000247 |
| wan22 | `MTYQT6fSzaE_s00091_n4_clean_v2` | 85.00 | 100.00 | 70.00 | 85.00 | 2 / 1 / 0 | 2 | 0.000366 |
| storymem | `74Od5-Fmf60_s00006_n4_clean_v2` | 85.00 | 100.00 | 100.00 | 100.00 | 1 / 0 / 0 | 1 | 0.000261 |
| storymem | `74S1Iw0gJrA_s00006_n4_clean_v2` | 100.00 | 100.00 | 100.00 | 100.00 | 0 / 0 / 0 | 0 | 0.000157 |
| storymem | `kTAOppBVgsU_s00001_n6_clean_v2` | 100.00 | 100.00 | 100.00 | 100.00 | 0 / 1 / 0 | 0 | 0.000238 |
| storymem | `7M9pU29bOeY_s00004_n4_clean_v2` | 100.00 | 85.00 | 100.00 | 92.50 | 1 / 0 / 0 | 1 | 0.000235 |
| storymem | `2hEV6a24yXc_s00017_n8_clean_v3_alt8` | 85.00 | 100.00 | 100.00 | 100.00 | 1 / 0 / 0 | 1 | 0.000247 |
| storymem | `6kwhPKkHFpA_s00007_n4_clean_v2` | 100.00 | 100.00 | 100.00 | 100.00 | 0 / 0 / 0 | 0 | 0.000157 |
| storymem | `v9I0QHOiU0Y_s00050_n4_clean_v2` | 70.00 | 100.00 | 100.00 | 100.00 | 1 / 0 / 0 | 1 | 0.000255 |
| storymem | `KFuxHDKp2oc_s00012_n6_clean_v2` | 100.00 | 100.00 | 100.00 | 100.00 | 0 / 0 / 0 | 0 | 0.000157 |
| storymem | `tIB4z4uMeNs_s00023_n4_clean_v2` | 100.00 | 100.00 | 100.00 | 100.00 | 0 / 0 / 0 | 0 | 0.000157 |
| storymem | `MTYQT6fSzaE_s00091_n4_clean_v2` | 85.00 | 100.00 | 100.00 | 100.00 | 1 / 0 / 1 | 1 | 0.000316 |
| holocine | `74Od5-Fmf60_s00006_n4_clean_v2` | 72.25 | 100.00 | 100.00 | 100.00 | 2 / 0 / 0 | 2 | 0.000344 |
| holocine | `74S1Iw0gJrA_s00006_n4_clean_v2` | 85.00 | 100.00 | 100.00 | 100.00 | 1 / 0 / 0 | 1 | 0.000220 |
| holocine | `kTAOppBVgsU_s00001_n6_clean_v2` | 95.00 | 100.00 | 100.00 | 100.00 | 1 / 0 / 0 | 1 | 0.000261 |
| holocine | `7M9pU29bOeY_s00004_n4_clean_v2` | 70.00 | 100.00 | 100.00 | 100.00 | 1 / 0 / 0 | 1 | 0.000253 |
| holocine | `2hEV6a24yXc_s00017_n8_clean_v3_alt8` | 85.00 | 85.00 | 100.00 | 92.50 | 2 / 0 / 0 | 2 | 0.000300 |
| holocine | `6kwhPKkHFpA_s00007_n4_clean_v2` | 70.00 | 100.00 | 100.00 | 100.00 | 1 / 0 / 0 | 1 | 0.000224 |
| holocine | `v9I0QHOiU0Y_s00050_n4_clean_v2` | 100.00 | 100.00 | 100.00 | 100.00 | 0 / 0 / 0 | 0 | 0.000157 |
| holocine | `KFuxHDKp2oc_s00012_n6_clean_v2` | 100.00 | 100.00 | 100.00 | 100.00 | 0 / 2 / 0 | 0 | 0.000313 |
| holocine | `tIB4z4uMeNs_s00023_n4_clean_v2` | 100.00 | 100.00 | 100.00 | 100.00 | 0 / 0 / 0 | 0 | 0.000157 |
| holocine | `MTYQT6fSzaE_s00091_n4_clean_v2` | 72.25 | 100.00 | 100.00 | 100.00 | 2 / 0 / 0 | 2 | 0.000364 |

The scorer does not inspect pixels or the original prompt. Zero confirmed reviewed issues yields 100 for that dimension under this protocol; it does not establish perfect generation. The rubric and formula are documented in `EECBench/docs/vl-vv-episode-scoring-v1.md`.
