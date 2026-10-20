# Study3 final integrated fresh evaluation

Fresh WeDetect/independent clustering, geometry, motion, identity/registration, relation consistency, displacement, appearance, binding and four-dimensional prompt alignment from all18 original frames. Normal narrative and registry/79claims frozen before execution. No prior detector/geometry/judgment reuse; pretrained weights and text reference reused.

Pipeline wall time: 1431.606s (23.86 min). Outer launch including immediate GPU guard/setup: 1433.193s.
Model calls: 54 directories / 54 recorded requests. Total tokens: 1,308,446; standard API equivalent USD 15.188604 (not a bill).
Input 1,249,852, including cached-read 26,624 and cache-write 0; output 58,594. Cached tokens are not counted twice.
Recorded Astra pricing verified 2026-09-20: USD/M uncached10/cache-read1/cache-write12.5/output50; input>272000: input-side x2/output x1.5; not billed

One initial binding response was rejected by unchanged witness validation; a same-input retry succeeded. The initial attempt is archived, both calls are included in tokens/cost, and elapsed time includes the recovery gap. Successful stages come only from this same fresh run. Binding stage seconds sum the initial stage and retry model call, excluding retry local postprocessing; see execution.json and recovery_runtime.json.

## Stage timing and usage

| Stage | Seconds | Tokens | API equivalent USD |
|---|---:|---:|---:|
| detection_and_clustering | 71.569 | 46429 | 0.516050 |
| geocalib | 42.549 | 0 | 0.000000 |
| prepare_shot_inputs | 0.267 | 0 | 0.000000 |
| pi3x_shot1 | 47.141 | 0 | 0.000000 |
| boxer_shot1 | 13.818 | 0 | 0.000000 |
| pi3x_shot3 | 22.702 | 0 | 0.000000 |
| expected_motion_shot1 | 41.661 | 29960 | 0.343840 |
| boxer_shot3 | 12.468 | 0 | 0.000000 |
| pi3x_shot2 | 23.487 | 0 | 0.000000 |
| expected_motion_shot3 | 42.005 | 32073 | 0.364530 |
| within_shot1 | 31.877 | 36896 | 0.399240 |
| boxer_shot2 | 12.626 | 0 | 0.000000 |
| expected_motion_shot2 | 17.575 | 19569 | 0.209770 |
| within_shot3 | 36.765 | 39560 | 0.434480 |
| pair_000_prepare | 0.323 | 0 | 0.000000 |
| pair_000_initial_identity | 124.361 | 80846 | 0.961020 |
| pair_000_roma_matches | 131.032 | 0 | 0.000000 |
| within_shot2 | 0.420 | 0 | 0.000000 |
| pair_000_lift | 1.909 | 0 | 0.000000 |
| pair_000_registration | 0.534 | 0 | 0.000000 |
| pair_000_identity_review | 392.405 | 140970 | 1.917540 |
| pair_000_boundary | 341.612 | 405593 | 4.598890 |
| global_entity_table | 0.090 | 0 | 0.000000 |
| prompt_binding | 179.640 | 62134 | 0.837660 |
| appearance_prepare | 5.506 | 0 | 0.000000 |
| appearance_dino | 28.632 | 0 | 0.000000 |
| appearance_compact | 4.415 | 0 | 0.000000 |
| entity_displacement | 0.094 | 0 | 0.000000 |
| prompt_alignment | 279.788 | 190586 | 2.232980 |
| appearance_codex | 103.380 | 223830 | 2.372604 |
| appearance_report | 2.677 | 0 | 0.000000 |
| prompt_binding_report | 0.073 | 0 | 0.000000 |

Stages overlap, so summed durations are not wall time. Position scoring is CPU-only with0newtokens/USD0API.

## Scores

Position consistency (independent of original pair-relation score):

| Scope | Score | Valid records |
|---|---:|---:|
| within | 62.82449822984375 | 39 |
| cross | 63.12742062368126 | 9 |
| all | 62.881107872972585 | 48 |

Original spatial-relation summaries:

```json
{
  "within": {
    "shot1": {
      "score": 100.0,
      "total_pairs": 190,
      "confirmed_conflict_pairs": 0,
      "anomaly_ratio": 0.0,
      "no_conflict_pairs": 28,
      "unresolved_pairs": 125,
      "exempt_pairs": 37,
      "scoring_protocol": "confirmed_anomaly_fraction_v1",
      "formula": "100*(1-confirmed_conflict_pairs/total_pairs)"
    },
    "shot2": {
      "score": 100.0,
      "total_pairs": 15,
      "confirmed_conflict_pairs": 0,
      "anomaly_ratio": 0.0,
      "no_conflict_pairs": 3,
      "unresolved_pairs": 3,
      "exempt_pairs": 9,
      "scoring_protocol": "confirmed_anomaly_fraction_v1",
      "formula": "100*(1-confirmed_conflict_pairs/total_pairs)"
    },
    "shot3": {
      "score": 100.0,
      "total_pairs": 190,
      "confirmed_conflict_pairs": 0,
      "anomaly_ratio": 0.0,
      "no_conflict_pairs": 78,
      "unresolved_pairs": 93,
      "exempt_pairs": 19,
      "scoring_protocol": "confirmed_anomaly_fraction_v1",
      "formula": "100*(1-confirmed_conflict_pairs/total_pairs)"
    }
  },
  "boundaries": {
    "pair_000": {
      "score": 97.77777777777777,
      "total_pairs": 45,
      "confirmed_conflict_pairs": 1,
      "anomaly_ratio": 0.022222222222222223,
      "no_conflict_pairs": 32,
      "unresolved_pairs": 12,
      "exempt_pairs": 0,
      "scoring_protocol": "confirmed_anomaly_fraction_v1",
      "formula": "100*(1-confirmed_conflict_pairs/total_pairs)"
    }
  }
}
```

Appearance (Codex and DINO separately):

```json
{
  "status": "success",
  "model_protocol": "entity_appearance_compact_v3",
  "protocol": "entity_appearance_scoring_v6",
  "fused_score": false,
  "model_calls": 34,
  "total_tokens": 223830,
  "standard_api_equivalent_usd": 2.372604,
  "stage_seconds_sum": 144.61016058921814,
  "cost_note": "Usage of calls in this pipeline; local report adds no model calls. Standard Astra API equivalent, not a billing guarantee.",
  "results_path": "/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/study3_final_integrated_20260921/run/appearance/report/results.json",
  "entity_scores_path": "/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/study3_final_integrated_20260921/run/appearance/report/entities.csv",
  "appearance_inputs_path": "/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/study3_final_integrated_20260921/run/appearance/canonical",
  "all_entities": {
    "entities": 36,
    "scored_entities": 34,
    "unscored_entities": 2,
    "codex_score": 84.19426424744047,
    "codex_entity_mean": 95.1593137254902,
    "dino_score": 0.913816647687973,
    "dino_scored_entities": 34,
    "unknown_dimensions": 25
  },
  "multi_shot_entities": {
    "entities": 10,
    "scored_entities": 10,
    "unscored_entities": 0,
    "codex_score": 71.46517721956012,
    "codex_entity_mean": 85.41666666666666,
    "dino_score": 0.8584378157283427,
    "dino_scored_entities": 10,
    "unknown_dimensions": 6
  },
  "single_shot_entities": {
    "entities": 26,
    "scored_entities": 24,
    "unscored_entities": 2,
    "codex_score": 96.17267227690128,
    "codex_entity_mean": 99.21875,
    "dino_score": 0.9368911610044856,
    "dino_scored_entities": 24,
    "unknown_dimensions": 19
  }
}
```

Prompt alignment (conditional scores, unknowns retained):

| Dimension | Score | T/F/U |
|---|---:|---|
| presence | 100.0 | 18/0/0 |
| appearance | 92.85714285714286 | 25/1/2 |
| spatial | 80.95238095238095 | 9/3/5 |
| motion | 100.0 | 12/0/4 |

## Audit and limits

All source/frame hashes, final stage success after the documented recovery, four-dimensional contract/results, independent token/cost reconciliation, exact displacement recompute and prompt-score reaggregation passed. GPU maximum1; API reservation maximum6.
Raw r_e and distances/baselines/frame evidence: run/displacement/results.json and entities.csv. All original requests/responses and per-call usage retained. This is a fresh final-version end-to-end evaluation, not an estimate from cached stages.
Excludes preflight resource checks, human-authored/frozen reference preparation, historical experiments, parent assistant conversation and cluster monetary cost. Fees are recorded-model standard API equivalents; actual service billing unavailable.
Newly sampled detector/clustering/identity/model verdicts can change population and results. Position scores remain relative geometric deviations, including detection noise; prompt unknowns are not verified successes. No tuning or verdict selection by desired study ranking.

Initial rejected binding response:31,028tokens/USD0.417280, included in total1,308,446tokens/USD15.188604.53accepted model results plus1rejected response;54recorded requests. No judge prompt/schema/gate changes during recovery. GPU6 release guard passed after final audit; all own execution sessions ended.
