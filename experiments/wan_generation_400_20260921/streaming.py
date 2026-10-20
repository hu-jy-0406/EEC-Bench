"""Memory transport only: original Wan forward/sampling, disk-backed idle weights.

Original FP32 expert tensors are cast on CPU exactly as official .to(bfloat16),
then copied one parameter at a time. Inactive models have meta parameters instead
of independent 27 GiB host copies. No quantization, sampling or prompt changes.
"""
import contextlib
import fcntl
import gc
import json
from pathlib import Path
import socket
import time
import types

import torch
from accelerate import init_empty_weights
from safetensors import safe_open
from wan.text2video import WanT2V
from wan.modules.model import WanModel
from wan.modules.t5 import T5EncoderModel, umt5_xxl
from wan.modules.tokenizers import HuggingfaceTokenizer
from wan.modules.vae2_1 import Wan2_1_VAE

ROOT=Path(__file__).resolve().parent

@contextlib.contextmanager
def loader_lock():
    # Serialize checkpoint copies on each node to bound temporary CPU RAM/I/O.
    path=ROOT/'loader_locks'/f'{socket.gethostname()}.lock'
    path.parent.mkdir(exist_ok=True)
    with path.open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        yield

def bind_disk_transport(model, source, dtype):
    names={name for name,_ in model.named_parameters()}
    assert not list(model.named_buffers()), 'Unexpected registered buffer: audit needed'
    source=Path(source)
    if source.is_dir():
        index=json.loads((source/'diffusion_pytorch_model.safetensors.index.json').read_text())['weight_map']
        assert set(index)==names,(set(index)-names,names-set(index))
        shards={f:sorted(k for k,v in index.items() if v==f) for f in sorted(set(index.values()))}
    else:
        shards=None

    def assign(name,tensor,device):
        parent,_,leaf=name.rpartition('.')
        module=model.get_submodule(parent) if parent else model
        old=module._parameters[leaf]
        assert tuple(tensor.shape)==tuple(old.shape),(name,tensor.shape,old.shape)
        # Explicit CPU conversion is bit-identical to the original constructor.
        module._parameters[leaf]=torch.nn.Parameter(tensor.to(dtype=dtype).to(device),requires_grad=False)

    def load(this,device):
        device=torch.device(device)
        if next(this.parameters()).device==device:return this
        assert device.type=='cuda'
        started=time.perf_counter()
        with loader_lock(),torch.no_grad():
            if shards:
                for filename,keys in shards.items():
                    with safe_open(str(source/filename),framework='pt',device='cpu') as handle:
                        for key in keys:
                            tensor=handle.get_tensor(key)
                            assign(key,tensor,device)
                            del tensor
            else:
                state=torch.load(str(source),map_location='cpu',mmap=True,weights_only=True)
                assert set(state)==names,(set(state)-names,names-set(state))
                for key in sorted(state):assign(key,state[key],device)
                del state
            torch.cuda.synchronize()
        gc.collect()
        print('STREAM_LOAD',source.name,round(time.perf_counter()-started,3),flush=True)
        return this

    def unload(this,*args,**kwargs):
        for module in this.modules():
            for key,param in tuple(module._parameters.items()):
                if param is not None and param.device.type!='meta':
                    module._parameters[key]=torch.nn.Parameter(torch.empty_like(param,device='meta'),requires_grad=False)
        # freq tensors are tiny, deterministic nonparameter buffers; keep exact values.
        gc.collect()
        torch.cuda.empty_cache()
        return this

    def to(this,*args,**kwargs):
        device=kwargs.get('device',args[0] if args else None)
        assert device is not None,'Unexpected dtype-only conversion'
        if torch.device(device).type=='cpu':return unload(this)
        return load(this,device)

    model.to=types.MethodType(to,model)
    model.cpu=types.MethodType(unload,model)
    model.disk_load=types.MethodType(load,model)
    return model

class StreamingWan(WanT2V):
    def __init__(self,config,checkpoint_dir):
        self.device=torch.device('cuda:0');self.config=config;self.rank=0
        self.t5_cpu=False;self.init_on_cpu=True
        self.num_train_timesteps=config.num_train_timesteps
        self.boundary=config.boundary;self.param_dtype=config.param_dtype
        self.vae_stride=config.vae_stride;self.patch_size=config.patch_size
        self.sp_size=1;self.sample_neg_prompt=config.sample_neg_prompt
        ckpt=Path(checkpoint_dir)
        # T5 constructor normally duplicates a large checkpoint in host RAM.
        enc=T5EncoderModel.__new__(T5EncoderModel)
        enc.text_len=config.text_len;enc.dtype=config.t5_dtype;enc.device=torch.device('cpu')
        enc.checkpoint_path=str(ckpt/config.t5_checkpoint)
        enc.tokenizer_path=str(ckpt/config.t5_tokenizer)
        with init_empty_weights():
            t5=umt5_xxl(encoder_only=True,return_tokenizer=False,dtype=config.t5_dtype,device='meta')
        t5.eval().requires_grad_(False)
        enc.model=bind_disk_transport(t5,ckpt/config.t5_checkpoint,config.t5_dtype)
        enc.tokenizer=HuggingfaceTokenizer(name=enc.tokenizer_path,seq_len=config.text_len,clean='whitespace')
        self.text_encoder=enc
        with loader_lock():
            self.vae=Wan2_1_VAE(vae_pth=str(ckpt/config.vae_checkpoint),device=self.device)
        for attr,folder in [('low_noise_model',config.low_noise_checkpoint),('high_noise_model',config.high_noise_checkpoint)]:
            with init_empty_weights():
                expert=WanModel.from_config(str(ckpt/folder))
            expert.eval().requires_grad_(False)
            assert not expert.freqs.is_meta,'RoPE must retain original CPU values'
            setattr(self,attr,bind_disk_transport(expert,ckpt/folder,config.param_dtype))

    def _prepare_model_for_timestep(self,t,boundary,offload_model):
        high=t.item()>=boundary
        target=self.high_noise_model if high else self.low_noise_model
        other=self.low_noise_model if high else self.high_noise_model
        if next(other.parameters()).device.type!='meta':other.cpu()
        if next(target.parameters()).device.type!='cuda':target.disk_load(self.device)
        return target
