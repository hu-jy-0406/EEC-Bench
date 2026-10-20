import torch,traceback
print('TORCH',torch.__version__,torch.version.hip,flush=True)
print('DEVICE',torch.cuda.get_device_name(0),flush=True)
try:
 import flash_attn
 print('FLASH',flash_attn.__version__,flush=True)
 q=torch.randn(1,128,4,64,device='cuda',dtype=torch.bfloat16)
 y=flash_attn.flash_attn_func(q,q,q);torch.cuda.synchronize()
 ref=torch.nn.functional.scaled_dot_product_attention(q.transpose(1,2),q.transpose(1,2),q.transpose(1,2)).transpose(1,2)
 print('FLASH_PASS',y.shape,(y-ref).abs().max().item(),flush=True)
except Exception:traceback.print_exc()
