# HoloCine ROCm execution probe

Completed; final measured results and limitations: `HOLOCINE_REPORT.md` and `holocine_summary.json`. Historical progress notes follow. Official `HoloCine-14B-full`, both experts, bfloat16 execution, full attention. No sparse substitution or inference-cache approximation.

- Existing allocation 196092 / auh7-1b-gpu-196, physical GPU1 UUID `GPU-d6ec5a470ed40212`; every launch uses `guard_gpu.py` and fails closed on utilization, VRAM, resident KFD process or UUID mismatch.
- Environment: shared `vace` unchanged. Shared experiment `deps/` is read-only. Additional `modelscope-hub==0.4.5` installed only under `holocine_deps/`.
- Current transformers no longer exports `PretrainedConfig` through `transformers.modeling_utils`; the one-line HoloCine StepVideo import is corrected to public `transformers` imports. See `holocine_compat.patch`.
- Runner retains native staged CPU offload. Omits example's redundant `pipe.to(cuda)` after wrapping, which otherwise eagerly moves both experts and the text encoder to GPU and contradicts the wrapper's initial CPU state. Pipeline computation device remains CUDA/ROCm. VRAM retention threshold is 52 GiB (native management subtracts its 0.5 GiB buffer).
- All local model/tokenizer paths are explicit and Hugging Face offline mode is enabled for inference.
- True local UMT5 tokenizer lengths: four shots 281, six shots 397, eight shots 429. All <=512, no truncation required.
- Unified output 16 fps, 321/481/641 frames = 20/30/40 seconds of inter-frame span plus the first frame (container durations 20.0625/30.0625/40.0625 seconds). Official example uses 15 fps; the experiment deliberately changes only output fps and requested frame counts to match the other generators' target duration.
- Two-step runs are resource/timing probes, not normal-quality samples. Planned full-quality execution: 4-shot 321-frame video with official 50 steps. No 400-video batch is launched.

Authoritative live state: `logs/holocine_coordinator.json`. Per-case metrics and synchronized denoising-step timings are under `outputs/holocine/`; GPU logs under `logs/holocine_*.log`. All generation is local, zero model API calls / USD 0 API cost; cluster cost is not a monetary bill estimate.

## First loading attempt: host-memory kill, not GPU failure

The original allocation 196092 has a 64 GiB **job cgroup host-RAM limit**, despite node-wide available RAM exceeding 2 TiB. First micro process exited SIGKILL/-9 during model loading before any denoising (start 1790003210, failure 1790003411). Cgroup `memory.max=68719476736`, `memory.events` reported `oom=11, oom_kill=2` in the shared allocation; this supports host-memory pressure but these aggregate event counts must not all be attributed to this single process. GPU1 remained approximately 13 MB. Preserved log: `logs/holocine_micro_attempt1_host_oom.log`. No video or timing validation succeeded in that attempt.

Local ModelManager patch now forwards its selected `torch_dtype` into `load_state_dict`. For safetensors this casts one tensor at a time while reading, instead of retaining an entire FP32 checkpoint dictionary while converting the model. Resulting BF16 model values are unchanged. Both experts plus UMT5 still require substantially more than a safe share of the old 64 GiB allocation; no automatic retry there. Coordinator now requires explicit `--gpu-index` and `--gpu-uuid` to support a verified higher-memory existing allocation.

## Relocation and revised sampling plan

Continuing on pre-existing allocation **206117**, node **auh7-1b-gpu-306**, with a 2 TiB host-memory allowance. Resource probes use physical GPU3 / UUID `GPU-95be8fdc770fcfd7`; an independently guarded standard-sampling short probe uses physical GPU5 / UUID `GPU-413935505e32b8da`. Other resident GPUs remain untouched.

The first real 321-frame full-attention denoising step took **323.2638 seconds**, peak allocated **42.4425 GiB**. Because a 50-step 20-second sample would require roughly 4.5 hours at this rate, the parent revised the plan before that long run began: retain 321/481/641-frame **two-step** resource/decoding probes, and run **81 frames / 50 steps / 832x480 / 4 shots** in parallel. This shortened sample preserves the four-shot entity schedule but compresses the episode to approximately five seconds. It is not a 20-second standard-quality video. The obsolete 321-frame 50-step name is explicitly skipped before model loading, including if encountered by the already-running old coordinator.

The final 400-video time estimate must extrapolate denoising steps from measured full-length two-step probes; it must not claim 20/30/40-second 50-step runtimes were fully measured.

## Completed standard-sampling short probe

`outputs/holocine/4shot_5s_50step/video.mp4` contains 81 fully decoded frames at 832x480, 16 fps (5.06-second reported container duration). Actual 50-step generation: 1799.3206 seconds; model load: 82.9491 seconds; recorded wall including encoding/pixel audit/decode: 1895.9377 seconds. Peak allocated/reserved GPU memory: 30.8048/34.2910 GiB. RGB min/max 0/255, mean 88.7091, std 67.9002; all output pixels finite, nonconstant.

The saved contact sheet was visually inspected: it shows a woman in a gray coat and white knit hat, a two-person snowy courtyard wide view, the woman closer again, then the hat-wearing older man. This is direct visual evidence that standard 50-step sampling yields recognizable, prompt-related images and the requested four-shot order on ROCm. It is not a formal quality evaluation, an identity-consistency score, or a validation of 20/30/40-second 50-step quality.

After that process exited normally (0), GPU5 was freshly guarded and reused for the 641-frame 40-second two-step probe. GPU3 continues the 481-frame probe. The shared per-output lock prevents the old coordinator from running a duplicate 641-frame sample.

## Redundant coordinator launch correctly blocked

After the 481-frame run completed, the older coordinator attempted its now-redundant 641-frame launch on GPU3. Fresh guard observed 7,745,880,064 bytes VRAM already in use and correctly refused before starting inference. The independent GPU5 641-frame run was already active and remains the authoritative 40-second probe. Thus the legacy coordinator's final `failed` state records a safety-check rejection of a duplicate launch, not an HoloCine 40-second model failure. The coordinator is not restarted. No resident process was interrupted.
