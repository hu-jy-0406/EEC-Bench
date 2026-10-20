import hashlib,json,sys,subprocess
from pathlib import Path
from PIL import Image
HERE=Path(__file__).resolve().parent;BASE=HERE.parents[1]
sys.path.insert(0,str(BASE/'scripts'))
from run_geocalib_boxer import frozen
from run_isolated_shot_static_3d import owned_compute_job
owned_compute_job()
for sid,shot in frozen().items():
 shot['image_sizes']=[list(Image.open(f['path']).size) for f in shot['frames']]
 p=BASE/'experiments/study_inconsistent_3/geocalib_boxer_20260913/calibration'/f'{sid}.json'
 shot['calibration']=json.loads(p.read_text());shot['calibration_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
 dest=HERE/'inputs'/f'{sid}.json';dest.parent.mkdir(exist_ok=True);dest.write_text(json.dumps(shot,ensure_ascii=False,indent=2))
 print(sid,len(shot['entities']),len(shot['frames']))
repos={name:subprocess.check_output(['git','-C',str(BASE/'third_party'/name),'rev-parse','HEAD'],text=True).strip() for name in ['Depth-Anything-3','Pi3','dvlt','boxer','GeoCalib']}
(HERE/'source_revisions.json').write_text(json.dumps(repos,indent=2))
