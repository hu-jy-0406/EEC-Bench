#!/usr/bin/env python3
"""Run an existing GS stage with only model transport replaced by Gemini."""
import runpy
import sys
from pathlib import Path
from gs_gemini_backend import install

ALLOWED = {'run_wedetect_shot_entities.py', 'run_gs_motion_fusion.py', 'run_gs_flow1_stage.py'}

if __name__ == '__main__':
    stage = sys.argv[1]
    if stage not in ALLOWED:
        raise ValueError('Unsupported Gemini stage')
    install()
    sys.argv = [str(Path(__file__).with_name(stage))] + sys.argv[2:]
    if stage == 'run_wedetect_shot_entities.py':
        import run_wedetect_shot_entities
        run_wedetect_shot_entities.main()
    else:
        runpy.run_path(sys.argv[0], run_name='__main__')
