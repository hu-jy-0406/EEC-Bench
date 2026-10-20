# Wan2.2 A14B · 400 episodes production campaign

Status: **running**, launched 2026-09-21 UTC. Verified at **2026-09-21T21:10:42UTC: all68workers have entered real diffusion sampling** (each completed at least one step); zero current failed workers. All68claimed shots are in core100, later stages remain pending. The first full production shots have not finished at this snapshot. Check live `workers/*.json`, `queue.json`, and `recovery_status.json`; this report is a launch record, not a completion claim.

## Frozen inputs and settings

- 400 episodes / 2,000 independent shots. Use the completed Wan-specific `wan_prompt_en` exactly, with no extra global concatenation, rewriting or truncation.
- Input snapshot: `input_queue_400.jsonl`, SHA256 `479568f1410beb5706ab3a6373f618bc91ef24e71c1d40a2745a9a0754896174`.
- Wan2.2-T2V-A14B; original checkpoint and official BF16 conversion, no quantization. Original negative prompt. 832×480, 81 frames at 16 fps, 40 UniPC steps, shift12, CFG low/high3/4.
- Each shot spans5.0seconds in frame timestamps; MP4 playback duration is81/16=5.0625seconds. Episode concatenation retains all81frames per shot.
- Seed per shot: first32bits of SHA256(`wan400-v1:<episode_id>/<shot_id>`), preserved in the queue and output metadata.
- Independent-shot Wan: no visual memory, reference images or generated cross-shot conditioning added.

## Priority and output

Strict queue barriers: all500shots of core100 → next500shots (cumulative200) → remaining1,000shots (full400). A claimed shot is marked done only after finite-tensor and complete81-frame decode/dimension validation. Parallel claiming/ownership, stage barriers and one failed-task retry passed a36-task/8-worker compute-side test.

Outputs: `videos/<episode_id>/ShotN.mp4`, exact `.prompt.txt`, timing/seed/checksum `.json`, first/middle/last `.contact.jpg`; once all shots finish, `episode.mp4` and `episode.json`. Concat output is fully decoded and frame-count checked. Source episode/scene metadata remains in the immutable input snapshot.

## Resources and authorization

The user explicitly confirmed that the idle cards in peiyuan.zhu's shared jobs under guangyi.chen were coordinated and could be used for this campaign. No new GPU allocation was requested; no other task was terminated. GPU use, VRAM and KFD processes are rechecked immediately before every launch; binding uses GPU UUIDs. One initially idle card became occupied before launch and was skipped.

| Node | Existing job | Campaign cards |
|---|---:|---:|
|196|196092|7|
|197|196093|7|
|209|200798|8|
|254|200797|7|
|255|194180|8|
|257|204827|7|
|284|204826|6|
|295|204828|7|
|306|206117|4|
|307|194259|7|
|Total||68|

Other occupied cards remain excluded. Existing jobs have different expiry times; earliest is node196 at2026-09-22T17:01:50UTC. The recovery process requeues unfinished shots if an allocation ends; no automatic new allocation or cancellation is permitted by this runner.

## Host-memory and runtime fixes

Most jobs have64GiB host-memory limits despite abundant physical node memory. The original CPU-offload implementation is used on node306 GPU2/3/4. Other workers use `streaming.py`: inactive parameters reside on meta, checkpoint tensors are streamed and converted with the same original CPU BF16 operation, and the original Wan forward/sampling loop is inherited unchanged. Per-node serialized checkpoint copies bound transient RAM. No cgroup limit was raised or bypassed.

A same-prompt/same-seed5-frame/2-step comparison produced **exactly equal tensors**, max absolute difference0, with finite outputs; `streaming_validation.json` contains the full settings/timing. This is a short transport test, not full81-frame/40-step equivalence validation. Full inference is underway.

Nodes257/284 exposed a read-only default MIOpen SQLite database. Failed workers are restarted with independent writable `/tmp/eecbench_wan400_miopen/<worker>` caches. Original failed logs/results remain in `worker_history/` and `logs/`. Recovery also clears inherited Slurm resource environment variables before starting a step in another existing job; the first recovery attempts were rejected by Slurm because they inherited the2TiB parent memory request. No allocation was modified.

`postlaunch_audit.json` records per-node anonymous RAM, OOM-kill deltas and actual KFD mappings. Empty mapping lists mean not observed at that snapshot, not a verified idle GPU. The first postlaunch audit found no new OOM kills or observed GPU sharing with another task.

## Completion-time estimate

Historical full-shot generation+save:1543.973seconds/shot, measured on two full shots. This gives857.763GPU-hours for all2,000shots, or12.61hours at ideal68-card throughput before barriers/initialization/I/O. Current stable diffusion steps are about37seconds; low-memory workers additionally stream expert weights and may wait for their node's loader.

Provisional planning range after startup: core100 about4–5hours, cumulative200 about8–10hours, full400 about15–18hours. These are generation-only extrapolations, not measured campaign completion times; allow revision after complete production shots. They include a practical allowance for loading, phase tails and retries, and exclude downstream benchmark evaluation. Resources must remain available; this is not a guarantee.

Local inference API usage:0tokens / USD0 API charges. GPU/storage billing rates are unavailable.

## Inspect / stop

Run `python campaign.py status` from this directory (or use its absolute path) for a lightweight snapshot. Logs and per-worker heartbeats are updated continuously. `complete.json` is written only after all2,000shots and400episode concatenations finish.

Create `STOP` to stop workers between shots; create `STOP_RECOVERY` to stop the recovery loop. This does not cancel shared Slurm allocations or affect other tasks. Do not rerun `prepare` or overwrite `queue.json`. Restart/reclaim only after proving a prior process is gone and rechecking its GPU.


## 2026-09-22 source revision supersedes the original frozen input for three episodes

User authorized regenerated/new outputs from revised prompts for ranks52/308/349. See prompt_revision_20260922/REPORT.md. Effective full400 input is now prompt_revision_20260922/input_queue_400.v2.jsonl; original snapshot is historical. Rank52 old six-shot episode archived and requeued with original seeds/settings; ranks308/349 not yet generated and refreshed in place. Three episode records updated, only one actual Wan shot text changed. Actual18input tokenizer audit passes,98–194tokens≤512;0APIcalls/0tokens/USD0. Revision is applied/queued, not yet completed.


## 2026-09-22 05:29 UTC — PAUSED by user (supersedes running status above)

202 complete episodes / 1,038 shots saved. 962 unfinished shots retained and pending; 0 running. All68 Wan workers and recovery exited. STOP/STOP_RECOVERY retained. See pause_20260922/README.md and remaining_shots.jsonl. 61 former cards observed idle; node196 seven cards now have other Qwen work, untouched. Resume only on user direction after fresh resource checks.
