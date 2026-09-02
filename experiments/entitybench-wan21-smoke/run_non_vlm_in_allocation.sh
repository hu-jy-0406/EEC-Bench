#!/bin/bash
# Run only inside an existing allocation after a physical GPU has been
# revalidated as idle. The caller must expose exactly that one GPU, e.g.:
#   srun --jobid=<job_id> --overlap --nodes=1 --ntasks=1 --cpus-per-task=8 \
#     env -u HIP_VISIBLE_DEVICES -u CUDA_VISIBLE_DEVICES \
#         ROCR_VISIBLE_DEVICES=<physical_id> \
#     bash experiments/entitybench-wan21-smoke/run_non_vlm_in_allocation.sh

set -euo pipefail

EEC_ROOT=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench
EXPERIMENT_ROOT=${EEC_ROOT}/experiments/entitybench-wan21-smoke
VACE_PYTHON=/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python
BERT_SNAPSHOT=${EXPERIMENT_ROOT}/cache/huggingface/models--google-bert--bert-base-uncased/snapshots/86b5e0934494bd15c9632b12f734a8a67f723594

if [[ -z "${SLURM_JOB_ID:-}" ]]; then
  echo "Refusing to run outside an existing Slurm allocation" >&2
  exit 2
fi
if [[ -z "${ROCR_VISIBLE_DEVICES:-}" ]]; then
  echo "Refusing to run without an explicit ROCR_VISIBLE_DEVICES binding" >&2
  exit 2
fi

export PYTHONNOUSERSITE=1
export HF_HOME=${EXPERIMENT_ROOT}/cache/huggingface-home
export HF_HUB_CACHE=${EXPERIMENT_ROOT}/cache/huggingface
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export XDG_CACHE_HOME=${EXPERIMENT_ROOT}/cache
export TORCH_HOME=${EXPERIMENT_ROOT}/cache/torch
export MIOPEN_USER_DB_PATH=${EXPERIMENT_ROOT}/cache/miopen
export MIOPEN_CUSTOM_CACHE_DIR=${EXPERIMENT_ROOT}/cache/miopen

export GDINO_CONFIG=/vast/users/guangyi.chen/anaconda3/envs/vace/lib/python3.12/site-packages/groundingdino/config/GroundingDINO_SwinT_OGC.py
export GDINO_WEIGHTS=${EXPERIMENT_ROOT}/cache/models/groundingdino_swint_ogc.pth
export GDINO_TEXT_ENCODER_PATH=${BERT_SNAPSHOT}
export GDINO_MSDA_BACKEND=pytorch
export DINO_MODEL_PATH=${EXPERIMENT_ROOT}/cache/models/dinov2-base
export CLIP_MODEL_PATH=${EXPERIMENT_ROOT}/cache/models/clip-vit-base-patch32

VISIBLE_GPU_COUNT=$(${VACE_PYTHON} -c 'import torch; print(torch.cuda.device_count())')
if [[ "${VISIBLE_GPU_COUNT}" != "1" ]]; then
  echo "Expected exactly one visible GPU, got ${VISIBLE_GPU_COUNT}" >&2
  exit 2
fi

mkdir -p ${EXPERIMENT_ROOT}/eval_results ${EXPERIMENT_ROOT}/logs
cd ${EEC_ROOT}

${VACE_PYTHON} eval/evaluate_benchmark.py \
  --results_dir experiments/entitybench-wan21-smoke/generated \
  --scripts_dir data/scripts \
  --split_json experiments/entitybench-wan21-smoke/smoke_split.json \
  --out_dir experiments/entitybench-wan21-smoke/eval_results/wan21_non_vlm_rocm \
  --method_name wan21_t2v_1.3b_smoke20_non_vlm \
  --pillars 2,3 \
  --device cuda \
  --non_vlm_only \
  --resume
