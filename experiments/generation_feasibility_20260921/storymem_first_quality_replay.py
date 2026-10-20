import os,time,json,logging,sys,shutil,hashlib
from pathlib import Path
r=Path(__file__).resolve().parent
logging.basicConfig(level=logging.INFO,format='[%(asctime)s] %(levelname)s: %(message)s',handlers=[logging.StreamHandler(sys.stdout)])
from extract_keyframes import save_keyframes
import torch
src=r/'outputs/storymem_official/01_01.mp4';dest=r/'outputs/storymem_official/timing_replay';dest.mkdir(exist_ok=True)
assert not list(dest.glob('*keyframe*.jpg')), 'Timing replay must start with an empty memory bank'
shutil.copy2(src,dest/src.name)
st=time.monotonic();save_keyframes(str(dest/src.name));torch.cuda.synchronize();elapsed=time.monotonic()-st
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
actual=sorted(dest.glob('*keyframe*.jpg'));old=sorted(src.parent.glob('01_01_keyframe*.jpg'))
out=dict(seconds=elapsed,cpu_binding=sorted(os.sched_getaffinity(0)),video_sha256=sha(src),copy_sha256=sha(dest/src.name),retained=[p.name for p in actual],same_retained_files_and_hashes={p.name:sha(p) for p in actual}=={p.name:sha(p) for p in old},scope='unchanged official selector on identical completed first video, empty isolated memory bank, corrected CPU binding; original chain untouched; no diffusion')
(r/'storymem_first_quality_replay.json').write_text(json.dumps(out,indent=2));print('FIRST_QUALITY_TIMING_REPLAY',out,flush=True)
