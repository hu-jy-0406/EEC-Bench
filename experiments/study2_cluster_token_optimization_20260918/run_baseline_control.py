import importlib.util,sys
from pathlib import Path
H=Path(__file__).resolve().parent;B=H.parents[1]
spec=importlib.util.spec_from_file_location('baseline_runner',H/'baseline_source/scripts/run_wedetect_shot_entities.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.ROOT=B.parent;m.ASSETS=H/'baseline_source/skills/wedetect-shot-entities';m.DETECTOR=B/'experiments/study_inconsistent_2/detector_upgrade_20260910'
m.main()
