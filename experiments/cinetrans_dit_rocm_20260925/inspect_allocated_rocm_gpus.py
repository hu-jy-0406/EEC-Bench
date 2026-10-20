#!/usr/bin/env python3
"""Read-only summary of AMD GPUs on a node already allocated to this user."""

import json
import re
import socket
import subprocess


def run(args):
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


def main():
    host = socket.gethostname()
    summary = run(["rocm-smi", "--showuse", "--showmeminfo", "vram", "--showuniqueid"])
    kfd = run(["rocm-smi", "--showpids"])
    devices = {}
    for match in re.finditer(r"GPU\[(\d+)\].*?Unique ID:\s*(\S+)", summary):
        idx = int(match.group(1))
        devices[idx] = {"index": idx, "uuid": match.group(2)}
    for idx, card in devices.items():
        use = re.search(rf"GPU\[{idx}\].*?GPU use \(%\):\s*(\d+)", summary)
        mem = re.search(rf"GPU\[{idx}\].*?VRAM Total Used Memory \(B\):\s*(\d+)", summary)
        card["use_pct"] = int(use.group(1)) if use else None
        card["vram_used_bytes"] = int(mem.group(1)) if mem else None
        card["pids"] = []

    kfd_pids = []
    in_table = False
    for line in kfd.splitlines():
        if line.startswith("PID") and "PROCESS NAME" in line:
            in_table = True
            continue
        if in_table:
            match = re.match(r"\s*(\d+)\s+\S+", line)
            if match:
                kfd_pids.append(int(match.group(1)))
    mapping_complete = True
    for pid in sorted(set(kfd_pids)):
        mapped = run(["rocm-smi", "--showpidgpus", str(pid)])
        match = re.search(r"is using (\d+) DRM device\(s\):\s*([0-7 \n]*)", mapped)
        if not match:
            if re.search(r"is using 0 DRM device", mapped):
                continue
            mapping_complete = False
            continue
        count = int(match.group(1))
        indexes = [int(x) for x in match.group(2).split()]
        if count != len(indexes):
            mapping_complete = False
            continue
        for idx in indexes:
            if idx in devices:
                devices[idx]["pids"].append(pid)

    load = os_loadavg()
    for card in devices.values():
        card["available"] = bool(
            mapping_complete
            and card["use_pct"] == 0
            and card["vram_used_bytes"] is not None
            and card["vram_used_bytes"] < 100_000_000
            and not card["pids"]
        )
        print(json.dumps({"host": host, "loadavg": load, **card}, sort_keys=True))
    if not devices:
        print(json.dumps({"host": host, "loadavg": load, "status": "no_readable_gpu_inventory"}))


def os_loadavg():
    try:
        return list(__import__("os").getloadavg())
    except (AttributeError, OSError):
        return None


if __name__ == "__main__":
    main()
