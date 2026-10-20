#!/bin/bash
#SBATCH --job-name=eec-multishot-three
#SBATCH --partition=faculty
#SBATCH --account=faculty-acc
#SBATCH --qos=stqos
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --gres=gpu:mi210:8
#SBATCH --mem=256G
#SBATCH --time=02:00:00
#SBATCH --no-requeue
#SBATCH --output=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/multishot_registration_ab_20260922/slurm-%j.log
set -euo pipefail
cd /vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench
exec /vast/users/guangyi.chen/anaconda3/bin/python -u EECBench/experiments/multishot_registration_ab_20260922/run_parallel.py
