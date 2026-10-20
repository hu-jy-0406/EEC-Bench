# Wan2.2 T2V A14B AMD feasibility — complete

Two complete source-scheduled shots generated successfully on one AMD Instinct MI210, in addition to one tiny debugging smoke. This is actual model inference with full decode/finite checks, not import-only feasibility. It is not a complete four-shot episode, a 400-episode run, or a quality/consistency benchmark.

## Configuration and provenance

- Official source commit `1ea34ff48f87168174e12956e200b1d908b1c5ff`; checkpoint `Wan-AI/Wan2.2-T2V-A14B` revision `c8c270b13ee05bfa474194ac9fb07a5868a97cea`. Central download metadata remains under models/Wan2.2-T2V-A14B/download_complete.json; original FP32 expert weights retained.
- PyTorch 2.7.1+rocm6.3, ROCm 6.3.42131-fa1d09cbd, vace environment, native FlashAttention2. Original model math, no quantization. Official convert_model_dtype=True converts expert weights to bf16; CPU weight offload=True, T5 onGPU, init_on_cpu=True.
- 832×480;81frames@16fps;40UniPC steps;shift12;CFG(low/high)=3/4;original negative prompt.81frame timestamps span5.0s, MP4 playback5.0625s. Seeds20260921/20260922.
- Episode `MTYQT6fSzaE_s00091_n4_clean_v2`, first two unchanged per-shot schedules from prompts/test_cases.json. Per-shot text includes a short courtyard background; no full-episode action concatenation or future-entity leakage.
- Actual allocation206117/nodeauh7-1b-gpu-306, Slurm RAM2TiB, physical GPU2 UUID GPU-aabcddaa244a3d6e. Utilization/VRAM/KFD guard passed immediately before launch. Initial node196 waiting coordinator stopped before loading because its job RAM limit64GiB was insufficient despite abundant hostfreeRAM. No new Slurm allocation.
- Only necessary source fix: optional modality imports made lazy in wan/__init__.py, preventing unused S2V librosa import from blockingT2V. Exact patch wan_checkout.patch. No shared environment change.

## Measured timing

Load 239.817s. Model loaded once and reused across smoke and both full shots. Generation includes text encoding, transfers, denoising and VAE decoding; save and validation are separate. The tiny smoke includes first VAE kernel setup and is excluded from throughput.

| Shot | Frames | Steps | Generate s | Save s | Tensor/decode validation s | Peak allocated GiB |
|---|---:|---:|---:|---:|---:|---:|
| smoke | 5 | 2 | 116.408 | 5.325 | 5.261 | 28.536 |
| shot1 | 81 | 40 | 1535.364 | 11.938 | 8.419 | 41.357 |
| shot2 | 81 | 40 | 1532.508 | 8.136 | 7.070 | 41.327 |

Mean full-shot generate+save **1543.973s = 25.733minutes**. Measured min/max1540.644/1547.303s. Peak allocated41.357GiB, peak reserved43.727GiB. Because full-shot time exceeds20min, the bounded runner stopped after2full shots, as authorized.

For400episodes/2000shots at these settings, extrapolated single-GPU generation+save is **857.763GPUhours = 35.740days**. Observed per-shot min/max implies855.913–859.613GPUhours; this is a sample range, not a statistical confidence interval. Downloads, one-time loading, queueing, retries, quality filtering, validation and downstream evaluation are excluded. No parallel throughput scaling or2000-shot production run was measured.

## Output verification and limitations

Both full videos have finite output tensors, exact81decoded frames,832×480dimensions and saved SHA256s in wan_outputs/timings.json. First/middle/last contact sheets were visually inspected: recognizable humans and snowy courtyard with small motion, not black frames/noise. Prompt adherence is imperfect: Shot1 arms are held in front rather than clearly down and the peach neckline is not obvious; Shot2 tree is to the woman's right rather than clearly between the people. Appearance/camera/scene continuity is not scored here. Independent-shot Wan is not a native entity-memory controller.

Outputs: wan_outputs/shot1.mp4 and shot2.mp4, corresponding contact.jpg files, timings.json and summary.json. Logs logs/wan_benchmark_306.log. Reproduction runner wan_benchmark.py; launch with `srun -u --jobid=206117 --overlap -N1 -n1 -c4 bash .../run_wan_benchmark.sh --shots 4` only after fresh allocation/capacity checks. Slurm default line buffering delayed tqdm carriage-return progress in this run; use-u or compute-side log redirection in future.

Session38275 exited0. PID3851416 confirmed absent;GPU2 returned0% utilization/13475840bytesVRAM. No Wan inference remains. Local generation API usage0tokens/USD0; GPU/storage price unavailable. Parent conversation/research API usage is outside this model-runtime measurement.
