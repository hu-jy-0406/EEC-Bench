#!/bin/bash
#SBATCH --job-name=eec-multishot-ab
#SBATCH --partition=faculty
#SBATCH --account=faculty-acc
#SBATCH --qos=stqos
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:mi210:1
#SBATCH --mem=96G
#SBATCH --time=04:00:00
#SBATCH --output=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/multishot_registration_ab_20260922/slurm-%j.log
set -euo pipefail
cd /vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench
exec /vast/users/guangyi.chen/anaconda3/bin/python -u EECBench/experiments/multishot_registration_ab_20260922/run_experiment.py
