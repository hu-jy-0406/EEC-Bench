#!/usr/bin/env bash
set -euo pipefail
cd /vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export PATH=/vast/users/guangyi.chen/.local/bin:$PATH
exec nice -n 19 /vast/users/guangyi.chen/anaconda3/bin/python EECBench/scripts/gs_prompt_binding.py run \
 --case EECBench/experiments/pipeline_parallel_20260921/run \
 --registry EECBench/experiments/prompt_binding_study3_20260921/prompt_registry.json \
 --out EECBench/experiments/prompt_binding_study3_20260921/binding
