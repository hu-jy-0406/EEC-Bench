# Appearance v6 integrated into the full temporal pipeline

2026-09-20. User requested integration of the selected low-cost scoring system.

`run_gs_integrated.py` now defaults to `temporal_v2 --stop-after full`, running original
canonical preparation, guarded DINO, compact-v3 Codex and local v6 scoring after the
global registry. Both FPS32 and direct Codex registration feed the same appearance
stages. Explicit identity/presence/spatial stopping scopes remain unchanged.
Historical flow1_fused_v1 retains its spatial default; requesting full with that
historical protocol errors explicitly.

The original model prompt, schema, role, Astra/medium setting, crop evidence and DINO
implementation were not edited. No new verifier, event mechanism, score fusion,
manual relabeling or paid call was added for integration. Model calls are counted
once from compact/calls status records, including in the total pipeline usage and
standard API equivalent cost. The local report's reuse counters are cross-checked,
not added to costs again. GPU stages retain serialized scheduling and the existing
physical-GPU/UUID idle guard. New output directories remain required; there is no
implicit full-pipeline resume or overwrite of historical inference.

## Validation

- 62 focused tests passed: legacy integrated orchestration, temporal scoring,
  global registry, canonical/compact/minimal/v6 appearance, and six new integration tests.
- New tests cover both registration paths, singleton scenes, explicit early stops,
  guarded DINO dependencies, score and token/cost aggregation, model-failure
  propagation, and refusal to finish full without appearance results.
- `validate.py` invoked the public CLI `--plan-only` default on both studies;
  regenerated canonical crops and compact sheets; checked every appearance field
  except its derived file path, all crop hashes, exact wire inputs and sheet hashes.
- It then reused frozen DINO and Codex artifacts, exercising the selected score
  dispatch with model calls patched to fail if attempted, and ran the real v6 report
  and integrated summary. All 71 entities / 474 appearance panels passed native-pixel,
  raw-response, prompt, schema, model and original-frame audits.
- The original complete-run rejection of existing output directories is covered by
  regression tests. Standalone scoring can read already-completed entity outputs;
  this validation does not add full-pipeline resume semantics.

| Frozen study | Entities / scored | Codex v6 | DINO | Reused historical tokens | Reused API equivalent |
|---|---:|---:|---:|---:|---:|
| Study2 | 36 / 34 | 93.7500 | 0.9100262 | 217,751 | $1.670230 |
| Study3 | 35 / 33 | 85.4031 | 0.9116231 | 212,127 | $1.719078 |

All aggregate fields equal the previous selected v6 report, including subset
scores and unknown counts. The two historical model populations total 429,878
tokens / $3.389308 standard API equivalent; they are not fresh charges.
**This validation added 0 model calls, 0 tokens and $0 API cost.**

Tests and CPU/image replay used the existing account-owned allocation 196093 on
auh7-1b-gpu-197 after CPU-load/process inspection, one CPU and nice19, GPU visibility
disabled. The existing geometry interpreter was checked for torch/transformers imports.
No new allocation or GPU workload was launched.

This is integration and frozen-artifact validation, **not a fresh frontend/GPU/model
end-to-end run**. Per-study `summary.json` explicitly labels all recorded usage as
historical replay. `validation.json` records audited results and source hashes.
Production `summary.json.appearance` describes calls made in its own new run.

Usage and output paths: [integration documentation](../../docs/gs-integrated-appearance-v6.md).
