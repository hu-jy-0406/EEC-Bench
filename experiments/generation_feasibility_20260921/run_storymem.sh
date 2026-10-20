#!/bin/bash
set -euo pipefail
ROOT=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench
R="$ROOT/EECBench/experiments/generation_feasibility_20260921"
export PYTHONPATH="$R/storymem_deps:$R/deps:$R/repos/StoryMem"
export PYTHONNOUSERSITE=1 HF_HUB_DISABLE_XET=1 TOKENIZERS_PARALLELISM=false
export STORYMEM_CLIP_CHECKPOINT="$R/models/CLIP/ViT-B-32-openai.pt"
export STORYMEM_CLIP_ROOT="$R/models/CLIP"
export STORYMEM_HPS_CONFIG="$R/prompts/storymem_hps.yaml"
export STORYMEM_HPS_CHECKPOINT="$R/models/HPSv3/HPSv3.safetensors"
export MIOPEN_USER_DB_PATH="$R/outputs/storymem_miopen" MIOPEN_CUSTOM_CACHE_DIR="$R/outputs/storymem_miopen"
mkdir -p "$R/outputs/storymem_official" "$MIOPEN_USER_DB_PATH"
cd "$R/repos/StoryMem"
exec /vast/users/guangyi.chen/anaconda3/envs/vace/bin/python -u pipeline.py --story_script_path "$R/prompts/storymem_case.json" --t2v_model_path "$R/models/Wan2.2-T2V-A14B" --i2v_model_path "$R/models/Wan2.2-I2V-A14B" --lora_weight_path "$R/models/StoryMem/Wan2.2-MI2V-A14B" --size '832*480' --max_memory_size 10 --output_dir "$R/outputs/storymem_official" --log_file "$R/logs/storymem_official.log" --offload_model --convert_model_dtype --lora_rank 128 --mi2v --sample_steps 40 --frame_num 81 --seed 20260921 "$@"
