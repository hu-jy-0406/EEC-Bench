import sys,traceback
from pathlib import Path
r=Path(__file__).resolve().parent
sys.path[:0]=[str(r/'deps'),str(r/'repos'/sys.argv[1])]
try:
 if sys.argv[1]=='HoloCine':from diffsynth.pipelines.wan_video_holocine import WanVideoHoloCinePipeline
 else:import wan
 print('IMPORT_OK',sys.argv[1],flush=True)
except Exception:traceback.print_exc();sys.exit(1)
