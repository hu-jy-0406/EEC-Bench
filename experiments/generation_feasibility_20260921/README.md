# Generation feasibility — complete, 2026-09-21

All three models ran successfully on AMD MI210. See [REPORT.md](REPORT.md) for measured scope, fixes, video artifacts and conditional400-episode estimates; [runtime_estimates.json](runtime_estimates.json) is recomputable with estimate_completed.py.

Wan:2 full40-step shots. Holo:81-frame50-step4-shot video plus321/481/641-frame2-step length probes. Story:4 full40-step shots with actual memory chain and complete324-frame concatenation, plus isolated10-memory2-step capacity diagnostic. All task inference ended. Historical failure/recovery logs retained. No production400 batch or consistency evaluation was started.

Original dataset and production evaluation unchanged. Existing allocation reused, no new Slurm allocation; resource identifiers in historical logs are not permanent reservations. Revalidate allocation, CPU memory/affinity and GPU UUID/utilization/VRAM/KFD before reuse.
