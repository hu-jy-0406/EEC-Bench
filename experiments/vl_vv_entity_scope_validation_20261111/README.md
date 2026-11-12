# 40-video validation of the new default pipeline (2026-11-11)

Times are Dubai time. Experiment folder; nothing committed.

## Owner requests

- 2026-11-11: "所有类别都加吧，同步改contract" (worn items and place parts are entities, contracts 1-200 rewritten);
  C default with the unspecified branch as a plug-in.
- 14:3x: "先用空闲卡，等uec自己的分配下来再转"; "在逻辑允许的情况下尽可能多地复用之前的detection结果".

## What runs (`run_validation.py`)

The 40 videos of `../vl_vv_full_first200_v3_20261109/sample_task_ids.txt` (8 per model). Per video: a fresh case
from the v3 keyframe manifest and the new contract with its recompiled requirement package; live
`run_vl_vv_pipeline.py --mode full` (background frontend on, plug-in off) -> `results/`; then the plug-in, one merged
V-V review and scoring with the same V-L review -> `results_with/`.

Reuse of earlier detection results: the v3 case's WeDetect run of the same keyframes is reused
(`--reuse-detections`; clustering checks frame coverage and image hashes), so WeDetect does not run again. Everything
that depends on the changed rules or contracts runs fresh: shot clustering (new entity rules), binding and prompt
recovery (new contract entities), background discovery and box choice (new prompt), the second detection pass,
matching, V-L and V-V. The earlier C run's model outputs are not reused because each of them was made under the old
entity rules or contracts.

Scheduling: one driver per allocation, one checked GPU per video for its whole pipeline, tasks shared through
`claims/`, `stop_<host>` stops a driver from starting new videos (to move to the UEC allocation when it starts).
Budget gate USD 8 (standard-price estimate).

## Status

- 14:35 Dubai: started on idle GPUs of two cl-pool allocations owned by guangyi.chen (385762 node 304 GPU 0, UUID
  GPU-037d471d36c83639 zero-padded from rocm-smi's 15-digit id as rocminfo prints it; 385763 node 231 GPU 1); the
  other GPU of each node runs another task and was not touched. Both idle in two samples 30 s apart
  (`gpu_probe_*.json`); node loads 4.6 and 18 of 128. uec-full (370693) and eec-eval (230237) are pending.

`summarize_validation.py` -> `summary.json` compares v3, C, C + plug-in (old scope) with new and new + plug-in on the
finished videos.
- 14:48 Dubai: paused at the owner's request ("先暂停一下，需要改一下api调用"): stop files for both hosts, drivers
  stopped, no validation process left on nodes 304 and 231. Finished: priority_013__cinetrans and
  priority_075__cinetrans (both arms). Interrupted mid-pipeline: priority_036, 047, 048, 096, 109, 126 (CineTrans);
  their run folders and claims must be removed before a rerun. About USD 0.18 spent on the two finished videos
  (standard-price estimate) plus the interrupted partial calls.
- 15:0x Dubai: switched to OpenRouter (`../openrouter_switch_20261111/README.md`); the OpenAI-direct runs (2 finished,
  6 interrupted) moved to `openai_direct_20261111/`. Check: #013 and #075 rerun with OpenRouter on the cl-pool GPUs,
  all calls succeeded with billed cost (USD 0.1362 and 0.0924 billed vs 0.1165 and 0.0784 at the direct standard
  price); scores and counts differ from the direct runs within run-to-run variation.
- 15:17 Dubai: uec-full (370693, node 308, 4 GPUs, a holding allocation running only `sleep infinity`) started; all
  four GPUs idle in two samples 30 s apart (`gpu_probe_370693.json`), OpenRouter reachable. The remaining 38 videos run
  there only (driver_370693.log); the cl-pool GPUs are no longer used.
- 16:35 Dubai: driver on 370693 finished, 39 of 40 succeeded. priority_048__wan21 failed at matching: one OpenRouter
  reply was cut off mid-string (768 output tokens, invalid JSON). Fix in the shim (non-completed status or incomplete
  JSON -> "OpenAI API incomplete", retried by the existing transport retry; the cut-off call's billed usage is kept as
  a `response.incomplete` event), see `../openrouter_switch_20261111/README.md`. 347 tests pass
  (`tests_after_incomplete_fix.txt`).
- Rerun of priority_048__wan21 on 370693 GPU 0 (idle: 0%, 13 MB, no KFD process on it; the other user's processes on
  node 308 use four GPUs outside this allocation). Attempt 2 stopped at its first stage because the shim was edited
  while it ran (the pipeline's immutable-source check); attempt 3 (16:58-17:12 Dubai) succeeded. Both failed attempts
  are in `failed_attempts/` and are counted separately. 40 of 40 complete; no further cut-off reply occurred.

## Results (40 videos, `summary.json`, `per_model_uec.json`)

| version | UEC | V-L | within | cross | confirmed V-V | with unspecified subject | share of V-V | confirmed V-L | share of all | ledger specified / unspecified |
|---|---|---|---|---|---|---|---|---|---|---|
| v3 | 82.36 | 65.58 | 97.23 | 84.26 | 122 | 0 | 0% | 470 | 0% | 539 / 93 |
| C | 81.40 | 63.16 | 96.46 | 84.57 | 123 | 1 | 0.81% | 512 | 0.16% | 539 / 185 |
| C + plug-in | 81.71 | 63.29 | 97.10 | 84.74 | 120 | 8 | 6.67% | 512 | 1.27% | 539 / 185 |
| new | 82.69 | 64.63 | 98.27 | 85.18 | 102 | 13 | 12.75% | 485 | 2.21% | 815 / 304 |
| new + plug-in | 82.30 | 65.16 | 98.17 | 83.56 | 127 | 40 | 31.50% | 485 | 6.54% | 815 / 304 |

- v3, C and C + plug-in are the earlier runs on the same 40 videos (old entity rules and contracts; v3 per-shot
  rescoring). The plug-in variants reuse the same V-L review; their V-L score differs because the scoring stage rates
  severity again (run-to-run variation, not a plug-in effect).
- Model order (UEC): StoryMem > HoloCine > Wan2.2 > Wan2.1 > CineTrans in v3, C, C + plug-in and new; new + plug-in
  swaps HoloCine (85.72) and Wan2.2 (85.91). 8 videos per model; differences of this size are within run-to-run
  variation.
- Unspecified-subject issues are counted from the ledger labels (pb specified, ge/n unspecified); precision of these
  issues was not checked by a person.

Cost and time (OpenRouter billed amounts, `usage.cost_usd`; standard-price estimate = GPT-6 Luna direct price, not a
bill):
- new (pipeline, 40 videos): 2,189 calls; 42,764,201 input tokens (17,348,360 cached, 25,415,841 uncached),
  1,519,473 output; billed USD 4.1100 (0.103 per video); standard estimate USD 3.4748 (0.087 per video; not comparable with
  the C run's 0.070 per video, which lacks C's first detection pass, see "Cost by version").
- plug-in + merged review + scoring: 749 calls; 5,793,131 input (464,143 cached), 822,846 output; billed USD 1.0821
  (0.027 per video); standard estimate USD 0.9490.
- Failed attempts of priority_048__wan21: 63 calls, billed USD 0.0633. Direct-OpenAI runs before the switch
  (`openai_direct_20261111/`): 221 calls, standard estimate USD 0.3131 (the OpenAI bill is not available here).
- Validation total billed on OpenRouter: USD 5.2554 (plus the smoke test, below USD 0.001).
- Pipeline time per video: median 449 s, maximum 728 s (one GPU per video, up to 4 videos in parallel on 370693).

## Cost by version (same 40 videos; `cost_by_version.py` -> `cost_by_version.json`, zero model calls)

Standalone cost = the API calls one version needs on its own. v3 and C ran on direct OpenAI (standard-price estimate
only, GPT-6 Luna USD 0.10/M uncached input, 0.01/M cached, 0.50/M output; the OpenAI bill is not available here);
new and new+plug ran on OpenRouter (billed `usage.cost_usd`; uncached input bills at USD 0.125/M). WeDetect, Grounding
DINO and DINO are GPU stages without API calls.

| version | calls | input (cached) | output | standard USD | per video | billed USD |
|---|---|---|---|---|---|---|
| v3 | 1,327 | 30,116,299 (12,286,899) | 878,170 | 2.3449 | 0.0586 | n/a |
| C | 2,103 | 37,018,967 (14,275,026) | 1,250,739 | 3.0425 | 0.0761 | n/a |
| C + plug-in | 2,550 | 39,206,869 (14,871,613) | 1,711,522 | 3.4380 | 0.0860 | n/a |
| new | 2,189 | 42,764,201 (17,348,360) | 1,519,473 | 3.4748 | 0.0869 | 4.1100 |
| new + plug-in | 2,788 | 46,081,931 (17,812,503) | 2,203,738 | 4.1069 | 0.1027 | 4.8134 |

- Two corrections against the earlier full-run comparison (`../vl_vv_full_first200_c_20261110/cost_compare.py`):
  (1) v3 reuse-mode outputs link `vl_detection/` and `vl_review/` to the first run as symlinks, which `Path.rglob`
  does not enter, so the V-L calls of the 668 reuse videos were not counted (all 40 sample videos are reuse videos:
  89 calls, USD 0.4594); (2) the C run took its first detection pass (clustering + prompt binding) from the v3 case
  instead of calling the model, so C's "as run" cost lacks it (384 calls, USD 0.3308 on these 40 videos). Both are
  added above. The full-run totals (v3 USD 53.23, C USD 70.32, C + plug-in USD 88.08) have NOT been recomputed.
- Plug-in versions: standalone = base without the base V-V review and scoring (replaced by the merged review and
  scoring) plus the plug-in calls. As run in this experiment (both arms): C + plug-in USD 3.4136 (without the reused
  pass 1), new + plug-in USD 4.4238 standard / 5.1920 billed.
- By stage, standard USD (v3 / C / C+plug / new / new+plug): frontend 0.388 / 0.904 / 0.904 / 1.112 / 1.112;
  V-L detection + review 0.459 / 0.465 / 0.465 / 0.627 / 0.627; V-V detection 1.225 / 1.368 / 1.368 / 1.419 / 1.419;
  plug-in detection - / - / 0.441 / - / 0.619; V-V review 0.241 / 0.270 / 0.237 / 0.285 / 0.308; scoring 0.032 /
  0.036 / 0.024 / 0.032 / 0.023.
- new vs C (standard): +14.2% (frontend +23%, V-L +35%, V-V detection +4%); new + plug-in vs C + plug-in +19.5%.
- Not included: the failed attempts of priority_048__wan21 (63 calls, billed USD 0.0633) and the direct-OpenAI runs
  before the switch (221 calls, standard USD 0.3131).
