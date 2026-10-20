# Ten-episode V-L/V-V pipeline run

## Scope

Freshly run detection/entity binding, issue discovery, and per-issue review for
Wan2.2, StoryMem, and HoloCine on the same ten episodes. The chosen contract
priority indices are 0, 1, 2, 5, 7, 8, 9, 10, 12, and 13. This avoids all four
episodes used in the previous multimodel pilot. The selection contains 48 shots
per model (144 generated shot videos total) and includes 4-, 6-, and 8-shot
episodes. All selected contract/video paths were checked before extraction.

Episode/model inputs:

- Contracts: `experiments/episode_contracts_20260921/deliverables/episodes/<episode>/contract.json`
- Wan2.2: `experiments/wan_generation_400_20260921/videos/<episode>/ShotN.mp4`
- StoryMem: `data/generated/storymem_200_hf/storymem_outputs/priority100_hpsv3/episodes/<episode>/shots/01_NN.mp4`
- HoloCine: its validated `attempts/<episode>/<attempt>/episode.mp4`, sampled in
  fixed five-second shot windows.

`prepare_inputs.py` stores original-video checksums and six uniform original
keyframes per shot, then creates frozen detector case inputs. Its extraction
uses CPU only. Each case then runs the existing `run_case.sh` stages (WeDetect,
within-shot clustering and prompt recovery, global matching, DINO appearance,
and issue discovery) followed by `run_vl_vv_issue_review.py`. No geometry
registration or scoring stage is included.

## Resources

Use only the user-authorized cards in the existing allocation 214135:

- node 251 physical GPUs 0–5;
- node 302 physical GPUs 0–3.

Before each GPU stage, the existing WeDetect and DINO launch guards check
utilization, VRAM, KFD process mappings, and the physical-index/UUID match. GPU
ordinals are not reused as ROCr visibility masks. CPU workers are pinned to
cores 8–55 on node 251 and 8–39 on node 302; the resident Qwen jobs were
observed pinned to cores 0–7 and 64–71. No other node/cards are used.

Each GPU worker processes all three models for one episode; model order rotates
by worker slot. The pipeline wrapper records total pipeline and review elapsed
time per case. The review runner records its own duration and token usage.

## Reporting

`summarize.py` aggregates successful and failed cases without changing them. It
reports candidate totals, review verdict counts, entity inventory counts,
per-case elapsed time, Luna API response count and token totals. Cached input is
reported separately as a subset of input. USD uses the discovery/review
standard API basis: uncached input $0.10/M, cached input $0.01/M, output
$0.50/M. These are estimates, not actual billing. Candidate counts and model
review judgments are not calibrated final scores.
