"""Detect hard cuts anywhere in episode-level videos (16 fps, 208x120 gray):
a cut at frame i when diff(i-1,i) > max(12, 4 x median diff of the surrounding 2 s).
Report detected cut count vs expected shot boundaries and offset to nearest boundary."""
import json, numpy as np
from concurrent.futures import ProcessPoolExecutor
from audit import frames
def one(t):
    a = frames(t['shots'][0]['source_video']); d = np.abs(np.diff(a,axis=0)).mean(axis=(1,2))
    cuts = []
    for i in range(len(d)):
        lo, hi = max(0,i-16), min(len(d), i+17); med = np.median(np.r_[d[lo:i], d[i+1:hi]])
        if d[i] > max(12.0, 4*med): cuts.append(i+1)
    b = []; st = 0
    for s in t['shots'][:-1]: st += int(round(s['target_duration_seconds']*16)); b.append(st)
    off = [min(abs(c-x) for x in b) for c in cuts] if b else []
    return dict(model=t['model_id'], priority=t['generation_priority'], expected=len(b), detected=len(cuts), cut_frames=cuts, boundaries=b, offsets=off, frames=len(a))
if __name__ == '__main__':
    T = [json.loads(l) for l in open('../vl_vv_multimodel_first200_20260926/batch/worklist.jsonl')]
    T = [t for t in T if t['model_id'] in ('cinetrans','holocine')]
    with ProcessPoolExecutor(24) as ex: R = list(ex.map(one, T, chunksize=4))
    json.dump(R, open('cuts_detected.json','w')); print('done', len(R))
