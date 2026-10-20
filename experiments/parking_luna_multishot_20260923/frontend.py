#!/usr/bin/env python3
"""Fresh four-shot frontend for the prompt-bound-gated Luna registration test."""
import json, os, subprocess, sys, time
from pathlib import Path

R = Path(__file__).resolve().parent
B = R.parents[1]
sys.path.insert(0, str(B / 'scripts'))
from run_gs_integrated import prepare, read, save, FRONT, S, CPU, GEOM

case = R / 'shared' / 'parking4'
inp = R / 'inputs' / 'parking4'
gpu, uuid = sys.argv[1:]
prepare(case, inp / 'manifest.json', inp / 'narrative.json',
        FRONT / 'study2/yyfz233--Pi3X_download.json',
        B / 'experiments/study_inconsistent_3/geocalib_boxer_20260913/weights/geocalib-pinhole.tar',
        protocol='temporal_v2')
registry = B / 'experiments/parking_prompt_recovery_20260922/case/prompt_registry.json'
(case / 'prompt_registry.json').symlink_to(registry)
env = os.environ.copy()
env.update(CASE_ROOT=str(case), PYTHONPATH=str(B / 'experiments/shot_scene_boxes_goal_20260916/deps'),
           OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='4', MKL_NUM_THREADS='4')
for key, name in [('MIOPEN_USER_DB_PATH','miopen_db'),('MIOPEN_CUSTOM_CACHE_DIR','miopen_cache'),('MPLCONFIGDIR','matplotlib')]:
    p = case / 'runtime_cache' / name; p.mkdir(parents=True, exist_ok=True); env[key] = str(p)
steps = [
 ('detection', [CPU, FRONT/'guard_gpu.py', gpu, uuid, CPU, S/'run_wedetect_shot_entities.py', '--manifest',case/'raw_manifest.json','--output',case/'entities','--gpu',gpu,'--model','gpt-6-luna','--reasoning','low','--shot-workers','2','--timeout','1800']),
 ('prompt_recovery',[CPU, FRONT/'guard_gpu.py',gpu,uuid,CPU,S/'gs_shot_prompt_recovery.py','--case',case,'--registry',registry,'--workers','2','--device','cuda','--gpu',gpu,'--gpu-uuid',uuid]),
 ('geocalib',[GEOM,S/'prepare_gs_integrated.py',case,'calibrate','--all-shots']),
 ('inputs',[CPU,S/'prepare_gs_integrated.py',case,'inputs','--all-shots']),
]
for sid in ('Shot1','Shot2','Shot3','Shot4'):
    steps += [(f'pi3x_{sid}',[GEOM,FRONT/'geometry.py','--method','pi3x','--shot',sid]),
              (f'boxer_{sid}',[GEOM,FRONT/'boxer.py','--method','pi3x','--shot',sid]),
              (f'motion_{sid}',[CPU,S/'run_gs_temporal_stage.py',case,'expectation','--shot',sid,'--runtime-profile','temporal_spatial_v1'])]
state = dict(status='running', started=time.time(), stages=[])
try:
    for name, command in steps:
        t=time.time()
        with (case/(name+'.log')).open('w') as log:
            p=subprocess.run(list(map(str,command)), env=env, stdout=log, stderr=subprocess.STDOUT)
        row=dict(stage=name, seconds=time.time()-t, returncode=p.returncode); state['stages'].append(row); save(case/'frontend_runtime.json',state)
        if p.returncode: raise RuntimeError(row)
    # The isolated motion stage emits the selected scene graphs consumed by global matching.
    old = B/'experiments/parking_recovered_registration_20260922'
    sys.path.insert(0,str(old)); import model_stages
    model_stages.initial(case)
    state['status']='success'
except BaseException as exc:
    state.update(status='failed', error=repr(exc)); raise
finally:
    state.update(finished=time.time(),seconds=time.time()-state['started']); save(case/'frontend_runtime.json',state)
