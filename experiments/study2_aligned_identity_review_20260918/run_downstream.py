import sys,os
from pathlib import Path
H=Path(__file__).resolve().parent;OLD=H.parent/'study012_two_scores_20260916'
sys.path.insert(0,str(OLD))
import evaluate
from run_isolated_shot_static_3d import owned_compute_job
owned_compute_job();evaluate.H=H;evaluate.transport.PROMPTS=OLD/'prompts'
e=evaluate.Eval('study2')
assert (e.out/'identity_review_audit.json').exists(), 'Post-alignment identity review required'
getattr(e,sys.argv[1])()
