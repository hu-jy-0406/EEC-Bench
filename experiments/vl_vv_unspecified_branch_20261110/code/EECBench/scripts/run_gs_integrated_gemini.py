#!/usr/bin/env python3
"""Independent Gemini 3.5 Flash variant of the current complete GS pipeline.

Identical arguments to run_gs_integrated.py; invoke through gemini_env.sh.
All geometry, prompt builders, codecs and scoring validators remain shared.
"""
from pathlib import Path
from gs_gemini_backend import install
install()
import run_gs_integrated as pipeline

original_plan = pipeline.plan
original_prepare = pipeline.prepare


def plan(*args, **kwargs):
    jobs = original_plan(*args, **kwargs)
    model_scripts = {'run_wedetect_shot_entities.py', 'run_gs_motion_fusion.py', 'run_gs_flow1_stage.py'}
    for job in jobs:
        command = job['command']
        for index, word in enumerate(command):
            if Path(word).name in model_scripts:
                command[index:index + 1] = [str(pipeline.S / 'run_gs_gemini_stage.py'), Path(word).name]
                break
    return jobs


def prepare(case, *args, **kwargs):
    original_prepare(case, *args, **kwargs)
    path = case / 'provenance.json'
    provenance = pipeline.read(path)
    for name in ['gs_gemini_backend.py', 'run_gs_gemini_stage.py', 'run_gs_integrated_gemini.py']:
        source = pipeline.S / name
        provenance['source_hashes'][str(source)] = pipeline.sha(source)
    provenance.update(model_backend='gemini-3.5-flash', codex_executions=0,
        experiment='model replacement; original evaluator and original frame bytes retained')
    pipeline.save(path, provenance)


pipeline.plan = plan
pipeline.prepare = prepare

if __name__ == '__main__':
    pipeline.main()
