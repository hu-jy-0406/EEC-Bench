#!/bin/bash
#SBATCH --job-name=eec-gdino-v2
#SBATCH --partition=faculty
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --gres=gpu:mi210:1
#SBATCH --time=01:00:00
#SBATCH --output=experiments/entity-graph-smoke/001_001.temporal_joint_v2.slurm-%j.log

set -euo pipefail

EEC_ROOT=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench
VACE_PYTHON=/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python

if [[ -z "${SLURM_JOB_ID:-}" ]]; then
  echo "Refusing to run outside a Slurm allocation" >&2
  exit 2
fi

export PYTHONNOUSERSITE=1
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-4}
export MKL_NUM_THREADS=${SLURM_CPUS_PER_TASK:-4}
export TOKENIZERS_PARALLELISM=false

cd "${EEC_ROOT}"

"${VACE_PYTHON}" scripts/extract_shot_entity_graph.py \
  experiments/entitybench-wan21-complete-20260825/generated/000020ca-f66b-3542-8ad1-5c3172105f7b__run15__i0_j19__T240/001_001.mp4 \
  --semantic-json experiments/entity-graph-smoke/001_001.codex_semantics.json \
  --output experiments/entity-graph-smoke/001_001.temporal_joint_v2.json \
  --video-id easy_smoke_episode \
  --shot-id 001_001 \
  --keep-reference-frames experiments/entity-graph-smoke/001_001.temporal_joint_v2.frames
