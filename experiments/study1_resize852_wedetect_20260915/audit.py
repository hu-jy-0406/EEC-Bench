import json,sys
from pathlib import Path
import cv2,numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'EECBench/scripts'))
import run_wedetect_shot_entities as io
from run_isolated_shot_static_3d import owned_compute_job
owned_compute_job();cv2.setNumThreads(1)
inputs=io.read(OUT/'inputs.json');assert len(inputs)==12
for f in inputs:
 assert io.sha(f['source'])==f['source_sha256'] and io.sha(f['resized'])==f['resized_sha256']
 original=np.asarray(Image.open(f['source']).convert('RGB'))
 converted=np.asarray(Image.open(f['resized']).convert('RGB'))
 assert original.shape==(480,854,3) and converted.shape==(480,852,3)
 assert np.array_equal(cv2.resize(original,(852,480),interpolation=cv2.INTER_LINEAR),converted)
raw=0
for condition in ['original','resized']:
 for sid in ['shot1','shot3']:
  er=OUT/(condition+'_'+sid)/'entities';shot=io.read(er/'manifest.json')['shots'][0]
  io.load_detections(er/'detections',[shot])
  for f in shot['frames']:
   p=er/'detections'/sid/f"frame_{f['frame_id']:06d}"/'raw_forward.npz'
   with np.load(p) as d:
    assert d['scores'].shape[0]==8400 and d['boxes_letterbox'].shape==(8400,4)
    raw+=8400
assert raw==201600
runtime=io.read(OUT/'detector_runtime.json');prior=io.read(ROOT/'EECBench/experiments/study01_shot1_original_jpeg_20260915/detector_runtime.json')
for k in ['python','torch','numpy','seed','threads','weights_sha256','source_hashes','adapter_sha256','policy']:
 assert runtime[k]==prior[k],k
assert runtime['status']=='success'
comparison=io.read(OUT/'comparison.json');assert all(f['original_matches_historical_labels_boxes'] for f in comparison['frames'])
audit=dict(status='pass',source_hashes_unchanged=12,exact_resize_pixel_replays=12,frames_detected=24,raw_proposals=raw,previous_runtime_weights_source_and_policy_equal=True,original_labels_boxes_reproduced=12,max_historical_score_delta=max(f['max_historical_score_delta'] for f in comparison['frames']),new_codex_calls=0)
io.dump(OUT/'audit.json',audit);print(json.dumps(audit,indent=2))
