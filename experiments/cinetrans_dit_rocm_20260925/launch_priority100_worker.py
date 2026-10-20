#!/usr/bin/env python3
"""Resolve this task's physical ROCm card UUID, then start one guarded worker."""

import csv
import os
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
RUNNER = HERE / "run_priority100_serial.py"
RUN_ID = "resume_miopen_20260925"
JOB_ID = "214135"
WORKER_COUNT = 22


def main() -> None:
    if len(sys.argv) == 3:
        worker_index, gpu_index = map(int, sys.argv[1:])
        start_priority, end_priority = 3, 100
        run_id = RUN_ID
        worker_count = WORKER_COUNT
        skip_priorities = (7, 8)
    elif len(sys.argv) == 4:
        gpu_index, priority = map(int, sys.argv[1:3])
        worker_index = 0
        worker_count = 1
        start_priority = end_priority = priority
        run_id = sys.argv[3]
        skip_priorities = ()
    else:
        raise SystemExit(
            "usage: launch_priority100_worker.py WORKER_INDEX GPU_INDEX "
            "or GPU_INDEX PRIORITY RUN_ID"
        )
    if not 0 <= worker_index < worker_count:
        raise SystemExit(f"invalid worker index: {worker_index}")
    if not 0 <= gpu_index < 8:
        raise SystemExit(f"invalid physical GPU index: {gpu_index}")

    output = subprocess.check_output(
        ["rocm-smi", "--showuniqueid", "--csv"], text=True
    )
    rows = csv.DictReader(line for line in output.splitlines() if line.strip())
    matches = [row for row in rows if row.get("device") == f"card{gpu_index}"]
    if len(matches) != 1:
        raise SystemExit(f"cannot resolve UUID for physical card{gpu_index}")
    uuid = matches[0]["Unique ID"].strip().lower().removeprefix("0x").zfill(16)

    command = [
        sys.executable, str(RUNNER),
        "--job-id", JOB_ID,
        "--start-priority", str(start_priority),
        "--end-priority", str(end_priority),
        "--worker-count", str(worker_count),
        "--worker-index", str(worker_index),
        "--gpu-index", str(gpu_index),
        "--gpu-uuid", f"GPU-{uuid}",
        "--run-id", run_id,
    ]
    for priority in skip_priorities:
        command.extend(("--skip-priority", str(priority)))
    print(
        f"CineTrans worker={worker_index} card={gpu_index} uuid=GPU-{uuid}",
        flush=True,
    )
    os.execv(command[0], command)


if __name__ == "__main__":
    main()
