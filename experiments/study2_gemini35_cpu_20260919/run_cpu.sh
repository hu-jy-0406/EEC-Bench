#!/usr/bin/env bash
set -euo pipefail
cd /vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench
export SLURM_JOB_ID=191764
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=4
exec EECBench/scripts/gemini_env.sh nice -n 19 /vast/users/guangyi.chen/anaconda3/bin/python -u EECBench/scripts/run_gs_integrated_gemini_cpu.py --manifest EECBench/experiments/study2_gemini35_cpu_20260919/manifest.json --narrative EECBench/experiments/study2_gemini35_cpu_20260919/narrative.json --output EECBench/experiments/study2_gemini35_cpu_20260919/run01 --cores 21,22,23,24
