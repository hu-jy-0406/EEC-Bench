import json
from pathlib import Path
r=Path(__file__).resolve().parent
case=json.loads((r/'prompts/test_cases.json').read_text())[0]
(r/'prompts/storymem_case.json').write_text(json.dumps({'scenes':[{'scene_num':1,'video_prompts':case['per_shot_prompts'],'cut':[True]*len(case['per_shot_prompts'])}]},indent=2))
s=(r/'storymem_deps/hpsv3/config/HPSv3_7B.yaml').read_text().replace('"Qwen/Qwen2-VL-7B-Instruct"',json.dumps(str(r/'models/Qwen2-VL-7B-Instruct')))
# Inference does not run DeepSpeed/training; remove training-only DeepSpeed path to avoid init checks.
s=s.replace('deepspeed: hpsv3/config/ds_config/zero2.json','deepspeed: null')
(r/'prompts/storymem_hps.yaml').write_text(s)
