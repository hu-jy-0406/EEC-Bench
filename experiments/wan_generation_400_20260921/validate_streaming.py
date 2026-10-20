#!/usr/bin/env python3
import gc
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parent
FEAS=ROOT.parent/'generation_feasibility_20260921'
sys.path[:0]=[str(FEAS/'wan_deps'),str(FEAS/'deps'),str(FEAS/'repos/Wan2.2')]
import torch
from wan import WanT2V
from wan.configs import WAN_CONFIGS
from streaming import StreamingWan
from campaign import write_json,worker

cfg=WAN_CONFIGS['t2v-A14B']
prompt=json.loads((ROOT/'input_queue_400.jsonl').read_text().splitlines()[0])['shots'][0]['wan_prompt_en']
settings=dict(size=(832,480),frame_num=5,shift=cfg.sample_shift,sampling_steps=2,
    guide_scale=cfg.sample_guide_scale,seed=20260921,offload_model=True)
result={'settings':settings,'prompt':prompt,'started':time.time()}
t=time.perf_counter()
model=WanT2V(cfg,str(FEAS/'models/Wan2.2-T2V-A14B'),device_id=0,t5_cpu=False,init_on_cpu=True,convert_model_dtype=True)
result['standard_load_seconds']=time.perf_counter()-t
t=time.perf_counter();reference=model.generate(prompt,**settings).cpu();result['standard_seconds']=time.perf_counter()-t
del model;gc.collect();torch.cuda.empty_cache()
t=time.perf_counter();model=StreamingWan(cfg,str(FEAS/'models/Wan2.2-T2V-A14B'));result['stream_load_seconds']=time.perf_counter()-t
t=time.perf_counter();actual=model.generate(prompt,**settings).cpu();result['stream_seconds']=time.perf_counter()-t
result.update(max_abs_difference=(reference-actual).abs().max().item(),exact_equal=torch.equal(reference,actual),
    shape=list(actual.shape),finite=bool(torch.isfinite(actual).all()),completed=time.time())
write_json(ROOT/'streaming_validation.json',result)
print('STREAM_VALIDATION',json.dumps(result),flush=True)
assert result['exact_equal'],'Memory-only adaptation changed output; do not deploy'
del model,reference,actual;gc.collect();torch.cuda.empty_cache()
worker(SimpleNamespace(worker='node306_gpu5',memory_mode='stream'))
