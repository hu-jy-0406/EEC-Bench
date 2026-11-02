#!/usr/bin/env python3
"""Apply camera_moves_third.json through the two contract toolchains: same steps as apply_style_and_moves.py, no style.

Owner 2026-11-01: a camera requirement that needs several shots to judge, a reverse view above all, moves to
cross_shot. Run once on a compute node, after the snapshot; tools/verify_camera_third.py compares with the backup.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply_style_and_moves as tool  # noqa: E402

tool.STYLES = {}
tool.MOVES = json.loads((tool.HERE / 'camera_moves_third.json').read_text())['moves']
tool.main()
