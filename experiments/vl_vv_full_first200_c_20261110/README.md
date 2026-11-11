# First-200 full run with pipeline C, without and with the unspecified plug-in (2026-11-10/11)

Times are Dubai time. Experiment folder only: no live pipeline, AGENTS.md or paper change, no commit.

## Owner request

2026-11-10 ~21:45: "我希望的是新流程把C设为默认，然后把这个unspecify专属分支作为plug in。今晚11点之前把这个新分支调好，然后我睡觉的
时候你用带/不带这个分支的C把200个episode全量开跑。"

## What runs (`run_full_c.py`)

All 1,000 videos of the first-200 rerun v3 (`../vl_vv_full_first200_v3_20261109`, read-only sources: case folders with
the original WeDetect detections; the rerun v3 results are the "current pipeline" baseline).

- C frontend, as overnight arm B (`../vl_vv_background_discovery_20261110`, frozen code `code/EECBench`): discovery
  (one Luna-low call per shot), Grounding DINO on the listed frames (GPU, pinned by UUID), box choice (one Luna-low
  call per shot, one retry), augmented detections (originals unchanged), then fresh shot clustering, detect (binding +
  prompt recovery, GPU) and matching.
- C evaluation, as overnight arm C: V-V detection, review and scoring with `code_vv/EECBench` (17 items + W8, X10);
  V-L detection and review with `code/EECBench`. Output `runs/<task>/results/` = C without the branch.
- Plug-in, round 3 of `../vl_vv_unspecified_branch_20261110` (U1 wider inventory, medium; U2 by rule; U3 with
  anchors, high): its real findings are appended to C's V-V candidates (issue ids and added-entity keys continue C's
  numbering), one V-V review of all candidates and scoring with C's V-L review. Output `runs/<task>/results_with/`.
- Scheduling: one driver per allocation (356508 and 356509, 4 GPUs each, all idle in two probes 30 s apart; one
  slot per GPU for the GPU stages), 8 videos at a time per driver; tasks shared through `claims/`; every stage has a
  marker so a video resumes where it stopped. Budget gate on the standard-price estimate of all calls.

## Estimates (before launch)

- Cost (GPT-6 Luna standard-price estimate, not a bill), from the overnight arms and round 3: C about USD 0.073 per
  video (full pipeline 0.062, discovery and box choice 0.004, W8/X10 0.006), plug-in about USD 0.020 per video
  (branch 0.012, second V-V review and scoring 0.008): about USD 93 for 1,000 videos. Cap USD 110.
- Time: about 4 minutes of stages per video (GPU about 75 s of it); with 8 GPUs and 16 videos at a time, about 4-6
  hours.

## Status

- Single-video test #078 (21:53-22:00 Dubai): all 16 stages succeeded
  after one fix (Grounding DINO requires the GPU UUID in ROCR_VISIBLE_DEVICES). 30 boxes added by the C frontend;
  plug-in 7 suspects, 4 real, appended as V10-V13. Scores: C uec 87.58 (V-L 95.92, V-V within 95.92, cross 70.91);
  C + plug-in uec 88.15 (within 98.35, cross 70.18). The with-plug-in variant reviews all candidates again, so its
  main-candidate verdicts can differ from C's own review (here within-shot rose). Cost USD 0.109 (standard-price
  estimate) for this 6-shot video; about 6.5 minutes of stages in sequence (detect 75 s on GPU).
- Revised estimate: about USD 100 for 1,000 videos (cap 120); with 12 videos at a time per driver (24 in all) and 8
  GPUs, about 4.5-5 hours.
- Owner chose the merged review for the plug-in variant ("保持合并复核"). Launched 22:27 Dubai: drivers on 356508
  (node 289, GPUs 0-3) and 356509 (node 319, GPUs 0-3), 12 videos at a time each, cap USD 120. Node 319 GPU 0 failed
  ("No HIP GPUs are available"; its unique id 0x763c831cad37d9b has 15 hex digits, so the UUID string the probe
  builds does not match): that driver was stopped at 22:29 and relaunched at 22:30 with GPUs 1-3 only (all idle in a
  new probe); interrupted call folders are now removed before a stage reruns. #004 HoloCine failed at grounding on
  that GPU and resumes from its stage markers.
- 23:45 check: 217 videos finished, no failure since the 22:30 relaunch; USD 20.92 spent (standard-price estimate),
  about USD 0.09 per video. 10 videos (#003 StoryMem/Wan2.1/Wan2.2, #004 all five, #005 HoloCine/StoryMem) failed during
  the 22:27-22:30 incident: the stopped processes left a grounding output folder or a clustering `case/entities`
  folder, which the scripts refuse on rerun. The driver now removes those folders before the stage reruns (running
  drivers keep the code they loaded). These 10 are rerun with `--only` after both drivers finish (their claims are
  removed first; GPU stages must not overlap the running drivers).
- 05:58: both drivers finished, 990 of 1,000 succeeded. 06:00-06:22: the 10 failed videos were rerun on node 319
  GPUs 1-3 (idle in two probes 30 s apart, `gpu_probe_rerun_356509.json`; `rerun_tasks.txt`, `driver_rerun_356509.log`):
  all 10 succeeded. 1,000 of 1,000 complete; wall time 22:27-06:22 (longer than the 4.5-5 h estimate).

## Results (`summarize_full.py` -> `summary.json`)

The current-pipeline baseline (v3) uses its per-shot rescoring (`../vl_vv_score_formula_20261109/rescored.jsonl`); its
stored result.json files hold the old product scores and are not comparable. C and C + plug-in use the per-shot rule.

| Model | UEC v3 | UEC C | UEC C+plug | Unspecified-subject confirmed V-V: v3 / C / C+plug | Plug-in confirmed units |
|---|---|---|---|---|---|
| CineTrans | 67.61 | 67.50 | 67.51 | 11 / 16 / 29 | 19 |
| HoloCine | 87.57 | 87.10 | 86.88 | 6 / 10 / 27 | 19 |
| StoryMem | 91.22 | 90.95 | 90.83 | 6 / 19 / 42 | 25 |
| Wan2.1 | 77.22 | 76.66 | 76.89 | 18 / 32 / 74 | 47 |
| Wan2.2 | 86.17 | 85.47 | 85.25 | 11 / 40 / 91 | 57 |
| All (1,000) | 81.96 | 81.54 | 81.47 | 52 / 117 / 263 | 167 |

- Model order is the same in all three arms. All confirmed V-V issues: 2,935 / 3,121 / 3,213. Plug-in: 978 candidates,
  167 confirmed units (units that contain a plug-in candidate). Whether the added confirmations are real is not
  checked.
- Merged review: of 4,204 C units with the same grouping, 931 (22%) got a different verdict, nearly symmetric
  (confirmed->rejected 360, rejected->confirmed 343, uncertain<->others 228); severity changed in 517; 215 units were
  regrouped. The V-L scores of C and C + plug-in differ by up to 0.6 per model although the V-L reviews are the same
  (only the severity calls ran again). Score differences of this size are within review and scoring variation.
- Cost (GPT-6 Luna standard-price estimate, not a bill): USD 88.08 in all (1.022 G input tokens incl. 0.392 G cached,
  42.2 M output, 59,225 calls): C frontend additions and rerun case 14.91, C evaluation 55.42, plug-in 17.76. Per
  video: C USD 0.070, plug-in USD 0.018.
- Share of confirmed issues with an unspecified subject (`unspecified_share.py` -> `unspecified_share.json`): V-V
  52/2,935 = 1.77% (v3), 117/3,121 = 3.75% (C), 263/3,213 = 8.19% (C + plug-in); V-L has none (0 of about 12,100
  in every arm), so over all confirmed issues 0.35% / 0.77% / 1.72%. With uncertain issues included: V-V 1.82% /
  4.03% / 10.08%. Allocation 356508 ended after the run; the computation ran on 356509.
- Whole-pipeline tokens and cost per version for all 1,000 videos (`cost_compare.py` -> `cost_compare.json`; GPT-6
  Luna standard-price estimate, not a bill): v3 32,371 calls, 723.8 M input (305.7 M cached), 16.7 M output,
  USD 53.23 (including USD 6.91 of first-run frontend and V-L calls that 668 videos reused); C 43,863 calls, 899.7 M
  (367.6 M), 26.9 M, USD 70.32; C + plug-in 59,225 calls, 1,022.5 M (392.0 M), 42.2 M, USD 88.08.
- Results page (owner request 2026-11-11): `build_results_page.py` (from `page_data.json`) -> `results_page.html`,
  https://claude.ai/artifact/A3JH7bxSu4wB3zh7TM8XUC (private until the owner shares it).
