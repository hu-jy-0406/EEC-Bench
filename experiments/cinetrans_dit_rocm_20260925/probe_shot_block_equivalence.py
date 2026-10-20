import torch
import torch.nn.functional as F

from wan.modules.attention import ShotBlockMask, attention


torch.manual_seed(20260925)
device = "cuda"
dtype = torch.bfloat16
lengths = (2, 1, 2)
frame_tokens = 4
query_tokens = sum(lengths) * frame_tokens
heads = 4
head_dim = 32


def compare_self():
    q = torch.randn((1, query_tokens, heads, head_dim), device=device, dtype=dtype)
    k = torch.randn_like(q)
    v = torch.randn_like(q)
    dense_mask = torch.zeros((query_tokens, query_tokens), device=device, dtype=torch.bool)
    dense_mask[:, :frame_tokens] = True
    start = 0
    for latent_count in lengths:
        end = start + latent_count * frame_tokens
        dense_mask[start:end, start:end] = True
        start = end
    reference = F.scaled_dot_product_attention(
        q.transpose(1, 2), k.transpose(1, 2), v.transpose(1, 2),
        attn_mask=dense_mask)
    actual = attention(
        q, k, v,
        attn_mask=ShotBlockMask("self", lengths, frame_tokens),
        dtype=dtype)
    return (actual.float() - reference.transpose(1, 2).float()).abs().max().item()


def compare_text():
    text_tokens = 8
    prompt_count = len(lengths) + 1
    q = torch.randn((1, query_tokens, heads, head_dim), device=device, dtype=dtype)
    k = torch.randn((1, prompt_count * text_tokens, heads, head_dim), device=device, dtype=dtype)
    v = torch.randn_like(k)
    dense_mask = torch.zeros(
        (query_tokens, prompt_count * text_tokens), device=device, dtype=torch.bool)
    start = 0
    for shot_index, latent_count in enumerate(lengths):
        end = start + latent_count * frame_tokens
        dense_mask[start:end, shot_index * text_tokens:(shot_index + 1) * text_tokens] = True
        dense_mask[start:end, -text_tokens:] = True
        start = end
    reference = F.scaled_dot_product_attention(
        q.transpose(1, 2), k.transpose(1, 2), v.transpose(1, 2),
        attn_mask=dense_mask)
    actual = attention(
        q, k, v,
        attn_mask=ShotBlockMask(
            "text", lengths, frame_tokens,
            text_tokens_per_prompt=text_tokens,
            include_global_prompt=True),
        dtype=dtype)
    return (actual.float() - reference.transpose(1, 2).float()).abs().max().item()


torch.cuda.synchronize()
print("device", torch.cuda.get_device_name())
print("self_max_abs_diff", compare_self())
print("text_max_abs_diff", compare_text())
torch.cuda.synchronize()
