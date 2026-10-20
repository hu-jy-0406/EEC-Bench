#!/usr/bin/env python3
"""CPU structural test of official HoloCine at 512 and configurable text length.

Run on an allocated compute node, not a login node. This uses randomly
initialized tiny dimensions, not the pretrained UMT5/14B checkpoints. Official
class definitions and the actual inline window-mask statements are executed
without rewriting their AST. A pass establishes shape/position/information
reachability in those components, NOT pretrained long-prompt generation quality.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_t5(path):
    spec = importlib.util.spec_from_file_location("official_holocine_t5", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def extract_attention(path, torch, rearrange):
    tree = ast.parse(path.read_text())
    names = {"flash_attention", "RMSNorm", "AttentionModule", "CrossAttention"}
    nodes = [node for node in tree.body
             if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
    assert {node.name for node in nodes} == names
    scope = {"torch": torch, "nn": torch.nn, "F": torch.nn.functional,
             "rearrange": rearrange, "FLASH_ATTN_3_AVAILABLE": False,
             "FLASH_ATTN_2_AVAILABLE": False, "SAGE_ATTN_AVAILABLE": False}
    # Every tested call supplies a mask. The official mask branch uses PyTorch
    # SDPA directly; no FlashAttention/SageAttention or substitute kernel is used.
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), scope)
    return scope["CrossAttention"], {
        node.name: {"start": node.lineno, "end": node.end_lineno} for node in nodes}


def extract_mask(path):
    tree = ast.parse(path.read_text())
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == "model_fn_wan_video")
    candidates = []
    for node in ast.walk(function):
        if isinstance(node, ast.Try):
            targets = {sub.id for statement in node.body for sub in ast.walk(statement)
                       if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store)}
            if {"L_text_ctx", "global_mask", "shot_table", "attn_mask"} <= targets:
                candidates.append(node)
    assert len(candidates) == 1, "Official inline mask block is missing or ambiguous"
    node = candidates[0]
    # Execute exactly the production try-body. Deliberately omit only its
    # exception-swallowing wrapper so a test failure cannot silently disable masks.
    code = compile(ast.Module(body=node.body, type_ignores=[]), str(path), "exec")
    return code, {"start": node.body[0].lineno, "end": node.body[-1].end_lineno,
                  "ast_sha256": hashlib.sha256(ast.dump(ast.Module(
                      body=node.body, type_ignores=[])).encode()).hexdigest()}


def official_mask(code, torch, context, query, ranges):
    scope = {"torch": torch, "x": query, "context": context,
             "clip_feature": None, "clip_embdding": None,
             "dit": SimpleNamespace(require_clip_embedding=False),
             "text_cut_positions": {"global": [0, 31], "shots": ranges},
             "shot_indices": torch.arange(len(ranges)).unsqueeze(0),
             "h": 1, "w": 1, "kwargs": {"prompt": "synthetic test input"}}
    exec(code, scope)
    result = scope["attn_mask"]
    assert result is not None
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1]
                        / "generation_feasibility_20260921/repos/HoloCine")
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("dynamic_context_validation.json"))
    parser.add_argument("--text-len", type=int, default=1215,
                        help="Target length from full original-input audit; must exceed 1024")
    parser.add_argument("--threads", type=int, default=1)
    args = parser.parse_args()
    if args.text_len <= 1024:
        parser.error("--text-len must exceed 1024 to test tokens beyond both 512 and 1024")
    text_len = args.text_len
    late_token = max(1024, text_len - 24)
    tested_tokens = [(700, 2), (late_token, 3)]
    import torch
    from einops import rearrange
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    torch.manual_seed(1024)
    repo = args.repo.resolve()
    encoder_path = repo / "diffsynth/models/wan_video_text_encoder.py"
    dit_path = repo / "diffsynth/models/wan_video_dit.py"
    pipeline_path = repo / "diffsynth/pipelines/wan_video_holocine.py"
    t5 = load_t5(encoder_path)
    CrossAttention, attention_spans = extract_attention(dit_path, torch, rearrange)
    mask_code, mask_span = extract_mask(pipeline_path)
    result = {
        "status": "running", "device": "cpu", "dtype": "float32", "seed": 1024,
        "baseline_text_len": 512, "target_text_len": text_len,
        "tested_context_tokens": [token for token, _ in tested_tokens],
        "validation_scope": "Official code with random tiny weights; structural validation only",
        "not_validated": ["pretrained UMT5 weights", "pretrained 14B diffusion weights",
                          "video generation", "ROCm GPU kernels", "long-prompt generation quality"],
        "repo": str(repo), "torch_version": torch.__version__,
        "source_files": {str(p.relative_to(repo)): sha256(p)
                         for p in (encoder_path, dit_path, pipeline_path)},
        "official_attention_definitions": attention_spans,
        "official_inline_mask_body": mask_span,
        "mask_behavior": "Original inclusive slicing and padding policy preserved unchanged",
        "tests": {},
    }
    with torch.inference_mode():
        encoder = t5.WanTextEncoder(vocab=128, dim=32, dim_attn=32, dim_ffn=64,
                                   num_heads=4, num_layers=1, num_buckets=32,
                                   shared_pos=False, dropout=0).eval()
        ids = torch.randint(0, 128, (1, text_len))
        encoded_512 = encoder(ids[:, :512], torch.ones(1, 512, dtype=torch.long))
        encoded_target = encoder(ids, torch.ones(1, text_len, dtype=torch.long))
        assert tuple(encoded_512.shape) == (1, 512, 32)
        assert tuple(encoded_target.shape) == (1, text_len, 32)
        assert torch.isfinite(encoded_512).all() and torch.isfinite(encoded_target).all()
        position = encoder.blocks[0].pos_embedding
        bias512, bias_target = position(512, 512), position(text_len, text_len)
        assert tuple(bias_target.shape) == (1, 4, text_len, text_len)
        torch.testing.assert_close(bias512, bias_target[:, :, :512, :512], rtol=0, atol=0)
        altered_ids = ids.clone()
        altered_ids[:, late_token] = (altered_ids[:, late_token] + 1) % 128
        altered_encoded = encoder(altered_ids, torch.ones(1, text_len, dtype=torch.long))
        tail_delta = (encoded_target[:, late_token] - altered_encoded[:, late_token]).abs().max().item()
        prefix_delta = (encoded_target[:, :512] - altered_encoded[:, :512]).abs().max().item()
        assert tail_delta > 0 and prefix_delta > 0
        result["tests"]["official_t5"] = {
            "shapes": [list(encoded_512.shape), list(encoded_target.shape)],
            "bias_target_shape": list(bias_target.shape),
            "bias_prefix_exactly_matches_512": True,
            "changed_token_index": late_token,
            "changed_late_token_output_delta": tail_delta,
            "changed_late_token_prefix_output_delta": prefix_delta,
        }

        ranges512 = [[32, 255], [256, 511]]
        ranges_target = ranges512 + [[512, 767], [768, text_len - 1]]
        query = torch.randn(1, 4, 32)
        mask512 = official_mask(mask_code, torch, encoded_512, query[:, :2], ranges512)
        mask_target = official_mask(mask_code, torch, encoded_target, query, ranges_target)
        assert tuple(mask512.shape) == (1, 1, 2, 512)
        assert tuple(mask_target.shape) == (1, 1, 4, text_len)
        torch.testing.assert_close(mask512, mask_target[:, :, :2, :512], rtol=0, atol=0)
        assert (mask_target[0, 0, :, 10] == 0).all()
        for token, own_shot in tested_tokens:
            assert mask_target[0, 0, own_shot, token].item() == 0
            assert all(mask_target[0, 0, other, token].item() == -1e4
                       for other in range(4) if other != own_shot)
        result["tests"]["official_window_mask"] = {
            "shapes": [list(mask512.shape), list(mask_target.shape)],
            "prefix_exactly_matches_512": True, "shared_global_visible": True,
            "token_700_visible_only_to_shot_2": True,
            "late_token_visible_only_to_shot_3": {"token_index": late_token, "passed": True},
        }

        attention = CrossAttention(dim=32, num_heads=4, has_image_input=False).eval()
        out512 = attention(query[:, :2], encoded_512, attn_mask=mask512)
        out_target = attention(query, encoded_target, attn_mask=mask_target)
        assert tuple(out512.shape) == (1, 2, 32)
        assert tuple(out_target.shape) == (1, 4, 32)
        assert torch.isfinite(out512).all() and torch.isfinite(out_target).all()
        deltas = {}
        # Perturb a post-encoder context vector to isolate the real CrossAttention
        # mask. T5 is bidirectional, so changing IDs before encoding is not a test
        # of cross-attention isolation alone.
        for token, own_shot in tested_tokens:
            changed_context = encoded_target.clone()
            changed_context[:, token] += torch.linspace(-2, 2, 32)
            changed_out = attention(query, changed_context, attn_mask=mask_target)
            per_shot_delta = (changed_out - out_target).abs().amax(dim=(0, 2))
            assert per_shot_delta[own_shot].item() > 0
            assert all(per_shot_delta[other].item() == 0
                       for other in range(4) if other != own_shot)
            deltas[str(token)] = per_shot_delta.tolist()
        # At 512, the same prefix context/mask is exactly unchanged by a tail-only
        # perturbation: those vectors are absent, unlike the target-length path.
        torch.testing.assert_close(attention(query[:, :2], changed_context[:, :512],
                                            attn_mask=mask512),
                                   attention(query[:, :2], encoded_target[:, :512],
                                             attn_mask=mask512), rtol=0, atol=0)
        result["tests"]["official_cross_attention"] = {
            "shapes": [list(out512.shape), list(out_target.shape)],
            "late_token_perturbation_per_shot_deltas": deltas,
            "512_context_cannot_consume_tail_vectors": True,
        }
    result["status"] = "pass"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": "pass", "output": str(args.output),
                      "scope": result["validation_scope"]}))


if __name__ == "__main__":
    main()
