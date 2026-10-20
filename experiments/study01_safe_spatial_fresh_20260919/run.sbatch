#!/bin/bash
#SBATCH --job-name=gs-study01-fresh
#SBATCH --partition=faculty
#SBATCH --account=faculty-acc
#SBATCH --qos=stqos
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:mi210:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=01:30:00
#SBATCH --output=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/study01_safe_spatial_fresh_20260919/logs/slurm-%j.log
set -euo pipefail
cd /vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=4
exec /vast/users/guangyi.chen/anaconda3/bin/python /vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/study01_safe_spatial_fresh_20260919/run_batch.py
