#!/bin/bash
#SBATCH --job-name=eec-storymem400
#SBATCH --account=faculty-acc
#SBATCH --partition=faculty
#SBATCH --qos=bgqos
#SBATCH --nodes=8
#SBATCH --ntasks=8
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=64
#SBATCH --gres=gpu:mi210:8
#SBATCH --mem=2T
#SBATCH --time=3-00:00:00
#SBATCH --exclusive
#SBATCH --requeue
#SBATCH --output=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/storymem_generation_400_20260922/logs/slurm-%j.log
#SBATCH --error=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/storymem_generation_400_20260922/logs/slurm-%j.log
set -euo pipefail
ROOT=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments/storymem_generation_400_20260922
PY=/vast/users/guangyi.chen/anaconda3/envs/vace/bin/python
cd "$ROOT"
"$PY" campaign.py begin-job
srun --nodes=8 --ntasks=8 --ntasks-per-node=1 --cpus-per-task=64 --gres=gpu:mi210:8 --cpu-bind=none --gpu-bind=none --kill-on-bad-exit=0 "$PY" -u "$ROOT/node.py"
"$PY" campaign.py finalize
