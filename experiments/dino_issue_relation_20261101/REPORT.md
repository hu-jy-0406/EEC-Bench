# Does a low DINO score go with confirmed appearance issues? (2026-11-01)

Offline check, requested by the owner before deciding whether `dino_appearance` stays in the detector ledger that is sent to the V-L / V-V detection models. 0 model calls, 0 tokens, USD 0. (Writing this report used a Claude Code subagent, 222,635 tokens of Claude plan usage; no API bill applies.)

## Question

The ledger carries, per entity, a DINOv2 appearance score: the mean cosine of the entity's crops to their shot-balanced centroid. Does a lower score go with a review-confirmed appearance issue on that entity, and does it point to which entity in a video has the issue?

## Data and labels

- Runs: `vl_vv_multimodel_first200_run02` and `vl_vv_multimodel_first200_run02_b`, 1,000 runs (200 episodes x 5 generation models), v1 chain (discovery v1 -> review v1 -> scoring v2, Luna/low).
- Units: 21,898 ledger entities with a non-null DINO score (of 23,835); 9,035 are observed in two or more shots.
- Main label: the entity's ledger ID is in `entity_ids` of a review-confirmed V-V appearance issue (within- or cross-shot). Entities with only a confirmed V-L appearance issue are excluded. Broader label: any confirmed appearance issue (V-L or V-V).
- AUC = P(DINO of a positive < DINO of a negative); 0.5 is chance. 95% CI: cluster bootstrap over runs, 500 resamples.
- Scripts: `collect.py` (-> `out/entities.json`, `out/vocab.json`), `analyze.py` (-> `out/results.json`), `controls.py` (-> `out/controls.json`). Run on an existing allocation's node with one CPU.

## Results (main label)

| Comparison | n | Positives | AUC [95% CI] |
|---|---:|---:|---:|
| All entities | 21,111 | 393 | 0.787 [0.767, 0.807] |
| Entities in >=2 shots | 8,417 | 388 | 0.628 [0.597, 0.658] |
| Characters, >=2 shots | 2,023 | 250 | 0.589 [0.551, 0.627] |
| Places, >=2 shots | 1,183 | 24 | 0.621 [0.492, 0.749] |
| Objects, >=2 shots | 5,013 | 113 | 0.605 [0.553, 0.656] |
| Unbound, >=2 shots | 198 | 1 | n/a |

Controls (entities in >=2 shots; pairs compared only inside a group):

| Pairs compared within | Pairs | AUC |
|---|---:|---:|
| Same run and category (one video) | 825 | 0.515 |
| Same shot count | 721,054 | 0.568 |
| Same shot count and category | 283,156 | 0.566 |
| Same model and category | 188,611 | 0.551 |
| Same episode and category, across models | 5,691 | 0.606 |
| Same contract entity, same episode, across models | 1,120 | 0.613 |

Within one video by category: characters 0.489 (268 pairs), objects 0.528 (549), places 0.5 (8).

Other numbers (entities in >=2 shots):

- Lowest DINO decile: 8.3% have a confirmed V-V appearance issue vs a 4.6% base rate (characters 19.2% vs 12.4%).
- Mean DINO: positives 0.720, negatives 0.770.
- Confirmed vs rejected V-V appearance candidates: mean entity DINO 0.722 (405 confirmed) vs 0.762 (55 rejected); P(rejected lower than confirmed) = 0.409.
- Broader label: >=2 shots 0.572 [0.550, 0.592]; characters 0.519 [0.493, 0.546]; same run and category 0.528 (2,233 pairs).

Per generation model (entities in >=2 shots):

| Model | Entities | Mean DINO | Confirmed V-V appearance rate |
|---|---:|---:|---:|
| wan21 | 1,720 | 0.717 | 9.7% |
| wan22 | 1,725 | 0.726 | 7.9% |
| holocine | 1,992 | 0.759 | 0.4% |
| storymem | 1,831 | 0.769 | 1.1% |
| cinetrans | 1,767 | 0.863 | 3.2% |

## Interpretation

- The overall AUC is mostly a shot-count effect: single-shot entities have high DINO and cannot have cross-shot issues. In >=2 shots it is 0.628, and about 0.57 within the same shot count.
- Across videos there is a modest signal: for the same contract entity in the same episode, the video with a confirmed issue has the lower DINO in 61% of pairs.
- Within one video, among entities of the same category, the score is at chance (0.515; characters 0.489). In these runs it does not show which entity in a video has the issue, which is what issue detection needs.
- Per-model means do not order models by issue rate (cinetrans has the highest DINO but a higher rate than holocine and storymem).
- The review difference is small and rests on 55 rejected candidates.

## Caveats

- Labels are Luna/low pipeline verdicts, not human annotation. A negative means "no confirmed issue", which includes issues the chain missed.
- Partly circular: the v1 discovery prompt said "the detector ledger and its DINO values are clues, not proof" and the ledger carried them, so discovery may have favoured low-DINO entities; the association is closer to an upper bound.
- Historical runs: v1 ledger and visual matching, the old worn-item rule, and for the episode-video models (cinetrans, holocine) the old nominal-grid keyframes, so some crops may come from the wrong shot. This is not a test of the current chain (discovery v5 -> review v6 -> scoring v5, matching v2).
