"""Apply unchanged numerical/witness gates to saved per-stage responses, no model call."""
import sys,json,shutil
from pathlib import Path
H=Path(__file__).resolve().parent;B=H.parents[1];sys.path.insert(0,str(B/'scripts'))
import gs_flow1_evaluator as flow
from run_isolated_shot_static_3d import owned_compute_job
from run_gs_spatial_consistency import validate_single
C=B/'experiments/study2_integrated_full_fresh_20260919/study2'
owned_compute_job()
for variant in sys.argv[1:]:
 out=H/(variant+'_gate_audit');out.mkdir(exist_ok=False)
 for name in ['inputs','selected','registration']:(out/name).symlink_to(C/name,target_is_directory=True)
 for name in ['narrative.json','matching.json','identity_review.json','identity_review_payload.json']:shutil.copy2(C/name,out/name)
 e=flow.Eval(str(out))
 def saved(stage,prompt,payload,images,schema):
  # Frozen per-stage replay: assess the new local evidence with original gate logic.
  # verify_relations was called on the old local payload; this is NOT a chained-model validation.
  return flow.read(H/variant/stage/'response.json')
 e.call=saved
 try:
  e.presence();e.spatial();flow.save(out/'audit.json',dict(valid=True,presence=flow.read(out/'presence.json')['summary'],spatial=flow.read(out/'spatial.json')['summary']))
 except Exception as exc:flow.save(out/'audit.json',dict(valid=False,error=repr(exc)))
 print(variant,flow.read(out/'audit.json'),flush=True)
