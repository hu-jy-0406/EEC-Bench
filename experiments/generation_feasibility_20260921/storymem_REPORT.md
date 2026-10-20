# StoryMem AMD feasibility

Completed: all four official 40-step shots, unchanged quality selection, recovered final concatenation, and complete decode validation. Three shots used actual earlier visual memory. A separate cap10 capacity diagnostic also completed. No 400-episode batch was launched. Two post-generation recoveries are explicitly preserved below; this was not a clean first-attempt end-to-end run.

## Tested configuration and evidence

Official StoryMem commit `052c68d2627a22a95f79dbb4d3376cc30c96f1a3`, source episode `MTYQT6fSzaE_s00091_n4_clean_v2`; original/adapted inputs are in `prompts/test_cases.json` and `prompts/storymem_case.json`. Four shots, all scene cuts. Later shots consume actual HPS/CLIP-selected earlier generated frames through the official MI2V LoRA. No first-frame continuation is imposed because these are cuts.

832×480, 81 frames at 16 fps per shot, 40 UniPC steps, guidance3.5, seed20260921 plus within-scene index, T2V shift12 / M2V shift4, official memory cap10/fix3. BF16 conversion and CPU offload; no quantization. First shot was generated independently because the parallel Wan baseline uses different guidance.

Production ran on one AMD MI210, physical GPU4 UUID `GPU-24ee801b7c402006`, existing Slurm206117/node306 (2TB requested host memory). Every GPU process launch passed utilization, VRAM, UUID and KFD residency guards. Official memory generation used four dedicated CPU cores24–27. Isolated timing/capacity validations used idle GPU2 and CPUs28–31. No new allocation or shared-environment edit. All own inference processes have exited; final GPU4 utilization/VRAM/KFD release guard passed (logs/storymem_final_gpu_release.log). The earlier job196092 had only64GB host-memory allowance despite high node-wide free RAM; its idle coordinator was stopped before full video loading.

Primary evidence: `storymem_metrics.json`, `logs/storymem_first_terminal.log`, `logs/storymem_memory_terminal.log`, `logs/storymem_official.log`; individual videos and first/middle/last frame contact sheet under `outputs/storymem_official/`. Tensor finiteness is recorded before encoding; decoded RGB statistics are in `video_audit.json`. Visual inspection of all four shots shows ordinary snowy courtyard/person imagery, without black/noise failures. This is execution feasibility, not scored identity or prompt fidelity; the first-shot arm pose differs from the prompt.

## Measured stages

All times are seconds. Generate includes text/memory conditioning, full diffusion and original VAE decoding; encode is MP4 saving. Quality is the unchanged HPSv3/CLIP selector, including its model loading.

| Shot | Input memory frames | Generate | Encode | Quality | Newly retained frames |
|---|---:|---:|---:|---:|---|
| 1 | 0 | 1608.712 | unavailable | 50.168 corrected-binding replay | frame0 |
| 2 | 1 | 1747.266 | 10.084 | 49.321 | frame0 |
| 3 | 2 | 1899.619 | 10.255 | 49.302 | none after cross-bank deduplication |
| 4 | 2 | 1851.254 | 9.866 | 71.230 | frames0,54 |

T2V initialization223.195s and M2V+LoRA initialization183.357s are separate. The official two-invocation lifecycle reloads both models for each episode; persistent workers are not implemented. Thus400episodes add400×(223.195+183.357)/3600 =45.1724 hours of model loading, excluding interpreter/guard startup. Do not charge this only once per worker.

The original first process produced its complete video and then failed during CLIP loading (returncode1; phase1979.054s). After a scoped loader repair, only original keyframe selection was recovered on that saved video, taking823.688s under the initially contended CPU binding. Multiple `srun -c4` tasks had all received CPUs0–1,64–65. Later launches reused the existing full CPU allocation and bound only their own workers to distinct cores. No other task affinity or cgroup was changed.

The independent first-quality replay with corrected binding took50.168s (HPS strict checkpoint load40.694s, CLIP load1.326s). Its copied video SHA256 and selected frame0 JPEG SHA256 match the original recovery exactly. Replay outputs are isolated in `timing_replay/` and did not modify the running bank. Keep823.688s and the failed attempt as historical validation overhead;50.168s is a composition-estimate reference, not a rewritten original measurement. First-shot encode duration was not captured. Raw wall time includes recovery and manual gaps and is not a clean uninterrupted production baseline.

The final official bank contains four selected frames: one each from shots1/2 and two from shot4. Shot4 required adaptive selector passes through thresholds0.90,0.89,0.88,0.87, explaining its longer quality time. No cap10 saturation occurred in this chain.

After the last selection, the original memory process exited1 only because `ffmpeg` was absent from its PATH. Four completed original MP4s were concatenated with the installed `imageio_ffmpeg` executable in0.112s (exit0); source now resolves this fallback explicitly. No generation or selector was repeated for this repair. Preserve `storymem_memory_status.json` (original failure) and `storymem_concat_recovery.json` (postprocess recovery) separately. Complete sequential decoding passed for all4×81frames and the324-frame/20.25s concatenation, at832×480/16fps. All four tensors are finite and all twelve sampled RGB frames have nonzero variance. See `full_decode_audit.json`, `video_audit.json` and inspected `contactsheet.jpg`.

## 400-episode composition estimate

For400first+1600memory shots, measured memory-generation mean1832.713s (observed1747.266–1899.619s), memory encode mean10.069s, memory quality mean56.617s, corrected first quality50.168s. Add400copies of both measured model initializations. The resulting sequential single-device composition is **1073.67hours (~44.74days)**, with observed low-memory minimum/maximum timing scenarios **1035.69–1103.41hours**. These are workload scenarios, not confidence bounds. Model loading alone contributes45.17hours.

The cap10 compute-shape condition described below gives **1620.03hours (~67.50days)** if all1600memory shots had its extrapolated cost. It is a separate condition, not a strict upper bound. Both estimates omit the unmeasured first-shot encoding; using measured memory encoding as an explicit proxy adds1.119hours across400first shots (mean then1074.79hours). Interpreter/guard startup, concat, recovery/manual gaps and filesystem/scheduling variability are excluded. These are composition estimates, not a measured400episode batch, nor a guaranteed future throughput.

## Cap10 diagnostic and extrapolation boundary

`outputs/storymem_capacity10_probe/metrics.json` records a separate successful81-frame,2-step test with ten distinct real first-shot frames (indices0,9,18,27,36,44,53,62,71,80). It deliberately bypasses the selector solely to test capacity, as explicitly authorized; these are not ten officially retained frames, and the original bank is untouched. Both high/low expert CFG forwards and VAE decoding completed, tensor finite. Peak PyTorch allocation49.285GiB; reserved53.652GiB. This is allocator peak, not full device residency. Two-step generate314.649s, init79.548s; no claim of two-step video quality.

Official40-step UniPC/shift4 schedule contains13 high-noise and27 low-noise steps. The diagnostic measured78.928s/high step and69.240s/low step, each already including conditional+unconditional forwards. Keeping fixed generation overhead166.481s once gives `166.481 +13*78.928 +27*69.240 =3062.032s` (~51.03min) as a cap10 compute-shape scenario. This is not measured40-step performance, a strict upper bound, or validation of6/8-shot quality. Model loading, video saving and quality selection remain separate. Details: `storymem_capacity_projection.json`.

For400episodes/2000shots, use400 first shots plus1600 memory shots. The regular low-memory estimate must derive from all actual memory-shot measurements, with load/encode/quality added separately. The tested official chain has only1–2 input memory frames, below cap10. The cap10 scenario describes higher-memory cost but cannot replace the unknown actual future selector population. Warm caches, CPU binding and per-step timing variation also confound attribution of all differences solely to memory size.

## Fixes and model provenance

`storymem_fixes.diff` preserves every source change: CLI frame/step/shift arguments honored, latent high-noise finetune checkpoint self-reference repaired (not exercised by this LoRA run), final concat restricted to shot clips to exclude `motion_frames.mp4`, local model paths, safe CLIP loading, portable ffmpeg resolution, and timing/finiteness diagnostics. HPS thresholds, CLIP thresholds, adaptive selection, bank compression and memory attention are unchanged.

The local compatibility layer `storymem_deps` uses Transformers4.45.2, tokenizers0.20.3, Diffusers0.32.2, PEFT0.14.0, Hub0.36.2 and TRL0.12.2, plus missing official-package dependencies. Shared vace supplies Torch2.7.1/ROCm6.3 and FA2.7.4; exact versions are in `storymem_versions.json`. Training-only DeepSpeed config is disabled for inference. Full HPSv3 checkpoint loads with strict=True, including rm_head; the earlier Qwen base warning about a newly initialized head precedes this strict full-checkpoint load. Separate HPS smoke succeeded; its93.22s is validation expense.

HPSv3: MizzenAI/HPSv3 commit `4f81e3e09edd82fe3c5f636444c721b592a735ca`; base: Qwen/Qwen2-VL-7B-Instruct commit `eed13092ef92e448dd6875b2a00151bd3f7db0ac`. OpenAI CLIP Azure download was blocked by proxy403. The timm mirror `timm/vit_base_patch32_clip_224.openai` commit `a6f597a30f7b82c51704746581f9a4e41421e878` declares OpenAI pretrained provenance and strictly loads into original OpenAI CLIP ViT-B/32. Identity tensor-key mapping, no reshape/retraining, only torch.save reserialization. Azure byte/element identity was not independently verifiable; see `models/CLIP/provenance.json` and preserved mirror README/config.

The old CLIP loader attempted JIT then reused a consumed file handle for torch.load, causing EOFError on the valid non-JIT checkpoint. The explicit local path now uses torch.load(path,weights_only=True) and original clip.model.build_model, with unchanged CPUfloat32 arithmetic. The recovery/replay preserved original selection behavior.

All video/reward inference is local: API calls0, tokens0, API cost USD0. Cluster monetary cost is unavailable, not zero compute cost. Source prompt construction and assistant/service expenses are outside this measurement.
