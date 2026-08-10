# EECBench execution memory

## AMD Slurm GPU policy

- The cluster is AMD/ROCm and jobs are managed by Slurm.
- The Slurm user is `guangyi.chen`; inspect current allocations with
  `squeue -u guangyi.chen`.
- Normally do not request a new GPU. Find a genuinely idle GPU within an
  allocation already owned by `guangyi.chen` and run through that allocation.
- Before launch, verify GPU utilization, VRAM use, and resident KFD processes
  from inside the allocation. A momentary 0% utilization is not sufficient if
  a model or process remains resident.
- Never overlap with or disrupt another task. Availability is transient, so
  revalidate immediately before every launch.
- Prefer `/vast/users/guangyi.chen/anaconda3/envs/vace` for Wan/video-model
  workloads unless a documented incompatibility requires another environment.

