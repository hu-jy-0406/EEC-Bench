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

- Run only through a new Slurm allocation owned by `guangyi.chen`.
- Request exactly one MI210 GPU on a node with unallocated GRES capacity.
- Do not attach to, cancel, reprioritize, or modify an existing job.
- Write only under `EECBench/experiments/entitybench-wan21-smoke/`.
- Resume by skipping existing non-empty MP4 files; never overwrite completed
  outputs.

## Evaluation policy

- First perform import/model/video-layout preflight checks.
- Pillars 2 and 3 require GroundingDINO plus Gemini-compatible credentials;
  they will not be silently approximated if unavailable.
- Pillar 1 requires VBench. Any added Python packages must be installed into an
  experiment-local dependency directory, never the shared Wan environment.
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

