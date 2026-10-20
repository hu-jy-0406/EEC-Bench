import torch
import torch.nn.functional as F
from torch.nn.attention import SDPBackend, sdpa_kernel


torch.manual_seed(20260925)
device = "cuda"
q = torch.randn((1, 4, 256, 64), device=device, dtype=torch.bfloat16)
k = torch.randn_like(q)
v = torch.randn_like(q)
mask = torch.zeros((256, 256), device=device, dtype=torch.bool)
mask[:, :32] = True
mask[:32, :32] = True
mask[32:128, 32:128] = True
mask[128:, 128:] = True
reference = F.scaled_dot_product_attention(q, k, v, attn_mask=mask)
torch.cuda.synchronize()
print("device", torch.cuda.get_device_name(), "reference", tuple(reference.shape))

for backend in (SDPBackend.FLASH_ATTENTION, SDPBackend.EFFICIENT_ATTENTION):
    try:
        with sdpa_kernel(backend):
            result = F.scaled_dot_product_attention(q, k, v, attn_mask=mask)
            torch.cuda.synchronize()
        error = (result.float() - reference.float()).abs().max().item()
        print(backend.name, "supported", "max_abs_diff", error)
    except Exception as exc:
        torch.cuda.synchronize()
        print(backend.name, "unsupported", type(exc).__name__, str(exc).splitlines()[0])
