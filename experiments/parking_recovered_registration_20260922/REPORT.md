> 更正：本页优化“四组”采用了人工排除结果，不是原始 pipeline 输出。请以 [原始执行报告](RAW_PIPELINE_REPORT.md) 为准；两条路线原始输出均为三组。下文保留为历史记录。

# Parking recovered-detection registration comparison

Frozen recovered detection, fresh common geometry and motion; independent incremental optimization and pure Codex registration. Initial scene-wide identities are frozen for diagnostics. This is NOT a full consistency-scoring run or ground-truth accuracy benchmark.

| Case | Method | Coordinate groups | Attached shots | Comparable shot pairs | Method wall seconds |
|---|---|---:|---:|---:|---:|
| parking4 | optimization | 4 | 0 | 0/6 | 377.46 |
| parking4 | direct | 3 | 1 | 1/6 | 48.81 |

Numeric attachment is provisional. More connected shots does not by itself mean better registration. Optimization acceptance checks do not use a calibrated residual threshold; direct acceptance is the model’s register/abstain judgment.

## Excluded car-anchor diagnostics — not accepted registration

Mean Euclidean residual divided by target point-cloud RMS radius. Same anchor/RoMa pool for both methods; FPS32 fit points come from this pool, so it is NOT independent validation. Null/missing comparisons are unavailable, not zero error.

| Case | Shot pair | Method | Point count | Normalized mean residual |
|---|---|---|---:|---:|
| parking4 | Shot1 / Shot3 | optimization | 1721 | 0.9144820296480656 |
| parking4 | Shot1 / Shot3 | direct | 1721 | 10.502187519788363 |

## Usage

All recorded model calls: 258,041 tokens; estimated standard API equivalent USD 2.744650. Not actual billing. Includes fresh motion/initial identity and direct registration only; earlier detection/recovery cost excluded. Startup failures had no API calls. Cluster cost unavailable.

## Visuals and detailed records

### parking4

![Original first frames](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/parking_recovered_registration_20260922/inputs/parking4/overview.jpg)

![Registration comparison](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/parking_recovered_registration_20260922/shared/parking4/registration_topviews.png)

[Raw entity center distances and re](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/parking_recovered_registration_20260922/shared/parking4/entity_distances.csv) · [All cosine proposals and point diagnostics](/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/parking_recovered_registration_20260922/shared/parking4/comparison.json)

Distinct coordinate groups are offset only for plotting and never compared numerically. Overlays project the same original 3D box corners onto each method’s XY plane; silhouettes need not be rectangles. Entity position differences can be real generated changes, detection noise or registration error. Negative cosines here are proposals, not confirmed spatial violations. Final aligned identity/spatial review and appearance/prompt scoring were outside this registration experiment.

## Final audit

All four shots were freshly reconstructed with GeoCalib/Pi3X/Boxer and isolated motion;25 recovered entities, with six valid3D pillar observations in Shot1/2/4. Frozen detection/recovery reused. Pillar pairs1/2,1/4,2/4:180000raw matches each,2216/137/3820sameanchorregion matches respectively, but0confidence-and-cycle matches and0lifted points. Failure precedes numerical optimization.

The initial model incorrectly selected the car as anchor, violating the unchanged fixed-structure/large-furniture rule. Its rawShot3→1 fit and1721point diagnostics are preserved but excluded from accepted registration in optimization_audited/results.json. The car-pool table above is excluded raw-fit diagnostics, not protocol-valid registration accuracy. Accepted optimization retains4coordinate groups. Direct retains3groups, with onlyShot3→1 lowconfidence(scale0.68,yaw160°,translation[-0.045,0.547,0.21]);Shot2/4 abstain. No final scoring/anomaly confirmation.

Measured runtime720.559870s(12.01min):HIPprobe12.26s,frontend271.84s,initialidentity58.77s overlapsdirect49.08s,optimization377.66s. Plotting/restoration excluded.258041tokens/USD2.744650 standardAPIequivalent,notbill; previous recovery cost excluded.

Holo node284_gpu0 restored after test with originaljob204826/UUID/mappedmode/cores0,1,2,4. PID839436 loaded, freshheartbeat and liveprocess verified2026-09-23. No task inference remains.
