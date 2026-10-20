# Ten-episode Wan2.2 / StoryMem / HoloCine pipeline run

Status: `success`. Each model uses the same ten selected episodes.

Candidate counts are issue-discovery outputs; confirmed/rejected/uncertain are reviewer judgments. These are not calibrated final scores.

## Model summary

| Model | Pipeline cases | Entities | V-L candidates | V-V within | V-V cross | Confirmed | Rejected | Uncertain | Luna calls | Luna tokens | API estimate (USD) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| wan22 | 10/10 | 259 | 12 | 0 | 8 | 18 | 1 | 1 | 142 | 2863440 | 0.328097 |
| storymem | 10/10 | 234 | 6 | 1 | 0 | 5 | 1 | 1 | 147 | 2775548 | 0.317730 |
| holocine | 10/10 | 255 | 9 | 2 | 1 | 10 | 2 | 0 | 174 | 2991935 | 0.354992 |

## Runtime and token accounting

Times below sum per-case elapsed seconds; model cases ran concurrently across the ten GPUs. Recovery time is reported separately and is already reflected in each recovered case’s total pipeline elapsed time. Luna input includes cached input, reported separately as a subset. API USD is a standard-price estimate, not a billing record.

| Model | Frontend (h:m:s, summed) | Find issues (h:m:s, summed) | Review (h:m:s, summed) | Recovery (h:m:s, summed) | Uncached input | Cached input | Output | API errors |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| wan22 | 0:52:46 | 0:01:55 | 0:01:52 | 0:01:01 | 2759058 | 0 | 104382 | 0 |
| storymem | 0:31:16 | 0:01:34 | 0:00:50 | 0:00:00 | 2667696 | 6052 | 101800 | 0 |
| holocine | 1:43:11 | 0:01:43 | 0:01:18 | 0:05:30 | 2809436 | 35105 | 147394 | 0 |

## Luna API usage by stage

| Model | Stage | Calls | Total tokens | Estimated USD |
|---|---|---:|---:|---:|
| wan22 | entity_clustering | 60 | 356073 | 0.049055 |
| wan22 | prompt_binding | 48 | 395259 | 0.054160 |
| wan22 | global_matching | 14 | 615773 | 0.069364 |
| wan22 | issue_discovery | 10 | 1159028 | 0.118993 |
| wan22 | issue_review | 10 | 337307 | 0.036525 |
| wan22 | other | 0 | 0 | 0.000000 |
| storymem | entity_clustering | 69 | 414276 | 0.056686 |
| storymem | prompt_binding | 48 | 389123 | 0.053278 |
| storymem | global_matching | 14 | 607867 | 0.068314 |
| storymem | issue_discovery | 10 | 1155520 | 0.117520 |
| storymem | issue_review | 6 | 208762 | 0.021933 |
| storymem | other | 0 | 0 | 0.000000 |
| holocine | entity_clustering | 96 | 610552 | 0.088967 |
| holocine | prompt_binding | 48 | 399899 | 0.055616 |
| holocine | global_matching | 12 | 532751 | 0.061329 |
| holocine | issue_discovery | 10 | 1171941 | 0.119765 |
| holocine | issue_review | 8 | 276792 | 0.029315 |
| holocine | other | 0 | 0 | 0.000000 |

## Per-episode details

| Model | Episode | Case status | Frontend s | Find issues s | Review s | Recovery s | V-L | V-V within | V-V cross | Confirmed / rejected / uncertain | Luna calls | API estimate (USD) |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| wan22 | `74Od5-Fmf60_s00006_n4_clean_v2` | success | 1572.0 | 11.0 | 7.4 | 61.7 | 1 | 0 | 0 | 1 / 0 / 0 | 14 | 0.034400 |
| wan22 | `74S1Iw0gJrA_s00006_n4_clean_v2` | success | 134.8 | 10.2 | 10.5 | 0.0 | 2 | 0 | 0 | 2 / 0 / 0 | 12 | 0.017861 |
| wan22 | `kTAOppBVgsU_s00001_n6_clean_v2` | success | 214.9 | 10.3 | 11.7 | 0.1 | 1 | 0 | 1 | 2 / 0 / 0 | 18 | 0.050930 |
| wan22 | `7M9pU29bOeY_s00004_n4_clean_v2` | success | 166.9 | 13.3 | 19.7 | 0.1 | 2 | 0 | 2 | 3 / 0 / 1 | 13 | 0.025888 |
| wan22 | `2hEV6a24yXc_s00017_n8_clean_v3_alt8` | success | 229.9 | 14.8 | 11.2 | 0.1 | 1 | 0 | 1 | 2 / 0 / 0 | 20 | 0.064321 |
| wan22 | `6kwhPKkHFpA_s00007_n4_clean_v2` | success | 163.4 | 12.0 | 12.6 | 0.0 | 2 | 0 | 0 | 2 / 0 / 0 | 12 | 0.024223 |
| wan22 | `v9I0QHOiU0Y_s00050_n4_clean_v2` | success | 182.9 | 10.4 | 8.6 | 0.0 | 0 | 0 | 1 | 1 / 0 / 0 | 13 | 0.030717 |
| wan22 | `KFuxHDKp2oc_s00012_n6_clean_v2` | success | 167.4 | 11.1 | 11.1 | 0.0 | 1 | 0 | 1 | 2 / 0 / 0 | 15 | 0.031013 |
| wan22 | `tIB4z4uMeNs_s00023_n4_clean_v2` | success | 176.2 | 9.3 | 8.3 | 0.0 | 0 | 0 | 1 | 1 / 0 / 0 | 13 | 0.026960 |
| wan22 | `MTYQT6fSzaE_s00091_n4_clean_v2` | success | 157.9 | 13.1 | 11.9 | 0.1 | 2 | 0 | 1 | 2 / 1 / 0 | 12 | 0.021785 |
| storymem | `74Od5-Fmf60_s00006_n4_clean_v2` | success | 200.0 | 8.6 | 8.3 | 0.0 | 1 | 0 | 0 | 1 / 0 / 0 | 14 | 0.035519 |
| storymem | `74S1Iw0gJrA_s00006_n4_clean_v2` | success | 146.7 | 10.5 | 0.2 | 0.0 | 0 | 0 | 0 | 0 / 0 / 0 | 10 | 0.017035 |
| storymem | `kTAOppBVgsU_s00001_n6_clean_v2` | success | 274.4 | 10.2 | 7.7 | 0.0 | 1 | 0 | 0 | 0 / 1 / 0 | 25 | 0.056895 |
| storymem | `7M9pU29bOeY_s00004_n4_clean_v2` | success | 142.5 | 4.7 | 5.8 | 0.0 | 0 | 1 | 0 | 1 / 0 / 0 | 11 | 0.021631 |
| storymem | `2hEV6a24yXc_s00017_n8_clean_v3_alt8` | success | 233.0 | 11.1 | 8.4 | 0.0 | 1 | 0 | 0 | 1 / 0 / 0 | 22 | 0.059002 |
| storymem | `6kwhPKkHFpA_s00007_n4_clean_v2` | success | 173.6 | 8.6 | 0.2 | 0.0 | 0 | 0 | 0 | 0 / 0 / 0 | 12 | 0.023421 |
| storymem | `v9I0QHOiU0Y_s00050_n4_clean_v2` | success | 177.7 | 8.8 | 7.4 | 0.0 | 1 | 0 | 0 | 1 / 0 / 0 | 12 | 0.027159 |
| storymem | `KFuxHDKp2oc_s00012_n6_clean_v2` | success | 185.3 | 14.6 | 0.2 | 0.0 | 0 | 0 | 0 | 0 / 0 / 0 | 16 | 0.031071 |
| storymem | `tIB4z4uMeNs_s00023_n4_clean_v2` | success | 194.1 | 7.9 | 0.2 | 0.0 | 0 | 0 | 0 | 0 / 0 / 0 | 14 | 0.026272 |
| storymem | `MTYQT6fSzaE_s00091_n4_clean_v2` | success | 149.8 | 9.9 | 12.2 | 0.0 | 2 | 0 | 0 | 1 / 0 / 1 | 11 | 0.019726 |
| holocine | `74Od5-Fmf60_s00006_n4_clean_v2` | success | 226.1 | 14.3 | 9.1 | 0.0 | 2 | 0 | 0 | 2 / 0 / 0 | 15 | 0.038051 |
| holocine | `74S1Iw0gJrA_s00006_n4_clean_v2` | success | 141.1 | 8.7 | 4.7 | 0.0 | 1 | 0 | 0 | 1 / 0 / 0 | 11 | 0.017656 |
| holocine | `kTAOppBVgsU_s00001_n6_clean_v2` | success | 1901.6 | 11.7 | 9.0 | 187.4 | 1 | 0 | 0 | 1 / 0 / 0 | 57 | 0.093699 |
| holocine | `7M9pU29bOeY_s00004_n4_clean_v2` | success | 141.9 | 8.9 | 4.8 | 0.1 | 1 | 0 | 0 | 1 / 0 / 0 | 11 | 0.019961 |
| holocine | `2hEV6a24yXc_s00017_n8_clean_v3_alt8` | success | 1391.7 | 12.7 | 17.6 | 83.5 | 1 | 1 | 0 | 2 / 0 / 0 | 21 | 0.062823 |
| holocine | `6kwhPKkHFpA_s00007_n4_clean_v2` | success | 1716.5 | 9.3 | 8.4 | 59.3 | 1 | 0 | 0 | 1 / 0 / 0 | 11 | 0.024591 |
| holocine | `v9I0QHOiU0Y_s00050_n4_clean_v2` | success | 177.0 | 6.5 | 0.2 | 0.0 | 0 | 0 | 0 | 0 / 0 / 0 | 11 | 0.022682 |
| holocine | `KFuxHDKp2oc_s00012_n6_clean_v2` | success | 164.1 | 11.9 | 17.2 | 0.0 | 0 | 1 | 1 | 0 / 2 / 0 | 16 | 0.032143 |
| holocine | `tIB4z4uMeNs_s00023_n4_clean_v2` | success | 182.2 | 11.0 | 0.2 | 0.0 | 0 | 0 | 0 | 0 / 0 / 0 | 10 | 0.021907 |
| holocine | `MTYQT6fSzaE_s00091_n4_clean_v2` | success | 149.6 | 8.9 | 7.3 | 0.0 | 2 | 0 | 0 | 2 / 0 / 0 | 11 | 0.021478 |

## Accounting basis

- Pricing: uncached input USD 0.1/M, cached input USD 0.01/M, output USD 0.5/M; cached input is a subset of input.
- Costs are estimates from successful API response usage; they are not actual billed amounts. Any error event or response with unknown usage is reported separately.
- Detection entity counts and issue/review decisions describe these frozen ten-episode outputs. No severity-weighted score is produced.
