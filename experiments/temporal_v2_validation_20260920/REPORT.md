# Temporal v2 implementation validation

Status: success. Tests: 54 passed; adapter checks passed.

Validation reuses frozen Study3-concise-MTD detections, geometry, reviewed identities and FPS32 registration. Expected-motion and temporal/boundary Codex calls are fresh. This is NOT a fresh WeDetect/GPU end-to-end run, and Shot2 is not part of this component replay. The integrated plan covers all supplied shots; singleton/Shot2 coverage and both registration paths are tested.

All registration source hashes unchanged: True. Historical inputs/results unchanged: True.

| Scope | Presence | Spatial | Presence C/K/U/E | Spatial C/K/U/E |
|---|---:|---:|---|---|
| shot1 | 100.0 | 100.0 | 11/0/8/1 | 0/0/190/0 |
| shot3 | 100.0 | 100.0 | 9/0/3/3 | 0/0/91/14 |
| boundary Shot1 -> Shot3 | 100.0 | 100.0 | 6/0/7/11 | 0/0/20/1 |

Scores retain the historical unknown-inclusive formula. A spatial score of 100 is not proof that every relation is verified compatible. Inspect coverage and event witnesses.

Component validation elapsed 1225.79 seconds; 8 fresh Codex calls; 838604 tokens. These are validation costs, not fresh full-pipeline latency/cost.

## Confirmed events

No confirmed conflicts in this component replay. Unknown cases remain unresolved.

## Verified behavior

- Shot3 short cup retains static intervals before frame202 and reasonable pickup/drinking thereafter.
- Boundary vectors use exact Shot1 frame240 and Shot3 frame0 boxes, including the moving short-cup identity.
- Missing endpoint boxes stay null; full identity population and ambiguous groups remain in ledgers.
- The unweighted unsquared 3D registration objective, FPS32 selector, RoMA settings and direct estimator were not changed.

Entry: `scripts/run_gs_integrated.py --consistency-protocol temporal_v2 --alignment-method roma_fps32 ...`; direct remains selectable. Historical scoring: `--consistency-protocol flow1_fused_v1`.

Additional integration checks: all three actual CLI plan-only paths passed without creating a case; expected-static/observed-moving objects remain in the normative static export but are ineligible as anchors; alias mapping is metadata, not a motion-authorizing prompt fact. Final deterministic gate revalidation changed no model-derived event status.
