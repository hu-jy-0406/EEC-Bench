# Wan2.1 EntityBench smoke result

## Status

Pillar 1 completed on 2026-08-10 and the API-free portions of Pillars 2/3
completed on 2026-08-25. This is an integration smoke result, not a canonical
Wan2.1 EntityBench baseline: generation used 20 sampling steps instead of the
Wan2.1 reference setting, and the sample contains one easy episode.

## Scope and resources

- Episode: `000020ca-f66b-3542-8ad1-5c3172105f7b__run15__i0_j19__T240`
- Videos: 10 shots across 3 scenes
- Generator: Wan2.1 T2V 1.3B, 832x480, 81 frames, 16 FPS
- Generation environment: read-only `vace`
- Pillar 1 environment: read-only `vbench`
- Slurm: existing job `132688`, node `auh7-1b-gpu-217`, one MI210 per step
- Isolation: no new GPU allocation; experiment-local caches and outputs

All 10 MP4s passed `ffprobe`: H.264, 832x480, 16 FPS, 81 frames, and 5.063
seconds. The strict evaluator found all 10 expected shots.

## Strict Pillar 1 result

Every configured VBench dimension evaluated all 10 shots with zero failures.

| Dimension | Canonical scale | Mean | Coverage |
|-----------|-----------------|------|----------|
| subject_consistency | [0, 1] | 0.975430 | 10/10 |
| temporal_flickering | [0, 1] | 0.989938 | 10/10 |
| motion_smoothness | [0, 1] | 0.993366 | 10/10 |
| dynamic_degree | {0, 1} | 0.200000 | 10/10 |
| aesthetic_quality | [0, 1] | 0.587253 | 10/10 |
| imaging_quality | [0, 100] | 68.025922 | 10/10 |

The machine-readable episode result and complete report are under
`eval_results/wan21_pillar1/`. Outputs and generated media are intentionally
git-ignored because they are reproducible run artifacts.

## Strict API-free Pillar 2/3 result

The `vace` run used local GroundingDINO Swin-T, BERT base uncased,
`openai/clip-vit-base-patch32`, and `facebook/dinov2-base` checkpoints. On ROCm,
GroundingDINO used its bundled PyTorch multi-scale deformable-attention backend;
the backend and checkpoint paths are pinned in `run_manifest.json`.

- GroundingDINO: 215/215 calls completed without an exception.
- Entity-shot slots confidently present: 30/43.
- Saved canonical crops: 43 (including weak candidates retained for audit).
- MI2V transition pairs: 7/7 evaluated, zero failures.
- Gap-decay records: 45.
- Gemini/API calls: 0 by construction.

| Metric | Value | Internal coverage |
|--------|------:|------------------:|
| intra_character_presence | 0.8000 | 10 shots |
| intra_object_presence | 0.9667 | 10 shots |
| intra_location_presence | 0.1000 | 10 shots |
| cs_face | 0.7769 | 11 comparisons |
| cs_object | 0.7830 | 18 comparisons |
| cs_transition_boundary | 0.2541 | 7 transitions |

Machine-readable results, the audit crops, manifest, and Markdown report are
under `eval_results/wan21_non_vlm_rocm/`. Because Gemini was omitted, the
cross-shot fidelity gate could not be applied; these numbers validate execution
and reporting, not a canonical benchmark score.

## Compatibility findings

- VBench 0.1.5 must be called with `local=True` and must receive
  `VBENCH_CACHE_DIR` before its first import, otherwise it can download models
  or write global caches.
- Its local DINO loader still checks Torch's URL checkpoint cache, so the run
  uses an experiment-local `TORCH_HOME` with a read-only checkpoint symlink.
- VBench's AMT loader predates PyTorch 2.6's `weights_only=True` default. The
  runner sets `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1` only inside the evaluation
  process for the standard pre-provisioned VBench checkpoints.

## Remaining full-benchmark blocker

Only Gemini-derived entity, object, scene, style, action, and intra-shot
fidelity judgments remain unexecuted, along with the fidelity gate that depends
on those judgments. The canonical model is `gemini-2.5-pro`. Configure a Google
AI Studio key outside the repository as documented in `docs/gemini-setup.md`;
then rerun Pillars 2/3 without `--non_vlm_only`.
