# EntityBench × Wan2.1 ROCm smoke protocol

## Objective

Verify the local end-to-end integration needed to evaluate the unmodified
Wan2.1-T2V-1.3B baseline with EntityBench on the AMD Slurm cluster:

1. generate every shot in one valid EntityBench episode;
2. preserve EntityBench's required `<episode>/<scene>_<shot>.mp4` layout;
3. run the strongest EntityBench pillar supported by an isolated local
   dependency stack and the available credentials;
4. record failures as integration evidence, without changing upstream Wan2.1,
   model checkpoints, datasets, or other users' jobs.

## Locked smoke sample

- Episode: `000020ca-f66b-3542-8ad1-5c3172105f7b__run15__i0_j19__T240`
- Tier: easy
- Scenes: 3
- Shots: 10
- Prompt source: each scene's `video_prompts` field in the released
  EntityBench script JSON

This is the shortest released episode (tied at 10 shots); ties are resolved by
lexicographic episode ID.

## Locked generation configuration

- Generator: unmodified Wan2.1 `t2v-1.3B`
- Checkpoint: `/vast/users/guangyi.chen/causal_group/jinyuan.hu/shotpilot/models/Wan2.1-T2V-1.3B`
- Resolution: `832x480`
- Frames: 81
- FPS: 16
- Solver: UniPC
- Sampling steps: 20
- Shift: 8.0
- Guidance: 6.0
- Prompt extension: disabled
- Base seed: 20260810; per-shot seed is base seed plus zero-based global shot index
- Model offload: enabled

Twenty steps are intentionally a smoke setting, not the Wan2.1 50-step
reference setting. Scores from this run must not be reported as a canonical
Wan2.1 EntityBench baseline.

## Resource isolation

- Reuse only an existing Slurm allocation owned by `guangyi.chen`; do not
  request a new allocation under normal circumstances.
- Before every launch, use `squeue`, `scontrol`, and `rocm-smi` to verify that
  the selected allocation and GPU are idle.
- Launch an isolated one-GPU step with
  `srun --jobid=<existing_job> --overlap --gres=gpu:mi210:1`.
- Do not attach to, cancel, reprioritize, or modify another user's job.
- Write only under `EECBench/experiments/entitybench-wan21-smoke/`.
- Resume by skipping existing non-empty MP4 files; never overwrite completed
  outputs.

## Evaluation policy

- First perform import/model/video-layout preflight checks.
- Pillars 2 and 3 use GroundingDINO, CLIP, DINOv2, and Gemini. Before Gemini
  credentials are available, `--non_vlm_only` may run only the API-free
  grounding, presence, cross-shot DINOv2, transition, and gap-decay paths.
  Gemini-derived values remain absent and the manifest labels the run.
- Prefer the read-only `vace` conda environment. This run used it for Wan2.1
  generation; Pillar 1 used the read-only `vbench` environment because VBench
  and PyIQA are not installed in `vace`.
- All model and framework caches are routed into the experiment directory or
  exposed there through read-only symlinks; shared environments and caches are
  not modified.
- EntityBench strict mode remains enabled for any reported metric. If strict
  execution is blocked by missing infrastructure, preserve the error and
  report the run as an integration preflight rather than a benchmark score.

## Acceptance criteria

1. Slurm binds the process to exactly one allocated MI210 and ROCm is visible.
2. Ten readable MP4 files exist with the exact EntityBench naming convention.
3. EntityBench discovers all ten shots for the selected episode.
4. At least one strict evaluation pillar completes, or its concrete external
   dependency/credential blocker is reproduced and recorded.
5. Existing ShotPilot files, checkpoints, datasets, and Slurm jobs remain
   unchanged.

## Execution note (2026-08-10)

The run reused job `132688` on `auh7-1b-gpu-217`. All eight allocated MI210s
showed 0% utilization and 0% VRAM before launch; each workload requested one
logical GPU. Job `132639`, submitted before the no-new-allocation clarification,
was cancelled before any MP4 completed and fully released.

## API-free Pillar 2/3 execution note (2026-08-25)

The API-free evaluation reused physical GPU 5 in existing job `151620` on
`auh7-1b-gpu-208`. The GPU was checked repeatedly for 0% utilization, 0% VRAM,
and no KFD-resident process immediately before each launch. When another task
temporarily occupied it, evaluation paused rather than overlapping; it resumed
only after the process exited and repeated checks again showed the card idle.

The read-only `vace` environment contains Transformers 5.5.4 and a
GroundingDINO build without the NVIDIA `_C` extension. The evaluator therefore
uses process-local compatibility for the removed BERT helpers/signature and
`GDINO_MSDA_BACKEND=pytorch`, GroundingDINO's bundled PyTorch multi-scale
deformable-attention implementation. Checkpoints are pinned under the
experiment cache and their paths/backend are recorded in the manifest.
