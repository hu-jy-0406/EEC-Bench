"""Fresh isolated clustering on frozen detector evidence; no downstream rerun."""
import sys,time
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
import run_wedetect_shot_entities as io
SOURCE=B/'experiments/within_negative_review_20260920/full'

def one(study,sid):
    root=SOURCE/study;dest=R/study/sid
    if dest.exists():raise FileExistsError(dest)
    shots=io.load_manifest(root/'raw_manifest.json');detections=io.load_detections(root/'entities/detections',shots)
    shot=next(s for s in shots if s['shot_id']==sid)
    payload=io.make_payload(shot,detections)
    assert payload==io.read(root/'entities/shots'/sid/'input.json')
    for f in shot['frames']:assert io.sha(f['path'])==f['sha256']
    args=SimpleNamespace(prepare_only=False,model='gpt-6-astra',reasoning='medium',codex_bin='/vast/users/guangyi.chen/.local/bin/codex',timeout=1800)
    start=time.time()
    record=io.review(shot,payload,args,dest)
    record.update(seconds=time.time()-start,detector_mode='frozen_reuse',source=str(root/'entities/shots'/sid),source_input_sha256=io.sha(root/'entities/shots'/sid/'input.json'))
    io.dump(dest/'status.json',record);print(study,sid,'complete',record['entity_count'],flush=True)
    return record

if __name__=='__main__':
    io.safe_compute()
    with ThreadPoolExecutor(max_workers=3) as p:
        fs=[p.submit(one,*key) for key in [('study4','shot1'),('study4','shot3'),('study2','shot1')]]
        io.dump(R/'validation_status.json',[f.result() for f in fs])
