# HoloCine first200 production campaign — 74 GPUs running

User requested all genuinely idle allocated GPUs, adding newly allocated idle GPUs, with strict core100 then additional100, stopping at200. Queue contains200episodes/1000shots only. Wan remains paused. No new GPU allocation was requested or shared job cancelled.

Exact latest uncompressed shared Wan/StoryMem prompts and contracts are frozen under inputs/. All prompts use native HoloCine markers, text_len=tokenizer.seq_len=1519, pre-diffusion no-truncation and complete-shot-span gates. No compressed historical prompt aliases or structured-helper additions.

Parameters preserve validated feasibility runner: HoloCine14B full-attention dual experts, official BF16,832x480,16fps,80*N+1frames, cuts80*j+1,50steps,CFG5,sigma_shift5,tiledVAE,retention52GiB. Fixed short Chinese negative matches earlier feasibility runner (not the longer official demo negative). Per-episode deterministic seeds SHA256(holocine200-v1:<id>), first32bits. No sparse attention, quantization or approximate caches.

A task completes only after finite diffusion latents, finite decoded tensors, nonconstant RGB frames, full ffmpeg decode and exact frame count. Successful videos/<id> links to an immutable attempts/<id>/<attempt> directory with input/text audit, timing, contact sheet and result/checksum. Failed/interrupted attempts remain; bounded failures retry once. Strict completed-and-validated phase barrier prevents extra100 starting while any core100 is unfinished. Queue parallel ownership/barrier/retry test passes.

## Resource scheduling

controller.py runs on existing206117/node306 and polls Slurm about every120seconds. It creates per-allocation/node managers only within allocated GPU index sets. Managers inspect3 utilization samples, VRAM, KFD residents, GPU UUID, CPU cores/utilization and actual cgroup memory; per-GPU lease + fresh guard rechecks at launch. CPU cores for current campaign workers stay disjoint. Other task residents are excluded. StoryMem's independently scheduled campaign is explicitly excluded to avoid racing its startup. No Slurm resources are submitted or cancelled. Current source execution/launch status is in workers/, managers/, controller_status.json and logs/.

## Low host-memory transport validation

Most shared allocations have only64GiB host RAM. mapped_weights/ contains exact per-tensor official CPU BF16 conversions, saved once as safetensors and checked by torch.equal. Original model classes, weight converters and GPU operations are preserved. mapped_storage.py retains file-backed CPU tensor storage across GPU offloads instead of allocating one private CPU checkpoint per worker. Parameter.data mutation is avoided by storing separate Tensor views and rebuilding Parameter handles on offload. Original upstream checkout stays unchanged. Broad expansion was gated on mapped_validation.json. Six short runs (standard/file-only/mapped, each twice) show all actual loaded parameters and diffusion latents bit-exact; RGB differs by at most1/255, also observed in the original standard repeat control. Thus RGB is NOT bit-exact. Initial strict pixel equality test failed and is preserved in logs/validate_mapped_first_failed.log; diagnosis and acceptance are explicit, not silently erased. Repeated mapped onload/offload passed. This short transport comparison is not full production video quality validation.

## Operations

Run status.py for a compact read-only snapshot. STOP stops workers between episodes and managers; STOP_CONTROLLER stops only the allocation discovery loop. Do not run prepare twice or overwrite queue.json. Dead processes are requeued only after local identity/process-exit checks, or a terminal Slurm allocation; interruption history is retained. GPU occupancy is rechecked before every fresh worker. Never reset an occupied card or cancel a shared allocation. complete.json requires200successful episodes; no full-completion or end-to-end time claim yet.

All inference is local:0API calls/0billableAPI tokens/USD0 API cost. GPU/storage billing is unavailable. Historical throughput estimates used short/small-text probes and do not establish this1519-token campaign runtime.


## Startup memory incident and selected correction

The initial private-safetensors mapping expansion reached70claimed workers but failed the64GiB multi-worker host-memory check. Anonymous RAM rose to17–29GiB on sampled processes and cgroup OOM kills occurred. Expansion was immediately stopped; all67 mapped workers were stopped/reconciled (including the node306 child stopped with its supervisor), while the3 independently launched standard workers continued. Failed/interrupted attempts, logs, worker memory captures and retry histories remain. This is not a clean no-retry launch. Existing noncampaign resident processes1351487/node196,1275072/node254,622869/node284 were verified still alive;1351492 was already absent from the pre-expansion KFD inventory and later observed as a zombie. No other tasks or allocations were explicitly stopped.

Selected transport is now shared_mmap_v2: derived officialBF16 safetensors loaded with torch.from_file(shared=True), preserving actual loaded parameters. Private-to-shared mapping removes the observed anonymous page-copy growth during ROCm transfers. Actual /proc mappings are rw-s with0anonymous bytes for checkpoint mappings. Standard/shared repeat controls have identical parameters and diffusion latents; RGB remains within original implementation's1/255 repeat noise. shared_mmap_equivalence.json records4runs (2standard+2shared). Earlier6private-mmap diagnostic runs and initial failed strict-pixel test remain separate historical validation.

A full-resolution single-card production pilot on64GiB node197 entered diffusion with~1.8GiB anonymous RAM and no new OOM. Then9low-memory nodes each ran2workers: all18 entered diffusion at1.78–1.82GiB anonymous RAM each, with0OOM-kill delta against the post-incident baseline. shared_ramp_validation.json records this actual resource validation. Preparation can transiently allocate more RAM, so further workers serialize text/input preparation per node until entering diffusion. Diffusion remains parallel. resource_policy.json restored cap8 only after this staged proof; fresh host-memory/CPU/GPU guards still apply. Old raw OOM counters include history and must not be reported as new errors without a baseline comparison.

Controller/managers now keep their Slurm steps alive until their own children exit, preventing supervisor shutdown from inadvertently killing running worker children. Attempts stay monotonic across allocation interruptions, and interrupted resource-fix attempts are retained with explicit retry allowance. Wan's STOP markers remain untouched.


## Local-cache migration after network IO stall

After the shared-mapping expansion, network-backed MAP_SHARED pages caused cross-node writeback stalls (observed balance_dirty_pages and idle GPU samples). All67 mapped workers were stopped and their unfinished attempts reconciled; the3 original independent standard workers continued. local_cache_migration/ preserves termination evidence. Source prompts, seeds, model math and retry histories remain intact.

Selected transport local_shared_mmap_v3 uses one node-local /tmp/eecbench_holocine200_bf16_shared_v3 copy of the exact derived BF16 files. Streamed source SHA256 and reread destination SHA256 must match before atomic publication; per-node receipts are in local_cache_audits/. Nodes require at least file bytes plus20GiB free local storage. Cache copying uses a checked idle CPU within existing allocations. Managers recheck resources after copying before launches. Shared mapping remains within each node only. Initial local-cache restart is capped at2workers per low-memory node until live progress/memory verification; do not interpret configured eligibility as running GPU count.


## Bounded staging correction (validation in progress)

Local MAP_SHARED avoided cross-node contention but low-memory nodes still stalled during ROCm host-page registration: repeated faults, one busy CPU thread, unchanged GPU/text progress despite source-cache release and no new OOM. These attempts were stopped and retained in staged_copy_migration/. Selected candidate local_staged_mmap_v4 retains file-backed CPU originals, but clones only each current CPU tensor into transient anonymous storage before the original GPU transfer; original class forwards/precision/math are unchanged. File maps are now private and CPU-read only; GPU never registers them directly. onload/keep use the same target dtype/device and original offload restores frozen CPU views. Nonretained cast_to copies use the same staging. Equivalence and 64GiB memory pilots are separate required checks, not assumed successes.

For node307's58GiB free local disk, only low-noise expert2 uses a node-exclusive network file with a local symlink; the other~40GB stay local. Full SHA256 proof is retained. No files belonging to another task were removed. A lightweight login-side watchdog can take over controller discovery after allocation expiry; all probe/model/copy work still runs in owned compute allocations.


### Staging validation outcome

Four runs (two standard, two staged) have identical actual loaded parameters and bit-exact diffusion latents. Standard-repeat RGB noise was2/255, and both staged comparisons were also2/255. The previous1/255 hardcoded assertion therefore failed even on the standard repeat; diagnosis/logs are retained, and staged_mmap_equivalence.json explicitly accepts no more than the measured original repeat noise. This is not bit-exact RGB or full production-quality proof.

A64GiB node255 staged pilot completed33frames/2steps with the longest original prompt in104.50s. Anonymous RAM transiently peaked12.56GiB during text preparation, then remained~1.87–2.00GiB through diffusion/decode. An attempted8GiB peak gate failed; acceptance uses serialized per-node preprocessing and recorded steady tail<3GiB, not a false claim of peak<8GiB. The first pilot failed on an unwritable default MIOpen cache; the corrected pilot used a task-specific writable cache and passed. Production workers already have per-worker cache directories. Original failed logs remain.


## Final launch checkpoint — 2026-09-22 07:01 UTC

All74 currently eligible GPUs across10nodes have live verified campaign PIDs and are in full-resolution production denoising:196/197/209/255/257/295/307 each8,254/284 each7,306four. Three original standard workers continue,71 use selected local_staged_mmap_v4. Newly available node196 cards were rechecked before launch. Baseline-relative cgroup OOM-kill delta is0 on all10nodes after the initial private-mapping incident. final_live_audit/ and final_launch_audit.json contain raw GPU utilization/VRAM, actual PID/state and anonymous-memory observations. Some earlier workers completed a diffusion step; original standard workers reached13/13/6 steps. This checkpoint is launch validation, not completion of full videos; completed episodes remain0.

The queue contains only the requested200episodes/1000shots. Strict completed-core100 then additional100 barrier remains; all additional100 are still pending. Existing/newly RUNNING allocations are checked every~120seconds, with UUID/KFD/VRAM/CPU/memory guards before each launch. No new allocation was requested. Lightweight watchdog_status.json tracks controller failover; STOP_CONTROLLER stops it. Wan remains paused with both stop markers.

Current selected code is source_snapshot_staged_v4/ plus source_hashes_staged_v4.json. Use status.py, controller_status.json and worker heartbeat freshness for live progress; earlier stage reports are historical attempts, not current state. All task API usage0calls/0tokens/USD0 API; cluster/storage billing unavailable.


## 2026-09-22 — HoloCine queue/recovery audit and prompt inventories

Audited200 unique sequential ranks and exact prompt hashes;46done artifacts have matching video/result/full-decode/frame-count proof,54running,100stage2pending. Export: EECBench/experiments/holocine_generation_200_20260922/progress_snapshots/20260922T133131Z/{all,completed,unfinished}.{csv,jsonl}; full queue snapshot retained. These are dated snapshots, queue.json remains live authority. Rank79 provides actual allocation_TIMEOUT recovery: node265_gpu3→node284_gpu0,attempt2. Recovery restarts an entire episode with original prompt/seed; no diffusion checkpoint continuation. Bounded errors may become failed and need explicit handling.

Main controller remains active. Login watchdog1509028 had exited (last heartbeat11:38UTC); restarted detached with stdin/devnull, log redirection and new session, pid818767; fresh heartbeat/process verified. This improves supervisor independence without interrupting any running worker or changing model/prompts/priorities.
