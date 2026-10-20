#!/bin/bash
#SBATCH --job-name=eec-hold64
#SBATCH --account=faculty-acc
#SBATCH --partition=faculty
#SBATCH --qos=bgqos
#SBATCH --nodes=8
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --gres=gpu:mi210:8
#SBATCH --mem=2T
#SBATCH --time=3-00:00:00
#SBATCH --exclusive
#SBATCH --requeue
#SBATCH --output=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/gpu_hold_64_20260923/logs/slurm-%j.log
#SBATCH --error=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/gpu_hold_64_20260923/logs/slurm-%j.log

set -euo pipefail
mkdir -p /vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/gpu_hold_64_20260923/logs
printf 'HOLD_READY job=%s nodes=%s utc=%s\n' "${SLURM_JOB_ID}" "${SLURM_JOB_NODELIST}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
while true; do
  sleep 300
done
