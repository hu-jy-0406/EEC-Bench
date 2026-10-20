#!/bin/bash
#SBATCH --job-name=eec-eval
#SBATCH --account=faculty-acc
#SBATCH --partition=faculty
#SBATCH --qos=gtqos
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --gres=gpu:mi210:8
#SBATCH --mem=500G
#SBATCH --time=1-00:00:00
#SBATCH --output=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/vl_vv_multimodel_first200_run02/eval_hold.log
#SBATCH --error=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/vl_vv_multimodel_first200_run02/eval_hold.log

set -euo pipefail
echo "EVAL_NODE_ALLOCATED: $(hostname) job=${SLURM_JOB_ID} time=$(date -u)"
while true; do
  sleep 60
done
