#!/usr/bin/env python3
"""Fail-closed idle-GPU guard; bind ROCr by UUID, not ordinal."""

import os
import re
import subprocess
import sys
import time


def run(args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT)


def normalize_gpu_id(value):
    """Return ROCr's 16-hex-digit GPU id, padding short rocm-smi ids."""
    value = value.removeprefix("GPU-").removeprefix("0x").lower()
    if not re.fullmatch(r"[0-9a-f]{1,16}", value):
        raise SystemExit(f"Invalid GPU UUID: {value!r}")
    return value.zfill(16)


idx = int(sys.argv[1])
requested_uuid = sys.argv[2]
expected_id = normalize_gpu_id(requested_uuid)
cmd = sys.argv[3:]

text = run([
    "rocm-smi", "-d", str(idx), "--showuse", "--showmeminfo", "vram",
    "--showuniqueid",
])
print(text, flush=True)
use = re.search(r"GPU\[" + str(idx) + r"\].*GPU use \(%\):\s*(\d+)", text)
mem = re.search(r"VRAM Total Used Memory \(B\):\s*(\d+)", text)
actual_id_match = re.search(r"Unique ID:\s*0x([0-9a-f]+)", text, re.IGNORECASE)
actual_id = actual_id_match[1].lower().zfill(16) if actual_id_match else None
if not (
    use
    and mem
    and int(use[1]) == 0
    and int(mem[1]) < 100_000_000
    and actual_id == expected_id
):
    raise SystemExit("GPU not idle or UUID mismatch")

pids = run(["rocm-smi", "--showpids"])
print(pids, flush=True)
for pid in re.findall(r"^\s*(\d+)\s+", pids, re.MULTILINE):
    mapping = run(["rocm-smi", "--showpidgpus", pid])
    print(mapping, flush=True)
    match = re.search(r"DRM device\(s\):\s*\n([0-9 ]+)", mapping)
    if not match:
        if re.search(r"is using 0 DRM device", mapping):
            continue
        raise SystemExit("Cannot verify process GPU mapping")
    if idx in [int(value) for value in match[1].split()]:
        raise SystemExit("Resident GPU process")

bound_uuid = f"GPU-{expected_id}"
os.environ["ROCR_VISIBLE_DEVICES"] = bound_uuid
for key in ["HIP_VISIBLE_DEVICES", "CUDA_VISIBLE_DEVICES"]:
    os.environ.pop(key, None)
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["MKL_NUM_THREADS"] = "4"
print("GUARD PASS", time.time(), "visible", idx, "UUID", bound_uuid, flush=True)
os.execvp(cmd[0], cmd)
