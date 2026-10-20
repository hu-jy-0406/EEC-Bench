# Study3 optimized pipeline — fresh end-to-end measurement

Default optimized runtime scoring_efficiency_v1 / parallel_v2; full temporal_v2 + appearance + binding + four-dimensional prompt alignment, RoMa FPS32 registration. Started from18 original JPEG keyframes, fresh detection/clustering/geometry/all model judgments. Original frames, frozen normal reference and pretrained weights reused; no historical inference outputs.

Pipeline wall 798.553s; outer launch including immediate GPU guard 801.059s (13.35min).
53 recorded model requests / 53 call directories; 1,141,079 tokens; standard API equivalent USD12.632622, not actual billing.
Input1,096,306; cached input subset63,232; cache-write subset0; output44,773.
Astra standard API equivalent, not bill: USD/M input10, cached-input1, cache-write12.5, output50; input>272000 uses input-side x2/output x1.5. Cache is a subset of input.

## Full-run comparison

| Version | Outer wall seconds | Tokens | API equivalent USD |
|---|---:|---:|---:|
| Previous complete run (recorded binding retry) | 1433.193 | 1,308,446 | 15.188604 |
| Fresh optimized run | 801.059 | 1,141,079 | 12.632622 |

Measured fresh run; previous baseline includes one binding retry/recovery gap. Different compute node and fresh stochastic inventories/verdicts: observed difference is not a controlled pure optimization effect.
Observed outer wall reduction44.11%; total token reduction12.79%. Old component validation expense (8calls/601721tokens/USD6.002010) is separate and not added to this production-run total.

## Measured stages

| Stage | Seconds | Tokens | API equivalent USD |
|---|---:|---:|---:|
| detection_and_clustering | 73.779 | 46,404 | 0.514880 |
| geocalib | 42.925 | 0 | 0.000000 |
| prepare_shot_inputs | 0.295 | 0 | 0.000000 |
| pi3x_shot1 | 41.423 | 0 | 0.000000 |
| boxer_shot1 | 14.014 | 0 | 0.000000 |
| pi3x_shot3 | 23.067 | 0 | 0.000000 |
| expected_motion_shot1 | 41.869 | 29,970 | 0.343780 |
| boxer_shot3 | 13.119 | 0 | 0.000000 |
| pi3x_shot2 | 23.930 | 0 | 0.000000 |
| expected_motion_shot3 | 40.294 | 32,017 | 0.363410 |
| within_shot1 | 33.068 | 36,945 | 0.402130 |
| boxer_shot2 | 13.348 | 0 | 0.000000 |
| expected_motion_shot2 | 19.731 | 19,594 | 0.209940 |
| within_shot3 | 35.258 | 39,467 | 0.432150 |
| pair_000_prepare | 0.324 | 0 | 0.000000 |
| pair_000_initial_identity | 117.452 | 80,544 | 0.949200 |
| pair_000_roma_matches | 130.693 | 0 | 0.000000 |
| within_shot2 | 0.452 | 0 | 0.000000 |
| pair_000_lift | 1.918 | 0 | 0.000000 |
| pair_000_registration | 0.582 | 0 | 0.000000 |
| pair_000_identity_review | 174.267 | 134,092 | 1.558440 |
| pair_000_boundary | 229.479 | 292,162 | 3.320740 |
| global_entity_table | 0.090 | 0 | 0.000000 |
| prompt_binding | 100.800 | 32,341 | 0.446130 |
| appearance_prepare | 5.609 | 0 | 0.000000 |
| appearance_dino | 31.961 | 0 | 0.000000 |
| appearance_compact | 4.226 | 0 | 0.000000 |
| appearance_codex | 173.028 | 223,734 | 2.039772 |
| prompt_alignment | 140.906 | 173,809 | 2.052050 |
| appearance_report | 2.766 | 0 | 0.000000 |
| prompt_binding_report | 0.082 | 0 | 0.000000 |
| entity_displacement | 0.106 | 0 | 0.000000 |

Stages overlap; their summed durations are not episode wall time. All actual calls/usage are retained in run/calls.csv; cached input is not counted again as additional tokens.

## Scores and population

```json
{
  "global_entities": {
    "path": "/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/study3_scoring_efficiency_fresh_20260921/run/global_entities/global_entities.json",
    "local_entities": 46,
    "global_records": 36,
    "confirmed_links": 10,
    "unresolved_links": 1
  },
  "position": {
    "within": {
      "score": 62.804234199204366,
      "total_records": 46,
      "scored_records": 39,
      "unscored_records": 7,
      "weighting": "equal_entity_observation_records"
    },
    "cross": {
      "score": 67.14910493652648,
      "total_records": 29,
      "scored_records": 9,
      "unscored_records": 20,
      "weighting": "equal_entity_observation_records"
    },
    "all": {
      "score": 63.57939385199178,
      "total_records": 75,
      "scored_records": 48,
      "unscored_records": 27,
      "weighting": "equal_entity_observation_records"
    }
  },
  "spatial_within": {
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
      "presence": {
        "score": 92.3076923076923,
        "coverage": 0.7692307692307693,
        "N": 13,
        "C": 9,
        "K": 1,
        "U": 3,
        "E": 16,
        "identification_interval": [
          69.23076923076923,
          92.3076923076923
        ]
      },
      "spatial": {
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
  },
  "appearance": {
    "status": "success",
    "model_protocol": "entity_appearance_compact_v3",
    "protocol": "entity_appearance_scoring_v6",
    "fused_score": false,
    "model_calls": 34,
    "total_tokens": 223734,
    "standard_api_equivalent_usd": 2.039772,
    "stage_seconds_sum": 217.59171676635742,
    "cost_note": "Usage of calls in this pipeline; local report adds no model calls. Standard Astra API equivalent, not a billing guarantee.",
    "results_path": "/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/study3_scoring_efficiency_fresh_20260921/run/appearance/report/results.json",
    "entity_scores_path": "/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/study3_scoring_efficiency_fresh_20260921/run/appearance/report/entities.csv",
    "appearance_inputs_path": "/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/study3_scoring_efficiency_fresh_20260921/run/appearance/canonical",
    "all_entities": {
      "entities": 36,
      "scored_entities": 34,
      "unscored_entities": 2,
      "codex_score": 85.7756006249227,
      "codex_entity_mean": 96.0171568627451,
      "dino_score": 0.9138166462733652,
      "dino_scored_entities": 34,
      "unknown_dimensions": 26
    },
    "multi_shot_entities": {
      "entities": 10,
      "scored_entities": 10,
      "unscored_entities": 0,
      "codex_score": 74.45048380540685,
      "codex_entity_mean": 88.33333333333334,
      "dino_score": 0.8584378157283427,
      "dino_scored_entities": 10,
      "unknown_dimensions": 8
    },
    "single_shot_entities": {
      "entities": 26,
      "scored_entities": 24,
      "unscored_entities": 2,
      "codex_score": 96.17267227690128,
      "codex_entity_mean": 99.21875,
      "dino_score": 0.9368911590004578,
      "dino_scored_entities": 24,
      "unknown_dimensions": 18
    }
  },
  "binding": {
    "bound": 11,
    "unbound": 25,
    "unknown": 0
  },
  "prompt_alignment": {
    "presence": {
      "score": 100.0,
      "counts": {
        "T": 18,
        "F": 0,
        "U": 0,
        "N": 18,
        "score": 100.0,
        "identification_interval": [
          100.0,
          100.0
        ]
      }
    },
    "appearance": {
      "score": 92.85714285714286,
      "counts": {
        "T": 25,
        "F": 1,
        "U": 2,
        "N": 28,
        "score": 96.15384615384616,
        "identification_interval": [
          89.28571428571429,
          96.42857142857143
        ]
      }
    },
    "spatial": {
      "score": 78.57142857142857,
      "counts": {
        "T": 8,
        "F": 3,
        "U": 6,
        "N": 17,
        "score": 72.72727272727273,
        "identification_interval": [
          47.05882352941177,
          82.3529411764706
        ]
      }
    },
    "motion": {
      "score": 100.0,
      "counts": {
        "T": 12,
        "F": 0,
        "U": 4,
        "N": 16,
        "score": 100.0,
        "identification_interval": [
          75.0,
          100.0
        ]
      }
    }
  }
}
```

## Audit

68 source snapshots and18 image hashes match. Fresh detector provenance, all stage successes, DAG order, GPUpeak1/APIreservedpeak8, independent token/cost reconciliation, exact r_e recompute, alignment aggregation and FPS32 objective all pass.
Raw r_e: run/displacement/results.json and entities.csv. Canonical/model wire inputs, all model responses, unknowns and original evidence remain. Source snapshots do not depend on future workspace edits. No expected anomaly counts or desired scores were supplied.
Original-video generation, frozen reference preparation, resource checks/queue, post-run audit/report, historical validation and parent conversation; cluster monetary cost unavailable.

Final GPU release guard passed; no failed model calls or retries. The evaluation launcher exited successfully.
