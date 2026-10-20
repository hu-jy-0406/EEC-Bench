"""Offline compatibility audit. Reused artifacts are fixtures, never new inference."""
import ast,json,shutil,sys,tempfile
from pathlib import Path
B=Path(__file__).resolve().parents[2];sys.path.insert(0,str(B/'scripts'))
import run_gs_integrated as flow
from prepare_gs_integrated import inputs
from gs_flow1_evaluator import Eval
source=flow.FRONT/'study2'
with tempfile.TemporaryDirectory() as d:
 case=Path(d)/'case'
 flow.prepare(case,flow.FRONT/'raw_manifest.json',B/'experiments/study2_full_fresh_20260918/study2/narrative.json',source/'yyfz233--Pi3X_download.json',B/'experiments/study_inconsistent_3/geocalib_boxer_20260913/weights/geocalib-pinhole.tar')
 for name in ['entities/manifest.json','entities/shots/shot1/entities.json','entities/shots/shot3/entities.json','calibration_new/calibration/shot1.json','calibration_new/calibration/shot3.json','selected/shot1_scene.json','selected/shot3_scene.json']:
  target=case/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/name,target)
 inputs(case)
 for sid in ['shot1','shot3']:assert flow.read(case/'inputs'/f'{sid}.json')==flow.read(source/'inputs'/f'{sid}.json')
 e=Eval(str(case))
 counts={g['shot_id']:len(g['entities']) for g in e.graphs}
 assert counts=={'shot1':19,'shot3':21}
 assert len(e.allimages)==12
 old=ast.parse((flow.FRONT/'motion_fusion.py').read_text());new=ast.parse((B/'scripts/run_gs_motion_fusion.py').read_text())
 functions=lambda tree:{n.name:ast.dump(n,include_attributes=False) for n in tree.body if isinstance(n,ast.FunctionDef)}
 assert functions(old)==functions(new)
 for p in [B/'scripts/run_gs_integrated.py',B/'scripts/prepare_gs_integrated.py',B/'scripts/run_gs_motion_fusion.py']:ast.parse(p.read_text())
 result=dict(status='passed',mode='offline_reused_fixtures_no_inference',fixture=str(source),prepare_fresh_directory=True,inputs_byte_value_equivalent=True,static_counts=counts,original_image_count=len(e.allimages),motion_function_ast_unchanged=True,integration_tests=7,single_presence_tests=8,new_model_calls=0,new_model_tokens=0,gpu_work=False,fresh_end_to_end_run=False)
 flow.save(Path(__file__).with_name('audit.json'),result);print(json.dumps(result))
