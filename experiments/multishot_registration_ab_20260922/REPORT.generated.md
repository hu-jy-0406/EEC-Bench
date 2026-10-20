# Three-episode multi-shot registration comparison

Fresh common frontend; independent incremental optimization and pure Codex registration. Initial scene-wide identities are frozen for diagnostics. This is NOT a full consistency-scoring run or ground-truth accuracy benchmark.

| Case | Method | Coordinate groups | Attached shots | Comparable shot pairs | Method wall seconds |
|---|---|---:|---:|---:|---:|
| parking4 | optimization | 4 | 0 | 0/6 | 0.03 |
| parking4 | direct | 3 | 1 | 1/6 | 65.26 |
| bedroom4 | optimization | 4 | 0 | 0/6 | 138.02 |
| bedroom4 | direct | 4 | 0 | 0/6 | 46.15 |
| diner8 | optimization | 8 | 0 | 0/28 | 136.87 |
| diner8 | direct | 7 | 1 | 1/28 | 106.15 |

Numeric attachment is provisional. More connected shots does not by itself mean better registration. Optimization acceptance checks do not use a calibrated residual threshold; direct acceptance is the model’s register/abstain judgment.

## Same-point registration diagnostics

Mean Euclidean residual divided by target point-cloud RMS radius. Same anchor/RoMa pool for both methods; FPS32 fit points come from this pool, so it is NOT independent validation. Null/missing comparisons are unavailable, not zero error.

| Case | Shot pair | Method | Point count | Normalized mean residual |
|---|---|---|---:|---:|

## Usage

All recorded model calls: 1,296,511 tokens; estimated standard API equivalent USD 13.530038. Not actual billing. Includes common clustering/motion/initial identity and direct registration. Startup failures had no API calls. Cluster cost unavailable.

## Visuals and detailed records

### parking4

![Original first frames](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/multishot_registration_ab_20260922/inputs/parking4/overview.jpg)

![Registration comparison](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/multishot_registration_ab_20260922/shared/parking4/registration_topviews.png)

[Raw entity center distances and re](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/multishot_registration_ab_20260922/shared/parking4/entity_distances.csv) · [All cosine proposals and point diagnostics](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/multishot_registration_ab_20260922/shared/parking4/comparison.json)

### bedroom4

![Original first frames](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/multishot_registration_ab_20260922/inputs/bedroom4/overview.jpg)

![Registration comparison](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/multishot_registration_ab_20260922/shared/bedroom4/registration_topviews.png)

[Raw entity center distances and re](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/multishot_registration_ab_20260922/shared/bedroom4/entity_distances.csv) · [All cosine proposals and point diagnostics](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/multishot_registration_ab_20260922/shared/bedroom4/comparison.json)

### diner8

![Original first frames](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/multishot_registration_ab_20260922/inputs/diner8/overview.jpg)

![Registration comparison](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/multishot_registration_ab_20260922/shared/diner8/registration_topviews.png)

[Raw entity center distances and re](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/multishot_registration_ab_20260922/shared/diner8/entity_distances.csv) · [All cosine proposals and point diagnostics](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/multishot_registration_ab_20260922/shared/diner8/comparison.json)

Distinct coordinate groups are offset only for plotting and never compared numerically. Overlays project the same original 3D box corners onto each method’s XY plane; silhouettes need not be rectangles. Entity position differences can be real generated changes, detection noise or registration error. Negative cosines here are proposals, not confirmed spatial violations. Final aligned identity/spatial review and appearance/prompt scoring were outside this registration experiment.
