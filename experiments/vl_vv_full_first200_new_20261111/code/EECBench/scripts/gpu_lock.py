"""Optional per-GPU lock for GPU subprocesses (owner, 2026-11-11: "应用提速").

When EECBENCH_GPU_LOCK_DIR is set, several pipelines may share one GPU: each GPU subprocess (Grounding DINO recovery,
background Grounding DINO, DINO) runs under `flock <dir>/<uuid>.lock`, so only one of them uses the GPU at a time; it
waits for the previous holder to exit, then 5 s for the GPU to settle, and only then runs the command (which keeps its
own fail-closed idle check where it has one). The API stages of the pipelines run in parallel. Unset (default): no
lock and no wait, the command is unchanged.
"""
import os
from pathlib import Path

SETTLE_SECONDS = 5


def prefix(gpu_uuid):
    """Command prefix that holds the GPU's lock while the command runs; [] when no lock directory is set."""
    folder = os.environ.get('EECBENCH_GPU_LOCK_DIR', '').strip()
    if not folder:
        return []
    if not gpu_uuid or not str(gpu_uuid).startswith('GPU-'):
        raise ValueError('The GPU lock needs the checked GPU UUID (GPU-...)')
    Path(folder).mkdir(parents=True, exist_ok=True)
    return ['flock', str(Path(folder) / f'{gpu_uuid}.lock'), 'sh', '-c', f'sleep {SETTLE_SECONDS}; exec "$@"', 'eec-gpu-lock']
