"""Save inspectable CPU-only copies; historical GPU implementations stay untouched."""
import json
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parents[1];D=R/'cpu_adapters';D.mkdir(exist_ok=True)
changes=[]
def copy(source,name,replacements):
 s=source.read_text()
 for old,new in replacements:
  assert old in s,(name,old)
  s=s.replace(old,new);changes.append(dict(file=name,old=old,new=new))
 compile(s,str(D/name),'exec');(D/name).write_text(s)
 return s
base="BASE=Path("+repr(str(B))+"); HERE=Path(os.environ['CASE_ROOT'])"
front=B/'experiments/study2_detection_only_fresh_20260918'
copy(front/'geometry.py','geometry_cpu.py',[
 ("BASE=Path(__file__).resolve().parents[2]; HERE=Path(os.environ['CASE_ROOT'])",base),
 (" if not os.environ.get('ROCR_VISIBLE_DEVICES','').startswith('GPU-'):raise RuntimeError('Expected UUID guarded GPU binding')\n assert torch.cuda.is_available() and torch.cuda.device_count()==1", " assert not torch.cuda.is_available() and torch.cuda.device_count()==0, 'CPU-only run must hide all GPUs'"),
 (".to('cuda')", ".to('cpu')"),
 ("with torch.inference_mode(),torch.autocast('cuda',dtype=torch.bfloat16):pred=model(imgs[None],with_prior=False)","with torch.inference_mode():pred=model(imgs[None],with_prior=False)"),
 (" torch.cuda.synchronize();peak=torch.cuda.max_memory_allocated();del model;torch.cuda.empty_cache()", " peak=0;del model"),
 ("seconds=time.time()-start,peak_gpu_bytes=peak", "seconds=time.time()-start,execution_device='cpu',effective_precision='float32',peak_gpu_bytes=peak")])
copy(front/'boxer.py','boxer_cpu.py',[
 ("BASE=Path(__file__).resolve().parents[2]; HERE=Path(os.environ['CASE_ROOT'])",base),
 (" assert os.environ.get('ROCR_VISIBLE_DEVICES','').startswith('GPU-') and torch.cuda.is_available()", " assert not torch.cuda.is_available() and torch.cuda.device_count()==0"),
 ("device='cuda'", "device='cpu'"),
 (" del model;torch.cuda.empty_cache()", " del model")])
reg=B/'experiments/study2_full_fresh_20260918'
copy(reg/'run_matching.py','roma_cpu.py',[
 ("from common import *", "sys.path.insert(0,"+repr(str(reg))+")\nfrom common import *"),
 (" assert os.environ.get('ROCR_VISIBLE_DEVICES','').startswith('GPU-') and torch.cuda.device_count()==1", " assert not torch.cuda.is_available() and torch.cuda.device_count()==0"),
 (" model=RoMaV2();model.apply_setting('precise')", " from dataclasses import replace\n cfg=RoMaV2.Cfg();cfg=replace(cfg,descriptor=replace(cfg.descriptor,enable_amp=False),matcher=replace(cfg.matcher,enable_amp=False))\n model=RoMaV2(cfg).float();model.apply_setting('precise')\n for mod in model.modules():\n  if hasattr(mod,'enable_amp'):mod.enable_amp=False")])
(D/'calibrate_cpu.py').write_text('''import os,sys
from pathlib import Path
B=Path('''+repr(str(B))+''');sys.path.insert(0,str(B/'scripts'))
import torch
assert not torch.cuda.is_available() and torch.cuda.device_count()==0
torch.set_num_threads(4)
from run_isolated_shot_static_3d import owned_compute_job
owned_compute_job()
import run_geocalib_boxer as impl
from run_gs_integrated import read,sha
case=Path(sys.argv[1]);shots=[s for s in read(case/'entities/manifest.json')['shots'] if s['shot_id'] in ['shot1','shot3']]
for shot in shots:
 for frame in shot['frames']:assert sha(frame['path'])==frame['sha256']
assert not (case/'calibration_new/calibration').exists()
impl.frozen=lambda:{s['shot_id']:s for s in shots}
impl.calibrate(case/'calibration_new','cpu')
''')
(D/'changes.json').write_text(json.dumps(dict(device='cpu',precision='FP32 instead of GPU BF16 autocast where applicable; no numerical equality claim',original_model_settings_preserved=['weights','resolution','frame_count','thresholds','seeds','all_RoMa_pairs','precise_RoMa','geometry_fitting','model_judging'],edits=changes),indent=2)+'\n')
