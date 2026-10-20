import json
import hashlib
from pathlib import Path
import cv2
import numpy as np

cv2.setNumThreads(1)
ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'EECBench/experiments/study01_gs_v12_20260915'
OUT = Path(__file__).parent
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def diff(a,b):
    shapes = [list(a.shape),list(b.shape)]
    same_shape = a.shape == b.shape
    if not same_shape:
        b=cv2.resize(b,(a.shape[1],a.shape[0]),interpolation=cv2.INTER_LINEAR)
    d = np.abs(a.astype(np.int16)-b.astype(np.int16))
    return dict(original_shapes=shapes,resize_for_diagnostic=not same_shape,equal=bool(same_shape and np.array_equal(a,b)), mean_absolute_error=float(d.mean()), max_error=int(d.max()), changed_pixel_fraction=float(np.any(d,axis=2).mean()))

manifests = [json.loads((BASE/c/'entities/manifest.json').read_text())['shots'][0] for c in ['study0','study1']]
frames=[]
for f,g in zip(manifests[0]['frames'],manifests[1]['frames']):
    p,q=Path(f['path']),Path(g['path'])
    frames.append(dict(frame_id=f['frame_id'], study0_sha256=sha(p),study1_sha256=sha(q),**diff(cv2.imread(str(p)),cv2.imread(str(q)))))
videos = [ROOT/'EECBench/experiments/study/shots/study_shot1.mp4', ROOT/'EECBench/experiments/study_inconsistent_2/shots/inconsistent_study_shot1.mp4']
caps=[cv2.VideoCapture(str(p)) for p in videos]
meta=[dict(path=str(p),sha256=sha(p),fps=c.get(cv2.CAP_PROP_FPS),frame_count=c.get(cv2.CAP_PROP_FRAME_COUNT),width=c.get(cv2.CAP_PROP_FRAME_WIDTH),height=c.get(cv2.CAP_PROP_FRAME_HEIGHT)) for p,c in zip(videos,caps)]
vd=[]
while True:
    ra,a=caps[0].read();rb,b=caps[1].read()
    if not ra or not rb:
        assert ra == rb
        break
    vd.append(dict(frame_id=len(vd),**diff(a,b)))
for c in caps:c.release()
result=dict(keyframe_comparison=frames,video_metadata=meta,decoded_video_frames=vd)
(OUT/'input_comparison.json').write_text(json.dumps(result,indent=2))
print(json.dumps(dict(keyframes=frames,video_metadata=meta,decoded_frames=len(vd),equal_decoded_frames=sum(x['equal'] for x in vd),mean_video_pixel_mae=float(np.mean([x['mean_absolute_error'] for x in vd])),video_pixel_mae_range=[min(x['mean_absolute_error'] for x in vd),max(x['mean_absolute_error'] for x in vd)]),indent=2))
