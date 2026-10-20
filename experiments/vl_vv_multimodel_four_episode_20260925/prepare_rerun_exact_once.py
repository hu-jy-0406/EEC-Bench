from pathlib import Path
import json, subprocess, sys
ROOT=Path(__file__).resolve().parents[2]
SRC=Path(__file__).resolve().parent
OUT=ROOT/'experiments/vl_vv_multimodel_four_episode_exact_once_rerun_20260925'
MODELS=('veo31','wan22','storymem','holocine')
EPS=('52apMIyJVlc_s00176_n6_clean_v2','8iDEmCxXz-A_s00025_n6_clean_v2','9ugYT3Xc59s_s00093_n4_clean_v2','Wl6COOA3V6Y_s00022_n4_clean_v2')
for model in MODELS:
  for ep in EPS:
    src=SRC/model/ep
    dst=OUT/model/ep
    dst.mkdir(parents=True,exist_ok=False)
    for name in ('keyframes.json','source_videos.json'):
      (dst/name).write_bytes((src/name).read_bytes())
    subprocess.run([sys.executable,str(ROOT/'scripts/run_vl_vv_detection.py'),'prepare','--manifest',str(dst/'keyframes.json'),'--contract',str(ROOT/'experiments/episode_contracts_20260921/deliverables/episodes'/ep/'contract.json'),'--case',str(dst/'case')],check=True)
print(json.dumps({'root':str(OUT),'cases':len(MODELS)*len(EPS)}))
