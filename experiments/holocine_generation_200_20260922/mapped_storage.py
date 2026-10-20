"""Retain read-only CPU mapped storage across original GPU onload/offload cycles."""
def install(pipe):
 import torch
 from diffsynth.vram_management.layers import AutoTorchModule
 original=AutoTorchModule.offload
 original_to=AutoTorchModule.to
 if not getattr(AutoTorchModule,'_mapped_installed',False):
  def staged_to(self,*args,**kwargs):
   device,dtype,non_blocking,memory_format=torch._C._nn._parse_to(*args,**kwargs)
   if getattr(self,'_mapped_storage',None) is None or device is None or device.type=='cpu':return original_to(self,*args,**kwargs)
   def convert(t):
    source=t.clone() if t.device.type=='cpu' else t
    return source.to(*args,**kwargs)
   return self._apply(convert)
  AutoTorchModule.to=staged_to
  import diffsynth.vram_management.layers as layers
  original_cast=layers.cast_to
  def staged_cast(weight,dtype,device):
   return original_cast(weight.clone() if weight.device.type=='cpu' else weight,dtype,device)
  layers.cast_to=staged_cast
  def offload(self):
   storage=getattr(self,'_mapped_storage',None)
   if storage is None:return original(self)
   if self.state!=0:
    for module,params,buffers in storage:
     for k,item in params.items():
      module._parameters[k]=None if item is None else torch.nn.Parameter(item[0],requires_grad=item[1])
     for k,v in buffers.items():module._buffers[k]=v
    self.state=0
  AutoTorchModule.offload=offload;AutoTorchModule._mapped_installed=True
 count=0
 for name in ['text_encoder','dit','dit2','vae']:
  model=getattr(pipe,name)
  for wrapper in model.modules():
   if not isinstance(wrapper,AutoTorchModule):continue
   storage=[]
   for module in wrapper.modules():
    assert all(v is None or v.device.type=='cpu' for v in [*module._parameters.values(),*module._buffers.values()])
    # Module.to may mutate Parameter.data in place; retain separate Tensor objects.
    params={k:None if v is None else (v.detach(),v.requires_grad) for k,v in module._parameters.items()}
    buffers={k:None if v is None else v.detach() for k,v in module._buffers.items()}
    storage.append((module,params,buffers))
   wrapper._mapped_storage=storage;count+=1
 return count

def install_shared_loader(root):
 """File views stay on CPU; bounded anonymous staging prevents GPU registration of file pages."""
 import json,os,struct
 import torch
 import diffsynth.models.model_manager as manager
 import diffsynth.models.utils as utils
 original=manager.load_state_dict
 prefix=str(root.resolve())+os.sep
 def load(path,torch_dtype=None,device='cpu'):
  if not str(path).startswith(prefix):return original(path,torch_dtype=torch_dtype,device=device)
  assert str(device)=='cpu'
  with open(path,'rb') as f:
   length=struct.unpack('<Q',f.read(8))[0];header=json.loads(f.read(length))
  raw=torch.from_file(str(path),shared=False,size=os.path.getsize(path),dtype=torch.uint8)
  dtypes={'BF16':torch.bfloat16,'F32':torch.float32,'F16':torch.float16,'I64':torch.int64,'I32':torch.int32,'BOOL':torch.bool}
  out={}
  for key,meta in header.items():
   if key=='__metadata__':continue
   a,b=meta['data_offsets'];value=raw[8+length+a:8+length+b].view(dtypes[meta['dtype']]).reshape(meta['shape'])
   assert torch_dtype is None or value.dtype==torch_dtype
   out[key]=value
  return out
 manager.load_state_dict=load;utils.load_state_dict=load
