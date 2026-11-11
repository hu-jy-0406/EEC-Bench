# Full first-200 evaluation, third version (2026-11-09)

Times are Dubai time.

## Why

Owner, 2026-11-09: rerun the first 200 episodes (5 models, 1,000 videos) with the V-V detection change as the
first version of the results ("先用V-V的改动把前200条重新跑一遍，然后看看结果，作为初版"), keeping reasoning effort
low and adding the rule that walls, floors, ceilings and the ground are part of their place ("“开跑前要定的两件事”我都同意").
Live code: chain v6, GPT-6 Luna, reasoning low; V-V detection one call per checklist item (live 15:31,
`../vl_vv_checklist_traversal_20261109/REPORT.md`) and the wall/floor rule (live 16:19,
`../vl_vv_walls_part_of_place_20261109/REPORT.md`). The second run (`../vl_vv_full_first200_v2_20261109`, 218 videos
with the earlier V-V version) is not reused.

## How

- `run_full.py` copied from the second run (only the docstring differs). `--tasks reuse`: the 668 videos the first run
  (`../vl_vv_full_first200_20261107`) finished keep their frontend case and V-L detection/review (unchanged stages;
  the transport additions of 15:31 are used only by per-item V-V calls) and rerun V-V detection, V-V review and
  episode scoring. `--tasks full`: the whole pipeline (CPU frontend) for the other 332. Shared claims.
- `reuse_p`: the 40 videos of the earlier A/B sample (`sample_task_ids.txt`) first, as the baseline of the worn-item
  entity pilot (`../vl_vv_worn_entities_pilot_20261109`); `reuse_a`: the remaining reused videos.
- Allocation 365937 skipped (178 of 192 GiB memory in use at the probe); 356506 ended at 16:21.
- Probes and start lines: `runs.log`.

## Expected

Reuse about 2 h; full pipelines about 10 h with 17 CPU workers (about 2 videos per worker-hour). Cost estimate about
USD 50 (GPT-6 Luna standard estimate, not a bill); actual usage reported when done.

## Speed-up (owner request 17:2x: "前两百条的重跑能不能加加速")

- 17:20-17:26: six GPU workers added for the full pipelines on idle GPUs of owned allocations, each GPU idle in two
  samples 30 s apart just before launch (`gpu_probe*_*.json`): `gpu_b1` (356508 GPU 0, first as a test of the GPU
  path: detect, match and dino_prepare in about 3 min), `gpu_b2` (356508 GPUs 1-3), `gpu_c2` (356509 GPUs 1 and 3;
  its GPUs 0 and 2 are busy with other work). The pipeline checks each GPU again before its GPU stages. 356507 had
  no GPU that passed the check. 365936/365937 skipped (host memory nearly full).
- The full-pipeline videos are therefore a mix of CPU frontends (`cpu_*`) and GPU frontends (`gpu_*`, WeDetect,
  Grounding DINO and DINO on GPU); the controller records the device per attempt. Small numeric differences in the
  detector are possible; the model stages are identical.
- `reuse_b` (4 more reuse workers on 365936) after `reuse_p` finished.
- 19:36: `runs/cpu_{b,c,d}/DRAIN` set: the CPU workers finish their current task (about 24 min each) and stop; the
  remaining unclaimed full-pipeline videos go to the six GPU workers (about 4.5 min each), which shortens the tail.

## Result (finished about 20:02; analysis 20:30-21:00)

1,000/1,000 videos succeeded (668 reuse, 332 full: 134 CPU frontend, 198 GPU frontend), no failed attempt.
Sanity checks (`sanity_check.py`, `scan_logs.py`): every task ran V-V detection per item (17 item calls; 27 tasks
with 1-2 repair rounds), all with the same V-V item prompt (SHA-256 aba772ad..., the 16:18 wall rule); confirmed
counts match the scoring statistics; the GPU guard logs show only our own processes. One evaluation per video; not
human-calibrated.

Scores and counts (`analyze_results.py` -> `results_summary.json`; means over videos):

| model | V-L | within | cross | V-V | UEC | confirmed V-L | confirmed V-V (within / cross) |
|---|---|---|---|---|---|---|---|
| StoryMem | 44.82 | 85.76 | 74.22 | 79.99 | 68.27 | 720 | 307 (106 / 201) |
| HoloCine | 27.33 | 86.38 | 86.70 | 86.54 | 66.80 | 1,630 | 191 (97 / 94) |
| Wan2.2 | 44.63 | 88.51 | 28.93 | 58.72 | 54.02 | 697 | 840 (91 / 749) |
| CineTrans-DiT | 1.58 | 73.70 | 54.25 | 63.98 | 43.18 | 7,219 | 601 (231 / 370) |
| Wan2.1 | 14.27 | 84.90 | 21.27 | 53.09 | 40.15 | 1,865 | 996 (114 / 882) |
| all | 26.53 | 83.85 | 53.08 | 68.46 | 54.49 | 12,131 | 2,935 (639 / 2,296) |

Old vs new on the 668 reuse videos (same frontend and V-L branch): confirmed V-V 1,037 -> 1,993 (within 110 -> 422,
cross 927 -> 1,571), V-V 80.25 -> 68.65, UEC 62.63 -> 54.88, V-L 27.39 -> 27.34 (severity calls rerun).

Unspecified-entity metrics (definitions in `analyze_results.py`: specified = ledger pb with a detected occurrence,
unspecified = ledger ge; agent-added n entities are not in the denominators; "has a problem" = subject of at least
one confirmed issue):

- Share of entities: unspecified 2,335 / 16,869 = 13.8% (CineTrans 4.7%, HoloCine 11.2%, StoryMem 17.9%, Wan2.1
  14.1%, Wan2.2 19.5%); among entities detected in two or more shots 278 / 8,543 = 3.3%. 29 more agent-added n
  subjects.
- Share of issues: confirmed V-V issues with an unspecified subject 52 / 2,935 = 1.8% (27 with a ledger ge subject,
  25 with only agent-added n); over all confirmed issues 52 / 15,066 = 0.35%. Old vs new on the reuse videos: 42 /
  1,037 = 4.1% (all n, mostly agent-added walls and background parts) -> 31 / 1,993 = 1.6% (13 ge, 18 n).
- Per entity (V-V): specified 1,832 / 14,534 = 12.6%, unspecified 26 / 2,335 = 1.1%; recurring only 1,718 / 8,265 =
  20.8% vs 3 / 278 = 1.1%. Contract entities with a confirmed V-L issue 4,484 / 14,675 = 30.6% (V-L or V-V 35.4%).
  Reuse videos old vs new: specified 7.7% -> 13.1%, unspecified 0% -> 1.0%.

Wall/floor issues (owner question 20:1x, `wall_issue_audit.py`, `draw_wall_category.py` -> `wall_category/`): of the
42 old issues counted unspecified on the reuse videos, 21 had an agent-added wall/floor/ground subject. In the new
run 12 of them are confirmed with the contract place as subject (specified), 4 with another contract entity (pool
tiles, window, shelves, curtains), 5 are not confirmed. WeDetect produced no wall/floor/ceiling candidate in any
keyframe of these videos (its vocabulary has such words; score floor 0.4), and 9 of the 12 places' contract
descriptions name the wall or floor. Upper bound if background parts counted as unspecified entities: 85 confirmed
setting/background issues have only a place as subject (`place_issue_count.py`), share at most about 4.7%.
Examples with boxes: `unspecified_examples/`, issue list `unspecified_issues.json`.

Usage of this run's new calls (`rerun_usage.py` -> `rerun_usage.json`; GPT-6 Luna standard API estimate, USD
0.10/M uncached input, 0.01/M cached input, 0.50/M output, cached input a subset of input; not a bill): 25,124 calls
(367 repair), 672,548,146 input tokens (305,389,189 cached), 13,108,186 output, USD 46.323881. Reuse (V-V detection,
V-V review, scoring only) USD 26.323628; full pipelines USD 20.000252 (CPU frontend 8.063748, GPU frontend
11.936504). V-V detection 17,030 calls, USD 31.787001 (69%). Wall clock 16:23-20:02 (about 3 h 40 min); mean
pipeline time per video: reuse 61.5 s, full GPU 277.2 s, full CPU 1,557.1 s.

Summary page for the owner's mentor (22:30, private until the owner shares it): https://claude.ai/artifact/Bh9UA2dU9PW3beHf2EaVPp
(source `report_page.html`; numbers from `results_summary.json`, `wall_issue_audit.json`, `place_issue_count.py`,
`rerun_usage.json`).

Scores rescored (owner made the per-shot rule the default, 2026-11-09 evening; pipeline-sync session): the stored
`episode_scoring/result.json` files and the score table above use the old product rule. Current scores (rule
`s = 100*exp(-sum(D)/(100*S))` per dimension, same per-issue D): `../vl_vv_score_formula_20261109/rescored.jsonl`
and its REPORT.md (UEC StoryMem 91.22, HoloCine 87.57, Wan2.2 86.17, Wan2.1 77.22, CineTrans-DiT 67.61, all 81.96).
On the 668 reuse videos under the new rule (`rescore_reuse_old_new.py` -> `rescored_reuse_old_new.json`, new side
matches rescored.jsonl within 0.005): V-V 94.98 -> 91.24, UEC 84.87 -> 82.29 (old -> new). Issue counts and all
unspecified-entity metrics do not depend on the rule. The mentor page (version 2, about 23:15) uses the new scores.
