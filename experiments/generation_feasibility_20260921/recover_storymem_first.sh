#!/bin/bash
set -euo pipefail
R=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/generation_feasibility_20260921
export PYTHONPATH="$R/storymem_deps:$R/deps:$R/repos/StoryMem"
export PYTHONNOUSERSITE=1 TOKENIZERS_PARALLELISM=false
export STORYMEM_HPS_CONFIG="$R/prompts/storymem_hps.yaml" STORYMEM_HPS_CHECKPOINT="$R/models/HPSv3/HPSv3.safetensors" STORYMEM_CLIP_CHECKPOINT="$R/models/CLIP/ViT-B-32-openai.pt"
export MIOPEN_USER_DB_PATH="$R/outputs/storymem_miopen" MIOPEN_CUSTOM_CACHE_DIR="$R/outputs/storymem_miopen"
exec /vast/users/guangyi.chen/anaconda3/envs/vace/bin/python -u "$R/recover_storymem_first.py"
