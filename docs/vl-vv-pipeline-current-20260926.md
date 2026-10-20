# Current VL/VV pipeline and batch readiness — 2026-09-26

> **2026-10-09 update (latest): the branch-separated chain is the default.**
> Discovery v5 → review v6 → scoring v5: separate V-L and V-V detection
> calls (contract-checking template / V-V checklist template), separate V-L
> and V-V review calls (keep or split, clarify the description, then
> confirmed / rejected / uncertain with evidence criteria; no partly-true),
> and separate scores: V-L, V-V within/cross, plus the V-V subset involving
> unintentional (prompt-unbound) entities with issue counts and proportions.
> The two branches run concurrently. Spec:
> `docs/vl-vv-branch-pipeline-v1.md`. `--discovery-protocol v4` (or v1–v3)
> keeps the single-issue-list chains described below.
>
> **2026-10-06 update (latest): discovery v4 → review v5 is the default chain.**
> Both add one rule to v3 / v4: a contract or global description of an entity
> applies in every shot where the entity appears, unless that shot's own text
> describes it differently (`docs/vl-vv-entity-description-scope.md`).
>
> **2026-10-06 update (later the same day): discovery v3 is the default.**
> Each issue carries exactly one label. A discrepancy that is both V-V and V-L
> becomes two linked issues, and the V-L one covers only the violating shots
> (`docs/vl-vv-issue-discovery-v3.md`). `--discovery-protocol v2` keeps
> multi-label issues. Review v4 and scoring v3 accept both.
>
> **2026-10-06 update: review v4 is the default after discovery v2 (and v3).**
> - **Review v4:** one confirmed / rejected / uncertain verdict per V-L / V-V
>   label, judged on the label's core problem. A real core problem is
>   confirmed even if secondary details of the description are wrong; a label
>   is rejected only when the core problem itself is false.
> - **Scoring:** v3, unchanged.
> - **Rollback:** `--review-protocol v2` restores the previous review.
> - **Removed:** review v3 (partly true) and scoring v4, on the same day.
> - **Details:** `docs/vl-vv-issue-review-v4.md`.

> **2026-10-04 update — protocol v2 is the default.** Issue discovery now uses
> a must-check checklist with an open-ended sweep, a continuity ledger for
> recurring characters/places, shot-transition checks, and non-exclusive
> V-L / V-V labels on one issue list (`prompts/vl_vv_issue_discovery_v2.txt`).
> Review v2 gives one verdict per label; scoring v3 deducts a dual-labeled
> issue in both its V-L and V-V bucket with unchanged penalty rubric v2
> weights. `run_vl_vv_pipeline.py --discovery-protocol v1` restores the chain
> described below (discovery v1 → review v1 → scoring v2). Definitions,
> subcategories and checklist: `docs/vl-vv-issue-taxonomy-checklist-v2.md`;
> evidence and validation: `experiments/vl_vv_checklist_v2_20261004/REPORT.md`.
> The 1,000 first-200 scores were produced by v1 and are not comparable with
> v2 scores.
>
> **Running either version (both are kept).** One case, inside an allocation:
> `run_vl_vv_pipeline.py --case CASE --output FRESH_DIR --mode from-registry
> --discovery-protocol v1` (historical: discovery v1 → review v1 → scoring v2)
> or `--discovery-protocol v2` (checklist: discovery v2 → review v2 → scoring
> v3; the default). Batch: `experiments/vl_vv_multimodel_first200_20260926/run_batch.py`
> takes `--discovery-protocol v1|v2`; a new `--exp-dir` must state it, an
> existing directory keeps its recorded chain (directories created before
> 2026-10-05, e.g. `vl_vv_multimodel_first200_run02`, resume as v1 with no
> flag), and a mismatched flag is refused so the two chains never mix in one
> directory. The success check accepts only the scoring protocol of that
> chain (`vl_vv_episode_scoring_v2` for v1, `..._v3` for v2).

> **2026-10-05 — keyframes of single-video episodes (CineTrans-DiT, HoloCine).**
> Shots are segmented at the cuts recorded at inference (CineTrans `mask_info`,
> HoloCine `shot_cut_frames`), not the nominal 5 s grid, and keyframes are
> sampled by exact frame index: shot 1 from frame 0, later shots from the
> recorded cut + 4 frames (or after a clear visible cut within 8 frames), last
> keyframe 4 frames before the shot end (`scripts/episode_shot_segments.py`).
> Batch `prepare_case.py` does this automatically; detection prepare, the
> pipeline runner and the discovery/review runners reject grid-sampled episode
> keyframes unless `--allow-legacy-nominal-keyframes` is given for reproducing
> historical results. Resampled keyframes for the 400 first-200 videos:
> `experiments/episode_shot_resegmentation_20261005/`.

This is the current operational map for the four-stage V-L/V-V evaluator. The
2026-09-25 handoff retains historical experiments and contains older paragraphs
written before scoring was implemented.

## One episode, four stages

| Stage | Entrypoint | Input and judgment | Output |
| --- | --- | --- | --- |
| 1. Detection and registry | `scripts/run_vl_vv_detection.py` | One prepared case with the original contract and exactly six original keyframes per shot. WeDetect, isolated within-shot Luna clustering, contract binding with targeted Grounding DINO recovery, exact-once global identity matching, and separate DINO appearance evidence. | Frozen `case/episode_entities.json`; `case/run.json` status `complete`. |
| 2. Issue discovery | `scripts/run_vl_vv_issue_discovery.py` | All keyframes, original prompt/contract and frozen entity ledger. GPT-6 Luna/low receives `prompts/vl_vv_issue_discovery_v1.txt`, including the expanded candidate families. | `issue_discovery/result.json`: V-L, within-shot V-V and cross-shot V-V **candidates**. |
| 3. Issue review | `scripts/run_vl_vv_issue_review.py` | Every discovery candidate, the original contract and all keyframes. Luna/low independently confirms, rejects or marks each issue uncertain. No candidate means no review API call. | `issue_review/result.json`, with original candidates preserved and one review per issue. |
| 4. Episode scoring | `scripts/run_vl_vv_episode_scoring.py` | Completed issue-review JSON only, without images. Luna/low assigns a discrete impact tier and duplicate links; Python applies penalty rubric v2 and reviewer-confidence factors. | `episode_scoring/result.json`: separate V-L, V-V within, V-V cross and their V-V mean, with event ledger and usage/cost estimate. |

The discovery `SKILL.md` is an operator reference. The discovery runner sends
the prompt file, not that skill, to Luna. The scoring runner sends
`skills/vl-vv-episode-scorer/SKILL.md` as its model instructions. Both model
calls use `scripts/openai_api_env.sh`; never place credentials in commands,
output directories or reports. The older 3D registration/GS pipeline remains
a separate protocol.

The current scoring bases are minor/moderate/major/critical = 10/25/50/80.
Confirmed issue deductions are multiplied by the reviewer-confidence factor
(high 1, medium 0.75, low 0.5). The maximum adjusted deduction represents a
same-bucket duplicate group. Distinct groups compound as
`100 * product(1 - deduction/100)`. Rejected and uncertain issues have no
deduction. An empty confirmed-issue bucket scores 100 under this protocol; it
does not demonstrate perfect video consistency. There is no combined V-L/V-V
score. These weights have not been calibrated against human ratings.

## One-case integrated runner

Use `scripts/run_vl_vv_pipeline.py` for a fresh, immutable run output. It does
not choose models, extract videos, submit Slurm jobs or request resources.
Input preparation remains model-specific: freeze source-video checksums, use
the original contract, extract six keyframes per shot on an allocated compute
node and run `run_vl_vv_detection.py prepare` into a fresh case directory.

For an existing completed detector case, reuse the frozen registry and run the
new discovery prompt, review and v2 scoring into a **different fresh directory**:

```bash
/vast/users/guangyi.chen/anaconda3/bin/python \
  EECBench/scripts/run_vl_vv_pipeline.py \
  --case /abs/completed-case --output /abs/new-evaluation \
  --mode from-registry --dry-run
```

Remove `--dry-run` only from inside an already owned, suitable Slurm compute
allocation. This mode does not use a GPU. It still reads and checks original
keyframe hashes during the model stages. For a newly prepared case, use
`--mode full --gpu PHYSICAL_INDEX --gpu-uuid GPU-HEX`; the runner executes
detect, match, DINO preparation/inference/attachment, discovery, review and
scoring in order. The existing GPU guards recheck utilization, VRAM, KFD
processes and the physical-index/UUID binding. Revalidate card availability
immediately before launch and do not overlap another workload. The runner
refuses `EECBENCH_ALLOW_SHARED_GPU=1` in full mode.

The runner checks stage result statuses, records commands, immutable source
hashes, per-stage log paths, durations and failures under the new output root.
It refuses existing output directories and keeps the source case intact in
`from-registry` mode. A failed stage remains on disk for diagnosis; recovery
must use a fresh output directory or the appropriate stage-specific CLI rather
than overwriting a partial result.

## Verified readiness and remaining live check

- The existing Wan2.2/StoryMem/HoloCine ten-episode cohort has 30/30 cases
  with contract, keyframe manifest, completed entity registry, old discovery
  and old review results. All 30 pass the new runner's local `from-registry`
  preflight and the old discovery/review schema checks for downstream input.
- The old discovery calls used prompt SHA-256
  `70621658bfbada7ef01f4449dcbee24f459ca451f0fe93e4e7788bd137829309`.
  The expanded current prompt has SHA-256
  `167aefdfd398f522314655f291b097fd55b4a406c2a928c4fe2097ddf88cf7a8`.
  The old candidate/review outputs are therefore **not** evidence of the new
  discovery prompt's recall.
- The new runner's real-case dry run and 15 focused local pipeline/discovery/
  scoring tests pass. Its execution and failure paths were exercised with
  fake stage outputs; they made no API or GPU calls.
- No fresh end-to-end call has yet used the expanded discovery prompt and v2
  scorer. The prior attempt to transmit 30 frozen review JSONs to the external
  Luna API was rejected by workspace auto-review because authorization for
  that specific transfer was unclear; it made no successful request. A future
  batch needs the user-selected data scope and corresponding authorization.
- The old `experiments/vl_vv_wan_storymem_holocine_10_20260925/launch_batch_10.sh`
  hardcodes an expired Slurm allocation and its case wrapper ends at review.
  `experiments/vl_vv_episode_scoring_penalty_v2_20260925/run_batch.py` is
  hardcoded to old review JSONs. Neither is the new integrated entrypoint.

The model cohort, episode range and input preparation for the next batch are
pending the user's selection. Verify video/contract availability and shared
episode IDs for that selection before building a batch manifest or allocating
GPU workers. Report uncached input, cached input and output tokens with the
corresponding USD estimate or actual bill, clearly labeled.
