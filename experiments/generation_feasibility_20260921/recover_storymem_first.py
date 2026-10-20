import os,time,json,logging,sys
from pathlib import Path
r=Path(__file__).resolve().parent
logging.basicConfig(level=logging.INFO,format='[%(asctime)s] %(levelname)s: %(message)s',handlers=[logging.StreamHandler(sys.stdout)])
from extract_keyframes import save_keyframes
import torch
st=time.monotonic()
save_keyframes(str(r/'outputs/storymem_official/01_01.mp4'))
torch.cuda.synchronize()
out=dict(seconds=time.monotonic()-st,retained=[p.name for p in sorted((r/'outputs/storymem_official').glob('*keyframe*.jpg'))],source='original completed first-shot mp4; no diffusion rerun')
(r/'storymem_first_keyframe_recovery.json').write_text(json.dumps(out,indent=2));print('KEYFRAME_RECOVERY',out,flush=True)
