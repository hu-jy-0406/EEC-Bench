"""Optional diagnostic hook, NOT enabled in completed feasibility measurements.

Install before pipe(...). Saves the last scheduler result while it is still
available, before pipeline model offload/decoder. It does not change the returned
latent tensor. Intended for a separately labelled diagnostic retry only.
"""
import functools
from pathlib import Path

def install(pipe, path, steps):
    import torch
    original=pipe.scheduler.step
    state={'calls':0}
    @functools.wraps(original)
    def wrapped(*args,**kwargs):
        result=original(*args,**kwargs)
        state['calls']+=1
        if state['calls']==steps:
            destination=Path(path);destination.parent.mkdir(parents=True,exist_ok=True)
            torch.save({'latents':result.detach().cpu(),'scheduler_steps':steps,'dtype':str(result.dtype),'shape':list(result.shape)},destination)
            print('DIAGNOSTIC_LATENTS_SAVED',destination,flush=True)
        return result
    pipe.scheduler.step=wrapped
    return state
