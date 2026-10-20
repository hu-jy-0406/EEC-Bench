# CineTrans-DiT ROCm validation and priority-100 run

Updated: 2026-09-25 20:32 UTC

## Resume batch snapshot (2026-09-25 20:15 UTC)

Two episodes currently have validated outputs: priority 1 is an already-valid
skip, and priority 2 completed in 3097.5s. The first workers for priorities
3–10 all failed. Priorities 3–6 and 9–10 failed in VAE decode with
`miopenStatusInternalError`; priorities 7 and 8 subsequently reached all 50
denoising steps but failed at the same decode stage. Each trace reports MIOpen's
shared default `/tmp` find database as readonly. All original logs are retained.

The read-only checker revalidated 22 idle cards within allocation 214135:
node 251 cards 0–7, node 252 cards 0–7, and node 302 cards 2–7. The
`resume_miopen_20260925` batch runs one episode per card on those GPUs. At the
20:14 UTC log check four-shot episodes were at steps 39–40/50 and six-shot
episodes at 21–22/50; none had completed or reached the previous decode error.
The per-card MIOpen cache change is still unverified until a decode succeeds.

After priorities 7 and 8 failed, a fresh checker confirmed node 302 cards 0–1
idle. Dedicated retries for those two priorities started there at 20:12 UTC;
both UUID guards passed, and each uses its own MIOpen cache and run namespace.
There are now 24 workers across 24 GPUs: the 22-worker resume batch plus the
two retries. Total validated output count remains 2. The retries use
`retry_p7_miopen_20260925_worker00_events.jsonl` and
`retry_p8_miopen_20260925_worker00_events.jsonl`; main-batch events and logs
are under `resume_miopen_20260925_worker*`.

### Completion-time estimate

At the 20:14 UTC snapshot, ongoing denoising rates were about 49.5 seconds per
step for four-shot episodes and 89.5 seconds per step for six-shot episodes;
the earlier eight-shot attempt averaged about 140 seconds per step. Using
conservative successful-episode durations of roughly 50/84/128 minutes for
4/6/8 shots and the actual 22-worker priority stripes, the slowest projected
worker path is about 6 hours from that snapshot. Planning range: 6–8 hours,
approximately 2026-09-26 02:15–04:15 UTC, if isolated MIOpen caches pass VAE
decode. This estimate excludes any further decode failure and retry. Allocation
214135 ends at 12:05 UTC, so the estimate currently fits within the allocation.

The runner change is in `run_priority100_serial.py`: it creates isolated
MIOpen/MPL caches, namespaces resumed ledgers/logs, skips explicitly owned
priorities, and archives any invalid old output before retry. The added
`launch_priority100_worker.py` resolves card UUIDs on-node before invoking the
existing UUID guard. Python compilation and `git diff --check` pass.

## Result so far

CineTrans-DiT runs in the existing ROCm `vace` environment on MI210 after a
local, exact p=0 block-mask implementation. Priorities 1 and 2 completed. At
17:54 UTC, a live checker found eight idle candidates within allocation
214135: node252 cards2–5 and node302 cards0–3. Other allocated nodes could not
be counted because SSH host-key verification failed. Eight disjoint
episode-level workers have since been started on those candidates, beginning
at priority 3. At 18:08 UTC, five workers were generating and three corrected
workers had passed the guard and were initializing; the latter cards are
reserved even if short sensor samples still report 0% utilization. The 17:48
inventory of 39 idle cards is historical, not current. Node241 is excluded
because `/dev/kfd` access is denied.

Worker ledgers are
[`run_priority100/serial_batch_worker00_events.jsonl`](run_priority100/serial_batch_worker00_events.jsonl)
through `serial_batch_worker07_events.jsonl`; the original serial history is
also retained at
[`run_priority100/serial_batch_events.jsonl`](run_priority100/serial_batch_events.jsonl).

The priority-1 output is
[`video.mp4`](run_priority100/videos/74Od5-Fmf60_s00006_n4_clean_v2/video.mp4).
It validates at 832x480, 16 fps, 321 frames, 20.063 seconds, 11,450,704 bytes.
The completed run used one card only: the idle MI210 with UUID
`GPU-d79d4a081e34548d`, bound through the workspace UUID guard. All four shot
prompts and the existing final global prompt were reused unchanged. Settings:
50 steps, guidance 6, seed 42, official 832x480 resolution.

## Measured speed and estimate

- Model construction and weight loading: about 57 seconds before generation
  began.
- Denoising: 50 steps in 48m20s, or 58.0 seconds/step.
- Decode and MP4 write: about 4m26s after denoising.
- Full log-start to MP4 modification time: about 53m44s for one 4-shot,
  20-second episode. This is about 0.0062x playback speed.
- Priority 100 has 60 four-shot, 30 six-shot and 10 eight-shot episodes: 500
  shots / 2,500 media seconds. Linear scaling from the measured 4-shot episode
  estimates about 112 hours (4.7 days) on one MI210. Treat this as a rough
  estimate: only the four-shot duration has completed measurement; longer
  episodes may scale differently.
- Allocation 214135 had about 18h remaining at the latest inventory. The current runner
  should therefore complete only a priority prefix, not all 100. Its admission
  guard reserves time for episode execution and stops before allocation expiry.

The full pilot log is
[`priority_001_attempt3.log`](run_priority100/logs/priority_001_attempt3.log).
Two earlier attempts OOMed in stock masked SDPA, including the EFFICIENT
backend attempt. They are preserved as
[`priority_001.log`](run_priority100/logs/priority_001.log) and
[`priority_001_attempt2.log`](run_priority100/logs/priority_001_attempt2.log).

## Implementation and prompt decision

Existing prompts fit CineTrans's interface: pass each shot's current
`wan_prompt_en` unchanged and append the existing `global_prompt_original` as
the final global prompt (`general_prompt: true`). No prompt rewriting or
specialized prompt dataset is needed for this inference compatibility check.
`prepare_priority100_configs.py` wrote the configs and prompt-hash audit under
[`run_priority100`](run_priority100).

The official implementation materializes dense full-video attention masks.
For the selected p=0 configuration, the local `ShotBlockMask` representation
computes each shot block with the globally visible first latent frame and
exposes each shot's own text plus the shared global prompt. Synthetic checks
found exact dense/blockwise equality (maximum absolute error 0) for both
self-attention and text-attention masks. This preserves mask connectivity; it
does not claim pixelwise equivalence to an unmodified full run that OOMs.

The official repository offers optional Ulysses/Ring context parallelism and
FSDP. The current USP forward path replaces self-attention and does not accept
CineTrans's `premask` / `premask_text`; enabling it as-is would not preserve
the benchmark's shot-isolation mask. FSDP shards parameters and is not evidence
of faster single-episode inference. Do not enable multi-GPU same-episode mode
until a mask-aware ROCm path passes equivalence tests. Episode-level parallel
generation preserves the current per-episode settings. The single-card
measurement above is still the only speed measurement; do not claim measured
parallel speedup or recompute full-100 ETA from the new pool until episodes
complete.

## Operational notes

The first serial-runner launch mistakenly tried to repeat priority 1 because
system `ffprobe` is absent on compute nodes. That duplicate step was terminated
after about 54 seconds; the original MP4 remained intact. The runner now uses
the `imageio_ffmpeg` binary bundled in `vace`, and this check was validated on
node260 with a CPU-only step. A per-episode launch also rechecks Slurm time
left, then runs `guard_geocalib_boxer_gpu.py` to check utilization, VRAM,
resident GPU mappings, and the device UUID before model execution.

Three initial worker starts failed before generation because short ROCm IDs
were not padded to 16 hexadecimal digits. `guard_geocalib_boxer_gpu.py` now
normalizes the ID before comparing and setting `ROCR_VISIBLE_DEVICES`; a HIP
probe then passed, and all three retried workers passed the guard. Two
intermediate GRES-map attempts selected a different physical device and were
rejected by the guard before model execution. Those logs and the original
UUID failures are retained with `_failure.log` suffixes. The final retries use
the full-node physical index and explicit UUID, matching the five workers
that initialized successfully.

Continuation entrypoint:
[`run_priority100_serial.py`](run_priority100_serial.py). Current per-episode
logs and worker ledgers are under [`run_priority100`](run_priority100). Model
weights and locally modified upstream clone are untracked experiment
artifacts, not committed project dependencies.

## Decode validation update (2026-09-25 20:32 UTC)

The isolated per-GPU MIOpen cache has now passed VAE decode for fourteen
four-shot episodes in the resume batch (priorities 5, 6, 9, 10, 13–16, 19–22,
29 and 30). Their videos all validate as H.264, 832x480, 16 fps and 20.06 s;
full worker wall times are 2,805–2,861 s. Together with previously completed
priority 2 and already-valid priority 1, there are 16 validated outputs.

At the 20:31 UTC log check, active six-shot runs were at 32–33/50 steps and
averaging about 89.5 s/step. Expect their next VAE decode to start in about
25–27 minutes (around 20:56–20:59 UTC). The dedicated eight-shot p7/p8 retries
were at 6/50, around 140 s/step, projecting their decode about 1h42m later
(around 22:13 UTC). These are denoising-based estimates; successful six/eight-
shot decode has not yet been observed.

After completing successful four-shot episodes, several worker processes
immediately failed their next launch because the UUID-bound GPU guard found
residual VRAM with 0% utilization. Those workers exited. This is separate from
the MIOpen decode failure and should be resolved from the worker guard logs
before reusing affected cards. Consequently the original 24-worker capacity
is no longer fully active, and no revised full-priority-100 ETA is claimed.
