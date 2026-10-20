"""Shot-cut and inter-shot similarity audit for episode-level CineTrans/HoloCine videos
and per-shot Wan2.2/StoryMem files (first-200 cohort). CPU only, read only.
cut_ratio = |frame(boundary) - frame(boundary-1)| / median within-shot consecutive diff
(16 fps, 208x120 gray). mid_sim = mean abs diff between middle frames of adjacent shots."""
import json, subprocess, numpy as np, imageio_ffmpeg
from concurrent.futures import ProcessPoolExecutor
FF = imageio_ffmpeg.get_ffmpeg_exe(); W, H = 208, 120
WL = '../vl_vv_multimodel_first200_20260926/batch/worklist.jsonl'
def frames(p):
    b = subprocess.run([FF,'-v','error','-i',p,'-vf',f'scale={W}:{H},format=gray','-f','rawvideo','-'],capture_output=True,check=True).stdout
    return np.frombuffer(b,np.uint8).reshape(-1,H,W).astype(np.float32)
def one(t):
    shots = t['shots']
    if shots[0]['source_scope'] == 'shot':
        segs = [frames(s['source_video']) for s in shots]; cuts = None
    else:
        a = frames(shots[0]['source_video']); segs = []; cuts = []; st = 0
        for s in shots:
            n = int(round(s['target_duration_seconds']*16)); segs.append(a[st:st+n])
            if st > 0 and st < len(a):
                within = np.median(np.abs(np.diff(a[max(0,st-16):st+16],axis=0)).mean(axis=(1,2)))
                cuts.append(float(np.abs(a[st]-a[st-1]).mean()/max(within,0.1)))
            st += n
    mids = [s[len(s)//2] for s in segs if len(s)]
    mid = [float(np.abs(mids[i+1]-mids[i]).mean()) for i in range(len(mids)-1)]
    return dict(model=t['model_id'], priority=t['generation_priority'], shots=len(shots), cut_ratio=cuts, mid_diff=mid)
if __name__ == '__main__':
    T = [json.loads(l) for l in open(WL)]
    T = [t for t in T if t['model_id'] in ('cinetrans','holocine','wan22','storymem')]
    with ProcessPoolExecutor(24) as ex: R = list(ex.map(one, T, chunksize=4))
    json.dump(R, open('cut_audit.json','w')); print('done', len(R))
