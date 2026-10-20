#!/usr/bin/env python3
"""Prevent two campaign recovery launches from racing for the same empty GPU."""
import fcntl
import os
from pathlib import Path
import socket
import sys

root=Path(__file__).resolve().parent
path=root/'gpu_leases'/f'{socket.gethostname()}_{sys.argv[2]}.lock'
path.parent.mkdir(exist_ok=True)
fd=os.open(path,os.O_RDWR|os.O_CREAT,0o600)
try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:raise SystemExit('Another campaign process holds this GPU lease')
os.set_inheritable(fd,True)
guard=root.parent/'study2_detection_only_fresh_20260918/guard_gpu.py'
os.execv(sys.executable,[sys.executable,str(guard),*sys.argv[1:]])
