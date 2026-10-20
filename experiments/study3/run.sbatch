#!/bin/bash
#SBATCH --job-name=eec-study3-identity
#SBATCH --partition=faculty
#SBATCH --account=faculty-acc
#SBATCH --qos=stqos
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:mi210:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=00:30:00
#SBATCH --output=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/study3/logs/slurm-%j.log
set -euo pipefail
cd /vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=4
exec /vast/users/guangyi.chen/anaconda3/bin/python EECBench/experiments/study3/run.py
