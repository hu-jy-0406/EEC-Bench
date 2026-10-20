import json,sys,os,time
from pathlib import Path
H=Path(__file__).resolve().parent;B=H.parents[1];O=H/'study2'
sys.path.insert(0,str(B/'scripts'))
from run_isolated_shot_static_3d import owned_compute_job
import run_geocalib_boxer as impl
owned_compute_job()
assert os.environ.get('ROCR_VISIBLE_DEVICES','').startswith('GPU-')
manifest=json.loads((H/'raw_manifest.json').read_text())
# Override the legacy frozen() loader: this fresh calibration sees raw JPEGs only.
impl.frozen=lambda:{s['shot_id']:s for s in manifest['shots']}
assert not (O/'calibration_new/calibration').exists()
impl.calibrate(O/'calibration_new','cuda')
