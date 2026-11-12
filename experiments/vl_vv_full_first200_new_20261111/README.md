# Full first-200 run of the new pipeline, without and with the unspecified plug-in (2026-11-11)

Owner, 2026-11-11 (Dubai evening): "好的，复用V-L打分，然后对new和new+插件跑200个全量".

## What runs

- 1,000 videos = the successful videos of `../vl_vv_full_first200_v3_20261109` (200 episodes x CineTrans, HoloCine,
  StoryMem, Wan2.1, Wan2.2).
- new = the current default pipeline (chain v6, pipeline C background frontend, worn items and place parts are
  entities, contracts 1-200 of the granularity pass with their compiled requirement packages), plug-in off ->
  `runs/<task>/results/`.
- new + plug-in = the plug-in on new's V-V detection, one V-V review of the merged candidates, and scoring with new's
  V-L review -> `runs/<task>/results_with/`.
- V-L severities of new + plug-in are reused from new's scoring (`run_vl_vv_branch_scoring.py --vl-scoring-from`,
  added 2026-11-11 at the owner's request), so both versions report the same V-L score. The option refuses to reuse
  unless the V-L review file, the rendered V-L severity prompt and the V-L scorer input are byte-identical, and it
  re-validates the reused response. Tests: 338 VL/VV + transport tests pass
  (`tests/test_vl_vv_pipeline_sync.py::OfflineChainV6`).
- WeDetect detections of the same keyframes are copied from each v3 case (detector and keyframes unchanged; every
  model judgment runs fresh), as in the 40-video validation.
- Reused: the 40 videos of `../vl_vv_entity_scope_validation_20261111` (same pipeline). Their code differs from the
  snapshot only in the cut-off-reply transport fix (`eec_api_codex_shim.py`, `run_wedetect_shot_entities.py` retry
  pattern) and the new scoring option; only their plug-in scoring runs here (`runs/<task>/reused_from.json`).

## Code and resources

- Frozen code: `code/EECBench` (configs, prompts, schemas, scripts, skills, tests copied at 2026-11-11 20:01 Dubai,
  `SHA256SUMS_code_frozen`, equal to the live tree at that time); data, models, experiments and docs are links to
  the live tree. Later edits of the live tree do not reach this run.
- API: OpenRouter (`openrouter_env.sh`, model `openai/gpt-6-luna`, provider pinned to OpenAI). Key limit USD 1,000,
  USD 884.70 remaining before the run (account credits about USD 3,624 remaining).
- Allocation 370693 (uec-full-g4-1, auh7-1b-gpu-308, 4 x MI210, 43 h left at launch); GPUs 0-3 idle in two samples
  30 s apart (`gpu_probe_370693.json`). One video per GPU at a time: the pipeline's GPU guard needs an otherwise
  empty GPU, and a video holds its GPU for its whole pipeline (median 449 s in the validation), so about 30 h for
  960 videos.
- Budget gate: standard-price estimate of this run's calls, cap USD 140 (expected about USD 106 standard / 125
  billed for 960 videos with both versions).

## Driver

`run_full_new.py` (claims/, stage markers, resumable; `stop_<host>` stops new starts on that host). Logs:
`events.jsonl`, `driver_*.log`, per video `runs/<task>/logs/`.

## Status

- 2026-11-11 20:03-20:17 Dubai: smoke test, both succeeded (`driver_smoke_370693.log`). priority_001__cinetrans: full
  pipeline 637 s on the snapshot code (31 of 36 recorded source paths in `code/EECBench`, the rest case files), 73 calls,
  billed USD 0.1504 for both versions; new V-L 44.93 = new + plug-in V-L 44.93, plug-in scoring made only the V-V call.
  priority_048__wan21 (reused): V-L 41.23 in both versions, one V-V severity call (7 s).
- 2026-11-11 20:23 Dubai: full run launched on 370693 (`driver_370693.log`), GPUs 0-3 re-checked idle just before
  (`gpu_probe_launch_370693.json`), 8 driver threads, cap USD 140 standard. Expected 30-40 h (the smoke video took
  637 s alone; the validation median was 449 s).
- 2026-11-11 21:23 Dubai: owner chose "Add idle GPUs". Extra drivers on idle GPUs of six other allocations owned by
  guangyi.chen (`launch_on_allocation.sh`: two samples 30 s apart right before launch, only idle GPUs used;
  `gpu_probe_launch_<job>.json`, `driver_<job>.log`): 378048 (gpu-206, 2 GPUs), 378049 (gpu-241, 2), 378050 (gpu-238,
  2), 378375 (gpu-319, 1), 378376 (gpu-223, 1), 378377 (gpu-249, 1); 13 GPUs in all with 370693. These zcrl
  allocations had only their sleeping batch script, no step of their own; the busy processes on those nodes belong to
  other jobs (402xxx) with their own GPUs. Not used: 365938 cl-pool4k-1 (its own flux process is assigned to its only
  idle GPU), 371633 retain4 (all GPUs busy), 378051 (node load about 95), 378374 (same node as 378050; one driver per
  node). The zcrl allocations end in about 20 h: drivers start no new video with less than 30 min left
  (`--min-time-left`); a video cut off by an allocation end is moved aside and rerun on 370693. Claims now record
  host and allocation (`host job pid`), so two drivers on one host never take the same video.
- 2026-11-11 22:35-23:01 Dubai: drained (stop files on all hosts; 168 succeeded, 2 failed) for three code changes, applied
  to the live tree and to `code/EECBench` (hashes after the change: `SHA256SUMS_code_after_2026111123`; the snapshot again
  equals the live tree; 344 VL/VV + transport tests pass):
  1. Plug-in U1 has no 30-object cap (owner: "Remove the cap"). The cap was an assistant choice of the 2026-11-10
     experiment, not in the U1 prompt; under the new scope one shot (priority_016__storymem Shot1) exceeded it in all
     9 attempts. `u1_object_counts.py`: old scope 5,000 shots, max 21, never fired; new scope 563 shots, median 3,
     max 32, 1 over 30. `cap_affected.py`: no passed shot had been shortened by the cap; priority_016__storymem's
     plug-in is rerun (old output kept as `results_with_cap30/`).
  2. Per-GPU lock (owner: "应用提速"): `scripts/gpu_lock.py`; with EECBENCH_GPU_LOCK_DIR set, every GPU subprocess of the
     frontend (Grounding DINO recovery, background Grounding DINO, DINO) runs under `flock <dir>/<uuid>.lock`, waits 5 s
     after the previous holder, then keeps its own idle check. Unset by default. The driver's `--slots-per-gpu 3` lets
     three videos share a GPU; their API stages run in parallel. Reason: a video held its GPU for its whole pipeline
     (median 474 s) but used it about 195 s.
  3. Transport: a reply with status "failed" and no output text (priority_033__holocine V-V item W5) is retried like a
     cut-off reply (status checked before the text is read). The failed attempt is in `failed_attempts/` and reruns.
  Driver events now go to `events/<host>_<job>.jsonl` (drivers on several hosts garbled one line of the shared
  `events.jsonl`, which keeps the events before 23:00).
- 2026-11-11 23:0x Dubai: relaunched on all seven allocations with three slots per GPU (`driver_<job>_slots3.log`).

- 2026-11-12 03:07 Dubai: all seven drivers finished (`driver_finished` in every `events/*.jsonl`). 995 of 1,000 done.
  Five failed at the pipeline stage:
  - Four were blocked by OpenRouter's OpenAI input moderation (HTTP 403 "requires moderation", not charged, not
    retryable): priority_064__holocine, priority_064__wan21, priority_064__wan22 and priority_080__holocine
    (`moderation_blocked.json`). They are left unfinished; whether to rerun them through direct OpenAI is the owner's
    decision.
  - priority_127__holocine: its V-V review rewrite was still invalid after 8 repair rounds. The failed attempt was
    moved to `failed_attempts/` and rerun from prepare on 370693 GPU 0 (`driver_rerun_127.log`, 03:09-03:22 Dubai),
    which succeeded.
  - Wall clock: about 6 h 45 min from the 20:23 launch to 03:07, including the 26-minute drain; 23:03-03:07 with
    three slots per GPU. Median per video 903 s (start to all five stages).
- 2026-11-12 03:2x Dubai: `summarize_full_new.py` (now also counts the calls of unfinished videos and of failed
  attempts) → `summary.json`, 996 videos.
  - Mean scores, new vs new + plug-in:
    - UEC 82.02 / 81.62
    - V-L 63.64 / 63.64 (identical in 996/996)
    - within 96.55 / 96.71
    - cross 85.86 / 84.52
  - Model order is the same in both versions: StoryMem, HoloCine, Wan2.2, Wan2.1, CineTrans. UEC in new:
    91.69 / 86.80 / 85.82 / 78.00 / 67.82; in plug: 91.52 / 86.59 / 85.34 / 77.50 / 67.22.
  - Confirmed V-V issues: 3,023 → 3,417. Those with an unspecified subject: 319 (10.55%) → 830 (24.29%); as a share
    of all confirmed issues (V-L 12,643): 2.04% → 5.17%.
  - Ledger: 22,122 specified and 8,071 unspecified entities.
  - Within-shot scores rose slightly for some models with the plug-in: the merged V-V review re-verifies every
    candidate, so its verdicts on new's candidates can differ from new's review.
  - Usage (standard estimate at the GPT-6 Luna direct price, not a bill; billed = OpenRouter `usage.cost_usd`):
    - this run: 71,241 calls, 1,207.4 M input (445.0 M cached), 58.1 M output; standard USD 109.73; billed
      USD 128.77.
    - failed attempts and blocked videos: 200 calls; standard 0.29; billed 0.34.
    - Billed total of this run: USD 129.11 (the earlier rejected U1 attempts of priority_016 are in
      `runs/priority_016__storymem/results_with_cap30/` and included).
    - Standalone, per version over 996 videos (the 40 validation videos' new calls were made by the validation run):
      - new: standard 90.20, billed 106.64 (1 call without a bill)
      - new + plug-in: standard 105.79, billed 123.99 (3 calls without a bill)
    - OpenRouter bills uncached input at USD 0.125/M vs 0.10 direct.
- 2026-11-12 09:36-09:49 Dubai: owner chose "Rerun via OpenAI" for the four moderation-blocked videos.
  - Driver change: `run_full_new.py --provider openai` uses `openai_api_env.sh` and sets EECBENCH_API_PROVIDER=openai.
    The default is unchanged (openrouter); the pre-change copy is `failed_attempts/run_full_new.py.before_provider_option`.
  - The blocked attempts were moved to `failed_attempts/<task>_attempt1_openrouter_moderation`, then rerun from
    prepare on 370693 GPUs 0-3 (re-probed idle; `driver_rerun_openai.log`). The first request recorded backend
    `openai_api`. All four succeeded.
  - Their 306 calls have no billed amount in the call records. Standard estimate: 4.90 M input (1.80 M cached), 0.23 M
    output, USD 0.44.
- `summary.json` re-run with all 1,000 videos:
  - Mean scores, new vs new + plug-in:
    - UEC 82.01 / 81.61
    - V-L 63.64 / 63.64 (identical in 1,000/1,000)
    - within 96.56 / 96.71
    - cross 85.85 / 84.50
  - Each model now has 200 videos. UEC in new / plug:
    - StoryMem 91.69 / 91.52
    - HoloCine 86.77 / 86.54
    - Wan2.2 85.83 / 85.34
    - Wan2.1 77.96 / 77.45
    - CineTrans 67.82 / 67.22
  - Confirmed V-V issues with an unspecified subject: 319/3,039 (10.50%) → 833/3,437 (24.24%). As a share of all
    confirmed issues (V-L 12,684): 2.03% → 5.17%.
  - Ledger: 22,190 specified and 8,093 unspecified entities.
  - Cost of this run:
    - OpenRouter billed USD 129.11: 128.77 for the finished videos plus 0.34 for failed attempts and blocked attempts.
    - Direct OpenAI, standard estimate: USD 0.44 for the four reruns.
    - Whole run at the standard estimate: USD 110.45 (110.17 + 0.29).
  - Standalone per version, standard estimate:
    - new: USD 90.55
    - new + plug-in: USD 106.19
    - Their billed figures leave out the direct-OpenAI calls (237 / 292 calls without a bill).
- 2026-11-12 Dubai: owner asked to update the results page and report unspecified-entity metrics for C, C + plug-in,
  new and new + plug-in. All computations below made zero model calls; they ran on 370693.
  - `unspecified_entity_metrics.py` → `unspecified_entity_metrics.json`
    - Entities: the ledger (pb = specified, ge = unspecified) plus the entities added by that version's detection
      (unspecified).
    - An entity "has a problem" when it is a subject of at least one confirmed issue; context references are
      excluded.
    - Results, C / C + plug / new / new + plug:
      - unspecified share of entities: 22.45 / 23.96 / 27.50 / 28.89%
      - unspecified share of confirmed V-V issues: 3.75 / 8.19 / 10.50 / 24.24%
      - specified entities with a V-V problem: 12.80 / 12.94 / 10.95 / 10.63%
      - unspecified entities with a V-V problem: 3.32 / 6.71 / 4.79 / 11.16%
      - ledger unspecified only: 2.00 / 4.44 / 2.64 / 7.27%
      - added entities: 53.7 / 26.1 / 58.3 / 45.2%. These are biased high, because detection adds them for a
        candidate.
  - `cost_four_versions.py` → `cost_four_versions.json`. Standalone standard estimates, not bills:
    - C USD 78.93. This includes the first clustering/binding pass that C took from v3 (USD 8.61); the C page's
      70.32 left it out.
    - C + plug USD 89.00
    - new USD 90.55
    - new + plug USD 106.77. This includes new's reused V-L severity call. Billed (OpenRouter) for new + plug:
      124.64.
  - `build_results_page.py` → `results_page.html`. It replaces the three-version page and keeps the same URL,
    https://claude.ai/artifact/A3JH7bxSu4wB3zh7TM8XUC (version 2; private until the owner shares it). Palette:
    the first four slots of the dataviz reference categorical palette. The validator was not run (no node on the
    cluster); every bar carries a direct value label.
